import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

# ============================================================
# 1. 路径与实验配置
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

LOG_DIR = ROOT / "experiments" / "raw" / "logs"
RAW_DIR = ROOT / "experiments" / "raw" / "csv"
TABLE_DIR = ROOT / "results" / "tables"
FIGURE_DIR = ROOT / "results" / "figures"

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

# 使用固定的批次 ID，不依赖文件修改时间。
LOG_FILES = [
    (
        "1",
        "sapling_output_msm_stages_1threads.log",
        "sapling-output-stage-1threads-v1",
    ),
    (
        "20",
        "sapling_output_msm_parallel_wall_20threads.log",
        "sapling-output-stage-20threads-v1",
    ),
]

# 清理当前仓库中旧版脚本根据文件修改时间生成的批次 ID。
# 新结果会使用 LOG_FILES 中定义的稳定 ID。
LEGACY_BATCH_IDS = {
    "1791532793242413400",
    "1791533298926442700",
}


# ============================================================
# 2. 日志解析规则
# ============================================================

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


# ============================================================
# 3. CSV 工具
# ============================================================


def read_existing(path):
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def save_preserving_history(path, rows, batch_ids_to_replace):
    """
    用本次重新解析的结果替换指定批次，
    保留其他不相关的历史批次。
    """
    if not rows:
        raise ValueError(f"拒绝写入空数据：{path}")

    old_rows = read_existing(path)

    old_rows = [
        row for row in old_rows if row.get("batch_id") not in batch_ids_to_replace
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys())

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(old_rows)
        writer.writerows(rows)


def summarize(values):
    if not values:
        raise ValueError("无法对空数据计算统计量。")

    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "stddev": (statistics.stdev(values) if len(values) > 1 else 0.0),
        "min": min(values),
        "max": max(values),
    }


# ============================================================
# 4. 解析单份实验日志
# ============================================================


def parse_log(threads, filename, batch_id):
    path = LOG_DIR / filename

    if not path.is_file():
        raise FileNotFoundError(f"找不到日志文件：{path}")

    lines = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines()

    stages = {}
    msm_metadata = {}
    proofs = []

    for line in lines:
        # ---------- MSM 内部阶段 ----------
        match = STAGE_RE.search(line)

        if match:
            groups = match.groups()
            call_id = int(groups[0])

            if call_id in stages:
                raise ValueError(f"{filename}: 重复的阶段 call_id={call_id}")

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
                    float(groups[9]) if groups[9] is not None else ""
                ),
                "part_fold_ms": (float(groups[10]) if groups[10] is not None else ""),
                "inner_elapsed_ms": float(groups[11]),
            }

        # ---------- 完整 MSM 调用 ----------
        match = MSM_RE.search(line)

        if match:
            call, count, density, window, elapsed = match.groups()

            call_id = int(call)

            if call_id in msm_metadata:
                raise ValueError(f"{filename}: 重复的 MSM call_id={call_id}")

            msm_metadata[call_id] = {
                "exponent_count": int(count),
                "density_map_size": density,
                "window": int(window),
                "call_elapsed_ms": float(elapsed),
            }

        # ---------- Prove / Verify ----------
        match = PROOF_RE.search(line)

        if match:
            run, prove, verify, size, verified = match.groups()

            proofs.append(
                {
                    "batch_id": batch_id,
                    "threads": threads,
                    "run": int(run),
                    "prove_ms": float(prove),
                    "verify_ms": float(verify),
                    "proof_bytes": int(size),
                    "verified": verified == "true",
                }
            )

    # ---------- 完整性检查 ----------
    expected_call_ids = set(range(1, 41))

    if set(stages) != expected_call_ids:
        missing = sorted(expected_call_ids - set(stages))
        unexpected = sorted(set(stages) - expected_call_ids)

        raise ValueError(
            f"{filename}: 阶段计时编号异常；"
            f"实际记录 {len(stages)} 条，"
            f"缺失编号={missing}，异常编号={unexpected}"
        )

    if set(msm_metadata) != expected_call_ids:
        missing = sorted(expected_call_ids - set(msm_metadata))
        unexpected = sorted(set(msm_metadata) - expected_call_ids)

        raise ValueError(
            f"{filename}: MSM 元数据编号异常；"
            f"缺失编号={missing}，异常编号={unexpected}"
        )

    if len(proofs) != 5:
        raise ValueError(
            f"{filename}: 预期 5 次证明记录，" f"实际为 {len(proofs)} 次。"
        )

    proof_runs = [row["run"] for row in proofs]

    if sorted(proof_runs) != [1, 2, 3, 4, 5]:
        raise ValueError(f"{filename}: Prove 运行编号重复或不完整。")

    if not all(row["verified"] for row in proofs):
        raise ValueError(f"{filename}: 存在验证失败的证明，不生成正式派生结果。")

    # 合并阶段计时与 MSM 调用元数据。
    rows = []

    for call_id in sorted(stages):
        rows.append(
            {
                **stages[call_id],
                **msm_metadata[call_id],
            }
        )

    print(
        f"[CHECK PASS] batch={batch_id}, "
        f"threads={threads}, MSM calls={len(rows)}, "
        f"proofs={len(proofs)}, verified=5/5"
    )

    return batch_id, rows, proofs


# ============================================================
# 5. 主流程
# ============================================================


def main():
    all_rows = []
    all_proofs = []
    current_batch_ids = set()

    # ---------- 解析两份日志 ----------
    for threads, filename, stable_batch_id in LOG_FILES:
        batch_id, rows, proofs = parse_log(
            threads,
            filename,
            stable_batch_id,
        )

        current_batch_ids.add(batch_id)
        all_rows.extend(rows)
        all_proofs.extend(proofs)

    if len(current_batch_ids) != len(LOG_FILES):
        raise ValueError("配置中的批次 ID 必须唯一。")

    # 新 ID + 已确认的旧时间戳 ID。
    # 只替换这些批次，保留其他历史记录。
    batch_ids_to_replace = current_batch_ids | LEGACY_BATCH_IDS

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    # ========================================================
    # 5.1 输出逐调用阶段数据
    # ========================================================

    raw_path = RAW_DIR / "sapling_output_msm_stage_calls.csv"

    save_preserving_history(
        raw_path,
        all_rows,
        batch_ids_to_replace,
    )

    print(f"[OK] Raw stage calls: {raw_path}")

    # ========================================================
    # 5.2 输出按查询类型汇总的阶段数据
    # ========================================================

    summary_rows = []

    for threads, _, batch_id in LOG_FILES:
        for query in QUERIES:
            group = [
                row
                for row in all_rows
                if row["threads"] == threads and row["query"] == query
            ]

            if len(group) != 5:
                raise ValueError(
                    f"threads={threads}, query={query}: "
                    f"预期 5 条记录，实际 {len(group)} 条。"
                )

            row = {
                "batch_id": batch_id,
                "threads": threads,
                "query": query,
                "samples": len(group),
                "exponent_count": group[0]["exponent_count"],
                "window": group[0]["window"],
            }

            for metric in STAGE_FIELDS:
                values = [float(item[metric]) for item in group if item[metric] != ""]

                if not values:
                    row[f"{metric}_median_ms"] = ""
                    continue

                stats = summarize(values)

                row[f"{metric}_median_ms"] = f"{stats['median']:.3f}"

            summary_rows.append(row)

    summary_path = TABLE_DIR / "sapling_output_msm_stage_comparison.csv"

    save_preserving_history(
        summary_path,
        summary_rows,
        batch_ids_to_replace,
    )

    print(f"[OK] Stage summary: {summary_path}")

    # ========================================================
    # 5.3 输出完整证明耗时对照
    # ========================================================

    proof_summary = []

    for threads, _, batch_id in LOG_FILES:
        group = [row for row in all_proofs if row["threads"] == threads]

        if len(group) != 5:
            raise ValueError(
                f"threads={threads}: " f"预期 5 次证明，实际 {len(group)} 次。"
            )

        prove = summarize([row["prove_ms"] for row in group])

        verify = summarize([row["verify_ms"] for row in group])

        proof_summary.append(
            {
                "batch_id": batch_id,
                "threads": threads,
                "samples": len(group),
                "prove_median_ms": f"{prove['median']:.3f}",
                "prove_mean_ms": f"{prove['mean']:.3f}",
                "prove_stddev_ms": f"{prove['stddev']:.3f}",
                "verify_median_ms": f"{verify['median']:.3f}",
                "proof_bytes": ";".join(
                    str(value)
                    for value in sorted({row["proof_bytes"] for row in group})
                ),
                "all_verified": all(row["verified"] for row in group),
            }
        )

    proof_path = TABLE_DIR / "sapling_output_msm_stage_proof_comparison.csv"

    save_preserving_history(
        proof_path,
        proof_summary,
        batch_ids_to_replace,
    )

    print(f"[OK] Proof summary: {proof_path}")

    # ========================================================
    # 5.4 图一：按查询对比 MSM 内部 elapsed
    # ========================================================

    medians = defaultdict(dict)

    for row in summary_rows:
        value = row["inner_elapsed_ms_median_ms"]

        if value == "":
            raise ValueError(f"缺少 inner_elapsed_ms：{row}")

        medians[row["threads"]][row["query"]] = float(value)

    x = list(range(len(QUERIES)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(11, 6))

    ax.bar(
        [i - width / 2 for i in x],
        [medians["1"][query] for query in QUERIES],
        width,
        label="1 thread",
    )

    ax.bar(
        [i + width / 2 for i in x],
        [medians["20"][query] for query in QUERIES],
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

    figure1 = FIGURE_DIR / "sapling_output_msm_inner_thread_comparison.png"

    fig.savefig(figure1, dpi=160)
    plt.close(fig)

    print(f"[OK] Internal MSM chart: {figure1}")

    # ========================================================
    # 5.5 图二：Bucket fill 与 bucket sum 的分块耗时
    # ========================================================

    fig, ax = plt.subplots(figsize=(11, 6))

    series = [
        ("1", "bucket_fill_max_chunk_ms", "1 thread: bucket fill"),
        ("1", "bucket_sum_max_chunk_ms", "1 thread: bucket sum"),
        ("20", "bucket_fill_max_chunk_ms", "20 threads: bucket fill"),
        ("20", "bucket_sum_max_chunk_ms", "20 threads: bucket sum"),
    ]

    for threads, metric, label in series:
        rows_for_threads = [row for row in summary_rows if row["threads"] == threads]

        rows_by_query = {row["query"]: row for row in rows_for_threads}

        values = []

        for query in QUERIES:
            value = rows_by_query[query][f"{metric}_median_ms"]

            if value == "":
                raise ValueError(
                    f"缺少阶段数据：threads={threads}, "
                    f"query={query}, metric={metric}"
                )

            values.append(float(value))

        ax.plot(
            range(len(QUERIES)),
            values,
            marker="o",
            label=label,
        )

    ax.set_xticks(
        range(len(QUERIES)),
        QUERIES,
        rotation=25,
    )

    ax.set_ylabel("Maximum chunk time (ms, log scale)")
    ax.set_yscale("log")
    ax.set_title("Bucket Fill vs Bucket Summation")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    figure2 = FIGURE_DIR / "sapling_output_msm_bucket_phase_comparison.png"

    fig.savefig(figure2, dpi=160)
    plt.close(fig)

    print(f"[OK] Bucket phase chart: {figure2}")

    # ========================================================
    # 5.6 最终摘要
    # ========================================================

    print("\n=== Experiment summary ===")

    for row in proof_summary:
        print(
            f"batch={row['batch_id']}, "
            f"threads={row['threads']}, "
            f"samples={row['samples']}, "
            f"prove_median_ms={row['prove_median_ms']}, "
            f"verify_median_ms={row['verify_median_ms']}, "
            f"verified={row['all_verified']}"
        )

    print("\n[OK] Stage profiling data regenerated.")
    print("[OK] Legacy batch IDs replaced.")
    print("[OK] Original log files were not modified.")


if __name__ == "__main__":
    main()
