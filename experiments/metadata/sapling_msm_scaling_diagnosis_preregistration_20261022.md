# 预注册：Groth16 prover 多核扩展性拐点诊断（Stage 0）— 2026-10-22

> 本文件按 `sapling_optimization_validation_protocol_20261017.md` §5 的模板，**在写任何新脚本、改任何代码、跑任何新测量之前**填写并冻结。
> 一旦冻结，本文件的场景、样本量、估计口径、验收判据和判定规则**不得修改**；测量中若发现口径写错，只能在结果文档里标注，不能回改本文档。
>
> 与既有工作的关系：
> - 目标 a–g 解决的是“单份证明在固定电路与固定参数下如何更快/更省内存”；
> - 2026-10-22 的交易 baseline 把测量边界上移到了真实 `zcash_primitives::transaction::builder::Builder`；
> - 本 Stage 0 **不实现任何优化**，只回答一个诊断问题：**为什么 8 线程只有约 3.65×，拐点到底来自窗口尾部、SMT、串行阶段，还是内存/带宽？**
>
> 因此本文没有“达到阈值 ⇒ 采用某个开关”的结构，只有“诊断成立 ⇒ Stage 1 选哪个杠杆”的结构（§6）。

---

## 0. 一句话

在**不改变任何算法默认值**的前提下，用现有 instrumented release 二进制，在冻结的 P 核亲和性下测 1/2/4/8/16 线程的 Spend、Output 和“1 spend + 2 outputs”真实交易构造；并用 8 线程 `0xFFFF`（8 物理 P 核 × HT）对 `0x5555`（每物理 P 核一个 LP）的 ABBA 对照、以及 8 线程窗口宽度 `c ∈ {10,11,12,13}` 扫描，把 3.65× 的损失分解为**窗口尾部（H1）／SMT（H2）／串行或低扩展阶段（H3）／内存与竞争（H4，次要）**，为 Stage 1 选择一个可由数据支持的优化方向。

---

## 1. 目标、范围与非目标

### 1.1 要回答的问题

| # | 问题 | 主指标 | 对应假设 |
|---|---|---|---|
| Q1 | 当前默认配置下，Spend / Output / 真实交易的线程扩展曲线是什么？8t 相对 1t 的 speedup 与 parallel efficiency 各是多少？ | `S(P)=median(t(1))/median(t(P))`、`E(P)=S(P)/P` | 描述性 |
| Q2 | 8t 的损失有多少来自 **SMT**（8 个 worker 落在 4 个物理核的 8 个 sibling 上）？ | 8t `0x5555` vs `0xFFFF` 的 prove 中位差、H-query 每 chunk fill 时间 | H2 |
| Q3 | 8t 的损失有多少来自 **窗口尾部**（H-query 的 20 个 window 不能被 8 个 worker 整除）？ | 强制 `c` 使 `W=22/24` 时的 `ns / modelled group add`，相对 `W=20` | H1 |
| Q4 | 8t 的损失有多少来自 **非 MSM 的串行/低扩展阶段**（circuit synthesis、QAP/FFT、结果装配）？ | G16 阶段分解、两参数 Amdahl 拟合对 16t 的预测误差 | H3 |
| Q5 | Output 与真实交易的拐点是否和 Spend 相同？交易层的 3.65× 是否只是 Spend 的解释？ | Output prove、交易 `build_ms`、`sum_proofs_ms`、非证明部分 | 描述性 + 组合检验 |
| Q6 | 是否存在“每 add 变慢”的内存/竞争信号，足以否定纯调度解释？ | `bucket_fill` 的 `ns/add` 随 P 的变化、活跃 bucket payload 与 L2/L3 的关系 | H4（次要） |

### 1.2 范围

- **电路**：Sapling Spend、Sapling Output、以及固定形状的真实交易（1 spend + 2 outputs）。
- **线程**：1、2、4、8、16 个 Rayon worker。
- **亲和性**：仅 P 核。`0xFFFF` = 16 个 P 逻辑核（8 物理核 × HT）；`0x5555` = 每个 P 物理核取一个 LP（本机为 LP0/2/4/…/14）。1 线程固定 `0x1`（LP0），与冻结 baseline 一致。
- **窗口**：默认 `c=13`（`W=20`，`2^12=4096` buckets，signed recoding）为基线；另测 `c=10/11/12`，仅用于诊断，不改变默认。
- **测量边界**：prover 进程内的 prove 墙钟与 G16/MSM 阶段；交易进程内的 `build_ms` 与逐 proof 分解。参数加载在计时窗口外。

### 1.3 非目标

1. **不实现、不合并任何算法优化**。不改 `vendor/bellman`、`vendor/groth16` 的算法路径，不改默认开关。
2. **不产生“某配置应成为默认值”的结论**。本阶段只产生“损失来自哪里”的证据。
3. 不测 E 核、P+E 混合、不绑核、28 线程、或 16 线程以上的配置。
4. 不测网络广播、mempool、链上确认；所有时间都是本机构造/证明时间。
5. 不做跨机器泛化；单机结论只对本机 + 本工具链负责。
6. 不把 Stage 0 的窗口扫描结果直接当作优化收益；收益必须在 Stage 1 用独立预注册验证。

---

## 2. 背景与可检验假设

### 2.1 已有事实（仅作为设计依据，不作为本阶段结果）

- 交易 baseline：1t `0x1` 的 `build_ms` 暖态中位约 **4,292.7 ms**；8t `0xFFFF` 约 **1,176.0 ms**；比值约 **3.65×**，parallel efficiency 约 **45.6%**。
- 同一交易包含 1 个 Spend 证明和 2 个 Output 证明；1t 的逐 proof 合计约 4,292.5 ms，其中 Spend 约 3,333 ms、两个 Output 约 480 + 479 ms。**Spend 占证明时间约 77.7%**，因此 Spend 的扩展性是交易 3.65× 的主项，但不是唯一项。
- 历史 8t Spend 阶段数据（不同批次、不同默认值，不能与本阶段直接配对）显示：`circuit_synthesis_constraints_ms` 约 104 ms（与 1t 几乎相同），`qap_fft_h_exponent_prep_ms` 从约 388 ms 降到约 109 ms，`assignment_query_prep_dispatch_ms` 从约 2,459 ms 降到约 29 ms，`wait_and_assembly_ms` 约 465 ms，`create_proof_body_ms` 约 719 ms。
- 历史 8t H-query：`window=12`、`chunk_count=22`、`chunk_parallel_wall_ms≈463 ms`、`bucket_fill_sum≈1568 ms`、`bucket_fill_max≈99 ms`、`max_concurrent_chunk_regions=8`。按 `fill_sum/(wall×P)` 粗算，fill 的有效并行度只有约 **42%**，远低于 1t 的约 95%。这既可能是 SMT，也可能是窗口尾部或每 chunk 变慢。
- 默认 `c=13` 时 H-query 的 `W=20`：8 个 worker 做 20 个 chunk，理想情况下是 3 波（8+8+4），**尾部利用率 20/(8×3)=83.3%**；`c=12` 时 `W=22`，利用率 91.7%；`c=11` 时 `W=24`，利用率 100%。模型化的 group-add 数随 `c` 变化（`W×(n+2^(c-1)×2)`），因此不能只看墙钟，必须看 **每模型化 group add 的时间**。

### 2.2 假设

四个假设**不互斥**；Stage 0 的目标是估计它们的相对份额，而不是选一个“赢家”。

#### H1 — 窗口尾部/粒度假设

**机制**：`multiexp` 把 `window_count` 个 chunk 交给 Rayon `into_par_iter`。当 `W` 不能被 `P` 整除时，最后一波只有 `W mod P` 个 worker 有活；此外，每个 chunk 的 bucket 数组是独立的，chunk 太大时单 chunk 的串行 fill 也会限制尾部。

**预测**：
- 8t `0x5555` 下，`c=12`（W=22）或 `c=11`（W=24）的 **每模型化 add 时间**低于 `c=13`（W=20），尽管总 add 数更多；
- `max_concurrent_chunk_regions` 在 8t 能达到 8，但最后一段明显低于 8；
- 当 `W` 被 8 整除时，`fill_sum/(wall×8)` 更接近 1。

**否证**：`c=12/11` 的每 add 时间不低于 `c=13`（或差异 <2%），且 `max_concurrent` 已长期为 8；则尾部不是主要因素。

#### H2 — SMT/放置假设

**机制**：`0xFFFF` 允许 8 个 worker 落在 8 个物理核的 16 个 sibling 上。若 Windows 调度器把两个 worker 放到同一物理核的两个 HT 上，两个 chunk 的 mixed add 会争用同一核的执行端口/缓存，单 chunk 时间上升；`0x5555` 强制每个物理核一个 LP，消除这种竞争。

**预测**：
- 8t `0x5555` 的 prove 中位显著低于 `0xFFFF`；
- H-query 的 `bucket_fill_sum/W`（每 chunk 平均 fill 时间）在 `0x5555` 下显著下降；
- 1t 基线（`0x1`）只用于计算 `S(P)`，不参与 H2；2t/4t 的 `0x5555` 也应优于 `0xFFFF`，但幅度随 P 减小。

**否证**：8t 两种 mask 的 prove 差异 <2%，或 `0x5555` 反而更慢；则 SMT 不是 3.65× 的主因。

#### H3 — 串行/低扩展阶段假设

**机制**：Groth16 的 `circuit_synthesis_constraints` 在 worker 侧基本串行；QAP/FFT 与结果装配有固定开销；这些阶段不随 P 线性下降，Amdahl 上限会压低整体 speedup。

**预测**：
- 用 1/2/4/8t 的 prove 拟合 `t(P)=a+b/P`，外推 16t 的误差在 ±10% 内；
- 8t 的 `circuit_synthesis + qap_fft + proof_scalar_terms` 占 `create_proof_body` 的比例 ≥15%，且它们的 speedup 明显低于 H-query MSM；
- 若把 H-query 的 MSM 墙钟按 8× 理想化扣除，剩余部分仍占 8t body 的 ≥20%。

**否证**：两参数模型对 16t 的预测误差 >10%，或非 MSM 阶段占比 <10%；则不能用简单串行分数解释，需考虑竞争/过订阅。

#### H4 — 内存/带宽/竞争假设（次要）

**机制**：8 个并发 chunk 各自持有 `2^(c-1)` 个 bucket；`c=13` 时每 chunk 约 589,824 B，8 个约 4.7 MB（L2 每核通常 2 MB，L3 共享）。若每 add 时间随 P 上升、且在小 bucket（`c=11`，每 chunk 147,456 B）仍不回落，则更像执行端口/缓存竞争而非容量。

**预测**：
- `bucket_fill` 的 `ns/add` 在 8t 比 1t 高 ≥20%，且 `max_concurrent=8`；
- `c=11`（小 bucket）相对 `c=13` 的每 add 时间不因容量下降而显著改善，反而可能因窗口更多而变差。

**定位**：H4 不作为独立 pass/fail，只作为 H1/H2 的替代解释检查；若 H1/H2 均不成立而 H4 信号强，Stage 1 才考虑 cache blocking/调度。

---

## 3. 实验设计

### 3.1 工作负载与固定值

| 工作负载 | 二进制 | 每次进程的证明数 | 计时口径 | 固定值 |
|---|---|---|---|---|
| Spend | `experiments/prover-smoke/target/release/spend_prover_smoke.exe` | 5 | `prove_ms`；G16 阶段；8 个 MSM 的 inner stage | Sapling Spend，`target_height=1_700_000`（v5/Nu5），参数 `sapling-spend.params` |
| Output | `experiments/prover-smoke/target/release/sapling-output-smoke.exe` | 5 | `prove_ms` | Sapling Output，同一 height/参数 `sapling-output.params` |
| 真实交易 | `experiments/transaction-smoke/target/release/tx_construct_bench.exe` | 6 笔交易 | `build_ms`、`sum_proofs_ms`、`serialize_ms`、`verify_ms` | 1 spend + 2 outputs；spend 100,000,000 zats；收款 60,000,000；找零 39,990,000；fee 10,000；value balance +10,000；`MAIN_NETWORK`；`tx_bytes=2377` |

> 交易的“1 spend + 2 outputs”是**固定形状的真实构造**，不是任意混合负载。Stage 0 只用它回答“交易层的 3.65× 是否与 Spend 的拐点一致”，不外推到其他形状。

### 3.2 因子与水平

| 因子 | 水平 | 说明 |
|---|---|---|
| 线程 `P` | 1, 2, 4, 8, 16 | `RAYON_NUM_THREADS=P` |
| 亲和性 `M` | `0x1`（仅 1t）、`0xFFFF`、`0x5555` | `0xFFFF`=16 个 P LP；`0x5555`=8 个 P 物理核各一个 LP；`0x1`=LP0 |
| 窗口 `c` | 默认（13）、10、11、12 | 仅 8t `0x5555` 的诊断扫描；`SAPLING_MSM_WINDOW_C` 覆盖 |
| 负载 | Spend、Output、真实交易 | 见 §3.1 |

**为什么 16t 只配 `0xFFFF`**：`0x5555` 只有 8 个 LP，16 个 worker 会过订阅（每 LP 2 个），不是“每物理核一个”的对照；16t 的用途是观察 `0xFFFF` 下 HT 全开 + 过订阅的极端，不是 H2 的主对照。

**为什么 1t 用 `0x1` 而不是 `0xFFFF`**：遵守冻结 baseline 的 1t 惯例（LP0）；`0x1` 与 `0xFFFF` 的单线程差异属于放置噪声，不进入 H1/H2 的主比较。

### 3.3 实验臂与样本量

每个“batch”是一个独立进程；Spend/Output 每 batch 5 次证明，交易每 batch 6 次构造。**每个 batch 的第 1 次一律丢弃**（进程内暖机）；其余为 warm 样本。

| 臂 | 负载 | 配置 | batch 数 | warm 样本/配置 | 用途 |
|---|---|---|---|---|---|
| **S-Scale** | Spend | 1t `0x1`；2t/4t/16t `0xFFFF`；2t/4t `0x5555` | 2 / 配置 = 12 | 8 | 扩展曲线（不含 8t） |
| **S-ABBA** | Spend | 8t `0xFFFF` vs `0x5555` | 8（每 mask 4） | 16 / mask | H2 主检验 |
| **S-Window** | Spend | 8t `0x5555`，`c=10/11/12/13` | 2 / c = 8 | 8 / c | H1 主检验 |
| **O-Scale** | Output | 1t `0x1`；16t `0xFFFF` | 2 / 配置 = 4 | 8 | Output 端点 |
| **O-ABBA** | Output | 8t `0xFFFF` vs `0x5555` | 4（每 mask 2） | 8 / mask | Output 的 SMT 次要检验 |
| **T-Scale** | 交易 | 1t `0x1`；16t `0xFFFF` | 2 / 配置 = 4 | 10 | 交易端点 |
| **T-ABBA** | 交易 | 8t `0xFFFF` vs `0x5555` | 4（每 mask 2） | 10 / mask | 交易层 SMT 次要检验 |
| **合计** | | | **44** | | |

> S-ABBA 的 ABBA 顺序为 `FFFF, 5555, 5555, FFFF, FFFF, 5555, 5555, FFFF`（每 mask 4 个 batch），用于抵消随时间漂移的频率/温度。
> O-ABBA / T-ABBA 的顺序为 `FFFF, 5555, 5555, FFFF`（每 mask 2 个 batch）。

### 3.4 运行顺序与漂移控制

1. **S-Scale**：batch 1 按 `1t-0x1 → 2t-FFFF → 4t-FFFF → 16t-FFFF → 2t-5555 → 4t-5555` 升序；batch 2 按相反顺序。每个配置两个 batch 在时间上分开，避免同一时刻的缓存/频率状态绑定到某个线程数。
2. **S-ABBA**：严格按 §3.3 的 8 个 batch 顺序执行，每个 batch 之间空闲 5 s。
3. **S-Window**：`c` 的执行顺序为 `13, 11, 12, 10, 10, 12, 11, 13`（回文），每个 `c` 两个 batch。
4. **O/T**：先跑 1t 与 16t 各两个 batch（顺序 `1t,16t,16t,1t`），再跑 8t ABBA。
5. 所有臂**串行执行**，不并发；每个 batch 之间空闲 5 s；不运行其他重负载。
6. 每个 batch 记录开始/结束时间、进程退出码、亲和性读回值、实际 `RAYON_NUM_THREADS`、二进制 SHA-256、参数 SHA-256、git HEAD。

### 3.5 环境与默认开关

- 主机：Intel i7-14700（8 P 核 × HT + 12 E 核；28 LP）；Windows 11；PowerShell 5.1；`rustc 1.98.1`；host `x86_64-pc-windows-gnu`。
- 拓扑核验：`GetLogicalProcessorInformation` 给出的 P 核掩码为 `0x3, 0xC, 0x30, …, 0xC000`；因此 `0x5555`（LP0,2,…,14）= 每个 P 物理核一个 LP。
- 参数目录：`D:\Research\zcash-params`；spend `sapling-spend.params` SHA-256 期望 `8e48ffd2…`；output `sapling-output.params` SHA-256 期望 `2f0ebbcb…`。参数加载约 27–29 s，在计时窗口外。
- **默认开关**（Stage 0 不改）：
  - `SAPLING_MSM_SIGNED_DIGITS=1`（默认）
  - `SAPLING_MSM_LAZY_RECODING=1`（默认）
  - `SAPLING_FFT_SERIAL_SINGLE_THREAD=1`（默认；1t 走串行 FFT，2t+ 走并行 FFT，这是默认行为的一部分，不在本阶段归因）
  - `SAPLING_MSM_WINDOW_C` **不设置**（S-Window 臂除外）
  - `SAPLING_MSM_BRANCH_COUNTS=0`（所有臂统一关闭 branch census，减少诊断开销）
- **Profiling 开关**：
  - Spend：`SAPLING_PROFILE=1`、`SAPLING_MSM_STAGE_TIMING=1`；需要 G16 阶段与 8 个 MSM 的 inner stage。
  - Output / 交易：`SAPLING_PROFILE=0`；只测外层 prove/build，避免诊断计时器扰动。
  - 注意：Spend 的绝对 prove 时间会因 `SAPLING_PROFILE=1` 略高于无 profiling 的 baseline；Stage 0 的**比较只在同一 profiling 条件下进行**，不把绝对值和交易 baseline 直接相减。

---

## 4. 冻结口径与指标定义

### 4.1 基本统计

- 每个配置先算**每个 batch 的 warm 中位**（丢弃 run 1），再对 batch 中位取中位，得到 `median_config`。
- 同时报告：warm 样本的 min/max、IQR、CV（`sd/mean`）、batch 间极差。
- 主比较用 **cluster bootstrap**：以 batch 为重采样单位，batch 内保留 warm 样本；10,000 次重采样，报告 90% CI。这样不会把同一进程内的 4–5 次证明误当成完全独立样本。
- 不删除离群点；高 CV 只标记，不剔除。

### 4.2 扩展性

对每个配置 `P`：

```text
S(P) = median_config(t_prove, P=1) / median_config(t_prove, P)
E(P) = S(P) / P
```

同时对以下量重复同样定义：
- `create_proof_body_ms`
- `circuit_synthesis_constraints_ms`
- `qap_fft_h_exponent_prep_ms`
- `assignment_query_prep_dispatch_ms`
- `wait_and_assembly_ms`
- H-query 的 `chunk_parallel_wall_ms`、`bucket_fill_sum_ms`

### 4.3 H-query 的窗口/尾部指标

对每个 warm 证明的 H-query 记录：

```text
W                 = chunk_count
P                 = threads
max_conc          = max_concurrent_chunk_regions
U                 = max_conc / min(P, W)
T                 = tail_ideal = W / (P * ceil(W / P))
fill_per_chunk    = bucket_fill_sum_ms / W
fill_imbalance    = bucket_fill_max_ms / fill_per_chunk
fill_parallel_eff = bucket_fill_sum_ms / (chunk_parallel_wall_ms * P)
modelled_adds     = W * (n + 2 * 2^(c-1))          # n = exponent_count
ns_per_add        = chunk_parallel_wall_ms * 1e6 / modelled_adds
```

说明：
- `modelled_adds` 是 signed recoding 的操作数模型（每窗口 n 次 bucket add + 每窗口 2×bucket 数的 reduce add）；它用于**跨 c 归一化**，不是实测指令数。
- `fill_parallel_eff` 的分母是 `wall×P`；它把“每 chunk 在 SMT 下变慢”和“尾部空闲”混在一起，因此只作为描述量，H1/H2 的判定分别看 `ns_per_add` 和 `fill_per_chunk`。
- `max_conc` 是原子最大值，可能略高于实际同时活跃数；只用于判断“是否达到 P”，不用于精确占用率。

### 4.4 Amdahl 两参数拟合

对每个配置的 `median_config(t_prove, P)`，用 `P ∈ {1,2,4,8}` 做最小二乘：

```text
t(P) = a + b / P
serial_fraction = a / (a + b)
predicted_16 = a + b / 16
error_16 = (predicted_16 - observed_16) / observed_16
```

同时对每个 stage 做同样拟合（仅作诊断，不强制每个 stage 都成立）。

### 4.5 交易层

```text
non_proof_ms = build_ms - sum_proofs_ms
S_tx(P)      = median_config(build_ms, 1t) / median_config(build_ms, P)
```

`non_proof_ms` 包含见证准备、sighash、签名、装配等；它不是 mock 分解（mock 在 1t 已有独立 baseline），因此只作为描述量，不替换 mock 口径。

### 4.6 不使用的口径

- 不用逐 run 编号把真实交易与 mock 交易配对（mock 不消耗证明随机数，交易不完全相同；该口径已在交易 baseline 评审中否定）。
- 不把 `msm_elapsed_sum` 直接除以 `prove_ms` 当作 MSM 占比（多个 MSM 可能重叠，sum 可大于 wall）。
- 不把历史批次（不同默认值/不同二进制）与本阶段配对；历史数据只用于提出假设。
- 不用“交易完全相同”表述；只声明序列化长度与结构一致（`tx_bytes=2377`，1 spend/2 outputs，v5/Nu5）。

---

## 5. 验收表（冻结）

Stage 0 的“PASS”只表示**测量与分解可用**，不表示任何优化收益。全部 12 项必须通过；任一项失败，相关配置不得进入结论。

| # | 检查 | 通过条件 | 失败处理 |
|---|---|---|---|
| A1 | Spend 每 batch 行数/验证 | 每 batch 恰好 5 行，5/5 `verified=true` | 该 batch 作废；用**新 batch ID** 重跑，不覆盖 |
| A2 | Spend profile 记录数 | 每 batch 40 条 `BELLMAN_MSM_PROFILE`、40 条 `BELLMAN_MSM_SUBMIT_PROFILE`、5 条 `G16_STAGE_PROFILE`、40 条 `BELLMAN_MSM_STAGE_PROFILE` | 该 batch 作废；检查日志，不用部分数据 |
| A3 | 阶段闭合 | 每 run `abs(stage_sum - create_proof_body) ≤ 0.01 ms` | 该 batch 作废 |
| A4 | 窗口扫描一致性 | 每 batch 的 H-query `window` 字段等于请求的 `c`；40 条 inner-stage 记录；5/5 验证 | 该 `c` 整臂作废；不静默丢弃某个 `c` |
| A5 | Output | 每 batch 恰好 5 行，5/5 `verified=true` | 该 batch 作废 |
| A6 | 交易 | 每 batch 恰好 6 行；6/6 `verified=true`；`tx_bytes=2377`；`tx_version=V5`；`spend_count=1`、`output_count=2` | 该 batch 作废 |
| A7 | 亲和性读回 | 每个 batch 启动后读回的 `ProcessorAffinity` 精确等于请求 mask | 立即终止；该 batch 作废 |
| A8 | 线程数 | 每行记录的 `rayon_threads` 等于请求 P（Spend/Output/交易） | 该 batch 作废 |
| A9 | 溯源 | 每 batch 记录二进制 SHA-256、参数 SHA-256、git HEAD、CPU 型号、请求 mask；Spend profile 的二进制与交易二进制均来自同一 commit | 缺一项即不可发布 |
| A10 | 样本量 | 每个配置的 batch 数与 §3.3 一致；warm 样本数一致；无缺失配置 | 缺配置则整臂不完整，不得选择性报告 |
| A11 | 不覆盖 | 新 CSV/日志/manifest 路径不存在；若存在则中止，不追加 | 换新 tag；旧数据保留 |
| A12 | 分析独立性 | 分析脚本从原始 CSV 重新计数/复核 A1–A6，不依赖启动器的断言 | 分析脚本失败则结果不可用 |

### 5.1 噪声标记（不构成失败）

- 若某配置的 warm CV >20%，标记 `noisy`；允许在**同一配置**追加 1 个新 batch（新 batch ID），把 warm 样本从 8 提到 12（ABBA 从 16 提到 20）。
- 追加后 CV 仍 >20%，结果标注为“高噪声，结论仅描述性”，不得据此声称 H2/H1 成立。
- 不因为“结果不符合预期”而追加；追加只看 CV，不看效应方向。

---

## 6. 判定规则

所有效应量都带 90% cluster bootstrap CI。`Δ` 定义为“对照 − 处理”的相对差（正数表示处理更快）。

### 6.1 H2（SMT，主检验）

在 8t、同一二进制、ABBA 数据上：

```text
Δ_prove = (median_FFFF(t_prove) - median_5555(t_prove)) / median_FFFF(t_prove)
Δ_fill  = (median_FFFF(fill_per_chunk) - median_5555(fill_per_chunk)) / median_FFFF(fill_per_chunk)
```

- **支持**：`Δ_prove ≥ 5%`，其 90% CI 下界 >0，且 `Δ_fill ≥ 8%`。
- **部分支持**：`2% ≤ Δ_prove < 5%`，或 prove 的 CI 跨 0 但 `Δ_fill ≥ 8%` 且方向一致。
- **不支持**：`Δ_prove < 2%`，或 `Δ_prove ≤ 0`（`0xFFFF` 更快/相同）。
- 1t 基线（`0x1`）只用于计算 `S(P)`，不参与 H2 判定。

### 6.2 H1（窗口尾部，主检验）

在 8t `0x5555`、`c ∈ {10,11,12,13}` 上，主比较是 `c=12`（W=22，尾部利用率 T=91.7%）对 `c=13`（W=20，T=83.3%）：

```text
R = ns_per_add(c=12) / ns_per_add(c=13)
```

- **支持**：`R ≤ 0.98`，且 90% CI 上界 <1.00；同时 `max_conc` 在 c=12 达到 8。
- **不支持**：`R ≥ 0.99`，或 c=12 的 CI 完全在 1.00 以上。
- **不确定**：`0.98 < R < 0.99`，或 CI 跨 1.00。
- 次要比较：`c=11`（W=24，T=100%）对 `c=13`；若 c=12 不支持而 c=11 支持（`R≤0.98`），标注“尾部存在但最佳窗口在 c=11”，不直接改默认。
- 若 `c=12` 或 `c=13` 在 A4 失败，H1 判定为“数据不足”；若仅 `c=10/11` 失败，该 c 不进入次要比较，主比较仍可判定，但必须在结果文档标注缺失。

### 6.3 H3（串行/低扩展）

- **支持**：8t 的 `circuit_synthesis + qap_fft + proof_scalar_terms` 占 `create_proof_body` ≥15%，且 §4.4 的 Amdahl 拟合对 16t 的 `|error_16| ≤ 10%`。
- **部分支持**：上述占比 ≥15%，但 `|error_16| > 10%`；说明串行项存在，但两参数模型不足，需在 Stage 1 加入竞争/过订阅项。
- **不支持**：占比 <10%，或 16t 实际远好于/差于模型且无法用阶段解释。

### 6.4 H4（内存/竞争，次要）

只报告，不做 pass/fail：

- 若 8t `ns_per_add(8t)/ns_per_add(1t) ≥ 1.2`，且 `max_conc=8`，标记“每 add 变慢”；
- 若同时 `c=11`（每 chunk 147 KB）相对 `c=13`（589 KB）没有改善，则更可能是执行端口/同步竞争，而非 bucket 容量；
- 若 `ns_per_add` 基本不变（比值 ≤1.1），则 H2/H1 的调度解释优先。

### 6.5 组合判定与 Stage 1 选择（预注册映射）

| H2 | H1 | H3 | Stage 1 第一优先 | 理由 |
|---|---|---|---|---|
| 支持 | 任意 | 任意 | **线程放置/调度策略**（先做 placement-aware 的 chunk 调度或文档化绑核建议） | SMT 是最大单项，且不需要改密码学算法 |
| 不支持/部分 | 支持 | 任意 | **自适应窗口/窗口内切分**（`W mod P` 感知；在 Spend/Output/交易验证） | 尾部是可测量的算法级杠杆 |
| 不支持 | 不支持 | 支持 | **串行阶段重叠/流水线**（synthesis/QAP/assembly），而不是继续调 MSM 窗口 | MSM 已接近线性，瓶颈不在 MSM |
| 不支持 | 不支持 | 不支持 | **不写优化器**；先加 OS/硬件计数器（context switch、frequency、per-thread CPU）复测 | 现有模型不足，避免盲目优化 |

> 若 H2 与 H1 同时支持，先按第一行执行（先消除放置差异），再在相同放置下做 H1 的窗口策略，避免把 SMT 收益误归因给窗口。

> 该表只决定 Stage 1 的**第一优先**，不预先承诺实现细节；Stage 1 仍需独立预注册与验收。

---

## 7. 实现与运行计划（预注册后执行）

### 7.1 代码/脚本改动（最小化）

1. **`scripts/run_spend_combined_profile.ps1`**：在设置 `ProcessorAffinity` 后读回 `$process.ProcessorAffinity`，若不等于请求 mask 立即失败；metadata 增加 `affinity_readback`。不改变计时、证明数、CSV 语义。
2. **`scripts/run_pinned_prover_campaign.ps1`**：同样增加亲和性读回与失败检查；不改变 prove 口径。
3. **新增 `scripts/run_msm_scaling_campaign.ps1`**：Stage 0 编排器。
   - 校验工作树干净、二进制/参数存在、tag 不冲突；
   - 按 §3.3/§3.4 的顺序调用现有 Spend/Output runner；
   - S-Window 臂设置 `SAPLING_MSM_WINDOW_C`；
   - 交易臂调用新增的 `scripts/run_tx_scaling_campaign.ps1`（每次一个进程，6 次构造，设置/读回 affinity，追加到新 CSV）；
   - 写 `experiments/metadata/msm_scaling_manifest_20261022.csv`，每行一个 batch：arm、config、order、batch_id、start/end、exit、mask、threads、c、log paths、hashes。
4. **新增 `scripts/analyze_msm_scaling_diagnosis.py`**：冻结 `TAG=msm_scaling_20261022`；独立复核 A1–A6；计算 §4 指标；输出 CSV/图；写 `experiments/metadata/sapling_msm_scaling_diagnosis_results_20261022.md` 的结果表。
5. **不修改** `vendor/bellman`、`vendor/groth16`、`experiments/*/src/*.rs` 的算法/计时逻辑；只允许在脚本层加读回检查和新编排器。

### 7.2 构建与指纹

- 在 `experiments/prover-smoke` 和 `experiments/transaction-smoke` 分别 `cargo build --release --locked`。
- 记录两个二进制的 SHA-256；记录 `rustc -Vv`、git HEAD、参数 SHA-256。
- 若构建产物与 manifest 中记录不一致，整批作废，不混用。

### 7.3 运行与日志

- 运行前关闭无关重负载；记录开始时间、室温/是否插电（若可获得）。
- 每个 batch 的 stdout/stderr 写入 `experiments/raw/logs/msm_scaling_20261022_<arm>_<config>_b<k>.{stdout,stderr}.log`。
- 原始 CSV：
  - Spend：沿用 `experiments/raw/csv/sapling_spend_prover_runs_<label>.csv` 与每 batch 的 `sapling_spend_stage_profile_<batch_id>.csv`、`sapling_spend_msm_inner_stage_profile_<batch_id>.csv` 等；
  - Output：`experiments/raw/csv/sapling_output_prover_runs_msm_scaling_20261022.csv`；
  - 交易：`experiments/raw/csv/sapling_tx_scaling_runs_msm_scaling_20261022.csv`。
- 估时：Spend 约 13–15 min，S-Window 约 4–5 min，Output 约 4 min，交易约 5 min，总计约 30–35 min（不含构建）。

### 7.4 提交顺序

1. 本预注册文件 + 脚本改动（不含原始数据）；
2. 原始 CSV/日志 + manifest + 派生表/图；
3. 结果文档、README/INDEX/每周汇总更新。

通过 PR 合并；不直接 push `main`。

---

## 8. 溯源与不覆盖

- 本阶段 tag：`msm_scaling_20261022`。所有新文件带此 tag；若路径已存在，编排器中止。
- 原始 CSV 只追加，不覆盖；每个 batch 有唯一 `batch_id`；manifest 把 `batch_id` 映射到配置。
- 不删除、不改写交易 baseline 的 raw CSV（`sapling_tx_construct_runs_real.csv`、`..._mock.csv`）或其分析器。
- 旧批次（不同默认值/不同二进制）只作为假设来源，不进入本阶段的配对统计。
- 结果文档必须列出：二进制 SHA-256、参数 SHA-256、git HEAD、CPU、Windows 版本、所有 mask、所有 c、每配置样本量、失败/重跑记录。

---

## 9. 风险与限制

1. **单机、单工具链**：结论只对 i7-14700 + Windows 11 + 当前 rustc 成立。
2. **样本量**：每配置 8–16 个 warm 证明；cluster bootstrap 已考虑 batch 相关，但 5% 级效应的功效有限。H2 的 5% 阈值是“工程上值得追”的门槛，不是统计显著性的替代。
3. **SMT 对照是间接的**：`0x5555` 消除了 sibling 共享，但无法证明每个 worker 在测量期间没有迁移；Windows 调度器仍可能在允许的 LP 集合内迁移。若 `0x5555` 无改善，不能反推“没有 SMT”，只能说“在该 mask 下无可测收益”。
4. **阶段计时器有开销**：Spend 的 `SAPLING_PROFILE=1` 会略微改变绝对时间；本阶段只做同条件比较，不把 Spend 的绝对值与交易 baseline 相减。
5. **1t FFT 路由**：默认 `SAPLING_FFT_SERIAL_SINGLE_THREAD=1` 使 1t 走串行 FFT、2t+ 走并行 FFT；1→2t 的 QAP/FFT 变化包含路由切换，不是纯并行加速。结果文档必须显式标注。
6. **窗口覆盖是诊断开关**：`SAPLING_MSM_WINDOW_C` 会改变 bucket 数和总操作数；c 扫描的结论只用于 H1，不作为默认值建议。
7. **交易层**：只测 1 spend + 2 outputs；Output 数量/形状变化可能改变拐点。Stage 0 不泛化。
8. **内存指标**：`bucket_payload_at_max_concurrency_estimate_bytes` 是估算，不是进程峰值 RSS；H4 只用它做量级判断。

---

## 10. 冻结声明

- 本文件在**任何 Stage 0 代码/测量之前**冻结；§3 的配置、§5 的验收表、§6 的判定规则在数据出来后不得修改。
- 若实现中发现某条口径写错（例如字段名/单位），只能在结果文档的“偏差”一节标注，并说明对结论的影响；不得回改本文件。
- 本文件的提交哈希、冻结时间、执行者将在结果文档 §0 记录。
- 本阶段不产生优化收益结论；Stage 1 的实现必须重新预注册。

**冻结日期**：2026-10-22
**执行者**：OpenCode（2026-10-22，用户确认后执行）
**协议模板**：`experiments/metadata/sapling_optimization_validation_protocol_20261017.md` §5
