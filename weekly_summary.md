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

整进程 Peak Working Set 已补充为每种电路 4 次独立进程测量。Spend 中位数为 101.30 MiB，范围为 101.29–101.45 MiB；Output 中位数为 21.54 MiB，范围为 20.79–22.36 MiB。该指标覆盖参数加载、验证、证明生成和验证的整个进程生命周期，并非 Prove 阶段独占内存。这些数据描述当前实验环境下的观测范围，不代表普遍适用的内存上限。

已开展进程级的探索性 cold-versus-warm 对照。冷条件尝试清空 Windows standby list，热条件预读参数文件；这些是近似控制，并未严格隔离所有操作系统缓存层。部分历史 RAMMap 控制日志缺失，最初 Spend 批次开始时工作区不干净。观测到的 Prove 时间差异较小且方向不一致，因此当前数据不能证明缓存状态带来稳定的 proving-time 收益。参数加载与验证仍单独计时；同一进程中的首次与后续 Prove 也不能直接视为严格的冷／热缓存测量。详见 `experiments/metadata/sapling_measurement_campaign_closure_20261011.md`。

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
5. 收集并归档 Spend 调用级 MSM 与 Worker 计时的探索性证据；主批次的源码、日志和补丁哈希已记录，每种多线程配置仍只有一个进程批次。
6. 梳理 Sapling 的交易构造、证明生成与验证调用链。

仍可进一步开展：

- 如缓存行为成为后续核心研究问题，再在干净工作区、完整控制日志和来源元数据条件下开展严格的 cold-versus-warm 对照；
- 若需要更严格的内存模型，可在不同硬件、系统环境或更长时间窗口下增加独立样本；
- 若继续扩展 Spend profile，使用干净且已提交的实验版本，并为新增批次记录源码 revision、参数哈希、构建配置和计时边界；
- 若未来尝试优化，同时测量局部阶段耗时和完整 Prove 的端到端变化。

## 10. 后续进展（2026-10-17）：缺口闭合、fallback 消融与核放置

本轮在既有基线上闭环了三项遗留问题，并新发现一个影响**所有单线程数字**的方法学问题。

### 10.1 Prove 阶段内存账（原缺口 1–3 已闭合）

用计数型全局分配器实测（`experiments/metadata/sapling_prove_memory_ledger_20261017.md`）：

- Spend 单线程 Prove 期**绝对** live 高水位 **100.29 MiB**（8 线程 134.82 MiB）；证明前常驻 65.55 MiB；参数加载后常驻 58.00 MiB（与静态 `capacity_payload` 60,819,152 B 仅差 712 B）。
- 峰值落在 **H query 的 G1 MSM 内部**，主因是「窗口化指数表示」瞬态 **25.97 MB (24.77 MiB)**，远大于桶数组（G1 0.59 MB / G2 1.18 MB）与指数转换（≤9 MB）。
- 即：内存维度的主因从「桶数组」修正为「H query 的窗口化指数缓冲」。

### 10.2 fallback 消融已收敛（原「待隔离」）

固定线程=1、**绑核**、ABBA 配对，只改 worker 调度分支：

- A（fallback）vs B（强制 async）端到端 Prove 差 **+1.1%（均值）**，Mann–Whitney **p≈0.11**（n=10/条件），**不显著**。
- 结论：fallback 是**计时归属／调度现象**，不是吞吐瓶颈；强制 async 只把约 2.5 s 从 `assignment_query_prep_dispatch` 挪进 `wait_and_assembly`，端到端不变。
- 明细：`experiments/metadata/sapling_spend_worker_fallback_ablation_conclusion_20261017.md`。

### 10.3 核放置：单线程测量必须绑核（新发现）

- 同一 exe、同一参数，未约束时单线程 prove 在 **3.4–8.9 s** 间波动（P-core vs E-core，最高 **2.6×**），参数加载 25 s vs 54 s。
- 既有正式基线本身也被污染：Spend 单线程 27 批中 **9 批（33%）**、Output 30 批中 **4 批（13%）**落在 E-core 区间。
- 绑核可复现值：**Spend ≈3.72 s、Output ≈0.53 s**。明细：`experiments/metadata/sapling_smoke_fresh_runs_and_cpu_affinity_20261017.md`。

### 10.4 新增与更新的入口

- 综合参数与瓶颈细化报告（中文）：`docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md`
- 本轮新增／改动：`vendor/bellman/src/mem_probe.rs`（新增）、`vendor/bellman/src/{lib,multiexp}.rs`、`scripts/run_spend_combined_profile.ps1`（新增 `-AffinityMask`）、`experiments/prover-smoke/src/bin/{prove_memory_ledger,exponent_conversion_memory}.rs`（新增）、`experiments/prover-smoke/src/main.rs`（补 `SAPLING_PROVER_RUNS_CSV` 覆盖）。

本阶段的成果是工程基线和候选热点定位，不是算法优化结果。下一阶段应基于可追溯的实验记录提出具体假设，再设计受控对照，而不是继续以寻找最佳线程数为目标。

## 11. 后续进展（2026-10-17 晚）：绑定基线冻结、线程扩展判定、密度普查纠偏与验证协议

本轮把 §10.3 的「必须绑核」从结论升级为**可执行的口径**，并闭合了 §12.4 遗留的线程非单调性与两处「只有推断/只有受控微测量」的问题。原始数据全部新增，不改任何既有 raw 文件。

### 11.1 冻结的绑核正式基线（任务二-1）

1 线程固定掩码 `0x1`（LP0），3 批 × 5 次，弃第 1 批与每次 run 1：

- **Spend 暖态中位 3,685.6 ms**（pooled 3,711.5）；**Output 暖态中位 558.5 ms**（pooled 558.7）。
- 冷启动是真实偏差：Spend 第 1 批中位比暖态高 **+5.8%**（批内前两次 +21%）。
- 核态参照：单核 `0x1` 3711.5 ms / 全 P 核 `0xFFFF` 3842.2 ms（+3.5%）/ 仅 E 核 `0xFFF0000` 7803.6 ms（**2.10×**）/ 不绑核 8808.7 ms（**最慢**）。不绑核的 Output 甚至在**同一进程内迁移**（批内极差 70%）。
- 明细：`experiments/metadata/sapling_pinned_baseline_and_thread_scaling_20261017.md`；新 runner `scripts/run_pinned_prover_campaign.ps1`。

### 11.2 线程非单调性已判定（任务二-2 / 三-1）

固定 `0xFFFF`、2 批/配置：1/2/4/8/16/20 线程中位 = 3842 / 1891 / 1064 / 817 / 786 / 808 ms。

- 4→8 只有 1.30×、8→16 只有 1.039× ⇒ **8 线程起已饱和**（并行效率 58.8%）。
- 16→20 **变慢 2.9%**：20 > 16 个 P 逻辑核，HT 竞争 + `WORKER_SPAWN_MAX_COUNT = 4×线程数` 放大任务队列 ⇒ **只有额外开销、没有额外并行度**。
- **判定：饱和 + 过订阅，不是调度缺陷。** 可执行方向是「线程钉在 4–8」与「缩短串行尾段」。

### 11.3 历史 1 线程基线按核态分层重算（任务三-3）

不改原始文件，只增派生表（`results/tables/sapling_baseline_core_regime_*.csv`）：

- Spend 27 批：快态 19 批（中位 3460.7）／慢态 8 批（中位 7131.1），慢/快 **2.06×**；pooled 中位 3515.9。
- Output 30 批：快态 26 批（519.3）／慢态 4 批（973.2）；pooled 521.8。
- **中位数本身只偏 +1.60% / +0.15%，但极差被放大 1.6–1.7×，且全部来自核放置**；Spend 至少有 5 个批次是「批内混合」。⇒ 用极差论证稳定性的段落必须重述，正式基线须绑核重采。

### 11.4 转换瞬态 in-situ 与窗口化密度直接普查（任务三-2 / 三-4）

- **in-situ 转换**：真实 `create_proof` 内，转换的**峰值增量 = 新建的目标向量**（Spend h **5,242,840 B**），而非「源+目标」；Spend aux 例外地为 **9,361,800 B**，因为此时 h 的 MSM 仍在后台跑、与其共享时间窗。⇒ **峰值记账用 in-situ 数**。
- **密度普查（纠偏）**：直接统计 `Zero`/`One`/`Chunks` 与槽占用——H query（131,071）**100% 为 `Chunks` 且槽非零率 99.35%**（此前推断的 ~94% 是字节模型产物）；L/A_aux/B_aux 只有 **29.0%** 是 `Chunks`，其余 **71% 恰为 0 或 1（零堆分配）**，`Chunks` 内槽非零率 99.37%。字节模型以实测 `ChunkedExponent=24 B` 闭合到 +4,696 B / +40 B。
- **优化含义**：H 的 ~26 MB **不能靠「跳过零 chunk」缩小**（仅 0.65% 槽为零），只能靠「不物化 / 换表示 / 减小窗口 c」；L/A/B 的 0/1 短路已有效。
- 明细：`experiments/metadata/sapling_in_situ_conversion_and_exponent_density_20261017.md`。

### 11.5 优化验证协议已冻结（任务二-3 前半段）

新增 `experiments/metadata/sapling_optimization_validation_protocol_20261017.md`：固定协议（绑核、4–8 线程辅口径、≥3 批、ABBA 配对、非参检验）、**预声明验收阈值 ≥3%**（1 线程下 <3% 不可分辨）、数据留存模板与「代码/数据/文档」三提交拆分。**优化目标已选定为 e 并完成验证，见 §12**；候选与建议顺序（e 零风险 → a 内存主因 → b 时间主因）列于该文档 §7。

### 11.6 与 §10 的口径关系

§10.1 的「25.97 MB」与 §10.3 的「≈3.72 s / ≈0.53 s」是**当时的单次/单批观测**。请在引用时改用本轮冻结值：**窗口化缓冲实测 prep 增量 26.2 MB**、**绑核冻结基线 Spend 3,685.6 ms / Output 558.5 ms**。

## 12. 优化目标 e 的验证（配置级：线程数/亲和性，2026-10-17 完成）

负责人拍板选择候选 **e**。按 §11.5 协议先冻结**预声明验收表**（`sapling_default_config_experiment_preregistration_20261017.md`），再跑数据；结果记录 `sapling_default_config_experiment_results_20261017.md`，分析脚本 `scripts/analyze_default_config_experiment.py`，派生表 `results/tables/sapling_default_vs_pinned_config_20261017.csv`。**未改任何算法代码。**条件：A = 出厂默认（不绑核 + rayon 默认 28 线程）；B = 绑 P 核 `0xFFFF` + 8 线程；C/D/E 为归因参照。

### 12.1 结果 1（稳健）：串行参数读取被 E 核拖慢 1.8–1.9×

Spend `params_read_validate_ms` 中位：**允许 E 核**的三种配置 = 55,159 / 53,622 / 51,833 ms；**只允许 P 核**的四种配置 = 29,165 / 27,052 / 27,950 / 26,042 ms。**与线程数（1/8/16/28）无关，只与蒙版有关**，比值 **1.8–1.9×**（机制假设：串行部分被调度到 E 核，与 §11.1 的 E 核 54 s 特征一致）。端到端批总时长 A 60.6 s vs B 35.5 s（**1.71×**）——但参数读取在钱包中通常**每进程一次**。

### 12.2 结果 2（未认证）：Spend prove

ABBA 交错两轮共 10 对：B−A 配对中位 **−8.5%**（候选更快 6/10，**符号检验 p=0.754 不显著**）；合并 n=50/组中位 A **978.9 ms** vs B **863.7 ms（−11.8%）**，MWU **p=0.0164**。**但同轮内 B 首→末漂移 −44.5% / −26.9%**，触发预声明漂移守门 ⇒ 按预声明记为**「未认证」，不改默认配置**。

### 12.3 结果 3（认证级负结果）：Output 反对降线程

Output prove 中位：默认 28 线程 **80.6 ms**（全 28 LP/28t 83.4）≪ P 核 8t 98.2 / P 核 16t 102.5 / 全 28 LP 8t 103.9。⇒ Output 由**线程数**决定、蒙版几乎无关；降线程使其慢 **22–29%**（预声明 B vs A = **+21.8%，p=0.0102**）。

### 12.4 结论

1. **【稳健，建议采纳】** 把证明进程限制到 **P 核集合**：Spend 单进程省约 25 s（读取阶段 1.8–1.9×），prove 无实测退化，Output 中性。
2. **【已认证，反对】** **不要降低线程数**（Output −21.8%）。
3. **【未认证】** P 核限制是否改变 Spend prove 中位（点估计有利，噪声掩盖）。
4. **【方法学】** 本机是繁忙桌面，绑核配置批间波动 **30–45%** ⇒ **prove 阶段的优化结论必须在安静主机上重测**；这正验证了协议里的漂移守门是必要的。
5. **重建中性对照**：今日二进制 1t@`0x1` = 3,785.7 ms vs 冻结暖态 3,685.6 ms（**+2.72%**，噪声内）⇒ 新增默认关闭插桩未改变性能，§11.1 冻结基线可继续沿用。

> 一句话：目标 e 是**半个胜利 + 一个更重要的方法学结论**——"绑 P 核"对准备阶段是稳健收益，"降到 8 线程"被证否，且本机噪声已证明会掩盖 prove 阶段的真实效应。
