# MSM 内核研究计划与研究状态冻结（2026-10-23）

**阶段定位：MSM 内层算法与曲线算术优化预研——从参数调优转向群运算内核。**

本文件是阶段 A 的产出，冻结当前研究状态，作为下一轮研究的唯一状态入口。实验数据的权威入口是 [`experiments/metadata/INDEX.md`](../../experiments/metadata/INDEX.md)（一张索引表覆盖全部 campaign targets 与 measurement threads）；本文件只收敛结论，不复制原始实验结果。阶段 B 的文献对照表见 [`msm_literature_survey_20261023.md`](msm_literature_survey_20261023.md)。

> **状态同步（2026-10-23 结项后）：** 阶段 A（本文件冻结）、B（[文献对照](msm_literature_survey_20261023.md)）、C（A/A 校准 + 同输入 MSM 基准 vs blst）均已完成，成果经 **PR #17** 合入 main（`a705f508`）。当前研究进度：**阶段 D 尚未实施**——xyzz 桶 fill 内核为已文档化候选，是否实施须另立预注册（见 §6）。§1–§4 的阶段 A 冻结内容作为历史记录保留；§3 的代码基线与 §5 的分支纪律已按结项状态更新。

## 1. 已经认证的优化及其原始数据入口

生产默认开启的优化开关共三项（README 顶部"two switches"的旧表述已于本次修正为三项）：

| 开关 | 来源 target | 认证结果 |
|---|---|---|
| `SAPLING_MSM_SIGNED_DIGITS=1` | b — balanced-signed window recoding | Spend 1t −6.63%、Output 1t −11.35%、peak −2.00 MB |
| `SAPLING_MSM_LAZY_RECODING=1` | g 组合项 | 与 f 共同构成 −16.38% 内存收益 |
| `SAPLING_FFT_SERIAL_SINGLE_THREAD=1` | g 组合项 | 同上 |

| 已认证事项 | 关键结果 | 数据入口（INDEX.md） |
|---|---|---|
| g — 组合 + 默认翻转 | shipped-default Spend prove peak 103.06 → 86.18 MB（−16.38%），100% 正确，无时间回归 | Campaign targets 表 g 行 |
| f — 单线程 FFT four-step scratch 移除 | lazy=1 下 peak −3,945,720 B（恰为可转换最大值） | Campaign targets 表 f 行 |
| e — 线程数/亲和性配置（部分认证） | setup 1.8–1.9×；线程数下调使 Output 回归 21.8% | Campaign targets 表 e 行 |
| 正式基线 | Spend prove median 3,385.7 ms / Output 514.9 ms（最快批次）；pinned baseline 3,685.6 / 558.5 ms | Measurement programme 表第 1 行 |
| 交易层计时基线 | 1 spend + 2 outputs：`t_total_construct` 4,292.7 ms（1t @ `0x1`）/ 1,176.1 ms（8t @ `0xFFFF`）；proving share 99.89% | Transaction construction (2026-10-22) 行 |
| closure 侦察 | 内存：结构下限 86.18 MB（peak 由 `circuit_synthesis` 持有）；时间：MSM ≈85% of prove，bucket fill ~462 ns/nonzero digit，c=13 时间最优 | Campaign targets 表 closure 两行 |

## 2. 已经关闭的研究路线和具体失败原因

| 路线 | 结论 | 失败原因 |
|---|---|---|
| Stage 1b 窗口自适应 + 尾窗口分裂 | NO_GO | P1 Spend C1/C0 = 1.019（CI 0.958–1.077）；forced c=11 control C4/C0 = 0.999；tail split C2 = 1.117、C3 = 1.027；P4 FAIL；Output P5 CI 上界 1.0546 > 1.05；Stage 0 的 c=11 657.81 ms 未复现（C4 679.60 ms） |
| c=12 pilot | NO_GO | C0 731.354 / C1 690.717 ms，R = 0.9444（G1 过）；但最慢 C1 703.710 > 最快 C0 698.611（G2 反例失败，0.73%） |
| Stage 3 独立证明并发 | NO_GO | S0 670.908 → S1 560.983 ms/proof（R = 0.836，G1 过）；但 batch 6 出现 938.951 > 647.044（G2 失败）；单证明延迟 +66.27% |
| Stage 4 QAP/FFT 调度 | 关闭 | QAP 118.803 → 96.424 ms（−18.84%），但完整证明仅 −3.89%，低于 5% 门槛；后续三组 −5.09% 与顺序混淆，不采用 |
| Stage 5 FFT 算术 | MARGINAL 关闭 | 1t 2^17 45.809 → 29.490 ms（1.553×）、8t 全变换 14.980 → 12.021 ms（1.246×），均低于冻结的 1.25× S3 门槛 |
| Stage 6 电路合成 | NO_GO | 无单项 ≥5%：eval A/B/C 合计 29.744 ms = body 4.63%；probe-on/off 合成差 ~16 ms；alloc 54.266 ms / enforce 57.897 ms 为大项但无独立优化点 |
| Stage 1c 机制核查 | 仅侦察 | 同进程 bench：c=12 最低，c=11 vs c=13 +1.6%/+6.3%；绝对漂移 10–16%；支持 Stage 1b 的 null，不构成新结论 |

**共同教训**：跨批次绝对耗时漂移达到 10%–16%，超过多个候选之间的差异。这是阶段 C 必须先做 A/A 测量校准的直接原因。

## 3. 当前生产配置与实验环境

- **代码状态**（两项分列，避免把历史基线误写为最新提交）：
  - 当前 main HEAD（2026-10-23 本轮文档维护冻结时点）：`85d4edd2b4b53836c66a5563f6c1e348228e74d7`（PR #19 合并提交；PR #18 `6b482896cb355ad3b9588f793c7af294809932ba` 同属本轮纯文档更新，均无代码改动）；
  - 阶段 C 测量及生产代码基线：`a705f508d1e8a6d01b7b7136f7564ccf8633ca0a`（PR #17，阶段 A–C 结项合入；阶段 C 全部测量均在该基线上的生产代码完成）；更早的阶段 A 冻结基线 `4454c53` 已过时。
- CI 6 job 全绿（PR #19 的 pull_request 运行与合并后 main 的 push 运行均 6/6 success；本轮及后续纯文档提交不改变代码基线与任何认证结论）。
- **主机**：Intel Core i7-14700（8 P-core + 12 E-core，28 线程；Intel ARK 官方指令集规格为 SSE4.1 / SSE4.2 / AVX2，**不含 AVX-512**）；32 GB 内存；Windows 11；Rust 1.98.1；release 构建。
- **协议栈**：Groth16 / BLS12-381；sapling-crypto 0.9.0（锁定 `88a7946b…`）；本地 vendor/bellman 0.15.0 与 vendor/groth16 0.2.0。
- **主测试条件**：8 P 核固定亲和性（`0xFFFF` 或 `0x5555` 按实验预设），`RAYON_NUM_THREADS=8`；预热 + 多次正式测量取中位数。
- **真实查询规模**：H-query G1 n = 131,071；L-query G1 与 A/B 辅助 G1 各 98,638；B-G2 98,638；输入相关小查询 8 个标量槽。
- **MSM 实现现状**（`vendor/bellman/src/multiexp.rs`）：Pippenger；balanced-signed 重编码（桶数 2^(c−1)，biased slot 存储，lazy carry-bit 变体）；bucket fill 占 Spend H-query MSM ~94%；每次混合加 ~462–470 ns（11 次 Fp 乘法），同批次口径下**算术受限而非内存受限**（实现级成本口径：阶段 C 同主机对照 blst ≈253 ns/模型操作，见 §6）；填充循环无软件预取；桶为标准投影坐标，无批量仿射转换。

## 4. 下一轮允许研究的候选及 Go/No-Go 判据

### 4.1 候选：MSM bucket fill 点累加内核（唯一候选方向）

> 研究问题：在 CPU 多核环境下，对 BLS12-381 的 Pippenger 类 MSM，能否在不改变计算结果、控制额外内存的前提下，减少 bucket fill 的单位群运算成本，并在真实 Sapling Spend 证明中获得稳定的端到端收益？

文献审查后排定的候选子方向（依据见文献对照表 §3）：

1. **blst 式 bucket fill 内核技术**：xyzz（缓存 Z²/Z³）桶坐标 + 仿射点混合加、填充循环内对下一个桶的软件预取、批量仿射转换（Montgomery trick）。不依赖 SIMD，可在 i7-14700 上直接验证。
2. **Fan et al. (JoC 2025) 最优桶集合 + endomorphism 分解**：改的是桶集合构造与标量分解方式，不是窗口宽度；前作 Luo-Fu-Gong (TCHES 2023) 在 BLS12-381 + blst 上实测对流行 Pippenger 变体省 3.1–9.2%、对 blst Pippenger 省 17.7%。
3. **（小查询专用）固定基 BGMW/查表路线**：仅适用于 8 标量槽的输入相关小查询，不参与 H-query 决策。

一次只验证一个子方向；不同时改窗口、线程池和点运算公式。

> **2026-10-23 阶段 C 后**：首选候选明确为第 1 项（xyzz 桶 fill 内核）——阶段 C 实测将 bellman/blst 差距归于 fill 点加公式（1.9063×，CI95 [1.8999, 1.9110]，两轮复现）；第 2、3 项保留为后续候选，不并入下一轮实验。实施前须另立预注册（含侧信道语义评估，见 §6 阶段 D）。

### 4.2 Go/No-Go 判据（实验前冻结）

**内核筛选门槛**：对 H-query 这样的主要负载取得可重复的改善（"可重复"的统计形式在阶段 C 预注册中定义），并计算实际影响比例（内核收益 × 内核时间占比）。只在极小 MSM 上快、覆盖不了证明主要耗时的，不继续投入。

**正式证明门槛**：完整 Spend proof 中位耗时改善 ≥ 5%，用预先设定的配对区组或 cluster bootstrap 置信区间确认收益方向；Output 与交易层通过预先设定的非回退判据。

**必要条件**：正确性检查通过（群意义一致）；峰值内存不超出冻结资源预算（以 86.18 MB 为基线，上限在预注册中冻结）；G1 与 G2 分别报告；不改变证明系统安全性假设（含侧信道语义评估）；原始数据与候选代码可独立复现。

**停止条件**：内核有提升但完整 Spend proof 没有可靠改善 → 关闭候选。不得只报告内核加速比来代替整个证明系统的收益。文献筛选或初步实验若发现没有合适候选，提前停止，不为走完流程强行写新算法。

## 5. 实验分支与数据纪律

- 阶段 A/B/C 实验已在分支 `experiment/msm-kernel-20261023` 完成并经 PR #17 合入 main（`a705f508`）；下一阶段（阶段 D）如需继续，应**从当前 main 创建新的实验分支**，而非从已合入的旧基线出发；生产默认值保持不变。
- 原始 CSV、日志与历史数据不覆盖；失败或过时批次保留，作为可追溯性的一部分。
- 新候选必须有独立配置、版本和结果记录；仅通过显式参数启用。
- 算法正确性验证与性能测试分开进行。
- 任何新测量前先冻结预注册（沿用 `experiments/metadata/*_preregistration_*.md` 惯例），阈值不得在看到结果后修改。

## 6. 阶段 C–E 路线图（2026-10-23 同步：A/B/C 已完成，D 尚未实施）

- **阶段 C（已完成，PR #17 合入）**：A/A 测量稳定性校准 → `msm-kernel-bench`（同输入同输出，H-query 优先，计时拆分参数读取/基点转换/预计算/MSM 核心，含 blst 对照实现）→ 性能差距表。结果：1t A/A 半宽 0.25–1.29% 达标（门槛：测量不确定性明显小于 5% 的完整证明收益目标）；**P1 = bellman/blst = 1.9063（CI95 [1.8999, 1.9110]，两轮独立复现）**，差距归于 fill 点加公式。入口：[阶段 C 预注册](../../experiments/metadata/sapling_msm_kernel_stagec_preregistration_20261023.md)、[阶段 C 结果](../../experiments/metadata/sapling_msm_kernel_stagec_results_20261023.md)。
- **阶段 D（暂停，不立即实施）**：xyzz 桶 fill 内核（见 §4.1）作为候选仍保留，但当前优先级让位于端到端 Testnet 交易剖析（见下）；如需继续，须另立预注册。只在隔离内核做完全一致性测试（零 digit、最大 digit、signed digit、进位边界、单位元、相同/互逆点）；预注册必须包含：具体点加内核选择、测试负载、正确性测试、统计方案、内存上限与停止条件；blst 点加实现非 constant-time，候选进入生产默认路径前须单独评估标量相关分支与访存的侧信道语义。
- **端到端 Testnet 交易剖析（当前优先，非 MSM 内核工作）**：研究目标已转向端到端 Testnet 真实转账的耗时与内存剖析（钱包输入准备 → 确认，含证明生成分段），范围界定 [`../experiments/metadata/sapling_real_input_tx_proving_scoping_note_20261026.md`](../experiments/metadata/sapling_real_input_tx_proving_scoping_note_20261026.md) 与预注册 [`../experiments/metadata/sapling_e2e_testnet_tx_preregistration_20261026.md`](../experiments/metadata/sapling_e2e_testnet_tx_preregistration_20261026.md)。既有 MSM A–C 优化保留为对照基线；本工作不改动生产实现。
- **阶段 E（未开始）**：正式 A/B、全证明验证、多规模负载扩展与论文可行性判断。

阶段 C 已否证"成熟实现与当前实现接近"的可能：同主机、同线程数下 blst 的单位操作成本约为 bellman 路径的一半（≈253 vs ≈482 ns/模型操作），差距为实现级且可定位。后续候选按 §4 判据执行；一个经过严格验证的 NO_GO 结论同样是有价值的产出。
