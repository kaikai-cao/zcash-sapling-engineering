#!/usr/bin/env python3
"""Analyze a Sapling Spend MSM inner-stage profile batch.

This script does not run cryptographic workloads and does not modify raw data.
It derives source-level loop / group-operation counts from the committed profile
records and the current Bellman MSM implementation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiments" / "raw" / "csv"
TABLES = ROOT / "results" / "tables"
METADATA = ROOT / "experiments" / "metadata"
SOURCE = ROOT / "vendor" / "bellman" / "src" / "multiexp.rs"
SCALAR_NUM_BITS = 255
MIB = 1024 * 1024
QUERY_ORDER = [
    "H_query_G1",
    "L_query_G1",
    "A_input_G1",
    "A_aux_G1",
    "B_G1_input",
    "B_G1_aux",
    "B_G2_input",
    "B_G2_aux",
]
TIMING_FIELDS = [
    "exponent_chunk_prep_ms",
    "chunk_parallel_wall_ms",
    "bucket_init_sum_ms",
    "bucket_init_max_ms",
    "bucket_fill_sum_ms",
    "bucket_fill_max_ms",
    "bucket_reduce_sum_ms",
    "bucket_reduce_max_ms",
    "result_merge_ms",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required input is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def integer(row: dict[str, str], field: str) -> int:
    try:
        return int(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer field {field!r}: {row!r}") from exc


def number(row: dict[str, str], field: str) -> float:
    try:
        return float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric field {field!r}: {row!r}") from exc


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-id",
        default="1792134295649",
        help="Profile batch ID (default: 1792134295649)",
    )
    args = parser.parse_args()
    batch = args.batch_id

    detail_path = RAW / f"sapling_spend_msm_inner_stage_profile_{batch}.csv"
    summary_path = RAW / f"sapling_spend_msm_inner_stage_summary_{batch}.csv"
    out_csv = TABLES / f"sapling_spend_msm_operation_counts_{batch}.csv"
    out_md = METADATA / f"sapling_spend_msm_operation_accounting_{batch}.md"

    detail = read_csv(detail_path)
    summary = read_csv(summary_path)
    if len(detail) != 40:
        raise ValueError(f"Expected 40 detail rows, found {len(detail)}")
    if len(summary) != 8:
        raise ValueError(f"Expected 8 summary rows, found {len(summary)}")

    detail_by_query: dict[str, list[dict[str, str]]] = {}
    for row in detail:
        if row.get("batch_id") != batch:
            raise ValueError(f"Unexpected batch_id in detail CSV: {row.get('batch_id')}")
        detail_by_query.setdefault(row["query"], []).append(row)

    summary_by_query = {row["query"]: row for row in summary}
    if set(detail_by_query) != set(QUERY_ORDER):
        raise ValueError(f"Unexpected query names: {sorted(detail_by_query)}")
    if set(summary_by_query) != set(QUERY_ORDER):
        raise ValueError(f"Unexpected summary query names: {sorted(summary_by_query)}")

    output_rows: list[dict[str, Any]] = []
    for query in QUERY_ORDER:
        rows = detail_by_query[query]
        if len(rows) != 5:
            raise ValueError(f"{query}: expected 5 runs, found {len(rows)}")
        rows.sort(key=lambda r: integer(r, "run"))
        if [integer(r, "run") for r in rows] != [1, 2, 3, 4, 5]:
            raise ValueError(f"{query}: run IDs are not exactly 1..5")

        first = rows[0]
        group = first["group"]
        n = integer(first, "exponent_count")
        c = integer(first, "window")
        b = integer(first, "bucket_count")
        k = integer(first, "chunk_count")
        element_size = integer(first, "bucket_element_size_bytes")
        threads = integer(first, "threads") if "threads" in first else ""

        expected_b = (1 << c) - 1
        expected_k = math.ceil(SCALAR_NUM_BITS / c)
        if b != expected_b:
            raise ValueError(f"{query}: bucket_count={b}, expected 2^{c}-1={expected_b}")
        if k != expected_k:
            raise ValueError(f"{query}: chunk_count={k}, expected ceil(255/{c})={expected_k}")
        if group not in ("G1", "G2"):
            raise ValueError(f"{query}: unknown group {group!r}")
        expected_size = 144 if group == "G1" else 288
        if element_size != expected_size:
            raise ValueError(f"{query}: bucket element size {element_size}, expected {expected_size}")

        for row in rows:
            invariant_fields = ["group", "exponent_count", "window", "bucket_count", "chunk_count", "bucket_element_size_bytes"]
            for field in invariant_fields:
                if row[field] != first[field]:
                    raise ValueError(f"{query}: {field} changes between runs")

            active = integer(row, "max_concurrent_chunk_regions")
            recorded_payload = integer(row, "bucket_payload_at_max_concurrency_estimate_bytes")
            computed_payload = active * b * element_size
            if recorded_payload != computed_payload:
                raise ValueError(
                    f"{query} run {row['run']}: bucket payload estimate mismatch: "
                    f"recorded {recorded_payload}, computed {computed_payload}"
                )

        fill_slots = n * k
        bucket_elements_per_chunk = b
        bucket_elements_init_total = b * k
        bucket_reduce_iterations = b * k
        # In multiexp_inner's bucket reduction loop, each item invokes:
        # running_sum.add_assign(&exp) and acc.add_assign(&running_sum).
        reduce_group_add_calls = 2 * b * k
        # Each result part does c doubles then adds the chunk result.
        merge_double_calls = c * k
        merge_add_calls = k
        per_chunk_payload = b * element_size

        out: dict[str, Any] = {
            "batch_id": batch,
            "query": query,
            "group": group,
            "exponent_count": n,
            "window": c,
            "bucket_count_per_chunk": b,
            "chunk_count": k,
            "bucket_element_type": "G1Projective" if group == "G1" else "G2Projective",
            "bucket_element_size_bytes": element_size,
            "fill_loop_slot_visits_per_call_exact": fill_slots,
            "bucket_elements_initialized_per_call_exact": bucket_elements_init_total,
            "bucket_reduce_iterations_per_call_exact": bucket_reduce_iterations,
            "reduce_group_add_assign_calls_per_call_exact": reduce_group_add_calls,
            "result_merge_double_calls_per_call_exact": merge_double_calls,
            "result_merge_chunk_add_calls_per_call_exact": merge_add_calls,
            "bucket_payload_bytes_per_chunk": per_chunk_payload,
            "median_exponent_chunk_prep_ms": round(statistics.median(number(r, "exponent_chunk_prep_ms") for r in rows), 3),
            "median_chunk_parallel_wall_ms": round(statistics.median(number(r, "chunk_parallel_wall_ms") for r in rows), 3),
            "median_bucket_init_sum_ms": round(statistics.median(number(r, "bucket_init_sum_ms") for r in rows), 3),
            "median_bucket_fill_sum_ms": round(statistics.median(number(r, "bucket_fill_sum_ms") for r in rows), 3),
            "median_bucket_reduce_sum_ms": round(statistics.median(number(r, "bucket_reduce_sum_ms") for r in rows), 3),
            "median_result_merge_ms": round(statistics.median(number(r, "result_merge_ms") for r in rows), 3),
            "fill_sum_to_parallel_wall_ratio": round(
                statistics.median(number(r, "bucket_fill_sum_ms") / number(r, "chunk_parallel_wall_ms") for r in rows), 3
            ),
            "aggregate_fill_ms_per_loop_slot_us": round(
                statistics.median(number(r, "bucket_fill_sum_ms") for r in rows) * 1000 / fill_slots, 6
            ),
            "median_max_concurrent_chunk_regions": round(statistics.median(integer(r, "max_concurrent_chunk_regions") for r in rows), 1),
            "max_concurrent_chunk_regions_observed": max(integer(r, "max_concurrent_chunk_regions") for r in rows),
            "max_observed_bucket_payload_estimate_bytes": max(integer(r, "bucket_payload_at_max_concurrency_estimate_bytes") for r in rows),
            "status": "source-derived counts; dynamic bucket digit/add counts not instrumented",
        }
        if threads != "":
            out["threads"] = threads
        output_rows.append(out)

    totals = {
        field: sum(int(row[field]) for row in output_rows)
        for field in [
            "fill_loop_slot_visits_per_call_exact",
            "bucket_elements_initialized_per_call_exact",
            "bucket_reduce_iterations_per_call_exact",
            "reduce_group_add_assign_calls_per_call_exact",
            "result_merge_double_calls_per_call_exact",
            "result_merge_chunk_add_calls_per_call_exact",
        ]
    }

    write_csv(out_csv, output_rows)

    source_hash = sha256(SOURCE) if SOURCE.is_file() else "unavailable"
    lines = [
        f"# Sapling Spend MSM source-level operation accounting — batch {batch}",
        "",
        "## Scope and provenance",
        "",
        f"- Detail input: `{detail_path.relative_to(ROOT).as_posix()}` ({len(detail)} rows).",
        f"- Summary input: `{summary_path.relative_to(ROOT).as_posix()}` ({len(summary)} rows).",
        f"- Instrumented source: `vendor/bellman/src/multiexp.rs`.",
        f"- Source SHA-256 at analysis time: `{source_hash}`.",
        "- This script does not rerun the prover and does not change raw measurement files.",
        "",
        "## Code-level interpretation",
        "",
        "| Measured field | Source region / exact interpretation |",
        "|---|---|",
        "| `exponent_chunk_prep_ms` | `exponents.iter().map(|exp| exp.chunks(c)).collect()`; transforms each exponent into `Zero`, `One`, or a vector of window chunks. The exact count of allocated inner `Vec<u64>` values is not currently recorded. |",
        "| `bucket_init_sum_ms` | All per-chunk `vec![G::identity(); bucket_count]` initialization intervals added together. |",
        "| `bucket_fill_sum_ms` | All per-chunk passes over `exponents.iter().zip(density_map.iter())`, including density checks, enum branches, base-source `skip`/`next` access, and point additions for selected digits. It is not only group-add time. |",
        "| `bucket_reduce_sum_ms` | All per-chunk reverse bucket loops. Every bucket iteration executes two source-level group accumulation calls: `running_sum.add_assign(&exp)` and `acc.add_assign(&running_sum)`. |",
        "| `chunk_parallel_wall_ms` | Wall-clock time around the parallel chunk iterator through collection; includes scheduling and overlapping work, but excludes exponent chunk preparation and the later merge. |",
        "| `result_merge_ms` | Folding chunk results in reverse order; each part performs `window` doublings followed by one chunk-result addition. |",
        "",
        "## Exact source-derived counts per MSM call",
        "",
        "The following are source-level iteration/API-call counts derived from `exponent_count`, `window`, and `chunk_count`, not hardware instruction counts.",
        "",
        "| Query | Exponent count | Window | Chunks | Fill-loop slots | Bucket elements initialized | Reduction iterations | Reduction add-assign calls | Merge doubles | Merge adds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in output_rows:
        lines.append(
            f"| {row['query']} | {row['exponent_count']:,} | {row['window']} | {row['chunk_count']} "
            f"| {row['fill_loop_slot_visits_per_call_exact']:,} "
            f"| {row['bucket_elements_initialized_per_call_exact']:,} "
            f"| {row['bucket_reduce_iterations_per_call_exact']:,} "
            f"| {row['reduce_group_add_assign_calls_per_call_exact']:,} "
            f"| {row['result_merge_double_calls_per_call_exact']:,} "
            f"| {row['result_merge_chunk_add_calls_per_call_exact']:,} |"
        )

    lines.extend([
        "",
        "### Total across the eight MSM calls in one proof",
        "",
        f"- Exponent/density loop-slot visits: **{totals['fill_loop_slot_visits_per_call_exact']:,}**.",
        f"- Bucket elements initialized across all chunks: **{totals['bucket_elements_initialized_per_call_exact']:,}**.",
        f"- Bucket-reduction iterations: **{totals['bucket_reduce_iterations_per_call_exact']:,}**.",
        f"- Source-level group `add_assign` calls in bucket reduction: **{totals['reduce_group_add_assign_calls_per_call_exact']:,}**.",
        f"- Source-level group doubling calls during merge: **{totals['result_merge_double_calls_per_call_exact']:,}**.",
        f"- Source-level chunk-result additions during merge: **{totals['result_merge_chunk_add_calls_per_call_exact']:,}**.",
        "",
        "Across five successful proof runs, multiply these per-proof counts by five. This does not imply five runs executed at exactly the same hardware instruction count if the code path or input-dependent branches differ; the counted loop slots and reduction loop sizes are fixed by these dimensions.",
        "",
        "## Timing findings and caveats",
        "",
        "- `bucket_fill_sum_ms` accumulates per-chunk intervals; it can exceed `chunk_parallel_wall_ms` because the chunks overlap in time.",
        "- `aggregate_fill_ms_per_loop_slot_us` is a normalized aggregate timer divided by the loop-slot count. Because it uses summed per-chunk time, it is not a single-thread latency per exponent and includes branch/source-access/group-add work as applicable.",
        "- The H-query fill region is much longer than L-query despite a smaller exponent-count ratio. A plausible reason is different input-dependent `Zero`/`One`/`Chunks` and digit distributions, but those branch/add counts are **not captured by the current data**. Do not state that explanation as proven until branch counters or an independent count-only diagnostic is added.",
        "- `bucket_payload_bytes_per_chunk × max_concurrent_chunk_regions` is a bucket payload estimate associated with overlapping instrumented regions. Since the region guard begins before bucket allocation and ends as the worker closure exits, it is not an exact allocator peak. It excludes other buffers, point vectors, allocator metadata, and the rest of the process.",
        "- The counts above are method/loop counts in Rust source, not exact low-level field multiplication counts or CPU instructions. Those require deeper type implementation analysis or hardware profiling.",
        "",
        "## Output",
        "",
        f"- Operation-count CSV: `{out_csv.relative_to(ROOT).as_posix()}`.",
        f"- Source-level accounting report: `{out_md.relative_to(ROOT).as_posix()}`.",
        "",
    ])
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"Validated {len(detail)} detail rows and {len(summary)} per-query summaries.")
    print("Source-derived operation totals across 8 MSM calls / one proof:")
    for field, value in totals.items():
        print(f"  {field} = {value:,}")
    print(f"\nCSV: {out_csv}")
    print(f"Markdown: {out_md}")


if __name__ == "__main__":
    main()
