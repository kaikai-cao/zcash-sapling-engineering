#!/usr/bin/env python3
"""Rebuild three Sapling Spend plots from versioned CSV data.

Run at repository root:
    python scripts/plot_spend_bottleneck_figures.py

Requires matplotlib: python -m pip install matplotlib

This script is a data-processing and plotting tool only. It must read the
versioned raw CSV inputs and must never manufacture raw measurements from
hardcoded/transcribed values. If the raw stage/MSM CSVs or their source logs
are missing, preserve that limitation and rerun the experiment with archived
stdout/stderr rather than recreating observations here. A new batch can be
selected with --stage-csv, --msm-csv and --output-tag. No proof is generated.
"""

from pathlib import Path
import argparse
import re
import csv
import statistics
import sys

try:
    import matplotlib.pyplot as plt
except ImportError as exc:
    raise SystemExit(
        "matplotlib missing; run: python -m pip install matplotlib"
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiments/raw/csv"
TABLES = ROOT / "results/tables"
FIGURES = ROOT / "results/figures"
OUTPUT_TAG = None


def table_path(stem):
    suffix = OUTPUT_TAG if OUTPUT_TAG else "20261011"
    return TABLES / f"{stem}_{suffix}.csv"


def figure_path(stem):
    return FIGURES / (f"{stem}_{OUTPUT_TAG}.png" if OUTPUT_TAG else f"{stem}.png")
THREAD_CSV = RAW / "sapling_spend_thread_scaling_20261011_202051.csv"
STAGE_CSV = RAW / "sapling_spend_stage_profile_20261011.csv"
MSM_CSV = RAW / "sapling_spend_msm_call_profile_20261011.csv"

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
# run, circuit synthesis, worker/VK, QAP/FFT/H, H access, assignment/query/dispatch,
# proof scalar terms, wait/assembly, full create_proof_body (all milliseconds)
# Stage timing is loaded from the selected existing raw CSV; never transcribe data here.
# query, group, exponent count, window
QUERIES = [
    ("H_query_G1", "G1", 131071, 12),
    ("L_query_G1", "G1", 98638, 12),
    ("A_input_G1", "G1", 8, 3),
    ("A_aux_G1", "G1", 98638, 12),
    ("B_G1_input", "G1", 8, 3),
    ("B_G1_aux", "G1", 98638, 12),
    ("B_G2_input", "G2", 8, 3),
    ("B_G2_aux", "G2", 98638, 12),
]

def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required CSV missing: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(row, key):
    try:
        return float(row[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid {key!r} in row {row}") from exc


def write_summary(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def summarize_threads():
    rows = read_csv(THREAD_CSV)
    if len(rows) != 30:
        raise ValueError(f"Expected 30 thread rows, found {len(rows)}")
    groups = {}
    for r in rows:
        t = int(r["threads"])
        groups.setdefault(t, []).append(r)
        if r["verified"].lower() != "true":
            raise ValueError(f"Unverified proof: {r}")
    expected = [1, 2, 4, 8, 16, 20]
    for t in expected:
        if len(groups.get(t, [])) != 5:
            raise ValueError(f"Expected five runs at {t} threads")
    baseline = statistics.median(num(r, "prove_ms") for r in groups[1])
    out = []
    summary_rows = []
    for t in expected:
        prove = [num(r, "prove_ms") for r in groups[t]]
        verify = [num(r, "verify_ms") for r in groups[t]]
        med = statistics.median(prove)
        row = {
            "threads": t,
            "runs": len(prove),
            "median": med,
            "min": min(prove),
            "max": max(prove),
            "verify_median": statistics.median(verify),
            "speedup": baseline / med,
        }
        out.append(row)
        summary_rows.append(
            [
                t,
                5,
                f"{med:.3f}",
                f"{min(prove):.3f}",
                f"{max(prove):.3f}",
                f"{row['verify_median']:.3f}",
                f"{row['speedup']:.3f}",
                "True",
            ]
        )
    write_summary(
        table_path("sapling_spend_thread_scaling_summary"),
        [
            "threads",
            "runs",
            "median_prove_ms",
            "min_prove_ms",
            "max_prove_ms",
            "median_verify_ms",
            "speedup_vs_1",
            "verified_all",
        ],
        summary_rows,
    )
    return out


def summarize_stages():
    rows = read_csv(STAGE_CSV)
    if len(rows) != 5:
        raise ValueError(f"Expected five stage rows, found {len(rows)}")
    med = {
        field: statistics.median(num(r, field) for r in rows) for field in STAGE_FIELDS
    }
    write_summary(
        table_path("sapling_spend_stage_profile_summary"),
        ["stage", "median_ms"],
        [[field, f"{med[field]:.3f}"] for field in STAGE_FIELDS],
    )
    return med


def summarize_msm():
    rows = read_csv(MSM_CSV)
    if len(rows) != 40:
        raise ValueError(f"Expected 40 MSM rows, found {len(rows)}")
    stats = []
    for query, group, count, window in QUERIES:
        records = [r for r in rows if r["query"] == query]
        if len(records) != 5:
            raise ValueError(f"Expected five records for {query}")
        vals = [num(r, "elapsed_ms") for r in records]
        stats.append(
            {
                "query": query,
                "group": group,
                "count": count,
                "window": window,
                "median": statistics.median(vals),
                "min": min(vals),
                "max": max(vals),
            }
        )
    write_summary(
        table_path("sapling_spend_msm_profile_summary"),
        [
            "query",
            "group",
            "exponent_count",
            "window",
            "median_elapsed_ms",
            "min_elapsed_ms",
            "max_elapsed_ms",
        ],
        [
            [
                r["query"],
                r["group"],
                r["count"],
                r["window"],
                f"{r['median']:.3f}",
                f"{r['min']:.3f}",
                f"{r['max']:.3f}",
            ]
            for r in stats
        ],
    )
    return stats


def plot_threads(data):
    data = sorted(data, key=lambda r: r["threads"])
    x = [r["threads"] for r in data]
    y = [r["median"] for r in data]
    err = [
        [r["median"] - r["min"] for r in data],
        [r["max"] - r["median"] for r in data],
    ]
    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    ax.errorbar(x, y, yerr=err, marker="o", capsize=4, linewidth=1.8)
    for r in data:
        ax.annotate(
            f"{r['speedup']:.2f}×",
            (r["threads"], r["median"]),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=9,
        )
    ax.set(
        title="Sapling Spend Prove: Thread Scaling",
        xlabel="Rayon thread count",
        ylabel="Prove median (ms)",
    )
    ax.set_xticks(x)
    ax.grid(True, axis="y", alpha=0.3)
    fig.text(
        0.01,
        0.01,
        "Five runs per setting; whiskers show observed min–max, not confidence intervals. The 8-thread group varies substantially.",
        fontsize=8,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    out = figure_path("sapling_spend_thread_scaling")
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_msm(data):
    data = sorted(data, key=lambda r: r["median"])
    labels = [f"{r['query']} ({r['group']}, n={r['count']:,})" for r in data]
    med = [r["median"] for r in data]
    xerr = [
        [r["median"] - r["min"] for r in data],
        [r["max"] - r["median"] for r in data],
    ]
    fig, ax = plt.subplots(figsize=(10, 6.0))
    ax.errorbar(med, labels, xerr=xerr, fmt="o", capsize=4, linewidth=1.5)
    ax.set_xscale("log")
    ax.set_xlim(min(med) * 0.45, max(r["max"] for r in data) * 2)
    ax.set(
        title="Sapling Spend: MSM Call Timing",
        xlabel="Per-call elapsed (ms, logarithmic scale)",
    )
    ax.grid(True, axis="x", which="both", alpha=0.3)
    for i, v in enumerate(med):
        ax.annotate(
            f"{v:.3f} ms", (v, i), xytext=(5, 4), textcoords="offset points", fontsize=8
        )
    fig.text(
        0.01,
        0.01,
        "Single-thread diagnostic batch; points show five-run medians and whiskers show min–max. Call elapsed is not a universal exclusive wall-clock breakdown.",
        fontsize=8,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    out = figure_path("sapling_spend_msm_breakdown")
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_stages(stage_medians):
    # Tiny (< 5 ms) timer intervals remain in the CSV summary but are omitted here for readability.
    chart = [
        ("circuit_synthesis_constraints_ms", "Circuit synthesis / constraints"),
        ("qap_fft_h_exponent_prep_ms", "QAP / FFT / H preparation"),
        (
            "assignment_query_prep_dispatch_ms",
            "Assignment / query prep / MSM dispatch path",
        ),
        ("wait_and_assembly_ms", "Wait for MSM / proof assembly"),
    ]
    labels = [label for _, label in chart][::-1]
    vals = [stage_medians[k] for k, _ in chart][::-1]
    body = stage_medians["create_proof_body_ms"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.barh(labels, vals)
    ax.axvline(
        body,
        linestyle="--",
        linewidth=1.6,
        label=f"create_proof_body median = {body:.1f} ms",
    )
    ax.set_xlim(0, body * 1.25)
    ax.set(
        title="Sapling Spend: Main-Thread Stage Timers",
        xlabel="Stage timer median (ms)",
    )
    ax.grid(True, axis="x", alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    for bar, v in zip(bars, vals):
        ax.text(
            v + body * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.3f} ms",
            va="center",
            fontsize=8,
        )
    fig.text(
        0.01,
        0.01,
        "Five-run single-thread batch. Sub-5-ms intervals omitted for readability. The body timer is a reference line, not an extra stage; fallback affects main-thread accounting.",
        fontsize=8,
    )
    fig.tight_layout(rect=[0, 0.08, 1, 1])
    out = figure_path("sapling_spend_stage_breakdown")
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def main():
    global THREAD_CSV, STAGE_CSV, MSM_CSV, OUTPUT_TAG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread-csv", default=str(THREAD_CSV), help="Path to the existing thread-scaling raw CSV")
    parser.add_argument("--stage-csv", default=str(STAGE_CSV), help="Path to the existing stage raw CSV")
    parser.add_argument("--msm-csv", default=str(MSM_CSV), help="Path to the existing MSM-call raw CSV")
    parser.add_argument("--output-tag", default=None, help="Optional tag for new summary/figure files (e.g. batch ID); prevents overwriting old outputs")
    args = parser.parse_args()

    def resolve_input(value):
        path = Path(value)
        return path.resolve() if path.is_absolute() else (ROOT / path).resolve()

    THREAD_CSV = resolve_input(args.thread_csv)
    STAGE_CSV = resolve_input(args.stage_csv)
    MSM_CSV = resolve_input(args.msm_csv)
    OUTPUT_TAG = args.output_tag
    if OUTPUT_TAG and not re.fullmatch(r"[A-Za-z0-9_-]+", OUTPUT_TAG):
        raise ValueError("--output-tag may contain only letters, numbers, '_' and '-'.")

    missing = [str(path) for path in (THREAD_CSV, STAGE_CSV, MSM_CSV) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Required raw input CSV(s) missing; no raw data were synthesized:\n" + "\n".join(missing))
    for folder in (RAW, TABLES, FIGURES):
        folder.mkdir(parents=True, exist_ok=True)
    threads = summarize_threads()
    stages = summarize_stages()
    msm = summarize_msm()
    outputs = [plot_threads(threads), plot_msm(msm), plot_stages(stages)]
    print("Thread scaling results: (threads, median_ms, speedup)")
    for r in threads:
        print(f"  {r['threads']:>2}: {r['median']:.3f} ms, {r['speedup']:.3f}x")
    print("Generated figures:")
    for p in outputs:
        print(" ", p.relative_to(ROOT))
    print("Updated summary tables:")
    for p in (
        table_path("sapling_spend_thread_scaling_summary"),
        table_path("sapling_spend_stage_profile_summary"),
        table_path("sapling_spend_msm_profile_summary"),
    ):
        print(" ", p.relative_to(ROOT))
    print("No proving workload was executed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
