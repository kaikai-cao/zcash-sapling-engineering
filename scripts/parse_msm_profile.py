
import csv
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]

LOG = (
    ROOT
    / "experiments"
    / "raw"
    / "logs"
    / "sapling_output_msm_profile_sizes_20threads.log"
)

RAW_DIR = ROOT / "experiments" / "raw" / "csv"
TABLE_DIR = ROOT / "results" / "tables"
FIGURE_DIR = ROOT / "results" / "figures"

MSM_CSV = RAW_DIR / "sapling_output_msm_calls.csv"
STAGE_CSV = RAW_DIR / "sapling_output_internal_stages.csv"
SUMMARY_CSV = TABLE_DIR / "sapling_output_msm_summary.csv"

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

STAGE_PATTERN = re.compile(
    r"G16_PROFILE\s+"
    r"stage=(\S+)\s+"
    r"elapsed_ms=([\d.]+)"
)


def read_existing_rows(path):
    """读取已有 CSV；文件不存在时返回空列表。"""
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def save_batch(path, fieldnames, new_rows, batch_id):
    """
    保存新批次并保留历史批次。
    重复处理同一份日志时，替换该批次而不是重复追加。
    """
    old_rows = read_existing_rows(path)

    old_rows = [
        row
        for row in old_rows
        if row.get("batch_id") != batch_id
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(old_rows)
        writer.writerows(new_rows)


def check_call_ids(msm_rows):
    """校验 MSM 编号是否完整，不要求日志按编号顺序排列。"""
    call_ids = [
        int(row["call_id"])
        for row in msm_rows
    ]

    counts = Counter(call_ids)

    duplicates = sorted(
        call_id
        for call_id, count in counts.items()
        if count > 1
    )

    expected_ids = set(range(1, len(call_ids) + 1))
    actual_ids = set(call_ids)

    missing = sorted(expected_ids - actual_ids)
    unexpected = sorted(actual_ids - expected_ids)

    print(f"MSM 记录总数：{len(call_ids)}")
    print(f"重复编号：{duplicates}")
    print(f"缺失编号：{missing}")
    print(f"超出预期范围的编号：{unexpected}")

    if duplicates or missing or unexpected:
        raise ValueError(
            "MSM 编号校验失败，请检查日志内容。"
        )

    if len(call_ids) == 0:
        raise ValueError("没有找到 MSM 记录。")

    if len(call_ids) % len(QUERY_NAMES) != 0:
        raise ValueError(
            "MSM 记录数量不是每份证明 8 次调用的整数倍。"
        )


def parse_log():
    """从内部性能日志中解析 MSM 记录和 Groth16 阶段计时。"""
    if not LOG.exists():
        raise FileNotFoundError(
            f"找不到日志文件：{LOG}"
        )

    log_text = LOG.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )

    # 使用日志文件修改时间标识本批次。
    batch_id = str(LOG.stat().st_mtime_ns)

    thread_match = re.search(
        r"_(\d+)threads",
        LOG.name,
    )
    threads = (
        thread_match.group(1)
        if thread_match
        else "unknown"
    )

    msm_rows = []
    stage_rows = []
    current_run = 0

    for line in log_text.splitlines():
        stage_match = STAGE_PATTERN.search(line)

        if stage_match:
            stage, elapsed = stage_match.groups()

            if stage == "circuit_synthesis":
                current_run += 1

            if current_run > 0:
                stage_rows.append({
                    "batch_id": batch_id,
                    "run": current_run,
                    "stage": stage,
                    "elapsed_ms": float(elapsed),
                    "threads": threads,
                    "build_profile": "release",
                })

        msm_match = MSM_PATTERN.search(line)

        if msm_match:
            groups = msm_match.groups()

            call_id = int(groups[0])
            exponent_count = int(groups[1])
            density_map_size = groups[2]
            window = int(groups[3])
            elapsed = float(groups[4])

            # call_id 表示提交顺序，不是任务完成顺序。
            run = (
                (call_id - 1) // len(QUERY_NAMES)
            ) + 1

            query_index = (
                call_id - 1
            ) % len(QUERY_NAMES)

            query = QUERY_NAMES[query_index]

            msm_rows.append({
                "batch_id": batch_id,
                "run": run,
                "call_id": call_id,
                "query": query,
                "exponent_count": exponent_count,
                "density_map_size": density_map_size,
                "window": window,
                "elapsed_ms": elapsed,
                "threads": threads,
                "build_profile": "release",
            })

    check_call_ids(msm_rows)

    run_count = len({
        row["run"]
        for row in msm_rows
    })

    if len(msm_rows) != run_count * len(QUERY_NAMES):
        raise ValueError(
            "MSM 调用数量与证明运行次数不匹配。"
        )

    if not stage_rows:
        raise ValueError(
            "没有找到 G16_PROFILE 阶段计时记录。"
        )

    stage_run_count = len({
        row["run"]
        for row in stage_rows
    })

    if stage_run_count != run_count:
        raise ValueError(
            f"阶段计时运行数为 {stage_run_count}，"
            f"但 MSM 对应的运行数为 {run_count}。"
        )

    return batch_id, threads, msm_rows, stage_rows


def calculate_stats(values):
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "stddev": (
            statistics.stdev(values)
            if len(values) > 1
            else 0.0
        ),
        "min": min(values),
        "max": max(values),
    }


def save_raw_data(
    batch_id,
    threads,
    msm_rows,
    stage_rows,
):
    msm_fields = [
        "batch_id",
        "run",
        "call_id",
        "query",
        "exponent_count",
        "density_map_size",
        "window",
        "elapsed_ms",
        "threads",
        "build_profile",
    ]

    stage_fields = [
        "batch_id",
        "run",
        "stage",
        "elapsed_ms",
        "threads",
        "build_profile",
    ]

    save_batch(
        MSM_CSV,
        msm_fields,
        msm_rows,
        batch_id,
    )

    save_batch(
        STAGE_CSV,
        stage_fields,
        stage_rows,
        batch_id,
    )


def save_summary(batch_id, threads, msm_rows):
    grouped = defaultdict(list)

    for row in msm_rows:
        grouped[row["query"]].append(
            float(row["elapsed_ms"])
        )

    summary_rows = []

    for query in QUERY_NAMES:
        values = grouped[query]
        result = calculate_stats(values)

        # 保证缺少某一类查询时不会生成错误统计。
        if not values:
            raise ValueError(
                f"没有找到查询 {query} 的测量值。"
            )

        exponent_counts = {
            row["exponent_count"]
            for row in msm_rows
            if row["query"] == query
        }

        windows = {
            row["window"]
            for row in msm_rows
            if row["query"] == query
        }

        density_sizes = {
            row["density_map_size"]
            for row in msm_rows
            if row["query"] == query
        }

        summary_rows.append({
            "batch_id": batch_id,
            "threads": threads,
            "query": query,
            "samples": len(values),
            "exponent_count": ";".join(
                map(str, sorted(exponent_counts))
            ),
            "density_map_size": ";".join(
                sorted(density_sizes)
            ),
            "window": ";".join(
                map(str, sorted(windows))
            ),
            "median_ms": f"{result['median']:.3f}",
            "mean_ms": f"{result['mean']:.3f}",
            "stddev_ms": f"{result['stddev']:.3f}",
            "min_ms": f"{result['min']:.3f}",
            "max_ms": f"{result['max']:.3f}",
        })

    fields = list(summary_rows[0].keys())

    save_batch(
        SUMMARY_CSV,
        fields,
        summary_rows,
        batch_id,
    )

    return grouped


def plot_msm(grouped):
    FIGURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig, ax = plt.subplots(figsize=(11, 6))

    for index, query in enumerate(QUERY_NAMES):
        values = grouped[query]
        median = statistics.median(values)

        # 显示每次测量值，避免只看中位数掩盖波动。
        offsets = [
            (i - (len(values) - 1) / 2) * 0.045
            for i in range(len(values))
        ]

        ax.scatter(
            [
                index + offset
                for offset in offsets
            ],
            values,
            marker="o",
            zorder=3,
        )

        ax.hlines(
            median,
            index - 0.25,
            index + 0.25,
            linewidth=2,
        )

    ax.set_xticks(
        range(len(QUERY_NAMES)),
        QUERY_NAMES,
        rotation=25,
    )
    ax.set_ylabel("MSM task elapsed time (ms)")
    ax.set_title(
        "Sapling Output: MSM Task Latencies"
    )
    ax.set_yscale("log")
    ax.grid(
        axis="y",
        alpha=0.3,
    )

    fig.tight_layout()

    output = (
        FIGURE_DIR
        / "sapling_output_msm_by_query.png"
    )

    fig.savefig(
        output,
        dpi=160,
    )
    plt.close(fig)

    return output


def plot_stages(stage_rows):
    important_stages = [
        "circuit_synthesis",
        "qap_fft_quotient",
        "post_dispatch_wait_assembly",
    ]

    fig, ax = plt.subplots(figsize=(8, 5))

    for stage in important_stages:
        selected = [
            row
            for row in stage_rows
            if row["stage"] == stage
        ]

        selected.sort(
            key=lambda row: int(row["run"])
        )

        if not selected:
            continue

        ax.plot(
            [
                int(row["run"])
                for row in selected
            ],
            [
                float(row["elapsed_ms"])
                for row in selected
            ],
            marker="o",
            label=stage,
        )

    ax.set_xlabel("Proof run")
    ax.set_ylabel("Elapsed time (ms)")
    ax.set_title(
        "Selected Groth16 Prover Phase Timings"
    )
    ax.grid(
        True,
        alpha=0.3,
    )
    ax.legend()
    fig.tight_layout()

    output = (
        FIGURE_DIR
        / "sapling_output_internal_stages.png"
    )

    fig.savefig(
        output,
        dpi=160,
    )
    plt.close(fig)

    return output


def main():
    (
        batch_id,
        threads,
        msm_rows,
        stage_rows,
    ) = parse_log()

    print(f"Batch: {batch_id}")
    print(f"Threads: {threads}")
    print(f"Proof runs: {len(msm_rows) // 8}")

    save_raw_data(
        batch_id,
        threads,
        msm_rows,
        stage_rows,
    )

    grouped = save_summary(
        batch_id,
        threads,
        msm_rows,
    )

    msm_figure = plot_msm(grouped)
    stage_figure = plot_stages(stage_rows)

    print(f"MSM records: {len(msm_rows)}")
    print(f"Prover stage records: {len(stage_rows)}")
    print(f"MSM raw CSV: {MSM_CSV}")
    print(f"Stage raw CSV: {STAGE_CSV}")
    print(f"Summary: {SUMMARY_CSV}")
    print(f"MSM chart: {msm_figure}")
    print(f"Stage chart: {stage_figure}")

    print("\nMedian MSM task latency by query:")

    for query in QUERY_NAMES:
        median = statistics.median(
            grouped[query]
        )
        print(f"{query}: {median:.3f} ms")


if __name__ == "__main__":
    main()