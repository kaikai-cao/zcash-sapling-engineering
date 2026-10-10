# Sapling MSM Profiling and Worker Scheduling Notes

本文档保存 Sapling Output 与 Spend 的探索性 MSM 调用级计时、内部阶段分析及 Worker 调度观察。它是详细技术记录，不是正式性能基线。

正式 proving 基线仍以 `results/tables/engineering_performance.csv` 指定的批次为准：Spend `1791613854129`（Prove 中位数 3,385.716 ms），Output `1791549582046`（Prove 中位数 514.853 ms）。文中所有探索性 profile 均应与这些正式结果分开解释。

本文中的相对路径均以仓库根目录为基准。不同插桩强度、批次和线程配置的数据不可随意混算。

## 1. Sapling Output：调用级 MSM profile

两份较低开销的单线程 profile 日志显示，排除每份日志的首轮后，八次 MSM 调用 elapsed 的合计约占整次 Prove 的 93.2%–93.4%。它支持“MSM 主导当前测得 Output 单线程路径”的范围有限结论，不应推广到 Spend 或所有 Groth16 电路。

### 1.1 八次 MSM 调用映射

| MSM 调用 | 群 | 标量数量 | window | `profile_sizes` 稳态中位数 | `op_counts` 稳态中位数 |
|---|---|---:|---:|---:|---:|
| H query | G1 | 8,191 | 10 | 129.125 ms | 127.084 ms |
| L query | G1 | 7,821 | 9 | 82.987 ms | 82.089 ms |
| A input query | G1 | 6 | 3 | 0.938 ms | 1.033 ms |
| A auxiliary query | G1 | 7,821 | 9 | 65.012 ms | 64.723 ms |
| B-G1 input query | G1 | 6 | 3 | 0.772 ms | 0.890 ms |
| B-G1 auxiliary query | G1 | 7,821 | 9 | 53.180 ms | 53.738 ms |
| B-G2 input query | G2 | 6 | 3 | 2.237 ms | 2.273 ms |
| **B-G2 auxiliary query** | **G2** | **7,821** | **9** | **152.731 ms** | **151.694 ms** |

调用名称依据 `vendor/groth16/src/prover.rs` 中的调用顺序及日志里的标量数量和 window 对应。B-G2 auxiliary 是这些记录中耗时最高的单次调用；这并不说明所有 G2 调用都慢，例如只有 6 个标量的 B-G2 input 调用约需 2.2 ms。

## 2. Sapling Output：B-G2 auxiliary 内部阶段

更深度插桩日志 `sapling_output_msm_stages_1threads.log` 中，`call_id=8,16,24,32,40` 对应 B-G2 auxiliary query。五次调用的阶段计时如下：

| call_id | Bucket fill (ms) | Bucket sum (ms) | Inner elapsed (ms) | Fill 占比 | Sum 占比 |
|---:|---:|---:|---:|---:|---:|
| 8 | 129.89 | 52.72 | 185.96 | 69.85% | 28.35% |
| 16 | 135.45 | 53.90 | 191.90 | 70.58% | 28.09% |
| 24 | 124.61 | 50.84 | 177.90 | 70.04% | 28.58% |
| 32 | 110.67 | 44.78 | 157.56 | 70.24% | 28.42% |
| 40 | 110.72 | 45.72 | 158.65 | 69.79% | 28.82% |
| **合计计时加权占比** | **611.34** | **247.96** | **871.97** | **约 70.11%** | **约 28.44%** |

该比例以五次 `inner_elapsed_ms` 合计为分母。更重的细粒度计时会抬高完整 Prove 时间，因此只适合分析该调用内部的相对成本结构，不能用来预测端到端优化收益。此前出现的约 73%–74% 是多个 MSM 调用内部计时的汇总，统计范围与本节单个 B-G2 auxiliary 调用不同。

## 3. Sapling Output：线程扩展和 Worker 调度

### 3.1 两组独立线程实验

| 数据集 | 线程数 | Prove 中位数 | 样本数 | 验证结果 |
|---|---:|---:|---:|---:|
| `sapling_output_thread_comparison.csv` | 1 | 514.784 ms | 5 | 5/5 |
| 同上 | 20 | 78.851 ms | 5 | 5/5 |
| `sapling_output_worker_proof_summary.csv` | 1 | 512.951 ms | 5 | 5/5 |
| 同上 | 2 | 270.691 ms | 5 | 5/5 |
| 同上 | 4 | 165.925 ms | 5 | 5/5 |
| 同上 | 8 | 99.003 ms | 5 | 5/5 |
| 同上 | 20 | 89.835 ms | 5 | 5/5 |

两组不同批次的 1→20 线程中位数变化分别约为 6.53x 与 5.71x。这两组结果应独立报告，不拼成统一 benchmark；它们不是算法优化对照，也不说明任何线程数对所有负载都最优。

### 3.2 Worker 调度线索

`results/tables/sapling_output_worker_task_start_summary.csv` 汇总了不同线程数下的任务启动延迟与 MSM 计时。在该组单线程测量中，B-G1 auxiliary 的 synchronous fallback 出现在 5/5 样本中，submit 阶段耗时中位数约 326.755 ms，而相应 MSM elapsed 中位数约 52.5 ms。

这提示后续应同时观测任务派发、fallback 和整次 Prove 的墙钟关键路径，但不能单凭这些计时确认根因，也不能证明优化调度一定带来端到端收益。多线程下任务可能重叠，不能将各调用 elapsed 相加后当作 MSM / Prove 比例。

## 4. Sapling Spend：调用级 MSM 与 Worker 提交计时

这组实验于 2026-10-10 在独立工作区 `D:\Research\zcash-sapling-engineering-msm-profile` 中进行，使用了修改过的 `vendor/bellman/src/multiexp.rs`。主仓库的冻结标签不包含这些计时插桩。

### 4.1 单线程批次摘要

- Batch ID：`1791634015130`
- 运行：5 次；证明检查通过：5/5；证明大小均为 192 bytes
- Prove 时间：8,020.464、7,996.506、8,176.483、8,320.273、7,896.238 ms
- Prove 中位数：**8,020.464 ms**
- 八次 MSM 调用 elapsed 合计 / Prove 比例：87.04%、87.62%、88.52%、86.01%、87.82%；中位数：**87.62%**
- 计时记录：40/40 条 MSM 调用、40/40 条 `task_start_delay_ms` 和 40/40 条 `submit_elapsed_ms`

该批次的运行时间高于正式未插桩 Spend 基线 3,385.716 ms，不能替换正式基线。MSM 占比仅描述这组插桩批次中的串行调用结构。

### 4.2 Spend 的八次 MSM 调用

| 调用序号 | MSM 查询映射 | 标量数量 | elapsed 中位数 |
|---:|---|---:|---:|
| 1 | H query, G1 | 131,071 | 3,530.905 ms |
| 2 | L query, G1 | 98,638 | 975.897 ms |
| 3 | A input query, G1 | 8 | 1.842 ms |
| 4 | A auxiliary query, G1 | 98,638 | 680.353 ms |
| 5 | B-G1 input query | 8 | 1.498 ms |
| 6 | B-G1 auxiliary query | 98,638 | 507.662 ms |
| 7 | B-G2 input query | 8 | 4.118 ms |
| 8 | B-G2 auxiliary query | 98,638 | 1,317.713 ms |

H query 是该批次最耗时的 MSM 调用之一，B-G2 auxiliary 也占据较大的单次成本。此处没有对 MSM 内部 bucket fill 等子阶段做更深层拆分。

### 4.3 Worker 提交与任务开始延迟

单线程批次中，调用编号 6、14、22、30、38 对应 B-G1 auxiliary。五次 `submit_elapsed_ms` 分别约为 5,607.894、5,681.407、5,862.091、5,872.212、5,652.460 ms；每次提交耗时都大致等于任务开始延迟与 MSM 执行时间之和。该现象与 Worker 队列回压或同步回退路径一致，但无法仅靠计时记录确认根因。

### 4.4 各线程配置的探索性结果

以下每种线程配置仅有一个独立进程批次、每批 5 次证明；这些结果用于观察调度路径，不用于宣称最佳线程数。

| 线程数 | Batch ID | Prove 中位数 | 最大任务开始延迟 | 最大 submit 耗时 |
|---:|---:|---:|---:|---:|
| 1 | `1791634015130` | 8,020.464 ms | 约 5,385 ms | 约 5,872 ms |
| 2 | `1791634566417` | 3,651.495 ms | 约 2,511 ms | 1.777 ms |
| 4 | `1791634631946` | 1,029.796 ms | 约 642 ms | 0.013 ms |
| 8 | `1791634682281` | 687.381 ms | 约 0.44 ms | 0.163 ms |
| 20 | `1791634733519` | 943.024 ms | 约 0.50 ms | 0.404 ms |

该数据不构成经多个独立进程重复验证的线程扩展曲线，不能据此声称 8 线程普遍最优。

## 5. 原始证据、版本绑定与解释边界

Spend profile 的主要实验日志、线程配置日志、原始 CSV 和线程对照表均已归档。主结果批次的实际源码 SHA-256、日志 SHA-256、源码差异 SHA-256、参数文件哈希、工具链和基础 commit 见：

`experiments/metadata/spend_msm_profile_1791634015130.md`

主要源码差异：

`experiments/metadata/source_patches/spend_msm_profile_vs_baseline.patch`

关键原始日志：

- `experiments/raw/logs/sapling_spend_msm_queue_profile_20261010_200606.log`：主分析批次，87.62% MSM-call elapsed share 的来源。
- `experiments/raw/logs/sapling_spend_msm_queue_2threads_20261010_201521.log`
- `experiments/raw/logs/sapling_spend_msm_queue_4threads_20261010_201624.log`
- `experiments/raw/logs/sapling_spend_msm_queue_8threads_20261010_201717.log`
- `experiments/raw/logs/sapling_spend_msm_queue_20threads_20261010_201805.log`
- `results/tables/sapling_spend_thread_queue_comparison.csv`：线程配置的派生对照表。

另外两份较早的单线程日志也已保留作探索过程记录，但不用于计算文中主分析批次的 87.62% 比例。各线程配置目前只有一个独立进程批次，不足以识别普遍最佳线程数。

这些实验没有实施或验证算法优化。它们的价值是进一步刻画已测工作负载中的 MSM 调用和 Worker 调度特征，为后续提出可检验的优化假设提供依据。
