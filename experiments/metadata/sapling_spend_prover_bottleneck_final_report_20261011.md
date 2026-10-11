# Sapling Spend Groth16 Prover：阶段性瓶颈定位报告

- 日期：2026-10-11
- 研究目标：定位 Sapling Spend Groth16 Prover 的主要性能成本，不进行算法优化。
- 工程：zcash-sapling-engineering
- 环境：Windows 11、Rust Release、Sapling Groth16、BLS12-381
- 依赖：sapling-crypto 0.9.0、bellman 0.15.0、groth16 0.2.0

## 1. 已完成的工作

- 复现 Sapling Spend / Output proof generation 与 verification。
- 校验参数文件，记录参数体量、电路规模和进程资源。
- 建立 Prove / Verify 基准记录。
- 为 Groth16 Prover、Bellman MSM 和 Worker 路径增加诊断计时。
- 完成 Spend 阶段计时和八类 MSM 调用的分析。
- 完成 1、2、4、8、16、20 线程扩展实验。
- 保存原始 CSV、汇总表和分析记录。

本阶段关注的是测量、成本分析与瓶颈定位，没有实施或验证算法级优化。

## 2. 必须分开的实验批次

| 数据集 | Prove 中位数 | 用途 |
|---|---:|---|
| 正式参考基准 batch `1791613854129` | 3385.716 ms | 正式参考结果 |
| Spend 阶段计时批次 | 3411.271 ms | 内部阶段归因 |
| 单独的关闭 profiling 验证批次 | 7030.150 ms | 异常待解释，不作为正式基线 |
| 线程扩展批次的 1 线程组 | 3499.607 ms | 该线程扩展批次内部的加速比参照 |
| 独立的 MSM 调用级插桩批次 | 6858.210 ms | MSM 调用级成本分析 |

这些数值来自不同实验批次，不能拼接、混合或取平均。

尤其是关闭 profiling 的验证批次中位数为 7030.150 ms，明显高于正式参考基准和后续线程扩展批次的 1 线程结果。现有证据没有确认差异的原因，因此不能直接归因于 profiling 插桩、Worker 调度或 CPU 状态。

## 3. 阶段级计时

Spend 阶段计时批次中，`create_proof_body_ms` 的中位数为 3411.215 ms。

| 计时字段 | 中位数 |
|---|---:|
| circuit_synthesis_constraints_ms | 100.876 ms |
| worker_vk_setup_ms | 0.003 ms |
| qap_fft_h_exponent_prep_ms | 379.312 ms |
| h_query_access_dispatch_ms | 0.035 ms |
| assignment_query_prep_dispatch_ms | 2337.731 ms |
| proof_scalar_terms_ms | 1.502 ms |
| wait_and_assembly_ms | 591.827 ms |
| create_proof_body_ms | 3411.215 ms |

这些阶段记录在每轮运行中与 body 计时基本闭合，存在毫秒精度的舍入差异。

其中，`assignment_query_prep_dispatch_ms` 是最大的主线程计时区间。但不能把它直接解释为纯赋值准备成本：Bellman Worker 的同步 fallback 路径可能执行或排空已提交的任务，使实际计算工作被计入提交调用所在的主线程时间区间。

因此，该表描述的是当前源码路径中的计时区间，而不是所有底层工作完全互斥的成本分解。

## 4. MSM 调用级分析

在单线程 Spend 诊断批次中，观察到八类 MSM 调用。

| MSM 调用 | Exponent 数量 | 执行耗时中位数 |
|---|---:|---:|
| H query G1 | 131071 | 1446.624 ms |
| L query G1 | 98638 | 398.915 ms |
| A input G1 | 8 | 0.950 ms |
| A auxiliary G1 | 98638 | 278.323 ms |
| B-G1 input | 8 | 0.770 ms |
| B-G1 auxiliary | 98638 | 211.220 ms |
| B-G2 input | 8 | 2.200 ms |
| B-G2 auxiliary | 98638 | 590.730 ms |

在该批次中，H query G1 是最大的单次 MSM 调用；B-G2 auxiliary、L query、A auxiliary 和 B-G1 auxiliary 也有明显耗时。

八次调用的 elapsed 累计值约占该次外层 Prove 时间的 85%–86%。这个比例只描述该特定的单线程插桩批次，不应直接推广到其他线程配置或不同的计时口径。

### Worker fallback 观察

单线程诊断日志中，五轮证明均记录了 Worker fallback。

对于 B-G1 auxiliary 调用：

| 计时指标 | 中位数 |
|---|---:|
| submit_elapsed_ms | 2334.96 ms |
| task_start_delay_ms | 2123.68 ms |
| 该调用 elapsed_ms | 211.22 ms |

提交耗时接近任务启动延迟与本次调用执行耗时之和。这支持一个有限判断：同步 fallback 路径会影响先前排队工作和当前调用在主线程计时中的归属。

这不意味着约 2.1 秒全部是 CPU 空闲或纯调度开销；排队任务可能在这段时间内被实际执行。

## 5. 线程扩展实验

原始数据：

`experiments/raw/csv/sapling_spend_thread_scaling_20261011_202051.csv`

汇总表：

`results/tables/sapling_spend_thread_scaling_summary_20261011.csv`

每种线程配置重复五次，共 30 次证明，30/30 验证成功。

| Rayon 线程数 | Prove 中位数 | 测量范围 | 相对 1 线程加速比 |
|---:|---:|---:|---:|
| 1 | 3499.607 ms | 3480.081–3544.655 ms | 1.00× |
| 2 | 1831.514 ms | 1825.416–1874.669 ms | 1.91× |
| 4 | 1008.486 ms | 997.631–1051.515 ms | 3.47× |
| 8 | 769.625 ms | 659.059–1178.840 ms | 4.55× |
| 16 | 591.082 ms | 572.541–639.469 ms | 5.92× |
| 20 | 596.008 ms | 565.040–627.991 ms | 5.87× |

本批次观察到：

1. 增加线程数显著降低了 Prove 时间。
2. 从 1 线程到 16 线程，中位数加速比约为 5.92×。
3. 20 线程的中位数没有进一步下降。
4. 8 线程组波动明显，最后两轮证明时间与验证时间都升高。

这些结果只描述本批次。它们不能证明 16 线程是普遍最优配置，也不能证明已经达到硬件极限或确定了收益递减的根因。

## 6. 阶段性结论

当前有证据支持以下判断：

1. 对已测的 Sapling Spend 工作负载，证明生成的时间成本远高于验证。
2. 在所测的单线程诊断批次中，MSM 是主要计算成本来源之一；H query G1 是最大的单次 MSM 调用。
3. Worker fallback 影响了部分 MSM 工作在主线程计时区间中的归属。
4. 本次线程扩展批次显示，多线程能显著降低 Prove 时间，但收益并非随线程数线性增长。
5. 目前没有实施或验证任何算法级优化。

本阶段完成的是工程复现、测量和初步瓶颈定位，而不是优化成功的验证。

## 7. 尚未解决的问题

- 7030.150 ms 的关闭 profiling 验证批次与其他批次存在明显差异，原因尚未确定。
- 当前阶段计时尚不能视为底层并行工作的完全互斥成本分解。
- 8 线程组出现波动，其原因需要独立证据才能判断。
- 当前证据没有确定 MSM 内部所有成本的根因，也没有验证具体优化能带来多少端到端收益。

下一阶段若继续研究，应先针对这些问题提出可检验的假设，再决定是否开展优化实验。