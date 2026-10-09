import csv
import re
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "experiments" / "raw" / "logs"
TABLE_DIR = ROOT / "results" / "tables"
FIGURE_DIR = ROOT / "results" / "figures"

QUERY_NAMES = [
    "H",
    "L",
    "A_inputs",
    "A_aux",
    "B_G1_inputs",
    "B_G1_aux",
    "B_G2_inputs",
    "B_G2_aux",
]

MSM_PATTERN = re.compile(
    r"BELLMAN_MSM_PROFILE\s+"
    r"call_id=(\d+)\s+"
    r"exponent_count=(\d+)\s+"
    r"density_map_size=(None|Some\(\d+\))\s+"
    r"window=(\d+)\s+"
    r"elapsed_ms=([\d.]+)"
)

PROOF_PATTERN = re.compile(
    r"run=(\d+),\s*prove_ms=([\d.]+),\s*"
    r"verify_ms=([\d.]+),\s*proof_bytes=(\d+),\s*"
    r"verified=(true|false)"
)


def parse_log(filename, threads):
    path = LOG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"找不到日志：{path}")

    msm_rows = []
    proof_rows = []

    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = MSM_PATTERN.search(line)
        if match:
            call_id, count, density, window, elapsed = match.groups()
            call_id = int(call_id)

            msm_rows.append(
                {
                    "threads": threads,
                    "run": (call_id - 1) // 8 + 1,
                    "call_id": call_id,
                    "query": QUERY_NAMES[(call_id - 1) % 8],
                    "exponent_count": int(count),
                    "density_map_size": density,
                    "window": int(window),
                    "elapsed_ms": float(elapsed),
                }
            )

        match = PROOF_PATTERN.search(line)
        if match:
            run, prove, verify, size, valid = match.groups()
            proof_rows.append(
                {
                    "threads": threads,
                    "run": int(run),
                    "prove_ms": float(prove),
                    "verify_ms": float(verify),
                    "proof_bytes": int(size),
                    "verified": valid.lower() == "true",
                }
            )

    ids = [row["call_id"] for row in msm_rows]
    expected = set(range(1, len(ids) + 1))

    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError(f"{filename} 的 MSM 编号有重复或缺失。")

    if len(ids) == 0 or len(ids) != len(proof_rows) * 8:
        raise ValueError(f"{filename} 的 MSM 记录与证明运行次数不匹配。")

    if not all(row["verified"] for row in proof_rows):
        raise ValueError(f"{filename} 存在验证失败的证明。")

    return msm_rows, proof_rows


def summary(values):
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "stddev": (statistics.stdev(values) if len(values) > 1 else 0),
        "min": min(values),
        "max": max(values),
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    logs = [
        ("sapling_output_msm_profile_sizes_1threads.log", "1"),
        ("sapling_output_msm_profile_sizes_20threads.log", "20"),
    ]

    all_msm = []
    all_proofs = []

    for filename, thread_count in logs:
        msm, proofs = parse_log(filename, thread_count)
        all_msm.extend(msm)
        all_proofs.extend(proofs)

    medians = {}
    summary_rows = []

    for threads in ("1", "20"):
        medians[threads] = {}

        for query in QUERY_NAMES:
            rows = [
                row
                for row in all_msm
                if row["threads"] == threads and row["query"] == query
            ]
            values = [row["elapsed_ms"] for row in rows]
            stats = summary(values)
            medians[threads][query] = stats["median"]

            summary_rows.append(
                {
                    "threads": threads,
                    "query": query,
                    "samples": len(values),
                    "exponent_count": rows[0]["exponent_count"],
                    "density_map_size": rows[0]["density_map_size"],
                    "window": rows[0]["window"],
                    "median_ms": f"{stats['median']:.3f}",
                    "mean_ms": f"{stats['mean']:.3f}",
                    "stddev_ms": f"{stats['stddev']:.3f}",
                    "min_ms": f"{stats['min']:.3f}",
                    "max_ms": f"{stats['max']:.3f}",
                }
            )

    msm_csv = TABLE_DIR / "sapling_output_msm_thread_comparison.csv"
    write_csv(msm_csv, summary_rows)

    proof_rows = []
    for threads in ("1", "20"):
        rows = [row for row in all_proofs if row["threads"] == threads]
        prove = summary([row["prove_ms"] for row in rows])
        verify = summary([row["verify_ms"] for row in rows])

        proof_rows.append(
            {
                "threads": threads,
                "samples": len(rows),
                "prove_median_ms": f"{prove['median']:.3f}",
                "prove_mean_ms": f"{prove['mean']:.3f}",
                "prove_stddev_ms": f"{prove['stddev']:.3f}",
                "verify_median_ms": f"{verify['median']:.3f}",
                "proof_bytes": ";".join(
                    map(str, sorted({row["proof_bytes"] for row in rows}))
                ),
                "all_verified": all(row["verified"] for row in rows),
            }
        )

    proof_csv = TABLE_DIR / "sapling_output_prove_thread_comparison.csv"
    write_csv(proof_csv, proof_rows)

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    x = list(range(len(QUERY_NAMES)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(
        [i - width / 2 for i in x],
        [medians["1"][q] for q in QUERY_NAMES],
        width,
        label="1 thread",
    )
    ax.bar(
        [i + width / 2 for i in x],
        [medians["20"][q] for q in QUERY_NAMES],
        width,
        label="20 threads",
    )

    ax.set_xticks(x, QUERY_NAMES, rotation=25)
    ax.set_ylabel("Median MSM task time (ms, log scale)")
    ax.set_yscale("log")
    ax.set_title("Sapling Output: MSM Latency by Thread Count")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()

    figure = FIGURE_DIR / "sapling_output_msm_thread_comparison.png"
    fig.savefig(figure, dpi=160)
    plt.close(fig)

    prove_1 = float(proof_rows[0]["prove_median_ms"])
    prove_20 = float(proof_rows[1]["prove_median_ms"])

    print(f"MSM comparison CSV: {msm_csv}")
    print(f"Proof comparison CSV: {proof_csv}")
    print(f"Comparison chart: {figure}")
    print(f"1-thread proof median: {prove_1:.3f} ms")
    print(f"20-thread proof median: {prove_20:.3f} ms")
    print(f"End-to-end speedup: {prove_1 / prove_20:.2f}x")
    print("\nQuery medians:")

    for query in QUERY_NAMES:
        one = medians["1"][query]
        many = medians["20"][query]
        print(f"{query}: 1 thread={one:.3f} ms, " f"20 threads={many:.3f} ms")


if __name__ == "__main__":
    main()
