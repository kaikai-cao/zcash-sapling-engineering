#!/usr/bin/env python3
"""Rebuild three Sapling Spend plots from versioned CSV data.

Run at repository root:
    python scripts/plot_spend_bottleneck_figures.py

Requires matplotlib: python -m pip install matplotlib

The thread plot reads the committed raw 30-run CSV. Stage/MSM measurements below
are transcribed from the five-run diagnostic output supplied for batch
spend_worker_fallback_20261011_194743. On first run, the script writes these
observations to experiments/raw/csv/*.csv; later runs read those CSV files
without overwriting them. Commit the generated CSV files with this script.
No proof is generated, and no optimization is performed.
"""

from pathlib import Path
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
STAGE_ROWS = [
    [1, 153.334, 0.001, 379.312, 0.144, 2332.175, 1.526, 591.827, 3458.320],
    [2, 99.776, 0.003, 378.304, 0.032, 2337.731, 1.497, 593.872, 3411.215],
    [3, 102.013, 0.003, 379.353, 0.035, 2329.957, 1.493, 591.043, 3403.897],
    [4, 99.910, 0.003, 378.491, 0.030, 2339.077, 1.502, 591.445, 3410.459],
    [5, 100.876, 0.003, 383.138, 0.039, 2392.394, 1.509, 619.420, 3497.379],
]
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
# Five runs of (call_id, task_start_delay_ms, elapsed_ms), in query order.
MSM_RUNS = [
    [
        (1, 0.015, 1442.063),
        (2, 1439.439, 398.915),
        (3, 1838.327, 0.954),
        (4, 1839.291, 276.306),
        (5, 2115.640, 0.760),
        (6, 2116.420, 212.930),
        (7, 0.050, 2.200),
        (8, 2.280, 590.730),
    ],
    [
        (9, 0.010, 1446.624),
        (10, 1443.961, 397.200),
        (11, 1841.182, 0.958),
        (12, 1842.153, 280.715),
        (13, 2122.900, 0.770),
        (14, 2123.680, 211.220),
        (15, 0.170, 2.180),
        (16, 2.350, 592.660),
    ],
    [
        (17, 0.014, 1444.423),
        (18, 1441.402, 398.582),
        (19, 1839.944, 0.948),
        (20, 1840.906, 275.139),
        (21, 2116.080, 0.880),
        (22, 2116.980, 209.750),
        (23, 0.090, 2.140),
        (24, 2.270, 589.920),
    ],
    [
        (25, 0.015, 1448.739),
        (26, 1446.030, 399.348),
        (27, 1845.370, 0.940),
        (28, 1846.310, 278.323),
        (29, 2124.660, 0.770),
        (30, 2125.450, 210.700),
        (31, 0.000, 2.240),
        (32, 2.270, 590.340),
    ],
    [
        (33, 0.016, 1472.114),
        (34, 1469.483, 411.375),
        (35, 1880.879, 0.950),
        (36, 1881.840, 288.732),
        (37, 2170.600, 0.830),
        (38, 2171.450, 218.070),
        (39, 0.050, 2.200),
        (40, 2.290, 618.280),
    ],
]


def write_if_missing(path, headers, rows):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print("Created input CSV:", path.relative_to(ROOT))


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


def create_transcribed_csvs():
    write_if_missing(STAGE_CSV, ["run"] + STAGE_FIELDS, STAGE_ROWS)
    msm_rows = []
    for run, calls in enumerate(MSM_RUNS, 1):
        for idx, (call_id, delay, elapsed) in enumerate(calls):
            query, group, count, window = QUERIES[idx]
            msm_rows.append(
                [
                    run,
                    call_id,
                    query,
                    group,
                    count,
                    window,
                    f"{delay:.3f}",
                    f"{elapsed:.3f}",
                ]
            )
    write_if_missing(
        MSM_CSV,
        [
            "run",
            "call_id",
            "query",
            "group",
            "exponent_count",
            "window",
            "task_start_delay_ms",
            "elapsed_ms",
        ],
        msm_rows,
    )


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
        TABLES / "sapling_spend_thread_scaling_summary_20261011.csv",
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
        TABLES / "sapling_spend_stage_profile_summary_20261011.csv",
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
        TABLES / "sapling_spend_msm_profile_summary_20261011.csv",
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
    out = FIGURES / "sapling_spend_thread_scaling.png"
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
    out = FIGURES / "sapling_spend_msm_breakdown.png"
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
    out = FIGURES / "sapling_spend_stage_breakdown.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def main():
    if not THREAD_CSV.exists():
        raise FileNotFoundError(f"Thread raw CSV not found: {THREAD_CSV}")
    for folder in (RAW, TABLES, FIGURES):
        folder.mkdir(parents=True, exist_ok=True)
    create_transcribed_csvs()
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
        TABLES / "sapling_spend_thread_scaling_summary_20261011.csv",
        TABLES / "sapling_spend_stage_profile_summary_20261011.csv",
        TABLES / "sapling_spend_msm_profile_summary_20261011.csv",
    ):
        print(" ", p.relative_to(ROOT))
    print("No proving workload was executed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
