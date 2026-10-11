# Frozen Groth16 Baseline 与 Sapling 的规模及成本结构对照

**分析日期：** 2026-10-10  
**文档修订：** 2026-10-11

**数据来源：** 冻结合成基线实验记录，以及 `zcash-sapling-engineering/experiments/raw/logs/` 中的 Sapling Spend / Output 剖析日志。

## 1. 核心结论

1. 冻结合成 Groth16 基线的一条带阶段统计记录中，MSM 累计耗时占 Prove 的 **91.60%**（2,816.798 / 3,075.022 ms）。这是一条具体实验记录，不能直接视为多次测量的稳定统计结论。

2. 真实 Sapling **Output、单线程**的两份较低开销剖析日志相互印证。排除每份日志的首轮后，`sapling_output_msm_profile_sizes_1threads.log` 的 run 2–5 中，8 次 MSM 调用耗时合计的中位数约为 **487.710 ms**，Prove 中位数约为 **522.315 ms**，逐轮 `MSM sum / Prove` 比例为 **93.17%–93.51%**，中位数为 **93.41%**。另一份 `sapling_output_msm_op_counts_1threads_smoke.log` 的 run 2–5 比例为 **93.03%–93.38%**，中位数为 **93.19%**。因此，现有证据支持“MSM 是当前测得的 Sapling Output 单线程证明路径的主导成本”这一范围明确的结论。

3. 更细的 `sapling_output_msm_stages_1threads.log` 显示，run 2–5 中 MSM 内部 bucket fill 的分块计时合计约占 MSM 调用内部阶段计时的 **73%–74%**，bucket sum 约占 **23%–24%**。但细粒度计时会明显增加运行时间：该日志 Prove 约为 581–743 ms，而较低开销剖析的稳态 Prove 约为 521–523 ms。因此，这份日志适合定位内部成本结构，不适合报告正式 Prove 性能，也不能直接用于预测优化后的端到端收益。

4. **不能把以上结论无条件推广到所有 Sapling 证明。** Spend 已有一批单线程、重度插桩的探索性 MSM profile：批次 `1791634015130` 的 Prove 中位数为 **8,020.464 ms**，八次 MSM 调用耗时之和与 Prove 时间之比的逐轮中位数为 **87.62%**，5 次证明均验证成功。但该批次受到重度插桩影响，不能替代正式 Spend 基线，也不能与 Output 的低开销 profile 直接比较绝对耗时。多线程时 MSM 调用可能并行重叠，逐调用 `elapsed_ms` 之和不能直接当作整个 Prove 的墙钟耗时。20-thread 日志中，`post_dispatch_wait_assembly` 在常规后续轮次约占 Prove 的 70%–72%，提示并行 MSM 完成与结果组装阶段值得继续研究，但该阶段不是纯 MSM 计时。

## 2. 已记录结果

| 指标 | 冻结合成 Groth16 基线 | Sapling Spend | Sapling Output |
|---|---|---|---|
| 曲线 / 实现 | BN254 / arkworks 0.6.0 | BLS12-381 / Sapling 的 Bellman/Groth16 路径 | BLS12-381 / Sapling 的 Bellman/Groth16 路径 |
| 工作负载标记 | `N = 100,000` | 真实 Spend 电路 | 真实 Output 电路 |
| 约束数 | 不能从 `N` 标签直接推定 | 98,777 | 7,827 |
| 参数文件大小 | 当前对照摘录中没有可比字段 | 45.737 MiB | 3.426 MiB |
| 正式 Prove 统计 | 单次带剖析记录：3,075.022 ms | 正式批次中位数：3,385.716 ms | 正式批次中位数：514.853 ms |
| 正式证明大小 | 当前对照摘录中没有可核验的同口径值 | 192 bytes | 192 bytes |
| MSM 成本结构 | MSM 2,816.798 ms / Prove 3,075.022 ms = 91.60% | 探索性重度插桩批次 `1791634015130`：87.62%；不代表正式基线 | 单线程低开销剖析后续轮次中位占比 93.41%；独立日志复核为 93.19% |

注：

- 合成基线的 `N=100,000` 是基准程序的工作负载参数。在未核对其具体生成逻辑与约束计数前，不能把它直接当成 100,000 个 Sapling 意义上的约束。
- 合成基线的一次记录、Sapling 正式批次中位数和 Sapling 插桩剖析结果具有不同测量口径，不能据此直接宣称哪个系统更快。
- Spend 的 87.62% 来自重度插桩的探索性 profile；正式 Spend 基线的 Prove 中位数仍为 3,385.716 ms。
- Output 的 93.41% 和 93.19% 来自两份较低开销剖析日志的后续轮次，不是正式基线批次本身的 MSM 计时结果。

## 3. Sapling Output 单线程 MSM 证据

主结果来自 `sapling_output_msm_profile_sizes_1threads.log`。下表是每轮调用级 MSM elapsed 的合计除以该轮完整 Prove 时间。run 1 单独保留，稳态描述使用 run 2–5。

| Run | Prove (ms) | 8 次 MSM elapsed 合计 (ms) | MSM / Prove |
|---:|---:|---:|---:|
| 1 | 558.825 | 482.323 | 86.31% |
| 2 | 521.122 | 487.116 | 93.47% |
| 3 | 521.944 | 488.044 | 93.51% |
| 4 | 522.686 | 487.909 | 93.35% |
| 5 | 523.243 | 487.510 | 93.17% |

第二份 `sapling_output_msm_op_counts_1threads_smoke.log` 的后续 run 2–5 比例分别为 93.03%、93.38%、93.34%、93.03%。两份日志的后续 Prove 均在约 518–523 ms，MSM 占比结论一致。

这是调用级 MSM elapsed 的累计值。在单线程记录中，这些调用顺序执行，其合计与完整 Prove 的占比具有解释力。多线程情况下，调用可能重叠，因此不能把逐调用 elapsed 之和直接视为墙钟时间，也不能据此计算多线程的 MSM / Prove 占比。

## 4. MSM 内部进一步定位

`sapling_output_msm_stages_1threads.log` 加入了分块级计时。run 2–5 的汇总如下：

| Run | MSM 调用 elapsed 合计 (ms) | Bucket fill 计时合计 (ms) | Bucket sum 计时合计 (ms) | Bucket fill / MSM 调用计时 |
|---:|---:|---:|---:|---:|
| 2 | 701.132 | 521.113 | 164.237 | 74.32% |
| 3 | 573.722 | 419.325 | 139.658 | 73.05% |
| 4 | 552.813 | 405.810 | 131.450 | 73.41% |
| 5 | 547.109 | 402.364 | 131.825 | 73.55% |

这些计时反映的是分块计时的累计值。启用更细粒度的探针后，完整 Prove 时间明显升高。

因此，这张表支持的结论是：**在当前被测的 Output 单线程实现路径中，bucket fill 是 MSM 内部值得优先研究的成本段。** 它不支持把这份细粒度日志中的绝对耗时当成正式性能基线，也不证明优化 bucket fill 必然带来同等幅度的端到端提速。

需要进一步研究的问题包括：点加操作的成本、桶分配与初始化、任务切分，以及不同阶段对整体证明时间的实际贡献。

## 5. Output 的 8 次 MSM 调用映射

对照已提交的 `vendor/groth16/src/prover.rs` 中 `multiexp` 的调用顺序，以及日志中的指数数量和 window，Output 的单线程日志可以映射为：H query、L query、A input、A auxiliary、B-G1 input、B-G1 auxiliary、B-G2 input、B-G2 auxiliary。

run 2–5 的两份较低开销日志得到下表数值。这里比较的是单线程下各个调用的 elapsed，不依赖将多线程调用耗时相加。

| MSM 调用 | 群 | exponent_count | window | profile-size 日志中位数 (ms) | op-count 日志中位数 (ms) |
|---|---|---:|---:|---:|---:|
| H query | G1 | 8,191 | 10 | 129.125 | 127.084 |
| L query | G1 | 7,821 | 9 | 82.987 | 82.089 |
| A input query | G1 | 6 | 3 | 0.938 | 1.033 |
| A auxiliary query | G1 | 7,821 | 9 | 65.012 | 64.723 |
| B-G1 input query | G1 | 6 | 3 | 0.772 | 0.890 |
| B-G1 auxiliary query | G1 | 7,821 | 9 | 53.180 | 53.738 |
| B-G2 input query | G2 | 6 | 3 | 2.237 | 2.273 |
| B-G2 auxiliary query | G2 | 7,821 | 9 | **152.731** | **151.694** |

在这两份 Output 单线程剖析记录中，单次调用的最大成本是 B-G2 auxiliary query，其次是 H query、L query 和 A auxiliary query。按 profile-size 日志的稳态轮次计算，G1 相关调用累计约 332.5 ms，G2 相关调用累计约 155.1 ms；其中 B-G2 auxiliary 单次调用约为 153 ms。

逐调用数据、最小／最大值和两份日志的复核数值保存在 `results/tables/sapling_output_msm_query_profile.csv`。

以上排名仅适用于当前测量的 Output 单线程路径，不应直接推广到 Spend 或其他线程配置。

## 6. 哪些比较成立、哪些仍不成立

| 问题 | 当前结论 | 依据／限制 |
|---|---|---|
| 合成基线 MSM 是否重要 | 是，该次记录为 91.60% | 一次带阶段剖析的合成基线记录 |
| Sapling Output 单线程 MSM 是否主导 Prove | 有较强证据，是 | 两份较低开销日志的后续轮次占比约 93.2%–93.4% |
| Sapling Output 的 MSM 内部主要成本段 | bucket fill 值得优先研究 | 更细插桩显示 bucket fill 约占 MSM 内部阶段计时的 73%–74%，但计时插桩较重 |
| Sapling Spend 的 MSM 占比 | 已有探索性结果，但尚未完成可直接对照的 profile | 重度插桩批次 `1791634015130` 的逐轮 MSM-call elapsed / Prove 比例中位数为 87.62%；仍需相近计时口径的低开销 profile 进一步验证 |
| Sapling 20-thread 的 MSM 占比 | 不能直接用逐调用 elapsed 求和 | 并行调用可能重叠；wait/assembly 阶段可以辅助观察并行关键路径，但不是纯 MSM 计时 |
| BN254 合成基线与 BLS12-381 Sapling 谁更快 | 不成立 | 电路、曲线、实现、负载和统计口径不同 |
| 参数文件大小是否等于 CRS / PK / VK 大小 | 不成立 | 参数文件与具体证明系统对象是不同实体 |

## 7. 下一步研究问题

下一步不再泛泛验证“MSM 是否重要”，而应将已有结论推进到更具体、可检验的研究问题：

1. **对 Spend 采集低开销、同计时边界的 profile。** 检验调用级 MSM 分布能否在降低插桩开销后复现，并进一步确认大电路下的主要成本段。重度插桩批次保留作探索性证据，不替代正式基线。

2. **统一 Spend 与 Output 的 MSM 调用映射。** 对每次调用记录查询类型、群类型、标量数量、window 和 elapsed。只有在插桩强度与计时口径足够接近时，才进行两种电路的成本结构对照。

3. **以完整 Prove 的墙钟时间和关键路径衡量多线程行为。** 需要区分任务派发、任务启动、MSM 执行、等待与结果组装，不能将存在并行重叠的各调用 elapsed 简单相加。

4. **进一步拆分 bucket fill 的内部成本。** 关注点加操作、桶分配、任务切分及同步开销。评价候选优化时，同时报告局部阶段计时、完整 Prove 时间、证明验证结果和资源消耗，避免只在微基准上取得改善，却没有端到端收益。
