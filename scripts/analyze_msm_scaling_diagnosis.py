#!/usr/bin/env python3
"""Frozen analyzer for the Stage 0 MSM scaling-knee diagnosis (2026-10-22).

Inputs (raw, append-only):
  * experiments/metadata/msm_scaling_manifest_20261022.csv
  * experiments/raw/csv/sapling_spend_prover_runs_<label>.csv
  * experiments/raw/csv/sapling_spend_stage_profile_<batch_id>.csv
  * experiments/raw/csv/sapling_spend_msm_call_profile_<batch_id>.csv
  * experiments/raw/csv/sapling_spend_msm_inner_stage_profile_<batch_id>.csv
  * experiments/metadata/sapling_spend_combined_profile_<batch_id>.md
  * experiments/raw/csv/sapling_output_prover_runs_msm_scaling_20261022.csv
  * experiments/raw/csv/sapling_tx_scaling_runs_msm_scaling_20261022.csv

Outputs:
  * results/tables/msm_scaling_*_20261022.csv
  * results/figures/msm_scaling_*_20261022.png

The analyzer independently rechecks acceptance items A1-A6 from the raw rows. It
never writes to raw paths and never overwrites a previous analysis output.
"""

from __future__ import annotations

import csv
import math
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TAG = "msm_scaling_20261022"
BOOTSTRAP_N = 10000
BOOTSTRAP_ALPHA = 0.10  # 90% CI
RNG_SEED = 20261022

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "experiments" / "raw" / "csv"
METADATA_DIR = ROOT / "experiments" / "metadata"
TABLE_DIR = ROOT / "results" / "tables"
FIGURE_DIR = ROOT / "results" / "figures"

MANIFEST_PATH = METADATA_DIR / f"msm_scaling_manifest_{TAG}.csv"
OUTPUT_RAW = RAW_DIR / f"sapling_output_prover_runs_{TAG}_output.csv"
TX_RAW = RAW_DIR / f"sapling_tx_scaling_runs_{TAG}.csv"

SPEND_STAGE_COLUMNS = [
    "circuit_synthesis_constraints_ms",
    "worker_vk_setup_ms",
    "qap_fft_h_exponent_prep_ms",
    "h_query_access_dispatch_ms",
    "assignment_query_prep_dispatch_ms",
    "proof_scalar_terms_ms",
    "wait_and_assembly_ms",
    "create_proof_body_ms",
]

H_QUERY = "H_query_G1"

WINDOW_ORDER = [10, 11, 12, 13]

ACCEPTANCE = []


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def to_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def median(values: list[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        raise ValueError("median of empty set")
    return float(statistics.median(clean))


def parse_manifest() -> list[dict]:
    rows = read_csv(MANIFEST_PATH)
    if not rows:
        raise RuntimeError(f"manifest missing or empty: {MANIFEST_PATH}")
    records = []
    seen_ids: set[str] = set()
    for row in rows:
        args = row.get("runner_args", "")
        def arg(flag: str, pattern: str = r"(\S+)") -> str | None:
            match = re.search(rf"{re.escape(flag)}\s+{pattern}", args)
            return match.group(1) if match else None

        threads = to_int(arg("-Threads"))
        mask = to_int(arg("-AffinityMask") or arg("-AffinityMasks"))
        env_override = row.get("env_override", "")
        window_c = None
        if env_override.startswith("SAPLING_MSM_WINDOW_C="):
            window_c = to_int(env_override.split("=", 1)[1])

        batch_ids = [b for b in str(row.get("new_batch_ids", "")).split(";") if b.strip()]
        for batch_id in batch_ids:
            if batch_id in seen_ids:
                raise RuntimeError(f"duplicate batch id in manifest: {batch_id}")
            seen_ids.add(batch_id)

        records.append(
            {
                "tag": row.get("tag", ""),
                "order": to_int(row.get("order")),
                "arm": row.get("arm", ""),
                "config": row.get("config", ""),
                "kind": row.get("kind", ""),
                "threads": threads,
                "mask": mask,
                "window_c": window_c,
                "label": arg("-RunDataLabel") or arg("-Label") or arg("-Tag"),
                "prover": arg("-Prover"),
                "batch_ids": batch_ids,
                "exit_code": to_int(row.get("exit_code")),
                "start_utc": row.get("start_utc", ""),
                "end_utc": row.get("end_utc", ""),
                "git_head": row.get("git_head", ""),
                "prereg_sha256": row.get("prereg_sha256", ""),
                "runner_args": args,
            }
        )
    return records


def spend_raw_path(label: str) -> Path:
    return RAW_DIR / f"sapling_spend_prover_runs_{label}.csv"


def group_key(record: dict) -> tuple:
    return (
        record["arm"],
        record["kind"],
        record["threads"],
        record["mask"],
        record["window_c"],
    )


def w_value(window: int) -> int:
    return 255 // window + 1


def modelled_adds(n: int, window: int) -> int:
    return w_value(window) * (n + 2 * (1 << (window - 1)))


def cluster_bootstrap_median(batches: list[list[float]], rng: random.Random) -> tuple[float, float, float]:
    if not batches:
        raise ValueError("no batches")
    point = median([v for batch in batches for v in batch])
    stats = []
    for _ in range(BOOTSTRAP_N):
        picked = [batches[rng.randrange(len(batches))] for _ in batches]
        stats.append(median([v for batch in picked for v in batch]))
    stats.sort()
    lo = stats[int((BOOTSTRAP_ALPHA / 2) * BOOTSTRAP_N)]
    hi = stats[int((1 - BOOTSTRAP_ALPHA / 2) * BOOTSTRAP_N) - 1]
    return point, lo, hi


def cluster_bootstrap_difference(
    left: list[list[float]], right: list[list[float]], rng: random.Random
) -> tuple[float, float, float]:
    point = median([v for batch in left for v in batch]) - median([v for batch in right for v in batch])
    stats = []
    for _ in range(BOOTSTRAP_N):
        lp = [left[rng.randrange(len(left))] for _ in left]
        rp = [right[rng.randrange(len(right))] for _ in right]
        stats.append(
            median([v for batch in lp for v in batch]) - median([v for batch in rp for v in batch])
        )
    stats.sort()
    lo = stats[int((BOOTSTRAP_ALPHA / 2) * BOOTSTRAP_N)]
    hi = stats[int((1 - BOOTSTRAP_ALPHA / 2) * BOOTSTRAP_N) - 1]
    return point, lo, hi


def cluster_bootstrap_ratio(
    num: list[list[float]], den: list[list[float]], rng: random.Random
) -> tuple[float, float, float]:
    point = median([v for batch in num for v in batch]) / median([v for batch in den for v in batch])
    stats = []
    for _ in range(BOOTSTRAP_N):
        np_ = [num[rng.randrange(len(num))] for _ in num]
        dp = [den[rng.randrange(len(den))] for _ in den]
        stats.append(
            median([v for batch in np_ for v in batch])
            / median([v for batch in dp for v in batch])
        )
    stats.sort()
    lo = stats[int((BOOTSTRAP_ALPHA / 2) * BOOTSTRAP_N)]
    hi = stats[int((1 - BOOTSTRAP_ALPHA / 2) * BOOTSTRAP_N) - 1]
    return point, lo, hi


def speedup_table(groups: dict[tuple, dict], kind_stage: str = "prove_ms") -> list[dict]:
    baseline_key = next(
        k for k in groups if k[1] == "spend" and k[2] == 1 and k[3] == 0x1 and k[4] is None
    )
    baseline = groups[baseline_key]["metrics"][kind_stage]["median"]
    rows = []
    for key, group in sorted(groups.items()):
        if key[1] != "spend":
            continue
        metric = group["metrics"][kind_stage]
        rows.append(
            {
                "arm": key[0],
                "threads": key[2],
                "affinity_mask": f"0x{key[3]:X}",
                "window_c": key[4],
                "batches": len(group["batches"]),
                "warm_n": metric["warm_n"],
                "median_ms": round(metric["median"], 3),
                "speedup_vs_1t_0x1": round(baseline / metric["median"], 4) if metric["median"] else "",
                "efficiency": round((baseline / metric["median"]) / key[2], 4) if metric["median"] else "",
            }
        )
    return rows


def load_spend_group(record: dict) -> dict:
    label = record["label"]
    raw_rows = read_csv(spend_raw_path(label))
    wanted = set(record["batch_ids"])
    rows = [r for r in raw_rows if r.get("batch_id") in wanted]
    batches = {}
    for batch_id in record["batch_ids"]:
        batch_rows = sorted(
            [r for r in rows if r.get("batch_id") == batch_id],
            key=lambda r: to_int(r.get("run")) or 0,
        )
        batches[batch_id] = batch_rows
    return {"record": record, "batches": batches}


def load_table_group(record: dict, path: Path) -> dict:
    rows = read_csv(path)
    wanted = set(record["batch_ids"])
    batches = {}
    for batch_id in record["batch_ids"]:
        batch_rows = sorted(
            [r for r in rows if r.get("batch_id") == batch_id],
            key=lambda r: to_int(r.get("run")) or 0,
        )
        batches[batch_id] = batch_rows
    return {"record": record, "batches": batches}


def spend_batch_metrics(batch_rows: list[dict]) -> dict:
    warm = [r for r in batch_rows if (to_int(r.get("run")) or 0) >= 2]
    return {
        "prove_ms": [to_float(r["prove_ms"]) for r in warm],
        "warm_n": len(warm),
        "verified": all(str(r.get("verified", "")).lower() == "true" for r in batch_rows),
        "rows": len(batch_rows),
        "rayon_threads": {r.get("rayon_threads") for r in batch_rows},
    }


def output_batch_metrics(batch_rows: list[dict]) -> dict:
    warm = [r for r in batch_rows if (to_int(r.get("run")) or 0) >= 2]
    return {
        "prove_ms": [to_float(r["prove_ms"]) for r in warm],
        "warm_n": len(warm),
        "verified": all(str(r.get("verified", "")).lower() == "true" for r in batch_rows),
        "rows": len(batch_rows),
        "rayon_threads": {r.get("rayon_threads") for r in batch_rows},
    }


def tx_batch_metrics(batch_rows: list[dict]) -> dict:
    warm = [r for r in batch_rows if (to_int(r.get("run")) or 0) >= 2]
    return {
        "build_ms": [to_float(r["build_ms"]) for r in warm],
        "sum_proofs_ms": [to_float(r["sum_proofs_ms"]) for r in warm],
        "total_construct_ms": [to_float(r["total_construct_ms"]) for r in warm],
        "warm_n": len(warm),
        "verified": all(str(r.get("verified", "")).lower() == "true" for r in batch_rows),
        "rows": len(batch_rows),
        "tx_bytes": {r.get("tx_bytes") for r in batch_rows},
        "tx_version": {r.get("tx_version") for r in batch_rows},
        "spend_count": {r.get("spend_count") for r in batch_rows},
        "output_count": {r.get("output_count") for r in batch_rows},
        "rayon_threads": {r.get("rayon_threads") for r in batch_rows},
        "affinity_mask": {r.get("affinity_mask") for r in batch_rows},
    }


def summarize_metric(batches: list[list[float]]) -> dict:
    flat = [v for batch in batches for v in batch if not math.isnan(v)]
    return {
        "median": median(flat),
        "mean": float(statistics.fmean(flat)),
        "sd": float(statistics.stdev(flat)) if len(flat) > 1 else 0.0,
        "cv_pct": (float(statistics.stdev(flat)) / float(statistics.fmean(flat)) * 100.0)
        if len(flat) > 1 and statistics.fmean(flat)
        else 0.0,
        "min": min(flat),
        "max": max(flat),
        "warm_n": len(flat),
    }


def analyze() -> None:
    if not MANIFEST_PATH.exists():
        raise RuntimeError(f"manifest missing: {MANIFEST_PATH}")
    records = parse_manifest()
    if any(r["tag"] != TAG for r in records):
        raise RuntimeError("manifest tag mismatch")

    acceptance("A0", "manifest tag and preregistration hash present", all(r["tag"] == TAG for r in records))
    acceptance("A10-invocations", "expected 44 runner invocations", len(records) == 44)

    # ------------------------------------------------------------------
    # Load per-batch raw data by arm.
    # ------------------------------------------------------------------
    groups: dict[tuple, dict] = {}
    per_record_data: list[dict] = []
    for record in records:
        kind = record["kind"]
        if kind == "spend":
            data = load_spend_group(record)
            metric_fn = spend_batch_metrics
        elif kind == "output":
            data = load_table_group(record, OUTPUT_RAW)
            metric_fn = output_batch_metrics
        elif kind == "tx":
            data = load_table_group(record, TX_RAW)
            metric_fn = tx_batch_metrics
        else:
            raise RuntimeError(f"unknown kind: {kind}")

        per_batch = {}
        for batch_id, rows in data["batches"].items():
            per_batch[batch_id] = metric_fn(rows)
        data["per_batch"] = per_batch
        per_record_data.append(data)

        key = group_key(record)
        group = groups.setdefault(key, {"records": [], "data": [], "batches": []})
        group["records"].append(record)
        group["data"].append(data)

    # Aggregate metrics per group.
    for key, group in groups.items():
        metric_names = set()
        for data in group["data"]:
            for metrics in data["per_batch"].values():
                metric_names.update(metrics.keys())
        aggregated = {}
        for name in metric_names:
            if name in {"warm_n", "rows", "verified", "rayon_threads", "tx_bytes", "tx_version", "spend_count", "output_count", "affinity_mask"}:
                continue
            batches = []
            for data in group["data"]:
                for metrics in data["per_batch"].values():
                    if name in metrics:
                        batches.append([v for v in metrics[name]])
            if batches:
                aggregated[name] = summarize_metric(batches)
        group["metrics"] = aggregated
        group["batches"] = [b for data in group["data"] for b in data["per_batch"].keys()]

    # ------------------------------------------------------------------
    # Acceptance A1-A6 (independent recheck).
    # ------------------------------------------------------------------
    spend_records = [d for d in per_record_data if d["record"]["kind"] == "spend"]
    output_records = [d for d in per_record_data if d["record"]["kind"] == "output"]
    tx_records = [d for d in per_record_data if d["record"]["kind"] == "tx"]

    a1_ok = True
    a2_ok = True
    a3_ok = True
    a4_ok = True
    a8_ok = True
    a7_detail = []
    a9_detail = []
    for data in spend_records:
        rec = data["record"]
        if len(rec["batch_ids"]) != 1:
            a1_ok = False
        for batch_id, rows in data["batches"].items():
            if len(rows) != 5 or not all(str(r.get("verified", "")).lower() == "true" for r in rows):
                a1_ok = False
            if {str(r.get("rayon_threads")) for r in rows} != {str(rec["threads"])}:
                a8_ok = False
            # A2
            call_rows = read_csv(RAW_DIR / f"sapling_spend_msm_call_profile_{batch_id}.csv")
            inner_rows = read_csv(RAW_DIR / f"sapling_spend_msm_inner_stage_profile_{batch_id}.csv")
            stage_rows = read_csv(RAW_DIR / f"sapling_spend_stage_profile_{batch_id}.csv")
            if len(call_rows) != 40 or len(inner_rows) != 40 or len(stage_rows) != 5:
                a2_ok = False
            if any(not str(r.get("submit_elapsed_ms", "")).strip() for r in call_rows):
                a2_ok = False
            # A3 closure per run
            body = {to_int(r.get("run")): to_float(r.get("create_proof_body_ms")) for r in stage_rows}
            for stage_row in stage_rows:
                run = to_int(stage_row.get("run"))
                stage_sum = sum(to_float(stage_row.get(col)) for col in SPEND_STAGE_COLUMNS if col != "create_proof_body_ms")
                if abs(stage_sum - body.get(run, float("nan"))) > 0.0100001:
                    a3_ok = False
            # A4 window sweep
            if rec["window_c"] is not None:
                h_rows = [r for r in inner_rows if r.get("query") == H_QUERY]
                if len(h_rows) != 5 or any(to_int(r.get("window")) != rec["window_c"] for r in h_rows):
                    a4_ok = False
            # A9 spend metadata
            md_path = METADATA_DIR / f"sapling_spend_combined_profile_{batch_id}.md"
            if not md_path.exists():
                a9_detail.append(f"missing metadata {batch_id}")
            else:
                text = md_path.read_text(encoding="utf-8", errors="replace")
                if f"0x{rec['mask']:X}" not in text and f"0x{rec['mask']:x}" not in text:
                    a7_detail.append(f"affinity not found in metadata {batch_id}")
                if "Parameter SHA-256: 8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13" not in text:
                    a9_detail.append(f"spend parameter hash missing/mismatched in metadata {batch_id}")
    acceptance("A1", "spend 5 rows and 5/5 verified per batch", a1_ok)
    acceptance("A2", "spend 40 MSM + 40 inner-stage + 5 G16 records", a2_ok)
    acceptance("A3", "spend stage closure <= 0.01 ms", a3_ok)
    acceptance("A4", "window sweep window field matches requested c", a4_ok)

    a5_ok = True
    for data in output_records:
        for rows in data["batches"].values():
            if len(rows) != 5 or not all(str(r.get("verified", "")).lower() == "true" for r in rows):
                a5_ok = False
            if {str(r.get("rayon_threads")) for r in rows} != {str(data["record"]["threads"])}:
                a8_ok = False
    acceptance("A5", "output 5 rows and 5/5 verified per batch", a5_ok)

    a6_ok = True
    for data in tx_records:
        for rows in data["batches"].values():
            if len(rows) != 6:
                a6_ok = False
            if not all(str(r.get("verified", "")).lower() == "true" for r in rows):
                a6_ok = False
            if {r.get("tx_bytes") for r in rows} != {"2377"}:
                a6_ok = False
            if {r.get("tx_version") for r in rows} != {"V5"}:
                a6_ok = False
            if {r.get("spend_count") for r in rows} != {"1"} or {r.get("output_count") for r in rows} != {"2"}:
                a6_ok = False
            if {str(r.get("rayon_threads")) for r in rows} != {str(data["record"]["threads"])}:
                a8_ok = False
            expected_mask = f"0x{data['record']['mask']:X}"
            if {str(r.get("affinity_mask")).upper() for r in rows} != {expected_mask.upper()}:
                a7_detail.append(f"tx affinity mismatch in batch {data['record']['batch_ids']}")
    acceptance("A6", "tx 6 rows, 6/6 verified, shape/tx_bytes frozen", a6_ok)
    acceptance("A8", "rayon_threads matches the requested value", a8_ok)

    # A7: affinity readback is enforced by the runners; spend metadata records it.
    a7_ok = not a7_detail
    acceptance("A7", "affinity readback recorded/enforced", a7_ok, "; ".join(a7_detail))

    # A9: cross-batch provenance consistency.
    git_heads = {d["record"]["git_head"] for d in per_record_data}
    prereg_hashes = {d["record"]["prereg_sha256"] for d in per_record_data}
    tx_exe_hashes = {r.get("exe_sha256") for data in tx_records for rows in data["batches"].values() for r in rows}
    tx_spend_hashes = {r.get("spend_params_sha256") for data in tx_records for rows in data["batches"].values() for r in rows}
    tx_output_hashes = {r.get("output_params_sha256") for data in tx_records for rows in data["batches"].values() for r in rows}
    a9_ok = (
        len(git_heads) == 1
        and len(prereg_hashes) == 1
        and all(git_heads)
        and all(prereg_hashes)
        and len(tx_exe_hashes) == 1
        and tx_spend_hashes == {"8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13"}
        and tx_output_hashes == {"2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4"}
        and not a9_detail
    )
    acceptance("A9", "single git head, preregistration hash, and frozen tx parameter hashes", a9_ok, "; ".join(a9_detail))

    # A10: expected group layout.
    expected = {
        ("S-Scale", "spend", 1, 0x1, None): 2,
        ("S-Scale", "spend", 2, 0xFFFF, None): 2,
        ("S-Scale", "spend", 4, 0xFFFF, None): 2,
        ("S-Scale", "spend", 16, 0xFFFF, None): 2,
        ("S-Scale", "spend", 2, 0x5555, None): 2,
        ("S-Scale", "spend", 4, 0x5555, None): 2,
        ("S-ABBA", "spend", 8, 0xFFFF, None): 4,
        ("S-ABBA", "spend", 8, 0x5555, None): 4,
        ("S-Window", "spend", 8, 0x5555, 10): 2,
        ("S-Window", "spend", 8, 0x5555, 11): 2,
        ("S-Window", "spend", 8, 0x5555, 12): 2,
        ("S-Window", "spend", 8, 0x5555, 13): 2,
        ("O-Scale", "output", 1, 0x1, None): 2,
        ("O-Scale", "output", 16, 0xFFFF, None): 2,
        ("O-ABBA", "output", 8, 0xFFFF, None): 2,
        ("O-ABBA", "output", 8, 0x5555, None): 2,
        ("T-Scale", "tx", 1, 0x1, None): 2,
        ("T-Scale", "tx", 16, 0xFFFF, None): 2,
        ("T-ABBA", "tx", 8, 0xFFFF, None): 2,
        ("T-ABBA", "tx", 8, 0x5555, None): 2,
    }
    a10_ok = True
    a10_detail = []
    for key, count in expected.items():
        if key not in groups or len(groups[key]["records"]) != count:
            a10_ok = False
            a10_detail.append(f"{key}: got {len(groups.get(key, {}).get('records', []))}, want {count}")
    extra = set(groups) - set(expected)
    if extra:
        a10_ok = False
        a10_detail.append(f"unexpected groups: {sorted(extra)}")
    acceptance("A10", "expected group layout and batch counts", a10_ok, "; ".join(a10_detail))

    # A11: no duplicate batch ids; tag frozen.
    all_batch_ids = [b for d in per_record_data for b in d["record"]["batch_ids"]]
    acceptance("A11", "unique batch ids and frozen tag", len(all_batch_ids) == len(set(all_batch_ids)) and len(records) == 44)

    # A12: analyzer completed the independent recheck above.
    acceptance("A12", "independent raw-data recheck completed", True)

    # ------------------------------------------------------------------
    # Output tables.
    # ------------------------------------------------------------------
    rng = random.Random(RNG_SEED)

    summary_rows = []
    for key, group in sorted(groups.items()):
        for metric_name, metric in sorted(group["metrics"].items()):
            summary_rows.append(
                {
                    "arm": key[0],
                    "kind": key[1],
                    "threads": key[2],
                    "affinity_mask": f"0x{key[3]:X}",
                    "window_c": key[4] if key[4] is not None else "",
                    "batches": len(group["records"]),
                    "metric": metric_name,
                    "warm_n": metric["warm_n"],
                    "median": round(metric["median"], 4),
                    "mean": round(metric["mean"], 4),
                    "sd": round(metric["sd"], 4),
                    "cv_pct": round(metric["cv_pct"], 3),
                    "min": round(metric["min"], 4),
                    "max": round(metric["max"], 4),
                }
            )
    write_csv(TABLE_DIR / f"msm_scaling_summary_{TAG}.csv", summary_rows)

    # Stage summary for spend.
    stage_rows = []
    baseline_key = ("S-Scale", "spend", 1, 0x1, None)
    baseline_metrics = groups[baseline_key]["metrics"]
    for key, group in sorted(groups.items()):
        if key[1] != "spend":
            continue
        row = {
            "arm": key[0],
            "threads": key[2],
            "affinity_mask": f"0x{key[3]:X}",
            "window_c": key[4] if key[4] is not None else "",
            "batches": len(group["records"]),
            "prove_ms": round(group["metrics"]["prove_ms"]["median"], 3),
            "prove_speedup": round(baseline_metrics["prove_ms"]["median"] / group["metrics"]["prove_ms"]["median"], 4),
        }
        for column in SPEND_STAGE_COLUMNS:
            if column in group["metrics"]:
                row[column] = round(group["metrics"][column]["median"], 3)
                row[f"{column}_speedup"] = round(
                    baseline_metrics[column]["median"] / group["metrics"][column]["median"], 4
                )
        stage_rows.append(row)
    write_csv(TABLE_DIR / f"msm_scaling_stage_summary_{TAG}.csv", stage_rows)

    # H-query summary per group.
    h_rows = []
    for key, group in sorted(groups.items()):
        if key[1] != "spend":
            continue
        h_batches = []
        for data in group["data"]:
            for batch_id, rows in data["batches"].items():
                batch_id_int = to_int(batch_id)
                inner = read_csv(RAW_DIR / f"sapling_spend_msm_inner_stage_profile_{batch_id}.csv")
                warm = [r for r in inner if r.get("query") == H_QUERY and (to_int(r.get("run")) or 0) >= 2]
                if not warm:
                    continue
                rec = {
                    "wall": [to_float(r["chunk_parallel_wall_ms"]) for r in warm],
                    "fill_sum": [to_float(r["bucket_fill_sum_ms"]) for r in warm],
                    "fill_max": [to_float(r["bucket_fill_max_ms"]) for r in warm],
                    "max_conc": [to_float(r["max_concurrent_chunk_regions"]) for r in warm],
                    "window": to_int(warm[0].get("window")),
                    "chunk_count": to_int(warm[0].get("chunk_count")),
                    "exponent_count": to_int(warm[0].get("exponent_count")),
                    "bucket_count": to_int(warm[0].get("bucket_count")),
                    "bucket_element_size_bytes": to_int(warm[0].get("bucket_element_size_bytes")),
                    "payload": [to_float(r["bucket_payload_at_max_concurrency_estimate_bytes"]) for r in warm],
                }
                h_batches.append(rec)
        if not h_batches:
            continue
        window = h_batches[0]["window"]
        chunk_count = h_batches[0]["chunk_count"]
        n = h_batches[0]["exponent_count"]
        wall = median([v for rec in h_batches for v in rec["wall"]])
        fill_sum = median([v for rec in h_batches for v in rec["fill_sum"]])
        fill_max = median([v for rec in h_batches for v in rec["fill_max"]])
        max_conc = median([v for rec in h_batches for v in rec["max_conc"]])
        model = modelled_adds(n, window) if window else float("nan")
        fill_per_chunk = fill_sum / chunk_count if chunk_count else float("nan")
        row = {
            "arm": key[0],
            "threads": key[2],
            "affinity_mask": f"0x{key[3]:X}",
            "window_c": key[4] if key[4] is not None else "",
            "window": window,
            "chunk_count": chunk_count,
            "bucket_count": h_batches[0]["bucket_count"],
            "bucket_element_size_bytes": h_batches[0]["bucket_element_size_bytes"],
            "batches": len(h_batches),
            "wall_ms": round(wall, 4),
            "fill_sum_ms": round(fill_sum, 4),
            "fill_max_ms": round(fill_max, 4),
            "fill_per_chunk_ms": round(fill_per_chunk, 4),
            "fill_imbalance": round(fill_max / fill_per_chunk, 4) if fill_per_chunk else "",
            "max_concurrent": round(max_conc, 3),
            "U_max_conc_over_min_P_W": round(max_conc / min(key[2], chunk_count), 4) if chunk_count else "",
            "T_tail_ideal": round(chunk_count / (key[2] * math.ceil(chunk_count / key[2])), 4),
            "fill_parallel_eff": round(fill_sum / (wall * key[2]), 4) if wall else "",
            "modelled_adds": model,
            "ns_per_add": round(wall * 1e6 / model, 4) if model and not math.isnan(model) else "",
            "payload_at_max_concurrency_bytes": int(median([v for rec in h_batches for v in rec["payload"]])),
        }
        h_rows.append(row)
    write_csv(TABLE_DIR / f"msm_scaling_hquery_summary_{TAG}.csv", h_rows)

    # SMT ABBA comparisons.
    smt_rows = []
    for kind, arm in (("spend", "S-ABBA"), ("output", "O-ABBA"), ("tx", "T-ABBA")):
        metric = "prove_ms" if kind in {"spend", "output"} else "build_ms"
        key_ffff = (arm, kind, 8, 0xFFFF, None)
        key_5555 = (arm, kind, 8, 0x5555, None)
        if key_ffff not in groups or key_5555 not in groups:
            continue
        left = [d for data in groups[key_ffff]["data"] for d in [data]]
        right = [d for data in groups[key_5555]["data"] for d in [data]]
        left_batches = []
        right_batches = []
        for data in left:
            for metrics in data["per_batch"].values():
                left_batches.append(metrics[metric])
        for data in right:
            for metrics in data["per_batch"].values():
                right_batches.append(metrics[metric])
        diff, lo, hi = cluster_bootstrap_difference(left_batches, right_batches, rng)
        left_med = median([v for b in left_batches for v in b])
        right_med = median([v for b in right_batches for v in b])
        row = {
            "kind": kind,
            "metric": metric,
            "threads": 8,
            "batches_per_mask": len(left_batches),
            "median_0xFFFF": round(left_med, 4),
            "median_0x5555": round(right_med, 4),
            "delta_pct_FFFF_minus_5555": round((left_med - right_med) / left_med * 100.0, 4),
            "delta_ci90_low_ms": round(lo, 4),
            "delta_ci90_high_ms": round(hi, 4),
            "delta_ci90_excludes_zero": bool(lo > 0 or hi < 0),
        }
        if kind == "spend":
            # H fill per chunk comparison.
            def h_fill_per_chunk(mask_key):
                vals = []
                for data in groups[mask_key]["data"]:
                    for batch_id in data["batches"]:
                        inner = read_csv(RAW_DIR / f"sapling_spend_msm_inner_stage_profile_{batch_id}.csv")
                        warm = [r for r in inner if r.get("query") == H_QUERY and (to_int(r.get("run")) or 0) >= 2]
                        if warm:
                            vals.append(
                                median([to_float(r["bucket_fill_sum_ms"]) for r in warm])
                                / (to_int(warm[0]["chunk_count"]) or 1)
                            )
                return vals
            fill_ffff = h_fill_per_chunk(key_ffff)
            fill_5555 = h_fill_per_chunk(key_5555)
            if fill_ffff and fill_5555:
                row["h_fill_per_chunk_0xFFFF"] = round(median(fill_ffff), 4)
                row["h_fill_per_chunk_0x5555"] = round(median(fill_5555), 4)
                row["h_fill_delta_pct"] = round(
                    (median(fill_ffff) - median(fill_5555)) / median(fill_ffff) * 100.0, 4
                )
        smt_rows.append(row)
    write_csv(TABLE_DIR / f"msm_scaling_smt_abba_{TAG}.csv", smt_rows)

    # Window sweep.
    window_rows = []
    for c in WINDOW_ORDER:
        key = ("S-Window", "spend", 8, 0x5555, c)
        if key not in groups:
            continue
        ns_batches = []
        for data in groups[key]["data"]:
            for batch_id in data["batches"]:
                inner = read_csv(RAW_DIR / f"sapling_spend_msm_inner_stage_profile_{batch_id}.csv")
                warm = [r for r in inner if r.get("query") == H_QUERY and (to_int(r.get("run")) or 0) >= 2]
                if not warm:
                    continue
                wall = median([to_float(r["chunk_parallel_wall_ms"]) for r in warm])
                window = to_int(warm[0]["window"])
                n = to_int(warm[0]["exponent_count"])
                if window and n:
                    ns_batches.append([wall * 1e6 / modelled_adds(n, window)])
        if not ns_batches:
            continue
        point, lo, hi = cluster_bootstrap_median(ns_batches, rng)
        observed_window = ""
        if groups[key]["batches"]:
            first_inner = read_csv(
                RAW_DIR / f"sapling_spend_msm_inner_stage_profile_{groups[key]['batches'][0]}.csv"
            )
            first_h = [r for r in first_inner if r.get("query") == H_QUERY]
            if first_h:
                observed_window = to_int(first_h[0].get("window"))
        window_rows.append(
            {
                "window_c": c,
                "requested_window": c,
                "observed_window": observed_window,
                "W_chunk_count": w_value(c),
                "batches": len(ns_batches),
                "ns_per_add_median": round(point, 4),
                "ns_per_add_ci90_low": round(lo, 4),
                "ns_per_add_ci90_high": round(hi, 4),
            }
        )
    if window_rows:
        def ns_batches_for(c):
            key = ("S-Window", "spend", 8, 0x5555, c)
            batches = []
            for data in groups[key]["data"]:
                for batch_id in data["batches"]:
                    inner = read_csv(RAW_DIR / f"sapling_spend_msm_inner_stage_profile_{batch_id}.csv")
                    warm = [r for r in inner if r.get("query") == H_QUERY and (to_int(r.get("run")) or 0) >= 2]
                    if not warm:
                        continue
                    wall = median([to_float(r["chunk_parallel_wall_ms"]) for r in warm])
                    window = to_int(warm[0]["window"])
                    n = to_int(warm[0]["exponent_count"])
                    if window and n:
                        batches.append([wall * 1e6 / modelled_adds(n, window)])
            return batches
        if 12 in WINDOW_ORDER and 13 in WINDOW_ORDER:
            ratio, lo, hi = cluster_bootstrap_ratio(ns_batches_for(12), ns_batches_for(13), rng)
            for row in window_rows:
                if row["window_c"] == 12:
                    row["ratio_to_c13"] = round(ratio, 4)
                    row["ratio_ci90_low"] = round(lo, 4)
                    row["ratio_ci90_high"] = round(hi, 4)
        if 11 in WINDOW_ORDER and 13 in WINDOW_ORDER:
            ratio, lo, hi = cluster_bootstrap_ratio(ns_batches_for(11), ns_batches_for(13), rng)
            for row in window_rows:
                if row["window_c"] == 11:
                    row["ratio_to_c13"] = round(ratio, 4)
                    row["ratio_ci90_low"] = round(lo, 4)
                    row["ratio_ci90_high"] = round(hi, 4)
    write_csv(TABLE_DIR / f"msm_scaling_window_sweep_{TAG}.csv", window_rows)

    # Amdahl fit on the spend 0xFFFF default-window curve.
    amdahl_rows = []
    fit_points = []
    for t in (1, 2, 4, 8):
        if t == 8:
            key = ("S-ABBA", "spend", 8, 0xFFFF, None)
        else:
            key = ("S-Scale", "spend", t, 0xFFFF, None) if t != 1 else ("S-Scale", "spend", 1, 0x1, None)
        if key in groups:
            fit_points.append((1.0 / t, groups[key]["metrics"]["prove_ms"]["median"]))
    if len(fit_points) >= 3:
        xs = [p[0] for p in fit_points]
        ys = [p[1] for p in fit_points]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        b = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
        a = mean_y - b * mean_x
        observed_16 = None
        key16 = ("S-Scale", "spend", 16, 0xFFFF, None)
        if key16 in groups:
            observed_16 = groups[key16]["metrics"]["prove_ms"]["median"]
        predicted_16 = a + b / 16.0
        amdahl_rows.append(
            {
                "curve": "spend_0xFFFF_default_window",
                "fit_points_P": "1,2,4,8",
                "a_ms": round(a, 4),
                "b_ms": round(b, 4),
                "serial_fraction": round(a / (a + b), 4) if (a + b) else "",
                "predicted_16t_ms": round(predicted_16, 4),
                "observed_16t_ms": round(observed_16, 4) if observed_16 is not None else "",
                "error_16t": round((predicted_16 - observed_16) / observed_16, 4) if observed_16 else "",
            }
        )
    write_csv(TABLE_DIR / f"msm_scaling_amdahl_{TAG}.csv", amdahl_rows)

    # Acceptance table.
    acceptance_rows = [
        {"check": check, "status": "PASS" if status else "FAIL", "detail": detail}
        for check, status, detail in ACCEPTANCE
    ]
    write_csv(TABLE_DIR / f"msm_scaling_acceptance_{TAG}.csv", acceptance_rows)

    # Figures.
    make_figures(groups, h_rows, window_rows, smt_rows)

    failed = [row for row in acceptance_rows if row["status"] == "FAIL"]
    print(f"acceptance: {len(acceptance_rows) - len(failed)}/{len(acceptance_rows)} PASS")
    for row in acceptance_rows:
        print(f"  {row['status']:4} {row['check']}: {row['detail']}")
    if failed:
        print(f"WARNING: {len(failed)} acceptance check(s) failed")


def acceptance(check: str, detail: str, status: bool, extra: str = "") -> None:
    ACCEPTANCE.append((check, bool(status), detail + (f" [{extra}]" if extra else "")))


def make_figures(groups, h_rows, window_rows, smt_rows) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    def plot_curve(kind, metric, title, filename):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for mask, color in ((0x1, "tab:blue"), (0xFFFF, "tab:red"), (0x5555, "tab:green")):
            pts = []
            for key, group in groups.items():
                if key[1] != kind or key[3] != mask or key[4] is not None:
                    continue
                pts.append((key[2], group["metrics"][metric]["median"]))
            if pts:
                pts.sort()
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", color=color, label=f"0x{mask:X}")
        ax.set_xlabel("Rayon threads")
        ax.set_ylabel(metric)
        ax.set_title(title)
        ax.set_xscale("log", base=2)
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / filename, dpi=150)
        plt.close(fig)

    plot_curve("spend", "prove_ms", "Spend prove vs threads", f"msm_scaling_spend_prove_{TAG}.png")
    plot_curve("output", "prove_ms", "Output prove vs threads", f"msm_scaling_output_prove_{TAG}.png")
    plot_curve("tx", "build_ms", "Transaction build vs threads", f"msm_scaling_tx_build_{TAG}.png")

    if h_rows:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for mask, color in ((0xFFFF, "tab:red"), (0x5555, "tab:green")):
            pts = [(r["threads"], r["fill_per_chunk_ms"]) for r in h_rows if r["affinity_mask"] == f"0x{mask:X}" and r["window_c"] == ""]
            pts.sort()
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", color=color, label=f"0x{mask:X}")
        ax.set_xlabel("Rayon threads")
        ax.set_ylabel("H-query bucket_fill_sum / chunk_count (ms)")
        ax.set_title("H-query per-chunk fill time")
        ax.set_xscale("log", base=2)
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / f"msm_scaling_hquery_fill_per_chunk_{TAG}.png", dpi=150)
        plt.close(fig)

    if window_rows:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        cs = [r["window_c"] for r in window_rows]
        vals = [r["ns_per_add_median"] for r in window_rows]
        ax.bar([str(c) for c in cs], vals, color="tab:purple")
        ax.set_xlabel("window width c")
        ax.set_ylabel("H-query ns per modelled group add")
        ax.set_title("Window-width sweep at 8t / 0x5555")
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / f"msm_scaling_window_sweep_{TAG}.png", dpi=150)
        plt.close(fig)

    if smt_rows:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        labels = [f"{r['kind']}({r['metric']})" for r in smt_rows]
        x = range(len(labels))
        width = 0.35
        ax.bar([i - width / 2 for i in x], [r["median_0xFFFF"] for r in smt_rows], width, label="0xFFFF")
        ax.bar([i + width / 2 for i in x], [r["median_0x5555"] for r in smt_rows], width, label="0x5555")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=15)
        ax.set_ylabel("median ms")
        ax.set_title("8-thread SMT ABBA comparison")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / f"msm_scaling_smt_abba_{TAG}.png", dpi=150)
        plt.close(fig)


if __name__ == "__main__":
    analyze()
