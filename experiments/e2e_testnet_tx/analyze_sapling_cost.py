#!/usr/bin/env python3
"""
Sapling 端到端成本模型拟合（离线分析，读 raw/ 下的 rounds.csv）。

要回答的问题
  pipeline 耗时的自变量到底是谁？三个候选：
    M1  proofs = spends + outputs           （证明个数）
    M2  spends 单独
    M3  spends 与 outputs 各自的边际成本     （两变量最小二乘）
  三个 run 的 (spends, outputs) 组合已经覆盖 3 输出与 2 输出，足以判别 M1 与 M2 的差别。

同时做两件事
  - ZIP 317 手续费交叉验证：fee 应等于 5000 × max(spends, outputs)，用于确认形态计数正确
  - 单点形态对照：proofs 相同但 (S,O) 不同的样本，直接读出 Spend 与 Output 的价差
"""
import csv
import glob
import os
import statistics as st

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
RUNS = [
    ("v1-15x3", "sapling_e2e_v1/run_20261029_151727"),
    ("scale30", "sapling_e2e_scale30/run_20261029_151839"),
    ("scale60", "sapling_e2e_scale60/run_20261029_151923"),
    ("smoke2", "sapling_smoke2/run_20261029_151658"),
    ("smoke1", "sapling_smoke/run_20261029_151423"),
]

rows = []
for tag, rel in RUNS:
    p = os.path.join(BASE, rel, "rounds.csv")
    if not os.path.exists(p):
        continue
    for r in csv.DictReader(open(p)):
        if not r.get("txid") or r.get("error"):
            continue
        try:
            S = int(r["sapling_spends"])
            O = int(r["sapling_outputs"])
            P = float(r["pipeline"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"run": tag, "round": r["round"], "S": S, "O": O,
                     "P": P, "size": int(r["tx_size"]) if r.get("tx_size") else None,
                     "fee": int(r["fee_zat"]) if r.get("fee_zat") else None,
                     "submit": float(r["submit"]) if r.get("submit") else None})

print("样本数:", len(rows))

# ---------- 1) ZIP 317 手续费交叉验证 ----------
print("\n=== 1) ZIP 317 手续费校验：fee ?= 5000 × max(spends, outputs) ===")
bad = 0
for r in rows:
    if r["fee"] is None:
        continue
    exp = 5000 * max(r["S"], r["O"])
    if r["fee"] != exp:
        bad += 1
        print("  MISMATCH S=%d O=%d fee=%d 期望=%d" % (r["S"], r["O"], r["fee"], exp))
print("  校验结果: %d/%d 一致%s" % (len(rows) - bad, len(rows),
                                "" if bad == 0 else "  <- 形态计数可能有误"))

# ---------- 2) 同 proofs 不同形态的对照 ----------
print("\n=== 2) 证明个数相同、形态不同的样本（直接读出 Spend 与 Output 的价差）===")
by_p = {}
for r in rows:
    by_p.setdefault(r["S"] + r["O"], []).append(r)
for p in sorted(by_p):
    g = by_p[p]
    shapes = {}
    for r in g:
        shapes.setdefault((r["S"], r["O"]), []).append(r["P"])
    if len(shapes) >= 2:
        print("  proofs=%d:" % p)
        for k in sorted(shapes):
            v = shapes[k]
            print("     S=%d O=%d  n=%d  pipeline=%s"
                  % (k[0], k[1], len(v),
                     "/".join("%.0f" % x for x in sorted(v))))

# ---------- 3) 三种模型拟合 ----------
def lstsq(X, y):
    """最小二乘（正规方程，高斯消元）。X 每行含截距列。"""
    n, m = len(X), len(X[0])
    A = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(m)] + [sum(X[k][i] * y[k] for k in range(n))]
         for i in range(m)]
    for i in range(m):
        piv = max(range(i, m), key=lambda r: abs(A[r][i]))
        A[i], A[piv] = A[piv], A[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for r in range(m):
            if r != i:
                f = A[r][i] / A[i][i]
                for c in range(i, m + 1):
                    A[r][c] -= f * A[i][c]
    return [A[i][m] / A[i][i] for i in range(m)]


def report(name, X, y, terms):
    co = lstsq(X, y)
    if co is None:
        print("  %-28s 退化" % name)
        return None
    pred = [sum(c * x for c, x in zip(co, row)) for row in X]
    my = sum(y) / len(y)
    ss_tot = sum((v - my) ** 2 for v in y)
    ss_res = sum((a - b) ** 2 for a, b in zip(y, pred))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0
    rmse = (ss_res / len(y)) ** 0.5
    eq = " + ".join("%.1f×%s" % (c, t) for c, t in zip(co, terms))
    print("  %-28s %s   R²=%.4f  RMSE=%.0f ms" % (name, eq, r2, rmse))
    return co, r2, rmse


print("\n=== 3) 三模型对比（全部 %d 个样本）===" % len(rows))
y = [r["P"] for r in rows]
report("M1 pipeline=a·proofs+c",
       [[r["S"] + r["O"], 1] for r in rows], y, ["proofs", "1"])
report("M2 pipeline=a·spends+c",
       [[r["S"], 1] for r in rows], y, ["spends", "1"])
co3, r2_3, rmse3 = report("M3 pipeline=a·S+b·O+c",
                          [[r["S"], r["O"], 1] for r in rows], y,
                          ["spends", "outputs", "1"])

# 物理约束：强制截距 >= 0 的估计（仅当 M3 截距为负时提示）
print("\n=== 4) 按 Spend 数分层的 pipeline（O=2 子集，检验线性度）===")
sub = [r for r in rows if r["O"] == 2]
by_s = {}
for r in sub:
    by_s.setdefault(r["S"], []).append(r["P"])
prev = None
for s in sorted(by_s):
    v = by_s[s]
    m = st.median(v)
    d = "" if prev is None else "   Δ=%.0f ms/spend" % ((m - prev) / (s - prev_s))
    print("  S=%-3d n=%d  pipeline中位=%8.0f ms  size=%s B%s"
          % (s, len(v), m,
             sorted({x["size"] for x in sub if x["S"] == s and x["size"]}), d))
    prev, prev_s = m, s

# ---------- 5) 结论行 ----------
if co3:
    a, b, c = co3
    print("\n=== 5) 结论 ===")
    print("  每 Spend   ≈ %.0f ms" % a)
    print("  每 Output  ≈ %.0f ms" % b)
    print("  固定开销   ≈ %.0f ms" % c)
    print("  Spend / Output = %.2f 倍" % (a / b if b else float("nan")))
    if c < 0:
        print("  [!] 截距为负，说明还有未纳入的自变量（可能随 tx 尺寸或 note 数变化的项），"
              "不宜外推到大 spend 数之外")
