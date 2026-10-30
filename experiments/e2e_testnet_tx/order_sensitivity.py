#!/usr/bin/env python3
"""顺序敏感性诊断（**探索性**，非预注册分析）。

背景
----
预注册 §6 要求「50 次测量以随机顺序执行（预先生成随机序列并落盘）」。
实际执行器（`confirmatory_bench.py` L1718-1721）做的是**形态块随机化**：
先把 10 个形态的顺序随机打乱，再对每个形态连续跑满 5 次有效样本。
两者都随机化，但块内 5 次观测在时间上相邻，可能共享同一时段的温度 /
负载 / 节点状态，从而引入组内相关。本脚本量化这种可能性的量级。

做法
----
预注册的模型选择与假设判定都建立在**形态中位数**上（每组 5 个数先取中位数，
再拟合 M3）。中位数把组内相关基本吸收掉了，但为回答「顺序是否真的影响结论」，
本脚本在**轮次级**（50 个观测等权）上做三组对照：

  R0: y = a_S·S + c_O·O + b                     （基线，无顺序项）
  R1: y = a_S·S + c_O·O + b + d·block_idx      （形态块序号 1..10 作时间代理）
  R2: y = a_S·S + c_O·O + b + d·round_idx      （测量轮次 1..50 作时间代理）

关注量：Δ = a_S − c_O（H_A 的核心量）在三种设定下是否保持同号、量级是否稳定。

明确的边界
----------
* 这**不是**预注册分析，**不**用于替换或修正 `FIT.md` / `RESULTS.md` 的数值。
* `rounds.csv` 未记录逐轮墙钟时间戳（只有 round 序号），故时间代理只能是序号，
  无法做真实的时间漂移（drift）分析。
* 结论只用于评估「块随机化」对主判据的敏感性，不改任何裁决。

用法
----
    python3 order_sensitivity.py
    python3 order_sensitivity.py --run raw/confirmatory_20261030/run_20261030_201124
"""
import argparse
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUN = os.path.join(HERE, "raw", "confirmatory_20261030", "run_20261030_201124")


def load_rounds(run_dir):
    """读单个正式 run 的轮次级样本（只取成功且形态/手续费匹配的轮次）。"""
    path = os.path.join(run_dir, "rounds.csv")
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r.get("error") or "").strip():
                continue
            if not (r.get("txid") or "").strip():
                continue
            fm = (r.get("form_match") or "").strip().lower()
            fem = (r.get("fee_match") or "").strip().lower()
            if fm not in ("true", "1", "yes") or fem not in ("true", "1", "yes"):
                continue
            s = float(r["sapling_spends"])
            o = float(r["sapling_outputs"])
            y = float(r["pipeline"])
            rows.append(dict(round=int(r["round"]), spends=int(s), outputs=int(o),
                             pipeline=y))
    return rows


def fit_lstsq(X, y):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return coef, r2


def design(rows, order_key=None):
    n = len(rows)
    cols = [np.array([r["spends"] for r in rows], dtype=float),
            np.array([r["outputs"] for r in rows], dtype=float),
            np.ones(n)]
    if order_key == "block":
        # 形态块序号：按出现顺序给每个 unique 形态编号 1..10
        seen, block = {}, []
        for r in rows:
            k = (r["spends"], r["outputs"])
            if k not in seen:
                seen[k] = len(seen) + 1
            block.append(float(seen[k]))
        cols.append(np.array(block))
    elif order_key == "round":
        cols.append(np.array([float(r["round"]) for r in rows]))
    return np.column_stack(cols)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=DEFAULT_RUN, help="正式 run 目录")
    args = ap.parse_args()

    if not os.path.isdir(args.run):
        sys.exit("找不到 run 目录: %s" % args.run)

    rows = load_rounds(args.run)
    if len(rows) != 50:
        sys.exit("预期 50 轮成功样本，实际 %d 轮" % len(rows))

    shapes = sorted({(r["spends"], r["outputs"]) for r in rows})
    block_order = []
    for r in rows:
        k = (r["spends"], r["outputs"])
        if not block_order or block_order[-1] != k:
            block_order.append(k)
    print("样本：%d 轮 / %d 形态（来源 %s）" % (len(rows), len(shapes),
                                              os.path.basename(args.run.rstrip("/"))))
    print("实际形态块执行顺序（按 rounds.csv 出现次序）：%s"
          % " → ".join("(%d,%d)" % s for s in block_order))
    print("块大小：%s"
          % ", ".join("(%d,%d)=%d" % (s + (sum(1 for r in rows
                                               if (r["spends"], r["outputs"]) == s),))
                      for s in block_order))
    print()

    y = np.array([r["pipeline"] for r in rows], dtype=float)
    results = {}

    print("%-6s %-34s %10s %10s %10s %10s %8s" %
          ("设定", "模型", "a_S", "c_O", "b", "d(顺序)", "R²"))
    print("-" * 94)
    for tag, key, label in (
        ("R0", None, "y ~ S + O + 1"),
        ("R1", "block", "y ~ S + O + b·block_idx + 1"),
        ("R2", "round", "y ~ S + O + d·round_idx + 1"),
    ):
        X = design(rows, key)
        coef, r2 = fit_lstsq(X, y)
        a, c, b = coef[0], coef[1], coef[2]
        d = coef[3] if len(coef) > 3 else float("nan")
        results[tag] = dict(a=a, c=c, b=b, d=d, r2=r2, delta=a - c)
        print("%-6s %-34s %10.2f %10.2f %10.2f %10.2f %8.4f"
              % (tag, label, a, c, b, d, r2))

    print()
    print("=== 关注量 Δ = a_S − c_O（H_A 核心量）===")
    base = results["R0"]["delta"]
    for tag in ("R0", "R1", "R2"):
        r = results[tag]
        print("  %s: Δ = %8.2f ms   相对 R0 %+7.2f ms (%+6.2f%%)"
              % (tag, r["delta"], r["delta"] - base, (r["delta"] - base) / base * 100.0))

    print()
    print("=== 判读 ===")
    same_sign = all(results[t]["delta"] > 0 for t in results)
    max_shift = max(abs(results[t]["delta"] - base) for t in results)
    print("  三种设定下 Δ 是否同号（均 > 0）：%s" % ("是" if same_sign else "否"))
    print("  顺序项对 Δ 的最大扰动：%.2f ms（占基线 %.1f%%）"
          % (max_shift, max_shift / base * 100.0))
    print("  c_O 在 R1/R2 下相对 R0 的变化：%+.2f / %+.2f ms（%+.1f%% / %+.1f%%）"
          % (results["R1"]["c"] - results["R0"]["c"],
             results["R2"]["c"] - results["R0"]["c"],
             (results["R1"]["c"] / results["R0"]["c"] - 1) * 100.0,
             (results["R2"]["c"] / results["R0"]["c"] - 1) * 100.0))
    print()
    print("  注：R0 为轮次级基线，与 FIT.md 的形态中位数拟合（M3）**不等价**，")
    print("      两者数值差异来自「每轮等权」与「每形态等权」的加权方式不同；")
    print("      预注册的假设判定一律以形态中位数拟合为准，本表不参与裁决。")


if __name__ == "__main__":
    main()
