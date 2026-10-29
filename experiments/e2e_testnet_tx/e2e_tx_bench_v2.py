#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e2e_tx_bench_v2.py — z3 栈（Zebra + Zallet beta）PCZT 全流程端到端测量（N 轮重复）

与 v1 的差别（均为实测校准，非猜测）：
  1. 参数形状对齐 zallet beta 的 OpenRPC 实际签名：
       pczt_create(from, amounts, minconf, privacy_policy, fund_source)
       pczt_prove(pczt)
       pczt_sign(pczt, privacy_policy, strict)
       pczt_extract(pczt)
     其中 pczt 是 **base64 字符串**（不是对象）。
  2. 阶段间不再需要 _resolve_pczt 的占位符魔法，直接串 result["pczt"]。
  3. pczt_extract 只返回 {hex, txid, stored}，**不广播**；广播改走 zebra
     `sendrawtransaction`，再用 `generate` 挖块驱动入块与确认。
  4. 每个阶段前显式等待钱包与节点链尖追平（数值比较，忽略 locked 字段——
     zallet beta 在追平后 locked 常驻 true，属展示层 bug）。
  5. 内存采样改为读 /proc/<pid>/status VmRSS（原生进程，非 docker）。
  6. N 轮循环 + 逐阶段长表 CSV + 中位数汇总 CSV。

用法：
  python3 e2e_tx_bench_v2.py --rounds 5 --amount-zec 10 \
      --account-uuid 5fd7056a-3e6e-455f-b75d-d80b0556fea9 \
      --outdir /mnt/d/Research/zcash-sapling-engineering/experiments/e2e_testnet_tx/raw/e2e_regtest_v2

只读自检（不建交易，验证连通性与同步）：
  python3 e2e_tx_bench_v2.py --preflight
"""

import argparse
import base64
import csv
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# JSON-RPC
# ---------------------------------------------------------------------------


class RPCError(RuntimeError):
    def __init__(self, method, err):
        self.method = method
        self.err = err
        super().__init__("%s -> %s" % (method, err))


def rpc(url, method, params=None, auth=None, timeout=600.0):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params if params is not None else [],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth:
        tok = base64.b64encode(auth.encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + tok
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 401/500 也可能带 JSON-RPC 错误体
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            raise RuntimeError("%s: HTTP %s" % (method, e.code))
    if body.get("error") is not None:
        raise RPCError(method, body["error"])
    return body.get("result")


def read_cookie(path):
    """读 cookie 文件，返回 'user:pass'。zallet 的 .cookie 就是 user:pass 形式。"""
    if not path:
        return None
    with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
        s = f.read().strip()
    if not s:
        return None
    return s if ":" in s else "__cookie__:" + s


# ---------------------------------------------------------------------------
# 同步等待
# ---------------------------------------------------------------------------


def status(zallet_url, auth):
    return rpc(zallet_url, "getwalletstatus", [], auth=auth, timeout=30) or {}


def heights(zallet_url, auth):
    s = status(zallet_url, auth)
    wt = (s.get("wallet_tip") or {}).get("height")
    nt = (s.get("node_tip") or {}).get("height")
    fs = s.get("fully_synced_height")
    return wt, nt, fs, s.get("locked")


def wait_synced(zallet_url, auth, timeout=3600.0, interval=1.0, label=""):
    """等 wallet_tip >= node_tip。返回 (等待秒数, wallet_tip, node_tip)。"""
    t0 = time.monotonic()
    last_print = 0.0
    while True:
        wt, nt, fs, locked = heights(zallet_url, auth)
        if wt is not None and nt is not None and wt >= nt:
            return time.monotonic() - t0, wt, nt
        el = time.monotonic() - t0
        if el > timeout:
            raise TimeoutError(
                "%s 同步超时 %.0fs（wallet=%s node=%s synced=%s locked=%s）"
                % (label, el, wt, nt, fs, locked))
        if el - last_print >= 10:
            print("    [sync] wallet=%s node=%s synced=%s locked=%s 已等 %.0fs"
                  % (wt, nt, fs, locked, el))
            last_print = el
        time.sleep(interval)


# ---------------------------------------------------------------------------
# 内存采样（/proc/<pid>/status VmRSS）
# ---------------------------------------------------------------------------


def proc_rss(pid):
    try:
        with open("/proc/%s/status" % pid, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        return None
    return None


def auto_pids():
    """自动找 zebrad / zallet 的 pid。"""
    out = {}
    for label, pat in (("zebrad", "zebrad"), ("zallet", "zallet")):
        try:
            r = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True, timeout=5)
            pids = [p for p in r.stdout.split() if p.strip()]
            if pids:
                out[label] = sorted(pids, key=lambda x: int(x))[0]
        except Exception:
            pass
    return out


class MemSampler(threading.Thread):
    def __init__(self, pid_map, interval, out_csv, stop_event):
        super().__init__(daemon=True)
        self.pid_map = pid_map
        self.interval = interval
        self.out_csv = out_csv
        self.stop = stop_event
        self.peak = {}

    def run(self):
        with open(self.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ts_epoch", "round", "proc", "pid", "rss_bytes"])
            while not self.stop.is_set():
                ts = time.time()
                for name, pid in self.pid_map.items():
                    v = proc_rss(pid)
                    if v:
                        w.writerow(["%.3f" % ts, getattr(self, "round", 0), name, pid, v])
                        if v > self.peak.get(name, 0):
                            self.peak[name] = v
                f.flush()
                self.stop.wait(self.interval)


# ---------------------------------------------------------------------------
# 计时包装
# ---------------------------------------------------------------------------


def timed(fn):
    t0 = time.monotonic()
    res = fn()
    return (time.monotonic() - t0) * 1000.0, res


# ---------------------------------------------------------------------------
# 单轮
# ---------------------------------------------------------------------------


def resolve_recipient(args, zauth):
    """在循环外派生一次收款地址并复用。

    注意：请求 p2pkh receiver 会派生新的透明地址，多次调用会撞上透明 gap limit
    （默认 16，报 "reached the transparent gap limit"）。因此优先只请求 sapling
    receiver；失败再退回既有可用 UA。
    """
    for receivers in (["sapling"],):
        try:
            r = rpc(args.zallet_url, "z_getaddressforaccount",
                    [args.account_index, receivers], auth=zauth, timeout=60)
            ua = r.get("address") if isinstance(r, dict) else r
            if ua:
                print("  收款地址（仅 sapling receiver）：%s..." % ua[:36])
                return ua
        except RPCError as e:
            print("  [addr] receivers=%s 失败：%s" % (receivers, e.err.get("message", e.err)[:110]))

    # 回退 1：用此前已写入 create_sapling.json 的已知可用 UA（sapling+p2pkh）
    try:
        with open("/mnt/d/Research/z3/wsl/create_sapling.json", "r", encoding="utf-8") as f:
            p = json.load(f)
        ua = p[1][0]["address"]
        print("  收款地址（回退：create_sapling.json 中的 UA）：%s..." % ua[:36])
        return ua
    except Exception as e:
        print("  [addr] 回退 1 失败：%s" % e)

    # 回退 2：最后一次尝试 sapling+p2pkh（可能仍撞 gap limit）
    r = rpc(args.zallet_url, "z_getaddressforaccount",
            [args.account_index, ["sapling", "p2pkh"]], auth=zauth, timeout=60)
    return r.get("address") if isinstance(r, dict) else r


def one_round(idx, args, zauth, ua):
    T = {}
    print("\n----- round %d/%d -----" % (idx + 1, args.rounds))

    # 0. 前置：钱包必须完全追平（pczt_create 的 target_height 取钱包视图）
    sec, wt, nt = wait_synced(args.zallet_url, zauth, label="round%d 前置" % (idx + 1))
    T["pre_sync"] = sec * 1000.0
    print("  前置同步 OK：wallet=%s node=%s（%.1fs）" % (wt, nt, sec))

    amounts = [{"address": ua, "amount": args.amount_zec}]

    # 2. pczt_create
    T["pczt_create"], created = timed(lambda: rpc(
        args.zallet_url, "pczt_create",
        [args.account_uuid, amounts, None, args.privacy, args.fund_source],
        auth=zauth, timeout=300))
    pczt = created["pczt"]
    policy = created.get("privacy_policy") or args.privacy
    print("  create  %.1f ms  pczt=%dB  policy=%s" % (T["pczt_create"], len(pczt), policy))

    # 3. pczt_sign —— 必须先签名再证明。
    #    Sapling spend 的 proof_generation_key (ak, nsk) 只能由 Signer 写入；
    #    Prover 拿不到它就会报 Prover(MissingProofGenerationKey)。
    def _sign(text):
        last = None
        for params in ([text, policy, False], [text, policy], [text]):
            try:
                return rpc(args.zallet_url, "pczt_sign", params, auth=zauth, timeout=300)
            except RPCError as e:
                last = e
                print("    [sign] %d 参数形态失败: %s"
                      % (len(params), str(e.err.get("message", e.err))[:120]))
        raise last

    T["pczt_sign"], signed = timed(lambda: _sign(pczt))
    pczt_signed = signed["pczt"]
    print("  sign    %.1f ms  sapling_signed=%s"
          % (T["pczt_sign"], signed.get("sapling_signed")))

    # 4. pczt_prove（首次调用会生成/缓存 proving key，可能数十秒，给足超时）
    T["pczt_prove"], proved = timed(lambda: rpc(
        args.zallet_url, "pczt_prove", [pczt_signed], auth=zauth, timeout=1800))
    pczt_proved = proved["pczt"]
    print("  prove   %.1f ms  sapling_proven=%s orchard=%s"
          % (T["pczt_prove"], proved.get("sapling_proven"), proved.get("orchard_proven")))

    # 5. pczt_extract（只序列化 + 记账，不广播；要求已证明且已签名）
    T["pczt_extract"], ext = timed(lambda: rpc(
        args.zallet_url, "pczt_extract", [pczt_proved], auth=zauth, timeout=300))
    rawtx, txid = ext["hex"], ext["txid"]
    T["tx_size_bytes"] = len(rawtx) // 2
    print("  extract %.1f ms  txid=%s size=%dB stored=%s"
          % (T["pczt_extract"], txid[:16] + "...", T["tx_size_bytes"], ext.get("stored")))

    # 6. 广播（zebra，回环免鉴权）
    def _send():
        try:
            return rpc(args.zebra_url, "sendrawtransaction", [rawtx], auth=None, timeout=120)
        except RPCError as e:
            msg = str(e.err.get("message", ""))
            if "already" in msg.lower() or "exists" in msg.lower():
                return txid
            raise

    T["send_raw"], _ = timed(_send)
    print("  broadcast %.1f ms" % T["send_raw"])

    # 7. 挖块入块 + 等确认
    T["mine_blocks"], _ = timed(lambda: rpc(
        args.zebra_url, "generate", [args.mine_per_round], auth=None, timeout=600))
    print("  mine %d blocks %.1f ms" % (args.mine_per_round, T["mine_blocks"]))

    def _confirm():
        t0 = time.monotonic()
        while time.monotonic() - t0 < args.confirm_timeout:
            r = rpc(args.zebra_url, "getrawtransaction", [txid, 1], auth=None, timeout=60)
            if isinstance(r, dict) and (r.get("confirmations") or 0) >= args.confirmations:
                return r
            time.sleep(0.5)
        return None

    T["wait_confirm"], conf = timed(_confirm)
    print("  confirm %.1f ms  confirmations=%s"
          % (T["wait_confirm"], (conf or {}).get("confirmations")))

    # 8. 钱包重新追平（下一轮 pczt_create 的前置）
    sec2, wt2, nt2 = wait_synced(args.zallet_url, zauth, label="round%d 后置" % (idx + 1))
    T["post_sync"] = sec2 * 1000.0
    print("  后置同步 %.1fs（wallet=%s node=%s）" % (sec2, wt2, nt2))

    T["pczt_pipeline_ms"] = (T["pczt_create"] + T["pczt_prove"]
                             + T["pczt_sign"] + T["pczt_extract"])
    T["total_ms"] = T["pczt_pipeline_ms"] + T["send_raw"] + T["mine_blocks"] + T["wait_confirm"]

    return {
        "round": idx + 1,
        "txid": txid,
        "tx_size_bytes": T["tx_size_bytes"],
        "recipient": ua,
        "timings": T,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def preflight(args, zauth):
    print("== preflight ==")
    wt, nt, fs, locked = heights(args.zallet_url, zauth)
    print("  wallet=%s node=%s synced=%s locked=%s" % (wt, nt, fs, locked))
    bi = rpc(args.zebra_url, "getblockchaininfo", [], auth=None, timeout=30)
    print("  zebra blocks=%s chain=%s" % (bi.get("blocks"), bi.get("chain")))
    bal = rpc(args.zallet_url, "z_getbalanceforaccount", [args.account_index],
              auth=zauth, timeout=30)
    print("  balance=%s" % json.dumps(bal))
    print("  pids=%s" % auto_pids())
    return 0


def main():
    p = argparse.ArgumentParser(description="z3 栈 PCZT 端到端测量 v2")
    p.add_argument("--zallet-url", default="http://127.0.0.1:40232")
    p.add_argument("--zallet-cookie", default="~/z3-regtest/data/zallet/.cookie")
    p.add_argument("--zebra-url", default="http://127.0.0.1:18232")
    p.add_argument("--account-uuid", required=False,
                   default="5fd7056a-3e6e-455f-b75d-d80b0556fea9")
    p.add_argument("--account-index", type=int, default=0)
    p.add_argument("--amount-zec", type=float, default=10.0)
    p.add_argument("--privacy", default="FullPrivacy")
    p.add_argument("--fund-source", default="sapling")
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--confirmations", type=int, default=1)
    p.add_argument("--mine-per-round", type=int, default=2)
    p.add_argument("--confirm-timeout", type=float, default=600)
    p.add_argument("--sample-interval", type=float, default=0.25)
    p.add_argument("--outdir", default="./raw/e2e_regtest_v2")
    p.add_argument("--preflight", action="store_true")
    args = p.parse_args()

    zauth = read_cookie(args.zallet_cookie)
    if not zauth:
        print("[fatal] 读不到 zallet cookie: %s" % args.zallet_cookie)
        return 1

    if args.preflight:
        return preflight(args, zauth)

    outdir = os.path.expanduser(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    run_id = time.strftime("run_%Y%m%d_%H%M%S")
    run_dir = os.path.join(outdir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    pids = auto_pids()
    stop = threading.Event()
    sampler = None
    if pids:
        sampler = MemSampler(pids, args.sample_interval,
                             os.path.join(run_dir, "memory_timeseries.csv"), stop)
        sampler.start()
        print("[mem] 采样 %s 间隔 %.2fs" % (pids, args.sample_interval))
    else:
        print("[mem] 未找到 zebrad/zallet 进程，跳过内存采样")

    stages = ["pczt_create", "pczt_prove", "pczt_sign", "pczt_extract",
              "send_raw", "mine_blocks", "wait_confirm",
              "pre_sync", "post_sync", "pczt_pipeline_ms", "total_ms"]
    long_rows = []
    results = []
    errors = []
    ua = resolve_recipient(args, zauth)
    t_all0 = time.monotonic()
    try:
        for i in range(args.rounds):
            if sampler:
                sampler.round = i + 1
            try:
                r = one_round(i, args, zauth, ua)
            except Exception as e:
                print("  [error] round %d 失败：%s" % (i + 1, e))
                errors.append({"round": i + 1, "error": repr(e)})
                # 失败后尽量把钱包拉回同步态，避免污染下一轮
                try:
                    wait_synced(args.zallet_url, zauth, label="round%d 救援" % (i + 1))
                except Exception:
                    pass
                continue
            results.append(r)
            for s in stages:
                if s in r["timings"]:
                    long_rows.append([r["round"], r["txid"], s, "%.3f" % r["timings"][s]])
    finally:
        stop.set()
        if sampler:
            sampler.join(timeout=5)

    wall = time.monotonic() - t_all0

    # 逐阶段长表
    with open(os.path.join(run_dir, "stage_timings_long.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["round", "txid", "stage", "ms"])
        w.writerows(long_rows)

    # 中位数汇总
    summ = []
    for s in stages:
        vals = [r["timings"][s] for r in results if s in r["timings"]]
        if not vals:
            continue
        summ.append({
            "stage": s, "n": len(vals),
            "median_ms": statistics.median(vals),
            "min_ms": min(vals), "max_ms": max(vals),
            "mean_ms": statistics.fmean(vals),
        })
    with open(os.path.join(run_dir, "summary_median.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stage", "n", "median_ms", "mean_ms", "min_ms", "max_ms"])
        for row in summ:
            w.writerow([row["stage"], row["n"], "%.3f" % row["median_ms"],
                        "%.3f" % row["mean_ms"], "%.3f" % row["min_ms"],
                        "%.3f" % row["max_ms"]])

    meta = {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rounds": args.rounds,
        "amount_zec": args.amount_zec,
        "privacy": args.privacy,
        "fund_source": args.fund_source,
        "mine_per_round": args.mine_per_round,
        "confirmations": args.confirmations,
        "total_wall_s": wall,
        "mem_peak_bytes": sampler.peak if sampler else {},
        "tx_sizes": [r["tx_size_bytes"] for r in results],
        "txids": [r["txid"] for r in results],
        "recipient": ua,
        "errors": errors,
        "results": results,
    }
    with open(os.path.join(run_dir, "run_summary.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print("\n=== 汇总（中位数，n=%d）===" % args.rounds)
    print("%-18s %10s %10s %10s" % ("stage", "median_ms", "min_ms", "max_ms"))
    for row in summ:
        print("%-18s %10.1f %10.1f %10.1f"
              % (row["stage"], row["median_ms"], row["min_ms"], row["max_ms"]))
    print("\n输出目录: %s" % run_dir)
    print("总墙钟: %.1fs" % wall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
