# 预注册：阶段 C — A/A 测量稳定性校准与 MSM 内核基准（2026-10-23）

> 本文件在编写 `msm_kernel_bench` 二进制、运行任何阶段 C 计时**之前**填写并冻结。
> 它只决定两件事：**测量系统本身的不确定性有多大**，以及**当前 bellman 生产路径与成熟实现
> （blst）在同输入 MSM 上是否存在值得挖掘的性能空间**。它不是正式优化验收，不改变任何生产
> 默认值，不测完整 Groth16 证明。
>
> 上游依据：阶段 A 冻结文档 `docs/msm_kernel_research_plan_20261023.md`（候选：bucket fill
> 点累加内核）；阶段 B 文献对照 `docs/msm_literature_survey_20261023.md`（blst 的 Booth 重编码、
> xyzz 桶坐标、混合加、软件预取、批量仿射转换是与 bellman 现实现明确可区分的实现级差异，
> 且不依赖 AVX-512；其窗口规则在 n = 131,071 给出 c = 13，与本仓库实测最优一致）。
>
> 冻结后阈值与判定规则不得修改；若实测中发现标准写错，只能在结果文档里记录偏差，不能回改本文档。

---

## 0. 一句话

用同一进程内的交错区组测量**同一个基线实现**（A/A）来标定测量噪声；用同一组基点与标量、
分开计时的同输入基准，量化 bellman 生产路径与 blst（`no-threads` 锁定单线程）在真实 Sapling
查询规模上的 MSM 差距；再按事前冻结的 Go/No-Go 判据决定是否启动阶段 D 内核候选。

---

## 1. 边界与不做什么

| 项目 | 约定 |
|---|---|
| 性质 | **侦察（scoping）**，不是正式优化战役；没有端到端 PASS/FAIL 声明 |
| 代码范围 | 仅新增 `experiments/prover-smoke/src/bin/msm_kernel_bench.rs`；仅在该 harness 的 `Cargo.toml` 增加 `blst` 依赖（`no-threads` feature）；**不修改** `vendor/` 和任何生产默认值、不改三个已采纳开关 |
| 测量范围 | 独立 MSM kernel；五个查询负载；1 线程与 8 线程 bellman、单线程 blst |
| 不测 | 完整 Groth16 证明、参数文件读取、内存峰值全局 RSS、交易构造、跨机器、GPU/FPGA |
| 结果用途 | 只决定是否写阶段 D 候选预注册；若 NO_GO，关闭内核线并更换研究问题，不用同一次测量重挑子集 |
| 失败处理 | 任何门禁失败都按 §4 归档为 NO_GO / MARGINAL；不删除失败候选、不覆盖已写出的 raw CSV |

---

## 2. 基准设计：`msm-kernel-bench`

### 2.1 负载（同一份确定性 fixture，五点集同时供给两个实现）

| 负载 | 曲线 | n（标量槽） | 指数密度 | 优先级 |
|---|---|---:|---|---|
| H-query | G1 | 131,071 | 稠密（全随机） | **主** |
| L-query | G1 | 98,638 | 按记录比例注入 Zero/One | 高 |
| A/B aux | G1 | 98,638 ×2（L + 一次 A/B 辅助） | 按记录比例注入 Zero/One | 高 |
| B-G2 aux | G2 | 98,638 | 按记录比例注入 Zero/One | 高 |
| IC 小查询 | G1 | 8 | 稠密 | 参考 |

- fixture 生成：xorshift64* 确定性标量（固定种子，写在二进制里，与 `msm_window_bench` 同策略）；
  基点为生成元的连续倍数（内存布局真实，数值不影响成本结论——fill 顺序读取仿射向量）。
- Zero/One 注入比例取自 `sapling_default_time_profile_20261018.md` §2 的实测 census：
  G1 aux ≈ 77.7% Zero/One、G2 aux ≈ 85.2%；按相同比例把确定性标量替换为 0 或 1。
- 每个负载单独构造、单独计时；负载顺序固定为 H-query 先行。

### 2.2 计时分解（三段分开报告，避免把初始化藏进 MSM）

1. **fixture 构造**：bellman 侧 bases + scalars + `Exponent` 构造；blst 侧 `blst_p1/p2_deserialize`
   反序列化 + `blst_p*_from_affine` + scalar bytes 布局。单独计时，不计入 MSM。
2. **MSM 核心调用**：bellman `multiexp(worker, (bases,0), FullDensity, exponents).wait()`；
   blst `P1Affines::from(&points).mult(scalar_bytes, 255)`（nbits = 255，BLS12-381 标量宽度）。
3. **校验和**：每次计时输出 8 字节 FNV 校验和并打印，防止优化器删除计算、并检测结果漂移。

### 2.3 测量臂

| 臂 | 实现 | 线程 | 说明 |
|---|---|---|---|
| `bellman_8t_A` / `bellman_8t_B` | bellman 生产路径（三个默认开关保持默认，窗口用内置规则） | RAYON 8 | A/A 两臂：同一实现的两个标签 |
| `bellman_1t_A` / `bellman_1t_B` | 同上 | RAYON 1 | A/A 两臂；同时是与 blst 的**同线程数对照臂** |
| `blst_1t` | blst crate `no-threads`（`max_count()==1`，锁死单线程） | 1 | 成熟实现对照 |

- bellman 生产路径 = `SAPLING_MSM_SIGNED_DIGITS=1` + `SAPLING_MSM_LAZY_RECODING=1` 的默认行为
  （`SAPLING_FFT_SERIAL_SINGLE_THREAD` 只影响 FFT，与 MSM 无关）；bench 不调用任何
  `set_msm_*` 覆盖，窗口走内置规则。
- blst 用 `P1Affines::from(&[blst_p1])` 构造（其内部 `to_affines` 批量转换在 fixture 阶段完成）；
  G2 用 `P2Affines` 同构路径。

### 2.4 正确性门禁（任一失败整轮作废）

| # | 门禁 | 判据 |
|---|---|---|
| C1 | bellman 结果 vs blst 结果 | 群意义一致：bellman 投影点序列化（未压缩）后与 blst 结果（`to_affine` + serialize）逐字节相等；全部负载、全部被测臂 |
| C2 | bellman 1t vs 8t | 同一负载结果相等 |
| C3 | n = 8 负载 vs 朴素 double-and-add | 相等 |
| C4 | 测量稳定性 | 同一臂在同一区组内 3 次正式测量的校验和一致 |

---

## 3. A/A 测量设计（标定测量系统不确定性）

### 3.1 为什么先做 A/A

既有窗口侦察（`msm_window_bench` Stage 1c pilot，2026-10-23）记录到绝对 run-to-run 漂移
**10–16%**，超过候选间差别。在写任何新内核前，必须先知道“同一实现、同一输入、同一进程”
在正式流程下能复现到什么程度，否则算法 A/B 的结论不可信。

### 3.2 运行条件

| 条件 | 主条件 | 辅助条件 |
|---|---|---|
| 亲和性 | `0x5555`（8 个 P 核 LP0,2,4,6,8,10,12,14，禁 SMT 兄弟） | `0x1`（单 P 核） |
| `RAYON_NUM_THREADS` | 8 | 1 |
| 进程 | 同一二进制、同进程内完成全部区组 | 同 |
| 读回 | 运行脚本读回 `ProcessorAffinity` 并记录；不一致整轮作废 | 同 |

- 亲和性由 PowerShell 运行脚本设置（Windows `ProcessStartInfo.ProcessorAffinity`），
  与既有 pinned campaign 脚本同一机制；bench 二进制不设亲和性。
- 两个条件在同一次会话中先后执行（先 8t 后 1t），每条件独立区组序列与独立 raw CSV。

### 3.3 区组与顺序

- 每个条件 **B = 8 个区组**（默认，可由 `MSM_KB_BLOCKS` 覆盖，覆盖值记录在 raw）。
- 每区组内 5 个臂各测一次：`bellman_8t_A, bellman_8t_B, bellman_1t_A, bellman_1t_B, blst_1t`；
  臂的出场顺序由**冻结在二进制内的固定种子**伪随机生成，且每区组强制 ABBA 式平衡
  （任意前缀中两同类 bellman 臂出现次数差 ≤1），避免单侧漂移。
- 每臂每次：**1 次预热（不计时）+ 3 次正式测量**，区组内取中位 → 每区组每臂 1 个值。
- H-query 先行；其余负载按 §2.1 表序。

### 3.4 异常处理（事前冻结）

- 进程崩溃、亲和性读回不一致、C1–C4 失败、校验和在同臂同区组内不一致 → 整轮作废并重跑，
  记录原因；**不得**事后剔除单个区组来“改善”结果。
- raw CSV 只追加不覆盖；重跑使用新文件名后缀。

### 3.5 分析（脚本随本预注册一并冻结提交）

- 配对差：`d_i = bellman_8t_A_i − bellman_8t_B_i`（8t A/A）与 `bellman_1t_A_i − bellman_1t_B_i`（1t A/A），
  i = 区组。
- 报告：median(d)、IQR、配对 bootstrap 95% CI（10,000 次重抽样，固定种子 20261023）。
- 区组中位：每区组每臂取 3 次正式测量的中位。

---

## 4. 冻结门禁

### 4.1 测量质量门禁（M 级，先行；不过则改善测量设计，不进入性能结论）

| # | 门禁 | 阈值 | 判据 |
|---|---|---|---|
| M1 | 8t A/A 配对差 | 95% CI 半宽 ≤ **1.5%**（相对区组中位绝对值） | 必须；不过则增加区组/延长预热/检查系统负载后重测，不写性能结论 |
| M2 | 1t A/A 配对差 | 95% CI 半宽 ≤ **1.5%** | 必须；不过则同上 |

> 1.5% 的来历：阶段 D 的端到端目标是完整 Spend 中位 ≥5%。测量不确定度应明显小于目标收益
> （取 1/3），否则无法把 3–5% 量级的候选差异与噪声分开。

### 4.2 正确性门禁（C 级）

C1–C4 全部通过（§2.4）。任一失败 → 整轮作废或 NO_GO，不用“容差”替代群相等。

### 4.3 性能差距门禁（P 级；同线程数对照，1t 为主）

主指标：**H-query G1 全 MSM 墙上时间比** `R = median(bellman_1t) / median(blst_1t)`
（区组中位之比；bootstrap CI 报告方向）。

| # | 口径 | GO | MARGINAL | NO_GO |
|---|---|---:|---|---|
| P1 | H-query G1（n = 131,071） | R ≥ **1.15** | 1.08 ≤ R < 1.15 | R < 1.08 |
| P2 | G2 aux（n = 98,638） | 只记录，不设门禁 | — | — |
| P3 | 其余 G1 负载 | 只记录，不设门禁 | — | — |

- **GO**：M、C 全过且 P1 ≥ 1.15 → bellman 点运算路径存在明确可挖掘空间，进入阶段 D 候选预注册。
- **MARGINAL**：M、C 全过，1.08 ≤ P1 < 1.15 → 记录差距归因（§4.4）后再判；不得把
  “有信号”写成“应立项”。
- **NO_GO**：M 不过（先修测量），或 C 失败，或 P1 < 1.08 → 关闭内核候选线；
  结论归档到 INDEX.md，更换研究问题。

### 4.4 差距归因（P1 达 MARGINAL 以上时记录，不设门禁）

- 单位操作级单价：bellman 侧每非零数字 ns（历史基线 462 ns，`sapling_default_time_profile_20261018.md` §2）
  与 blst 侧等效单价（全 MSM 时间 ÷ 同一操作数模型 `ops(c) = ceil(255/c)·(n·d + 2·2^(c−1))`，
  blst 窗口 c 取其 `pippenger_window_size` 规则值）。
- 与文献对照表（阶段 B）的实现差异清单逐项对照：Booth 重编码、xyzz 桶坐标、混合加、
  软件预取、批量仿射转换、窗口规则。回答：差距可归于**群运算公式、数据布局、输入访问方式**
  中的哪些。
- 8t bellman 单独记录为生产参考（其线程框架与 blst 的 `da_pool` 不同，不与 blst 直接相比）。

---

## 5. 阈值依据（传导计算，随预注册冻结）

数据源：`sapling_default_time_profile_20261018.md`（1 线程，同批次中位）。

- 1t Spend body 3,625.2 ms：bucket fill 2,448.1 ms（**67.5%**）、reduce 681.7 ms、
  FFT prep 385.8 ms（10.6%）、synthesis 120.5 ms（3.3%）。
- H-query：全 MSM 1,514.3 ms（body 的 **41.8%**），其中 fill 1,415.2 ms（**93.5%**，
  body 的 39.0%）。
- 传导模型：body 相对变化 ≈ fill_share × (1 − 1/S)。
  - fill 整体加速 S：需 S ≥ **1.082** 才有 body −5%（1t）。
  - 仅 H-query fill 加速：需 S ≥ **1.128** 才有 body −5%。
- H-query 全 MSM 中 fill 占 93.5%，故 `R = 1.15` ≈ fill 级 1.16 ≈ body **−6.2%**（1t）；
  `R = 1.08` ≈ body **−4.6%**。8t 参考（c = 11 实测 657.81 ms）比例相近（fill ≈ 66% of body）。
- 这些换算只用于设定 P 级门禁的“值得挖掘”标准；**任何端到端结论必须由阶段 E 的完整证明
  A/B 验证**，内核加速比不得外推为证明系统收益。

---

## 6. 数据、脚本与元数据

- bench 二进制：`experiments/prover-smoke/src/bin/msm_kernel_bench.rs`
  （环境变量：`MSM_KB_BLOCKS` 默认 8、`MSM_KB_RUNS` 默认 3、`MSM_KB_SEED` 默认固定值
  `0x5A17_E5B3_A5E2_D10C`、`MSM_KB_CSV` 输出路径）。
- 运行脚本：`scripts/run_msm_kernel_bench.ps1`（设亲和性并读回、设 `RAYON_NUM_THREADS`、
  记录元数据、按条件调用二进制、raw 只追加）。
- 分析脚本：`scripts/analyze_msm_kernel_bench.py`（读 raw CSV，按 §3.5 计算，写派生表；
  TAG 硬编码，换批次必须改 TAG 与新输出文件名，不覆盖旧批次）。
- 原始 CSV：`experiments/raw/csv/msm_kernel_bench_20261023_{8t,1t}.csv`
  （列：`load,curve,n,arm,block,run,phase,elapsed_ms,checksum`）。
- 正确性 CSV：`experiments/raw/csv/msm_kernel_bench_20261023_correctness.csv`
  （列：`load,curve,n,check,ok`）。
- 日志：`experiments/raw/logs/msm_kernel_bench_20261023_*.log`。
- 派生表：`results/tables/msm_kernel_bench_20261023_summary.csv`。
- 元数据（运行脚本记录）：二进制 SHA-256、`git rev-parse HEAD`、dirty 状态、`rustc -V`、
  亲和性读回值、环境变量快照、完整命令行。

---

## 7. 与既有文档的关系

- 上游计划（阶段 A）：`docs/msm_kernel_research_plan_20261023.md`
- 文献对照（阶段 B）：`docs/msm_literature_survey_20261023.md`
- 历史时间剖面（传导计算数据源）：`experiments/metadata/sapling_default_time_profile_20261018.md`
- 窗口侦察 bench（本 bench 复用其 fixture 策略与 bellman API 调用）：
  `experiments/prover-smoke/src/bin/msm_window_bench.rs`
- 测量协议：`experiments/metadata/sapling_optimization_validation_protocol_20261017.md`
- blst 实现细节（Booth / xyzz / 预取 / 批量求逆 / 窗口规则）：阶段 B 文档 §3
- 本预注册结果（待写）：`experiments/metadata/sapling_msm_kernel_stagec_results_20261023.md`

---

## 8. 冻结签名

- 预注册日期：2026-10-23
- 代码改动前 HEAD：`eae41b7`（分支 `experiment/msm-kernel-20261023`）
- 状态：**FROZEN**（先于 `msm_kernel_bench` 二进制实现与任何阶段 C 计时；
  分析脚本与运行脚本随本预注册同提交冻结）
