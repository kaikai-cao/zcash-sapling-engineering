# -*- coding: utf-8 -*-
"""Stratify the historical formal 1-thread baseline by execution regime.

Motivation
----------
On the mixed P-core / E-core i7-14700, an *unbound* single-threaded prover run
is bimodal: the worker lands on a P-core (fast) or an E-core (slow). The formal
`*_prover_runs_release.csv` files were collected without processor affinity, so
their published medians are averages over two physically different execution
regimes.

This script does NOT modify any raw file. It re-reads the raw rows, classifies
each *batch* (one process invocation) into a regime, and writes new derived
tables under `results/tables/`.

Classification is not fitted to the release data. It uses the separately
measured, affinity-pinned reference points produced by
`scripts/run_pinned_prover_campaign.ps1` (label `pinned_baseline_20261017` for
the P-core regime, `affinity_ecore_1t_20261017` for the E-core regime). A batch
is assigned to whichever pinned reference its median is closer to in log space,
i.e. the split point is the geometric mean of the two references.
"""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "experiments" / "raw" / "csv"
TABLES = REPO / "results" / "tables"

# Affinity-pinned 1-thread reference medians (ms), measured 2026-10-17.
# fast = single P-core (mask 0x1); slow = E-core only (mask 0xFFF0000).
PINNED_REFERENCES = {
    "spend": {"fast": 3711.504, "slow": 7803.571},
    "output": {"fast": 558.727, "slow": 1206.423},
}

FORMAL_BASELINES = {
    "spend": RAW / "sapling_spend_prover_runs_release.csv",
    "output": RAW / "sapling_output_prover_runs_release.csv",
}

THREAD_SCALING_RAW = RAW / "sapling_spend_prover_runs_thread_scaling_pinned_20261017_summary.csv"


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def median(values: list[float]) -> float:
    return statistics.median(values)


def classify(value: float, references: dict) -> str:
    split = math.sqrt(references["fast"] * references["slow"])
    return "p_core_regime" if value < split else "e_core_regime"


def stratify(prover: str) -> tuple[list[dict], list[dict]]:
    rows = read_rows(FORMAL_BASELINES[prover])
    single_thread = [row for row in rows if row["rayon_threads"].strip() == "1"]

    batches: dict[str, list[float]] = {}
    for row in single_thread:
        batches.setdefault(row["batch_id"], []).append(float(row["prove_ms"]))

    references = PINNED_REFERENCES[prover]
    split = math.sqrt(references["fast"] * references["slow"])

    batch_rows: list[dict] = []
    for batch_id, values in batches.items():
        batch_median = median(values)
        batch_rows.append(
            {
                "prover": prover,
                "batch_id": batch_id,
                "rayon_threads": 1,
                "proofs": len(values),
                "batch_median_prove_ms": round(batch_median, 3),
                "batch_min_prove_ms": round(min(values), 3),
                "batch_max_prove_ms": round(max(values), 3),
                "regime": classify(batch_median, references),
            }
        )
    batch_rows.sort(key=lambda row: (row["prover"], row["batch_id"]))

    all_values = [value for values in batches.values() for value in values]
    summary_rows: list[dict] = []
    for regime in ("p_core_regime", "e_core_regime"):
        values = [
            value
            for batch_id, vals in batches.items()
            if classify(median(vals), references) == regime
            for value in vals
        ]
        summary_rows.append(
            {
                "prover": prover,
                "regime": regime,
                "batches": sum(
                    1
                    for batch_id, vals in batches.items()
                    if classify(median(vals), references) == regime
                ),
                "proofs": len(values),
                "median_prove_ms": round(median(values), 3) if values else "",
                "min_prove_ms": round(min(values), 3) if values else "",
                "max_prove_ms": round(max(values), 3) if values else "",
                "share_of_proofs_pct": round(100.0 * len(values) / len(all_values), 2) if all_values else "",
            }
        )

    summary_rows.append(
        {
            "prover": prover,
            "regime": "pooled_undivided",
            "batches": len(batches),
            "proofs": len(all_values),
            "median_prove_ms": round(median(all_values), 3),
            "min_prove_ms": round(min(all_values), 3),
            "max_prove_ms": round(max(all_values), 3),
            "share_of_proofs_pct": 100.0,
        }
    )

    # Proof-level clustering. Batch-level classification above answers "was this
    # process invocation contaminated"; a few batches contain a mix of fast and
    # slow proofs, i.e. the worker migrated mid-batch. Labelling individual
    # proofs shows the two cluster centres directly.
    for regime, label in ((lambda v: v < split, "p_core_cluster_proof"), (lambda v: v >= split, "e_core_cluster_proof")):
        values = [value for value in all_values if regime(value)]
        touched = sum(
            1 for vals in batches.values() if any(regime(value) for value in vals)
        )
        summary_rows.append(
            {
                "prover": prover,
                "regime": label,
                "batches": touched,
                "proofs": len(values),
                "median_prove_ms": round(median(values), 3) if values else "",
                "min_prove_ms": round(min(values), 3) if values else "",
                "max_prove_ms": round(max(values), 3) if values else "",
                "share_of_proofs_pct": round(100.0 * len(values) / len(all_values), 2) if all_values else "",
            }
        )

    print(f"[{prover}] 1-thread release: {len(batches)} batches, {len(all_values)} proofs")
    print(f"[{prover}] regime split point (geometric mean) = {split:.3f} ms")
    for row in summary_rows:
        print(
            "  {regime:<18} batches={batches:<3} proofs={proofs:<4} "
            "median={median_prove_ms:<10} min={min_prove_ms:<10} max={max_prove_ms:<10} "
            "share={share_of_proofs_pct}%".format(**row)
        )
    return batch_rows, summary_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise SystemExit(f"no rows to write for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(REPO)} ({len(rows)} rows)")


def thread_scaling_table() -> None:
    rows = read_rows(THREAD_SCALING_RAW)
    base = None
    for row in rows:
        if int(row["rayon_threads"]) == 1:
            base = float(row["median_prove_ms"])
    out = []
    for row in rows:
        med = float(row["median_prove_ms"])
        out.append(
            {
                "prover": row["prover"],
                "label": row["label"],
                "affinity_mask": row["affinity_mask"],
                "rayon_threads": int(row["rayon_threads"]),
                "proofs": int(row["proofs"]),
                "median_prove_ms": round(med, 3),
                "min_prove_ms": float(row["min_prove_ms"]),
                "max_prove_ms": float(row["max_prove_ms"]),
                "spread_pct": float(row["spread_pct"]),
                "speedup_vs_1t": round(base / med, 3) if base else "",
                "parallel_efficiency_pct_of_threads": (
                    round(100.0 * base / med / int(row["rayon_threads"]), 2) if base else ""
                ),
                "exe_sha256": row["exe_sha256"],
                "params_sha256": row["params_sha256"],
                "git_head": row["git_head"],
            }
        )
    write_csv(TABLES / "sapling_spend_thread_scaling_pinned_20261017.csv", out)
    print()
    print("Pinned P-core thread scaling (mask 0xFFFF):")
    for row in out:
        print(
            "  threads={rayon_threads:<3} median={median_prove_ms:<9} "
            "speedup={speedup_vs_1t:<7} efficiency={parallel_efficiency_pct_of_threads}%".format(**row)
        )


def main() -> None:
    batch_rows: list[dict] = []
    summary_rows: list[dict] = []
    for prover in ("spend", "output"):
        batches, summary = stratify(prover)
        batch_rows.extend(batches)
        summary_rows.extend(summary)
        print()

    write_csv(TABLES / "sapling_baseline_core_regime_batches_20261017.csv", batch_rows)
    write_csv(TABLES / "sapling_baseline_core_regime_summary_20261017.csv", summary_rows)
    thread_scaling_table()


if __name__ == "__main__":
    main()
