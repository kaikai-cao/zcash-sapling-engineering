
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]

LOGS = {
    "1": ROOT / "experiments/raw/logs/sapling_output_worker_task_start_1threads.log",
    "2": ROOT / "experiments/raw/logs/sapling_output_worker_task_start_2threads.log",
    "4": ROOT / "experiments/raw/logs/sapling_output_worker_task_start_4threads.log",
    "8": ROOT / "experiments/raw/logs/sapling_output_worker_task_start_8threads.log",
    "20": ROOT / "experiments/raw/logs/sapling_output_worker_task_start_20threads.log",
}

RAW_DIR = ROOT / "experiments/raw/csv"
TABLE_DIR = ROOT / "results/tables"
FIGURE_DIR = ROOT / "results/figures"

QUERIES = [
    "H",
    "L",
    "A_inputs",
    "A_aux",
    "B_G1_inputs",
    "B_G1_aux",
    "B_G2_inputs",
    "B_G2_aux",
]

BEGIN_RE = re.compile(
    r"BELLMAN_MSM_SUBMIT_BEGIN call_id=(\d+) exponent_count=(\d+)"
)
RETURN_RE = re.compile(
    r"BELLMAN_MSM_SUBMIT_RETURN call_id=(\d+) submit_elapsed_ms=([\d.]+)"
)
TASK_RE = re.compile(
    r"BELLMAN_MSM_TASK_START call_id=(\d+) delay_ms=([\d.]+)"
)
PROFILE_RE = re.compile(
    r"BELLMAN_MSM_PROFILE call_id=(\d+) exponent_count=(\d+).*?"
    r"window=(\d+) elapsed_ms=([\d.]+)"
)
PROOF_RE = re.compile(
    r"run=(\d+), prove_ms=([\d.]+), verify_ms=([\d.]+), "
    r"proof_bytes=(\d+), verified=(true|false)"
)
FALLBACK_RE = re.compile(r"BELLMAN_WORKER_SYNC_FALLBACK")


def new_call(call_id):
    run = (call_id - 1) // len(QUERIES) + 1
    query = QUERIES[(call_id - 1) % len(QUERIES)]

    return {
        "threads": "",
        "run": run,
        "query": query,
        "call_id": call_id,
        "exponent_count": "",
        "window": "",
        "submit_elapsed_ms": "",
        "task_start_delay_ms": "",
        "msm_elapsed_ms": "",
        "sync_fallback": False,
    }


def parse_log(path, threads):
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    calls = {}
    proof_rows = []
    current_submit_call = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = BEGIN_RE.search(line)
        if match:
            call_id = int(match.group(1))
            row = calls.setdefault(call_id, new_call(call_id))
            row["threads"] = threads
            row["exponent_count"] = int(match.group(2))
            current_submit_call = call_id
            continue

        if FALLBACK_RE.search(line):
            if current_submit_call is not None:
                calls[current_submit_call]["sync_fallback"] = True
            continue

        match = RETURN_RE.search(line)
        if match:
            call_id = int(match.group(1))
            row = calls.setdefault(call_id, new_call(call_id))
            row["threads"] = threads
            row["submit_elapsed_ms"] = float(match.group(2))

            if current_submit_call == call_id:
                current_submit_call = None
            continue

        match = TASK_RE.search(line)
        if match:
            call_id = int(match.group(1))
            row = calls.setdefault(call_id, new_call(call_id))
            row["threads"] = threads
            row["task_start_delay_ms"] = float(match.group(2))
            continue

        match = PROFILE_RE.search(line)
        if match:
            call_id = int(match.group(1))
            row = calls.setdefault(call_id, new_call(call_id))
            row["threads"] = threads
            row["exponent_count"] = int(match.group(2))
            row["window"] = int(match.group(3))
            row["msm_elapsed_ms"] = float(match.group(4))
            continue

        match = PROOF_RE.search(line)
        if match:
            proof_rows.append({
                "threads": threads,
                "run": int(match.group(1)),
                "prove_ms": float(match.group(2)),
                "verify_ms": float(match.group(3)),
                "proof_bytes": int(match.group(4)),
                "verified": match.group(5) == "true",
            })

    rows = [calls[k] for k in sorted(calls)]
    return rows, proof_rows


def median_field(rows, field):
    values = [
        float(row[field])
        for row in rows
        if row[field] != ""
    ]
    return statistics.median(values) if values else ""


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    all_calls = []
    all_proofs = []

    for threads, path in LOGS.items():
        calls, proofs = parse_log(path, threads)
        all_calls.extend(calls)
        all_proofs.extend(proofs)

    if not all_calls:
        raise RuntimeError("No MSM call records were found.")

    # Keep raw per-call records for later reanalysis.
    raw_path = RAW_DIR / "sapling_output_worker_task_start_calls.csv"
    raw_fields = [
        "threads",
        "run",
        "query",
        "call_id",
        "exponent_count",
        "window",
        "submit_elapsed_ms",
        "task_start_delay_ms",
        "msm_elapsed_ms",
        "sync_fallback",
    ]
    write_csv(raw_path, all_calls, raw_fields)

    # Summarize five runs for each query and thread configuration.
    summary_rows = []
    for threads in ("1", "2", "4", "8", "20"):
        for query in QUERIES:
            group = [
                row for row in all_calls
                if row["threads"] == threads and row["query"] == query
            ]
            if not group:
                continue

            summary_rows.append({
                "threads": threads,
                "query": query,
                "samples": len(group),
                "median_task_start_delay_ms": median_field(
                    group, "task_start_delay_ms"
                ),
                "median_submit_elapsed_ms": median_field(
                    group, "submit_elapsed_ms"
                ),
                "median_msm_elapsed_ms": median_field(
                    group, "msm_elapsed_ms"
                ),
                "fallback_count": sum(
                    bool(row["sync_fallback"]) for row in group
                ),
            })

    summary_path = TABLE_DIR / "sapling_output_worker_task_start_summary.csv"
    summary_fields = [
        "threads",
        "query",
        "samples",
        "median_task_start_delay_ms",
        "median_submit_elapsed_ms",
        "median_msm_elapsed_ms",
        "fallback_count",
    ]
    write_csv(summary_path, summary_rows, summary_fields)

    # Summarize the whole-proof measurements separately.
    proof_summary = []
    for threads in ("1", "2", "4", "8", "20"):
        group = [r for r in all_proofs if r["threads"] == threads]
        if not group:
            continue

        proof_summary.append({
            "threads": threads,
            "runs": len(group),
            "median_prove_ms": f"{statistics.median(r['prove_ms'] for r in group):.3f}",
            "median_verify_ms": f"{statistics.median(r['verify_ms'] for r in group):.3f}",
            "proof_bytes": group[0]["proof_bytes"],
            "all_verified": all(r["verified"] for r in group),
        })

    proof_path = TABLE_DIR / "sapling_output_worker_proof_summary.csv"
    write_csv(
        proof_path,
        proof_summary,
        [
            "threads",
            "runs",
            "median_prove_ms",
            "median_verify_ms",
            "proof_bytes",
            "all_verified",
        ],
    )

    # Plot task-start delay; logarithmic scale reveals both small and large delays.
    plot_data = {
        threads: [
            float(next(
                row["median_task_start_delay_ms"]
                for row in summary_rows
                if row["threads"] == threads and row["query"] == query
            ))
            for query in QUERIES
        ]
        for threads in ("1", "2", "4", "8", "20")
    }

    x = list(range(len(QUERIES)))
    fig, ax = plt.subplots(figsize=(11, 6))

    ax.plot(x, plot_data["1"], marker="o", label="1 thread")
    ax.plot(x, plot_data["20"], marker="s", label="20 threads")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(QUERIES, rotation=30, ha="right")
    ax.set_ylabel("Median task-start delay (ms, log scale)")
    ax.set_xlabel("MSM query")
    ax.set_title("Sapling MSM Task-Start Delay by Thread Configuration")
    ax.grid(True, which="both", linestyle="--", alpha=0.35)
    ax.legend()
    fig.tight_layout()

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure_path = FIGURE_DIR / "sapling_output_worker_task_start_delay.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)

    print(f"Raw MSM calls: {raw_path}")
    print(f"MSM summary:   {summary_path}")
    print(f"Proof summary: {proof_path}")
    print(f"Figure:        {figure_path}")

    print("\nProof generation medians:")
    for row in proof_summary:
        print(
            f"{row['threads']} thread(s): "
            f"{row['median_prove_ms']} ms, "
            f"verified={row['all_verified']}"
        )


if __name__ == "__main__":
    main()