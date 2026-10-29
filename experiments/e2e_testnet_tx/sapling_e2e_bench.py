#!/usr/bin/env python3
"""
真 Sapling 交易完整耗时基准（zallet beta.3，离线 regtest）。

为什么要用 z_sendmany 而不是 PCZT
  zallet beta.3 的 Sapling PCZT 通路不可用：pczt_create 产出的 Sapling spend 缺
  proof_generation_key，pczt_sign 只拿得到 ask（Sapling 的 ak/nsk 是两把独立密钥，
  pczt::sapling::Spend 也没有 PGK 的公开读写接口），pczt_prove 必然报
  Prover(MissingProofGenerationKey)。同钱包同批 note 用 z_sendmany 可正常花费，
  所以本基准走 z_sendmany —— 它内部完成 build -> prove -> sign -> broadcast，
  这条链路是 Sapling 真实可用的路径。

测量口径（重要）
  z_sendmany 是**异步**的：RPC 立即返回 opid，真正的钱包侧工作在后台线程完成。
  因此拆成三段，各自含义不同：
    t_submit    RPC 往返（提案构造 + 提交）—— 不是主体
    t_pipeline  opid 提交 -> status=success —— 真实成本（含 Sapling Groth16 证明 + 签名 + 广播）
    t_chain     挖块 + 钱包追平 —— regtest 人造成本，不代表主网
  轮询间隔 20 ms，故 t_pipeline 有 <=20 ms 的量化误差（相对 ~3 s 可忽略）。

  另记录每轮实际花费的 Sapling spend 数（z_viewtransaction），用于把
  「成本 ∝ spend 数」从定性变定量：多轮不同 spend 数时自动做最小二乘拟合，
  斜率即为单个 Sapling Spend 的边际成本。

用法
  python3 sapling_e2e_bench.py --rounds 15 --amount-zec 3
  python3 sapling_e2e_bench.py --rounds 6  --amount-zec 40     # 迫使多 spend，拿斜率
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

STAGES = ["submit", "pipeline", "mine", "sync", "total"]


# ---------------- RPC ----------------
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
    d = _post(ZA[0], ZA[1], {"jsonrpc": "2.0", "method": method,
                             "params": params, "id": 1}, zauth(), timeout)
    if d.get("error"):
        raise RuntimeError("%s -> %s" % (method, json.dumps(d["error"], ensure_ascii=False)))
    return d["result"]


def b(method, params, timeout=180):
    d = _post(ZB[0], ZB[1], {"jsonrpc": "2.0", "method": method,
                             "params": params, "id": 1}, None, timeout)
    if d.get("error"):
        raise RuntimeError("%s -> %s" % (method, json.dumps(d["error"], ensure_ascii=False)))
    return d["result"]


def height():
    try:
        return b("getblockchaininfo", [])["blocks"]
    except Exception:
        return None


def advance(n, timeout=180):
    """挖 n 块。generate 的 gossip 报错是假失败，只认链高增量。"""
    h0 = height()
    if h0 is None:
        raise RuntimeError("取链高失败")
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            b("generate", [n])
        except RuntimeError:
            pass
        h1 = height()
        if h1 is not None and h1 >= h0 + n:
            return h1 - h0, time.monotonic() - t0
        time.sleep(1.2)
    return (height() or h0) - h0, time.monotonic() - t0


def wait_sync(timeout=300):
    """等钱包追平。target 取 max(zallet node_tip, zebra blocks)。

    只比 node_tip 会在 zallet 重启后失效（实测 node_tip 曾陈旧 1001 块，
    条件恒真）。ignored: locked 字段是 beta.3 展示层 bug。
    """
    t0 = time.monotonic()
    wt = nt = 0
    while time.monotonic() - t0 < timeout:
        try:
            s = z("getwalletstatus", [])
            wt = (s.get("wallet_tip") or {}).get("height") or 0
            nt = (s.get("node_tip") or {}).get("height") or 0
            target = max(nt, height() or 0)
            if wt and wt >= target:
                return wt, target, time.monotonic() - t0
        except RuntimeError:
            pass
        time.sleep(0.5)
    return None, None, time.monotonic() - t0


def pools():
    r = z("z_getbalanceforaccount", [ACCOUNT])
    return {k: v.get("valueZat", 0) for k, v in r.get("pools", {}).items()}


def sapling_zat():
    return pools().get("sapling", 0)


# ---------------- 内存采样 ----------------
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
            self.w.writerow([time.strftime("%H:%M:%S"),
                             "%.3f" % (time.monotonic() - t0), self.round,
                             rss_kb(self.pids.get("zebrad")),
                             rss_kb(self.pids.get("zallet"))])
            self.fh.flush()
            self.stop_evt.wait(self.interval)
        self.fh.close()


# ---------------- 地址与状态 ----------------
def sapling_ua():
    """派生一个只含 sapling receiver 的 UA。

    只请求 ["sapling"]：不触发透明地址派生（每请求一次 p2pkh 就会推进 index，
    撞上 gap limit=16 后 z_getaddressforaccount 直接报错）。
    """
    r = z("z_getaddressforaccount", [0, ["sapling"]])
    a = r.get("address") if isinstance(r, dict) else r
    if not a:
        raise RuntimeError("派生 sapling 地址失败: %s" % json.dumps(r)[:200])
    return a


def view_tx(txid):
    """取 Sapling spend/output 计数与手续费。

    实测结构（zallet beta.3，v6 交易）：
      {"txid","status","confirmations",...,"fee":0.0001,
       "spends":[{"pool":"sapling","spend":0,...}],
       "outputs":[{"pool":"sapling","output":0,"walletInternal":true,...}]}
    注意 spends/outputs 是**顶层数组**（不是嵌在 sapling 子对象里），每项带 pool 字段。
    fee 单位是 ZEC（浮点），不是 zat。
    """
    v = z("z_viewtransaction", [txid])
    sp = v.get("spends") or []
    ou = v.get("outputs") or []
    ns = len([x for x in sp if x.get("pool") == "sapling"]) or len(sp)
    no = len([x for x in ou if x.get("pool") == "sapling"])
    nt = len([x for x in sp if x.get("pool") == "transparent"])
    mat = len([x for x in ou if x.get("pool") == "transparent"])
    fee_zat = int(round(float(v.get("fee") or 0) * 1e8))
    return {"spends": ns, "outputs": no, "t_spends": nt, "t_outputs": mat,
            "fee_zat": fee_zat, "confirmations": v.get("confirmations")}


def tx_size(txid):
    try:
        raw = b("getrawtransaction", [txid])
        if isinstance(raw, str):
            return len(raw) // 2
        if isinstance(raw, dict) and raw.get("hex"):
            return len(raw["hex"]) // 2
    except RuntimeError:
        pass
    return None


def send_and_time(from_ua, amounts, policy_order):
    """提交 -> 轮询 -> 返回 (t_submit_ms, t_pipeline_ms, opid, result, policy)。"""
    last = None
    for policy in policy_order:
        params = [from_ua, amounts, 1, None, policy]
        t0 = time.monotonic()
        try:
            opid = z("z_sendmany", params, timeout=120)
        except RuntimeError as e:
            last = e
            msg = str(e)
            print("    [sendmany] policy=%s 被拒: %s" % (policy, msg[:150]))
            continue
        t_submit = (time.monotonic() - t0) * 1000.0

        t1 = time.monotonic()
        res = None
        while time.monotonic() - t1 < 600:
            try:
                st = z("z_getoperationstatus", [[opid]])
            except RuntimeError as e:
                last = e
                break
            if st:
                srec = st[0] if isinstance(st, list) else st
                stt = srec.get("status")
                if stt == "success":
                    t_pipeline = (time.monotonic() - t1) * 1000.0
                    return t_submit, t_pipeline, opid, srec.get("result") or {}, policy
                if stt == "failed":
                    last = RuntimeError("operation failed: %s"
                                        % json.dumps(srec.get("error"), ensure_ascii=False))
                    break
            time.sleep(0.02)
        else:
            last = RuntimeError("operation timeout")
        print("    [sendmany] policy=%s 执行失败: %s" % (policy, str(last)[:180]))
    raise last if last else RuntimeError("z_sendmany 全部形态失败")


# ---------------- 单轮 ----------------
def build_amounts(recipients, amount_zec):
    """把总额 amount_zec 平摊到 recipients（zat 整数运算，余数并入第一个）。"""
    total = int(round(amount_zec * 1e8))
    n = len(recipients)
    per = total // n
    out = [{"address": recipients[0], "amount": (per + total - per * n) / 1e8}]
    for a in recipients[1:]:
        out.append({"address": a, "amount": per / 1e8})
    return out


def one_round(idx, a, from_ua, recipients, policy_order):
    row = {"round": idx}
    T = {}
    print("\n----- round %d/%d -----" % (idx, a.rounds))

    wt, target, sec = wait_sync()
    if wt is None:
        raise RuntimeError("前置同步超时")
    print("  前置同步 wallet=%s 目标=%s（%.1fs）" % (wt, target, sec))

    bal0 = sapling_zat()
    t_round = time.monotonic()

    amounts = build_amounts(recipients, a.amount_zec)
    ts, tp, opid, res, policy = send_and_time(from_ua, amounts, policy_order)
    txid = res.get("txid")
    T["submit"] = ts
    T["pipeline"] = tp
    print("  submit    %8.1f ms  RPC 返回 opid（policy=%s）" % (ts, policy))
    print("  pipeline  %8.1f ms  build+prove+sign+broadcast  txid=%s"
          % (tp, (txid or "?")[:16]))

    row["policy"] = policy
    row["txid"] = txid
    row["opid"] = opid
    row["fee_zat"] = res.get("fee_zat")

    h0 = height()
    nb, tm = advance(a.mine_blocks)
    T["mine"] = tm * 1000.0
    print("  mine      %8.1f ms  +%d 块 -> %s" % (tm * 1000.0, nb, height()))

    wt2, target2, sec2 = wait_sync()
    T["sync"] = sec2 * 1000.0
    print("  后置同步 wallet=%s 目标=%s（%.1fs）" % (wt2, target2, sec2))

    # 形态与尺寸在**上链后**取：getrawtransaction 对仅存在于 mempool 的交易不一定可取
    try:
        info = view_tx(txid) if txid else {}
    except RuntimeError as e:
        print("  [warn] z_viewtransaction 失败（形态字段留空）: %s" % str(e)[:160])
        info = {}
    row["sapling_spends"] = info.get("spends")
    row["sapling_outputs"] = info.get("outputs")
    if info.get("spends") is not None:
        row["sapling_proofs"] = (info["spends"] or 0) + (info["outputs"] or 0)
    row["t_spends"] = info.get("t_spends")
    row["t_outputs"] = info.get("t_outputs")
    row["confirmations"] = info.get("confirmations")
    row["fee_zat"] = info.get("fee_zat") if info.get("fee_zat") else res.get("fee_zat")
    row["tx_size"] = tx_size(txid) if txid else None
    print("  形态      spends=%s outputs=%s proofs=%s  size=%sB  conf=%s"
          % (row["sapling_spends"], row["sapling_outputs"], row.get("sapling_proofs"),
             row["tx_size"], row["confirmations"]))

    bal1 = sapling_zat()
    row["fee_measured_zat"] = (bal0 - bal1) if (bal0 and bal1) else None
    print("  手续费    %s zat（余额差 %s）"
          % (row["fee_zat"], row["fee_measured_zat"]))

    T["total"] = (time.monotonic() - t_round) * 1000.0
    print("  本轮墙钟  %8.1f ms" % T["total"])
    return row, T


# ---------------- 拟合 ----------------
def fit(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, intercept, r2


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rounds", type=int, default=15)
    p.add_argument("--amount-zec", type=float, default=3.0)
    p.add_argument("--mine-blocks", type=int, default=2)
    p.add_argument("--policies", default="FullPrivacy,AllowRevealedAmounts")
    p.add_argument("--outdir", default="./raw/sapling_e2e_v1")
    p.add_argument("--outputs", type=int, default=1,
                   help="把金额平摊到 N 个不同收款地址（N>1 用于把 Output 数推高，"
                        "分离 Output 的边际成本；默认 1 = 自转单输出）")
    a = p.parse_args()
    policy_order = [s.strip() for s in a.policies.split(",") if s.strip()]

    ts = time.strftime("%Y%m%d_%H%M%S")
    rundir = os.path.join(a.outdir, "run_" + ts)
    os.makedirs(rundir, exist_ok=True)
    print("[out]", rundir)

    pids = find_pids()
    print("[mem] 采样", pids, "间隔 0.25s")
    sampler = Sampler(os.path.join(rundir, "memory_timeseries.csv"))
    sampler.start()

    rows, timings = [], []
    try:
        p0 = pools()
        sap = p0.get("sapling", 0)
        print("[pool] 余额:", p0)
        # 自转（收付同一地址）：本金每轮回到 sapling 池，净支出只有手续费，
        # 所以按「单轮金额」而不是「金额×轮数」判断，否则大金额 scaling 会被误拒。
        need = int((a.amount_zec + 0.001) * 1e8)
        if sap < need:
            print("[!] sapling 余额 %d zat 不足单轮 %.2f ZEC + 手续费" % (sap, a.amount_zec))
            return 1
        print("[pool] 每轮自转 %.2f ZEC（净支出仅手续费），%d 轮"
              % (a.amount_zec, a.rounds))

        from_ua = sapling_ua()
        print("[addr] 花费地址（sapling-only UA）:", from_ua[:40] + "...")
        # 收款地址：N>1 时派生 N 个不同的 sapling 地址（只请求 ["sapling"]，
        # 不推进透明地址 index）；N=1 时自转，资金回到本账户。
        if a.outputs > 1:
            recipients = [sapling_ua() for _ in range(a.outputs)]
            print("[addr] %d 个收款地址（每个 %.4f ZEC），首地址: %s"
                  % (len(recipients), a.amount_zec / a.outputs, recipients[0][:36] + "..."))
        else:
            recipients = [from_ua]

        for i in range(1, a.rounds + 1):
            if sampler:
                sampler.round = i
            try:
                row, T = one_round(i, a, from_ua, recipients, policy_order)
            except Exception as e:
                print("  [error] round %d 失败：%s" % (i, str(e)[:300]))
                rows.append({"round": i, "error": str(e)[:300]})
                try:
                    wait_sync()
                except Exception:
                    pass
                continue
            rows.append(row)
            timings.append((i, T))
            row["_T"] = T
    finally:
        sampler.stop_evt.set()
        sampler.join(timeout=5)

    # ---- 落盘 ----
    cols = (["round", "txid", "opid", "policy", "sapling_spends", "sapling_outputs",
             "sapling_proofs", "t_spends", "t_outputs", "tx_size", "fee_zat",
             "fee_measured_zat", "confirmations"] + STAGES + ["error"])
    with open(os.path.join(rundir, "rounds.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r = dict(r)
            T = r.pop("_T", None) or {}
            for s in STAGES:
                r[s] = "%.1f" % T[s] if s in T else ""
            w.writerow(r)

    with open(os.path.join(rundir, "stage_timings.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "stage", "ms"])
        for i, T in timings:
            for s in STAGES:
                if s in T:
                    w.writerow([i, s, "%.1f" % T[s]])

    ok = [r for r in rows if "txid" in r and r.get("txid")]
    if ok:
        with open(os.path.join(rundir, "summary.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["stage", "median_ms", "min_ms", "max_ms", "n"])
            for s in STAGES:
                vals = [T[s] for (_i, T) in timings if s in T]
                if vals:
                    w.writerow([s, "%.1f" % statistics.median(vals),
                                "%.1f" % min(vals), "%.1f" % max(vals), len(vals)])

    # ---- 按 (spends, outputs) 形态分组 ----
    groups = {}
    for r in ok:
        k = (r.get("sapling_spends"), r.get("sapling_outputs"))
        if k[0] is None:
            continue
        groups.setdefault(k, []).append(r)

    def pipe_of(g):
        ids = {x["round"] for x in g}
        return [T["pipeline"] for (i, T) in timings if i in ids]

    if groups:
        with open(os.path.join(rundir, "summary_by_shape.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sapling_spends", "sapling_outputs", "proofs", "n",
                        "pipeline_median_ms", "pipeline_min_ms", "pipeline_max_ms", "size"])
            for k in sorted(groups):
                g = groups[k]
                pipe = pipe_of(g)
                sizes = sorted({x.get("tx_size") for x in g if x.get("tx_size")})
                w.writerow([k[0], k[1], (k[0] or 0) + (k[1] or 0), len(g),
                            "%.1f" % statistics.median(pipe) if pipe else "",
                            "%.1f" % min(pipe) if pipe else "",
                            "%.1f" % max(pipe) if pipe else "",
                            sizes[0] if len(sizes) == 1 else str(sizes)])

    try:
        ncpu = int(os.popen("nproc").read().strip())
    except Exception:
        ncpu = None
    json.dump({"args": vars(a), "pids": pids, "pools_before": p0,
               "nproc": ncpu, "cpu_model": os.popen(
                   "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").read().strip(),
               "timestamp": ts}, open(os.path.join(rundir, "meta.json"), "w"), indent=1)

    # ---- 屏幕汇总 ----
    print("\n=== 汇总（中位数，n=%d）===" % len(ok))
    print("%-10s %12s %12s %12s" % ("stage", "median_ms", "min_ms", "max_ms"))
    for s in STAGES:
        vals = [T[s] for (_i, T) in timings if s in T]
        if vals:
            print("%-10s %12.1f %12.1f %12.1f"
                  % (s, statistics.median(vals), min(vals), max(vals)))

    if groups:
        print("\n=== 按形态（spends, outputs）分组 ===")
        print("%-8s %-8s %-7s %4s %18s %14s"
              % ("spends", "outputs", "proofs", "n", "pipeline中位(ms)", "tx_size(B)"))
        for k in sorted(groups):
            g = groups[k]
            pipe = pipe_of(g)
            sizes = sorted({x.get("tx_size") for x in g if x.get("tx_size")})
            print("%-8s %-8s %-7s %4d %18.1f %14s"
                  % (k[0], k[1], (k[0] or 0) + (k[1] or 0), len(g),
                     statistics.median(pipe) if pipe else 0,
                     sizes[0] if len(sizes) == 1 else str(sizes)))

        # 以「证明个数 = spends + outputs」为自变量做最小二乘：
        # Sapling 的 Groth16 是逐 Spend / 逐 Output 各证一次的，所以证明个数才是
        # 真正的成本驱动量；outputs 固定为 2 时，斜率同样反映单 spend 边际成本。
        pts = [((k[0] or 0) + (k[1] or 0), statistics.median(pipe_of(g)))
               for k, g in sorted(groups.items())]
        pts = [(x, y) for x, y in pts if x > 0]
        if len(pts) >= 2:
            sl, ic, r2 = fit([x for x, _y in pts], [y for _x, y in pts])
            print("\n  线性拟合 pipeline = %.1f × proofs + %.1f   (R²=%.4f)"
                  % (sl, ic, r2))
            print("  → 单个 Groth16 证明边际成本 ≈ %.0f ms；固定开销 ≈ %.0f ms"
                  % (sl, ic))
        else:
            print("\n  [!] 只有一个证明数分组，无法拟合斜率。")
            print("      换一个金额重跑（如 --amount-zec 30 迫使多 spend），两组并起来看。")

    print("\n输出:", rundir)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
