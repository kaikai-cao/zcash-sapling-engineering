# Zcash Sapling 证明优化：最终研究报告

**文档类型：** 面向导师的结项研究报告（合成文档）
**日期：** 2026-10-18
**代码与数据基线：** 实验代码与数据冻结基线：`main` @ `e4a28ed`；`sapling-crypto 0.9.0`（`88a7946b…`）；`vendor/bellman 0.15.0`、`vendor/groth16 0.2.0`（含本研究插桩）。后续主分支提交（至 `7e51ca0`）仅用于报告与复现文档收尾，未改动任何实验数值；实验数值仍以各目标的一手结果文档及原始数据为准。2026-10-23 结项整理将 MSM 内核预研阶段 A/B/C 的文档、基准、脚本与原始数据合并进 `main`（合并提交 `207a296`），同样未改动任何 a–g 实验数值。
**测量环境：** Windows 11、Intel Core i7-14700（8 P-core + 12 E-core）、32 GB RAM、Rust 1.98.1、Release、Groth16 + BLS12-381
**证据原则：** 本报告只作合成与解释；每个结论都指向可独立复核的结果文档与原始数据（见 §8 索引）。优化结论均来自**预注册冻结后**才产生的测量，原始数据一个字节未动。

---

## 0. 一页速览

| 维度 | Sapling Spend | Sapling Output |
|---|---:|---:|
| R1CS 约束数 | 98,777 | 7,827 |
| FFT 域大小 N | 131,072 = 2¹⁷ | 8,192 = 2¹³ |
| Prove 中位数（绑核冻结基线，1 线程 @LP0） | 3,685.6 ms | 558.5 ms |
| Verify 中位数 | 2.790 ms | 2.150 ms |
| 证明大小 / 验证 | 192 B，5/5 | 192 B，5/5 |
| 历史整进程峰值工作集（`Process.PeakWorkingSet64`，独立进程测量，**非优化前后配对**） | 101.30 MiB | 21.54 MiB |
| 优化验收：证明内存台账 `prove_peak_abs_bytes`（目标 g：lazy=0,fix=0 → lazy=1,fix=1） | 103,063,495 → **86,184,607 B（−16.38%）** | 未设验收门槛（目标 g 仅验收 Spend） |
| MSM 占证明时间（单线程） | ≈85–88% | ≈93% |

> **口径提示（两种指标，勿混用）：** 表中「历史整进程峰值工作集」来自 Windows 整进程测量
> （`Process.PeakWorkingSet64`，250 ms 采样，含参数加载、证明生成与验证的整个进程生命周期，
> 表中为历史 4+4 次测量的中位数）——它是**独立进程的历史记录，不是优化前后配对结果**；
> 现有原始数据中没有与优化后同口径的成对测量，因此不能表述为「整进程峰值降到 86.18 MB」。
> **−16.38% 依据的是证明内存台账** `prove_peak_abs_bytes`（目标 g 的预注册验收主指标）：
> 103,063,495 → 86,184,607 B（−16,878,888 B）。一手来源：
> [`experiments/raw/csv/sapling_process_memory_raw.csv`](../experiments/raw/csv/sapling_process_memory_raw.csv)、
> [`sapling_combo_default_results_20261018.md`](../experiments/metadata/sapling_combo_default_results_20261018.md)。

**一句话结论：** 在一条预注册验证协议下完成了 7 个优化目标的受控评估（目标 b 与 g 通过认证并已成为出厂默认，目标 a 按冻结规则失败归档），组合默认配置使 Spend 证明峰值内存下降 **16.38%**（103,063,495 → 86,184,607 B）且无任何时间退化；此后侦察确认本管线在两个优化维度上均到达地板，战役结项。参数无关的正确性层已在 Windows 与 Ubuntu 两个操作系统上交叉验证一致；换硬件的真实证明复现是唯一明确的开放项。

---

## 1. 基线与 Prover 成本结构

**机制。** Sapling 证明是 Groth16： witness → R1CS → QAP（A/B/C 各 3×IFFT + 3×coset FFT、A·B−C、除 Z、icoset FFT 生成 H 指数）→ 三个 MSM（A/B/C，G1/G2 混合）→ 配对验证。成本结构由三件事决定：电路规模（约束数决定 QAP 域大小 N 与各 query 长度）、参数文件规模（决定解码内存与 MSM 点数的上限）、以及每条 query 的**指数分布**（决定 Pippenger 桶填充分子数）。

**证据。** Spend 电路 98,777 条约束 → QAP 域 N = 131,072；参数文件 45.74 MiB，含 376,701 个 G1 点与 61,400 个 G2 点；每次证明 8 次 MSM 调用，最大单次为 H query G1（131,071 点×标量）。Output 电路小一个量级（7,827 约束，N = 8,192）。完整逐步数字账（每个阶段、每个点、每块内存）在 [`sapling_proving_parameter_and_bottleneck_breakdown_zh.md`](sapling_proving_parameter_and_bottleneck_breakdown_zh.md) §1–§7。

**验收规则。** 正式基线一律使用**绑核冻结值**（1 线程 @LP0，暖态中位）：Spend 3,685.6 ms / Output 558.5 ms。历史未绑核数据（含 E-core 污染，Spend 3,515.9 ms）只作「未约束分布」参考，不与冻结基线混算——这是全部时间结论的口径前提。

**限制。** 单线程时间受 CPU 核放置影响可达 2.6×（P-core ≈3.4–4.0 s vs E-core ≈5.3–9.1 s），且不绑核时进程会在核间迁移（Output 批内极差实测 70%）。任何时间数字必须连同亲和性、线程数、主机负载一起引用。

---

## 2. 瓶颈定位：四条证据线的结论

### 2.1 时间线：MSM 是主成本，桶填充是算术地板

**机制。** 证明时间的 ≈85–88%（Spend，单线程）花在 MSM；MSM 内部 ≈78% 是 Pippenger 桶填充，即逐非零数字的群加。群加是固定成本的算术操作，因此存在一个**不随工程技巧消除的地板**。

**证据。** 同批次直接普查：每次 Spend 证明 H query 有 **2,620,825 个非零数字**，填充中位 1,211.7 ms，即 **462 ns/非零数字**——与 bellman 注释中记录的 ~470 ns 混合加成本一致。窗口宽度 c=13 对三大 query 均经操作数模型核算为最优。来源：[`sapling_default_time_profile_20261018.md`](../experiments/metadata/sapling_default_time_profile_20261018.md)。

**限制。** 「算术地板」的陈述边界是**本管线**（vendored bellman 的 Pippenger 实现、此电路集合、此测量条件）；它不排除其他实现（如更激进的批归一化或端点公式）改变单加成本本身。

### 2.2 Worker fallback：是一个归因假象，不是吞吐瓶颈

**机制。** 插桩曾显示 MSM 提交阶段出现大间隔，一度被怀疑是 worker 回退路径的调度缺陷。绑核 A/B 消融证明：大提交间隔是**排队工作在提交期间被同步执行**的计时归因假象。

**证据。** 1 线程绑核条件下端到端差异 +1.1%（p≈0.11，不显著）。来源：[`sapling_spend_worker_fallback_ablation_conclusion_20261017.md`](../experiments/metadata/sapling_spend_worker_fallback_ablation_conclusion_20261017.md)、报告 §9.1。

**限制。** 该结论只在单一线程数（1）与单一 workload 下成立；其他线程配置未测。

### 2.3 线程与核放置：扩展在 8 线程饱和；P 核绑核改善 setup

**机制。** 混合架构上，线程扩展受 SMT 超订与 P/E 核异构双重制约；setup 阶段（参数解码）对所在核的类型敏感。

**证据。** 绑核条件下线程扩展曲线在 8 线程饱和（并行效率 58.8%），8→16 仅 +3.9%，16→20 反而慢 2.9%；setup 阶段绑 P 核快 1.8–1.9×。来源：[`sapling_pinned_baseline_and_thread_scaling_20261017.md`](../experiments/metadata/sapling_pinned_baseline_and_thread_scaling_20261017.md)（即目标 e，见 §3）。

**限制。** >20 线程未测；「P 核掩码 + 默认线程数」这类过订组合未做往返深度测试。

### 2.4 内存线：峰值由电路合成阶段主导，存在不可释放的结构性余量

**机制。** prove 峰值的所有者是 `circuit_synthesis`（QAP 构建）：三个合成 Vec 的 capacity 均被 `from_coeffs` 的 resize **原地消费至 131,072（= QAP 域大小）**——不是余量，是全量占用；唯一真正的堆余量（aux，1,037,888 B）位于峰值点、不可释放。因此 MSM 侧的任何改动都无法把峰值压到 86.18 MB 以下。

**证据。** 合成容量探针（`SAPLING_G16_SYNTH_CAPACITY_PROBE`，默认关闭）+ 全局内存台账。来源：[`sapling_default_stage_decomposition_20261018.md`](../experiments/metadata/sapling_default_stage_decomposition_20261018.md)、报告 §24.1。

**限制。** 这是**本电路规模与本地分配器**下的结构性地板；换分配器或换电路规模会改变具体字节数（这正是跨硬件复现要记录的内容）。

---

## 3. 优化战役：预注册协议、七个目标、保留的负结果

### 3.1 方法：为什么这些数字可以信任

- **预注册冻结先于测量。** 每个目标的指标、阈值、臂集、统计方法与守门条件在测量前写入文档并单独提交；测量后只判定、不改验收表。
- **ABBA 与配对统计。** 时间结论用同二进制 A/B、ABBA 交替、配对检验（MWU）；内存结论用每臂 5 次进程调用取暖态中位。
- **提交链拆分。** 预注册 → 脚本 → 原始数据 → 代码 → 文档，各自独立提交，审计链完整（54 个提交随 PR #2 原样合入 main，未 squash）。
- **漂移守门。** 时间非退化预算 ±1%/臂；超预算即整个目标作废，不挑有利批次。
- **负结果保留。** 未达阈值的目标按规则归档，开关默认值留在 `0`，原始数据与判定文档一并保留——它们同样是研究发现（见 §3.3）。

### 3.2 七个目标的判定（全部对照各自冻结验收表）

| 目标 | 类型 | 结果 | 判定 |
|---|---|---|---|
| e — 线程数/亲和性配置 | 配置 | setup 绑 P 核快 1.8–1.9×；裁线程使 Output 退化 21.8%（p=0.0102） | 部分认证（仅绑核建议） |
| b — H query G1 有符号窗口重编码 | 算法 | Spend 1t **−6.63%**（配对 −6.94%，5/5，MWU p<1e-4），Output 1t **−11.35%**，峰值 **−2.00 MB** | **certified，默认 `1`** |
| a — H query 窗口化表示「去物化」 | 内存 | 缓冲 24.1 MB→0.33 MB，各臂全更快，但峰值 −12.93 MB **< 冻结阈值 15 MB** | **按冻结规则失败 → 归档** |
| f — 单线程 FFT four-step scratch 消除 | 内存 | lazy=1 下峰值 **−3,945,720 B，一分不差等于可转化上限** | **certified** |
| g — 组合 + 默认值切换 | 内存 | 出厂默认峰值 **−16.38%**，时间三臂全更快，正确性 100% | **certified，两个默认值翻 `1`**（连同目标 b 的开关，当前共三个默认开启） |
| 结项侦察（内存线 / 时间线） | — | 结构性地板 86.18 MB / 算术地板 462 ns 每数字 | 记录，无新目标 |

逐项判定表与原始数据入口：[`experiments/metadata/INDEX.md`](../experiments/metadata/INDEX.md)（单一总表）。

### 3.3 负结果为什么是资产而不是污点

目标 a 的失败直接产出了下一个发现：它证明 prove 峰值已换成 QAP/FFT 阶段的次级天花板（`qap_fft_h_exponent_prep`，90.13 MB），MSM 侧改动对此无能为力。由此确立的方法论（内存阈值必须从**相位分解**推导，即 `min(缓冲毛字节, 峰值 − H2)`，而非单点模型估算）被目标 f/g 直接沿用并成功——f/g 拿到的正是 `峰值 − H2` 这个可转化上限的全部字节。一次按规则归档的失败，换来了后续两个目标的正确阈值设定方式。

同类保留还有两处自我更正：窗口化指数非零密度此前的推断值（~94%）被直接普查（99.35%）取代；窗口化缓冲大小在档案中的三个数字（26.2/22.0/19.9 MB）被证明是同一缓冲的毛/净两种口径并已调和。旧数字在文档中明确标注「不应再被引用」。

---

## 4. 组合默认配置的核心结果（目标 g）

**机制。** 两个开关叠加：`SAPLING_MSM_LAZY_RECODING=1`（窗口化指数按需惰性转换，省去一次全量物化）与 `SAPLING_FFT_SERIAL_SINGLE_THREAD=1`（单线程 FFT 走四步法路径，省去该路径的 transient scratch）。目标 a 证明了 MSM 侧单独改动最多拿到 12.93 MB；f/g 把 QAP/FFT 侧的可转化空间一并取尽，组合拿下 **−16.88 MB**，越过 a 未能达到的 15 MB 冻结门槛。

**证据（对照冻结验收表，六项全过）：**

| # | 指标 | 冻结阈值 | 实测 | 判定 |
|---|---|---:|---:|:--:|
| 主 | prove 峰值 (lazy=0,fix=0)→(lazy=1,fix=1) | 中位下降 ≥ 15,000,000 B | **−16,878,888 B（−16.38%）**：103,063,495 → 86,184,607 B | MET（超门槛 1.88 MB） |
| 辅1 | 正确性 | 100% | 台账 10/10 + 时间战役 360/360 + 翻转后 5/5，证明均 192 B | PASS |
| 辅2 | 时间非退化 | 每臂 ≤ +1% | 三臂集 −5.81% / −3.95% / −2.35%（均为负） | PASS |
| 辅3 | 切换后复验（不设任何开关） | 三项全过 | 12/12 digest 一致；台账 +7 B；5/5 | PASS |
| 辅4 | 数据卫生 | 不覆盖 | 全新 label，无覆盖 | PASS |

**回退路径。** 三个开关（`SAPLING_MSM_SIGNED_DIGITS` / `SAPLING_MSM_LAZY_RECODING` / `SAPLING_FFT_SERIAL_SINGLE_THREAD`）默认均为 `1`，每个环境变量仍可双向覆盖；设为 `0` 即逐位恢复旧行为，FFT 门禁对两种路径给出逐位相同的 12 个摘要。

**限制。** 该结果在**既定测量条件**（单主机、绑核口径、本地分配器）下认证；它不保证其他硬件/OS 上获得相同字节收益（内存与正确性数字预期可移植，时间数字不可移植——见 §6）。

---

## 5. 阶段性地板与研究边界

- **内存线：结构性地板 86.18 MB。** 峰值由 `circuit_synthesis` 的 QAP 构建拥有；三个合成 Vec 的 capacity 被 `from_coeffs` 原地消费至域大小，唯一真余量（aux，1,037,888 B）位于峰值点不可释放。目标 f 已一分不差取尽其预注册可转化上限（3,945,720 B）；在此之上，全局剩余物理可转化上限仅 **3,314,512 B 且被证明不可达**（a/b/c 容量即域大小，动之更差）。**没有值得立即追逐的内存微优化目标。**
- **时间线：算术地板。** MSM ≈85% 的 prove，其中桶填充 ≈78%，462 ns/非零数字与文档化的混合加成本一致；窗口 c=13 经操作数模型核算为最优。**同样没有值得立即追逐的时间微优化目标。**
- **边界陈述。** 两条「地板」结论的范围是本管线（vendored bellman + Sapling Spend/Output）、当前机器与测量条件；它们不是关于「ZKP prover 在所有实现和硬件上没有优化空间」的普适命题。
- **因此结项，而非继续加实验。** 协议要求每个新目标先有可证伪的机制假设与预注册阈值；在地板结论之下继续调窗口/线程/释放方式，只会回到「不断增加实验却回答不了研究问题」的状态。

---

## 6. 复现与验证状态（截至 2026-10-18）

| 层 | 状态 | 证据 |
|---|---|---|
| 同主机独立复现（干净 checkout、全新构建、不设任何开关） | **通过** | 门禁一致；台账 5/5；峰值 86,184,600 B vs 认证 86,184,607 B（**−7 B**，分配器粒度内）；prove ≈3,233 ms。 [`sapling_independent_reproduction_20261018.md`](../experiments/metadata/sapling_independent_reproduction_20261018.md) |
| 参数无关 CI（fmt/clippy、库测试、构建、交易 crate 检查、两个门禁） | **双 OS 绿** | Ubuntu CI 6/6 job（合并后 main；第六个 job 于 2026-10-22 增加）；Windows 本机等价复跑全过。 [`ci.yml`](../.github/workflows/ci.yml) |
| 跨指令集摘要一致性 | **通过** | 同一提交三档构建（`x86-64` / `x86-64-v2` / `native`），FFT 门禁 12/12 摘要逐字节一致 |
| 跨 OS 摘要一致性 | **通过** | CI 日志打印的摘要集与 Windows 捕获 12/12 逐字节一致且顺序相同（run 39116177753） |
| **本地真实输入交易构造与证明基准（外部有效性）** | **开放** | 范围界定：[`../experiments/metadata/sapling_real_input_tx_proving_scoping_note_20261026.md`](../experiments/metadata/sapling_real_input_tx_proving_scoping_note_20261026.md)。覆盖真实 Note/witness 接入 → 交易构造 → 证明 → 序列化 → 本地验证；**不**覆盖广播/mempool/打包/确认/钱包同步（单独后续网络阶段）。预计需另一台机器 + 真实 witness：门禁 + Spend 证明/验证/大小 + 多次 prove 峰值统计 + 工具链/OS/CPU/参数哈希/commit；预期内存与正确性数字可移植、计时不可移植；记录实际偏差而非要求一致。规程：[`reproduction.md`](reproduction.md) §4 |

---

## 7. 结论与建议的后续方向

1. **成果形态。** 本项目现在的价值不是「快了多少」，而是一条可审查、可复现、可引用的工程研究链：预注册协议 → 受控测量 → 冻结判定 → 保留负结果 → 双 OS 自动门禁 → 单一实验索引。
2. **方向一：一般的 SNARK prover 资源成本模型。** 本研究在单一电路规模上确立了「峰值由电路合成主导、可转化上限 = 峰值 − 次高阶段高度 H2」的结构；下一步可以研究内存峰值如何随电路规模与 query 规模缩放（多 N 的相位分解），给出可预测的成本模型而非逐案例测量。
3. **方向二：协议结构学习。** 把已掌握的工程测量能力（账本、探针、ABBA 判定）与 Groth16/PLONK 等协议的结构问题结合，转向更具普适性的理论问题。
4. **不建议。** 在本地板结论下继续 target h 式微优化（窗口、线程、释放方式的继续微调）。

---


> **2026-10-22 更新（Stage 0）：** 交易 baseline 之后的 44 批诊断显示，8t 的损失不能只归因于 SMT（Spend `0xFFFF`→`0x5555` 为 4.22%，90% CI 跨 0；H2 部分支持）；H-query 窗口尾部被支持（`c=12`/`c=13` 的 `ns_per_add` R=0.8047，90% CI 上界 0.8465），且本负载实际 8t prove 最好的是 `c=11`（W=24，100% 尾部，657.81 ms，5.07×）。因此“继续微调窗口”不是无依据的 target h，而应作为**单独预注册的 Stage 1 自适应窗口/窗口内切分**（`W mod P` 感知、带 bucket 内存上限）来检验；8t `0x5555` 作为控制，16t 不推荐。详见 [`sapling_msm_scaling_diagnosis_results_20261022.md`](../experiments/metadata/sapling_msm_scaling_diagnosis_results_20261022.md)。
> **2026-10-23 更新（MSM 内核预研阶段 A–C 与结项）：** 战役结项后转入 MSM 内层算法与曲线算术预研，完成三个阶段并做结项整理（[结项文档](msm_kernel_project_closeout_20261023.md)）。**阶段 A** 冻结研究状态（已认证优化及数据入口、已关闭路线及失败原因、生产配置、下一轮候选与 Go/No-Go 判据）；**阶段 B** 完成文献对照（Fan et al. JoC 2025 的最优桶集合 + endomorphism、SimdMSM TCHES 2025 依赖 AVX-512 IFMA——本机 i7-14700 仅有 AVX2，实现与加速比均不可移植、blst 的 Booth 重编码/xyzz 桶/批量仿射转换、2026 固定基预印本仅覆盖小 MSM）；**阶段 C** 建成同输入 MSM 内核基准（H-query G1 n=131,071 等 5 个负载，fixture 与计时分离）并与 blst 库单线程对照，两轮独立复现均通过预冻结门禁：**bellman 单线程 H-query G1 全 MSM 耗时为 blst 的 1.9063 倍（CI95 [1.8999, 1.9110]，P1 = GO）**；单位成本探针将差距完全归于 fill 点加公式（同一「模型操作」分母下 bellman ≈482 ns/操作、blst ≈253 ns/操作；bellman Jacobian 混合加探针实测 477 ns/数字，与 482 一致；域运算层无差距 16.29 vs 20.38 ns，reduce 层无差距）。**口径修正：** §2.1 与 §5 的「算术地板」应读作**本管线 vendored bellman 的实现级单位成本地板**——同等操作数下，成熟实现于同一主机达到约一半的单位成本。这不否定任何 a–g 认证结果（它们全部在 bellman 路径上测得且仍然成立），但「无进一步时间优化目标」的陈述范围仅限已关闭的调参路线（窗口、线程、释放方式）。阶段 D 候选（xyzz 桶 fill 内核，默认关闭、独立配置）已文档化但**未实施**；如需继续，须另立预注册，不在本次结项范围内。

## 8. 证据索引（本报告数字的出处）

| 主题 | 文档 |
|---|---|
| 参数/成本逐步总账、瓶颈排序 | [`sapling_proving_parameter_and_bottleneck_breakdown_zh.md`](sapling_proving_parameter_and_bottleneck_breakdown_zh.md) §1–§17 |
| 优化验证协议（冻结） | [`experiments/metadata/sapling_optimization_validation_protocol_20261017.md`](../experiments/metadata/sapling_optimization_validation_protocol_20261017.md) |
| 七个目标 + 各测量线的结论/原始数据/判定 | [`experiments/metadata/INDEX.md`](../experiments/metadata/INDEX.md) |
| 目标 e / b / a / f / g 结果 | `experiments/metadata/sapling_{default_config_experiment,msm_signed_digit,msm_lazy_recoding,qap_fft_scratch,combo_default}_*_2026101[78].md` |
| 结项侦察（内存/时间地板） | `experiments/metadata/sapling_default_{stage_decomposition,time_profile}_20261018.md` |
| 复现规程与跨配置/跨 OS 验证 | [`docs/reproduction.md`](reproduction.md)、`experiments/metadata/sapling_{independent,cross_config}_reproduction_20261018.md` |
| MSM 多核扩展膝点（Stage 0） | [`sapling_msm_scaling_diagnosis_results_20261022.md`](../experiments/metadata/sapling_msm_scaling_diagnosis_results_20261022.md)；报告 §26；INDEX |
| MSM 内核预研阶段 A/B/C 与 2026-10-23 结项 | [`msm_kernel_research_plan_20261023.md`](msm_kernel_research_plan_20261023.md)、[`msm_literature_survey_20261023.md`](msm_literature_survey_20261023.md)、`experiments/metadata/sapling_msm_kernel_stagec_{preregistration,results}_20261023.md`、[`msm_kernel_project_closeout_20261023.md`](msm_kernel_project_closeout_20261023.md) |
| 原始测量数据（从不覆盖） | `experiments/raw/csv/`、`experiments/raw/logs/` |
| 周度过程记录 | [`weekly_summary.md`](../weekly_summary.md) §13–§19 |

*本报告为合成文档；凡与上述一手文档冲突，以一手文档为准。*
