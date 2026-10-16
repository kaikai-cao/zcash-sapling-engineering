import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROFILE_CSV = (
    ROOT
    / "experiments"
    / "raw"
    / "csv"
    / "sapling_spend_msm_call_profile_1791802391142.csv"
)

TYPE_SIZE_CSV = (
    ROOT
    / "experiments"
    / "raw"
    / "csv"
    / "sapling_runtime_type_sizes_20261016.csv"
)

OUTPUT_DIR = ROOT / "results" / "tables"
METADATA_DIR = ROOT / "experiments" / "metadata"

OUTPUT_CSV = (
    OUTPUT_DIR / "sapling_spend_msm_bucket_memory_20261016.csv"
)
OUTPUT_MD = (
    METADATA_DIR / "sapling_spend_msm_bucket_memory_20261016.md"
)

# BLS12-381 Scalar 的 NUM_BITS。
SCALAR_NUM_BITS = 255

# 参考此前的 20 线程 Spend 诊断批次。
THREAD_COUNT = 20

MIB = 1024 * 1024

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


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"找不到输入文件：{path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_projective_sizes():
    rows = read_csv(TYPE_SIZE_CSV)
    sizes = {
        row["type_name"]: int(row["size_bytes"])
        for row in rows
    }

    required = {
        "G1Projective": 144,
        "G2Projective": 288,
    }

    for name, expected in required.items():
        if name not in sizes:
            raise ValueError(f"类型大小 CSV 中缺少 {name}")

        if sizes[name] != expected:
            raise ValueError(
                f"{name} 大小与本次核算前提不一致："
                f"expected={expected}, actual={sizes[name]}"
            )

    return sizes


def read_unique_msm_calls():
    rows = read_csv(PROFILE_CSV)
    calls = {}

    for row in rows:
        name = row["query"]
        current = (
            row["group"],
            int(row["exponent_count"]),
            int(row["threads"]),
        )

        if name in calls and calls[name] != current:
            raise ValueError(
                f"{name} 在原始记录中出现不一致的参数："
                f"{calls[name]} vs {current}"
            )

        calls[name] = current

    missing = set(QUERY_ORDER) - set(calls)
    if missing:
        raise ValueError(f"MSM 原始记录缺少调用：{sorted(missing)}")

    return calls


def calculate_window(exponent_count):
    # 与 vendor/bellman/src/multiexp.rs 的规则对应。
    if exponent_count < 32:
        return 3

    return math.ceil(math.log(exponent_count))


def calculate_row(name, call, type_sizes):
    group, exponent_count, recorded_threads = call

    if group not in ("G1", "G2"):
        raise ValueError(f"未知群类型：{group}")

    window = calculate_window(exponent_count)

    # 每个 chunk 的桶数量。
    bucket_count = (1 << window) - 1

    # 标量位数按窗口切分后的 chunk 数量。
    chunk_count = math.ceil(SCALAR_NUM_BITS / window)

    projective_type = (
        "G1Projective" if group == "G1"
        else "G2Projective"
    )
    element_size = type_sizes[projective_type]

    # 单个 chunk 的一个桶数组。
    bytes_per_chunk = bucket_count * element_size

    # 所有 chunk 的桶数组累计数据区规模。
    # 这是累计量，不是同时驻留的峰值内存。
    total_bucket_slots = bucket_count * chunk_count
    cumulative_bytes = total_bucket_slots * element_size

    # 假设一个线程同一时刻最多处理一个 chunk 的桶数组，
    # 估算单个 MSM 调用在 20 线程池中的并发上界。
    # 这不是实际峰值测量，也不是整个 Prove 的进程内存。
    active_chunks_upper_bound = min(chunk_count, THREAD_COUNT)
    concurrent_upper_bound = (
        active_chunks_upper_bound * bytes_per_chunk
    )

    return {
        "query": name,
        "group": group,
        "exponent_count": exponent_count,
        "recorded_threads": recorded_threads,
        "scalar_num_bits": SCALAR_NUM_BITS,
        "window": window,
        "bucket_count_per_chunk": bucket_count,
        "chunk_count": chunk_count,
        "bucket_element_type": projective_type,
        "bucket_element_size_bytes": element_size,
        "bucket_array_payload_bytes_per_chunk": bytes_per_chunk,
        "bucket_slots_across_all_chunks": total_bucket_slots,
        "cumulative_bucket_payload_bytes_across_chunks": cumulative_bytes,
        "active_chunks_upper_bound_at_20_threads": active_chunks_upper_bound,
        "single_call_concurrent_payload_upper_bound_bytes": concurrent_upper_bound,
        "single_chunk_payload_MiB": round(bytes_per_chunk / MIB, 6),
        "cumulative_payload_MiB": round(cumulative_bytes / MIB, 6),
        "single_call_upper_bound_MiB": round(concurrent_upper_bound / MIB, 6),
        "status": "derived_static_estimate_not_runtime_peak",
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    type_sizes = read_projective_sizes()
    calls = read_unique_msm_calls()

    results = [
        calculate_row(name, calls[name], type_sizes)
        for name in QUERY_ORDER
    ]

    headers = list(results[0].keys())

    with OUTPUT_CSV.open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results)

    lines = [
        "# Sapling Spend MSM 桶数组内存核算",
        "",
        "**日期：** 2026-10-16",
        "",
        "## 1. 数据来源",
        "",
        "- MSM 调用数量：",
        "  `experiments/raw/csv/"
        "sapling_spend_msm_call_profile_1791802391142.csv`",
        "- 群元素对象大小：",
        "  `experiments/raw/csv/"
        "sapling_runtime_type_sizes_20261016.csv`",
        "- 实现：`vendor/bellman/src/multiexp.rs`",
        "",
        "本报告是根据已记录的调用参数和 Rust 类型大小得到的",
        "静态核算结果，不是新增的性能测量。",
        "",
        "## 2. 计算方法",
        "",
        "窗口规则：指数数量小于 32 时，`c = 3`；否则，",
        "`c = ceil(ln(exponent_count))`。",
        "",
        "每个 chunk 的桶数为 `2^c - 1`。",
        "",
        "单个桶数组数据区大小为：",
        "`bucket_count × size_of(projective group element)`。",
        "",
        "BLS12-381 标量位数按 255 计算，",
        "chunk 数为 `ceil(255 / c)`。",
        "",
        "## 3. 逐调用核算",
        "",
        "| 调用 | 群 | 指数数 | 窗口 | 桶数/chunk | chunk 数 | 单个桶数组 | 累计桶数组数据区 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    for row in results:
        lines.append(
            f"| {row['query']} "
            f"| {row['group']} "
            f"| {row['exponent_count']:,} "
            f"| {row['window']} "
            f"| {row['bucket_count_per_chunk']:,} "
            f"| {row['chunk_count']} "
            f"| {row['bucket_array_payload_bytes_per_chunk']:,} B "
            f"| {row['cumulative_bucket_payload_bytes_across_chunks']:,} B |"
        )

    lines.extend([
        "",
        "## 4. 如何解释这些数字",
        "",
        "- **单个桶数组数据区**：一个 chunk 中桶元素的数据区大小，",
        "  不包含 Vec 头部、分配器元数据或其他临时对象。",
        "- **累计桶数组数据区**：所有 chunk 的桶数组大小之和，",
        "  不是同一时刻的峰值内存。",
        "- **20 线程并发上界**：假设最多 20 个 chunk 桶数组同时活动时，",
        "  对单个 MSM 调用计算的理论上界；不是实测峰值。",
        "- 多个 MSM 调用可能相互重叠；单个调用的上界不能直接相加，",
        "  并当作整个证明过程的峰值内存。",
        "- 要获得实际峰值，后续仍需在执行时采集分配数量、桶数组",
        "  生命周期和并发情况，或使用系统级内存测量。",
        "",
        "## 5. 输出文件",
        "",
        f"- CSV：`{OUTPUT_CSV.relative_to(ROOT).as_posix()}`",
        f"- Markdown：`{OUTPUT_MD.relative_to(ROOT).as_posix()}`",
        "",
    ])

    OUTPUT_MD.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("MSM bucket memory accounting completed.\n")

    for row in results:
        print(
            f"{row['query']:16s} "
            f"group={row['group']} "
            f"n={row['exponent_count']:>7,} "
            f"c={row['window']:>2} "
            f"buckets={row['bucket_count_per_chunk']:>4,} "
            f"chunks={row['chunk_count']:>3} "
            f"per_chunk={row['bucket_array_payload_bytes_per_chunk']:>9,} B "
            f"cumulative={row['cumulative_bucket_payload_bytes_across_chunks']:>10,} B "
            f"20_thread_upper={row['single_call_concurrent_payload_upper_bound_bytes']:>10,} B"
        )

    print(f"\nCSV: {OUTPUT_CSV}")
    print(f"Markdown: {OUTPUT_MD}")


if __name__ == "__main__":
    main()