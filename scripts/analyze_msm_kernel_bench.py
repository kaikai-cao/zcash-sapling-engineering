#!/usr/bin/env python3
"""Analyze the MSM kernel benchmark (Phase C: A/A calibration + blst control).

The frozen thresholds and design live in
experiments/metadata/sapling_msm_kernel_stagec_preregistration_20261023.md.
This script only applies them; it does not define new gates after seeing data.

Inputs (raw, append-only):
  experiments/raw/csv/{tag}_8t.csv, {tag}_1t.csv   columns: load,curve,n,arm,block,run,phase,elapsed_ms,checksum
  experiments/raw/csv/{tag}_correctness.csv        columns: load,curve,n,check,ok

Outputs (derived):
  results/tables/{tag}_summary.csv
  results/tables/{tag}_aa.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
from collections import defaultdict
from pathlib import Path

TAG_DEFAULT = "msm_kernel_bench_20261023"

# Frozen in the pre-registration (section 4).
M_GATE_HALF_WIDTH_PCT = 1.5          # M1/M2: A/A paired-difference 95% CI half width
P1_GO = 1.15                          # P1: bellman_1t / blst_1t on H-query G1
P1_MARGINAL = 1.08
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261023

# Arms recorded per condition file.
AA_PAIRS = {
    "8t": ("bellman_8t_A", "bellman_8t_B"),
    "1t": ("bellman_1t_A", "bellman_1t_B"),
}


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def median(values):
    return statistics.median(values) if values else float("nan")


def bootstrap_ci(values, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED, alpha=0.05):
    """Paired bootstrap CI for the median of `values`."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    medians = []
    for _ in range(resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        medians.append(statistics.median(sample))
    medians.sort()
    lo = medians[int((alpha / 2) * resamples)]
    hi = medians[min(resamples - 1, int((1 - alpha / 2) * resamples))]
    return (lo, hi)


def block_medians(rows):
    """(load, arm) -> {block: median of measured runs}."""
    grouped = defaultdict(list)
    for row in rows:
        if row["phase"] != "measured":
            continue
        grouped[(row["load"], row["curve"], row["arm"])].append(
            (int(row["block"]), float(row["elapsed_ms"]))
        )
    out = {}
    for key, samples in grouped.items():
        by_block = defaultdict(list)
        for block, elapsed in samples:
            by_block[block].append(elapsed)
        out[key] = {block: median(vals) for block, vals in sorted(by_block.items())}
    return out


def paired_stats(blocks_a, blocks_b):
    """Paired per-block differences a - b over the common blocks."""
    common = sorted(set(blocks_a) & set(blocks_b))
    diffs = [blocks_a[b] - blocks_b[b] for b in common]
    if not diffs:
        return None
    center = median(diffs)
    scale = median(abs(d) for d in diffs) or float("nan")
    lo, hi = bootstrap_ci(diffs)
    return {
        "blocks": len(common),
        "median_diff": center,
        "iqr_like": scale,
        "ci_lo": lo,
        "ci_hi": hi,
        "half_width_ms": max(abs(lo - center), abs(hi - center)),
    }


def ratio_stats(blocks_a, blocks_b):
    """Per-block ratios a / b over common blocks (a = baseline arm)."""
    common = sorted(set(blocks_a) & set(blocks_b))
    ratios = [blocks_a[b] / blocks_b[b] for b in common if blocks_b[b] > 0]
    if not ratios:
        return None
    center = median(ratios)
    lo, hi = bootstrap_ci(ratios)
    return {
        "blocks": len(common),
        "median_ratio": center,
        "ci_lo": lo,
        "ci_hi": hi,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--tag", default=TAG_DEFAULT)
    parser.add_argument("--raw-dir", default=None)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    raw_dir = Path(args.raw_dir) if args.raw_dir else repo / "experiments" / "raw" / "csv"
    tag = args.tag

    conditions = {}
    for suffix in ("8t", "1t"):
        path = raw_dir / f"{tag}_{suffix}.csv"
        if not path.is_file():
            raise SystemExit(f"raw csv missing: {path}")
        conditions[suffix] = read_csv(path)

    correctness_path = raw_dir / f"{tag}_correctness.csv"
    correctness = read_csv(correctness_path) if correctness_path.is_file() else []
    failed = [r for r in correctness if r["ok"] not in ("1", "true", "True", "ok")]
    if not correctness:
        print("correctness=NO_DATA")
    elif failed:
        print(f"correctness=FAIL ({len(failed)} of {len(correctness)} checks failed)")
        for row in failed[:20]:
            print(f"  failed: {row}")
    else:
        print(f"correctness=PASS ({len(correctness)} checks)")

    medians = {}
    for suffix, rows in conditions.items():
        medians[suffix] = block_medians(rows)

    # --- M gates: A/A paired differences -----------------------------------
    print()
    print("=== M gates: A/A paired differences (same implementation, two labels) ===")
    print("(the ic load is a reference load of section 2.1: its absolute cost is ~1 ms,")
    print(" so its relative CI is timer-noise dominated and it does not gate)")
    aa_rows = []
    m_gate_pass = True
    for suffix, (arm_a, arm_b) in AA_PAIRS.items():
        loads = sorted({key[0] for key in medians[suffix]})
        for load in loads:
            key_a = (load, "G1" if load != "g2_aux" else "G2", arm_a)
            key_b = (load, "G1" if load != "g2_aux" else "G2", arm_b)
            if key_a not in medians[suffix] or key_b not in medians[suffix]:
                continue
            stats = paired_stats(medians[suffix][key_a], medians[suffix][key_b])
            if stats is None:
                continue
            scale = median(medians[suffix][key_a].values())
            half_pct = 100.0 * stats["half_width_ms"] / scale if scale else float("nan")
            gates = load != "ic"
            ok = (not gates) or (half_pct <= M_GATE_HALF_WIDTH_PCT)
            m_gate_pass = m_gate_pass and ok
            print(
                f"{suffix} load={load} blocks={stats['blocks']} "
                f"median_diff_ms={stats['median_diff']:.4f} "
                f"ci95=[{stats['ci_lo']:.4f},{stats['ci_hi']:.4f}] "
                f"half_width_pct={half_pct:.3f} gate={'PASS' if ok else 'FAIL'}"
                f"{'' if gates else ' (reference load, not gating)'} (<= {M_GATE_HALF_WIDTH_PCT}%)"
            )
            aa_rows.append(
                {
                    "condition": suffix,
                    "load": load,
                    "blocks": stats["blocks"],
                    "median_diff_ms": f"{stats['median_diff']:.6f}",
                    "ci95_lo_ms": f"{stats['ci_lo']:.6f}",
                    "ci95_hi_ms": f"{stats['ci_hi']:.6f}",
                    "half_width_pct": f"{half_pct:.4f}",
                    "gate": "PASS" if ok else "FAIL",
                }
            )

    # --- P1 gate: bellman_1t vs blst_1t on H-query G1 ----------------------
    print()
    print("=== P1 gate: bellman_1t / blst_1t (same thread count) ===")
    p1 = None
    hq = medians["1t"]
    key_b = ("h_query", "G1", "bellman_1t_A")
    key_l = ("h_query", "G1", "blst_1t")
    if key_b in hq and key_l in hq:
        p1 = ratio_stats(hq[key_b], hq[key_l])
    if p1 is None:
        print("P1=NO_DATA (h_query bellman_1t_A or blst_1t missing)")
        p1_gate = "NO_GO"
    else:
        verdict = "GO" if p1["median_ratio"] >= P1_GO else ("MARGINAL" if p1["median_ratio"] >= P1_MARGINAL else "NO_GO")
        p1_gate = verdict
        print(
            f"load=h_query curve=G1 blocks={p1['blocks']} "
            f"R={p1['median_ratio']:.4f} ci95=[{p1['ci_lo']:.4f},{p1['ci_hi']:.4f}] "
            f"gate={verdict} (GO>={P1_GO}, MARGINAL>={P1_MARGINAL})"
        )

    # --- Per-load summary table --------------------------------------------
    print()
    print("=== Per-load block medians (ms) ===")
    summary_rows = []
    for suffix in ("8t", "1t"):
        for (load, curve, arm), blocks in sorted(medians[suffix].items()):
            vals = list(blocks.values())
            summary_rows.append(
                {
                    "condition": suffix,
                    "load": load,
                    "curve": curve,
                    "arm": arm,
                    "blocks": len(vals),
                    "median_ms": f"{median(vals):.4f}",
                    "min_ms": f"{min(vals):.4f}",
                    "max_ms": f"{max(vals):.4f}",
                }
            )
            print(
                f"{suffix} load={load} curve={curve} arm={arm} blocks={len(vals)} "
                f"median_ms={median(vals):.3f} min={min(vals):.3f} max={max(vals):.3f}"
            )

    # --- Write derived tables (append-only new files) ----------------------
    out_dir = repo / "results" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / f"{tag}_summary.csv"
    aa_path = out_dir / f"{tag}_aa.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()) if summary_rows else ["condition"])
        writer.writeheader()
        writer.writerows(summary_rows)
    with aa_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["condition", "load", "blocks", "median_diff_ms", "ci95_lo_ms", "ci95_hi_ms", "half_width_pct", "gate"],
        )
        writer.writeheader()
        writer.writerows(aa_rows)
    print()
    print(f"wrote {summary_path}")
    print(f"wrote {aa_path}")

    # --- Overall verdict ----------------------------------------------------
    print()
    print(f"VERDICT: M_gates={'PASS' if m_gate_pass else 'FAIL'} P1={p1_gate}")
    if not m_gate_pass:
        print("M gates failed: improve measurement design before any performance conclusion.")
    elif p1_gate == "GO":
        print("GO: a distinguishable implementation-level gap exists; write the Phase D candidate pre-registration.")
    elif p1_gate == "MARGINAL":
        print("MARGINAL: record attribution (section 4.4) before deciding; do not treat signal as approval.")
    else:
        print("NO_GO: close the kernel-candidate route; archive to INDEX.md and pick the next research question.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
