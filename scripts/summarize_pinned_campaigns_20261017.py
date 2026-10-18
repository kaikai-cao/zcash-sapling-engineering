# -*- coding: utf-8 -*-
"""Summarise the 2026-10-17 affinity-pinned baseline and reference campaigns.

Reads the raw per-proof CSVs produced by
`scripts/run_pinned_prover_campaign.ps1` and reports, per (prover, label):

  * batch count / proof count
  * per-batch median prove_ms
  * pooled median over all proofs
  * "warm" median = median of runs 2..5 of every batch after the first
    (drops the cold page-cache first batch and the in-process run-1 warmup)
  * cold first-batch median, for documenting the warmup magnitude

Also writes a derived table to `results/tables/`.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "experiments" / "raw" / "csv"
TABLES = REPO / "results" / "tables"

CAMPAIGNS = [
    ("spend", "pinned_baseline_20261017"),
    ("output", "pinned_baseline_20261017"),
    ("spend", "thread_scaling_pinned_20261017"),
    ("spend", "affinity_ecore_1t_20261017"),
    ("spend", "unbound_1t_20261017"),
    ("output", "affinity_ecore_1t_20261017"),
    ("output", "unbound_1t_20261017"),
]


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def summarise(prover: str, label: str) -> dict:
    path = RAW / f"sapling_{prover}_prover_runs_{label}.csv"
    rows = read_rows(path)

    batches: dict[str, list[tuple[int, float]]] = {}
    for row in rows:
        batches.setdefault(row["batch_id"], []).append((int(row["run"]), float(row["prove_ms"])))

    batch_ids = sorted(batches)
    all_values = [value for values in batches.values() for _, value in values]
    batch_medians = {bid: statistics.median([v for _, v in batches[bid]]) for bid in batch_ids}

    warm_values = [
        value
        for bid in batch_ids[1:]
        for run, value in batches[bid]
        if run >= 2
    ]
    cold_values = [value for _, value in batches[batch_ids[0]]]

    return {
        "prover": prover,
        "label": label,
        "batches": len(batch_ids),
        "proofs": len(all_values),
        "threads": rows[0]["rayon_threads"],
        "pooled_median_ms": round(statistics.median(all_values), 3),
        "cold_batch_median_ms": round(statistics.median(cold_values), 3),
        "warm_median_ms": round(statistics.median(warm_values), 3) if warm_values else "",
        "warm_min_ms": round(min(warm_values), 3) if warm_values else "",
        "warm_max_ms": round(max(warm_values), 3) if warm_values else "",
        "warm_spread_pct": (
            round(100.0 * (max(warm_values) - min(warm_values)) / statistics.median(warm_values), 2)
            if warm_values
            else ""
        ),
        "batch_medians_ms": " ".join(f"{batch_medians[bid]:.1f}" for bid in batch_ids),
    }


def main() -> None:
    out = [summarise(prover, label) for prover, label in CAMPAIGNS]

    header = f"{'prover':<7}{'label':<32}{'t':<4}{'bat':<5}{'proofs':<8}{'pooled':<11}{'cold_b1':<11}{'warm':<11}{'warm_spread%':<14}batch_medians"
    print(header)
    for row in out:
        print(
            f"{row['prover']:<7}{row['label']:<32}{row['threads']:<4}{row['batches']:<5}"
            f"{row['proofs']:<8}{row['pooled_median_ms']:<11}{row['cold_batch_median_ms']:<11}"
            f"{row['warm_median_ms']:<11}{row['warm_spread_pct']:<14}{row['batch_medians_ms']}"
        )

    TABLES.mkdir(parents=True, exist_ok=True)
    target = TABLES / "sapling_pinned_campaigns_20261017.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0].keys()))
        writer.writeheader()
        writer.writerows(out)
    print()
    print(f"wrote {target.relative_to(REPO)}")


if __name__ == "__main__":
    main()
