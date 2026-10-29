#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e2e_tx_bench.py — 端到端 Testnet Sapling 转账测量脚手架

通过 Zallet 的 PCZT RPC 工作流（pczt_create -> pczt_prove -> pczt_sign ->
pczt_extract）驱动一笔真实 Sapling 转账，并用 Zebra 节点记录广播/接受/确认，
逐级计时并采样钱包与节点进程内存。

对应冻结方案：
  experiments/metadata/sapling_e2e_testnet_tx_preregistration_20261026.md
  experiments/metadata/sapling_real_input_tx_proving_scoping_note_20261026.md

实现原则：
- 仅用 Python 标准库（urllib / subprocess / csv / json / time / argparse），
  以便在装有 Docker + python3 的任意主机直接运行，无需 pip 安装。
- 不修改证明器；所有计时用单调时钟；内存从 `docker stats` 采样容器。
- Zallet 仍 Beta，pczt_* 精确参数随版本变化：先跑 --discover 取 OpenRPC 模式核对，
  或把参数以 --create-params / --prove-params 等 JSON 文件传入。

运行前置：z3 栈（zebra + zallet）已在 Testnet 同步完成（见 README_runbook.md）。
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# JSON-RPC 调用（Zcash 风格：method + params 数组）
# ---------------------------------------------------------------------------

def json_rpc_call(url, method, params=None, auth=None, timeout=600, rpc_id=1):
    """向一个 Zcash 风格 JSON-RPC 端点发请求，返回 result。"""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": method,
        "params": params if params is not None else [],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth:
        # auth 形如 "user:pass"
        import base64
        token = base64.b64encode(auth.encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + token
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if "error" in body and body["error"] is not None:
                raise RuntimeError("RPC error on %s: %s" % (method, body["error"]))
            return body.get("result")
        except (urllib.error.URLError, RuntimeError) as e:
            if attempt == 2:
                raise
            print("  [warn] %s 失败，重试 (%d/3): %s" % (method, attempt + 1, e))
            time.sleep(3)


def discover(url, auth):
    """取 OpenRPC schema，打印 pczt_* 方法的精确签名。"""
    schema = json_rpc_call(url, "rpc.discover", [], auth=auth)
    if not schema:
        print("rpc.discover 返回空；请手查 `zallet rpc help`")
        return
    methods = schema.get("methods", [])
    print("=== Zallet RPC 中 pczt_* 方法签名 ===")
    found = False
    for m in methods:
        if m.get("name", "").startswith("pczt_"):
            found = True
            params = m.get("params", [])
            print("• %s(%s)" % (m["name"], ", ".join(
                p.get("name", "?") for p in params)))
    if not found:
        print("(未发现 pczt_* 方法——当前构建未实现 PCZT，或方法命名不同)")


# ---------------------------------------------------------------------------
# 内存采样（docker stats；可选 PID 回退）
# ---------------------------------------------------------------------------

def parse_mem_usage(s):
    """解析 '123.4MiB / 2.0GiB' -> (used_bytes, limit_bytes)。"""
    try:
        used_s, limit_s = s.split("/")
    except ValueError:
        return (None, None)
    return (_to_bytes(used_s), _to_bytes(limit_s))


def _to_bytes(tok):
    tok = tok.strip().upper().replace("IB", "IB")
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3,
             "TB": 1024**4, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}
    for suf, mul in units.items():
        if tok.endswith(suf):
            try:
                return int(float(tok[:-len(suf)].strip()) * mul)
            except ValueError:
                return None
    try:
        return int(float(tok))
    except ValueError:
        return None


def _proc_rss_bytes(pid):
    """读取 /proc/<pid>/status 的 VmRSS（字节）。原生（非 Docker）内存采样用。"""
    try:
        with open("/proc/%s/status" % pid, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1]) * 1024
    except Exception:
        return None
    return None


class MemorySampler(threading.Thread):
    """后台线程：按 interval 采样内存到 CSV。

    原生模式（pids 非空）读 /proc/<pid>/status VmRSS；
    Docker 模式（默认）用 `docker stats`。
    """

    def __init__(self, containers, interval, out_csv, stop_event, pids=None):
        super().__init__(daemon=True)
        self.pids = [p.strip() for p in (pids or "").split(",") if p.strip()]
        if self.pids:
            self.containers = ["pid:" + p for p in self.pids]
        else:
            self.containers = [c.strip() for c in containers.split(",") if c.strip()]
        self.interval = interval
        self.out_csv = out_csv
        self.stop_event = stop_event
        self.rows = []  # (ts, container, used, limit)

    def run(self):
        with open(self.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ts_epoch", "container", "mem_used_bytes", "mem_limit_bytes"])
            f.flush()
            while not self.stop_event.is_set():
                ts = time.time()
                if self.pids:
                    for pid in self.pids:
                        try:
                            used = _proc_rss_bytes(pid)
                        except Exception as e:
                            used = None
                            print("  [mem采样] pid %s 失败: %s" % (pid, e))
                        if used is not None:
                            label = "pid:" + pid
                            w.writerow([f"{ts:.3f}", label, used, ""])
                            self.rows.append((ts, label, used, None))
                else:
                    for c in self.containers:
                        try:
                            out = subprocess.run(
                                ["docker", "stats", "--no-stream",
                                 "--format", "{{.MemUsage}}", c],
                                capture_output=True, text=True, timeout=10)
                            used, limit = parse_mem_usage(out.stdout.strip())
                            if used is not None:
                                w.writerow([f"{ts:.3f}", c, used, limit or ""])
                                self.rows.append((ts, c, used, limit))
                        except Exception as e:
                            print("  [mem采样] %s 失败: %s" % (c, e))
                f.flush()
                self.stop_event.wait(self.interval)

    def peak(self, container):
        vals = [r[2] for r in self.rows if r[1] == container and r[2] is not None]
        return max(vals) if vals else None


# ---------------------------------------------------------------------------
# 阶段计时
# ---------------------------------------------------------------------------

def stage(name, fn, timings):
    """执行 fn 并记录其单调时钟耗时（毫秒）到 timings[name]。"""
    t0 = time.monotonic()
    result = fn()
    dt_ms = (time.monotonic() - t0) * 1000.0
    timings[name] = dt_ms
    print("  [计时] %-22s %.1f ms" % (name, dt_ms))
    return result


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(args):
    os.makedirs(args.outdir, exist_ok=True)
    run_id = time.strftime("run_%Y%m%d_%H%M%S")
    run_dir = os.path.join(args.outdir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    mem_csv = os.path.join(run_dir, "memory_timeseries.csv")
    timings_csv = os.path.join(run_dir, "stage_timings.csv")
    summary_json = os.path.join(run_dir, "run_summary.json")

    print("=== 端到端 Testnet Sapling 转账测量 ===")
    print("run_id = %s" % run_id)

    # 载入可配置参数（Beta 易变，必须核对）
    create_params = _load_json_file(args.create_params) or [{"address": args.recipient, "amount": args.amount}]
    prove_params = _load_json_file(args.prove_params) or ["<PCZT_FROM_PREVIOUS_STAGE>"]
    sign_params = _load_json_file(args.sign_params) or ["<PCZT_FROM_PREVIOUS_STAGE>"]
    extract_params = _load_json_file(args.extract_params) or ["<PCZT_FROM_PREVIOUS_STAGE>"]

    timings = {}
    stop = threading.Event()
    sampler = MemorySampler(args.containers, args.sample_interval, mem_csv, stop, pids=args.pids)
    sampler.start()

    t_start = time.monotonic()
    timings["t_start_epoch"] = t_start

    # 阶段 1：输入选择 + witness 准备（pczt_create = Creator+Constructor）
    pczt = stage("pczt_create", lambda: json_rpc_call(
        args.zallet_url, "pczt_create", create_params, auth=args.zallet_auth), timings)

    # 阶段 2：构造 + 证明（pczt_prove）
    # 若上一阶段返回的是包装结构，取其中的 pczt 字段；否则原样传递
    pczt_arg = pczt.get("pczt") if isinstance(pczt, dict) and "pczt" in pczt else pczt
    prove_params_resolved = _resolve_pczt(prove_params, pczt_arg)
    proved = stage("pczt_prove", lambda: json_rpc_call(
        args.zallet_url, "pczt_prove", prove_params_resolved, auth=args.zallet_auth), timings)

    # 阶段 3：签名 + 序列化（pczt_sign -> pczt_extract）
    pczt_arg2 = proved.get("pczt") if isinstance(proved, dict) and "pczt" in proved else proved
    signed = stage("pczt_sign", lambda: json_rpc_call(
        args.zallet_url, "pczt_sign",
        _resolve_pczt(sign_params, pczt_arg2), auth=args.zallet_auth), timings)
    pczt_arg3 = signed.get("pczt") if isinstance(signed, dict) and "pczt" in signed else signed
    extracted = stage("pczt_extract", lambda: json_rpc_call(
        args.zallet_url, "pczt_extract",
        _resolve_pczt(extract_params, pczt_arg3), auth=args.zallet_auth), timings)

    # 提取原始交易 hex 与大小（字段名以 rpc.discover 为准；常见为 hex / rawtx）
    rawtx = None
    tx_size = None
    if isinstance(extracted, dict):
        rawtx = extracted.get("hex") or extracted.get("rawtx")
        tx_size = extracted.get("size") or extracted.get("tx_size")
    if rawtx is None and isinstance(extracted, str):
        rawtx = extracted

    # 阶段 4：广播 + 等待确认
    txid = None
    if rawtx is not None:
        # Zallet 可能在 extract 时已自动广播；先尝试 Zebra sendrawtransaction
        try:
            txid = stage("sendrawtransaction", lambda: json_rpc_call(
                args.zebra_url, "sendrawtransaction", [rawtx],
                auth=_cookie_auth(args.zebra_cookie)), timings)
        except Exception as e:
            print("  [warn] sendrawtransaction 失败（可能已由 Zallet 广播）: %s" % e)

        if txid:
            # Regtest：广播后挖块把交易纳入区块并驱动确认（regtest 不自动出块）
            if args.mine_blocks and args.mine_blocks > 0:
                try:
                    stage("mine_blocks", lambda: json_rpc_call(
                        args.zebra_url, "generate", [args.mine_blocks],
                        auth=_cookie_auth(args.zebra_cookie)), timings)
                except Exception as e:
                    print("  [warn] mine_blocks 失败: %s" % e)
            # 等待节点接受（进入 mempool）
            stage("wait_accept", lambda: _poll_until(
                args.zebra_url, "getmempoolentry", [txid], _truthy,
                auth=_cookie_auth(args.zebra_cookie), timeout=120), timings)
            # 等待进入区块
            stage("wait_in_block", lambda: _poll_until(
                args.zebra_url, "getrawtransaction", [txid, 1],
                lambda r: isinstance(r, dict) and r.get("blockhash"),
                auth=_cookie_auth(args.zebra_cookie), timeout=600), timings)
            # 等待 N 确认
            stage("wait_confirmations", lambda: _poll_until(
                args.zebra_url, "getrawtransaction", [txid, 1],
                lambda r: isinstance(r, dict) and (r.get("confirmations") or 0) >= args.confirmations,
                auth=_cookie_auth(args.zebra_cookie), timeout=1800), timings)
    else:
        print("  [warn] 未取到原始交易 hex，跳过广播/确认阶段（请核对 pczt_extract 返回字段）")

    # 阶段 5：钱包识别收款
    stage("wait_wallet_recognize", lambda: _poll_until(
        args.zallet_url, "getwalletinfo", [],
        lambda r: isinstance(r, dict), auth=args.zallet_auth, timeout=300), timings)

    t_end = time.monotonic()
    stop.set()
    sampler.join(timeout=5)

    timings["t_end_epoch"] = t_end
    timings["total_wall_ms"] = (t_end - t_start) * 1000.0

    # 写阶段计时
    with open(timings_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stage", "ms"])
        for k, v in timings.items():
            if k.endswith("_epoch"):
                continue
            w.writerow([k, "%.3f" % v if isinstance(v, float) else v])

    # 写汇总
    summary = {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "network": "testnet",
        "recipient": args.recipient,
        "amount": args.amount,
        "confirmations_target": args.confirmations,
        "txid": txid,
        "tx_size_bytes": tx_size,
        "stage_timings_ms": {k: v for k, v in timings.items() if isinstance(v, (int, float))},
        "mem_peak_bytes": {
            c: sampler.peak(c) for c in sampler.containers
        },
        "versions": {
            # 由调用方在运行前填写或通过 --meta 传入；此处留空占位
            "zebra": args.zebra_version or "FILL_IN",
            "zallet": args.zallet_version or "FILL_IN",
        },
        "host": args.host_meta or "FILL_IN",
        "note": "确认相关阶段（sendrawtransaction/wait_*）与本地证明阶段（pczt_*）分表解读；"
                "一次性成本（首同步、faucet）不在本文件。",
    }
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n=== 完成 ===")
    print("输出目录: %s" % run_dir)
    print("交易大小: %s bytes" % tx_size)
    for c in sampler.containers:
        pk = sampler.peak(c)
        print("  %s 峰值内存: %s" % (c, ("%d bytes" % pk) if pk else "N/A"))
    print("总耗时(墙钟): %.1f ms" % timings["total_wall_ms"])
    return run_dir


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _load_json_file(path):
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_pczt(params_template, pczt_value):
    """把模板里的占位符替换为上一阶段真实 pczt 字符串。"""
    if (isinstance(params_template, list) and len(params_template) == 1
            and params_template[0] == "<PCZT_FROM_PREVIOUS_STAGE>"):
        return [pczt_value]
    return params_template


def _cookie_auth(cookie_path):
    """从 Zebra cookie 文件读取 'user:pass' 形式的鉴权串。"""
    if not cookie_path or not os.path.exists(cookie_path):
        return None
    with open(cookie_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    # Zebra cookie 格式通常是 '__cookie__:<hex>' 或 'user:pass'
    if ":" in content:
        return content
    return "__cookie__:" + content


def _poll_until(url, method, params, predicate, auth=None, timeout=600, interval=2.0):
    """轮询某 RPC 直到 predicate(result) 为真或超时。"""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = json_rpc_call(url, method, params, auth=auth, timeout=30)
            if predicate(last):
                return last
        except Exception:
            pass
        time.sleep(interval)
    print("  [warn] %s 在 %.0fs 内未达预期（最后值: %r）" % (method, timeout, last))
    return last


def _truthy(x):
    return bool(x)


def build_arg_parser():
    p = argparse.ArgumentParser(description="端到端 Testnet Sapling 转账测量脚手架")
    p.add_argument("--zallet-url", default="http://127.0.0.1:40232")
    p.add_argument("--zallet-auth", default=None,
                   help="Zallet RPC 鉴权，形如 user:pass")
    p.add_argument("--zebra-url", default="http://127.0.0.1:18232")
    p.add_argument("--zebra-cookie", default=None,
                   help="Zebra RPC cookie 文件路径（共享卷 /var/run/auth/.cookie）")
    p.add_argument("--recipient", required=True)
    p.add_argument("--amount", type=int, required=True)
    p.add_argument("--confirmations", type=int, default=2)
    p.add_argument("--mine-blocks", type=int, default=0,
                   help="Regtest 专用：广播后挖 N 个块以驱动交易进入区块/确认"
                        "（regtest 不自动出块，必须显式挖块；默认 0 不挖）")
    p.add_argument("--containers", default="z3-testnet-zebra-1,z3-testnet-zallet-1",
                   help="docker stats 采样容器名，逗号分隔（Docker 模式）")
    p.add_argument("--pids", default="",
                   help="原生模式：逗号分隔的进程 PID，采样其 /proc/<pid>/status VmRSS")
    p.add_argument("--sample-interval", type=float, default=1.0)
    p.add_argument("--outdir", default="../raw/e2e_testnet_tx")
    p.add_argument("--discover", action="store_true",
                   help="仅取 OpenRPC schema 核对 pczt_* 签名后退出")
    p.add_argument("--dry-run", action="store_true",
                   help="校验连通性与参数，打印计划调用，不真正发交易")
    p.add_argument("--create-params", default=None, help="pczt_create 参数 JSON 文件")
    p.add_argument("--prove-params", default=None)
    p.add_argument("--sign-params", default=None)
    p.add_argument("--extract-params", default=None)
    p.add_argument("--zebra-version", default=None, help="复现元数据：Zebra 版本")
    p.add_argument("--zallet-version", default=None)
    p.add_argument("--host-meta", default=None)
    return p


def main():
    args = build_arg_parser().parse_args()

    if args.discover:
        print("== Zallet RPC 发现 ==")
        discover(args.zallet_url, args.zallet_auth)
        print("== Zebra RPC 发现 ==")
        discover(args.zebra_url, _cookie_auth(args.zebra_cookie))
        return

    # 连通性自检
    try:
        json_rpc_call(args.zallet_url, "getwalletinfo", [], auth=args.zallet_auth, timeout=20)
        print("[ok] Zallet RPC 可达")
    except Exception as e:
        print("[fatal] Zallet RPC 不可达: %s" % e)
        sys.exit(1)

    if args.dry_run:
        print("[dry-run] 计划调用：")
        print("  pczt_create  -> %s" % (_load_json_file(args.create_params)
                                         or [{"address": args.recipient, "amount": args.amount}]))
        print("  pczt_prove   -> <上一阶段 pczt>")
        print("  pczt_sign    -> <上一阶段 pczt>")
        print("  pczt_extract -> <上一阶段 pczt>")
        print("  广播/确认通过 Zebra RPC (cookie=%s)" % args.zebra_cookie)
        print("[dry-run] 退出，未发交易。")
        return

    run(args)


if __name__ == "__main__":
    main()
