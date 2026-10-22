# Zcash Sapling / Groth16 工程基线：阶段总结

**阶段状态：** 第一轮真实 Sapling 工程基线已建立并冻结；核心性能测量与候选热点定位已完成，并已按冻结的验证协议完成三项受控优化验证（配置级目标 e、算法级目标 b、内存级目标 a，见 §12–§14）。其中目标 b 通过并已设为默认；目标 a 机制完全生效且三个臂集都更快，但按预注册的冻结阈值（≥15 MB）判为**未通过并归档**，同时测出了 prove 峰值的新主因（QAP/FFT 阶段 90.13 MB 天花板）。  
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
3. **【未认证，后经 §12.5 上调为中等置信】** P 核限制是否改变 Spend prove 中位（点估计有利，噪声掩盖）。
4. **【方法学】** 本机是繁忙桌面，绑核配置批间波动 **30–45%** ⇒ **prove 阶段的优化结论必须在安静主机上重测**；这正验证了协议里的漂移守门是必要的。
5. **重建中性对照**：今日二进制 1t@`0x1` = 3,785.7 ms vs 冻结暖态 3,685.6 ms（**+2.72%**，噪声内）⇒ 新增默认关闭插桩未改变性能，§11.1 冻结基线可继续沿用。

### 12.5 安静主机复现（同日追加，第三轮交错）

每轮前采样 2.5 s 全进程 CPU 占用得 **1.9–7.2%**（28 逻辑核）；6 轮 × (A,B,C) 背靠背，**后半段反转顺序**（`A,B,C` → `C,B,A`）平衡轮内顺序效应。

| 配置 | prove 中位（n=30） | vs A | MWU p |
|---|---|---|---|
| A 不绑核，默认 28 t | **915.8 ms** | — | — |
| B P 核 8 t | **824.5 ms** | **−9.97%** | **0.0038** |
| C P 核 16 t | **823.2 ms** | **−10.11%** | **0.0001** |

- **配对检验并入三轮（16 对）**：B−A 配对中位 **−6.7%**，B 更快 **10/16**；精确符号检验 **p=0.454（仍不显著）**。
- **漂移**：A −2.9%（首次 <3%）／B −18.1%／C −10.6%。**绑核配置仍是波动最大的一方**——它被暴露给仍占用 P 核的交互程序，这是固有代价。
- **参数读取再次复现**：A 52,148 ms vs B 26,805 / C 26,983 ms（**1.94×**）。至此允许 E 核 4 个条件、只允许 P 核 6 个条件，落在互不重叠的 51.8–55.2 s 与 26.0–29.2 s 两区间。

**修订判定**：结论 1、2 不变（已认证）；结论 3 上调为"**方向一致、配对显著性不足**"（三次独立交错点估计 −6.7%~−10%，安静轮 MWU 显著，但预声明配对符号检验 p=0.454）。

> 一句话（修订）：目标 e = **一个已认证的阶段收益（绑 P 核 → 串行读取 1.9×）+ 一个已认证的负结果（降线程 → Output 慢 22%）+ 一个方向一致但配对显著性不足的 prove 增益（≈6–10%）+ 一条方法学结论**（繁忙桌面会掩盖 prove 阶段的真实效应）。

## 13. 优化目标 b 的验证（算法级：MSM 有符号窗口重编码，2026-10-17 完成）

负责人随后选择候选 **b**（时间主因：H query G1 MSM）。按 §11.5 协议先冻结预声明验收表（`experiments/metadata/sapling_msm_signed_digit_preregistration_20261017.md`，提交 `c507e0e`，**先于任何代码改动**），再动手；结果记录 `sapling_msm_signed_digit_results_20261017.md`，分析脚本 `scripts/analyze_msm_signed_digit_experiment.py`，派生表 `results/tables/sapling_msm_signed_digit_{abba,stage_profile}_20261017.csv`。与目标 e 不同，**这次改的是算法代码**（`vendor/bellman/src/multiexp.rs`）。

### 13.1 机制：无符号窗口 → 平衡有符号窗口

- 先把「为什么只能改这里」钉死：桶数组 36/147/590 KB 下单次混合加分别是 468/467/478 ns（**与桶大小无关** ⇒ 不是访存受限）；LTO/`native` 最好只有 −2.7%；纯窗口调参 ≤−3.7%。单次混合加 470 ns ≈ 11 次 `Fp` 乘 × 43 ns ⇒ **算术受限**，因此唯一 >5% 的杠杆是**减少群加次数**。
- 把窗口数字换成平衡有符号数字 `d ∈ [−2^(c−1), 2^(c−1)]`（偏置存储，桶下标 `|d|−1`）：**同宽度桶数减半**（`2^(c−1)`），省下的预算换 **+1 bit/窗口**。
- H query（n=131,071）：**22 个 12-bit 窗口 → 20 个 13-bit 窗口**，桶数组 4095 → 4096（几乎不变），群加次数 **3,063,742 → 2,785,260（−9.1%）**。

### 13.2 正确性（四项全过）

- ① 78/78 真实证明 `verified=true`、`proof_bytes=192`；
- ② 两种编码在 **c = 2..=20 每个宽度**下结果**逐位相同**（n=131,071 整规模断言）；
- ③ 64 项前缀 == double-and-add（两种编码）、n=8 小查询路径；
- ④ 参数哈希与电路规模未变。
- **实现坑（已修）**：平衡重编码会向最高窗口进位；当 `c | 255`（c=3/5/15/17…）时该进位非零，故窗口数必须是 `255/c + 1`（而非 `ceil(255/c)`），否则静默丢位致错。全宽度扫描 + debug `debug_assert` 把它挡住了。

### 13.3 主指标（冻结阈值 ≥3%）：Spend 1t @ `0x1`

同一二进制（`SAPLING_MSM_SIGNED_DIGITS` 开关，A=0 / B=1）做 **ABBA / ABBA / BAAB** 三轮交错（末轮反转顺序），各 6 批 × 5 次：

| 口径 | A（无符号） | B（有符号） | 变化 |
|---|---:|---:|---:|
| 批中位 pooled | 3903.6 ms | 3644.9 ms | **−6.63%** |
| 单次证明 pooled 中位 | 3887.9 ms | 3652.6 ms | **−6.05%**，MWU **p<1e-4** |
| 配对中位（ABBA，n=5，弃首批） | — | — | **−6.94%**，**5/5 全 B 更快** |
| 敏感性（不弃首批，n=6） | — | — | −6.04%，**6/6**，符号检验 **p=0.031** |

漂移守门：A **+0.4%** vs B **+0.4%**（轮内对称）。**主指标达标（−6% ≫ 3%）。** 说明：冻结口径下 5 对符号检验 p=0.0625 —— n=5 时「5/5」的最小可能双侧 p 就是 0.0625，故这不是反证；单次证明层 MWU 与不弃首批 6/6 均显著。

### 13.4 辅助指标

- **辅助 1（H query 阶段计时，非交错）**：`bucket_fill` 1561.1 → **1359.3 ms（−12.92%）**、`bucket_reduce` 102.5 → **88.7 ms（−13.45%）**；prep +5.7 ms（可忽略）。降幅略大于次数预测（−9.1%），说明 20 窗口下调度的合并也更省。
- **辅助 2（Spend 8t @ `0xFFFF`，非退化）**：−2.37%（pair −1.18%，4/7，p=0.57）。8 线程本就有 ±20% 批间波动（A 臂后半段 +24.5%）⇒ **只能说「未发现退化」**。
- **辅助 3（Output 1t @ `0x1`）**：**−11.35%**（pair −8.78%，**5/5**；敏感性 6/6 p=0.031）。Output 的 H query 仍取 c=10，但**桶数 1023 → 512**，reduce 直接减半 ⇒ 收益更大。
- **内存（要求不上升）**：`prove_peak_abs_bytes` 105,160,251 → **103,062,954 B（−2.00 MB / −1.99%）**；H query prep 增量 22,024,592 → 19,927,456 B，与「少 2 窗口 × 131,071 × 8 B = 2,097,136 B」**逐字节吻合**。

### 13.5 结论

1. **【通过，建议采纳，已设为默认】** 有符号窗口：Spend 1t −6.6%、Output 1t −11.4%、内存 −2.0 MB；`SAPLING_MSM_SIGNED_DIGITS=0` 可一键回到逐位相同的旧编码。
2. **与目标 e 相互独立、可叠加**：一个减群加次数，一个改调度。
3. **残余风险**：任何外部假设「窗口数 = `ceil(255/c)`」的代码需同步。
4. **作废件保留**：首次内存台账误用**未重建**的 `prove_memory_ledger.exe`（两臂同结果、插桩缺 `signed=`），已改名 `*_stale_binary.*` 原样保留并重跑。教训：改动被依赖的 crate 后必须 `--bins` 全量重建并核对哈希。
5. **未做**：wNAF（内存不可接受）、底层 `Fp` 算术（换库/写汇编）。

> 一句话：目标 b = **一个已认证的算法级改进（平衡有符号窗口：群加次数 −9.1% → Spend 端到端 −6.6%、Output −11.4%）+ 一个逐字节可验证的内存收益（−2.0 MB）+ 一次被正确性门挡住的进位 bug**。

---

## 14. 优化目标 a 的验证（内存级：H query 窗口化表示「去物化」，2026-10-18 完成）

负责人第三个选定候选 **a**（内存主因）。按协议先冻结预声明验收表（`experiments/metadata/sapling_msm_lazy_recoding_preregistration_20261018.md`，提交 `85ffb0d`，**先于任何代码改动**），结果 `sapling_msm_lazy_recoding_results_20261018.md`，分析脚本 `scripts/analyze_msm_lazy_recoding_experiment.py`，派生表 `results/tables/sapling_msm_lazy_recoding_{memory,abba}_20261018.csv`。改动仍在 `vendor/bellman/src/multiexp.rs`，另新增一个默认关闭的阶段归因探针（`vendor/groth16/src/prover.rs`）。

### 14.1 机制：只预存进位位，窗口数字在 fill 时即时折叠

- **关键结构事实（侦察推翻第一版设计）**：`multiexp_inner` 的并行轴是**窗口**（`(0..window_count).into_par_iter()`），窗口乱序并发 ⇒「按窗口顺序滚动推进进位」**不可行**；进位必须一次算完、之后只读。
- 只预计算**进位位图**：1 bit/窗口/指数 × 131,071 × 20 = **327,680 B**（原来 24,117,064 B 物料化缓冲）。
- 位段随机访问是 **O(1)**（`bls12_381::Scalar::ReprBits = [u64;4]` ⇒ `FieldBits` 是字对齐 `BitArray`，`BitField::load_le` 只走 live head/body/tail 字）；若用 `.chunks(c).nth(j)` 则每窗口 O(j)、总计 O(w²) ≈ **+10× 提取工作**，故弃用。
- 偏置槽算术与旧实现共用 `signed_slot`，0/1 短路不变 ⇒ **逐位等价**。开关 `SAPLING_MSM_LAZY_RECODING`，**默认保持 `0`**。

### 14.2 正确性（全过）

- **两种实现在 c = 2..=20、n = 131,071 整规模下逐位相同**（19/19）；64 项前缀 vs double-and-add 16/16；n=8 小查询 4/4；跨重编码 6、内建窗口规则 7；**120/120 证明 `verified=true` / 192 B**。
- **这条断言第一次整规模运行就抓到真 bug（已修）**：fill 循环改为只遍历 density map 后越界（`multiexp.rs:313`）。`FullDensity::iter()` 是 `iter::repeat(true)`，原实现靠与指数向量 zip 截断；现改为 `.take(exponent_count)`。

### 14.3 主指标（冻结阈值 ≥15 MB）：prove 峰值

| 项（1t @ `0x1`，台账 out/on 各 5 run，暖态 run 2–5 中位） | A（物料化） | B（进位位） | 变化 |
|---|---:|---:|---:|
| `prove_peak_abs_bytes` | 103,063,725 B | **90,130,324 B** | **−12,933,401 B（−12.55%）** |
| H query `exponent_prep_live_delta_bytes` | 23,873,080 B | **83,736 B** | −23,789,344 B |
| H query 进位位图 | — | 327,680 B | ≤0.4 MB 达标 |

A 臂复现冻结基线 103,062,954 B（+771 B 分配器粒度）⇒ 物料化路径未被扰动。**主指标 12.93 MB < 15 MB ⇒ 未达标。**

### 14.4 未达标的原因：直接测出的 90.13 MB 独立天花板

新增阶段探针 `SAPLING_G16_MEM_PHASE_PROBE=1`（默认关闭）在 `create_proof` 每个阶段边界报告 live 与阶段内峰值水位，并把峰值归因成一张表（run 2–5，绝对值）：

| 阶段 | A（物料化） | B（进位位） |
|---|---:|---:|
| `circuit_synthesis` | 86,184,617 | 86,184,616 |
| **`qap_fft_h_exponent_prep`** | **90,130,337** | **90,130,336** |
| `h_query_access_dispatch` | 83,867,537 | 78,924,712 |
| **`assignment_query_prep_dispatch`** | **103,064,497** | 82,870,336 |
| `wait_and_assembly` | 81,216,523 | 74,522,890 |

- B 臂的全局峰值**恰好是该阶段峰值**，且该值在两臂**逐字节相同**（差 1 B）⇒ 改动移除了天花板之上的**全部**内容，天花板本身分毫未动。
- A 臂更高的 103.06 MB 落在窗口化表示存活的窗口内；`103.06 − 90.13 = 12.93 MB` 就是**物理上可转化**的上限，24.1 MB 缓冲里约 11 MB 从来不在峰值里。
- ⇒ **prove 期内存主因已更新**：不再是 MSM 窗口化缓冲，而是 **QAP/FFT 阶段（三个域向量 `a/b/c` 同时驻留 + `h_exponents` 现场转换）的 90.13 MB**。

### 14.5 辅助指标：三个臂集**都更快**（不只是不退化）

同一二进制 + 开关，三轮 `ABBA,ABBA,BAAB`，弃每臂首批与每批 run 1：

| 臂集 | A → B 批中位 | 变化 | 配对 n=5 | B 更快 | 符号检验 p |
|---|---|---:|---:|---:|---:|
| Spend 1t @ `0x1`（主） | 3511.2 → 3349.6 ms | **−4.60%** | −5.30% | 5/5 | 0.0625 |
| Spend 8t @ `0xFFFF` | 894.8 → 818.6 ms | **−8.52%** | −6.87% | 4/5 | 0.3750 |
| Output 1t @ `0x1` | 498.2 → 488.7 ms | **−1.90%** | −1.42% | 5/5 | 0.0625 |

主臂单次证明中位 −4.96%（MWU p<1e-4）；敏感性（不弃首批 n=6）−5.04%、**6/6**、p=0.0312。微基准同进程：c=13 **1488.4 → 1371.8 ms（−7.8%）**，c=8/10/12/14/16 分别 −8.5/−8.5/−7.1/−8.0/−4.5%。

### 14.6 口径修正（冻结）：26.2 / 22.0 / 19.9 MB 三个数字归一

同一缓冲的毛值口径是「外层 24 B/指数 + 堆 8 B/槽」：c=12 = **26,214,200 B**，有符号 c=13 = **24,117,064 B**。`exponent_prep_live_delta_bytes` 是**净值**，测点时源 `Vec<Scalar>`（4,194,304 B = 精确 4 MiB）若已释放就整体少一个源向量——26.2（普查毛值）/ 22.0（台账 off，毛值−源）/ 19.9（台账 on，毛值−源）三者由此而来，均自洽（残差 +4,696 B）。**引用一律用毛值。**

### 14.7 结论

1. **【未通过 ⇒ 按冻结规则归档，默认值保持 `0`】** 主指标 12.93 MB < 15 MB；预注册回退条款记为「局部改动未转化为峰值下降」。**但改动本身完全生效**：瞬态 −23.79 MB（是判据 1a 要求的两倍）、缓冲 24.1 MB → 0.33 MB、三个臂集全部更快、正确性全过。
2. **方法论教训（重要）**：内存类目标的阈值必须**先做阶段分解**再定。正确做法是先用阶段探针测出次高阶段高度 `H2`，阈值取 `min(缓冲毛值, 峰值 − H2)`；本例 `H2 = 90.13 MB`，可转化上限从一开始就只有 12.93 MB，15 MB **物理上不可达**。
3. **下一步目标已明确**：`qap_fft_h_exponent_prep` 阶段的 90.13 MB 是当前 prove 峰值主因（时间维度上它是排名 #3 的 QAP/FFT，内存维度上现在是 #1，两个维度指向同一段代码）。
4. **【所有者决定 2026-10-18】** 保持 `SAPLING_MSM_LAZY_RECODING` 默认 `0`（严格遵守冻结规则），并把新测出的 QAP/FFT 阶段天花板（90.13 MB）立为**下一优化目标**。注意组合关系：在 shipped default（lazy=0）下全局峰值仍由 H query 窗口化缓冲所在区间决定，**单独压低天花板不会改变默认配置的全局峰值**；因此下一目标的主指标预注册在 **lazy=1** 配置上，天花板落地后再以「lazy=1 + 天花板下降」的组合重新立项验收（届时默认值切换才被显式授权）。

> 一句话：目标 a = **一个机制完全生效、时间还更快，但被自己预注册的阈值判为不通过的改动**——它的真正产出是**发现并测出了 prove 峰值的新主因（QAP/FFT 阶段 90.13 MB 天花板）**，以及一条「内存阈值必须先做阶段分解」的方法论。

## 15. 优化目标 f 的验证（内存级：单线程 FFT four-step scratch 消除，2026-10-18 完成）

目标 a 归档后，按既定方法论把 `qap_fft_h_exponent_prep` 阶段的 **90.13 MB 天花板**立为目标 f 并先冻结预注册（`experiments/metadata/sapling_qap_fft_scratch_preregistration_20261018.md`，提交 `997016a`，先于任何改动），结果文档 `experiments/metadata/sapling_qap_fft_scratch_results_20261018.md`，分析脚本 `scripts/analyze_qap_fft_fix_experiment.py`，派生表 `results/tables/sapling_qap_fft_fix_{memory,abba}_20261018.csv`。改动在 `vendor/bellman/src/domain.rs`：新开关 `SAPLING_FFT_SERIAL_SINGLE_THREAD`（默认 `0`），把 `log_num_threads()==0` 时的四步 `parallel_fft` 路径改走原地 `serial_fft`。

### 15.1 机制：四步法在单线程下是恒等变换，却每次分配一个整域缓冲

- 六次变换每次都走 `best_fft`：`log_num_threads()==0` 时 shuffle 退化为拷贝、拷回是恒等置换，**数学上是恒等操作**，但仍分配 131,072 × 32 B = **4,194,304 B** 全域缓冲。
- 侦察确认 `log_cpus ≥ 1` 时代码路径逐字节不变——8t 臂只作守门，不声称多线程收益。
- Output（2^13）绝对值收益仅 262,144 B，与 output 臂 −0.20% 一致。

### 15.2 判定：**通过（六项全过）**，且逐字节用尽物理可转化上限

| # | 指标 | 冻结阈值 | 实测 | 判定 |
|---|---|---:|---:|:--:|
| 主 | `lazy=1` 配置 prove 全局峰值下降 | ≥ 3,500,000 B | **−3,945,720 B（−4.38%）**：90,130,334 → 86,184,614 B | **MET** |
| 辅 1 | `qap_ffts_done` 阶段峰值下降 | ≥ 3,500,000 B | −4,194,352 B | **MET** |
| 辅 2 | 正确性 | 100% / 全过 | 20/20 验证通过；12/12 digest 逐位一致 | **PASS** |
| 辅 3 | 时间守门（三臂池化批中位） | 不退化 > 1% | −3.31% / −3.17% / −0.20%（均为负） | **PASS** |
| 辅 4 | `lazy=0`（shipped default）峰值不上升 | ≤ 0 B | −760 B（分配器噪声） | **PASS** |

- 预注册预测「全局可转化上限 = 峰值 − 次高阶段 = 3,945,720 B」与实测**恰好相等（偏差 0 B）**；fix1 后全局峰值改由既存的 `circuit_synthesis`（86.18 MB）决定——与预注册 §1.3 的预测完全一致。这是目标 a 确立的「阈值 = min(可移除量, 峰值 − 次高阶段)」方法论的第一次正向命中。
- 两处如实说明：① 8t 臂池化 −3.17% 与配对 +1.11% 方向不一致（代码路径不变，只能归因主机漂移：B 臂批中位漂 −13.1%；不弃首批敏感性 −0.32%），按冻结口径通过但**不得引述为"本改动让 8 线程更快"**；② 1t 臂 −3.31% 超出"≈略快"预期，方向与机制一致、敏感性稳健（−3.35%，6/6 全 B 更快），但端到端时间非本目标主指标，只作"未退化且方向为负"引述。

### 15.3 口径修正（派生表一处，不影响判定）

`sapling_qap_fft_fix_memory_20261018.csv` 的 `lazy0_peak_unchanged` 在 `1bc8bc7` 中为 `False`（按旧读法"峰值严格不变"生成）；冻结辅 4 判据是"不上升（≤ 0 B）"，−760 B 满足。本提交按冻结判据重生成（`True`，重跑分析脚本复现，其余字段不变），两种读法下辅 4 均非上升，**不改变任何判定**。

### 15.4 结论与下一步

1. **【通过】** 目标 f 单线程路径消除一个整域 scratch（4.19 MB），`lazy=1` 配置全局峰值下降 3.95 MB，恰好用尽物理上限；正确性与时间守门全过。
2. **【开关默认保持 `0`】** 按预注册范围声明与目标 a 的所有者决定惯例：本目标只降天花板本身，**组合收益（`lazy=1` + 本改动 = 103.06 → 86.18 MB，−16.88 MB / −16.4%，超过目标 a 未达到的 15 MB 门槛）的正式验收是目标 g 的事**，默认值切换随组合一并显式授权。
3. **下一步（目标 g）**：预注册「`lazy=1` + FFT scratch 消除」组合的主指标（prove 峰值下降 ≥ 15 MB）与默认值切换条款。届时若通过，shipped default 从 `lazy=0` 切到 `lazy=1`，全局峰值 103.06 → 86.18 MB。

> 一句话：目标 f = **一个机制干净、门禁全过、且把可转化上限一分不差全部拿到的改动**——它把 QAP/FFT 天花板从 90.13 MB 压到 86.18 MB，并为目标 g 的组合验收（−16.88 MB，越过目标 a 错过的 15 MB 门槛）铺平了道路。

## 16. 优化目标 g：组合验收与默认值切换（2026-10-18 完成）

目标 a/f 之后，两个开关的收益被阈值切开。目标 g 把 **`lazy=1` + 单线程 FFT scratch 消除作为一个组合**正式验收，并作为默认值切换的唯一授权路径。预注册 `experiments/metadata/sapling_combo_default_preregistration_20261018.md`（提交 `9e7ee2e`）**先于任何目标 g 测量**冻结；驱动 `scripts/run_combo_default_campaign.ps1`（双开关 ABBA：A 臂 = 现默认两 0，B 臂 = 拟新默认两 1）；判定 `scripts/analyze_combo_default_experiment.py`（统计口径与目标 f 逐字节同构）；结果 `experiments/metadata/sapling_combo_default_results_20261018.md`。

### 16.1 判定：**通过（六项全过），默认值已切换**

| 指标 | 冻结阈值 | 实测 | 判定 |
|---|---|---:|:--:|
| 主：组合 prove 峰值下降 | ≥ 15,000,000 B | **−16,878,888 B（−16.38%）**：103,063,495 → 86,184,607 B | **MET** |
| 辅 1：正确性 | 100% | 台账 10/10 + 时间战役 360/360 + 翻转后 5/5 | **PASS** |
| 辅 2：时间非退化（三臂集） | 每臂 ≤ +1% | −5.81% / −3.95% / −2.35%（均为负，配对 5/5，敏感性 6/6） | **PASS** |
| 辅 3：切换后复验 | 三项全过 | 门禁 12/12 一致；台账 +7 B；批次 5/5 | **PASS** |

- 主指标超门槛 1.88 MB——正是目标 a 单独未达到的 15 MB 门槛；重测值与目标 f 归档值偏差 ≤ 239 B（分配器粒度），两个独立批次互相印证。
- 时间三臂全部更快，但按预注册范围只作**附证**（主指标是内存；output −2.35% 低于协议 §4 的 3% bar）。8t 臂与目标 f 的 8t 臂形态不同：收益来自 lazy 重编码（目标 a 实测 8t −8.52%），配对与敏感性方向一致、漂移仅 +3.1%，是真实臂效应。
- **【默认值已切换】** 提交 `d4ed1df`：`SAPLING_MSM_LAZY_RECODING` 与 `SAPLING_FFT_SERIAL_SINGLE_THREAD` 默认值均 0 → 1；重编译后不设任何开关复验：门禁 digest 与显式四步法逐位一致、台账峰值 86,184,614 B（+7 B）、批次 5/5。shipped default 的 prove 峰值 **103.06 → 86.18 MB（−16.4%）**。环境变量仍可双向覆盖。

### 16.2 方法论备注

- 阈值 15,000,000 B 先于测量冻结且不随预期（16.88 MB）上调——目标 a 教训的反向应用：本次预期有阶段分解支撑，但阈值仍取下界，防「预期微超门槛」的运气判定。
- 目标 f 的四臂台账虽已含本目标两臂，但产生于本预注册之前，**判定未自借证据**，两臂同会话重测。
- 一处工具链坑：PowerShell 的重定向输出为 UTF-16LE，导致判定脚本首轮读不到门禁 digest（数据无损，已用 UTF-8 重捕获；门禁确定性，digest 不变）。后续凡是要被 Python 判读的日志，一律用 `[IO.File]::WriteAllText` + UTF8 编码捕获。

### 16.3 结论与下一步

1. **【完成】** 目标 g 通过并落地默认值切换：这是本工程第一个把 shipped default 真正切换掉的优化组合（−16.4% prove 峰值）。
2. **【候选清单】** 协议 §7 候选：a（未通过归档）、b/e/f/g 均已完成；c（B-G2 aux）与 d（赋值转换并行化，预期 <3%）未做。
3. **【下一内存目标】** 翻转后的 86.18 MB 峰值由 `circuit_synthesis` 阶段决定（§22 已测），下一目标必须先做阶段分解再立阈值。

## 17. 优化战役完结：两条线均到达地板（2026-10-18）

目标 g 切换默认值后，按既定方法论（先阶段分解、再立阈值）对新的 shipped default
做了结项侦察。**结论：内存线与时间线均到达各自地板，战役 a–g 完结。**

### 17.1 内存线：结构性地板（86.18 MB）

侦察文档 `experiments/metadata/sapling_default_stage_decomposition_20261018.md`；
新增合成容量探针 `SAPLING_G16_SYNTH_CAPACITY_PROBE`（`vendor/groth16/src/prover.rs`，默认关闭）。

- 全局峰值 86,184,603 B 归属 `circuit_synthesis` 末端；第二高阶段峰值 82,870,091 B
  ⇒ 物理可转化上限 **3,314,512 B**。
- 容量实测（5 次运行逐字节确定）：a/b/c/aux capacity 全为 131,072 = QAP 域大小，
  **不是余量**（`from_coeffs` resize 原地消费；预留下精确长度会把重分配瞬态
  移进 QAP 阶段、峰值反升 ≈87.0 MB）；唯一真余量 aux 1,037,888 B 在峰值点不可释放
  （shrink 瞬态 +3.16 MB；预知见证数无干净机制）。
- 60.8 MB 参数 + 7.9 MB 见证准备均为必需。⇒ 上限不可达，**不再设立内存目标**。

### 17.2 时间线：算术地板（1 线程 prove ≈3.4 s）

侦察文档 `experiments/metadata/sapling_default_time_profile_20261018.md`。

- 阶段墙时间（中位，剖析开销只取比例）：合成 120.5 ms（3.3%）、FFT+h 转换
  385.8 ms（10.6%）、MSM 队列排空 3,100 ms（85.4%）。
- MSM 按 query：H 1,514 ms（fill 93.5%）、G1 aux 987 ms、B-G2 aux 635 ms
  （reduce 44%）；fill 每非零数字 462 ns（同批次实测：2,620,825 个非零窗口数字/证明，
  与注释记录的 ~470 ns 混合加一致）
  ⇒ 算术受限，操作数由 Pippenger 算法固定。
- 操作数模型核算 **c=13 对三大 query 均已最优**（H：c=12 +6.8% / c=14 +0.6%；
  G2 aux：c=12 +0.7% / c=14 +11%）。候选 c 无机制；候选 d 低于 bar（<1%）。
- `wait_and_assembly` 640.8 ms 经追溯是 worker 队列尾部，非装配算术。⇒ **不再设立时间目标**。

### 17.3 陈述边界

结项只覆盖本管线（vendored bellman + Sapling Spend/Output + 既定开关体系）与既定
口径（1 线程主守门）。战役产物（b/e/f/g 的收益与默认值切换）继续有效。后续若出现
新机制（按 query 选窗、新桶元素布局、新 recoding），先用同款侦察再决定是否立项。

## 18. 仓库整备：评审驱动的四项收尾（2026-10-18）

外部评审指出：实验数据已充足，缺的是“从实验结果到可维护代码、从本机验证到独立复现的最后一段链路”。按建议顺序完成四项，均遵循非破坏式原则（无文件删除；历史章节只补 superseded 指向）。

### 18.1 README 当前状态统一（P0）

修复前后矛盾的“当前状态”表述，历史章节保留原样：

- 开头状态块更新至 2026-10-18：战役 a–g 完结、两个开关默认 `1`（加此前的 `SAPLING_MSM_SIGNED_DIGITS` 共三个）、shipped default 峰值 103.06 → 86.18 MB；
- Results at a Glance 增加战役成果表（目标 e/b/a/f/g + 结项侦察）；
- §16 补第 15–17 条（目标 f、目标 g、两条线结项及范围限定）；§14 补“当日被 f/g 取代”指向；
- §17 删去过时的“默认保持 0、下一步优化 QAP/FFT 天花板”，改为：默认-on 开关的回退路径（三个 `=0` 逐一说明）、单主机复现范围；
- §18 把候选 c/d 记为“已核查关闭”，新增战役后方向（通用 SNARK 内存模型 / MSM 代价模型 / 跨硬件复现），不再把已完成候选项列作待办。

### 18.2 PR #2 审查包（P0）

PR #2 原标题 "update test"、正文为空。本环境无 gh CLI/token，无法程序化改 PR；已将建议标题
（`Complete Sapling proving optimization campaign and certify combined defaults`）与完整正文
写入 `experiments/metadata/pull_request_2_review_packet.md`（含审查入口顺序、各目标判定表、
默认切换依据、复现命令、范围边界），需用户在 GitHub UI 手动粘贴。

### 18.3 自动化 CI（P1）

新增 `.github/workflows/ci.yml`（**不依赖外部参数文件**）：fmt + clippy `-D warnings`（仅限
本研究 crate）、vendored crate 编译检查与库测试（`--lib --tests`，跳过上游镜像自带的坏
doctest）、release 构建、两个守护默认-on 开关的确定性门禁（FFT 12 digest 跨开关态一致；
MSM 跨重编码 / lazy 等价）。所有门禁命令均在提交前于本地实测通过。为此完成两项修复：

- prover-smoke 一次性 `cargo fmt` + 修净全部 clippy warning（单独提交）；
- **发现并修复一个既有缺陷**：vendored groth16 的 manifest 把 bellman 解析到 crates.io，
  而插桩引用 vendored bellman 内部符号，导致 groth16 **根本无法独立构建/测试**——加
  `[patch.crates-io] bellman = { path = "../bellman" }` 后其独立测试通过（4+3），prover-smoke 不受影响。

### 18.4 实验索引与独立复现（P1）

- `experiments/metadata/INDEX.md`：一张总表把每条研究线（目标 a–g + 各测量线）映射到结果文档、
  原始数据入口与当前结论，并明确三类文件规则（raw 不覆盖 / 派生表可重建 / 报告作解释）。
- `docs/reproduction.md`：独立复现规程（干净 checkout、工具链、无参数门禁、带参数哈希的真实
  证明复现、跨硬件项）。
- **实际执行了一次同主机独立复现**（`experiments/metadata/sapling_independent_reproduction_20261018.md`）：
  干净 clone + 全新构建（45.7 s）+ 不设任何开关：两个门禁全过（digest 与主仓库捕获一致）、
  内存台账 5/5 验证、峰值中位 **86,184,600 B**（认证值 86,184,607 B，**−7 B**）、prove 中位
  ≈3,233 ms。跨硬件复现仍未做，已如实登记。

> 一句话：本轮不新增任何实验结论，而是把已有结论接到可维护代码与可独立复现的链路上——CI 守护
> 两个默认-on 开关，索引提供单一入口，同主机复现确认默认配置在干净 checkout 上逐字节成立。

## 19. PR #2 合并、CI 首次转绿与跨配置复现（2026-10-18）

### 19.1 PR #2 评审就绪并合并

- 通过 GitHub API 直接把 PR #2 的标题/正文替换为评审包内容（标题：*Complete Sapling
  proving optimization campaign and certify combined defaults*；正文含 diff 导读、战役表、
  默认值切换与回滚、复现步骤、适用范围）。原始数据一个字节未动，698 个文件全部保留。
- 以 **merge commit** 方式合并（合并提交 `765dc8b`），刻意不 squash：冻结协议要求的
  「预注册 → 脚本 → 原始数据 → 代码 → 文档」提交链必须保持可审计。54 个提交的历史完整进入 `main`。
- 合并后本地 `main` 快进到 `765dc8b`，工作树干净；三个开关默认值在代码中复核为 `1`。

### 19.2 参数无关层在两个操作系统上转绿

- **GitHub CI（Ubuntu 运行器）**：合并推送首次触发 `.github/workflows/ci.yml`，5 个 job
  全部 success（fmt/clippy、vendored 编译、bellman 49 + groth16 4/3 个库测试、release 构建、
  两个确定性门禁）。日志实证：`12 digests identical across all switch states`、
  `correctness=cross_recoding c=13 ok`、`MSM_WINDOW_BENCH=DONE`。
- **本地 Windows 复跑**（同一批命令，3 min 52 s）：逐项全过，与 CI job 一一对应。
- CI 改进：FFT 门禁现在把 12 个认证摘要**打印到日志**，任何平台的后续运行都可以只凭日志
  做逐字节比对，无需下载 artifact。

### 19.3 跨配置复现：三档指令集摘要一致，线程数不敏感

- 同一提交分别以默认（`x86-64`）、`-C target-cpu=x86-64-v2`、`-C target-cpu=native`
  （本机 AVX-512）构建 FFT 门禁：**12/12 摘要逐字节一致**——目标 f/g 依赖的路径等价不是
  SIMD 宽度的产物。
- MSM 门禁在 `RAYON_NUM_THREADS=1`（CI）与默认线程池（本机 20 LP）下均通过。
- **跨 OS 摘要比对（新增 CI 打印能力的首个运行即验证）**：PR #3 的 CI 运行 39116177753
  （Ubuntu）日志打印的 12 个摘要与 Windows 本机捕获**逐字节一致且顺序相同**——认证摘要集
  现在跨三档指令集 + 两个操作系统/工具链验证一致。提取方法：对 job 日志
  `grep -o 'blake2b=[0-9a-f]\{64\}'`。
- WSL 跨 OS 尝试被环境命令安全策略阻止（`wsl.exe` 黑名单，未尝试任何绕过）；OS 轴由
  Ubuntu CI 覆盖，是比 WSL 更干净的数据点。
- 详见 `experiments/metadata/sapling_cross_config_reproduction_20261018.md`；
  `docs/reproduction.md` §4 同步更新（已覆盖 / 仍开放两部分）。**真正换一台物理机器的
  复现（尤其真实证明内存台账）仍然开放**，已在文档中如实登记。

> 一句话：PR #2 以完整历史合入 `main`，参数无关层从此在 Ubuntu CI 与 Windows 本机双 OS
> 守护，且 FFT 等价性跨三档指令集复核一致；剩下的唯一开放项是换硬件的真实证明复现。

## 20. 最终研究报告（面向导师）+ 仓库同步收尾（2026-10-18）

### 20.1 仓库同步状态（用户评审第 1 步）

- 本地 main 已与远程同步于合并提交 `e4a28ed`，工作树干净；`experiment/fallback-ablation-20261016`
  正好落后 main 4 个提交（765dc8b / 12e6897 / ca50c41 / e4a28ed），全部为合并后的 CI 与复现
  文档补充，无未合并实验代码。后续工作一律从 main 出发。

### 20.2 最终研究报告

- 新增 `docs/sapling_proving_optimization_final_report_zh.md`：面向导师的合成报告，主线五段——
  ①基线与 Prover 成本结构；②四条证据线的瓶颈定位（MSM/算术地板、worker fallback 归因假象、
  核放置与线程饱和、内存结构性地板）；③预注册协议 + 七目标判定 + 负结果为何是资产
  （目标 a 失败直接产出「阈值须从相位分解推导」的方法论，被 f/g 沿用成功）；
  ④组合默认核心结果（−16.38%，六项验收表）；⑤阶段性地板、研究边界与后续方向。
- 写法按用户要求：突出机制、证据、验收规则与限制，不堆 profiling 日志；每个数字都指向一手
  文档（INDEX.md / 各 results / reproduction.md），并声明「与一手文档冲突以一手为准」。
- 入口已挂入 README §13（置顶）与 INDEX.md 顶部。

### 20.3 遗留开放项（不变）

- 换物理机器的真实证明复现（规程见 docs/reproduction.md §4）：内存/正确性数字预期可移植，
  计时不可移植；记录实际偏差。无第二台机器，不停滞项目。
- 已合并分支的归档/改名待用户确认后再动远程 ref。

## 21. 仓库管理收尾：删除 5 个已合并远程分支，只保留 main（2026-10-18）

### 21.1 决策与依据（用户确认）

用户核对 GitHub 分支关系后决定：删除 5 个已合入 main 的远程分支引用，不创建 archive 分支。
理由：①5 个分支的提交均已包含在 main 历史中，删除引用不丢失任何提交、PR 或研究文档；
②archive 分支只是额外指向历史提交的引用，不增加实验数据或复现证据，成果追溯已由最终
报告、实验索引、原始数据与复现文档承担；③远程只留 main 作为正式入口，避免误以为旧分支
仍在开发。明确不动：标签、提交、PR、实验文件、研究文档。

### 21.2 执行与安全核验

- 核验：5 个分支（`experiment/fallback-ablation-20261016`、`analysis/msm-branch-stage-join`、
  `docs/cross-config-reproduction-20261018`、`docs/final-report-20261018`、
  `profiling/spend-stage-timers`）相对 `origin/main` 全部 `ahead=0`，头均为 main 祖先；
  标签 `sapling-engineering-baseline-v1` 指向的提交在 main 可达范围内。删除不会孤立任何提交。
- 执行：一条 `git push origin --delete`（直连）删除 5 个远程引用。删除后 `git fetch --prune`
  确认远程仅剩 `main`（origin/HEAD → origin/main）。
- 历史出处记录（experiments/metadata 下各批次日志中的分支名）保持原样——那是一手证据；
  仅在两处前瞻文档加了指针说明：`docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md`
  基线行、`experiments/metadata/sapling_independent_reproduction_20261018.md` 复现设置表
  （均说明分支已合入 main、远程引用已删除、提交可从 main 到达、此后复现检出 main）。
- 本地同名分支与另一工作树的 `experiment/spend-msm-profile`（仅本地存在）未动；本次仅涉及
  远程引用。

## 22. 只读核查后的文档口径修订（2026-10-18）

用户对远程仓库、CI 记录与文档做只读核查后，提出一处实质性问题与两处澄清，本轮全部修订
（docs-only，无实验结论变化，无需重跑实验）。

### 22.1 内存指标口径拆分（实质性问题）

- 问题：最终报告「一页速览」把两种不同指标写成一行「整进程峰值工作集（优化前 → 优化后）：
  101.30 MiB → 86.18 MB」。实际 101.30 MiB 是历史整进程 `Process.PeakWorkingSet64` 测量
  （含参数加载/证明/验证的全进程生命周期，历史 4+4 次中位数），86,184,607 B 是目标 g 验收的
  证明内存台账 `prove_peak_abs_bytes`——二者不同口径，且原始数据中没有与优化后同口径的成对
  整进程测量。
- 修订：拆成两行——①历史整进程峰值工作集（Spend 101.30 MiB / Output 21.54 MiB，明确标注
  独立进程历史测量、非优化前后配对）；②优化验收台账峰值 103,063,495 → 86,184,607 B
  （−16,878,888 B，−16.38%，Output 未设验收门槛）。表下加口径提示，指向两份一手来源。
  优化结论不变：−16.38% 仍以目标 g 冻结验收数据为依据。

### 22.2 默认开关数量措辞统一

- README 开头与 ci.yml 注释原写「两个默认开启的开关」，实际当前共三个
  （`SAPLING_MSM_SIGNED_DIGITS` 来自目标 b；`SAPLING_MSM_LAZY_RECODING` 与
  `SAPLING_FFT_SERIAL_SINGLE_THREAD` 由目标 g 翻转）。
- 统一为「目标 g 新翻转的两个开关默认开启；连同目标 b 已采纳的开关，当前共有三个默认开启
  的优化开关」：README 开头、ci.yml 注释、最终报告目标 g 行均已按此澄清（README §17 与
  报告回退路径原本已是「三个」，不变）。

### 22.3 实验基线 vs 当前主分支提交

- 最终报告顶部原写基线 `e4a28ed`（当时即当前 main）。现改为：实验代码与数据冻结基线
  `e4a28ed`；后续主分支提交（至 `7e51ca0`）仅用于报告与复现文档收尾，未改动实验数值；
  实验数值以各目标一手结果文档及原始数据为准。

## 23. 完整交易构造计时（2026-10-22）

§1–§22 的时间都来自证明函数（`SpendParameters::create_proof` / `OutputParameters::create_proof`）。
本轮补上交易层：用真实构造器 `Builder::build(...)` 构造一笔固定 **1 spend + 2 outputs**
的交易，直接计时整个构造器起止，再分解时间组成。**这是测量 baseline，不产生优化收益结论。**

预注册（先于代码与测量）：`experiments/metadata/sapling_tx_construction_preregistration_20261022.md`；
一手结果：`experiments/metadata/sapling_tx_construction_results_20261022.md`；报告 §25。

**场景：** spend 100,000,000 zats、收款 60,000,000、找零 39,990,000、ZIP-317 手续费 10,000；
`target_height = 1,700,000`（v5 / NU5）；32 层合成 Merkle 路径、position 0；固定 zip32 种子；
参数文件与既有批次相同。三个独立进程臂各 6 run，丢弃 run 1，亲和性设置后读回核验。

| 暖态中位 | A1 真实 1t @ `0x1` | A2 真实 8t @ `0xFFFF` | A3 mock 1t @ `0x1` |
|---|---:|---:|---:|
| `t_total_construct`（build + serialize） | **4,292.720 ms** | **1,176.072 ms** | 4.888 ms（对照） |
| `t_build` | 4,292.699 ms | 1,176.049 ms | 4.832 ms |
| `t_serialize` | 0.022 ms | 0.024 ms | 0.020 ms |
| `t_proving`（独立组中位差） | 4,287.867 ms（**99.89%**） | — | — |
| `sum_proofs` | 4,292.703 ms | 1,175.588 ms | 4.367 ms |
| spend / output A / output B | 3,321.5 / 480.2 / 486.2 ms | 928.0 / 132.7 / 127.9 ms | mock |
| `t_verify`（不计入构造） | 10.384 ms | 13.826 ms | 未做 |

- **构造时间 = 证明时间：** 99.89% 的 `t_build` 是 Groth16；sighash、Spend 授权签名、
  binding 签名、bundle 装配与序列化合计约 **5 ms（0.11%）**。
- **两个独立估计闭合：** 独立组 `t_proving` 与 `sum_proofs` 相差 0.113%（门限 5%）。
  主估计取两组中位之差，**不是逐 run 配对**：mock 臂不消耗证明随机数，从 run 2 起
  RNG 流与真实臂分叉（A1/A3 只有 run 1 的 txid 相同）；编号对齐差 4,287.528 ms 仅作诊断。
- **8 线程 3.65×：** 总构造时间降到 1/3.65，并行效率约 45.6%，与既有 8 线程饱和结论一致。
- **结构常量：** 12 条真实 + 6 条 mock run 均为 2,377 B、v5、1 spend / 2 outputs、fee 10,000、
  Sapling value balance +10,000（分析脚本在 18/18 行独立复检）；12/12 通过 `BatchValidator`；
  验收表 7/7 PASS（主判据 18/18）。txid 随 run 变化，结论是"序列化长度与结构一致"，
  不是"交易字节完全相同"。
- **边界：** 本地构造时间，不含参数加载（约 27 s，在计时窗口外）、钱包输入选择、note 解密、
  数据库、广播、mempool、打包与确认；Merkle 路径与 note 为**合成测试状态**。
- **测量前偏差：** 初版预注册按 3 个 logical actions 估手续费 15,000；ZIP-317 实际取
  `max(1 spend, 2 outputs) = 2`，故为 10,000。修正发生在任何正式测量之前，记录在预注册 §10。
- **评审后收紧（不触碰原始数据）：** 交易 crate 已纳入 CI（`cargo fmt --check` +
  `cargo clippy -- -D warnings` + `cargo check --locked --all-targets`）；分析脚本独立复检
  mock 臂全部结构字段；`t_proving` 主定义改为独立组中位差，编号对齐差降为诊断。冻结阈值未改。

产物：`experiments/raw/csv/sapling_tx_construct_runs_{real,mock}.csv`、启动摘要 CSV、
`experiments/raw/logs/tx_construct_*`、`results/tables/sapling_tx_construct_*_20261022.csv`、
`results/figures/sapling_tx_construct_*.png`；代码 `experiments/transaction-smoke/`；
分析 `scripts/analyze_tx_construct_experiment.py`；启动器 `scripts/run_tx_construct_campaign.ps1`。