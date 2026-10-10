# Zcash Sapling / Groth16 工程基线：阶段总结

**阶段状态：** 第一轮真实 Sapling 工程基线已建立并冻结；当前完成了核心性能测量与候选热点定位，但尚未实现或验证算法优化。  
**测量日期：** 2026-10-10  
**Sapling 源码：** `sapling-crypto 0.9.0`，commit `88a7946b4a3066787776e11f0a502654167e022d`  
**正式基线环境：** Windows 11、Intel Core i7-14700、32 GB RAM、Rust 1.98.1、Release、`RAYON_NUM_THREADS=1`、BLS12-381 Groth16。

## 1. 工程规模与参数文件

| 指标 | Spend | Output |
|---|---:|---:|
| R1CS 约束数量 | 98,777 | 7,827 |
| 辅助变量数量 | 98,638 | 7,821 |
| 公开输入（不含常数 1） | 7 | 5 |
| 输入变量（含常数 1） | 8 | 6 |
| 估算 domain size | 131,072 | 8,192 |
| 参数文件大小 | 45.737 MiB | 3.426 MiB |
| 参数文件 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |

约束与变量数量来自 counting ConstraintSystem。Domain size 是按约束数向上取整到二次幂的估算值，并非直接读取运行时域对象。参数文件大小不等价于独立的 CRS、Proving Key 或 Verifying Key 大小。

完整的 BLAKE2b-512 哈希及参数元数据保存在 `results/tables/engineering_parameters.csv`；参数文件大小和哈希校验记录在 `experiments/metadata/parameter_validation.csv`。参数文件保存在仓库之外，不应提交到 Git。

## 2. 正式证明与验证基线

正式汇总只选择指定批次，每种电路各有 5 次证明与验证测量。两组都使用 Release 配置和一个 Rayon 线程。

| 指标 | Spend | Output |
|---|---:|---:|
| 正式 batch ID | `1791613854129` | `1791549582046` |
| Prove 中位数 | 3,385.716 ms | 514.853 ms |
| Prove 最小 / 最大 | 3,377.138 / 3,484.750 ms | 507.096 / 560.162 ms |
| Verify 中位数 | 2.790 ms | 2.150 ms |
| Verify 最小 / 最大 | 2.775 / 2.797 ms | 2.102 / 2.195 ms |
| 编码证明大小 | 192 bytes | 192 bytes |
| 验证成功 | 5 / 5 | 5 / 5 |

Prove 计时不包括参数加载、验证密钥准备和见证／输入构造。Verify 统计的是实验中的 Sapling 证明检查调用，不等于完整钱包交易或整套共识验证的端到端时间。

正式基线的汇总表为 `results/tables/engineering_performance.csv`；汇总脚本根据预先指定的 batch ID 筛选数据，不会把探索性批次静默混入正式结果。

## 3. 参数加载与内存测量的限制

参数元数据程序测得 Spend 24,326.502 ms、Output 1,774.506 ms 的读取与验证时间，但每种参数仅有一次测量。证明程序中的参数读取与验证计时来自另一组批次，不应混为同一组重复样本。

整进程 Peak Working Set 目前每种电路仅有一次观测：Spend 101.31 MiB、Output 22.22 MiB。该数值覆盖参数加载、验证、证明与验证过程，并非 Prove 独占内存；样本数量也不足以报告稳定的内存分布。

目前尚未完成严格的 cold-versus-warm 测量协议：参数、验证密钥和输入准备均发生在证明计时之前，也未强制清空操作系统文件缓存。因此，首次与后续调用的差异不能直接解释为冷／热缓存效应。

## 4. 成本结构对照

| 证据 | 测量结果 | 结论边界 |
|---|---|---|
| 合成 Groth16 基线（BN254 / arkworks 0.6.0） | 一次带插桩记录：Prove 3,075.022 ms；MSM 合计 2,816.798 ms，占 91.60% | 合成工作负载的一次记录 |
| Sapling Output（BLS12-381） | 两份较低开销单线程 profile 的稳态 MSM 调用时间占比中位数约 93.41% 和 93.19% | 支持 MSM 是已测 Output 单线程路径的主导成本 |
| Sapling Spend | 一批探索性插桩 profile 的中位占比为 87.62% | 插桩后运行，尚未绑定为正式可复现基线 |
| 多线程 Sapling | 调用级计时存在并行重叠 | 不能将各调用 elapsed 简单相加以计算 MSM / Prove 比例 |

BN254 合成基线与 BLS12-381 Sapling 的曲线、工作负载和实现不同。这项比较用于理解规模和成本结构，不是绝对速度竞赛。

## 5. Sapling Output：候选热点

较低开销的 Output 单线程 profile 显示，八次 MSM 调用的耗时合计在后续轮次约占完整 Prove 时间的 93.2%–93.4%。按 vendored Groth16 prover 的调用顺序与日志字段映射，当前测量中耗时最高的单次调用是 **B-G2 auxiliary query**。

| MSM 调用 | 群 | 标量数量 | window | profile-size 稳态中位数 |
|---|---|---:|---:|---:|
| H query | G1 | 8,191 | 10 | 129.125 ms |
| L query | G1 | 7,821 | 9 | 82.987 ms |
| A input query | G1 | 6 | 3 | 0.938 ms |
| A auxiliary query | G1 | 7,821 | 9 | 65.012 ms |
| B-G1 input query | G1 | 6 | 3 | 0.772 ms |
| B-G1 auxiliary query | G1 | 7,821 | 9 | 53.180 ms |
| B-G2 input query | G2 | 6 | 3 | 2.237 ms |
| **B-G2 auxiliary query** | **G2** | **7,821** | **9** | **152.731 ms** |

更深度的插桩中，B-G2 auxiliary 的内部 bucket fill 累计计时占该调用内部阶段计时约 70.11%。这一数字受更重的插桩影响，只用于识别候选成本段，不代表优化该阶段必然带来同等比例的端到端提速。

## 6. Spend：探索性调用级 profile

后续在独立工作区采集了一批 Spend MSM 与 Worker 调度计时。批次 `1791634015130` 的 5 次 Prove 中位数为 8,020.464 ms，八次 MSM 调用 elapsed 合计相对于 Prove 的逐轮比例中位数为 87.62%；5 次证明均验证通过。

这批数据来自插桩版 Bellman 源码，绝对耗时受到插桩影响，不能替代正式 Spend 基线 3,385.716 ms。调用映射、线程配置、任务启动延迟与提交耗时的详细表格保存在 [`docs/msm_profiling_notes.md`](docs/msm_profiling_notes.md)。完整复现前，应将原始日志、源码差异文件和具体源码版本绑定归档。

## 7. Zcash Sapling 调用链

`docs/zcash_sapling_flow.md` 记录了从钱包侧交易构造、`Builder::build`、Sapling bundle 的 `create_proofs`，到 SpendProver / OutputProver 和 Groth16 proof generation 的主要调用关系，并梳理相应的证明检查路径。

本工程直接调用证明和检查 API，没有执行完整的钱包交易构造、授权签名、交易序列化、网络处理或所有共识规则。因此，当前时间数据衡量的是 Sapling 证明流程中的核心环节，不是完整 Zcash 交易的端到端耗时。

## 8. 数据与复现入口

- 原始结构化数据：`experiments/raw/csv/`
- 原始运行日志：`experiments/raw/logs/`
- 参数校验记录：`experiments/metadata/parameter_validation.csv`
- 汇总表：`results/tables/`
- 图表：`results/figures/`
- 实验方法与边界：`docs/engineering_experiment_notes.md`
- 成本结构分析：`docs/baseline_comparison.md`
- Zcash 调用链：`docs/zcash_sapling_flow.md`
- 详细 MSM profile：`docs/msm_profiling_notes.md`

在仓库根目录运行 `python scripts/summarize_engineering.py` 可以从已有原始数据重新生成正式汇总表和七张核心图表；该脚本不重新执行证明实验。运行任何会追加 raw CSV 的实验程序前，应检查 batch ID 和输出路径。

正式基线对应标签 `sapling-engineering-baseline-v1`，冻结 commit 为 `281f1882bd1b8347f44f485f0f5dca296edafe08`。当前开发分支包含额外的 Bellman MSM／Worker 插桩，插桩结果不能直接当作正式基线复现。

## 9. 阶段结论与待办

目前已经完成：

1. 运行真实 Sapling Spend 与 Output 的证明和验证，并为各自指定正式批次收集 5 次测量。
2. 记录电路约束、变量规模、参数文件大小与哈希，以及单次参数读取／验证时间和单次整进程内存观测。
3. 固定正式性能统计的批次选择，保留原始记录，并区分合成基线和 Sapling 的成本结构。
4. 对 Output 完成调用级 MSM profiling，识别 B-G2 auxiliary 以及其内部 bucket fill 为候选成本段。
5. 收集 Spend 调用级 MSM 与 Worker 计时的探索性证据，但仍需完成日志、源码差异和实验元数据的版本绑定。
6. 梳理 Sapling 的交易构造、证明生成与验证调用链。

仍未完成：

- 进行受控的 cold-versus-warm 测量；
- 增加独立重复的峰值内存样本；
- 将 Spend 探索性 profile 的原始日志、源码差异、参数哈希与实际运行版本完整归档，并确保可追溯复现；
- 若未来尝试优化，同时测量局部阶段耗时和完整 Prove 的端到端变化。

本阶段的成果是工程基线和候选热点定位，不是算法优化结果。下一阶段应基于可追溯的实验记录提出具体假设，再设计受控对照，而不是继续以寻找最佳线程数为目标。
