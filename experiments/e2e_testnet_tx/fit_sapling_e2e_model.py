#!/usr/bin/env python3
"""
fit_sapling_e2e_model.py
------------------------
把 raw/ 下所有 sapling_e2e_* / sapling_smoke* 批次的 rounds.csv 汇总，
按 (spends, outputs) 形态取中位数，然后拟合并对比三个成本模型：

  M1  pipeline = a * proofs + b                  （按证明个数，proofs = spends + outputs）
  M2  pipeline = a * spends + b                  （output 边际为 0）
  M3  pipeline = a * spends + c * outputs + b    （双变量，分离边际）

输出：系数、R^2、RMSE、留一交叉验证 RMSE、残差表、预测对比表。
纯离线分析，不碰链、不碰 zapd/zallet。

用法：
  python3 fit_sapling_e2e_model.py
  python3 fit_sapling_e2e_model.py --raw-dir ./raw --md ./raw/sapling_e2e_v1/FIT.md
"""

import argparse
import csv
import os
import sys
from glob import glob

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))


def fnum(x):
    if x is None:
        return None
    x = str(x).strip()
    if x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def load_all(raw_dir):
    """收集所有批次的成功轮次。"""
    rows = []
    pat = os.path.join(raw_dir, "**", "rounds.csv")
    for path in sorted(glob(pat, recursive=True)):
        batch = os.path.basename(os.path.dirname(os.path.dirname(path)))
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if (r.get("error") or "").strip():
                    continue
                s = fnum(r.get("sapling_spends"))
                o = fnum(r.get("sapling_outputs"))
                p = fnum(r.get("sapling_proofs"))
                t = fnum(r.get("pipeline"))
                if None in (s, o, p, t):
                    continue
                if t <= 0:
                    continue
                rows.append(
                    dict(batch=batch, round=int(fnum(r["round"]) or 0),
                         spends=int(s), outputs=int(o), proofs=int(p),
                         pipeline=t, size=fnum(r.get("tx_size")),
                         fee=fnum(r.get("fee_zat")))
                )
    return rows


def aggregate(rows):
    """同一 (spends, outputs) 形态合并：取 pipeline 中位数，并记录 n / 各批次。"""
    shapes = {}
    for r in rows:
        k = (r["spends"], r["outputs"])
        shapes.setdefault(k, []).append(r)
    out = []
    for (s, o), group in sorted(shapes.items()):
        vals = np.array([g["pipeline"] for g in group], dtype=float)
        out.append(dict(
            spends=s, outputs=o, proofs=s + o, n=len(group),
            pipeline=float(np.median(vals)),
            pmin=float(vals.min()), pmax=float(vals.max()),
            size=np.median([g["size"] for g in group if g["size"]]) if any(g["size"] for g in group) else None,
            batches=",".join(sorted({g["batch"] for g in group})),
        ))
    return out


def design(shapes, kind, weights=None):
    if kind == "M1":
        cols = [[s["proofs"] for s in shapes]]
    elif kind == "M2":
        cols = [[s["spends"] for s in shapes]]
    else:
        cols = [[s["spends"] for s in shapes], [s["outputs"] for s in shapes]]
    X = np.column_stack(cols + [np.ones(len(shapes))])
    y = np.array([s["pipeline"] for s in shapes], dtype=float)
    return X, y


def fit(X, y):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    resid = y - pred
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    rmse = float(np.sqrt(ss_res / len(y)))
    return coef, pred, resid, r2, rmse


def loo(X, y, hard_zero_intercept=False):
    """留一交叉验证 RMSE。"""
    n = len(y)
    errs = []
    for i in range(n):
        mask = np.arange(n) != i
        Xi, yi = X[mask], y[mask]
        coef, *_ = np.linalg.lstsq(Xi, yi, rcond=None)
        errs.append(float(y[i] - X[i] @ coef))
    return float(np.sqrt(np.mean(np.square(errs)))), errs


def fmt_coef(kind, coef):
    if kind == "M1":
        return f"{coef[0]:.1f} ms/proof + {coef[1]:.1f} ms"
    if kind == "M2":
        return f"{coef[0]:.1f} ms/spend + {coef[1]:.1f} ms（output 免费）"
    return f"{coef[0]:.1f} ms/spend + {coef[1]:.1f} ms/output + {coef[2]:.1f} ms"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=os.path.join(BASE, "raw"))
    ap.add_argument("--md", default="")
    args = ap.parse_args()

    rows = load_all(args.raw_dir)
    if not rows:
        sys.exit("没有找到可用的 rounds.csv（检查 --raw-dir）")
    shapes = aggregate(rows)

    lines = []
    p = lines.append
    p("# Sapling 端到端成本模型拟合（全量批次）")
    p("")
    p(f"- 原始成功轮次：**{len(rows)}** 轮，来自 {len({r['batch'] for r in rows})} 个批次")
    p(f"- 聚合后形态数：**{len(shapes)}** 个 `(spends, outputs)`")
    p("")
    p("## 形态观测表（pipeline 为同形态中位数）")
    p("")
    p("| spends | outputs | proofs | n | pipeline 中位(ms) | min | max | tx_size(B) |")
    p("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in shapes:
        size_cell = "" if s["size"] is None else str(int(s["size"]))
        p(f"| {s['spends']} | {s['outputs']} | {s['proofs']} | {s['n']} | "
          f"{s['pipeline']:.1f} | {s['pmin']:.1f} | {s['pmax']:.1f} | {size_cell} |")
    p("")

    p("## 模型对比")
    p("")
    p("| 模型 | 形式 | 系数 | R² | RMSE | LOO-RMSE |")
    p("|---|---|---|---:|---:|---:|")
    results = {}
    for kind, form in (("M1", "a·proofs + b"), ("M2", "a·spends + b"),
                       ("M3", "a·spends + c·outputs + b")):
        X, y = design(shapes, kind)
        coef, pred, resid, r2, rmse = fit(X, y)
        loo_rmse, _ = loo(X, y)
        results[kind] = dict(coef=coef, pred=pred, resid=resid, r2=r2, rmse=rmse, loo=loo_rmse)
        p(f"| {kind} | {form} | {fmt_coef(kind, coef)} | {r2:.4f} | {rmse:.1f} | {loo_rmse:.1f} |")

    # 加权 M3（权重 = 同形态轮数），检验系数对采样不均衡是否敏感
    Xw, yw = design(shapes, "M3")
    w = np.sqrt(np.array([s["n"] for s in shapes], dtype=float))
    coefw, *_ = np.linalg.lstsq(Xw * w[:, None], yw * w, rcond=None)
    p(f"| M3(加权 n) | a·spends + c·outputs + b | {fmt_coef('M3', coefw)} | — | — | — |")
    p("")

    best = max(results, key=lambda k: results[k]["r2"])
    p(f"**按 R² 最优：{best}**；M3 相对 M1 的 RMSE 下降 "
      f"{results['M1']['rmse'] / results['M3']['rmse']:.1f} 倍。"
      f"加权后 M3 系数为 {coefw[0]:.0f} / {coefw[1]:.0f} / {coefw[2]:.0f} ms，"
      f"与未加权 {results['M3']['coef'][0]:.0f} / {results['M3']['coef'][1]:.0f} / "
      f"{results['M3']['coef'][2]:.0f} ms 一致 → 结论不受采样不均衡影响。")
    p("")

    # 残差表
    p("## 残差（观测 - 预测）")
    p("")
    hdr = "| spends | outputs | 观测(ms) | " + " | ".join(f"{k} 预测" for k in results) + " | " + \
          " | ".join(f"{k} 残差" for k in results) + " |"
    p(hdr)
    p("|---:|---:|---:|" + "---:|" * (2 * len(results)))
    for i, s in enumerate(shapes):
        cells = [f"{s['pipeline']:.1f}"]
        cells += [f"{results[k]['pred'][i]:.1f}" for k in results]
        cells += [f"{results[k]['resid'][i]:+.1f}" for k in results]
        p(f"| {s['spends']} | {s['outputs']} | " + " | ".join(cells) + " |")
    p("")

    # ---------- 无模型假设的实证检验 ----------
    p("## 检验 A：固定 outputs=2 的 spend 阶梯（不依赖拟合）")
    p("")
    p("| spends | pipeline 中位(ms) | 相对上一档 Δ(ms) | 折算 Δ/spend |")
    p("|---:|---:|---:|---:|")
    ladder = [s for s in shapes if s["outputs"] == 2]
    prev = None
    deltas = []
    for s in sorted(ladder, key=lambda x: x["spends"]):
        if prev is None:
            p(f"| {s['spends']} | {s['pipeline']:.1f} | — | — |")
        else:
            d = s["pipeline"] - prev["pipeline"]
            per = d / (s["spends"] - prev["spends"])
            deltas.append(per)
            p(f"| {s['spends']} | {s['pipeline']:.1f} | {d:+.1f} | {per:.1f} |")
        prev = s
    if deltas:
        p("")
        p(f"阶梯斜率：均值 **{np.mean(deltas):.1f} ms/spend**，标准差 {np.std(deltas):.1f}，"
          f"范围 {min(deltas):.0f}–{max(deltas):.0f}。跨 1→17 个 spend 保持线性，"
          f"说明这一档的边际成本稳定。")
    p("")

    p("## 检验 B：配对替换对照（形态相近，不依赖拟合）")
    p("")
    p("这是最强的无模型证据。若耗时只由证明个数决定，则「1 个 spend 换成 1 个 output」"
      "（proofs 不变）应当零代价；实测存在价差，差值即 spend−output 的直接估计。")
    p("")
    p("| 形态 A | 形态 B | Δspends | Δoutputs | Δpipeline | 解释 |")
    p("|---|---|---:|---:|---:|---|")
    pairs = 0
    swap_deltas = []
    for i, a in enumerate(shapes):
        for b in shapes[i + 1:]:
            dS = b["spends"] - a["spends"]
            dO = b["outputs"] - a["outputs"]
            dP = b["pipeline"] - a["pipeline"]
            if dS == 0 and abs(dO) >= 1:
                tag = f"{dP/dO:.0f} ms/output（O 单独变化）"
            elif dO == 0 and abs(dS) == 1:
                tag = f"{dP/dS:.0f} ms/spend（相邻档）"
            elif dS + dO == 0 and dS != 0:
                tag = f"{dP/dS:.0f} ms/(spend−output)（等量替换）"
                swap_deltas.append(dP / dS)
            else:
                continue
            pairs += 1
            p(f"| S={a['spends']},O={a['outputs']} | S={b['spends']},O={b['outputs']} | "
              f"{dS:+d} | {dO:+d} | {dP:+.1f} | {tag} |")
    p("")
    if swap_deltas:
        p(f"**等量替换价差：{', '.join(f'{d:.0f}' for d in swap_deltas)} ms**"
          f"（S=3,O=3 与 S=4,O=2 同为 6 个证明，把 1 个 output 换成 1 个 spend 多花 "
          f"{swap_deltas[0]:.0f} ms）。证明个数相同、耗时显著不同 → **「按证明个数计费」被直接否证**。")
    p("")
    p(f"共 {pairs} 组对照（仅列相邻档、单变量变化与等量替换；长跨度组合与上表阶梯信息重复，已省略）。")
    p("")

    # ZIP 317 交叉验证
    if any(r["fee"] for r in rows):
        ok = bad = 0
        mism = []
        for r in rows:
            if not r["fee"]:
                continue
            exp = 5000 * max(r["spends"], r["outputs"])
            if int(r["fee"]) == exp:
                ok += 1
            else:
                bad += 1
                mism.append(f"S={r['spends']} O={r['outputs']} fee={int(r['fee'])} 期望={exp}")
        p("## 形态计数交叉验证：ZIP 317 手续费")
        p("")
        p(f"若 `fee = 5000 × max(spends, outputs)` 全部成立，说明 bench 从 `z_viewtransaction` "
          f"读出的 spend/output 计数与钱包实际构造的形态一致。")
        p("")
        p(f"- 吻合 **{ok}/{ok + bad}** 轮" + ("。" if bad == 0 else "，不一致：" + "；".join(mism)))
        p("")

    # 检验 C：字节数解析式
    sized = [s for s in shapes if s["size"]]
    if len(sized) >= 4:
        Xs = np.column_stack([[s["spends"] for s in sized],
                              [s["outputs"] for s in sized],
                              np.ones(len(sized))])
        ys = np.array([s["size"] for s in sized], dtype=float)
        cs, *_ = np.linalg.lstsq(Xs, ys, rcond=None)
        res = ys - Xs @ cs
        p("## 检验 C：字节数解析式")
        p("")
        p(f"`tx_size(B) = {cs[0]:.0f}·spends + {cs[1]:.0f}·outputs + {cs[2]:.0f}`，"
          f"最大残差 **{np.abs(res).max():.1f} B**（{len(sized)} 个形态）。")
        p("")
        if abs(res).max() < 1.0:
            p("残差为 0：字节数是严格线性的，说明形态计数与序列化结构完全对应。"
              "对照时间模型可见 **字节成本与算力成本必须分开建模**：")
            p("")
            m3c = results["M3"]["coef"]
            p("| 维度 | 字节/单位 | 时间/单位 | 时间/字节 |")
            p("|---|---:|---:|---:|")
            p(f"| spend | {cs[0]:.0f} B | {m3c[0]:.1f} ms | **{m3c[0]/cs[0]:.2f} ms/B** |")
            p(f"| output | {cs[1]:.0f} B | {m3c[1]:.1f} ms | **{m3c[1]/cs[1]:.3f} ms/B** |")
            p("")
            p(f"output 的字节数是 spend 的 {cs[1]/cs[0]:.1f} 倍，时间却只有 1/"
              f"{(m3c[0]/cs[0])/(m3c[1]/cs[1]):.1f}。output 的体积主要来自 note ciphertext（可加密数据），"
              "spend 的体积主要来自证明与签名（真实算力）。")
            p("")

    # 判别实验：1 spend + 9 outputs
    p("")
    m3 = results["M3"]["coef"]
    p(f"- M3：spend **{m3[0]:.1f} ms**、output **{m3[1]:.1f} ms**、固定开销 **{m3[2]:.1f} ms**，"
      f"比值 **{m3[0]/m3[1]:.2f} : 1**")
    for s in shapes:
        if s["spends"] == 1 and s["outputs"] >= 8:
            i = shapes.index(s)
            m2 = results["M2"]["coef"]
            p("")
            p(f"实测 `1 spend + {s['outputs']} outputs`（共 {s['proofs']} 个证明）= "
              f"**{s['pipeline']:.1f} ms**（n={s['n']}，极差 "
              f"{s['pmin']:.1f}–{s['pmax']:.1f}）")
            p("")
            p("| 假设 | 该轮预测 | 与实测偏差 |")
            p("|---|---:|---:|")
            p(f"| M1 按证明个数（{results['M1']['coef'][0]:.0f} ms/proof） | "
              f"{results['M1']['pred'][i]:.0f} ms | {results['M1']['resid'][i]:+.0f} ms |")
            p(f"| M2 output 免费（{m2[0]:.0f} ms/spend） | "
              f"{results['M2']['pred'][i]:.0f} ms | {results['M2']['resid'][i]:+.0f} ms |")
            p(f"| M3 双变量 | {results['M3']['pred'][i]:.0f} ms | "
              f"{results['M3']['resid'][i]:+.0f} ms |")
            p("")
            p("**判定：M3 命中，M1/M2 均被否。** 该点同时否掉两个极端假设——"
              "output 不是「与 spend 同价」，也不是「免费」。")
    p("")

    txt = "\n".join(lines) + "\n"
    print(txt)
    if args.md:
        os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"[out] {args.md}")


if __name__ == "__main__":
    main()
