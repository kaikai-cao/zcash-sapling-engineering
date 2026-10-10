# Frozen Groth16 Baseline 与 Sapling 的规模及成本结构对照

**分析日期：** 2026-10-10  
**数据来源：** 已提交的合成基线记录，以及 `zcash-sapling-engineering/experiments/raw/logs/` 中的 Sapling Output 剖析日志。

## 1. 核心结论

1. 冻结合成基线一条带阶段统计的记录中，MSM 累计耗时占 Prove 的 **91.60%**（2,816.798 / 3,075.022 ms）。
2. 真实 Sapling **Output、单线程**的两份较轻量剖析日志给出了相互印证的结果。排除每次进程／实验内第一轮后，`sapling_output_msm_profile_sizes_1threads.log` 的 run 2–5 中，8 次 MSM 调用耗时合计的中位数约为 **487.710 ms**，Prove 中位数约为 **522.315 ms**，逐轮 `MSM sum / Prove` 比例为 **93.17%–93.51%**，中位数 **93.41%**。另一份 `sapling_output_msm_op_counts_1threads_smoke.log` 的 run 2–5 比例为 **93.03%–93.38%**，中位数 **93.19%**。因此，现有证据支持“MSM 是单线程 Sapling Output 证明耗时的主导部分”这一范围明确的结论。
3. 更细的 `sapling_output_msm_stages_1threads.log` 显示，在 run 2–5 中，MSM 内部 bucket fill 的分块计时合计约占 MSM 调用内部阶段计时的 **73%–74%**；bucket sum 约占 **23%–24%**。但这份细粒度计时会明显增加运行时间（该日志 Prove 约 581–743 ms，而较轻量剖析的稳态 Prove 约 521–523 ms），所以它适合定位内部成本结构，不应用于报告绝对 Prove 性能。
4. **不能推广到所有 Sapling 证明。** 目前已核验的 MSM 占比来自 Output 单线程。Spend 还缺少同口径剖析。多线程时 MSM 调用并行重叠，逐调用 `elapsed_ms` 之和可能超过整次 Prove；不能用该和计算 MSM 占比。20-thread 日志中 `post_dispatch_wait_assembly` 在常规后续轮次约占 Prove 的 70%–72%，这说明并行 MSM 完成／结果组装阶段很重要，但该阶段不是纯 MSM 计时。

## 2. 已记录结果

| 指标 | 冻结合成 Groth16 基线 | Sapling Spend | Sapling Output |
|---|---:|---:|---:|
| 曲线 / 实现 | BN254 / arkworks 0.6.0 | BLS12-381 / Sapling 的 Bellman/Groth16 路径 | BLS12-381 / Sapling 的 Bellman/Groth16 路径 |
| 工作负载标记 | `N = 100,000` | 真实 Spend 电路 | 真实 Output 电路 |
| 约束数 | 不能从 `N` 标签直接推定 | 98,777 | 7,827 |
| 参数文件大小 | 当前对照摘录中没有可比字段 | 45.737 MiB | 3.426 MiB |
| 正式 Prove 统计 | 单次带剖析记录：3,075.022 ms | 正式批次中位数：3,385.716 ms | 正式批次中位数：514.853 ms |
| 正式证明大小 | 当前对照摘录中没有可核验的同口径值 | 192 bytes | 192 bytes |
| MSM 成本结构 | MSM 2,816.798 ms / Prove 3,075.022 ms = 91.60% | 尚未得到可对账占比 | 单线程较轻量剖析后续轮次中位占比 93.41%；独立日志复核为 93.19% |

注：合成基线的 `N=100,000` 是基准程序的工作负载参数；在未核对其具体生成逻辑与约束计数前，不能把它直接当成 100,000 个 Sapling 意义上的约束。合成基线的一次记录、Sapling 正式批次中位数和 Sapling 插桩剖析结果有不同测量口径；不能用它们宣称哪个证明系统更快。

## 3. Sapling Output 单线程 MSM 证据

主结果来自 `sapling_output_msm_profile_sizes_1threads.log`。下表是每轮调用级 MSM elapsed 的合计除以该轮完整 Prove 时间；run 1 作为首轮单独保留，稳态描述使用 run 2–5。

| Run | Prove (ms) | 8 次 MSM elapsed 合计 (ms) | MSM / Prove |
|---:|---:|---:|---:|
| 1 | 558.825 | 482.323 | 86.31% |
| 2 | 521.122 | 487.116 | 93.47% |
| 3 | 521.944 | 488.044 | 93.51% |
| 4 | 522.686 | 487.909 | 93.35% |
| 5 | 523.243 | 487.510 | 93.17% |

第二份 `sapling_output_msm_op_counts_1threads_smoke.log` 的后续 run 2–5 分别为 93.03%、93.38%、93.34%、93.03%。两份日志的后续 Prove 均在约 518–523 ms，MSM 占比结论一致。

这是调用级 MSM elapsed 合计，不是任意线程配置下都能使用的计算方式。单线程记录中，这些调用顺序执行，合计与完整 Prove 的占比有解释力；多线程情况下，调用会重叠，逐调用 elapsed 之和不是墙钟时间。

## 4. MSM 内部进一步定位

`sapling_output_msm_stages_1threads.log`加入了分块级计时。run 2–5 的汇总如下：

| Run | MSM 调用 elapsed 合计 (ms) | Bucket fill 计时合计 (ms) | Bucket sum 计时合计 (ms) | Bucket fill / MSM 调用计时 |
|---:|---:|---:|---:|---:|
| 2 | 701.132 | 521.113 | 164.237 | 74.32% |
| 3 | 573.722 | 419.325 | 139.658 | 73.05% |
| 4 | 552.813 | 405.810 | 131.450 | 73.41% |
| 5 | 547.109 | 402.364 | 131.825 | 73.55% |

这些计时反映的是分块计时的累计值，且启用更细粒度的探针后，完整 Prove 时间明显升高。因此，这张表支持的结论是：**在该单线程 Output 实现路径中，bucket fill 是 MSM 内部最值得优先研究的成本段**；它不支持把这份细粒度日志里的绝对耗时作为正式性能基线，也不证明优化 bucket fill 必然带来同等幅度的端到端提升。

## 5. Output 的 8 次 MSM 调用映射

对照已提交的 `vendor/groth16/src/prover.rs` 中 `multiexp` 的调用顺序与日志内的指数数量／window，Output 的单线程日志可以映射为：H query、L query、A input、A auxiliary、B-G1 input、B-G1 auxiliary、B-G2 input、B-G2 auxiliary。run 2–5 的两份较轻量日志分别得到下表数值；这不依赖把多线程调用耗时相加。

| MSM 调用 | 群 | exponent_count | window | profile-size 日志中位数 (ms) | op-count 日志中位数 (ms) |
|---|---|---:|---:|---:|---:|
| H query | G1 | 8,191 | 10 | 129.125 | 127.084 |
| L query | G1 | 7,821 | 9 | 82.987 | 82.089 |
| A input query | G1 | 6 | 3 | 0.938 | 1.033 |
| A auxiliary query | G1 | 7,821 | 9 | 65.012 | 64.723 |
| B G1 input query | G1 | 6 | 3 | 0.772 | 0.890 |
| B G1 auxiliary query | G1 | 7,821 | 9 | 53.180 | 53.738 |
| B G2 input query | G2 | 6 | 3 | 2.237 | 2.273 |
| B G2 auxiliary query | G2 | 7,821 | 9 | **152.731** | **151.694** |

目前单次调用的最大成本是 B-G2 auxiliary query，其次为 H query、L query 和 A auxiliary query。按 profile-size 日志的稳态轮次计算，G1 相关调用累计约 332.5 ms，G2 相关调用累计约 155.1 ms；其中 B-G2 auxiliary 单个调用约 153 ms。逐调用数据、最小／最大值和两份日志的复核数值保存在 `results/tables/sapling_output_msm_query_profile.csv`。

## 6. 哪些比较成立、哪些仍不成立

| 问题 | 当前结论 | 依据／限制 |
|---|---|---|
| 合成基线 MSM 是否重要 | 是，该次记录为 91.60% | 一次带阶段剖析的合成基线记录 |
| Sapling Output 单线程 MSM 是否主导 Prove | 有较强证据，是 | 两份较轻量日志的后续轮次占比约 93.2%–93.4% |
| Sapling Output 的 MSM 内部主要成本段 | bucket fill 值得优先研究 | 更细插桩显示 bucket fill 约占 MSM 内部阶段计时的 73%–74%，但计时插桩较重 |
| Sapling Spend 的 MSM 占比 | 未确定 | 还没有同口径、同一完整 Prove 的剖析汇总 |
| Sapling 20-thread 的 MSM 占比 | 不能用逐调用 elapsed 直接求和 | 并行调用重叠；wait/assembly 阶段只能作为并行关键路径的近似观察 |
| BN254 合成基线与 BLS12-381 Sapling 谁更快 | 不成立 | 电路、曲线、实现、负载和统计口径不同 |
| 参数文件大小是否等于 CRS / PK / VK 大小 | 不成立 | 参数文件与具体证明系统对象是不同实体 |

## 7. 下一步研究问题

下一步不再泛泛验证“MSM 是否重要”，而应把已知结论推进到可优化的具体对象：

1. 对 Spend 以同样的单线程、调用级计时方式收集一份完整 Prove 剖析，确认大电路是否也由 MSM 主导。
2. 已通过 `vendor/groth16/src/prover.rs` 对 Output 的 8 次调用做了查询／群类型映射；下一步把同样的标签与剖析应用到 Spend，并确认大电路下的成本排序是否一致。
3. 若要比较多线程优化，使用整体等待／关键路径时间或线程任务阶段的墙钟指标；不要相加并行调用的各自 elapsed。
4. 优先检查 bucket fill 内的点加操作、桶分配与任务切分；用每阶段成本占比、点加计数和完整 Prove 时间同时评价优化，避免只优化局部微基准。
