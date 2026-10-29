#!/usr/bin/env python3
"""
PCZT 四阶段 5x 基准（zallet beta.3，regtest 离线）。

测量对象：ironwood（orchard 家族接收者）池的 shielded transfer。
口径说明：prove 阶段反映该池的证明系统成本，**不能**与 Sapling(Groth16) 混用。

阶段：pczt_create -> pczt_sign -> pczt_prove -> pczt_extract -> broadcast -> mine -> confirm

设计要点（均为本轮踩坑后的硬性要求）
  1) 收款地址在循环外一次性解析复用 —— 每次请求 p2pkh receiver 都会派生新透明地址，
     撞 gap limit(16) 后 z_getaddressforaccount 直接报错。
  2) 同步判定只比数值 wallet_tip >= node_tip，忽略 locked 字段（beta.3 展示层 bug）。
  3) zebrad 的 generate 会返回 "failed to send mined block to gossip task"，但区块
     实际已产生 —— 判据改为「链高是否按预期增长」，绝不看返回值。

产物（<outdir>/run_<ts>/）
  stage_timings.csv      长表：round,txid,stage,ms
  rounds.csv             宽表：每轮汇总 + 尺寸/actions/fee
  summary.csv            中位数 / min / max / n
  memory_timeseries.csv  VmRSS 采样（zebrad、zallet）
  meta.json              参数与环境快照
"""
import argparse
import base64
import csv
import http.client
import json
import os
import statistics
import threading
import time

ZA = ("127.0.0.1", 40232)
ZB = ("127.0.0.1", 18232)
COOKIE = os.path.expanduser("~/z3-regtest/data/zallet/.cookie")
ACCOUNT = "5fd7056a-3e6e-455f-b75d-d80b0556fea9"
SAP_UA = ("uregtest19tu34g0t8np34f43fwlnn7wy4lk59t7zmwh8xy5yr4vvgj3yfuu3zaga4yyjhx69ynphl5"
          "cwyte0ej8hqct6cqk3kez0rjhdl8lwwhgkt9x3v2zlsxjymru75mnm0mz62gc2uk6205n")

STAGES = ["pczt_create", "pczt_sign", "pczt_prove", "pczt_extract",
          "broadcast", "mine", "confirm"]


# ---------- RPC ----------
def _post(host, port, payload, auth=None, timeout=900):
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    h = {"Content-Type": "application/json"}
    if auth:
        h["Authorization"] = "Basic " + auth
    conn.request("POST", "/", json.dumps(payload), h)
    raw = conn.getresponse().read()
    conn.close()
    return json.loads(raw)


def zauth():
    return base64.b64encode(open(COOKIE).read().strip().encode()).decode()


def z(method, params, timeout=900):
    d = _post(ZA[0], ZA[1], {"jsonrpc": "2.0", "method": method, "params": params,
                             "id": 1}, zauth(), timeout)
    if d.get("error"):
        raise RuntimeError("%s -> %s" % (method, json.dumps(d["error"], ensure_ascii=False)))
    return d["result"]


def b(method, params, timeout=180):
    d = _post(ZB[0], ZB[1], {"jsonrpc": "2.0", "method": method, "params": params,
                             "id": 1}, None, timeout)
    if d.get("error"):
        raise RuntimeError("%s -> %s" % (method, json.dumps(d["error"], ensure_ascii=False)))
    return d["result"]


def height():
    try:
        return b("getblockchaininfo", [])["blocks"]
    except Exception:
        return None


def advance(n, timeout=120):
    """挖 n 块。不信 generate 的返回值，只认链高增量。"""
    h0 = height()
    if h0 is None:
        raise RuntimeError("取链高失败")
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            b("generate", [n])
        except RuntimeError:
            pass  # gossip 通道报错但区块已产生，忽略
        h1 = height()
        if h1 is not None and h1 >= h0 + n:
            return h1 - h0, time.monotonic() - t0
        time.sleep(1.5)
    return (height() or h0) - h0, time.monotonic() - t0


def wait_sync(timeout=300):
    """等钱包追平。

    判据取两个来源的**较大值**：
      - zallet 的 node_tip（正常情况下等于链尖）
      - zebra RPC 的 blocks（权威值）
    原因：zallet 重启后 node_tip 会短暂陈旧（实测曾报 31296 而实际链高 32297），
    若只比 node_tip，条件会无条件成立，"前置同步 OK" 变成恒真，测量前提失效。
    """
    t0 = time.monotonic()
    wt = nt = None
    while time.monotonic() - t0 < timeout:
        try:
            s = z("getwalletstatus", [])
            wt = (s.get("wallet_tip") or {}).get("height") or 0
            nt = (s.get("node_tip") or {}).get("height") or 0
            zh = height() or 0
            target = max(nt, zh)
            if wt and wt >= target:
                return wt, target, time.monotonic() - t0
        except RuntimeError:
            pass
        time.sleep(1)
    return None, None, time.monotonic() - t0


def pools():
    r = z("z_getbalanceforaccount", [ACCOUNT])
    return {k: v.get("valueZat", 0) for k, v in r.get("pools", {}).items()}


def target_pool(fund_source):
    """按 fund_source 选出实际会被花费的池。

    注意：本环境 fund_source="orchard" 实际命中的是 ironwood 池（同一接收者家族，
    构建把新池统一记为 ironwood）。因此两个名字都接受，取余额较大者。
    """
    p = pools()
    keys = ["orchard", "ironwood"] if fund_source == "orchard" else [fund_source]
    cand = {k: p.get(k, 0) for k in keys if p.get(k, 0) > 0}
    if not cand:
        cand = {k: v for k, v in p.items() if k != "transparent" and v > 0}
    if not cand:
        return None, p
    return max(cand, key=cand.get), p


# ---------- 内存采样 ----------
def find_pids():
    pids = {}
    for name in ("zebrad", "zallet"):
        try:
            out = os.popen("pgrep -x %s || pgrep -f '/%s '" % (name, name)).read().split()
            pids[name] = int(out[0]) if out else None
        except Exception:
            pids[name] = None
    return pids


def rss_kb(pid):
    if not pid:
        return None
    try:
        for line in open("/proc/%d/status" % pid):
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except Exception:
        return None
    return None


class Sampler(threading.Thread):
    def __init__(self, path, interval=0.25):
        super().__init__(daemon=True)
        self.path, self.interval = path, interval
        self.stop_evt = threading.Event()
        self.pids = find_pids()
        self.round = 0
        self.fh = open(path, "w", newline="")
        self.w = csv.writer(self.fh)
        self.w.writerow(["t_wall", "t_mono", "round", "zebrad_rss_kb", "zallet_rss_kb"])
        self.fh.flush()

    def run(self):
        t0 = time.monotonic()
        while not self.stop_evt.is_set():
            self.w.writerow([time.strftime("%H:%M:%S"), "%.3f" % (time.monotonic() - t0),
                             self.round, rss_kb(self.pids.get("zebrad")),
                             rss_kb(self.pids.get("zallet"))])
            self.fh.flush()
            self.stop_evt.wait(self.interval)
        self.fh.close()


# ---------- 单轮 ----------
def one_round(idx, args, recipient):
    T = {}
    row = {"round": idx}
    print("\n----- round %d/%d -----" % (idx, args.rounds))

    wt, nt, el = wait_sync()
    print("  前置同步 wallet=%s node=%s（%.1fs）" % (wt, nt, el))

    t0 = time.monotonic()
    created = z("pczt_create", [ACCOUNT, [{"address": recipient, "amount": args.send_zec}],
                                args.minconf, args.policy, args.fund_source])
    T["pczt_create"] = (time.monotonic() - t0) * 1000
    pczt = created["pczt"]
    insp = z("pczt_inspect", [pczt])
    row["policy"] = created.get("privacy_policy")
    row["fee_zat"] = insp.get("fee_zat")
    row["size_b64"] = len(pczt)
    row["actions"] = (insp.get("ironwood") or {}).get("actions")
    print("  create  %7.1f ms  b64=%dB  ironwood.actions=%s  policy=%s"
          % (T["pczt_create"], len(pczt), insp.get("ironwood", {}).get("actions"),
             row["policy"]))

    t0 = time.monotonic()
    signed = z("pczt_sign", [pczt, row["policy"], False])
    T["pczt_sign"] = (time.monotonic() - t0) * 1000
    row["signed"] = signed.get("ironwood_signed")
    print("  sign    %7.1f ms  ironwood_signed=%s unsigned=%s"
          % (T["pczt_sign"], signed.get("ironwood_signed"),
             signed.get("unsigned_ironwood")))

    t0 = time.monotonic()
    proved = z("pczt_prove", [signed["pczt"]], timeout=1800)
    T["pczt_prove"] = (time.monotonic() - t0) * 1000
    print("  prove   %7.1f ms  ironwood_proven=%s" % (T["pczt_prove"], proved.get("ironwood_proven")))

    t0 = time.monotonic()
    ext = z("pczt_extract", [proved["pczt"]])
    T["pczt_extract"] = (time.monotonic() - t0) * 1000
    row["txid"] = ext.get("txid")
    row["size_bytes"] = len(ext.get("hex", "")) // 2
    row["stored"] = ext.get("stored")
    print("  extract %7.1f ms  txid=%s size=%dB stored=%s"
          % (T["pczt_extract"], row["txid"], row["size_bytes"], row["stored"]))

    t0 = time.monotonic()
    b("sendrawtransaction", [ext["hex"]])
    T["broadcast"] = (time.monotonic() - t0) * 1000
    print("  broadcast %5.1f ms" % T["broadcast"])

    t0 = time.monotonic()
    dh, me = advance(args.mine_blocks)
    T["mine"] = me * 1000
    print("  mine    %7.1f ms  +%d 块" % (T["mine"], dh))

    t0 = time.monotonic()
    conf = None
    while time.monotonic() - t0 < 60:
        try:
            conf = b("getrawtransaction", [row["txid"], 1]).get("confirmations")
            if conf:
                break
        except RuntimeError:
            pass
        time.sleep(1)
    T["confirm"] = (time.monotonic() - t0) * 1000
    row["confirmations"] = conf
    print("  confirm %7.1f ms  confirmations=%s" % (T["confirm"], conf))

    wt, nt, el = wait_sync()
    print("  后置同步 wallet=%s node=%s（%.1fs）" % (wt, nt, el))

    row["total_ms"] = sum(T.values())
    for k, v in T.items():
        row[k] = round(v, 1)
    return row, T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--send-zec", type=float, default=3)
    ap.add_argument("--minconf", type=int, default=1)
    ap.add_argument("--policy", default="AllowRevealedAmounts")
    ap.add_argument("--fund-source", default="orchard")
    ap.add_argument("--mine-blocks", type=int, default=2)
    ap.add_argument("--outdir", default="./raw/pczt_pool_v1")
    a = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    rundir = os.path.join(a.outdir, "run_" + ts)
    os.makedirs(rundir, exist_ok=True)
    print("[out]", rundir)

    pool, p = target_pool(a.fund_source)
    print("[pool] 余额:", p, "  fund_source=%s -> 实际花费池: %s" % (a.fund_source, pool))
    if not pool:
        print("[!] 目标池无余额，先跑 pczt_orchard2.py 注资")
        return 1
    bal = p[pool]
    # 按**全部轮次**预检：每轮送出的金额+手续费都从该池扣，之前只检查 2 轮的量，
    # 15 轮会跑到中途因余额不足失败，前面数据白测。
    need_total = int((a.send_zec + 0.001) * 1e8) * a.rounds
    if bal < need_total:
        print("[!] 目标池余额 %.4f ZEC < 需要 %.4f ZEC（%d 轮 × %.2f）"
              % (bal / 1e8, need_total / 1e8, a.rounds, a.send_zec))
        print("    先注资： python3 /mnt/d/Research/z3/wsl/fund_pool.py --fund-zec %.0f"
              % ((need_total - bal) / 1e8 + 5))
        return 1
    print("[pool] 每轮 %.2f ZEC，余额 %.4f ZEC，%d 轮共需 %.4f ZEC"
          % (a.send_zec, bal / 1e8, a.rounds, need_total / 1e8))

    sampler = Sampler(os.path.join(rundir, "memory_timeseries.csv"))
    sampler.start()

    rows, long_rows = [], []
    try:
        for i in range(1, a.rounds + 1):
            sampler.round = i
            try:
                row, T = one_round(i, a, SAP_UA)
                rows.append(row)
                for st in STAGES:
                    if st in T:
                        long_rows.append([i, row.get("txid", ""), st, "%.1f" % T[st]])
            except Exception as e:
                print("  [error] round %d 失败: %s" % (i, str(e)[:300]))
                rows.append({"round": i, "error": str(e)[:300]})
    finally:
        sampler.stop_evt.set()
        sampler.join(timeout=8)

    # 长表
    with open(os.path.join(rundir, "stage_timings.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "txid", "stage", "ms"])
        w.writerows(long_rows)

    # 宽表
    cols = ["round", "txid", "actions", "signed", "size_bytes", "size_b64", "fee_zat",
            "policy", "confirmations"] + STAGES + ["total_ms", "error"]
    with open(os.path.join(rundir, "rounds.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # 汇总
    ok = [r for r in rows if "error" not in r]
    with open(os.path.join(rundir, "summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stage", "n", "median_ms", "min_ms", "max_ms", "stdev_ms"])
        for st in STAGES + ["total_ms"]:
            vals = [r[st] for r in ok if isinstance(r.get(st), (int, float))]
            if not vals:
                continue
            w.writerow([st, len(vals), "%.1f" % statistics.median(vals),
                        "%.1f" % min(vals), "%.1f" % max(vals),
                        "%.1f" % (statistics.stdev(vals) if len(vals) > 1 else 0)])

    # 按形态分组：只有 actions/signed 数相同的轮次才可合并统计。
    # 每轮都会把钱打到同一个 sapling 收款地址，note 逐步碎片化，spend 数可能变化；
    # 若形态不一致，整体中位数就是混合样本，不能当作单一形态的成本引用。
    shapes = {}
    for r in ok:
        shapes.setdefault((r.get("actions"), r.get("signed")), []).append(r)
    with open(os.path.join(rundir, "summary_by_shape.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["actions", "signed", "n", "stage", "median_ms", "min_ms", "max_ms"])
        for key, rs in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
            for st in STAGES + ["total_ms"]:
                vals = [x[st] for x in rs if isinstance(x.get(st), (int, float))]
                if vals:
                    w.writerow([key[0], key[1], len(vals), st,
                                "%.1f" % statistics.median(vals),
                                "%.1f" % min(vals), "%.1f" % max(vals)])

    json.dump({"args": vars(a), "pool": pool, "balances": p,
               "pids": sampler.pids, "timestamp": ts,
               "shape_groups": {str(k): len(v) for k, v in shapes.items()}},
              open(os.path.join(rundir, "meta.json"), "w"), indent=1)

    print("\n=== 汇总（中位数，n=%d）===" % len(ok))
    print("%-14s %10s %10s %10s" % ("stage", "median_ms", "min_ms", "max_ms"))
    for st in STAGES + ["total_ms"]:
        vals = [r[st] for r in ok if isinstance(r.get(st), (int, float))]
        if vals:
            print("%-14s %10.1f %10.1f %10.1f"
                  % (st, statistics.median(vals), min(vals), max(vals)))

    print("\n=== 按形态分组（actions, signed）===")
    print("%-9s %-8s %3s %12s %12s %10s"
          % ("actions", "signed", "n", "prove中位", "total中位", "size"))
    for key, rs in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
        pv = [x["pczt_prove"] for x in rs if isinstance(x.get("pczt_prove"), (int, float))]
        tv = [x["total_ms"] for x in rs if isinstance(x.get("total_ms"), (int, float))]
        sz = rs[0].get("size_bytes")
        print("%-9s %-8s %3d %12.1f %12.1f %10s"
              % (key[0], key[1], len(rs),
                 statistics.median(pv) if pv else 0,
                 statistics.median(tv) if tv else 0, sz))
    if len(shapes) > 1:
        print("\n[!] 形态不一致：上述整体中位数是混合样本，请引用 summary_by_shape.csv 中的分组值")

    print("\n输出:", rundir)
    return 0 if len(ok) == a.rounds else 2


if __name__ == "__main__":
    raise SystemExit(main())
