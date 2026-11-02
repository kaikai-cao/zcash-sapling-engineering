#!/usr/bin/env python3
"""Analyse the Phase D XYZZ A/B micro-benchmark.

Input : experiments/raw/csv/msm_xyzz_h_query_20261102.csv
Design: paired blocks; per block the arm order is a frozen permutation, each
        arm gets 1 warm-up + `runs` measured iterations, and the block value is
        the median of those iterations.

Primary metric (pre-registration §5.1):

    S_MSM = median_block(T_jacobian) / median_block(T_xyzz)

Gates: >= 1.15 GO | [1.08, 1.15) MARGINAL | < 1.08 NO_GO.

The A/A pair (jac_A vs jac_B) is reported as measurement uncertainty; it is not
a gate, but a drift larger than the effect size invalidates the comparison.

Stdlib only, so the analysis runs in the CI environment unchanged.
"""
import argparse
import csv
import os
import random
import statistics
import sys

THRESH_GO = 1.15
THRESH_MARGINAL = 1.08
BOOTSTRAP_B = 4000
BOOTSTRAP_SEED = 20261102


def median(values):
    return statistics.median(values)


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "block": int(r["block"]),
                    "arm": r["arm"],
                    "run": int(r["run"]),
                    "ms": float(r["ms"]),
                }
            )
    if not rows:
        raise SystemExit("no rows in %s" % path)
    return rows


def per_block(rows, arm):
    out = {}
    for r in rows:
        if r["arm"] != arm:
            continue
        out.setdefault(r["block"], []).append(r["ms"])
    return {b: median(v) for b, v in out.items()}


def bootstrap_ci(values, b=BOOTSTRAP_B, seed=BOOTSTRAP_SEED, alpha=0.05):
    rng = random.Random(seed)
    n = len(values)
    stats = []
    for _ in range(b):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(median(sample))
    stats.sort()
    lo = stats[int(b * alpha / 2)]
    hi = stats[int(b * (1 - alpha / 2)) - 1]
    return lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--csv",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "experiments/raw/csv/msm_xyzz_h_query_20261102.csv",
        ),
    )
    ap.add_argument("--md", default=None, help="write a markdown fragment here")
    args = ap.parse_args()

    rows = load(args.csv)
    blocks = sorted({r["block"] for r in rows})
    arms = sorted({r["arm"] for r in rows})

    pb = {a: per_block(rows, a) for a in arms}
    missing = [a for a in ("jac_A", "jac_B", "xyzz") if a not in pb]
    if missing:
        raise SystemExit("missing arms: %s (found %s)" % (missing, arms))

    common = sorted(set(pb["jac_A"]) & set(pb["jac_B"]) & set(pb["xyzz"]))
    lines = []
    add = lines.append

    add("# Phase D XYZZ A/B — analysis\n")
    add("CSV: `%s`\n" % os.path.basename(args.csv))
    add("blocks: %d, arms: %s\n" % (len(common), ", ".join(arms)))

    jac = [pb["jac_A"][b] for b in common]
    jac_b = [pb["jac_B"][b] for b in common]
    xyzz = [pb["xyzz"][b] for b in common]

    add("\n## Per-block medians (ms)\n")
    add("| block | jac_A | jac_B | xyzz | jac_A/xyzz |")
    add("|---|---|---|---|---|")
    for i, b in enumerate(common):
        add(
            "| %d | %.3f | %.3f | %.3f | %.4f |"
            % (b, jac[i], jac_b[i], xyzz[i], jac[i] / xyzz[i])
        )

    s_msm = median(jac) / median(xyzz)
    aa_drift = (median(jac_b) - median(jac)) / median(jac)
    ratios = [j / x for j, x in zip(jac, xyzz)]
    lo, hi = bootstrap_ci(ratios)

    add("\n## Primary metric\n")
    add("median(jac_A) = %.3f ms" % median(jac))
    add("median(xyzz)  = %.3f ms" % median(xyzz))
    add("**S_MSM = %.4f**  (95%% bootstrap CI of the per-block ratio: [%.4f, %.4f])" % (s_msm, lo, hi))
    add("A/A drift (jac_B vs jac_A): %+.3f%%" % (aa_drift * 100))
    add(
        "per-block ratio: min %.4f, median %.4f, max %.4f"
        % (min(ratios), median(ratios), max(ratios))
    )

    if s_msm >= THRESH_GO:
        verdict = "GO"
    elif s_msm >= THRESH_MARGINAL:
        verdict = "MARGINAL"
    else:
        verdict = "NO_GO"
    add("\n## Verdict\n")
    add(
        "S_MSM = %.4f vs thresholds GO>=%.2f, MARGINAL>=%.2f -> **%s**"
        % (s_msm, THRESH_GO, THRESH_MARGINAL, verdict)
    )
    if abs(aa_drift) > abs(s_msm - 1.0):
        add(
            "\n> WARNING: the A/A drift (%+.3f%%) is larger than the measured effect "
            "(%+.3f%%); the comparison cannot resolve an effect of this size."
            % (aa_drift * 100, (s_msm - 1) * 100)
        )

    text = "\n".join(lines)
    print(text)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("\n[written] %s" % args.md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
