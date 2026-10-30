#!/usr/bin/env python3
"""H_A / H_B 判据 bootstrap（预注册 §8 冻结算法，§9 判据）。

- 每次 bootstrap：在每个形态的成功测量中有放回重采样，重算该形态中位数；
  用这些中位数重新拟合 M3，得到 (a_S, c_O, b)。
- H_A: Δ = a_S − c_O 的分布 → 95% 百分位区间，下界 > 0 即接受。
- H_B: (4,2) 与 (3,3) 各自独立重采样中位数 → 两中位数之差的 95% 百分位区间，
       不含 0 且点估计同号、量级落在 [300, 800] ms 视为稳定。

固定 B=4000、seed=20261030（与预注册一致）。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_sapling_e2e_model as F  # noqa: E402

B = 4000
SEED = 20261030
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw", "confirmatory_20261030")

rows = F.load_all(RAW)
if not rows:
    raise SystemExit("无样本")

# 按形态分组（保留原始轮次值）
groups = {}
for r in rows:
    groups.setdefault((r["spends"], r["outputs"]), []).append(r["pipeline"])

shapes_all = F.aggregate(rows)
shapes_all = [s for s in shapes_all if s["spends"] is not None]
print("样本：%d 轮 / %d 形态" % (len(rows), len(shapes_all)))

# 点估计
X, y = F.design(shapes_all, "M3")
coef, pred, *_ = F.fit(X, y)
a_pt, c_pt, b_pt = coef
print("点估计 M3: a_S=%.2f  c_O=%.2f  b=%.2f  Δ=a_S−c_O=%.2f"
      % (a_pt, c_pt, b_pt, a_pt - c_pt))

rng = np.random.default_rng(SEED)
keys = sorted(groups.keys())
deltas = []
hb_diffs = []

for _ in range(B):
    shapes = []
    med = {}
    for k in keys:
        vals = np.array(groups[k], dtype=float)
        samp = rng.choice(vals, size=len(vals), replace=True)
        m = float(np.median(samp))
        med[k] = m
        s, o = k
        shapes.append(dict(spends=s, outputs=o, proofs=s + o, pipeline=m, n=len(vals)))
    Xb, yb = F.design(shapes, "M3")
    cb, *_ = F.fit(Xb, yb)
    deltas.append(cb[0] - cb[1])
    if (4, 2) in med and (3, 3) in med:
        hb_diffs.append(med[(4, 2)] - med[(3, 3)])

deltas = np.array(deltas)
hb = np.array(hb_diffs)


def ci(a, lo=2.5, hi=97.5):
    return float(np.percentile(a, lo)), float(np.percentile(a, hi))


print()
print("=== H_A：Δ = a_S − c_O（B=%d, seed=%d）===" % (B, SEED))
d_lo, d_hi = ci(deltas)
print("  点估计 Δ = %.2f ms" % (a_pt - c_pt))
print("  bootstrap 均值 = %.2f ms" % deltas.mean())
print("  95%% CI = [%.2f, %.2f] ms" % (d_lo, d_hi))
print("  判据：CI 下界严格 > 0 → %s" % ("接受 H_A" if d_lo > 0 else "未能重复确认 H_A"))

print()
print("=== H_B：(4,2) − (3,3) 中位数差（B=%d, seed=%d）===" % (B, SEED))
m42 = float(np.median(groups[(4, 2)]))
m33 = float(np.median(groups[(3, 3)]))
pt = m42 - m33
h_lo, h_hi = ci(hb)
print("  (4,2) 中位 = %.1f ms   (3,3) 中位 = %.1f ms" % (m42, m33))
print("  点估计差 = %.2f ms" % pt)
print("  95%% CI = [%.2f, %.2f] ms" % (h_lo, h_hi))
same_sign = (pt > 0 and h_lo > 0) or (pt < 0 and h_hi < 0)
in_range = 300 <= abs(pt) <= 800
print("  判据：CI 不含 0 → %s；点估计同号 → %s；量级 |%.0f| ∈ [300,800] → %s"
      % (not (h_lo <= 0 <= h_hi), same_sign, abs(pt), in_range))
ok = (not (h_lo <= 0 <= h_hi)) and same_sign
print("  判定：%s" % ("接受 H_B（稳定）" if ok and in_range
                    else ("接受 H_B（方向一致但量级不稳）" if ok else "未能重复确认 H_B")))

print()
print("=== H_C：M3 相对 M1 的按形态 LOO RMSE ===")
loos = {}
for kind in ("M1", "M2", "M3"):
    Xk, yk = F.design(shapes_all, kind)
    lk, _ = F.loo(Xk, yk)
    loos[kind] = lk
    print("  %s LOO-RMSE = %.2f ms" % (kind, lk))
rel = (loos["M1"] - loos["M3"]) / loos["M1"] * 100.0
absd = loos["M1"] - loos["M3"]
ok_hc = (rel >= 10.0) and (absd >= 20.0) and (loos["M3"] < loos["M2"])
print("  相对下降 = %.1f%%（判据 ≥10%%）；绝对差 = %.1f ms（判据 ≥20 ms）" % (rel, absd))
print("  M3 (%.2f) < M2 (%.2f) → %s" % (loos["M3"], loos["M2"], loos["M3"] < loos["M2"]))
print("  判定：%s" % ("接受 H_C" if ok_hc else "未能重复确认 H_C"))
