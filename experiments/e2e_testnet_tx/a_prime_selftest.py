#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A′ 只读自检：验证「钱包 DB 只读清单 + schema 断言 + 双 RPC 硬校验」是否成立。

严格只读：不恢复快照、不发交易、不写钱包 DB、不改预注册。
检查项（对应用户审阅第 4 条）：
  1) 清单 36 条 / 11999980000 zat，且与两个 RPC 聚合值 + 冻结预期值四方相等；
  2) 每条记录身份唯一（txid, output_index），无已 spent，mined_height 合法；
  3) 10 种形态全部可构造；
  4) 每种形态按边界选择的输入数严格 == S，A+F 落在 (sum_{S-1}, sum_S]，
     找零 >= MIN_CHANGE_ZAT，所选 note 金额之和与边界一致；
  5) 三类失败路径确实硬停（预期条数不符 / schema 不符 / DB 不存在）。
"""
import json
import os
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import confirmatory_bench as CB                    # noqa: E402
from sapling_e2e_bench import z, height, ACCOUNT   # noqa: E402

MATRIX = CB.DEFAULT_MATRIX
OUTDIR = os.path.join(HERE, "raw", "confirmatory_20261030", "_note_scan_diag")


def simulate_selection(inv_sorted, need_zat):
    """按「升序取最小 note 直到 >= need」模拟钱包的最小输入数选择（边界模型）。"""
    acc = 0
    chosen = []
    for i, v in enumerate(inv_sorted):
        acc += v
        chosen.append(i)
        if acc >= need_zat:
            break
    return chosen, acc


def spent_note_ids():
    """只读查询已被花费的 note id 集合（用于交叉核对"所选 note 均未花费"）。"""
    con = sqlite3.connect("file:%s?mode=ro" % CB.WALLET_DB_PATH, uri=True, timeout=10)
    try:
        cur = con.cursor()
        return {r[0] for r in cur.execute("SELECT sapling_received_note_id FROM sapling_received_note_spends")}
    finally:
        con.close()


def main():
    rep = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": {}, "forms": {}}
    print("=" * 78)
    print("A′ 只读自检")
    print("=" * 78)
    print("[env] 链高 =", height(), "| DB =", CB.WALLET_DB_PATH)

    # ---- 1) 清单读取（内含 schema 断言 + 双 RPC 硬校验） ----
    recs = CB.note_inventory_detailed()
    assert recs is not None, "note_inventory_detailed() 返回 None"
    inv = [r["value_zat"] for r in recs]
    total = sum(inv)

    bal = z("z_getbalanceforaccount", [ACCOUNT, 1])
    rpc_zat = int(bal["pools"]["sapling"]["valueZat"])
    rpc_cnt = int(z("z_getnotescount", [1])["sapling"])
    print("[1] DB 条数=%d 总额=%d | RPC 条数=%d 余额=%d | 预期 %d / %d"
          % (len(inv), total, rpc_cnt, rpc_zat,
             CB.EXPECTED_SAPLING_NOTE_COUNT, CB.EXPECTED_SAPLING_ZAT))
    c1 = (len(inv) == rpc_cnt == CB.EXPECTED_SAPLING_NOTE_COUNT
          and total == rpc_zat == CB.EXPECTED_SAPLING_ZAT)
    print("    四方一致:", c1)

    # ---- 2) 逐条身份 / spent / 高度 ----
    ids = [(r["txid"], r["output_index"]) for r in recs]
    uniq = len(set(ids)) == len(ids)
    spent = spent_note_ids()
    overlap = [r["note_id"] for r in recs if r["note_id"] in spent]
    heights = [r["mined_height"] for r in recs]
    confs = [r["confirmations"] for r in recs]
    c2 = uniq and not overlap and all(0 < x <= (height() or 0) for x in heights)
    print("[2] 身份唯一=%s | 与已花费集重叠=%d | mined_height %d..%d | 确认数 %d..%d -> %s"
          % (uniq, len(overlap), min(heights), max(heights), min(confs), max(confs), c2))

    # ---- 面值分布 ----
    from collections import Counter
    dist = dict(sorted(Counter(inv).items()))
    print("[3] 面值分布(zat):", dist)
    print("    面值分布(ZEC):", {k / 1e8: v for k, v in dist.items()})

    # ---- 4) 10 形态：构造 + 精确 S 选择 ----
    print("\n%-10s %-12s %-8s %-6s %-30s %-9s %-6s" %
          ("form", "amount_zat", "fee", "n_in", "A+F in (sum_{S-1}, sum_S]", "change", "OK"))
    print("-" * 90)
    all_ok = True
    for (S, O) in MATRIX:
        p = CB.pick_amount_zat(S, O, inv)
        if p is None:
            print("(S=%-2d,O=%d)  pick=None" % (S, O))
            rep["forms"]["%d,%d" % (S, O)] = {"pick": None}
            all_ok = False
            continue
        F = 5000 * max(S, O)
        need = p["amount_zat"] + F
        chosen, acc = simulate_selection(inv, need)
        sumS = sum(inv[:S])
        sumSm1 = sum(inv[:S - 1]) if S > 1 else 0
        change = acc - need
        ok = (len(chosen) == S
              and acc == sumS
              and need > sumSm1 and need <= sumS
              and change >= CB.MIN_CHANGE_ZAT
              and len(set(chosen)) == len(chosen))
        all_ok = all_ok and ok
        print("(S=%-2d,O=%d)  %-12d %-8d %-6d (%d, %d]%s %-9d %s"
              % (S, O, p["amount_zat"], p["fee_zat"], len(chosen),
                 sumSm1, sumS, " " * max(0, 18 - len(str(sumS))), change, "OK" if ok else "FAIL"))
        rep["forms"]["%d,%d" % (S, O)] = {
            "pick": p, "selected_inputs": len(chosen), "selected_sum_zat": acc,
            "need_zat": need, "bound_lo_exclusive": sumSm1, "bound_hi_inclusive": sumS,
            "change_zat": change, "ok": ok,
            "selected_values": [inv[i] for i in chosen],
            "selected_note_ids": [recs[i]["note_id"] for i in chosen],
        }

    # ---- 5) 失败路径必须硬停 ----
    print("\n[5] 失败路径（必须硬停，不允许降级/回退）")
    neg = {}

    old_cnt = CB.EXPECTED_SAPLING_NOTE_COUNT
    try:
        CB.EXPECTED_SAPLING_NOTE_COUNT = 99
        try:
            CB.note_inventory_detailed()
            neg["count_mismatch"] = "NO-STOP(FAIL)"
        except CB.StateError as e:
            neg["count_mismatch"] = "StateError: " + str(e).replace("\n", " | ")[:120]
        except Exception as e:
            neg["count_mismatch"] = type(e).__name__ + ": " + str(e)[:120]
    finally:
        CB.EXPECTED_SAPLING_NOTE_COUNT = old_cnt

    old_path = CB.WALLET_DB_PATH
    tmpd = tempfile.mkdtemp(prefix="a_prime_")
    bogus = os.path.join(tmpd, "bogus.db")
    con = sqlite3.connect(bogus)
    con.execute("CREATE TABLE unrelated(x INTEGER)")
    con.commit()
    con.close()
    try:
        CB.WALLET_DB_PATH = bogus
        try:
            CB.note_inventory_detailed()
            neg["schema_mismatch"] = "NO-STOP(FAIL)"
        except CB.SchemaMismatch as e:
            neg["schema_mismatch"] = "SchemaMismatch: " + str(e)[:120]
        except Exception as e:
            neg["schema_mismatch"] = type(e).__name__ + ": " + str(e)[:120]
    finally:
        CB.WALLET_DB_PATH = old_path

    try:
        CB.WALLET_DB_PATH = os.path.join(tmpd, "does_not_exist.db")
        r = CB.note_inventory_detailed()
        neg["db_missing"] = "None（上层硬停）" if r is None else "NO-STOP(FAIL)"
    finally:
        CB.WALLET_DB_PATH = old_path

    for k, v in neg.items():
        print("    %-16s -> %s" % (k, v))
    neg_ok = all("FAIL" not in str(v) for v in neg.values())

    # ---- 汇总 ----
    print("\n" + "=" * 78)
    print("结论：清单四方一致=%s | 记录合法=%s | 10 形态全可构造且输入数严格==S=%s | 失败路径硬停=%s"
          % (c1, c2, all_ok, neg_ok))
    print("=" * 78)

    rep["checks"] = {"four_way_equal": c1, "records_valid": c2,
                     "all_forms_ok": all_ok, "fail_paths_hard_stop": neg_ok,
                     "note_count": len(inv), "note_total_zat": total,
                     "rpc_count": rpc_cnt, "rpc_zat": rpc_zat,
                     "value_distribution_zat": dist,
                     "mined_height_range": [min(heights), max(heights)],
                     "confirmations_range": [min(confs), max(confs)]}
    rep["negative_tests"] = neg
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "a_prime_selftest_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, ensure_ascii=False)
    print("JSON:", out)
    return 0 if (c1 and c2 and all_ok and neg_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
