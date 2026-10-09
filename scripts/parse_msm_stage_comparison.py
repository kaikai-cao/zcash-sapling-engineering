
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "experiments" / "raw" / "logs"
RAW_DIR = ROOT / "experiments" / "raw" / "csv"
TABLE_DIR = ROOT / "results" / "tables"
FIGURE_DIR = ROOT / "results" / "figures"

QUERIES = [
    "H", "L", "A_inputs", "A_aux",
    "B_G1_inputs", "B_G1_aux",
    "B_G2_inputs", "B_G2_aux",
]

LOG_FILES = [
    ("1", "sapling_output_msm_stages_1threads.log"),
    ("20", "sapling_output_msm_parallel_wall_20threads.log"),
]

STAGE_RE = re.compile(
    r"BELLMAN_MSM_STAGE_PROFILE\s+"
    r"call_id=(\d+)\s+"
    r"chunks=(\d+)\s+"
    r"exponent_chunking_ms=([\d.]+)\s+"
    r"bucket_alloc_sum_ms=([\d.]+)\s+"
    r"bucket_alloc_max_chunk_ms=([\d.]+)\s+"
    r"bucket_fill_sum_ms=([\d.]+)\s+"
    r"bucket_fill_max_chunk_ms=([\d.]+)\s+"
    r"bucket_sum_sum_ms=([\d.]+)\s+"
    r"bucket_sum_max_chunk_ms=([\d.]+)"
    r"(?:\s+parallel_chunks_wall_ms=([\d.]+)"
    r"\s+part_fold_ms=([\d.]+))?"
    r"\s*inner_elapsed_ms=([\d.]+)"
)

MSM_RE = re.compile(
    r"BELLMAN_MSM_PROFILE\s+"
    r"call_id=(\d+)\s+"
    r"exponent_count=(\d+)\s+"
    r"density_map_size=(None|Some\(\d+\))\s+"
    r"window=(\d+)\s+"
    r"elapsed_ms=([\d.]+)"
)

PROOF_RE = re.compile(
    r"run=(\d+),\s*prove_ms=([\d.]+),\s*"
    r"verify_ms=([\d.]+),\s*proof_bytes=(\d+),\s*"
    r"verified=(true|false)"
)

STAGE_FIELDS = [
    "exponent_chunking_ms",
    "bucket_alloc_sum_ms",
    "bucket_alloc_max_chunk_ms",
    "bucket_fill_sum_ms",
    "bucket_fill_max_chunk_ms",
    "bucket_sum_sum_ms",
    "bucket_sum_max_chunk_ms",
    "parallel_chunks_wall_ms",
    "part_fold_ms",
    "inner_elapsed_ms",
    "call_elapsed_ms",
]


def read_existing(path):
    if not path.exists():
        return []

    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))


def save_preserving_history(path, rows, batch_ids):
    """替换本次处理的批次，并保留之前的批次。"""
    if not rows:
        return

    old = read_existing(path)
    old = [
        row for row in old
        if row.get("batch_id") not in batch_ids
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(old)
        writer.writerows(rows)


def parse_log(threads, filename):
    path = LOG_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"找不到日志文件：{path}"
        )

    batch_id = str(path.stat().st_mtime_ns)
    lines = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines()

    stages = {}
    msm_metadata = {}
    proofs = []

    for line in lines:
        match = STAGE_RE.search(line)
        if match:
            groups = match.groups()

            call_id = int(groups[0])
            stages[call_id] = {
                "batch_id": batch_id,
                "threads": threads,
                "call_id": call_id,
                "run": (call_id - 1) // 8 + 1,
                "query": QUERIES[(call_id - 1) % 8],
                "chunks": int(groups[1]),
                "exponent_chunking_ms": float(groups[2]),
                "bucket_alloc_sum_ms": float(groups[3]),
                "bucket_alloc_max_chunk_ms": float(groups[4]),
                "bucket_fill_sum_ms": float(groups[5]),
                "bucket_fill_max_chunk_ms": float(groups[6]),
                "bucket_sum_sum_ms": float(groups[7]),
                "bucket_sum_max_chunk_ms": float(groups[8]),
                "parallel_chunks_wall_ms": (
                    float(groups[9])
                    if groups[9] is not None else ""
                ),
                "part_fold_ms": (
                    float(groups[10])
                    if groups[10] is not None else ""
                ),
                "inner_elapsed_ms": float(groups[11]),
            }

        match = MSM_RE.search(line)
        if match:
            call, count, density, window, elapsed = (
                match.groups()
            )
            msm_metadata[int(call)] = {
                "exponent_count": int(count),
                "density_map_size": density,
                "window": int(window),
                "call_elapsed_ms": float(elapsed),
            }

        match = PROOF_RE.search(line)
        if match:
            run, prove, verify, size, verified = (
                match.groups()
            )
            proofs.append({
                "batch_id": batch_id,
                "threads": threads,
                "run": int(run),
                "prove_ms": float(prove),
                "verify_ms": float(verify),
                "proof_bytes": int(size),
                "verified": verified == "true",
            })

    expected = set(range(1, 41))

    if set(stages) != expected:
        raise ValueError(
            f"{filename}: 阶段计时编号不完整，"
            f"已读到 {len(stages)} 条。"
        )

    if set(msm_metadata) != expected:
        raise ValueError(
            f"{filename}: MSM 元数据编号不完整。"
        )

    if len(proofs) != 5 or not all(
        row["verified"] for row in proofs
    ):
        raise ValueError(
            f"{filename}: 证明运行次数或验证结果异常。"
        )

    rows = []

    for call_id in sorted(stages):
        rows.append({
            **stages[call_id],
            **msm_metadata[call_id],
        })

    return batch_id, rows, proofs


def summarize(values):
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "stddev": (
            statistics.stdev(values)
            if len(values) > 1 else 0.0
        ),
        "min": min(values),
        "max": max(values),
    }


def main():
    all_rows = []
    all_proofs = []
    batch_ids = set()

    for threads, filename in LOG_FILES:
        batch_id, rows, proofs = parse_log(
            threads, filename
        )
        batch_ids.add(batch_id)
        all_rows.extend(rows)
        all_proofs.extend(proofs)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / "sapling_output_msm_stage_calls.csv"

    save_preserving_history(
        raw_path,
        all_rows,
        batch_ids,
    )

    # 计算每种查询在两种线程配置下的统计量。
    summary_rows = []

    for threads in ("1", "20"):
        for query in QUERIES:
            group = [
                row for row in all_rows
                if row["threads"] == threads
                and row["query"] == query
            ]

            row = {
                "batch_id": group[0]["batch_id"],
                "threads": threads,
                "query": query,
                "samples": len(group),
                "exponent_count": group[0]["exponent_count"],
                "window": group[0]["window"],
            }

            for metric in STAGE_FIELDS:
                values = [
                    float(item[metric])
                    for item in group
                    if item[metric] != ""
                ]

                if not values:
                    row[f"{metric}_median_ms"] = ""
                    continue

                stats = summarize(values)

                row[f"{metric}_median_ms"] = (
                    f"{stats['median']:.3f}"
                )

            summary_rows.append(row)

    summary_path = (
        TABLE_DIR / "sapling_output_msm_stage_comparison.csv"
    )

    save_preserving_history(
        summary_path,
        summary_rows,
        batch_ids,
    )

    # 汇总完整证明生成耗时。
    proof_summary = []

    for threads in ("1", "20"):
        group = [
            row for row in all_proofs
            if row["threads"] == threads
        ]

        prove = summarize([
            row["prove_ms"] for row in group
        ])
        verify = summarize([
            row["verify_ms"] for row in group
        ])

        proof_summary.append({
            "batch_id": group[0]["batch_id"],
            "threads": threads,
            "samples": len(group),
            "prove_median_ms": f"{prove['median']:.3f}",
            "prove_mean_ms": f"{prove['mean']:.3f}",
            "prove_stddev_ms": f"{prove['stddev']:.3f}",
            "verify_median_ms": f"{verify['median']:.3f}",
            "proof_bytes": ";".join(
                str(x) for x in sorted({
                    row["proof_bytes"] for row in group
                })
            ),
            "all_verified": all(
                row["verified"] for row in group
            ),
        })

    proof_path = (
        TABLE_DIR / "sapling_output_msm_stage_proof_comparison.csv"
    )

    save_preserving_history(
        proof_path,
        proof_summary,
        batch_ids,
    )

    # 图一：整个 MSM 内部耗时。
    medians = defaultdict(dict)

    for row in summary_rows:
        medians[row["threads"]][row["query"]] = float(
            row["inner_elapsed_ms_median_ms"]
    )

    x = list(range(len(QUERIES)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(11, 6))

    ax.bar(
        [i - width / 2 for i in x],
        [medians["1"][q] for q in QUERIES],
        width,
        label="1 thread",
    )
    ax.bar(
        [i + width / 2 for i in x],
        [medians["20"][q] for q in QUERIES],
        width,
        label="20 threads",
    )

    ax.set_xticks(x, QUERIES, rotation=25)
    ax.set_ylabel("MSM elapsed time (ms, log scale)")
    ax.set_yscale("log")
    ax.set_title("MSM Internal Time by Query and Thread Count")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()

    figure1 = (
        FIGURE_DIR / "sapling_output_msm_inner_thread_comparison.png"
    )
    fig.savefig(figure1, dpi=160)
    plt.close(fig)

    # 图二：最慢分块中的桶填充与桶内累加。
    fig, ax = plt.subplots(figsize=(11, 6))

    series = [
        ("1", "bucket_fill_max_chunk_ms", "1 thread: bucket fill"),
        ("1", "bucket_sum_max_chunk_ms", "1 thread: bucket sum"),
        ("20", "bucket_fill_max_chunk_ms", "20 threads: bucket fill"),
        ("20", "bucket_sum_max_chunk_ms", "20 threads: bucket sum"),
    ]

    for threads, metric, label in series:
        rows = [
            row for row in summary_rows
            if row["threads"] == threads
        ]
        rows_by_query = {
            row["query"]: row for row in rows
        }

        ax.plot(
            range(len(QUERIES)),
            [
                float(
                    rows_by_query[q][f"{metric}_median_ms"]
                )
                for q in QUERIES
            ],
            marker="o",
            label=label,
        )

    ax.set_xticks(range(len(QUERIES)), QUERIES, rotation=25)
    ax.set_ylabel("Maximum chunk time (ms, log scale)")
    ax.set_yscale("log")
    ax.set_title("Bucket Fill vs Bucket Summation")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    figure2 = (
        FIGURE_DIR / "sapling_output_msm_bucket_phase_comparison.png"
    )
    fig.savefig(figure2, dpi=160)
    plt.close(fig)

    print(f"Raw MSM stages: {raw_path}")
    print(f"Stage summary: {summary_path}")
    print(f"Proof summary: {proof_path}")
    print(f"Internal MSM chart: {figure1}")
    print(f"Bucket phase chart: {figure2}")

    print("\nProof generation medians:")
    for row in proof_summary:
        print(
            f"{row['threads']} thread(s): "
            f"{row['prove_median_ms']} ms, "
            f"verified={row['all_verified']}"
        )


if __name__ == "__main__":
    main()