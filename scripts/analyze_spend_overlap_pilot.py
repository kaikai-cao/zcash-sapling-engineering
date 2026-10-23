#!/usr/bin/env python3
"""Analyze the Stage 3 independent-Spend overlap pilot.

Frozen by
  experiments/metadata/sapling_spend_overlap_pilot_preregistration_20261023.md

The decision quantity is batch throughput:

    ms_per_proof = batch_wall_ms / measured_proofs
    R = median(S1 ms_per_proof) / median(S0 ms_per_proof)

This is not a single-proof latency analysis. The script reports per-proof
latencies only as descriptive context.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


EXPECTED_ARMS = ["S0", "S1", "S1", "S0", "S0", "S1", "S1", "S0"]
EXPECTED_PROOFS = 8
EXPECTED_BATCHES = 8
ARM_ENV = {"S0": "seq", "S1": "conc2"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: Any, default: float = float("nan")) -> float:
    try:
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = -1) -> int:
    try:
        text = str(value).strip()
        return int(text) if text else default
    except (TypeError, ValueError):
        return default


def median(values: list[float]) -> float:
    return statistics.median(values)


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"id": name, "pass": bool(ok), "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="Optional path for the per-batch contrast table.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete analysis as JSON instead of a text report.",
    )
    args = parser.parse_args()

    manifest = read_csv(args.manifest)
    raw = read_csv(args.raw)
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    # ---------------------------------------------------------------- A1
    batch_ids = [row.get("batch_id", "").strip() for row in manifest]
    exit_codes = [as_int(row.get("exit_code")) for row in manifest]
    add_check(
        checks,
        "A1",
        len(manifest) == EXPECTED_BATCHES
        and len(set(batch_ids)) == EXPECTED_BATCHES
        and all(batch_id for batch_id in batch_ids)
        and all(code == 0 for code in exit_codes),
        f"rows={len(manifest)} unique_ids={len(set(batch_ids))} exit_codes={exit_codes}",
    )

    # ---------------------------------------------------------------- A2
    rows_by_batch: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw:
        rows_by_batch[row.get("batch_id", "").strip()].append(row)
    a2_details: list[str] = []
    a2_ok = True
    for batch_id in batch_ids:
        rows = rows_by_batch.get(batch_id, [])
        indices = sorted(as_int(row.get("proof_index")) for row in rows)
        verified = all(row.get("verified", "").strip().lower() == "true" for row in rows)
        walls = {as_float(row.get("batch_wall_ms")) for row in rows}
        ok = (
            len(rows) == EXPECTED_PROOFS
            and indices == list(range(EXPECTED_PROOFS))
            and verified
            and len(walls) == 1
            and next(iter(walls), float("nan")) > 0
        )
        a2_ok = a2_ok and ok
        a2_details.append(
            f"{batch_id}:rows={len(rows)},indices={indices[0] if indices else '-'}..{indices[-1] if indices else '-'},verified={verified},walls={sorted(walls)}"
        )
    add_check(checks, "A2", a2_ok, "; ".join(a2_details) if a2_details else "no manifest batches")

    # ---------------------------------------------------------------- A3
    arms = [row.get("arm", "").strip() for row in manifest]
    threads = [as_int(row.get("threads")) for row in manifest]
    affinity = [row.get("affinity", "").strip() for row in manifest]
    heads = {row.get("head", "").strip() for row in manifest}
    prereg_shas = {row.get("prereg_sha", "").strip() for row in manifest}
    binary_shas = {row.get("binary_sha", "").strip() for row in manifest}
    params_shas = {row.get("params_sha", "").strip() for row in manifest}
    proofs = [as_int(row.get("proofs")) for row in manifest]
    warmups = [as_int(row.get("warmups")) for row in manifest]

    raw_threads = {row.get("rayon_threads", "").strip() for row in raw}
    raw_affinity = {row.get("affinity_mask", "").strip() for row in raw}
    raw_heads = {row.get("git_head", "").strip() for row in raw}
    raw_arms_by_batch: dict[str, set[str]] = defaultdict(set)
    for row in raw:
        raw_arms_by_batch[row.get("batch_id", "").strip()].add(row.get("arm", "").strip())

    a3_ok = (
        arms == EXPECTED_ARMS
        and all(value == 8 for value in threads)
        and all(value == "0x5555" for value in affinity)
        and len(heads) == 1
        and "" not in heads
        and len(prereg_shas) == 1
        and "" not in prereg_shas
        and len(binary_shas) == 1
        and "" not in binary_shas
        and len(params_shas) == 1
        and "" not in params_shas
        and all(value == EXPECTED_PROOFS for value in proofs)
        and all(value == 1 for value in warmups)
        and raw_threads == {"8"}
        and raw_affinity == {"0x5555"}
        and len(raw_heads) == 1
        and "" not in raw_heads
        and all(
            raw_arms_by_batch.get(batch_id, set()) == {ARM_ENV[arm]}
            for batch_id, arm in zip(batch_ids, arms)
        )
    )
    add_check(
        checks,
        "A3",
        a3_ok,
        "arms={} threads={} affinity={} heads={} prereg={} binary={} params={} proofs={} warmups={} raw_threads={} raw_affinity={} raw_heads={}".format(
            arms,
            threads,
            affinity,
            sorted(heads),
            sorted(prereg_shas),
            sorted(binary_shas),
            sorted(params_shas),
            proofs,
            warmups,
            sorted(raw_threads),
            sorted(raw_affinity),
            sorted(raw_heads),
        ),
    )

    # ---------------------------------------------------------------- A4
    raw_batch_ids = {row.get("batch_id", "").strip() for row in raw}
    missing_logs = [
        row.get("stdout_log", "")
        for row in manifest
        if row.get("stdout_log") and not (Path(".") / row["stdout_log"]).exists()
    ]
    add_check(
        checks,
        "A4",
        set(batch_ids) == raw_batch_ids and not missing_logs,
        f"manifest_ids={len(batch_ids)} raw_ids={len(raw_batch_ids)} missing_logs={missing_logs}",
    )

    # ---------------------------------------------------------------- A5
    expected_rows = EXPECTED_BATCHES * EXPECTED_PROOFS
    a5_ok = len(raw) == expected_rows and all(
        len(rows_by_batch.get(batch_id, [])) == EXPECTED_PROOFS for batch_id in batch_ids
    )
    add_check(
        checks,
        "A5",
        a5_ok,
        f"raw_rows={len(raw)} expected={expected_rows}; measured proofs only (warmups are not written)",
    )

    # ---------------------------------------------------------------- A6
    add_check(
        checks,
        "A6",
        True,
        "Manual code review: the library default, spend_prover_smoke and production runners are unchanged; only the experimental binary/runner/analyzer/prereg were added.",
    )

    # ---------------------------------------------------------------- metrics
    batch_metrics: list[dict[str, Any]] = []
    for row, batch_id in zip(manifest, batch_ids):
        proofs_count = as_int(row.get("proofs"), EXPECTED_PROOFS)
        wall_from_manifest = as_float(row.get("batch_wall_ms"))
        raw_rows = rows_by_batch.get(batch_id, [])
        wall_from_raw = as_float(raw_rows[0].get("batch_wall_ms")) if raw_rows else float("nan")
        wall = wall_from_manifest if wall_from_manifest == wall_from_manifest else wall_from_raw
        if wall != wall or proofs_count <= 0:
            errors.append(f"{batch_id}: invalid batch wall/proofs ({wall}, {proofs_count})")
            continue
        prove_values = [as_float(item.get("prove_ms")) for item in raw_rows]
        verify_values = [as_float(item.get("verify_ms")) for item in raw_rows]
        batch_metrics.append(
            {
                "order": as_int(row.get("order")),
                "arm": row.get("arm", "").strip(),
                "batch_id": batch_id,
                "proofs": proofs_count,
                "batch_wall_ms": wall,
                "ms_per_proof": wall / proofs_count,
                "median_prove_ms": median(prove_values),
                "median_verify_ms": median(verify_values),
                "start_utc": row.get("start_utc", ""),
                "end_utc": row.get("end_utc", ""),
                "label": row.get("label", ""),
            }
        )

    s0 = sorted(
        (item["ms_per_proof"] for item in batch_metrics if item["arm"] == "S0")
    )
    s1 = sorted(
        (item["ms_per_proof"] for item in batch_metrics if item["arm"] == "S1")
    )
    g1 = bool(s0 and s1 and median(s1) / median(s0) <= 0.95)
    g2 = bool(s0 and s1 and max(s1) < min(s0))
    m0 = median(s0) if s0 else float("nan")
    m1 = median(s1) if s1 else float("nan")
    ratio = m1 / m0 if m0 == m0 and m1 == m1 and m0 > 0 else float("nan")

    all_a = all(check["pass"] for check in checks)
    if not all_a or errors:
        classification = "INVALID"
    elif g1 and g2:
        classification = "GO"
    else:
        classification = "NO_GO"

    # Descriptive single-proof latency ratio. This is deliberately not a gate.
    per_arm_prove = {
        arm: [as_float(row.get("prove_ms")) for row in raw if row.get("arm") == ARM_ENV[arm]]
        for arm in ("S0", "S1")
    }
    prove_ratio = (
        median(per_arm_prove["S1"]) / median(per_arm_prove["S0"])
        if per_arm_prove["S0"] and per_arm_prove["S1"]
        else float("nan")
    )

    result = {
        "classification": classification,
        "checks": checks,
        "errors": errors,
        "arms": {"S0": s0, "S1": s1},
        "medians_ms_per_proof": {"S0": m0, "S1": m1},
        "ratio_R": ratio,
        "G1_R_le_0_95": g1,
        "G2_max_S1_lt_min_S0": g2,
        "descriptive_single_proof_median_ratio_S1_over_S0": prove_ratio,
        "batch_metrics": batch_metrics,
        "note": "Decision quantity is batch throughput, not single-proof latency; a GO only warrants a formal Stage 3, not a default switch.",
    }

    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "order",
            "arm",
            "batch_id",
            "label",
            "proofs",
            "batch_wall_ms",
            "ms_per_proof",
            "median_prove_ms",
            "median_verify_ms",
            "start_utc",
            "end_utc",
        ]
        with args.out_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for item in batch_metrics:
                writer.writerow({key: item[key] for key in fieldnames})

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("Stage 3 independent-Spend overlap pilot")
        print(f"manifest: {args.manifest}")
        print(f"raw:      {args.raw}")
        print()
        print("Checks")
        for check in checks:
            print(f"  {check['id']}: {'PASS' if check['pass'] else 'FAIL'}  {check['detail']}")
        if errors:
            print("  errors:", *errors, sep="\n    ")
        print()
        print("Per-batch throughput")
        print("  order arm batch_id            wall_ms  ms/proof  median_prove_ms  median_verify_ms")
        for item in batch_metrics:
            print(
                "  {order:>5} {arm:<3} {batch_id:<19} {wall:8.3f} {mpp:9.3f} {prove:16.3f} {verify:16.3f}".format(
                    order=item["order"],
                    arm=item["arm"],
                    batch_id=item["batch_id"],
                    wall=item["batch_wall_ms"],
                    mpp=item["ms_per_proof"],
                    prove=item["median_prove_ms"],
                    verify=item["median_verify_ms"],
                )
            )
        print()
        print(f"  S0 batch ms/proof: {', '.join(f'{value:.3f}' for value in s0)}")
        print(f"  S1 batch ms/proof: {', '.join(f'{value:.3f}' for value in s1)}")
        print(f"  median S0={m0:.3f} ms/proof")
        print(f"  median S1={m1:.3f} ms/proof")
        print(f"  R={ratio:.6f}  G1(R<=0.95)={g1}  G2(max S1 < min S0)={g2}")
        print(
            "  descriptive per-proof median ratio S1/S0="
            f"{prove_ratio:.6f} (expected >1; not a gate)"
        )
        print()
        print(f"CLASSIFICATION={classification}")
        if classification == "GO":
            print(
                "Next: formal Stage 3 only (more batches plus 1-spend/2-output transaction validation); "
                "do not change a default."
            )
        elif classification == "NO_GO":
            print("Next: close the independent-proof overlap line; do not rerun this pilot.")
        else:
            print("Next: preserve artifacts, write a separate repair round; do not change this prereg.")

    return 0 if classification != "INVALID" else 2


if __name__ == "__main__":
    sys.exit(main())
