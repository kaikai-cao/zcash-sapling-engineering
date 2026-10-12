# Sapling Spend 性能测量与瓶颈分析：阶段性研究总结

**研究对象：** Zcash Sapling Spend 证明生成路径  
**实验平台：** Intel Core i7-14700，Windows 11，Rust 1.98.1，Release 构建  
**工程仓库：** `kaikai-cao/zcash-sapling-engineering`  
**总结范围：** 现有基线与 2026-10-12 的单线程、20 线程可追溯联合诊断批次

## 1. 当前研究目标

本阶段的目标不是声称已经提出新的密码学算法，而是建立可复现的 Sapling 工程测量流程，识别 Spend 证明生成中的主要耗时路径，并形成后续优化可以验证的具体假设。测量重点包括整体 Prove 墙钟时间、Groth16 prover 阶段计时、Bellman MSM 调用计时、任务开始延迟和任务提交耗时。

## 2. 工程基线与实验边界

此前的形式化 Sapling Spend 基线记录为：

- Spend 电路约束数：98,777；辅助变量数：98,638。
- Spend 参数文件大小：47,958,396 bytes（约 45.74 MiB）。
- 证明编码大小：192 bytes。
- 形式化基线 Prove 中位耗时约 3,385.716 ms；Verify 中位耗时约 2.790 ms。

这些形式化基线数据来自先前的基线测量，不等同于本报告两组开启详细插桩的诊断批次。开启插桩会增加观测开销，因此不应将不同批次直接混作同一组测量，或仅凭其差值推断优化收益。

## 3. 两组可追溯联合诊断批次

| 项目 | 单线程诊断 | 20 线程诊断 |
|---|---:|---:|
| Batch ID | `1791801666809` | `1791802391142` |
| `RAYON_NUM_THREADS` | 1 | 20 |
| Outer Prove 中位数 | 3,535.699 ms | 578.335 ms |
| `create_proof_body` 中位数 | 3,533.094 ms | 575.654 ms |
| 证明验证 | 5/5 | 5/5 |
| MSM 调用记录 | 40 | 40 |
| MSM 提交计时记录 | 40 | 40 |
| 阶段计时记录 | 5 | 5 |
| `BELLMAN_WORKER_FALLBACK` 记录 | 5 | 0 |

按这两个诊断批次的中位数计算，20 线程 Outer Prove 加速约 **6.11×**，耗时下降约 **83.64%**。`create_proof_body` 加速约 **6.14×**，耗时下降约 **83.71%**。

两组报告记录了相同的核心插桩源码哈希、相同的 Sapling 依赖提交、相同的参数文件 SHA-256 与相同硬件环境。两个批次各运行 5 次且全部验证成功。它们足以支持这台机器、该工作负载下存在明显线程扩展性信号；样本量仍然有限，结论不应直接泛化到其他硬件和负载。

## 4. 阶段计时对比

以下为每个计时区间在对应批次的中位数。阶段值是插桩路径的计时区间，其中某些区间会包含异步任务派发、同步 fallback 或等待行为，不等同于独立的 CPU 成本清单。

| 阶段 | 单线程中位数 | 20 线程中位数 | 说明 |
|---|---:|---:|---|
| Circuit synthesis / constraints | 102.182 ms | 103.247 ms | 两组接近 |
| Worker / VK setup | 0.001 ms | 0.001 ms | 接近计时分辨率 |
| QAP / FFT / H preparation | 384.724 ms | 119.883 ms | 20 线程明显更快 |
| H-query access / dispatch | 5.771 ms | 6.102 ms | 两组相近，20 线程略高 |
| Assignment / query prep / dispatch | 2,428.592 ms | 13.714 ms | 差异最大；单线程计时受 fallback 同步执行影响 |
| Proof scalar terms | 1.506 ms | 1.966 ms | 均很小，20 线程略高 |
| Wait / assembly | 608.975 ms | 322.071 ms | 20 线程下仍是较大的剩余阶段 |
| Proof body total | 3,533.094 ms | 575.654 ms | 整体下降约 83.71% |

不能把表中各阶段的中位数机械相加，并要求结果等于证明主体的中位数；中位数不是逐次观测的可加统计量。应以每次运行中阶段和主体的闭合检查为准。本次各批次的脚本均检查了逐次阶段计时闭合误差，最大误差在毫秒千分位附近。

## 5. MSM 调用对比

每类调用有 5 个观测。下表是单次调用 `elapsed_ms` 的批次内中位数：

| MSM query | 指数数量 | 单线程 | 20 线程 | 单线程 / 20 线程 |
|---|---:|---:|---:|---:|
| H-query G1 | 131,071 | 1,494.115 ms | 346.630 ms | 4.31× |
| L-query G1 | 98,638 | 408.817 ms | 327.595 ms | 1.25× |
| A-input G1 | 8 | 0.955 ms | 0.605 ms | 1.58× |
| A-aux G1 | 98,638 | 284.678 ms | 324.591 ms | 0.88× |
| B-G1 input | 8 | 0.785 ms | 0.916 ms | 0.86× |
| B-G1 auxiliary | 98,638 | 214.134 ms | 322.304 ms | 0.66× |
| B-G2 input | 8 | 2.172 ms | 1.714 ms | 1.27× |
| B-G2 auxiliary | 98,638 | 600.879 ms | 317.585 ms | 1.89× |

H-query G1 在两个批次中都是重要的单项 MSM 耗时，B-G2 auxiliary 也是 20 线程下仍需关注的较大调用。部分调用在 20 线程时单次 `elapsed_ms` 并未下降，可能受到与其他 MSM 并发、资源竞争和任务执行顺序的影响。它们不能单独代表整体墙钟时间。

特别注意：20 线程的 MSM `elapsed_ms` 之和可以超过整个 `create_proof_body`，因为各 MSM 任务的执行区间会重叠。比如 20 线程诊断中的 `MSM elapsed/body share median` 约为 285.87%，它不是“证明时间中 MSM 占了 285.87%”，也不是可消除的时间比例。

## 6. Worker fallback：当前最具体的候选机制

单线程原始 stderr 每次证明都包含 `BELLMAN_WORKER_FALLBACK previous_count=5 max_count=4 rayon_threads=1`。同时，B-G1 auxiliary MSM 对应的 `submit_elapsed_ms` 中位数约为 2,421.059 ms，而该调用自身 `elapsed_ms` 中位数约为 214.134 ms；同批次 `assignment_query_prep_dispatch` 阶段中位数约为 2,428.592 ms。

20 线程批次没有 fallback 记录。其 MSM 提交耗时总体在毫秒量级，B-G1 auxiliary 对应的 `submit_elapsed_ms` 中位数约为 0.002 ms；同批次 `assignment_query_prep_dispatch` 阶段中位数约为 13.714 ms。

这组共同变化与源码中的同步 fallback 路径吻合：当 worker 的提交计数超过阈值时，任务会在提交线程的同步调用上下文里执行，从而使该提交调用等待更长时间。现有证据强烈支持“单线程下 fallback 路径与主线程阻塞相关”这一判断。

**因果边界：** 线程数变化同时改变了 MSM 的并行计算能力和任务执行调度，因此这两个批次还不能把全部 6.11× 加速单独归因于 fallback。若后续要形成更强的因果结论，需要在可控条件下独立改变 fallback 行为或相关 worker 机制，并保持其余配置尽可能一致。

## 7. 计时字段如何解释

- `Outer Prove`：证明调用的墙钟耗时，适合比较端到端性能。
- `create_proof_body_ms`：插桩代码定义的证明主体墙钟计时区间。
- `elapsed_ms`：单个 MSM 实际执行区间耗时；多个任务可并发，区间会重叠。
- `task_start_delay_ms`：从该任务记录的提交时间点到任务开始执行的时间差；在同步 fallback 情况下，解读还需结合执行上下文。
- `submit_elapsed_ms`：调用 `Worker::compute` 的提交路径耗时。进入同步 fallback 时，它可能包含在提交调用中执行的计算和等待，因此不应当作为纯调度开销。

以上字段是不同、可能重叠的测量区间，不能彼此相加，也不能都被解释成互斥的耗时构成。

## 8. 当前阶段结论

1. 已建立可复现的 Spend 单线程和 20 线程联合诊断流程，每批均关联 batch ID、参数文件身份、核心源码哈希、原始 stdout/stderr、5 次验证记录、40 条 MSM 调用记录、40 条提交计时和 5 条阶段计时。
2. 在当前硬件与该测试工作负载下，20 线程将 Outer Prove 中位数从 3,535.699 ms 降至 578.335 ms，体现约 6.11× 的线程扩展性。
3. 最大阶段差异在 Assignment / Query prep / dispatch。结合 fallback 记录和 B-G1 auxiliary 提交时长，这部分差异很可能主要与单线程同步 fallback 和其触发的主线程阻塞有关，但现有对照尚未隔离其独立因果效应。
4. 在并行执行下，H-query G1 和 B-G2 auxiliary 仍是值得进一步检查的 MSM 计算热点；其单次计时与整体证明墙钟时间必须分开解释。
5. 本阶段没有更改密码学算法，也未声称已获得算法层面的优化。当前产出是工程性能剖析、可追溯实验和后续优化假设。

## 9. 推荐后续工作

1. 将已生成的对比脚本、两张 CSV 对比表、三张图和本报告纳入 Git，确保这些派生产物能从已归档的原始记录重新生成。
2. 基于现有源代码，设计一个只改变 worker fallback 条件或策略的控制实验；记录所有配置和源码差异，并用相同证明任务做多轮对照。若不适合直接修改 fallback，可先进一步增加 worker 队列/同步执行路径的观测点。
3. 对 H-query G1 与 B-G2 auxiliary 分别做更细的 MSM 内部测量；在保持电路、参数和其他环境不变的情况下，观察窗口大小、并行配置和工作分块策略对端到端 Prove 的影响。
4. 每次改变先提出假设、做基线和对照、保存原始数据及哈希、检查证明验证，并避免将计时插桩诊断数据与正式性能基线混在同一统计组内。

## 10. 可复核的原始批次报告

- 单线程联合诊断报告：`experiments/metadata/sapling_spend_combined_profile_1791801666809.md`
- 20 线程联合诊断报告：`experiments/metadata/sapling_spend_combined_profile_1791802391142.md`
- 线程对比分析报告：`experiments/metadata/sapling_spend_thread_profile_comparison_1791801666809_vs_1791802391142.md`
- 线程阶段对比表：`results/tables/sapling_spend_thread_profile_comparison_1791801666809_vs_1791802391142.csv`
- MSM 调用对比表：`results/tables/sapling_spend_msm_call_comparison_1791801666809_vs_1791802391142.csv`

本报告是阶段性工程分析总结，不替代原始 CSV 和日志。所有最终结论应当回溯到上述批次报告及原始观测。
