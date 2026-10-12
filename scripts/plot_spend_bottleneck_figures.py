#!/usr/bin/env python3
"""Rebuild three Sapling Spend plots from versioned CSV data.

Run at repository root:
    python scripts/plot_spend_bottleneck_figures.py

Requires matplotlib: python -m pip install matplotlib

This script processes existing raw CSV measurements and generates summary
tables and plots. It must never manufacture raw measurements from
hardcoded or transcribed values.

Historical raw CSV inputs are retained. Generated files receive an explicit
output tag, defaulting to a generation timestamp. The script refuses to
overwrite an existing output file.

A different input batch can be selected with --thread-csv, --stage-csv,
--msm-csv, and --output-tag. No proof is generated.
"""

from pathlib import Path
from datetime import datetime
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

# run, circuit synthesis, worker/VK, QAP/FFT/H, H access,
# assignment/query/dispatch, proof scalar terms, wait/assembly,
# full create_proof_body (all milliseconds).
# Stage timing is loaded from an existing raw CSV.
# Raw observations must never be transcribed or synthesized here.

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


def table_path(stem):
    """Return the tagged path for a generated summary table."""
    return TABLES / f"{stem}_{OUTPUT_TAG}.csv"


def figure_path(stem):
    """Return the tagged path for a generated figure."""
    return FIGURES / f"{stem}_{OUTPUT_TAG}.png"


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
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def summarize_threads():
    rows = read_csv(THREAD_CSV)

    if len(rows) != 30:
        raise ValueError(f"Expected 30 thread rows, found {len(rows)}")

    groups = {}

    for row in rows:
        threads = int(row["threads"])
        groups.setdefault(threads, []).append(row)

        if row["verified"].lower() != "true":
            raise ValueError(f"Unverified proof: {row}")

    expected_threads = [1, 2, 4, 8, 16, 20]

    for threads in expected_threads:
        if len(groups.get(threads, [])) != 5:
            raise ValueError(f"Expected five runs at {threads} threads")

    baseline = statistics.median(
        num(row, "prove_ms") for row in groups[1]
    )

    results = []
    summary_rows = []

    for threads in expected_threads:
        prove_times = [
            num(row, "prove_ms") for row in groups[threads]
        ]
        verify_times = [
            num(row, "verify_ms") for row in groups[threads]
        ]

        median_prove = statistics.median(prove_times)
        median_verify = statistics.median(verify_times)

        result = {
            "threads": threads,
            "runs": len(prove_times),
            "median": median_prove,
            "min": min(prove_times),
            "max": max(prove_times),
            "verify_median": median_verify,
            "speedup": baseline / median_prove,
        }

        results.append(result)

        summary_rows.append(
            [
                threads,
                5,
                f"{median_prove:.3f}",
                f"{min(prove_times):.3f}",
                f"{max(prove_times):.3f}",
                f"{median_verify:.3f}",
                f"{result['speedup']:.3f}",
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

    return results


def summarize_stages():
    rows = read_csv(STAGE_CSV)

    if len(rows) != 5:
        raise ValueError(f"Expected five stage rows, found {len(rows)}")

    medians = {
        field: statistics.median(num(row, field) for row in rows)
        for field in STAGE_FIELDS
    }

    write_summary(
        table_path("sapling_spend_stage_profile_summary"),
        ["stage", "median_ms"],
        [
            [field, f"{medians[field]:.3f}"]
            for field in STAGE_FIELDS
        ],
    )

    return medians


def summarize_msm():
    rows = read_csv(MSM_CSV)

    if len(rows) != 40:
        raise ValueError(f"Expected 40 MSM rows, found {len(rows)}")

    results = []

    for query, group, count, window in QUERIES:
        records = [
            row for row in rows if row["query"] == query
        ]

        if len(records) != 5:
            raise ValueError(
                f"Expected five records for {query}"
            )

        values = [
            num(row, "elapsed_ms") for row in records
        ]

        results.append(
            {
                "query": query,
                "group": group,
                "count": count,
                "window": window,
                "median": statistics.median(values),
                "min": min(values),
                "max": max(values),
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
                result["query"],
                result["group"],
                result["count"],
                result["window"],
                f"{result['median']:.3f}",
                f"{result['min']:.3f}",
                f"{result['max']:.3f}",
            ]
            for result in results
        ],
    )

    return results


def plot_threads(data):
    data = sorted(data, key=lambda row: row["threads"])

    x = [row["threads"] for row in data]
    y = [row["median"] for row in data]

    errors = [
        [row["median"] - row["min"] for row in data],
        [row["max"] - row["median"] for row in data],
    ]

    fig, ax = plt.subplots(figsize=(9.2, 5.6))

    ax.errorbar(
        x,
        y,
        yerr=errors,
        marker="o",
        capsize=4,
        linewidth=1.8,
    )

    for row in data:
        ax.annotate(
            f"{row['speedup']:.2f}×",
            (row["threads"], row["median"]),
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
        (
            "Five runs per setting; whiskers show observed min–max, "
            "not confidence intervals. The 8-thread group varies "
            "substantially."
        ),
        fontsize=8,
    )

    fig.tight_layout(rect=[0, 0.06, 1, 1])

    output = figure_path("sapling_spend_thread_scaling")
    fig.savefig(output, dpi=180)
    plt.close(fig)

    return output


def plot_msm(data):
    data = sorted(data, key=lambda row: row["median"])

    labels = [
        f"{row['query']} ({row['group']}, n={row['count']:,})"
        for row in data
    ]

    medians = [row["median"] for row in data]

    errors = [
        [
            row["median"] - row["min"]
            for row in data
        ],
        [
            row["max"] - row["median"]
            for row in data
        ],
    ]

    fig, ax = plt.subplots(figsize=(10, 6.0))

    ax.errorbar(
        medians,
        labels,
        xerr=errors,
        fmt="o",
        capsize=4,
        linewidth=1.5,
    )

    ax.set_xscale("log")
    ax.set_xlim(
        min(medians) * 0.45,
        max(row["max"] for row in data) * 2,
    )

    ax.set(
        title="Sapling Spend: MSM Call Timing",
        xlabel="Per-call elapsed (ms, logarithmic scale)",
    )

    ax.grid(True, axis="x", which="both", alpha=0.3)

    for index, value in enumerate(medians):
        ax.annotate(
            f"{value:.3f} ms",
            (value, index),
            xytext=(5, 4),
            textcoords="offset points",
            fontsize=8,
        )

    fig.text(
        0.01,
        0.01,
        (
            "Single-thread diagnostic batch; points show five-run "
            "medians and whiskers show min–max. Call elapsed is not "
            "a universal exclusive wall-clock breakdown."
        ),
        fontsize=8,
    )

    fig.tight_layout(rect=[0, 0.06, 1, 1])

    output = figure_path("sapling_spend_msm_breakdown")
    fig.savefig(output, dpi=180)
    plt.close(fig)

    return output


def plot_stages(stage_medians):
    # Tiny (< 5 ms) timer intervals remain in the CSV summary
    # but are omitted here for readability.
    chart = [
        (
            "circuit_synthesis_constraints_ms",
            "Circuit synthesis / constraints",
        ),
        (
            "qap_fft_h_exponent_prep_ms",
            "QAP / FFT / H preparation",
        ),
        (
            "assignment_query_prep_dispatch_ms",
            "Assignment / query prep / MSM dispatch path",
        ),
        (
            "wait_and_assembly_ms",
            "Wait for MSM / proof assembly",
        ),
    ]

    labels = [label for _, label in chart][::-1]
    values = [
        stage_medians[key] for key, _ in chart
    ][::-1]

    body = stage_medians["create_proof_body_ms"]

    fig, ax = plt.subplots(figsize=(10, 5.5))

    bars = ax.barh(labels, values)

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

    for bar, value in zip(bars, values):
        ax.text(
            value + body * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.3f} ms",
            va="center",
            fontsize=8,
        )

    fig.text(
        0.01,
        0.01,
        (
            "Five-run single-thread batch. Sub-5-ms intervals omitted "
            "for readability. The body timer is a reference line, "
            "not an extra stage; fallback affects main-thread accounting."
        ),
        fontsize=8,
    )

    fig.tight_layout(rect=[0, 0.08, 1, 1])

    output = figure_path("sapling_spend_stage_breakdown")
    fig.savefig(output, dpi=180)
    plt.close(fig)

    return output


def main():
    global THREAD_CSV, STAGE_CSV, MSM_CSV, OUTPUT_TAG

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--thread-csv",
        default=str(THREAD_CSV),
        help="Path to the existing thread-scaling raw CSV",
    )

    parser.add_argument(
        "--stage-csv",
        default=str(STAGE_CSV),
        help="Path to the existing stage raw CSV",
    )

    parser.add_argument(
        "--msm-csv",
        default=str(MSM_CSV),
        help="Path to the existing MSM-call raw CSV",
    )

    parser.add_argument(
        "--output-tag",
        default=None,
        help=(
            "Tag for generated summary/figure files; defaults "
            "to a generation timestamp."
        ),
    )

    args = parser.parse_args()

    def resolve_input(value):
        path = Path(value)

        if path.is_absolute():
            return path.resolve()

        return (ROOT / path).resolve()

    THREAD_CSV = resolve_input(args.thread_csv)
    STAGE_CSV = resolve_input(args.stage_csv)
    MSM_CSV = resolve_input(args.msm_csv)

    OUTPUT_TAG = args.output_tag or datetime.now().strftime(
        "generated_%Y%m%d_%H%M%S"
    )

    if not re.fullmatch(r"[A-Za-z0-9_-]+", OUTPUT_TAG):
        raise ValueError(
            "--output-tag may contain only letters, numbers, '_' and '-'."
        )

    # Validate inputs before creating any output.
    missing = [
        str(path)
        for path in (THREAD_CSV, STAGE_CSV, MSM_CSV)
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Required raw input CSV(s) missing; no raw data were synthesized:\n"
            + "\n".join(missing)
        )

    # Check all expected output paths before generating any table or figure.
    # This prevents accidental overwrites and avoids partial generation
    # when a user reuses an existing tag.
    expected_outputs = [
        table_path("sapling_spend_thread_scaling_summary"),
        table_path("sapling_spend_stage_profile_summary"),
        table_path("sapling_spend_msm_profile_summary"),
        figure_path("sapling_spend_thread_scaling"),
        figure_path("sapling_spend_msm_breakdown"),
        figure_path("sapling_spend_stage_breakdown"),
    ]

    existing_outputs = [
        path for path in expected_outputs if path.exists()
    ]

    if existing_outputs:
        paths = "\n".join(str(path) for path in existing_outputs)

        raise FileExistsError(
            "Refusing to overwrite existing generated outputs. "
            "Choose a new --output-tag:\n" + paths
        )

    for folder in (RAW, TABLES, FIGURES):
        folder.mkdir(parents=True, exist_ok=True)

    threads = summarize_threads()
    stages = summarize_stages()
    msm = summarize_msm()

    outputs = [
        plot_threads(threads),
        plot_msm(msm),
        plot_stages(stages),
    ]

    print("Thread scaling results: (threads, median_ms, speedup)")

    for result in threads:
        print(
            f"  {result['threads']:>2}: "
            f"{result['median']:.3f} ms, "
            f"{result['speedup']:.3f}x"
        )

    print("Generated figures:")

    for path in outputs:
        print(" ", path.relative_to(ROOT))

    print("Updated summary tables:")

    for path in (
        table_path("sapling_spend_thread_scaling_summary"),
        table_path("sapling_spend_stage_profile_summary"),
        table_path("sapling_spend_msm_profile_summary"),
    ):
        print(" ", path.relative_to(ROOT))

    print("Output tag:", OUTPUT_TAG)
    print("No proving workload was executed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise