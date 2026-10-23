#!/usr/bin/env python3
"""Frozen analyzer for the Stage 2 c=12 pilot (4 Spend batches, ABBA).

Input: experiments/metadata/msm_c12_pilot_manifest_20261023.csv
Outputs: results/tables/msm_c12_pilot_contrast_20261023.csv
         results/tables/msm_c12_pilot_analysis_20261023.json

This is a pilot/go-no-go analyzer, not the formal Stage 1b/2 analyzer. It
validates the preregistered A1-A5 checks, computes batch medians (run 1
discarded), and applies the frozen go/no-go rule.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

EXPECTED = [
    ("C0", "msm_c12_pilot_20261023_c0_b1"),
    ("C1", "msm_c12_pilot_20261023_c1_b2"),
    ("C1", "msm_c12_pilot_20261023_c1_b3"),
    ("C0", "msm_c12_pilot_20261023_c0_b4"),
]
EXPECTED_QUERIES = {
    "H_query_G1": 131071,
    "L_query_G1": 98638,
    "A_input_G1": 8,
    "A_aux_G1": 98638,
    "B_G1_input": 8,
    "B_G1_aux": 98638,
    "B_G2_input": 8,
    "B_G2_aux": 98638,
}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def best_signed_window(bits: int = 255, exponent_count: int = 0) -> int:
    best_c = 3
    best_ops = None
    for c in range(2, 21):
        windows = bits // c + 1
        ops = windows * (exponent_count + 2 * (1 << (c - 1)))
        if best_ops is None or ops < best_ops:
            best_ops = ops
            best_c = c
    return best_c


def resolve(path_text: str, root: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else root / path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="experiments/metadata/msm_c12_pilot_manifest_20261023.csv",
    )
    parser.add_argument(
        "--out-csv",
        default="results/tables/msm_c12_pilot_contrast_20261023.csv",
    )
    parser.add_argument(
        "--out-json",
        default="results/tables/msm_c12_pilot_analysis_20261023.json",
    )
    args = parser.parse_args()

    root = repo_root()
    manifest_path = resolve(args.manifest, root)
    if not manifest_path.exists():
        raise SystemExit(f"missing manifest: {manifest_path}")
    rows = read_csv(manifest_path)
    checks: list[dict[str, object]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"id": check_id, "passed": bool(passed), "detail": detail})

    check("A1_count", len(rows) == 4, f"manifest rows={len(rows)}")
    observed = [(r.get("arm", ""), r.get("label", "")) for r in rows]
    check("A1_plan", observed == EXPECTED, f"arm/label order={observed}")

    batch_ids = [r.get("batch_id", "") for r in rows]
    check(
        "A1_unique",
        len(batch_ids) == 4 and len(set(batch_ids)) == 4 and all(batch_ids),
        f"batch_ids={batch_ids}",
    )

    head_values = {r.get("head", "") for r in rows}
    prereg_values = {r.get("prereg_sha", "") for r in rows}
    binary_values = {r.get("binary_sha", "") for r in rows}
    check("A4_head", len(head_values) == 1 and "" not in head_values, f"heads={head_values}")
    check(
        "A4_prereg",
        len(prereg_values) == 1 and "" not in prereg_values,
        f"prereg_shas={prereg_values}",
    )
    check(
        "A4_binary",
        len(binary_values) == 1 and "" not in binary_values,
        f"binary_shas={binary_values}",
    )
    check(
        "A4_env",
        all(r.get("threads") == "8" and r.get("affinity") == "0x5555" for r in rows),
        "threads/affinity="
        + str([(r.get("threads"), r.get("affinity")) for r in rows]),
    )

    batch_records: list[dict[str, object]] = []
    for row in rows:
        arm = row["arm"]
        label = row["label"]
        batch_id = row["batch_id"]
        exit_code = row.get("exit_code", "")
        check(f"A1_exit_{label}", exit_code == "0", f"exit_code={exit_code}")

        raw_path = resolve(row.get("raw_csv", ""), root)
        stage_path = resolve(row.get("stage_csv", ""), root)
        msm_path = resolve(row.get("msm_csv", ""), root)
        check(f"A5_raw_exists_{label}", raw_path.is_file(), str(raw_path))
        check(f"A3_stage_exists_{label}", stage_path.is_file(), str(stage_path))
        check(f"A3_msm_exists_{label}", msm_path.is_file(), str(msm_path))

        raw_rows = [
            r
            for r in read_csv(raw_path)
            if r.get("batch_id") == batch_id
        ] if raw_path.is_file() else []
        raw_rows.sort(key=lambda r: int(r["run"]))
        check(f"A2_rows_{label}", len(raw_rows) == 5, f"rows={len(raw_rows)}")
        check(
            f"A2_verified_{label}",
            len(raw_rows) == 5
            and all(r.get("verified", "").lower() == "true" for r in raw_rows),
            f"verified={[r.get('verified') for r in raw_rows]}",
        )
        prove_values = [float(r["prove_ms"]) for r in raw_rows] if len(raw_rows) == 5 else []
        batch_median = median(prove_values[1:]) if len(prove_values) == 5 else None

        msm_rows = [
            r
            for r in read_csv(msm_path)
            if r.get("batch_id") == batch_id
        ] if msm_path.is_file() else []
        check(
            f"A3_msm_rows_{label}",
            len(msm_rows) == 40,
            f"msm rows={len(msm_rows)}",
        )
        window_ok = len(msm_rows) == 40
        window_detail: list[str] = []
        for msm in msm_rows:
            query = msm.get("query", "")
            count = int(msm.get("exponent_count", "0"))
            actual = int(msm.get("window", "0"))
            if query not in EXPECTED_QUERIES or count != EXPECTED_QUERIES[query]:
                window_ok = False
                window_detail.append(f"{query}: unexpected count={count}")
                continue
            expected = 12 if (arm == "C1" and count >= 16384) else best_signed_window(255, count)
            if actual != expected:
                window_ok = False
                window_detail.append(f"{query}: expected={expected} actual={actual}")
            if arm == "C0" and query == "H_query_G1" and actual != 13:
                window_ok = False
                window_detail.append(f"C0 H_query window={actual}, expected 13")
            if arm == "C1" and query == "H_query_G1" and actual != 12:
                window_ok = False
                window_detail.append(f"C1 H_query window={actual}, expected 12")
        check(
            f"A3_windows_{label}",
            window_ok,
            "all 40 rows match gate/default" if window_ok else "; ".join(window_detail),
        )

        h_rows = [r for r in msm_rows if r.get("query") == "H_query_G1"]
        h_median = median([float(r["elapsed_ms"]) for r in h_rows]) if h_rows else None
        batch_records.append(
            {
                "arm": arm,
                "label": label,
                "batch_id": batch_id,
                "batch_median_ms": batch_median,
                "prove_ms_runs": prove_values,
                "h_query_median_ms": h_median,
            }
        )

    c0 = [r for r in batch_records if r["arm"] == "C0"]
    c1 = [r for r in batch_records if r["arm"] == "C1"]
    valid_medians = (
        len(c0) == 2
        and len(c1) == 2
        and all(r["batch_median_ms"] is not None for r in batch_records)
    )
    if not valid_medians:
        check("A2_medians", False, "missing batch medians")
        m0 = m1 = ratio = None
        go = False
    else:
        m0 = median([float(r["batch_median_ms"]) for r in c0])
        m1 = median([float(r["batch_median_ms"]) for r in c1])
        ratio = m1 / m0
        no_reversal = max(float(r["batch_median_ms"]) for r in c1) < min(
            float(r["batch_median_ms"]) for r in c0
        )
        check("G1_ratio", ratio <= 0.97, f"R={ratio:.6f} (need <=0.97)")
        check(
            "G2_no_reversal",
            no_reversal,
            f"C1={[r['batch_median_ms'] for r in c1]}, C0={[r['batch_median_ms'] for r in c0]}",
        )
        go = ratio <= 0.97 and no_reversal

    validity_failures = [
        f"{c['id']}: {c['detail']}"
        for c in checks
        if not c["passed"] and str(c["id"]).startswith(("A1", "A2", "A3", "A4", "A5"))
    ]
    go_failures = [
        f"{c['id']}: {c['detail']}"
        for c in checks
        if not c["passed"] and str(c["id"]).startswith("G")
    ]
    status = "INVALID" if validity_failures else ("GO" if go else "NO_GO")
    result = {
        "status": status,
        "checks": checks,
        "validity_failures": validity_failures,
        "go_failures": go_failures,
        "batch_records": batch_records,
        "c0_median_ms": m0,
        "c1_median_ms": m1,
        "ratio_c1_over_c0": ratio,
        "go_rule": "R <= 0.97 and max(C1) < min(C0)",
        "go": bool(go and not validity_failures),
    }

    out_json = root / args.out_json
    out_csv = root / args.out_csv
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "arm",
                "label",
                "batch_id",
                "batch_median_ms",
                "h_query_median_ms",
                "prove_ms_runs",
            ]
        )
        for r in batch_records:
            writer.writerow(
                [
                    r["arm"],
                    r["label"],
                    r["batch_id"],
                    "" if r["batch_median_ms"] is None else f"{r['batch_median_ms']:.3f}",
                    "" if r["h_query_median_ms"] is None else f"{r['h_query_median_ms']:.3f}",
                    ";".join(f"{v:.3f}" for v in r["prove_ms_runs"]),
                ]
            )

    print(f"status={status}")
    for c in checks:
        print(f"{c['id']}: {'PASS' if c['passed'] else 'FAIL'} - {c['detail']}")
    if ratio is not None:
        print(f"C0 batch medians: {[round(float(r['batch_median_ms']), 3) for r in c0]}")
        print(f"C1 batch medians: {[round(float(r['batch_median_ms']), 3) for r in c1]}")
        print(f"m0={m0:.3f} ms m1={m1:.3f} ms R={ratio:.6f}")
    print(f"wrote {out_json}")
    print(f"wrote {out_csv}")
    return 0 if status != "INVALID" else 2


if __name__ == "__main__":
    sys.exit(main())
