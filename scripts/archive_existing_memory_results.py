import csv
from pathlib import Path


# =========================================================
# Configuration
# =========================================================

ROOT = Path(__file__).resolve().parents[1]

RAW_CSV = ROOT / "experiments" / "raw" / "csv"
RAW_LOGS = ROOT / "experiments" / "raw" / "logs"
METADATA = ROOT / "experiments" / "metadata"

ARCHIVE_DATE = "20261016"

for directory in (RAW_CSV, RAW_LOGS, METADATA):
    directory.mkdir(parents=True, exist_ok=True)


# =========================================================
# Helpers
# =========================================================

def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    """Write a UTF-8 CSV with a header row."""
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_text_if_absent(path: Path, content: str) -> None:
    """
    Create a reconstructed historical log only when the file
    does not already exist. Never overwrite an existing raw log.
    """
    if path.exists():
        print(f"[KEEP] Existing log preserved: {path.relative_to(ROOT)}")
        return

    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    print(f"[NEW]  {path.relative_to(ROOT)}")


def check_equal(label: str, actual: int, expected: int) -> None:
    """Stop archival if an important accounting total is incorrect."""
    if actual != expected:
        raise ValueError(
            f"{label}: expected {expected:,}, got {actual:,}"
        )


# =========================================================
# 1. Rust runtime type sizes
# Source: terminal output supplied during this conversation.
# These are object sizes, not serialized encoding sizes.
# =========================================================

type_rows = [
    {
        "type_name": "G1Affine",
        "size_bytes": 104,
        "alignment_bytes": 8,
        "category": "curve_point",
    },
    {
        "type_name": "G2Affine",
        "size_bytes": 200,
        "alignment_bytes": 8,
        "category": "curve_point",
    },
    {
        "type_name": "G1Projective",
        "size_bytes": 144,
        "alignment_bytes": 8,
        "category": "curve_point",
    },
    {
        "type_name": "G2Projective",
        "size_bytes": 288,
        "alignment_bytes": 8,
        "category": "curve_point",
    },
    {
        "type_name": "Scalar",
        "size_bytes": 32,
        "alignment_bytes": 8,
        "category": "scalar",
    },
    {
        "type_name": "Exponent<Scalar>",
        "size_bytes": 40,
        "alignment_bytes": 8,
        "category": "exponent",
    },
    {
        "type_name": "Vec<G1Affine> header",
        "size_bytes": 24,
        "alignment_bytes": 8,
        "category": "container_header",
    },
    {
        "type_name": "Vec<G2Affine> header",
        "size_bytes": 24,
        "alignment_bytes": 8,
        "category": "container_header",
    },
    {
        "type_name": "Vec<G1Projective> header",
        "size_bytes": 24,
        "alignment_bytes": 8,
        "category": "container_header",
    },
    {
        "type_name": "Vec<G2Projective> header",
        "size_bytes": 24,
        "alignment_bytes": 8,
        "category": "container_header",
    },
    {
        "type_name": "Vec<Scalar> header",
        "size_bytes": 24,
        "alignment_bytes": 8,
        "category": "container_header",
    },
    {
        "type_name": "Vec<Exponent<Scalar>> header",
        "size_bytes": 24,
        "alignment_bytes": 8,
        "category": "container_header",
    },
    {
        "type_name": "Arc<Vec<G1Affine>> handle",
        "size_bytes": 8,
        "alignment_bytes": 8,
        "category": "arc_handle",
    },
    {
        "type_name": "Arc<Vec<G2Affine>> handle",
        "size_bytes": 8,
        "alignment_bytes": 8,
        "category": "arc_handle",
    },
]

TYPE_CSV = RAW_CSV / f"sapling_runtime_type_sizes_{ARCHIVE_DATE}.csv"

write_csv(
    TYPE_CSV,
    ["type_name", "size_bytes", "alignment_bytes", "category"],
    type_rows,
)

type_log = """===== Elliptic Curve Runtime Types =====
G1Affine                         size= 104 bytes, align= 8 bytes
G2Affine                         size= 200 bytes, align= 8 bytes
G1Projective                     size= 144 bytes, align= 8 bytes
G2Projective                     size= 288 bytes, align= 8 bytes
Scalar                           size=  32 bytes, align= 8 bytes
Exponent<Scalar>                 size=  40 bytes, align= 8 bytes

===== Container Headers =====
Vec<G1Affine> header             size=  24 bytes, align= 8 bytes
Vec<G2Affine> header             size=  24 bytes, align= 8 bytes
Vec<G1Projective> header         size=  24 bytes, align= 8 bytes
Vec<G2Projective> header         size=  24 bytes, align= 8 bytes
Vec<Scalar> header               size=  24 bytes, align= 8 bytes
Vec<Exponent<Scalar>> header     size=  24 bytes, align= 8 bytes
Arc<Vec<G1Affine>> handle        size=   8 bytes, align= 8 bytes
Arc<Vec<G2Affine>> handle        size=   8 bytes, align= 8 bytes

Archive note: reconstructed from console output shared on 2026-10-16.
"""

write_text_if_absent(
    RAW_LOGS / f"sapling_runtime_type_sizes_{ARCHIVE_DATE}.log",
    type_log,
)


# =========================================================
# 2. Runtime parameter memory
#
# Values are copied from the actual terminal output shared
# in this conversation. They are NOT newly measured here.
#
# len_payload = len * size_of(T)
# capacity_payload = capacity * size_of(T)
#
# Fixed VK point payloads are reported separately.
# =========================================================

memory_columns = [
    "circuit",
    "component",
    "element_count",
    "capacity",
    "element_size_bytes",
    "len_payload_bytes",
    "capacity_payload_bytes",
    "status",
]

memory_rows = []

circuits = {
    "Spend": [
        # component, len, capacity, element_size, len_payload,
        # capacity_payload, status
        ("VK_FIXED_POINTS", 6, 6, "", 912, 912, "measured_fixed_points"),
        ("VK_IC", 8, 8, 104, 832, 832, "measured"),
        ("H_G1", 131071, 131072, 104, 13631384, 13631488, "measured"),
        ("L_G1", 98638, 131072, 104, 10258352, 13631488, "measured"),
        ("A_G1", 85390, 131072, 104, 8880560, 13631488, "measured"),
        ("B_G1", 61300, 65536, 104, 6375200, 6815744, "measured"),
        ("B_G2", 61300, 65536, 200, 12260000, 13107200, "measured"),
    ],
    "Output": [
        ("VK_FIXED_POINTS", 6, 6, "", 912, 912, "measured_fixed_points"),
        ("VK_IC", 6, 8, 104, 624, 832, "measured"),
        ("H_G1", 8191, 8192, 104, 851864, 851968, "measured"),
        ("L_G1", 7821, 8192, 104, 813384, 851968, "measured"),
        ("A_G1", 6298, 8192, 104, 654992, 851968, "measured"),
        ("B_G1", 4850, 8192, 104, 504400, 851968, "measured"),
        ("B_G2", 4850, 8192, 200, 970000, 1638400, "measured"),
    ],
}

expected_totals = {
    "Spend": {
        "len_payload_bytes": 51407240,
        "capacity_payload_bytes": 60819152,
    },
    "Output": {
        "len_payload_bytes": 3796176,
        "capacity_payload_bytes": 5048016,
    },
}

for circuit, entries in circuits.items():
    len_total = 0
    capacity_total = 0

    for (
        component,
        element_count,
        capacity,
        element_size,
        len_payload,
        capacity_payload,
        status,
    ) in entries:
        # Verify the arithmetic whenever element size is available.
        if element_size != "":
            check_equal(
                f"{circuit}/{component}: len * size",
                element_count * element_size,
                len_payload,
            )
            check_equal(
                f"{circuit}/{component}: capacity * size",
                capacity * element_size,
                capacity_payload,
            )

        memory_rows.append(
            {
                "circuit": circuit,
                "component": component,
                "element_count": element_count,
                "capacity": capacity,
                "element_size_bytes": element_size,
                "len_payload_bytes": len_payload,
                "capacity_payload_bytes": capacity_payload,
                "status": status,
            }
        )

        len_total += len_payload
        capacity_total += capacity_payload

    check_equal(
        f"{circuit} total len payload",
        len_total,
        expected_totals[circuit]["len_payload_bytes"],
    )
    check_equal(
        f"{circuit} total capacity payload",
        capacity_total,
        expected_totals[circuit]["capacity_payload_bytes"],
    )

    print(f"[PASS] {circuit}")
    print(f"       len_payload_bytes      = {len_total:,}")
    print(f"       capacity_payload_bytes = {capacity_total:,}")

MEMORY_CSV = RAW_CSV / f"sapling_runtime_params_memory_{ARCHIVE_DATE}.csv"

write_csv(MEMORY_CSV, memory_columns, memory_rows)


# =========================================================
# 3. Preserve runtime type size output
# =========================================================

runtime_type_log = """===== Elliptic Curve Runtime Types =====
G1Affine                         size= 104 bytes, align= 8 bytes
G2Affine                         size= 200 bytes, align= 8 bytes
G1Projective                     size= 144 bytes, align= 8 bytes
G2Projective                     size= 288 bytes, align= 8 bytes
Scalar                           size=  32 bytes, align= 8 bytes
Exponent<Scalar>                 size=  40 bytes, align= 8 bytes

===== Container Headers =====
Vec<G1Affine> header             size=  24 bytes, align= 8 bytes
Vec<G2Affine> header             size=  24 bytes, align= 8 bytes
Vec<G1Projective> header         size=  24 bytes, align= 8 bytes
Vec<G2Projective> header         size=  24 bytes, align= 8 bytes
Vec<Scalar> header               size=  24 bytes, align= 8 bytes
Vec<Exponent<Scalar>> header     size=  24 bytes, align= 8 bytes
Arc<Vec<G1Affine>> handle        size=   8 bytes, align= 8 bytes
Arc<Vec<G2Affine>> handle        size=   8 bytes, align= 8 bytes

Archive note: reconstructed from console output shared on 2026-10-16.
"""

write_text_if_absent(
    RAW_LOGS / f"sapling_runtime_type_sizes_{ARCHIVE_DATE}.log",
    runtime_type_log,
)


# =========================================================
# 4. Parameter audit output
#
# Preserve existing logs. If no log exists, reconstruct the
# supplied Output excerpt as a historical transcription.
# The authoritative full section data remains the raw CSV.
# =========================================================

parameter_audit_log = """===== Output =====
VK_FIXED_POINTS          count=      6 payload=       864 B prefix= 0 B encoded=       864 B
VK_IC                    count=      6 payload=       576 B prefix= 4 B encoded=       580 B
H_G1                     count=  8,191 payload=   786,336 B prefix= 4 B encoded=   786,340 B
L_G1                     count=  7,821 payload=   750,816 B prefix= 4 B encoded=   750,820 B
A_G1                     count=  6,298 payload=   604,608 B prefix= 4 B encoded=   604,612 B
B_G1                     count=  4,850 payload=   465,600 B prefix= 4 B encoded=   465,604 B
B_G2                     count=  4,850 payload=   931,200 B prefix= 4 B encoded=   931,204 B
MPC_CIRCUIT_HASH         count=      1 payload=        64 B prefix= 0 B encoded=        64 B
MPC_CONTRIBUTOR_COUNT    count=     97 payload=         0 B prefix= 4 B encoded=         4 B
MPC_CONTRIBUTION_RECORDS count=     97 payload=    52,768 B prefix= 0 B encoded=    52,768 B
PASS: Output = 3,592,860 bytes

所有参数文件的字节账均通过检查。

Archive note: reconstructed from console output shared on 2026-10-16.
The supplied console excerpt shows Output. Refer to the original parameter breakdown CSV for complete Spend and Output records.
"""

write_text_if_absent(
    RAW_LOGS / f"sapling_parameter_size_audit_{ARCHIVE_DATE}.log",
    parameter_audit_log,
)


# =========================================================
# 5. Research summary
#
# Correctly distinguishes measured data, reconstructed logs,
# serialization, object payload, buffer capacity, and peak RSS.
# =========================================================

report = f"""# Sapling 参数大小与运行时内存测量记录

**归档日期：** 2026-10-16
**用途：** 保存已完成测量的结果，并记录下一阶段的测量缺口。

## 1. 数据来源与状态

本次归档脚本将本次研究对话中用户提供的终端结果结构化。
本脚本本身不重新执行参数读取，也不生成新的性能测量结果。
历史终端输出的文本归档属于根据已提供输出重建的记录；
原始实验 CSV 和原有带时间戳日志仍是对应测量的主要证据。

| 测量内容 | 记录文件 | 状态 |
|---|---|---|
| 参数序列化分段 | `experiments/raw/csv/sapling_parameter_size_breakdown_20261011_142729.csv` | 原始 CSV 已存在 |
| 参数大小审计输出摘录 | `experiments/raw/logs/sapling_parameter_size_audit_{ARCHIVE_DATE}.log` | Output 输出已归档 |
| Rust 类型大小 CSV | `experiments/raw/csv/sapling_runtime_type_sizes_{ARCHIVE_DATE}.csv` | 已归档 |
| Rust 类型大小日志 | `experiments/raw/logs/sapling_runtime_type_sizes_{ARCHIVE_DATE}.log` | 已归档 |
| Spend/Output 参数内存 CSV | `experiments/raw/csv/sapling_runtime_params_memory_{ARCHIVE_DATE}.csv` | 两种电路已归档 |
| 实际双文件加载日志 | `experiments/raw/logs/sapling_runtime_params_memory_{ARCHIVE_DATE}_111353.log` | 已存在；原始日志保留 |

## 2. 参数文件序列化大小

| 电路 | 参数文件字节数 | MiB（1 MiB = 1,048,576 bytes） |
|---|---:|---:|
| Spend | 47,958,396 | 45.736691 |
| Output | 3,592,860 | 3.426418 |

详细点数、偏移、长度前缀和各段字节数以原始参数分解 CSV 为准。

## 3. Rust 类型布局

| 类型 | `size_of` | `align_of` |
|---|---:|---:|
| G1Affine | 104 B | 8 B |
| G2Affine | 200 B | 8 B |
| G1Projective | 144 B | 8 B |
| G2Projective | 288 B | 8 B |
| Scalar | 32 B | 8 B |
| Exponent<Scalar> | 40 B | 8 B |
| Vec<T> 头部 | 24 B | 8 B |
| Arc<Vec<T>> 句柄 | 8 B | 8 B |

这些数字来自当前运行环境的实际 `size_of` / `align_of` 输出。
它们是 Rust 对象的布局数据，不是参数文件中的序列化编码大小。

## 4. 运行时参数向量内存

定义：

- `len_payload_bytes = len × size_of(T)`
- `capacity_payload_bytes = capacity × size_of(T)`

这两项统计的是向量元素数据区或元素缓冲区容量，不包含分配器元数据。
VK 固定点按三个 G1 和三个 G2 点计算，单独计入 912 bytes。

| 电路 | 按 len 统计 | MiB | 按 capacity 统计 | MiB |
|---|---:|---:|---:|---:|
| Spend | 51,407,240 B | 49.025764 | 60,819,152 B | 58.001663 |
| Output | 3,796,176 B | 3.620316 | 5,048,016 B | 4.814163 |

### 4.1 Spend 参数主体读取与编码验证

历史运行日志 `sapling_runtime_params_memory_{ARCHIVE_DATE}_111353.log` 中记录：
45,608.842 ms。

另一次此前提供的独立测量记录为 29,772.887 ms。
另一次正式参数元数据记录中也有其他批次的耗时。
不同批次必须保留各自计时，不应相互覆盖或平均，尤其因为磁盘缓存、
系统负载、文件读取和点解码验证成本可能影响时间。

### 4.2 Output 参数主体读取与编码验证

在同一份双文件历史运行日志中记录：
3,591.546 ms。

这些计时是 `Parameters::read(..., true)` 的 Groth16 参数读取与点编码验证，
不是 Setup 时间、MPC 参数生成时间，也不是证明生成时间。

## 5. 重要限制

1. `len × size_of(T)` 是当前元素对象的数据区大小。
2. `capacity × size_of(T)` 是向量元素缓冲区容量，不代表全部进程内存。
3. `Vec` 头部、`Arc` 控制块、分配器元数据及其他临时分配未全部计入上述汇总。
4. 参数加载后内存大小不等于 Prove 期间峰值工作集。
5. 目前还没有把 MSM 桶数组、指数转换缓冲区、任务并行临时空间分解到完整的峰值内存账本。

## 6. 下一阶段待测项目

- Prove 期间的进程峰值工作集与可重复的系统内存采样。
- MSM 内部桶数组的数量、类型大小、分配容量与存活时间。
- `Exponent<Scalar>` 转换过程的临时数据规模。
- MSM 桶初始化、标量分块、分组累加、分部求和各阶段的耗时。
- 关键测量在至少多次独立运行中的变异范围。

## 7. 后续归档原则

未来的测量工具应在实验运行时同步写入：
结构化 CSV、原始日志、批次 ID、参数路径、源码版本、线程数、
构建模式和计时边界。聊天记录不应作为唯一证据源。
"""

SUMMARY_PATH = (
    METADATA / f"sapling_runtime_memory_measurements_{ARCHIVE_DATE}.md"
)
SUMMARY_PATH.write_text(report, encoding="utf-8")


# =========================================================
# 6. Final check and output
# =========================================================

print("\n===== Archival checks =====")

check_equal(
    "Spend parameter vector len bytes",
    expected_totals["Spend"]["len_payload_bytes"],
    51407240,
)
check_equal(
    "Spend parameter vector capacity bytes",
    expected_totals["Spend"]["capacity_payload_bytes"],
    60819152,
)
check_equal(
    "Output parameter vector len bytes",
    expected_totals["Output"]["len_payload_bytes"],
    3796176,
)
check_equal(
    "Output parameter vector capacity bytes",
    expected_totals["Output"]["capacity_payload_bytes"],
    5048016,
)

print(f"[PASS] CSV rows: {len(memory_rows)} (7 Spend + 7 Output)")
print("[PASS] Critical memory totals match recorded measurements.")

print("\nCreated or updated:")
for path in [
    TYPE_CSV,
    MEMORY_CSV,
    RAW_LOGS / f"sapling_runtime_type_sizes_{ARCHIVE_DATE}.log",
    RAW_LOGS / f"sapling_parameter_size_audit_{ARCHIVE_DATE}.log",
    SUMMARY_PATH,
]:
    print(f" - {path.relative_to(ROOT)}")

print("\nExisting raw logs were not overwritten.")
print("Archive complete.")