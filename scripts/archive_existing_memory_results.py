import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RAW_CSV = ROOT / "experiments" / "raw" / "csv"
RAW_LOGS = ROOT / "experiments" / "raw" / "logs"
METADATA = ROOT / "experiments" / "metadata"

for directory in (RAW_CSV, RAW_LOGS, METADATA):
    directory.mkdir(parents=True, exist_ok=True)


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------
# 1. 归档 Rust 类型大小测试结果
# 数据来源：本次对话中用户提供的实际终端输出
# ---------------------------------------------------------

type_rows = [
    ("G1Affine", 104, 8, "curve_point"),
    ("G2Affine", 200, 8, "curve_point"),
    ("G1Projective", 144, 8, "curve_point"),
    ("G2Projective", 288, 8, "curve_point"),
    ("Scalar", 32, 8, "scalar"),
    ("Exponent<Scalar>", 40, 8, "exponent"),
    ("Vec<G1Affine> header", 24, 8, "container_header"),
    ("Vec<G2Affine> header", 24, 8, "container_header"),
    ("Vec<G1Projective> header", 24, 8, "container_header"),
    ("Vec<G2Projective> header", 24, 8, "container_header"),
    ("Vec<Scalar> header", 24, 8, "container_header"),
    ("Vec<Exponent<Scalar>> header", 24, 8, "container_header"),
    ("Arc<Vec<G1Affine>> handle", 8, 8, "arc_handle"),
    ("Arc<Vec<G2Affine>> handle", 8, 8, "arc_handle"),
]

write_csv(
    RAW_CSV / "sapling_runtime_type_sizes_20261016.csv",
    ["type_name", "size_bytes", "alignment_bytes", "category"],
    [
        {
            "type_name": name,
            "size_bytes": size,
            "alignment_bytes": alignment,
            "category": category,
        }
        for name, size, alignment, category in type_rows
    ],
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
Vec<G1Projective> header        size=  24 bytes, align= 8 bytes
Vec<G2Projective> header        size=  24 bytes, align= 8 bytes
Vec<Scalar> header               size=  24 bytes, align= 8 bytes
Vec<Exponent<Scalar>> header     size=  24 bytes, align= 8 bytes
Arc<Vec<G1Affine>> handle        size=   8 bytes, align= 8 bytes
Arc<Vec<G2Affine>> handle        size=   8 bytes, align= 8 bytes

Archive note: reconstructed from console output shared on 2026-10-16.
"""

(RAW_LOGS / "sapling_runtime_type_sizes_20261016.log").write_text(
    type_log, encoding="utf-8"
)


# ---------------------------------------------------------
# 2. 归档 Spend 参数加载后的实际向量容量
# 注意：这是已提供的 Spend 数据，Output 尚待测量
# ---------------------------------------------------------

memory_rows = [
    {
        "circuit": "Spend",
        "component": "VK_FIXED_POINTS",
        "element_count": 6,
        "capacity": 6,
        "element_size_bytes": "",
        "len_payload_bytes": 912,
        "capacity_payload_bytes": 912,
        "status": "measured_fixed_points",
    },
    {
        "circuit": "Spend",
        "component": "VK_IC",
        "element_count": 8,
        "capacity": 8,
        "element_size_bytes": 104,
        "len_payload_bytes": 832,
        "capacity_payload_bytes": 832,
        "status": "measured",
    },
    {
        "circuit": "Spend",
        "component": "H_G1",
        "element_count": 131071,
        "capacity": 131072,
        "element_size_bytes": 104,
        "len_payload_bytes": 13631384,
        "capacity_payload_bytes": 13631488,
        "status": "measured",
    },
    {
        "circuit": "Spend",
        "component": "L_G1",
        "element_count": 98638,
        "capacity": 131072,
        "element_size_bytes": 104,
        "len_payload_bytes": 10258352,
        "capacity_payload_bytes": 13631488,
        "status": "measured",
    },
    {
        "circuit": "Spend",
        "component": "A_G1",
        "element_count": 85390,
        "capacity": 131072,
        "element_size_bytes": 104,
        "len_payload_bytes": 8880560,
        "capacity_payload_bytes": 13631488,
        "status": "measured",
    },
    {
        "circuit": "Spend",
        "component": "B_G1",
        "element_count": 61300,
        "capacity": 65536,
        "element_size_bytes": 104,
        "len_payload_bytes": 6375200,
        "capacity_payload_bytes": 6815744,
        "status": "measured",
    },
    {
        "circuit": "Spend",
        "component": "B_G2",
        "element_count": 61300,
        "capacity": 65536,
        "element_size_bytes": 200,
        "len_payload_bytes": 12260000,
        "capacity_payload_bytes": 13107200,
        "status": "measured",
    },
]

write_csv(
    RAW_CSV / "sapling_runtime_params_memory_20261016.csv",
    [
        "circuit",
        "component",
        "element_count",
        "capacity",
        "element_size_bytes",
        "len_payload_bytes",
        "capacity_payload_bytes",
        "status",
    ],
    memory_rows,
)

spend_log = r"""===== D:\Research\zcash-params\sapling-spend.params =====
groth16_body_read_validate_ms=29772.887
vk_fixed_points=6 vk_fixed_object_bytes=912
VK_IC        len=      8 capacity=      8 element_size=104 B len_payload=       832 B capacity_payload=       832 B
H_G1         len= 131071 capacity= 131072 element_size=104 B len_payload=  13631384 B capacity_payload=  13631488 B
L_G1         len=  98638 capacity= 131072 element_size=104 B len_payload=  10258352 B capacity_payload=  13631488 B
A_G1         len=  85390 capacity= 131072 element_size=104 B len_payload=   8880560 B capacity_payload=  13631488 B
B_G1         len=  61300 capacity=  65536 element_size=104 B len_payload=   6375200 B capacity_payload=   6815744 B
B_G2         len=  61300 capacity=  65536 element_size=200 B len_payload=  12260000 B capacity_payload=  13107200 B
point_object_payload_by_len_bytes=51407240
point_buffer_payload_by_capacity_bytes=60819152
point_object_payload_by_len_MiB=49.025764
point_buffer_payload_by_capacity_MiB=58.001663
vec_header_bytes=24 arc_handle_bytes=8
g1_affine_bytes=104 g2_affine_bytes=200

Archive note: reconstructed from console output shared on 2026-10-16.
Output runtime memory results were not included in the supplied output and remain pending.
"""

(RAW_LOGS / "sapling_runtime_params_memory_spend_20261016.log").write_text(
    spend_log, encoding="utf-8"
)


# ---------------------------------------------------------
# 3. 归档参数文件大小审计的输出片段
# 完整分段数据仍以原始 parameter breakdown CSV 为准
# ---------------------------------------------------------

audit_log = """===== Output =====
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

Archive note: preserved from console output shared on 2026-10-16.
The shared console excerpt contains the Output section; the original parameter breakdown CSV contains both circuits.
"""

(RAW_LOGS / "sapling_parameter_size_audit_20261016.log").write_text(
    audit_log, encoding="utf-8"
)


# ---------------------------------------------------------
# 4. 汇总说明：保留测量边界和仍待采集的数据
# ---------------------------------------------------------

report = """# Sapling 参数大小与运行时内存测量记录

**归档日期：** 2026-10-16

## 1. 数据来源与状态

本记录将本次研究对话中已经提供的终端结果补档到仓库。它不是最初实验运行时自动生成的日志；历史终端输出是在本次归档时按已提供内容写入文件。

| 测量内容 | 记录文件 | 状态 |
|---|---|---|
| 参数序列化分段 | `experiments/raw/csv/sapling_parameter_size_breakdown_20261011_142729.csv` | 原始 CSV 已存在 |
| 参数大小审计输出片段 | `experiments/raw/logs/sapling_parameter_size_audit_20261016.log` | Output 输出已归档 |
| Rust 类型大小 | `experiments/raw/logs/sapling_runtime_type_sizes_20261016.log` | 已归档 |
| Rust 类型大小 CSV | `experiments/raw/csv/sapling_runtime_type_sizes_20261016.csv` | 已归档 |
| Spend 参数内存输出 | `experiments/raw/logs/sapling_runtime_params_memory_spend_20261016.log` | 已归档 |
| Spend 向量内存 CSV | `experiments/raw/csv/sapling_runtime_params_memory_20261016.csv` | 已归档 |

## 2. 已核实的序列化大小

| 电路 | 参数文件总字节数 |
|---|---:|
| Spend | 47,958,396 |
| Output | 3,592,860 |

详细点数、偏移和编码字节数以既有原始参数分解 CSV 为准。

## 3. Rust 类型布局测量

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

这些数值描述当前构建环境的 Rust 类型布局，不是序列化编码大小。

## 4. Spend 参数的运行时元素内存

实际读取结果：

- Groth16 参数主体读取与点编码验证耗时：29,772.887 ms。
- 按 `len × size_of(T)` 计算的点对象数据量：51,407,240 bytes（49.025764 MiB）。
- 按 `capacity × size_of(T)` 计算的向量元素缓冲区容量：60,819,152 bytes（58.001663 MiB）。

上述统计包含 VK 固定点、VK IC 和五个查询向量。它不是完整进程峰值内存，也不包含分配器元数据、所有容器管理开销和证明期间的全部临时分配。

计时边界是 `Parameters::read(..., true)` 的参数主体读取与点编码验证，不应将其称为 Setup 或 MPC 参数生成时间。

## 5. 待补的数据

1. Output 参数的运行时向量 `len`、`capacity` 和容量字节数。
2. 两个电路在实际 Prove 期间的临时内存与峰值工作集。
3. MSM 桶数组和指数临时缓冲区的容量与生命周期。

## 6. 归档原则

今后的实验应在测量程序内部同时写入结构化 CSV 和原始日志，并给出批次编号、参数路径、源码版本、构建模式与线程数。聊天记录只用于讨论，不应作为唯一数据保存位置。
"""

(METADATA / "sapling_runtime_memory_measurements_20261016.md").write_text(
    report, encoding="utf-8"
)

print("归档完成。创建或更新了以下文件：")
for path in [
    RAW_LOGS / "sapling_parameter_size_audit_20261016.log",
    RAW_LOGS / "sapling_runtime_type_sizes_20261016.log",
    RAW_LOGS / "sapling_runtime_params_memory_spend_20261016.log",
    RAW_CSV / "sapling_runtime_type_sizes_20261016.csv",
    RAW_CSV / "sapling_runtime_params_memory_20261016.csv",
    METADATA / "sapling_runtime_memory_measurements_20261016.md",
]:
    print(path.relative_to(ROOT))