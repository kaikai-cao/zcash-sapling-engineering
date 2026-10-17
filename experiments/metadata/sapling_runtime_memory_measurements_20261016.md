# Sapling 参数大小与运行时内存测量记录

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
| 参数大小审计输出摘录 | `experiments/raw/logs/sapling_parameter_size_audit_20261016.log` | Output 输出已归档 |
| Rust 类型大小 CSV | `experiments/raw/csv/sapling_runtime_type_sizes_20261016.csv` | 已归档 |
| Rust 类型大小日志 | `experiments/raw/logs/sapling_runtime_type_sizes_20261016.log` | 已归档 |
| Spend/Output 参数内存 CSV | `experiments/raw/csv/sapling_runtime_params_memory_20261016.csv` | 两种电路已归档 |
| 实际双文件加载日志 | `experiments/raw/logs/sapling_runtime_params_memory_20261016_111353.log` | 已存在；原始日志保留 |

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

历史运行日志 `sapling_runtime_params_memory_20261016_111353.log` 中记录：
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
   → **2026-10-17 更新：** 已用计数型全局分配器实测闭合，见
   `experiments/metadata/sapling_prove_memory_ledger_20261017.md`
   与 `docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md` §13。

## 6. 下一阶段待测项目

- ~~Prove 期间的进程峰值工作集与可重复的系统内存采样。~~ → **已测**：Spend 单线程绝对高水位 100.29 MiB、8 线程 134.82 MiB。
- ~~MSM 内部桶数组的数量、类型大小、分配容量与存活时间。~~ → **已测**：G1 4,095 桶 = 589,680 B、G2 = 1,179,360 B，逐一吻合；闭包内一次性分配、返回即释放。
- ~~`Exponent<Scalar>` 转换过程的临时数据规模。~~ → **已测**：Spend input 576 B / aux 7,101,936 B / h 9,437,112 B（瞬态 = 源 + 目标）。
- MSM 桶初始化、标量分块、分组累加、分部求和各阶段的耗时。（已有部分阶段计时）
- 关键测量在至少多次独立运行中的变异范围。
- 新发现待跟进：H query 的**窗口化指数表示**是最大单笔瞬态（~26 MB），随非零密度增长。

## 7. 后续归档原则

未来的测量工具应在实验运行时同步写入：
结构化 CSV、原始日志、批次 ID、参数路径、源码版本、线程数、
构建模式和计时边界。聊天记录不应作为唯一证据源。
