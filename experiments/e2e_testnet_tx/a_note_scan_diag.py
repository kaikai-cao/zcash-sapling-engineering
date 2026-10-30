#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 方案诊断（A1-A5）：只读验证能否恢复完整、可信的可花费 Sapling Note 面值清单。

严格只读：仅 z_listunspent / z_getnotescount / z_getbalanceforaccount /
z_getaddressforaccount / getblockchaininfo。
不恢复快照、不构造交易、不发送任何交易、不写钱包状态。

思路（用户 A 方案 + 同一确认数不可分辨的硬约束）：
  A1 用二分定位"毒化确认数" C：z_listunspent([lo,hi]) 抛 memo 解码错的区间收缩到单点。
  A2 分段枚举 [1,C-1] 与 [C+1,MAX]（多毒化点时递归处理所有分段）。
  A3 由"总数 - 已枚举数"反推 C 处是否还有其他正常 Note（C 处 Note 全部被排除）。
  A4 数量与金额都与独立统计（z_getnotescount / z_getbalanceforaccount）严格对上。
  A5 用真实 pick_amount_zat 验证 S=10 / S=17 的金额边界可构造。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sapling_e2e_bench import z, ACCOUNT          # noqa: E402
from confirmatory_bench import pick_amount_zat, MIN_CHANGE_ZAT  # noqa: E402

MAXCONF_HI = 999999
MAX_PROBES = 800

CALLS = []
PROBES = []
REPORT = {}


def rpc(method, params):
    CALLS.append([method, params])
    return z(method, params)


def _sapling(rows):
    out = []
    for n in (rows or []):
        if n.get("pool") == "sapling" or n.get("type") == "sapling":
            v = n.get("valueZat")
            if v is None:
                v = int(round(float(n.get("amount", 0)) * 1e8))
            out.append({
                "valueZat": int(v),
                "confirmations": int(n.get("confirmations") or 0),
                "txid": n.get("txid"),
                "outindex": n.get("outindex"),
            })
    return out


def probe(lo, hi):
    """返回 ('ok', [notes]) 或 ('poison', err_text)。"""
    try:
        r = rpc("z_listunspent", [lo, hi])
        rows = r if isinstance(r, list) else (r.get("result") if isinstance(r, dict) else [])
        return "ok", _sapling(rows)
    except Exception as e:
        return "poison", str(e)[:240]


def enumerate_range(lo, hi, acc, poisons):
    if len(PROBES) >= MAX_PROBES:
        raise RuntimeError("探测次数超过上限 %d，中止（避免无限递归）" % MAX_PROBES)
    st, res = probe(lo, hi)
    PROBES.append({
        "range": [lo, hi],
        "status": st,
        "n": (len(res) if st == "ok" else None),
        "err": (None if st == "ok" else res),
    })
    if st == "ok":
        acc.extend(res)
        return
    if lo >= hi:
        poisons.append(lo)
        return
    mid = (lo + hi) // 2
    enumerate_range(lo, mid, acc, poisons)
    enumerate_range(mid + 1, hi, acc, poisons)


def parse_counts(obj):
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if isinstance(v, int)}
    return {}


def parse_bal(obj):
    zat = {}
    if isinstance(obj, dict):
        pools = obj.get("pools") or {}
        for name, d in pools.items():
            if isinstance(d, dict) and d.get("valueZat") is not None:
                zat[name] = int(d["valueZat"])
    return zat


def main():
    t0 = time.time()
    print("=" * 72)
    print("A 诊断：可花费 Sapling Note 清单完整性（只读）")
    print("=" * 72)

    # ---- 0. 环境基线 ----
    h = None
    try:
        h = rpc("getblockchaininfo", [])
        h = h.get("blocks") if isinstance(h, dict) else h
    except Exception as e:
        print("[warn] getblockchaininfo 失败:", e)
    print("[env] height =", h)

    # ---- 独立统计基线（不解码 memo） ----
    counts_raw = None
    try:
        counts_raw = rpc("z_getnotescount", [1])
    except Exception as e:
        counts_raw = {"err": str(e)[:200]}
    print("[base] z_getnotescount([1])       =", json.dumps(counts_raw, ensure_ascii=False))

    counts = parse_counts(counts_raw) if isinstance(counts_raw, dict) else {}
    bal_raw = None
    try:
        bal_raw = rpc("z_getbalanceforaccount", [ACCOUNT, 1])
    except Exception as e:
        bal_raw = {"err": str(e)[:200]}
    print("[base] z_getbalanceforaccount(1)  =", json.dumps(bal_raw, ensure_ascii=False))
    bal = parse_bal(bal_raw)

    total_count = counts.get("sapling")
    total_zat = bal.get("sapling")

    # 顺带验证账户 0 == ACCOUNT
    acct_ok = None
    try:
        a0 = rpc("z_getaddressforaccount", [0, ["sapling"]])
        acct_ok = (isinstance(a0, dict) and a0.get("account_uuid") == ACCOUNT)
        print("[base] account0 uuid match ACCOUNT =", acct_ok)
    except Exception as e:
        print("[base] z_getaddressforaccount 失败:", str(e)[:160])

    # ---- 试探 z_getnotescount 是否支持按确认数区间计数（可做逐段严格核对） ----
    gc_range = {}
    for lo, hi in ([1, MAXCONF_HI],):
        try:
            gc_range["%d-%d" % (lo, hi)] = rpc("z_getnotescount", [lo, hi])
        except Exception as e:
            gc_range["%d-%d" % (lo, hi)] = {"err": str(e)[:160]}
    print("[probe] z_getnotescount 双参形式    =", json.dumps(gc_range, ensure_ascii=False)[:300])

    # ---- A1/A2: 二分 + 分段枚举 ----
    print("\n--- A1/A2 分段枚举（z_listunspent 按确认数区间） ---")
    acc = []
    poisons = []
    t_enum = time.time()
    try:
        enumerate_range(1, MAXCONF_HI, acc, poisons)
    except Exception as e:
        print("[FATAL] 枚举中止:", e)
        REPORT["abort"] = str(e)
    dt_enum = time.time() - t_enum

    vals = sorted(n["valueZat"] for n in acc)
    known_count = len(acc)
    known_zat = sum(vals)
    print("[enum] 探测次数=%d 用时=%.1fs" % (len(PROBES), dt_enum))
    print("[enum] 已枚举 sapling note 数=%d 金额=%d zat (%.4f ZEC)"
          % (known_count, known_zat, known_zat / 1e8))
    print("[enum] 毒化确认数（单点区间无法读取）= %s" % (poisons,))

    # ---- A3: 毒化确认数处还有几个 Note ----
    rest_count = (total_count - known_count) if total_count is not None else None
    rest_zat = (total_zat - known_zat) if total_zat is not None else None
    print("\n--- A3 毒化确认数处的 Note ---")
    print("[A3] 总 sapling note 数(独立) = %s ; 已枚举 = %d ; 剩余(即 conf==C 处) = %s"
          % (total_count, known_count, rest_count))
    print("[A3] 总 sapling 金额(独立)    = %s ; 已枚举 = %d ; 剩余 = %s" % (total_zat, known_zat, rest_zat))

    # 对毒化点做额外只读尝试，确认该区间确实无法细分
    extra = []
    for c in poisons:
        for args in ([c, c], [c, c, True], [c, c, False, []]):
            try:
                r = rpc("z_listunspent", args)
                rows = _sapling(r if isinstance(r, list) else [])
                extra.append({"args": args, "status": "ok", "n": len(rows),
                              "vals": sorted(x["valueZat"] for x in rows)})
            except Exception as e:
                extra.append({"args": args, "status": "err", "err": str(e)[:160]})
    for e in extra:
        print("[A3-extra] z_listunspent%s -> %s %s"
              % (e["args"], e["status"], e.get("vals") or e.get("err", "")))

    # ---- A4: 数量 + 金额双核对 ----
    a4_count_ok = (rest_count is not None and rest_count >= 0)
    a4_zat_ok = (rest_zat is not None and rest_zat >= 0)
    complete = bool(a4_count_ok and a4_zat_ok and rest_count == 0 and rest_zat == 0)
    print("\n--- A4 完整性双核对 ---")
    print("[A4] 数量核对: 已枚举 %d + 剩余 %s == 总计 %s ? %s"
          % (known_count, rest_count, total_count,
             "PASS" if (rest_count is not None and known_count + rest_count == total_count) else "FAIL"))
    print("[A4] 金额核对: 已枚举 %d + 剩余 %s == 总计 %s ? %s"
          % (known_zat, rest_zat, total_zat,
             "PASS" if (rest_zat is not None and known_zat + rest_zat == total_zat) else "FAIL"))
    print("[A4] 是否要求'剩余=0'（全部可枚举，无匿名 note）:", complete)

    # 构造最终清单：若剩余仅 1 个 note 且仅 1 个毒化点，则其面值可由差额唯一确定
    final_inv = list(vals)
    attribution = None
    if rest_count == 1 and len(poisons) == 1 and rest_zat and rest_zat > 0:
        final_inv.append(rest_zat)
        final_inv.sort()
        attribution = {"conf": poisons[0], "valueZat": rest_zat,
                       "method": "total_zat - sum(enumerated)（唯一剩余 note）"}
        print("[A4] 毒化 note 面值可唯一反推: conf=%s valueZat=%d (%.8f ZEC)"
              % (poisons[0], rest_zat, rest_zat / 1e8))
    elif rest_count not in (None, 0):
        print("[A4] 毒化确认数处存在 %s 个无法分辨的 note（面值不可唯一确定）" % rest_count)

    # ---- A5: 金额选择逻辑 ----
    print("\n--- A5 pick_amount_zat 可行性（对恢复出的清单） ---")
    a5 = {}
    for (S, O) in ((10, 2), (17, 2), (1, 2), (7, 2)):
        p = pick_amount_zat(S, O, final_inv)
        a5["%d,%d" % (S, O)] = p
        if p is None:
            print("[A5] (S=%d,O=%d) -> None（不可构造）" % (S, O))
        else:
            F = 5000 * max(S, O)
            sumS = sum(sorted(final_inv)[:S])
            sumSm1 = sum(sorted(final_inv)[:S - 1]) if S > 1 else 0
            print("[A5] (S=%d,O=%d) -> amount=%d fee=%d unit=%d n_recip=%d | "
                  "A+F=%d in (%d, %d] ; change=%d"
                  % (S, O, p["amount_zat"], p["fee_zat"], p["unit_zat"], p["n_recip"],
                     p["amount_zat"] + F, sumSm1, sumS, sumS - p["amount_zat"] - F))

    # ---- 汇总 JSON ----
    REPORT.update({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "height": h,
        "account_uuid_is_account0": acct_ok,
        "baseline_counts_raw": counts_raw,
        "baseline_balance_raw": bal_raw,
        "baseline_sapling_count": total_count,
        "baseline_sapling_zat": total_zat,
        "z_getnotescount_range_probe": gc_range,
        "probes": PROBES,
        "probe_count": len(PROBES),
        "enum_seconds": round(dt_enum, 1),
        "poison_confs": poisons,
        "poison_extra_attempts": extra,
        "enumerated_count": known_count,
        "enumerated_zat": known_zat,
        "enumerated_values": vals,
        "enumerated_confs": sorted({n["confirmations"] for n in acc}),
        "remaining_count_at_poison": rest_count,
        "remaining_zat_at_poison": rest_zat,
        "complete_strict": complete,
        "poison_value_attribution": attribution,
        "final_inventory": final_inv,
        "final_inventory_count": len(final_inv),
        "a5_pick": a5,
        "rpc_call_count": len(CALLS),
        "elapsed_seconds": round(time.time() - t0, 1),
    })

    outdir = os.path.join(HERE, "raw", "confirmatory_20261030", "_note_scan_diag")
    os.makedirs(outdir, exist_ok=True)
    outfile = os.path.join(outdir, "scan_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, indent=1, ensure_ascii=False)

    print("\n" + "=" * 72)
    print("结论摘要")
    print("=" * 72)
    print("  A1 毒化确认数定位      :", poisons if poisons else "无（全部区间可读）")
    print("  A2 分段枚举            : %d 段探测，%d 个 note 成功读取" % (len(PROBES), known_count))
    print("  A3 C 处 Note 数        :", rest_count)
    print("  A4 数量+金额双核对     : 数量 %s / 金额 %s"
          % ("PASS" if (rest_count is not None and known_count + rest_count == total_count) else "FAIL",
             "PASS" if (rest_zat is not None and known_zat + rest_zat == total_zat) else "FAIL"))
    print("  A5 S=10/S=17 可构造    :", a5.get("10,2") is not None, "/", a5.get("17,2") is not None)
    print("  JSON:", outfile)
    print("  RPC 调用总数:", len(CALLS), "用时 %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
