#!/usr/bin/env python3
"""
bootstrap_sapling_ci.py
-----------------------
给 M3 的三个系数算自助法（bootstrap）置信区间，回答一个具体问题：
    「output 边际 91.5 ms 这个数，到底有多可信？」

两种重采样口径（都做，互为对照）：
  A) 轮级：对 29 个成功轮次有放回重采样（保留真实采样结构，O=2 形态自然占多数）
  B) 形态级：对 11 个 (spends, outputs) 形态等权重采样（消除采样不均衡）

输出：系数均值、95% 百分位区间、区间相对宽度。
用法：python3 bootstrap_sapling_ci.py [--B 4000]
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_sapling_e2e_model as F  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))


def fit_m3(spends, outputs, y):
    X = np.column_stack([spends, outputs, np.ones(len(spends))])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef


def bootstrap_rounds(rows, B, rng):
    S = np.array([r["spends"] for r in rows], float)
    O = np.array([r["outputs"] for r in rows], float)
    y = np.array([r["pipeline"] for r in rows], float)
    n = len(y)
    out = np.empty((B, 3))
    for b in range(B):
        idx = rng.integers(0, n, n)
        out[b] = fit_m3(S[idx], O[idx], y[idx])
    return out


def bootstrap_shapes(shapes, B, rng):
    S = np.array([s["spends"] for s in shapes], float)
    O = np.array([s["outputs"] for s in shapes], float)
    y = np.array([s["pipeline"] for s in shapes], float)
    n = len(y)
    out = np.empty((B, 3))
    for b in range(B):
        idx = rng.integers(0, n, n)
        out[b] = fit_m3(S[idx], O[idx], y[idx])
    return out


def summarize(name, samples, point):
    lo, hi = np.percentile(samples, [2.5, 97.5], axis=0)
    mean = samples.mean(axis=0)
    print(f"\n=== {name}（B={len(samples)}）===")
    print(f"{'系数':<12}{'点估计':>10}{'bootstrap 均值':>16}{'95% CI':>24}{'相对宽度':>12}")
    for i, label in enumerate(("spends", "outputs", "固定开销")):
        width = (hi[i] - lo[i]) / point[i] * 100 if point[i] else float("nan")
        print(f"{label:<12}{point[i]:>10.1f}{mean[i]:>16.1f}"
              f"{f'[{lo[i]:.1f}, {hi[i]:.1f}]':>24}{f'{width:.0f}%':>12}")
    # 关键判据：output 区间是否包含 0；spend/output 比值区间
    ratio = samples[:, 0] / samples[:, 1]
    rlo, rhi = np.percentile(ratio, [2.5, 97.5])
    o_lo, o_hi = lo[1], hi[1]
    print(f"\noutput 95% CI = [{o_lo:.1f}, {o_hi:.1f}] ms"
          + ("  <- 包含 0，output 可能免费" if o_lo <= 0 <= o_hi else "  <- 不含 0，output 成本确实存在"))
    print(f"spend/output 比值 95% CI = [{rlo:.2f}, {rhi:.2f}]"
          + ("  <- 含 1，无法区分" if rlo <= 1 <= rhi else "  <- 远离 1，两者不同价"))
    return dict(point=point, lo=lo, hi=hi, mean=mean, ratio=(rlo, rhi))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--raw-dir", default=os.path.join(BASE, "raw"))
    args = ap.parse_args()

    rows = F.load_all(args.raw_dir)
    shapes = F.aggregate(rows)
    if not rows:
        sys.exit("没有可用数据")

    point = fit_m3(np.array([r["spends"] for r in rows], float),
                   np.array([r["outputs"] for r in rows], float),
                   np.array([r["pipeline"] for r in rows], float))
    Xs, ys = F.design(shapes, "M3")
    point_shape, *_ = np.linalg.lstsq(Xs, ys, rcond=None)

    rng = np.random.default_rng(args.seed)
    print(f"样本：{len(rows)} 轮 / {len(shapes)} 形态")
    print(f"点估计（轮级 OLS）：  {point[0]:.1f} ms/spend + {point[1]:.1f} ms/output + {point[2]:.1f} ms")
    print(f"点估计（形态中位）：  {point_shape[0]:.1f} ms/spend + {point_shape[1]:.1f} ms/output + {point_shape[2]:.1f} ms")

    a = bootstrap_rounds(rows, args.B, rng)
    summarize("A 轮级重采样（保留采样结构）", a, point)
    b = bootstrap_shapes(shapes, args.B, rng)
    summarize("B 形态级重采样（等权，消除不均衡）", b, point_shape)


if __name__ == "__main__":
    main()
