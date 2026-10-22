#!/usr/bin/env python3
"""Frozen analyzer for Stage 1b (gated adaptive window + tail-only split).

Inputs are the Stage 1b manifest and append-only raw CSVs. The analyzer never
writes into experiments/raw; it only rebuilds results/tables and results/figures.
"""

from __future__ import annotations

import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TAG = "msm_adaptive_20261022"
PREREG_SHA = "fcd2bd7cbfd80443a0a9f9765f5077222c5b6ed4c5f5535c1536a8d6ec16b0a1"
BOOTSTRAP_N = 10000
ALPHA = 0.10
RNG_SEED = 20261022
H_QUERY = "H_query_G1"

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "experiments" / "raw" / "csv"
METADATA_DIR = ROOT / "experiments" / "metadata"
TABLE_DIR = ROOT / "results" / "tables"
FIGURE_DIR = ROOT / "results" / "figures"

MANIFEST = METADATA_DIR / f"msm_adaptive_manifest_{TAG}.csv"
TX_RAW = RAW_DIR / f"sapling_tx_scaling_runs_{TAG}.csv"
POLICY_OUTPUT = METADATA_DIR / f"msm_adaptive_policy_output_{TAG}.csv"

EXPECTED_POLICY = {
    "C0": (13, 20, 1, 20, "none"),
    "C1": (11, 24, 1, 24, "none"),
    "C2": (13, 20, 2, 24, "tail"),
    "C3": (10, 26, 4, 32, "tail"),
    "C4": (11, 24, 1, 24, "none"),
}
ARMS = ["C0", "C1", "C2", "C3", "C4"]


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
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def to_int(value) -> int | None:
    try:
        text = str(value).strip()
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(text)
    except (TypeError, ValueError):
        return None


def median(values: list[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        raise ValueError("median of empty values")
    return float(statistics.median(clean))


def quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("empty bootstrap sample")
    position = (len(sorted_values) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def batch_medians(values: list[float]) -> float:
    return median(values)


def ratio_ci(treatment: list[list[float]], control: list[list[float]], rng: random.Random):
    t_med = [batch_medians(v) for v in treatment if v]
    c_med = [batch_medians(v) for v in control if v]
    if not t_med or not c_med:
        return float("nan"), float("nan"), float("nan")
    point = median(t_med) / median(c_med)
    samples = []
    for _ in range(BOOTSTRAP_N):
        t_sample = [t_med[rng.randrange(len(t_med))] for _ in t_med]
        c_sample = [c_med[rng.randrange(len(c_med))] for _ in c_med]
        samples.append(median(t_sample) / median(c_sample))
    samples.sort()
    return point, quantile(samples, ALPHA / 2), quantile(samples, 1 - ALPHA / 2)


def superiority_verdict(ratio: float, low: float, high: float) -> str:
    if ratio <= 0.95 and high < 1.0:
        return "SUPPORT"
    if ratio >= 0.98 or low > 1.0:
        return "NOT_SUPPORTED"
    return "UNCERTAIN"


def noninferiority_verdict(ratio: float, high: float) -> str:
    return "PASS" if ratio <= 1.02 and high <= 1.05 else "FAIL"


def regression_verdict(ratio: float, high: float) -> str:
    if ratio <= 1.03 and high <= 1.05:
        return "NO_REGRESSION"
    return "REGRESSION_OR_UNCERTAIN"


def manifest_rows() -> list[dict]:
    rows = read_csv(MANIFEST)
    if not rows:
        raise RuntimeError(f"missing empty manifest: {MANIFEST}")
    records = []
    seen = set()
    for row in rows:
        batch = str(row.get("batch_id", "")).strip()
        if batch:
            if batch in seen:
                raise RuntimeError(f"duplicate batch id: {batch}")
            seen.add(batch)
        records.append(
            {
                "tag": row.get("tag", ""),
                "order": to_int(row.get("order")) or 0,
                "arm": row.get("arm", ""),
                "kind": row.get("kind", ""),
                "config": row.get("config", ""),
                "label": row.get("label", ""),
                "env": row.get("env", ""),
                "start_utc": row.get("start_utc", ""),
                "end_utc": row.get("end_utc", ""),
                "exit_code": to_int(row.get("exit_code")),
                "batch_id": batch,
                "git_head": row.get("git_head", ""),
                "prereg_sha256": row.get("prereg_sha256", ""),
                "spend_exe_sha256": row.get("spend_exe_sha256", ""),
                "output_exe_sha256": row.get("output_exe_sha256", ""),
                "tx_exe_sha256": row.get("tx_exe_sha256", ""),
                "spend_params_sha256": row.get("spend_params_sha256", ""),
                "output_params_sha256": row.get("output_params_sha256", ""),
                "notes": row.get("notes", ""),
            }
        )
    return records


def proof_rows(record: dict) -> list[dict]:
    if record["kind"] not in ("spend", "output"):
        return []
    path = RAW_DIR / f"sapling_{record['kind']}_prover_runs_{record['label']}.csv"
    return [r for r in read_csv(path) if str(r.get("batch_id", "")) == record["batch_id"]]


def tx_rows(record: dict, all_tx: list[dict]) -> list[dict]:
    return [r for r in all_tx if str(r.get("batch_id", "")) == record["batch_id"]]


def warm_prove(rows: list[dict]) -> list[float]:
    return [to_float(r.get("prove_ms")) for r in rows if (to_int(r.get("run")) or 0) >= 2]


def warm_build(rows: list[dict]) -> list[float]:
    return [to_float(r.get("build_ms")) for r in rows if (to_int(r.get("run")) or 0) >= 2]


def stage_rows(batch_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    inner = read_csv(RAW_DIR / f"sapling_spend_msm_inner_stage_profile_{batch_id}.csv")
    g16 = read_csv(RAW_DIR / f"sapling_spend_stage_profile_{batch_id}.csv")
    calls = read_csv(RAW_DIR / f"sapling_spend_msm_call_profile_{batch_id}.csv")
    return inner, g16, calls


def collect(records: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    all_tx = read_csv(TX_RAW)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    policy_rows: list[dict] = []
    stage_summary: list[dict] = []

    for record in sorted(records, key=lambda r: r["order"]):
        if not record["batch_id"]:
            continue
        key = (record["kind"], record["arm"])
        batch = {
            "batch_id": record["batch_id"],
            "order": record["order"],
            "rows": [],
            "values": [],
        }

        if record["kind"] in ("spend", "output"):
            rows = proof_rows(record)
            values = warm_prove(rows)
            batch["rows"] = rows
            batch["values"] = values
        else:
            rows = tx_rows(record, all_tx)
            values = warm_build(rows)
            batch["rows"] = rows
            batch["values"] = values

        if record["kind"] == "spend":
            inner, g16, calls = stage_rows(record["batch_id"])
            h_rows = [r for r in inner if r.get("query") == H_QUERY]
            if h_rows:
                first = h_rows[0]
                policy = {
                    "arm": record["arm"],
                    "batch_id": record["batch_id"],
                    "query": H_QUERY,
                    "window": to_int(first.get("window")),
                    "bucket_count": to_int(first.get("bucket_count")),
                    "chunk_count": to_int(first.get("chunk_count")),
                    "split": to_int(first.get("split")),
                    "task_count": to_int(first.get("task_count")),
                    "split_mode": first.get("split_mode", "none"),
                    "wall_ms": median([to_float(r.get("chunk_parallel_wall_ms")) for r in h_rows]),
                    "fill_ms": median([to_float(r.get("bucket_fill_sum_ms")) for r in h_rows]),
                    "reduce_ms": median([to_float(r.get("bucket_reduce_sum_ms")) for r in h_rows]),
                    "max_concurrent": median([to_float(r.get("max_concurrent_chunk_regions")) for r in h_rows]),
                }
                policy_rows.append(policy)
                stage_summary.append(
                    {
                        **policy,
                        "g16_rows": len(g16),
                        "call_rows": len(calls),
                        "inner_rows": len(inner),
                    }
                )
            batch["stage"] = {
                "inner": inner,
                "g16": g16,
                "calls": calls,
                "h": h_rows,
            }
        groups[key].append(batch)

    return groups, policy_rows, stage_summary


def acceptance(records: list[dict], groups: dict, policy_rows: list[dict], output_policy: list[dict]) -> list[dict]:
    checks: list[dict] = []

    def add(item: str, ok: bool, detail: str) -> None:
        checks.append({"item": item, "status": "PASS" if ok else "FAIL", "detail": detail})

    spend_batches = [b for (kind, _), batches in groups.items() if kind == "spend" for b in batches]
    output_batches = [b for (kind, _), batches in groups.items() if kind == "output" for b in batches]
    tx_batches = [b for (kind, _), batches in groups.items() if kind == "tx" for b in batches]

    spend_ok = True
    spend_details = []
    for batch in spend_batches:
        rows = batch["rows"]
        stage = batch.get("stage", {})
        ok = (
            len(rows) == 5
            and all(str(r.get("verified", "")).lower() == "true" for r in rows)
            and all((to_int(r.get("rayon_threads")) or 0) == 8 for r in rows)
            and len(stage.get("calls", [])) == 40
            and len(stage.get("inner", [])) == 40
            and len(stage.get("g16", [])) == 5
        )
        if not ok:
            spend_ok = False
            spend_details.append(batch["batch_id"])
    add("A1", spend_ok, f"Spend batches={len(spend_batches)}; bad={','.join(spend_details) or 'none'}")

    output_ok = True
    output_details = []
    for batch in output_batches:
        rows = batch["rows"]
        ok = (
            len(rows) == 5
            and all(str(r.get("verified", "")).lower() == "true" for r in rows)
            and all((to_int(r.get("rayon_threads")) or 0) == 8 for r in rows)
        )
        if not ok:
            output_ok = False
            output_details.append(batch["batch_id"])
    add("A2", output_ok, f"Output batches={len(output_batches)}; bad={','.join(output_details) or 'none'}")

    tx_ok = True
    tx_details = []
    for batch in tx_batches:
        rows = batch["rows"]
        ok = len(rows) == 6 and all(
            str(r.get("verified", "")).lower() == "true"
            and r.get("tx_version") == "V5"
            and to_int(r.get("spend_count")) == 1
            and to_int(r.get("output_count")) == 2
            and to_int(r.get("tx_bytes")) == 2377
            and to_int(r.get("rayon_threads")) == 8
            and to_int(r.get("affinity_mask")) == 0x5555
            for r in rows
        )
        if not ok:
            tx_ok = False
            tx_details.append(batch["batch_id"])
    add("A3", tx_ok, f"Tx batches={len(tx_batches)}; bad={','.join(tx_details) or 'none'}")

    configs = {r["config"] for r in records}
    add("A4", all(c == "8t_0x5555_C0" or c.startswith("8t_0x5555_") for c in configs),
        f"configs={len(configs)}; expected all 8t_0x5555_*")

    head_values = {r["git_head"] for r in records}
    spend_exe = {r["spend_exe_sha256"] for r in records}
    output_exe = {r["output_exe_sha256"] for r in records}
    tx_exe = {r["tx_exe_sha256"] for r in records}
    spend_params = {r["spend_params_sha256"] for r in records}
    output_params = {r["output_params_sha256"] for r in records}
    hash_ok = all(len(v) == 1 and next(iter(v)) for v in (head_values, spend_exe, output_exe, tx_exe, spend_params, output_params))
    tx_hash_ok = all(
        r.get("spend_params_sha256") == next(iter(spend_params))
        and r.get("output_params_sha256") == next(iter(output_params))
        and r.get("exe_sha256") == next(iter(tx_exe))
        for batch in tx_batches for r in batch["rows"]
    ) if tx_batches and hash_ok else False
    add("A5", hash_ok and tx_hash_ok,
        f"git_heads={len(head_values)}; spend_exe={len(spend_exe)}; output_exe={len(output_exe)}; tx_exe={len(tx_exe)}; params={len(spend_params)}/{len(output_params)}")

    tag_ok = all(r["tag"] == TAG for r in records)
    prereg_ok = all(r["prereg_sha256"] == PREREG_SHA for r in records)
    add("A6", tag_ok and prereg_ok, f"tag={TAG}; expected_prereg={PREREG_SHA}")

    policy_ok = True
    policy_detail = []
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for row in policy_rows:
        by_arm[row["arm"]].append(row)
    for arm, expected in EXPECTED_POLICY.items():
        rows = by_arm.get(arm, [])
        if len(rows) != 4:
            policy_ok = False
            policy_detail.append(f"{arm}:batches={len(rows)}")
            continue
        for row in rows:
            observed = (
                row["window"],
                row["chunk_count"],
                row["split"],
                row["task_count"],
                row["split_mode"],
            )
            if observed != expected:
                policy_ok = False
                policy_detail.append(f"{arm}:{row['batch_id']}={observed} expected={expected}")
                break
    if not output_policy:
        policy_ok = False
        policy_detail.append("output policy not observed")
    else:
        for row in output_policy:
            if row.get("arm") != "C1" or to_int(row.get("window")) != 10 or to_int(row.get("chunk_count")) != 26:
                policy_ok = False
                policy_detail.append(f"output:{row}")
    add("A7", policy_ok,
        "Spend H-query policy observed; " + ("Output C1 c10/W26 observed" if output_policy else "Output policy missing") +
        ("; " + "; ".join(policy_detail) if policy_detail else ""))

    unique_ids = {r["batch_id"] for r in records if r["batch_id"]}
    counts_ok = len(records) == 44 and len(unique_ids) == 44
    exits_ok = all(r["exit_code"] == 0 for r in records)
    kinds = defaultdict(int)
    for r in records:
        kinds[r["kind"]] += 1
    add("A8", counts_ok and exits_ok and kinds["spend"] == 20 and kinds["output"] == 12 and kinds["tx"] == 12,
        f"rows={len(records)} unique={len(unique_ids)} exits={sorted({r['exit_code'] for r in records})} kinds={dict(kinds)}")

    failed_files = list(RAW_DIR.glob(f"*{TAG}*.failed*"))
    notes_ok = all(not r["notes"] for r in records)
    add("A9", not failed_files and notes_ok,
        f"failed_files={len(failed_files)}; nonempty_notes={sum(1 for r in records if r['notes'])}")

    return checks


def make_tables(records: list[dict], groups: dict, policy_rows: list[dict], stage_summary: list[dict], checks: list[dict]) -> None:
    summary_rows = []
    for (kind, arm), batches in sorted(groups.items()):
        values = [v for batch in batches for v in batch["values"]]
        batch_values = [batch_medians(batch["values"]) for batch in batches if batch["values"]]
        if not values:
            continue
        summary_rows.append(
            {
                "kind": kind,
                "arm": arm,
                "metric": "build_ms" if kind == "tx" else "prove_ms",
                "batches": len(batch_values),
                "median_ms": round(median(batch_values), 4),
                "min_batch_ms": round(min(batch_values), 4),
                "max_batch_ms": round(max(batch_values), 4),
                "batch_medians_ms": ";".join(f"{v:.4f}" for v in batch_values),
            }
        )
    write_csv(TABLE_DIR / f"msm_adaptive_summary_{TAG}.csv", summary_rows)

    rng = random.Random(RNG_SEED)
    contrasts = []
    specs = [
        ("P1", "spend", "C1", "C0", "prove_ms", "superiority"),
        ("P2", "spend", "C2", "C0", "prove_ms", "superiority"),
        ("P3", "spend", "C3", "C0", "prove_ms", "superiority"),
        ("P4", "spend", "C1", "C4", "prove_ms", "noninferiority"),
        ("P5", "output", "C1", "C0", "prove_ms", "regression"),
        ("P6", "tx", "C1", "C0", "build_ms", "regression"),
        ("S1", "spend", "C4", "C0", "prove_ms", "descriptive"),
        ("S2", "output", "C4", "C0", "prove_ms", "descriptive"),
        ("S3", "tx", "C4", "C0", "build_ms", "descriptive"),
    ]
    for ident, kind, treatment, control, metric, mode in specs:
        t = [b["values"] for b in groups.get((kind, treatment), []) if b["values"]]
        c = [b["values"] for b in groups.get((kind, control), []) if b["values"]]
        if not t or not c:
            continue
        ratio, low, high = ratio_ci(t, c, rng)
        if mode == "superiority":
            verdict = superiority_verdict(ratio, low, high)
        elif mode == "noninferiority":
            verdict = noninferiority_verdict(ratio, high)
        elif mode == "regression":
            verdict = regression_verdict(ratio, high)
        else:
            verdict = "DESCRIPTIVE"
        contrasts.append(
            {
                "id": ident,
                "kind": kind,
                "metric": metric,
                "treatment": treatment,
                "control": control,
                "ratio": round(ratio, 6),
                "ci90_low": round(low, 6),
                "ci90_high": round(high, 6),
                "relative_pct": round((1.0 - ratio) * 100.0, 4),
                "verdict": verdict,
            }
        )
    write_csv(TABLE_DIR / f"msm_adaptive_contrasts_{TAG}.csv", contrasts)

    write_csv(TABLE_DIR / f"msm_adaptive_policy_{TAG}.csv", policy_rows)
    write_csv(TABLE_DIR / f"msm_adaptive_stage_{TAG}.csv", stage_summary)

    checks.append({"item": "A10", "status": "PASS", "detail": "analyzer rebuilt summary/contrasts/policy/stage tables and figures"})
    write_csv(TABLE_DIR / f"msm_adaptive_acceptance_{TAG}.csv", checks)


def make_figures(groups: dict, contrasts: list[dict]) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    for kind, arms, ylabel, name in [
        ("spend", ARMS, "prove_ms (warm median)", "spend_prove_by_arm"),
        ("output", ["C0", "C1", "C4"], "prove_ms (warm median)", "output_prove_by_arm"),
        ("tx", ["C0", "C1", "C4"], "build_ms (warm median)", "tx_build_by_arm"),
    ]:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        positions = []
        labels = []
        for index, arm in enumerate(arms):
            batches = groups.get((kind, arm), [])
            values = [batch_medians(b["values"]) for b in batches if b["values"]]
            if not values:
                continue
            positions.append(index)
            labels.append(arm)
            ax.scatter([index] * len(values), values, s=32, alpha=0.75)
            ax.plot([index - 0.18, index + 0.18], [median(values)] * 2, color="black", linewidth=2)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)
        ax.set_ylabel(ylabel)
        ax.set_title(f"Stage 1b {kind}: batch medians")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / f"msm_adaptive_{name}_{TAG}.png", dpi=180)
        plt.close(fig)

    if contrasts:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        labels = [c["id"] for c in contrasts]
        ratios = [to_float(c["ratio"]) for c in contrasts]
        lows = [to_float(c["ci90_low"]) for c in contrasts]
        highs = [to_float(c["ci90_high"]) for c in contrasts]
        y = list(range(len(labels)))
        ax.errorbar(ratios, y, xerr=[ [r - l for r, l in zip(ratios, lows)], [h - r for r, h in zip(ratios, highs)] ], fmt="o", capsize=3)
        ax.axvline(1.0, color="black", linewidth=1)
        ax.axvline(0.95, color="tab:green", linestyle="--", linewidth=1)
        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.set_xlabel("treatment / control (90% cluster bootstrap CI)")
        ax.set_title("Stage 1b preregistered contrasts")
        ax.grid(axis="x", alpha=0.25)
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / f"msm_adaptive_contrasts_{TAG}.png", dpi=180)
        plt.close(fig)


def main() -> None:
    records = manifest_rows()
    groups, policy_rows, stage_summary = collect(records)
    output_policy = read_csv(POLICY_OUTPUT)
    checks = acceptance(records, groups, policy_rows, output_policy)
    make_tables(records, groups, policy_rows, stage_summary, checks)
    contrasts = read_csv(TABLE_DIR / f"msm_adaptive_contrasts_{TAG}.csv")
    make_figures(groups, contrasts)

    print(f"manifest={MANIFEST}")
    print(f"records={len(records)} unique_batches={len({r['batch_id'] for r in records if r['batch_id']})}")
    for check in checks:
        print(f"{check['item']}: {check['status']} - {check['detail']}")
    for row in contrasts:
        print(f"{row['id']}: ratio={row['ratio']} ci=[{row['ci90_low']},{row['ci90_high']}] verdict={row['verdict']}")


if __name__ == "__main__":
    main()
