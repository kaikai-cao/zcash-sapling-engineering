#!/usr/bin/env python3
"""Analyze the FFT arithmetic scoping microbenchmark.

The frozen thresholds live in
experiments/metadata/sapling_fft_arith_scoping_preregistration_20261023.md.
This script only applies them; it does not define new gates after seeing data.
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import statistics
from collections import defaultdict
from pathlib import Path

TAG_DEFAULT = "sapling_fft_arith_scoping_20261023"

# Frozen in the pre-registration.
GO = {
    (1, 1 << 17): 1.30,
    (1, 1 << 14): 1.25,
    (8, 1 << 17): 1.25,
}
MARGINAL = {
    (1, 1 << 17): 1.15,
    (1, 1 << 14): 1.10,
    (8, 1 << 17): 1.10,
}
TABLE_LIMIT_1T = 2.5 * 1024 * 1024
TABLE_LIMIT_8T_PER_THREAD = 256 * 1024


def median(values):
    return statistics.median(values) if values else float("nan")


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def gate_status(speedup: float, key: tuple[int, int]) -> str:
    if speedup >= GO[key]:
        return "GO"
    if speedup >= MARGINAL[key]:
        return "MARGINAL"
    return "NO_GO"


def op_counts(n: int):
    log_n = n.bit_length() - 1
    baseline = n * log_n
    # data multiplications plus the per-stage table build; j=0 has no multiply
    candidate = (n // 2) * log_n + (n - 1 - log_n)
    return baseline, candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--tag", default=TAG_DEFAULT)
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    raw_dir = Path(args.raw_dir) if args.raw_dir else repo / "experiments" / "raw" / "csv"
    manifest = (
        Path(args.manifest)
        if args.manifest
        else repo / "experiments" / "metadata" / f"fft_arith_scoping_manifest_{args.tag}.csv"
    )
    out = (
        Path(args.out)
        if args.out
        else repo / "results" / "tables" / f"{args.tag}_summary.csv"
    )

    if not manifest.is_file():
        raise SystemExit(f"manifest missing: {manifest}")

    manifest_rows = read_csv(manifest)
    if not manifest_rows:
        raise SystemExit(f"manifest is empty: {manifest}")

    raw_paths = []
    for row in manifest_rows:
        path = repo / row["raw_csv"]
        if not path.is_file():
            raise SystemExit(f"raw file missing: {path}")
        raw_paths.append(path)

    correctness = []
    timed = defaultdict(list)           # (threads, n, impl) -> list[float]
    batch_medians = defaultdict(list)   # (threads, n, impl) -> list[float]
    per_file = defaultdict(lambda: defaultdict(list))
    checksums = defaultdict(set)

    for path in raw_paths:
        rows = read_csv(path)
        batch_values = defaultdict(list)
        for row in rows:
            threads = int(row["threads"])
            n = int(row["n"])
            impl = row["impl"]
            if row["kind"] == "correctness":
                correctness.append(row)
                checksums[(threads, n)].add(row["checksum"])
            elif row["kind"] == "time":
                if int(row["run"]) == 1:
                    continue
                try:
                    elapsed = float(row["elapsed_ms"])
                except ValueError:
                    continue
                if not math.isfinite(elapsed) or elapsed <= 0:
                    continue
                timed[(threads, n, impl)].append(elapsed)
                batch_values[(threads, n, impl)].append(elapsed)
        for key, values in batch_values.items():
            if values:
                batch_medians[key].append(statistics.median(values))

    def primary(threads: int, n: int, impl: str) -> float:
        return median(batch_medians.get((threads, n, impl), []))

    def pooled(threads: int, n: int, impl: str) -> float:
        return median(timed.get((threads, n, impl), []))

    def speedup(threads: int, n: int, impl: str) -> float:
        base = primary(threads, n, "baseline")
        cand = primary(threads, n, impl)
        return base / cand if cand > 0 else float("nan")

    # Correctness gate: every row must be exact and the checksum set per
    # (threads, n) must contain exactly one value.
    correctness_bad = [row for row in correctness if row.get("exact_match") != "1"]
    checksum_bad = [key for key, values in checksums.items() if len(values) != 1]

    # Harness control: mirrored baseline must be within 10% of production.
    control = []
    for threads, n in ((1, 1 << 14), (1, 1 << 17), (8, 1 << 17)):
        if (threads, n, "mirror_onfly") not in batch_medians:
            continue
        ratio = speedup(threads, n, "mirror_onfly")
        control.append((threads, n, ratio, abs(ratio - 1.0)))
    control_ok = all(diff <= 0.10 for _, _, _, diff in control)

    # Operation-count check for candidate A (1t path).
    #
    # The scoping binary does not carry a runtime multiplication counter: adding
    # one would change the timed binary and invalidate the speed comparison.
    # The counts below are derived from the exact butterfly/table loops, so the
    # frozen "candidate ratio <= 0.60" part is checkable; the "measured vs
    # theoretical within 10%" part is recorded as a methodology deviation in
    # the results document, not silently treated as measured.
    op_rows = []
    for n in (1 << 14, 1 << 17):
        baseline_ops, candidate_ops = op_counts(n)
        ratio = candidate_ops / baseline_ops
        ok = ratio <= 0.60
        op_rows.append((n, baseline_ops, candidate_ops, ratio, ok))
    op_ok = all(row[4] for row in op_rows)

    # Table memory.  The 8t path shares one 2^14 table; the 1t path uses the
    # largest per-stage table (2^17 / 2 scalars).
    table_1t = (1 << 17) // 2 * 32
    table_8t_shared = ((1 << 14) - 1) * 32
    table_ok = table_1t <= TABLE_LIMIT_1T and table_8t_shared <= TABLE_LIMIT_1T
    # Per-thread private storage is zero for the shared 8t table.
    table_8t_per_thread = 0

    s1 = speedup(1, 1 << 17, "cand_radix2_precomputed")
    s2 = speedup(1, 1 << 14, "cand_radix2_precomputed")
    s3 = speedup(8, 1 << 17, "cand_radix2_precomputed")
    has_radix4 = (8, 1 << 17, "cand_radix4_precomputed") in batch_medians
    s3_radix4 = speedup(8, 1 << 17, "cand_radix4_precomputed") if has_radix4 else float("nan")
    # Candidate B is conditional: only the better 8t candidate is compared to
    # the frozen S3 threshold.  Both values remain in the derived table.
    s3_effective = max(s3, s3_radix4) if has_radix4 else s3
    s1_status = gate_status(s1, (1, 1 << 17))
    s2_status = gate_status(s2, (1, 1 << 14))
    s3_status = gate_status(s3_effective, (8, 1 << 17))

    if correctness_bad or checksum_bad or not op_ok or not table_ok:
        overall = "NO_GO"
    elif not control_ok:
        overall = "HARNESS_INVALID"
    elif all(status == "GO" for status in (s1_status, s2_status, s3_status)):
        overall = "GO"
    elif any(status == "NO_GO" for status in (s1_status, s2_status, s3_status)):
        overall = "NO_GO"
    else:
        overall = "MARGINAL"

    out.parent.mkdir(parents=True, exist_ok=True)
    rows_out = []

    def add(metric, scope, n, value, threshold, status, note=""):
        rows_out.append(
            {
                "metric": metric,
                "scope": scope,
                "n": n,
                "value": value,
                "threshold": threshold,
                "status": status,
                "note": note,
            }
        )

    for threads, n, impl in sorted(timed):
        values = timed[(threads, n, impl)]
        add(
            "median_ms",
            f"{threads}t",
            n,
            round(primary(threads, n, impl), 6),
            "",
            "",
            f"impl={impl}; pooled={pooled(threads, n, impl):.6f}; "
            f"min={min(values):.6f}; max={max(values):.6f}; n={len(values)}",
        )

    add("control_ratio", "harness", "", "", "<=10% deviation", "PASS" if control_ok else "FAIL",
        "; ".join(f"{t}t/n={n}:{ratio:.4f}" for t, n, ratio, _ in control))
    add("correctness", "all", "", len(correctness_bad), "0 mismatches", "PASS" if not correctness_bad else "FAIL")
    add("checksum_consistency", "all", "", len(checksum_bad), "0 inconsistent groups", "PASS" if not checksum_bad else "FAIL")
    for n, base_ops, cand_ops, ratio, ok in op_rows:
        add("op_count_ratio", "1t", n, round(ratio, 6), "<=0.60 (static)", "PASS" if ok else "FAIL",
            f"baseline={base_ops}; candidate={cand_ops}; runtime counter not instrumented")
    add("table_bytes_1t", "1t", 1 << 17, table_1t, int(TABLE_LIMIT_1T), "PASS" if table_1t <= TABLE_LIMIT_1T else "FAIL",
        "largest per-stage table")
    add("table_bytes_8t_shared", "8t", 1 << 17, table_8t_shared, int(TABLE_LIMIT_1T), "PASS" if table_8t_shared <= TABLE_LIMIT_1T else "FAIL",
        f"shared 2^14 full table; private per thread={table_8t_per_thread}")
    add("S1_speedup", "1t", 1 << 17, round(s1, 6), GO[(1, 1 << 17)], s1_status, "baseline / candidate A")
    add("S2_speedup", "1t", 1 << 14, round(s2, 6), GO[(1, 1 << 14)], s2_status, "baseline / candidate A")
    add("S3_radix2_speedup", "8t", 1 << 17, round(s3, 6), GO[(8, 1 << 17)],
        gate_status(s3, (8, 1 << 17)), "baseline / candidate A; includes shuffle/copy")
    if has_radix4:
        add("S3_radix4_speedup", "8t", 1 << 17, round(s3_radix4, 6), GO[(8, 1 << 17)],
            gate_status(s3_radix4, (8, 1 << 17)), "baseline / conditional candidate B; includes shuffle/copy")
    add("S3_speedup", "8t", 1 << 17, round(s3_effective, 6), GO[(8, 1 << 17)], s3_status,
        "best of candidate A and conditional B")
    add("overall", "all", "", overall, "GO requires C0-C3 and S1-S3 GO", overall,
        "MARGINAL may test candidate B under the same frozen gates")

    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "scope", "n", "value", "threshold", "status", "note"])
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"manifest={manifest}")
    print(f"summary={out}")
    print(f"batches={len(manifest_rows)} raw_files={len(raw_paths)}")
    print(f"correctness_rows={len(correctness)} bad={len(correctness_bad)} checksum_bad={len(checksum_bad)}")
    print(f"control_ok={control_ok} op_ok={op_ok} table_ok={table_ok}")
    print(f"S1={s1:.4f} ({s1_status}) S2={s2:.4f} ({s2_status}) "
          f"S3_A={s3:.4f} S3_B={s3_radix4:.4f} S3_best={s3_effective:.4f} ({s3_status})")
    print(f"overall={overall}")
    for threads, n in ((1, 1 << 17), (1, 1 << 14), (8, 1 << 17)):
        if (threads, n, "baseline") not in batch_medians:
            continue
        base = primary(threads, n, "baseline")
        cand = primary(threads, n, "cand_radix2_precomputed")
        mirror = primary(threads, n, "mirror_onfly")
        line = (
            f"{threads}t n={n}: baseline={base:.4f} mirror={mirror:.4f} "
            f"candidate={cand:.4f} speedup={base/cand:.4f} control={base/mirror:.4f}"
        )
        if has_radix4 and (threads, n, "cand_radix4_precomputed") in batch_medians:
            cand4 = primary(threads, n, "cand_radix4_precomputed")
            line += f" radix4={cand4:.4f} speedup4={base/cand4:.4f}"
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
