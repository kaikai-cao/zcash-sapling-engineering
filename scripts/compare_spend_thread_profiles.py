#!/usr/bin/env python3
"""Compare two provenance-linked Sapling Spend profile batches.

Reads existing raw CSVs and metadata for two batches; never creates, edits, or
repairs raw observations. Writes derived comparison CSVs, PNGs, and a Markdown
report under results/ and experiments/metadata/.

Run from the repository root, or invoke this script from anywhere:
    python scripts/compare_spend_thread_profiles.py

Optional batch overrides:
    python scripts/compare_spend_thread_profiles.py \
      --single-batch 1791801666809 --parallel-batch 1791802391142
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from datetime import datetime, timezone
import statistics
import sys
from pathlib import Path
from typing import Any

DEFAULT_SINGLE_BATCH = "1791801666809"
DEFAULT_PARALLEL_BATCH = "1791802391142"
DEFAULT_SINGLE_THREADS = 1
DEFAULT_PARALLEL_THREADS = 20

STAGE_LABELS = {
    "circuit_synthesis_constraints_ms": "Circuit synthesis / constraints",
    "worker_vk_setup_ms": "Worker / VK setup",
    "qap_fft_h_exponent_prep_ms": "QAP / FFT / H preparation",
    "h_query_access_dispatch_ms": "H-query access / dispatch",
    "assignment_query_prep_dispatch_ms": "Assignment / query prep / dispatch",
    "proof_scalar_terms_ms": "Proof scalar terms",
    "wait_and_assembly_ms": "Wait / assembly",
    "create_proof_body_ms": "Proof body total",
}

STAGE_FIELDS = [
    "circuit_synthesis_constraints_ms",
    "worker_vk_setup_ms",
    "qap_fft_h_exponent_prep_ms",
    "h_query_access_dispatch_ms",
    "assignment_query_prep_dispatch_ms",
    "proof_scalar_terms_ms",
    "wait_and_assembly_ms",
    "create_proof_body_ms",
]

# Fixed call names in the instrumented Groth16 prover. CSV row order can differ
# under parallel execution because tasks emit their profile record on completion.
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

CORE_IDENTITY_KEYS = [
    "Parameter SHA-256",
    "vendor/bellman/src/multiexp.rs SHA-256",
    "vendor/groth16/src/prover.rs SHA-256",
    "spend_prover_smoke.rs SHA-256",
    "Cargo manifest SHA-256",
    "Sapling dependency HEAD",
]


def median(rows: list[dict[str, str]], field: str) -> float:
    return statistics.median(float(row[field]) for row in rows)


def fmt(value: float | None, places: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{places}f}"


def pct_reduction(single: float, parallel: float) -> float | None:
    if single == 0:
        return None
    return 100.0 * (1.0 - parallel / single)


def speedup(single: float, parallel: float) -> float | None:
    if parallel == 0:
        return None
    return single / parallel


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required existing input is missing: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"CSV has a header but no data rows: {path}")
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_report_value(report: str, key: str) -> str | None:
    # Keys are metadata bullet labels; return text after the first colon.
    pattern = re.compile(r"(?m)^- " + re.escape(key) + r":\s*(.*?)\s*$")
    match = pattern.search(report)
    return match.group(1) if match else None


def load_profile(root: Path, batch_id: str, expected_threads: int) -> dict[str, Any]:
    raw = root / "experiments" / "raw" / "csv"
    meta_path = root / "experiments" / "metadata" / f"sapling_spend_combined_profile_{batch_id}.md"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Profile metadata not found: {meta_path}")
    report = meta_path.read_text(encoding="utf-8-sig")
    report_batch = parse_report_value(report, "Batch ID")
    if report_batch != batch_id:
        raise ValueError(f"Metadata batch ID mismatch: requested {batch_id}, report says {report_batch!r}")
    thread_match = re.search(r"RAYON_NUM_THREADS=(\d+)", report)
    if not thread_match or int(thread_match.group(1)) != expected_threads:
        observed = thread_match.group(1) if thread_match else "missing"
        raise ValueError(f"Batch {batch_id}: metadata RAYON_NUM_THREADS does not match {expected_threads}; found {observed}")

    shared_prover_path = raw / "sapling_spend_prover_runs_release.csv"
    all_prover_rows = read_csv(shared_prover_path)
    prover_rows = [r for r in all_prover_rows if r.get("batch_id") == batch_id]
    if len(prover_rows) != 5:
        raise ValueError(f"Batch {batch_id}: expected 5 prover rows, found {len(prover_rows)}")
    prover_rows.sort(key=lambda r: int(r["run"]))
    if [int(r["run"]) for r in prover_rows] != [1, 2, 3, 4, 5]:
        raise ValueError(f"Batch {batch_id}: prover run IDs are not exactly 1..5")
    if any(r.get("verified", "").lower() != "true" for r in prover_rows):
        raise ValueError(f"Batch {batch_id}: at least one proof did not verify")
    observed_threads = {int(r["rayon_threads"]) for r in prover_rows}
    if observed_threads != {expected_threads}:
        raise ValueError(
            f"Batch {batch_id}: expected rayon_threads={expected_threads}; found {sorted(observed_threads)}"
        )
    profiles = {r.get("build_profile") for r in prover_rows}
    if profiles != {"release"}:
        raise ValueError(f"Batch {batch_id}: expected Release records; found {profiles}")

    stage_path = raw / f"sapling_spend_stage_profile_{batch_id}.csv"
    msm_path = raw / f"sapling_spend_msm_call_profile_{batch_id}.csv"
    summary_path = raw / f"sapling_spend_profile_run_summary_{batch_id}.csv"
    stage_rows = read_csv(stage_path)
    msm_rows = read_csv(msm_path)
    summary_rows = read_csv(summary_path)

    for label, rows, expected in [
        ("stage", stage_rows, 5),
        ("MSM", msm_rows, 40),
        ("per-run summary", summary_rows, 5),
    ]:
        if len(rows) != expected:
            raise ValueError(f"Batch {batch_id}: expected {expected} {label} rows, got {len(rows)}")
        other_ids = sorted({r.get("batch_id", "") for r in rows})
        if other_ids != [batch_id]:
            raise ValueError(f"Batch {batch_id}: {label} CSV contains unexpected batch IDs: {other_ids}")

    stage_rows.sort(key=lambda r: int(r["run"]))
    summary_rows.sort(key=lambda r: int(r["run"]))
    if [int(r["run"]) for r in stage_rows] != [1, 2, 3, 4, 5]:
        raise ValueError(f"Batch {batch_id}: stage run IDs are not exactly 1..5")
    if [int(r["run"]) for r in summary_rows] != [1, 2, 3, 4, 5]:
        raise ValueError(f"Batch {batch_id}: summary run IDs are not exactly 1..5")
    if any(r.get("all_verified", "").lower() != "true" for r in summary_rows):
        raise ValueError(f"Batch {batch_id}: summary says at least one proof was not verified")

    if {r.get("query") for r in msm_rows} != set(QUERY_ORDER):
        raise ValueError(f"Batch {batch_id}: MSM query categories do not match the expected eight queries")
    for query in QUERY_ORDER:
        rows = [r for r in msm_rows if r["query"] == query]
        if len(rows) != 5:
            raise ValueError(f"Batch {batch_id}: expected 5 MSM calls for {query}; found {len(rows)}")
    run_call_counts = {run: sum(int(r["run"]) == run for r in msm_rows) for run in range(1, 6)}
    if run_call_counts != {run: 8 for run in range(1, 6)}:
        raise ValueError(f"Batch {batch_id}: expected 8 MSM rows per run; got {run_call_counts}")
    call_ids = [int(r["call_id"]) for r in msm_rows]
    if len(set(call_ids)) != 40 or set(call_ids) != set(range(1, 41)):
        raise ValueError(f"Batch {batch_id}: call IDs are not exactly 1..40")
    observed_msm_threads = {int(r["threads"]) for r in msm_rows}
    if observed_msm_threads != {expected_threads}:
        raise ValueError(f"Batch {batch_id}: unexpected thread counts in MSM CSV: {observed_msm_threads}")
    if any(not r.get("submit_elapsed_ms") for r in msm_rows):
        raise ValueError(f"Batch {batch_id}: missing submit_elapsed_ms on one or more MSM rows")

    # Check stage closure against each run's body timer, using tolerance to allow
    # millisecond values rounded to three decimals in the raw log format.
    closure_diffs: list[float] = []
    stage_non_body = STAGE_FIELDS[:-1]
    for row in stage_rows:
        total = sum(float(row[field]) for field in stage_non_body)
        closure_diffs.append(total - float(row["create_proof_body_ms"]))
    max_closure = max(abs(value) for value in closure_diffs)
    if max_closure > 0.01:
        raise ValueError(f"Batch {batch_id}: stage timers fail closure (max abs difference {max_closure:.6f} ms)")

    stderr_match = re.search(
        r"(?m)^- Prover stderr / source instrumentation records: experiments/raw/logs/([^\r\n]+)",
        report,
    )
    if not stderr_match:
        raise ValueError(f"Batch {batch_id}: metadata has no prover stderr path")
    stderr_path = root / "experiments" / "raw" / "logs" / stderr_match.group(1).strip()
    if not stderr_path.is_file():
        raise FileNotFoundError(f"Batch {batch_id}: referenced stderr log is missing: {stderr_path}")
    stderr = stderr_path.read_text(encoding="utf-8-sig", errors="replace")
    log_counts = {
        "msm_profile_records": len(re.findall(r"(?m)^BELLMAN_MSM_PROFILE ", stderr)),
        "submit_profile_records": len(re.findall(r"(?m)^BELLMAN_MSM_SUBMIT_PROFILE ", stderr)),
        "stage_profile_records": len(re.findall(r"(?m)^G16_STAGE_PROFILE ", stderr)),
        "worker_fallback_records": len(re.findall(r"(?m)^BELLMAN_WORKER_FALLBACK ", stderr)),
        "long_submit_over_100ms": sum(float(r["submit_elapsed_ms"]) > 100.0 for r in msm_rows),
        "long_task_delay_over_100ms": sum(float(r["task_start_delay_ms"]) > 100.0 for r in msm_rows),
    }
    if (log_counts["msm_profile_records"], log_counts["submit_profile_records"], log_counts["stage_profile_records"]) != (40, 40, 5):
        raise ValueError(f"Batch {batch_id}: source log record counts are incomplete: {log_counts}")

    identity = {key: parse_report_value(report, key) for key in CORE_IDENTITY_KEYS}
    return {
        "batch_id": batch_id,
        "threads": expected_threads,
        "report": report,
        "meta_path": meta_path,
        "prover_path": shared_prover_path,
        "stage_path": stage_path,
        "msm_path": msm_path,
        "summary_path": summary_path,
        "stderr_path": stderr_path,
        "prover_rows": prover_rows,
        "stage_rows": stage_rows,
        "msm_rows": msm_rows,
        "summary_rows": summary_rows,
        "identity": identity,
        "log_counts": log_counts,
        "max_stage_closure_ms": max_closure,
        "prove_median_ms": median(prover_rows, "prove_ms"),
        "body_median_ms": median(stage_rows, "create_proof_body_ms"),
    }


def safe_tag(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Output tag may contain only letters, numbers, underscores, and hyphens.")
    return value


def build_stage_comparison(single: dict[str, Any], parallel: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [
        ("outer_prove_ms", "Outer Prove", single["prover_rows"], parallel["prover_rows"], "prove_ms"),
    ]
    # Stage rows include body timer; all source fields are summarized independently.
    rows: list[dict[str, Any]] = []
    metrics = [("outer_prove_ms", "Outer Prove", single["prover_rows"], parallel["prover_rows"], "prove_ms")]
    for field in STAGE_FIELDS:
        metrics.append((field, STAGE_LABELS[field], single["stage_rows"], parallel["stage_rows"], field))
    for key, label, srows, prows, field in metrics:
        s_med = median(srows, field)
        p_med = median(prows, field)
        ratio = speedup(s_med, p_med)
        reduction = pct_reduction(s_med, p_med)
        rows.append({
            "metric": key,
            "label": label,
            "single_batch_id": single["batch_id"],
            "single_threads": single["threads"],
            "single_runs": len(srows),
            "single_median_ms": round(s_med, 6),
            "parallel_batch_id": parallel["batch_id"],
            "parallel_threads": parallel["threads"],
            "parallel_runs": len(prows),
            "parallel_median_ms": round(p_med, 6),
            "single_over_parallel_speedup": round(ratio, 6) if ratio is not None else "",
            "parallel_time_reduction_pct": round(reduction, 4) if reduction is not None else "",
            "single_min_ms": round(min(float(r[field]) for r in srows), 6),
            "single_max_ms": round(max(float(r[field]) for r in srows), 6),
            "parallel_min_ms": round(min(float(r[field]) for r in prows), 6),
            "parallel_max_ms": round(max(float(r[field]) for r in prows), 6),
        })
    return rows


def build_msm_comparison(single: dict[str, Any], parallel: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query in QUERY_ORDER:
        srows = [r for r in single["msm_rows"] if r["query"] == query]
        prows = [r for r in parallel["msm_rows"] if r["query"] == query]
        se = median(srows, "elapsed_ms")
        pe = median(prows, "elapsed_ms")
        sd = median(srows, "task_start_delay_ms")
        pd = median(prows, "task_start_delay_ms")
        ss = median(srows, "submit_elapsed_ms")
        ps = median(prows, "submit_elapsed_ms")
        rows.append({
            "query": query,
            "group": srows[0].get("group", ""),
            "exponent_count": int(srows[0]["exponent_count"]),
            "single_threads": single["threads"],
            "single_runs": len(srows),
            "single_elapsed_median_ms": round(se, 6),
            "single_elapsed_min_ms": round(min(float(r["elapsed_ms"]) for r in srows), 6),
            "single_elapsed_max_ms": round(max(float(r["elapsed_ms"]) for r in srows), 6),
            "parallel_threads": parallel["threads"],
            "parallel_runs": len(prows),
            "parallel_elapsed_median_ms": round(pe, 6),
            "parallel_elapsed_min_ms": round(min(float(r["elapsed_ms"]) for r in prows), 6),
            "parallel_elapsed_max_ms": round(max(float(r["elapsed_ms"]) for r in prows), 6),
            "single_over_parallel_elapsed_speedup": round(speedup(se, pe), 6) if speedup(se, pe) is not None else "",
            "parallel_elapsed_reduction_pct": round(pct_reduction(se, pe), 4) if pct_reduction(se, pe) is not None else "",
            "single_task_start_delay_median_ms": round(sd, 6),
            "parallel_task_start_delay_median_ms": round(pd, 6),
            "single_submit_median_ms": round(ss, 6),
            "parallel_submit_median_ms": round(ps, 6),
        })
    return rows


def plot_stage_speedups(stage_rows: list[dict[str, Any]], path: Path, title_tag: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("matplotlib is required for charts; run: python -m pip install matplotlib") from exc
    filtered = [r for r in stage_rows if r["metric"] != "worker_vk_setup_ms" and r["single_over_parallel_speedup"] not in ("", None)]
    filtered.sort(key=lambda r: float(r["single_over_parallel_speedup"]))
    values = [float(r["single_over_parallel_speedup"]) for r in filtered]
    labels = [r["label"] for r in filtered]
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    bars = ax.barh(labels, values)
    ax.axvline(1.0, linestyle="--", linewidth=1.2, label="No change (1×)")
    ax.set_xscale("log")
    ax.set_xlabel("Single-thread median ÷ 20-thread median (log scale)")
    ax.set_title(f"Sapling Spend: Stage Speedup ({title_tag})")
    ax.grid(True, axis="x", which="both", alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    for bar, val in zip(bars, values):
        ax.text(val * 1.05 if val > 0 else 0, bar.get_y() + bar.get_height() / 2, f"{val:.2f}×", va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_msm_elapsed(msm_rows: list[dict[str, Any]], path: Path, title_tag: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("matplotlib is required for charts; run: python -m pip install matplotlib") from exc
    labels = [f"{r['query']} (n={r['exponent_count']:,})" for r in msm_rows]
    y = list(range(len(msm_rows)))
    height = 0.36
    single_vals = [float(r["single_elapsed_median_ms"]) for r in msm_rows]
    parallel_vals = [float(r["parallel_elapsed_median_ms"]) for r in msm_rows]
    fig, ax = plt.subplots(figsize=(11.0, 6.5))
    ax.barh([v - height / 2 for v in y], single_vals, height=height, label="1 thread")
    ax.barh([v + height / 2 for v in y], parallel_vals, height=height, label="20 threads")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("Per-call elapsed median (ms, log scale)")
    ax.set_title(f"Sapling Spend: MSM Call Timing ({title_tag})")
    ax.grid(True, axis="x", which="both", alpha=0.3)
    ax.legend(loc="lower right")
    fig.text(0.01, 0.01, "Per-call intervals may overlap under parallel execution; do not sum them as wall-clock stages.", fontsize=8)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_task_start_delays(msm_rows: list[dict[str, Any]], path: Path, title_tag: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("matplotlib is required for charts; run: python -m pip install matplotlib") from exc
    labels = [r["query"] for r in msm_rows]
    y = list(range(len(msm_rows)))
    height = 0.36
    single_vals = [max(float(r["single_task_start_delay_median_ms"]), 0.001) for r in msm_rows]
    parallel_vals = [max(float(r["parallel_task_start_delay_median_ms"]), 0.001) for r in msm_rows]
    fig, ax = plt.subplots(figsize=(10.5, 6.1))
    ax.barh([v - height / 2 for v in y], single_vals, height=height, label="1 thread")
    ax.barh([v + height / 2 for v in y], parallel_vals, height=height, label="20 threads")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("Median delay between submission and task start (ms, log scale)")
    ax.set_title(f"Sapling Spend: MSM Task-Start Delay ({title_tag})")
    ax.grid(True, axis="x", which="both", alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]), help="Repository root (defaults to parent of scripts/)")
    parser.add_argument("--single-batch", default=DEFAULT_SINGLE_BATCH)
    parser.add_argument("--parallel-batch", default=DEFAULT_PARALLEL_BATCH)
    parser.add_argument("--single-threads", type=int, default=DEFAULT_SINGLE_THREADS)
    parser.add_argument("--parallel-threads", type=int, default=DEFAULT_PARALLEL_THREADS)
    parser.add_argument("--output-tag", default=None, help="Optional output suffix; defaults to <single>_vs_<parallel>")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    tag = safe_tag(args.output_tag or f"{args.single_batch}_vs_{args.parallel_batch}")
    if args.single_batch == args.parallel_batch:
        raise ValueError("The two batch IDs must differ.")
    single = load_profile(root, args.single_batch, args.single_threads)
    parallel = load_profile(root, args.parallel_batch, args.parallel_threads)

    stage_csv_rows = build_stage_comparison(single, parallel)
    msm_csv_rows = build_msm_comparison(single, parallel)
    table_dir = root / "results" / "tables"
    figure_dir = root / "results" / "figures"
    metadata_dir = root / "experiments" / "metadata"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    stage_out = table_dir / f"sapling_spend_thread_profile_comparison_{tag}.csv"
    msm_out = table_dir / f"sapling_spend_msm_call_comparison_{tag}.csv"
    stage_fig = figure_dir / f"sapling_spend_stage_speedup_{tag}.png"
    msm_fig = figure_dir / f"sapling_spend_msm_elapsed_{tag}.png"
    delay_fig = figure_dir / f"sapling_spend_task_start_delay_{tag}.png"
    report_out = metadata_dir / f"sapling_spend_thread_profile_comparison_{tag}.md"

    write_csv(stage_out, stage_csv_rows, list(stage_csv_rows[0].keys()))
    write_csv(msm_out, msm_csv_rows, list(msm_csv_rows[0].keys()))
    plot_stage_speedups(stage_csv_rows, stage_fig, tag)
    plot_msm_elapsed(msm_csv_rows, msm_fig, tag)
    plot_task_start_delays(msm_csv_rows, delay_fig, tag)

    overall_speed = speedup(single["prove_median_ms"], parallel["prove_median_ms"])
    outer_reduction = pct_reduction(single["prove_median_ms"], parallel["prove_median_ms"])
    body_speed = speedup(single["body_median_ms"], parallel["body_median_ms"])
    core_match = all(single["identity"].get(k) == parallel["identity"].get(k) and single["identity"].get(k) for k in CORE_IDENTITY_KEYS)

    def metric_line(key: str) -> str:
        item = next(r for r in stage_csv_rows if r["metric"] == key)
        return (
            f"| {item['label']} | {item['single_median_ms']:.3f} | {item['parallel_median_ms']:.3f} | "
            f"{item['single_over_parallel_speedup']:.2f}× | {item['parallel_time_reduction_pct']:.2f}% |"
        )

    metric_keys = [
        "outer_prove_ms",
        "circuit_synthesis_constraints_ms",
        "qap_fft_h_exponent_prep_ms",
        "h_query_access_dispatch_ms",
        "assignment_query_prep_dispatch_ms",
        "proof_scalar_terms_ms",
        "wait_and_assembly_ms",
        "create_proof_body_ms",
    ]
    stage_table = "\n".join(metric_line(k) for k in metric_keys)
    msm_lines = []
    for r in msm_csv_rows:
        msm_lines.append(
            f"| {r['query']} | {r['single_elapsed_median_ms']:.3f} | {r['parallel_elapsed_median_ms']:.3f} | "
            f"{r['single_over_parallel_elapsed_speedup']:.2f}× | "
            f"{r['single_task_start_delay_median_ms']:.3f} | {r['parallel_task_start_delay_median_ms']:.3f} | "
            f"{r['single_submit_median_ms']:.3f} | {r['parallel_submit_median_ms']:.3f} |"
        )
    msm_table = "\n".join(msm_lines)

    core_list = "\n".join(
        f"- `{key}`: {'MATCH' if single['identity'].get(key) == parallel['identity'].get(key) and single['identity'].get(key) else 'MISMATCH / MISSING'}"
        for key in CORE_IDENTITY_KEYS
    )
    source_files = [
        single["prover_path"], single["stage_path"], single["msm_path"], single["summary_path"], single["meta_path"], single["stderr_path"],
        parallel["stage_path"], parallel["msm_path"], parallel["summary_path"], parallel["meta_path"], parallel["stderr_path"],
    ]
    unique_files: list[Path] = []
    seen = set()
    for p in source_files:
        p = p.resolve()
        if p not in seen:
            seen.add(p)
            unique_files.append(p)
    hashes = "\n".join(f"| `{p.relative_to(root).as_posix()}` | `{sha256(p)}` |" for p in unique_files)

    single_counts = single["log_counts"]
    parallel_counts = parallel["log_counts"]
    # The runner script changed to accept --Threads between these runs. The
    # profiler dependencies / circuit binary / manifest are compared separately.
    generated_at_utc = datetime.now(timezone.utc).isoformat()
    report_text = f"""# Sapling Spend Thread-Profile Comparison

- Single-thread batch: `{single['batch_id']}` (`{single['threads']}` thread(s))
- Parallel batch: `{parallel['batch_id']}` (`{parallel['threads']}` threads)
- Input runs: 5 per batch; all ten proofs verified; Release build
- Generated by: `scripts/compare_spend_thread_profiles.py`
- Comparison report generated at UTC: `{generated_at_utc}`

## Main result

- Outer Prove median, single-thread: **{single['prove_median_ms']:.3f} ms**
- Outer Prove median, {parallel['threads']}-thread: **{parallel['prove_median_ms']:.3f} ms**
- Overall speedup: **{overall_speed:.2f}×**
- Outer Prove median reduction: **{outer_reduction:.2f}%**
- `create_proof_body_ms` speedup: **{body_speed:.2f}×**

## Provenance and validation

- Single-thread rows: 5/5; verified: 5/5; Stage / MSM / summary rows: 5 / 40 / 5
- Parallel rows: 5/5; verified: 5/5; Stage / MSM / summary rows: 5 / 40 / 5
- Single-thread raw stderr counts: MSM {single_counts['msm_profile_records']}, submit {single_counts['submit_profile_records']}, stage {single_counts['stage_profile_records']}, Worker fallback {single_counts['worker_fallback_records']}
- Parallel raw stderr counts: MSM {parallel_counts['msm_profile_records']}, submit {parallel_counts['submit_profile_records']}, stage {parallel_counts['stage_profile_records']}, Worker fallback {parallel_counts['worker_fallback_records']}
- Calls with `submit_elapsed_ms > 100 ms`: single-thread {single_counts['long_submit_over_100ms']}, parallel {parallel_counts['long_submit_over_100ms']}
- Calls with `task_start_delay_ms > 100 ms`: single-thread {single_counts['long_task_delay_over_100ms']}, parallel {parallel_counts['long_task_delay_over_100ms']}
- Maximum stage-closure absolute difference: single-thread {single['max_stage_closure_ms']:.3f} ms; parallel {parallel['max_stage_closure_ms']:.3f} ms (threshold 0.01 ms)
- Core instrumented source and parameter identities:
{core_list}

The runner script itself differs between batches because the 20-thread batch used the version that parameterizes the thread count. The identity check above covers the parameter hash, Bellman MSM implementation, Groth16 prover implementation, proof-smoke binary source, Cargo manifest, and Sapling dependency commit.

## Stage / wall-clock timing comparison

Times are medians over five runs. A positive reduction means the 20-thread median is lower; a negative reduction means it is higher.

| Metric | 1-thread median (ms) | {parallel['threads']}-thread median (ms) | Single / parallel | Time reduction |
|---|---:|---:|---:|---:|
{stage_table}

## MSM timing comparison

Per-query `elapsed_ms` is a task interval. In multi-thread execution, different intervals overlap. The ratio of single-thread median to parallel median is a per-call comparison, not a speedup claim for the entire proof.

| Query | 1-thread elapsed median (ms) | {parallel['threads']}-thread elapsed median (ms) | Per-call ratio | 1-thread start-delay median (ms) | {parallel['threads']}-thread start-delay median (ms) | 1-thread submit median (ms) | {parallel['threads']}-thread submit median (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
{msm_table}

## Interpretation and limitations

1. Outer Prove is a wall-clock measure; the two runs show a strong thread-scaling signal for this Sapling Spend workload.
2. In the single-thread batch, five `BELLMAN_WORKER_FALLBACK` records coincide with long `submit_elapsed_ms` records for B-G1 auxiliary MSM. The parallel batch has zero fallback records and zero submit intervals above 100 ms. This is strong evidence of an association between the single-thread fallback path and main-thread blocking in this workload, but the thread count also changes computation parallelism; these two batches alone do not isolate the fallback mechanism as the sole cause of the total speedup.
3. `submit_elapsed_ms`, `task_start_delay_ms`, and `elapsed_ms` are different measurement intervals and are not mutually exclusive costs. Do not add them together.
4. The sum of MSM `elapsed_ms` can exceed `create_proof_body_ms` under parallel execution because task intervals overlap. It is not a wall-clock decomposition.
5. There are five measured runs per setting on one machine. Treat medians and ranges as diagnostic results, not as universal performance guarantees.
6. No algorithm was changed in these two batches. This comparison does not claim a cryptographic algorithm optimization.

## Input file SHA-256 fingerprints

These are hashes of the exact input files read by this generator at report-generation time. The shared prover CSV may include batches appended after an earlier batch's metadata was created.

| Input file | SHA-256 |
|---|---|
{hashes}

## Generated artifacts

- Table: `{stage_out.relative_to(root).as_posix()}`
- Per-query table: `{msm_out.relative_to(root).as_posix()}`
- Stage speedup chart: `{stage_fig.relative_to(root).as_posix()}`
- MSM elapsed chart: `{msm_fig.relative_to(root).as_posix()}`
- Task-start-delay chart: `{delay_fig.relative_to(root).as_posix()}`

Raw experimental inputs were read only and were not modified by this script.
"""
    report_out.write_text(report_text, encoding="utf-8")

    print("=== Spend thread-profile comparison complete ===")
    print(f"Single-thread batch: {single['batch_id']} (verified 5/5)")
    print(f"Parallel batch: {parallel['batch_id']} (verified 5/5)")
    print(f"Core instrumented source identity match: {core_match}")
    print(f"Outer Prove medians: {single['prove_median_ms']:.3f} ms vs {parallel['prove_median_ms']:.3f} ms")
    print(f"Overall speedup: {overall_speed:.2f}x; time reduction: {outer_reduction:.2f}%")
    print("Generated derived artifacts:")
    for p in [stage_out, msm_out, stage_fig, msm_fig, delay_fig, report_out]:
        print(f"  {p.relative_to(root).as_posix()}")
    print("No raw observations were generated or modified.")
    if not core_match:
        print("WARNING: one or more core source identities differ or are missing; treat comparisons with extra caution.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
