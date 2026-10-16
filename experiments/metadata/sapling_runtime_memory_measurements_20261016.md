# Sapling 参数大小与运行时内存测量记录

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
