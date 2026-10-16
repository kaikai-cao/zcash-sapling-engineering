#!/usr/bin/env python3
"""Parse BELLMAN_MSM_BRANCH_PROFILE lines from a provenance report's stderr log."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
FIELD_NAMES = [
    "density_true_slot_visits",
    "density_false_slot_visits",
    "zero_exponent_slot_visits",
    "one_exponent_slot_visits",
    "chunked_exponent_slot_visits",
    "zero_window_digit_visits",
    "nonzero_window_digit_visits",
    "bucket_base_add_calls",
    "direct_one_add_calls",
    "base_skip_calls",
    "base_skip_elements",
]
QUERY_NAMES = [
    "H_query_G1", "L_query_G1", "A_input_G1", "A_aux_G1",
    "B_G1_input", "B_G1_aux", "B_G2_input", "B_G2_aux",
]

PATTERN = re.compile(
    r"BELLMAN_MSM_BRANCH_PROFILE "
    r"call_id=(\d+) "
    + " ".join(re.escape(name) + r"=(\d+)" for name in FIELD_NAMES)
)


def read_report_log(batch_id: str) -> Path:
    report = ROOT / "experiments" / "metadata" / f"sapling_spend_combined_profile_{batch_id}.md"
    if not report.exists():
        raise FileNotFoundError(f"Batch metadata report not found: {report}")
    text = report.read_text(encoding="utf-8-sig")
    m = re.search(
        r"- Prover stderr / source instrumentation records: experiments/raw/logs/([^\r\n]+)",
        text,
    )
    if not m:
        raise ValueError("Could not resolve stderr filename from batch metadata report")
    path = ROOT / "experiments" / "raw" / "logs" / m.group(1).strip()
    if not path.exists():
        raise FileNotFoundError(f"stderr log referenced by metadata is missing: {path}")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-id", required=True)
    args = ap.parse_args()
    batch_id = args.batch_id

    stderr_path = read_report_log(batch_id)
    stderr = stderr_path.read_text(encoding="utf-8-sig", errors="replace")
    matches = list(PATTERN.finditer(stderr))
    if len(matches) != 40:
        raise ValueError(
            f"Expected 40 BELLMAN_MSM_BRANCH_PROFILE rows, found {len(matches)}. "
            "Do not treat a partial capture as a complete batch."
        )

    detail = []
    seen = set()
    for m in matches:
        call_id = int(m.group(1))
        if call_id < 1 or call_id > 40 or call_id in seen:
            raise ValueError(f"Invalid or duplicate call_id: {call_id}")
        seen.add(call_id)
        run = (call_id - 1) // 8 + 1
        query = QUERY_NAMES[(call_id - 1) % 8]
        row = {
            "batch_id": batch_id,
            "run": run,
            "call_id": call_id,
            "query": query,
        }
        for name, value in zip(FIELD_NAMES, m.groups()[1:]):
            row[name] = int(value)
        row["active_slot_partition_check"] = (
            row["density_true_slot_visits"]
            == row["zero_exponent_slot_visits"]
            + row["one_exponent_slot_visits"]
            + row["chunked_exponent_slot_visits"]
        )
        row["chunked_digit_partition_check"] = (
            row["chunked_exponent_slot_visits"]
            == row["zero_window_digit_visits"]
            + row["nonzero_window_digit_visits"]
        )
        row["base_source_operation_check"] = (
            row["base_skip_calls"] == row["base_skip_elements"]
        )
        if not all(row[k] for k in (
            "active_slot_partition_check",
            "chunked_digit_partition_check",
            "base_source_operation_check",
        )):
            raise ValueError(f"Counter partition invariant failed for call_id={call_id}: {row}")
        detail.append(row)

    detail.sort(key=lambda r: r["call_id"])
    if seen != set(range(1, 41)):
        raise ValueError("MSM call IDs are incomplete")

    csv_dir = ROOT / "experiments" / "raw" / "csv"
    metadata_dir = ROOT / "experiments" / "metadata"
    detail_path = csv_dir / f"sapling_spend_msm_branch_profile_{batch_id}.csv"
    summary_path = csv_dir / f"sapling_spend_msm_branch_summary_{batch_id}.csv"
    md_path = metadata_dir / f"sapling_spend_msm_branch_accounting_{batch_id}.md"
    for path in (detail_path, summary_path, md_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {path}")

    csv_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    detail_fields = list(detail[0].keys())
    with detail_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=detail_fields)
        writer.writeheader()
        writer.writerows(detail)

    summary = []
    for query in QUERY_NAMES:
        rows = [r for r in detail if r["query"] == query]
        if len(rows) != 5:
            raise ValueError(f"Expected 5 rows for {query}, got {len(rows)}")
        s = {"batch_id": batch_id, "query": query, "runs": len(rows)}
        for name in FIELD_NAMES:
            vals = [r[name] for r in rows]
            s[f"median_{name}"] = median(vals)
            s[f"sum_{name}_across_5_runs"] = sum(vals)
        summary.append(s)

    with summary_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    totals = {name: sum(r[name] for r in detail) for name in FIELD_NAMES}
    lines = [
        f"# Sapling Spend MSM Branch Counter Accounting — Batch {batch_id}",
        "",
        f"- Source stderr log: `{stderr_path.relative_to(ROOT).as_posix()}`",
        f"- Branch counter rows validated: {len(detail)} / 40",
        f"- Per-query summaries: {len(summary)} / 8",
        "- Each query has exactly five runs; call_id mapping follows the collector's established 8-call-per-run ordering.",
        "- Counters are collected locally per chunk and aggregated once after the timed fill loop. They still add instrumentation overhead.",
        "",
        "## Counters summed across the five-run diagnostic batch",
        "",
        "These totals aggregate five proofs, not one proof. For one-proof operation counts, inspect an individual row/run in the detail CSV.",
        "",
        "| Counter | Total across 5 proofs |",
        "|---|---:|",
    ]
    for name in FIELD_NAMES:
        lines.append(f"| `{name}` | {totals[name]:,} |")
    lines += [
        "",
        "## Interpretation rules",
        "",
        "- `density_true_slot_visits` + `density_false_slot_visits` equals total loop-slot visits across all chunks.",
        "- Active-density exponent visits partition into Zero, One and Chunks enum variants.",
        "- Chunked exponent visits partition into zero and nonzero window digits.",
        "- `bucket_base_add_calls` counts calls to `add_assign_from_source` for nonzero chunk digits; `direct_one_add_calls` counts the exponent-One direct accumulator path.",
        "- `base_skip_calls` / `base_skip_elements` count `skip(1)` calls/elements, not group additions.",
        "- These counters count source-level branches/calls, not machine instructions; the G1/G2 group-operation cost can differ.",
        "- They are diagnostic measurements with added instrumentation, not a new formal performance baseline.",
        "",
        "## Outputs",
        f"- Detail CSV: `{detail_path.relative_to(ROOT).as_posix()}`",
        f"- Per-query summary CSV: `{summary_path.relative_to(ROOT).as_posix()}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Validated {len(detail)} branch-counter rows and {len(summary)} per-query summaries.")
    print("Totals across five proofs (not one proof):")
    for name in FIELD_NAMES:
        print(f"  {name} = {totals[name]:,}")
    print(f"Detail CSV: {detail_path}")
    print(f"Summary CSV: {summary_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
