# Stage 0 结果：Groth16 prover 的 MSM 多核扩展膝点诊断（2026-10-22）

> 预注册：[`sapling_msm_scaling_diagnosis_preregistration_20261022.md`](sapling_msm_scaling_diagnosis_preregistration_20261022.md)
> 预注册文件 SHA-256：`71fa5ec37b2d4a2aa2fc80ecf43c965e101721b6aebc9694c97568e358a16916`
> 预注册提交：`489134a`
> 测量 HEAD：`547c943fec7a01143ecded6d14f49202418f7da5`
> 分析脚本：[`../../scripts/analyze_msm_scaling_diagnosis.py`](../../scripts/analyze_msm_scaling_diagnosis.py)
> 执行：OpenCode（2026-10-22，用户确认后执行）

本文件只记录 Stage 0 的**诊断结果**，不实现优化，也不切换任何默认值。所有阈值、主比较和判定规则沿用预注册 §6；本文不因结果方向修改阈值。

---

## 0. 结论摘要

1. **44/44 ??? manifest ? runner invocation ???? 0**?44 ??? batch ID?????? **14/14 PASS**?A0?A10-invocations?A1?A12???????????S-Window c=13???? batch ??????? 44 ???? ?2.2?
2. **H2（SMT/放置）为“部分支持”**：8t Spend `0xFFFF` → `0x5555` 的 prove 中位差为 **4.22%**（`0xFFFF` 更慢），90% cluster bootstrap CI 跨 0；H-query `fill_per_chunk` 差 **4.30%**，低于预注册的 8% 门槛。Output 为 **4.15%**（CI 不跨 0，但低于 5%），交易 `build_ms` 为 **6.66%**（CI 不跨 0）。因此主检验不把 SMT 判为已证实的主因；交易层的方向一致，作为次要证据。
3. **H1（窗口尾部）为“支持”**：8t `0x5555` 上，`c=12` 的 H-query `ns_per_add` 是 `c=13` 的 **0.8047 倍**（90% CI `0.7666–0.8465`，上界 <1），`max_concurrent=8`；`c=11` 更强（**0.7345**，CI `0.7007–0.7715`）。实际 prove 中位：`c=11` **657.81 ms**（5.07×）< `c=12` 662.55 ms < `c=10` 676.93 ms < `c=13` 751.51 ms（4.44×）。窗口尾部是真实可动的算法杠杆。
4. **H3（串行/低扩展阶段）为“部分支持”**：8t 串行项（synthesis + QAP/FFT + proof scalar）占 body 的 **31.5%**（≥15%），但 `t(P)=a+b/P` 对 16t 的预测误差为 **−20.48%**（>10%），说明 16t 的下降不能只用简单串行分数解释。
5. **H4（内存/带宽）不作独立判定**：8t `ns_per_add` 相对 1t 没有变慢（`173.20/490.33≈0.353`），不满足“每 add 变慢 ≥20%”的 H4 预测；但窗口扫描显示更小的 bucket footprint 伴随更低的 `ns_per_add`（c=10 的 0.59 MB → 122.50 ns/add；c=13 的 4.72 MB → 173.20 ns/add），与 H1 的窗口选择混叠，Stage 1 需要把内存上限纳入策略。
6. **Stage 1 第一优先（按预注册 §6.5 映射）**：H2 为“部分支持”、H1 为“支持” ⇒ **自适应窗口 / 窗口内切分**（`W mod P` 感知；在 Spend、Output、真实交易上验证）。8t `0x5555` 作为 Stage 1 的放置基线，不直接据此切换默认值；16t 不建议作为默认运行点。

**一句话：** 8t 的主要可动杠杆不是 SMT，而是 H-query 的窗口尾部与 bucket footprint；预注册的主比较 `c=12` 对 `c=13` 支持窗口尾部，且 `c=11`（W=24，8 的整数倍）在该负载上给出最好的实际 prove。Stage 1 应把“窗口选择 + 放置/内存约束”做成可检验的自适应策略。

---

## 1. 执行与环境

| 项 | 值 |
|---|---|
| 主机 | Intel Core i7-14700，28 LP（8 P 核 × HT + 12 E 核） |
| OS | Windows 11 Insider Preview 10.0.26220 |
| 工具链 | `rustc 1.98.1`，host `x86_64-pc-windows-gnu` |
| 参数目录 | `D:\Research\zcash-params` |
| Spend 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| Output 参数 SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| Spend 二进制 SHA-256 | `99b74fee0806b55be3f181e8a8030f89667df17e5b0269f2523c12031810e786` |
| Output 二进制 SHA-256 | `da516327f75ddc77904704110dd753ac36c02f1e71f818012bc277a498a6a663` |
| 交易二进制 SHA-256 | `836f0cd6c292eee7c8f21f5eb83cb5c3c7b8ad1bba8d2a6a101332ded1a76794` |
| 1t 亲和性 | `0x1`（LP0） |
| 8t 对照 | `0xFFFF`（8 P 核含 HT）vs `0x5555`（每个 P 核一个 LP） |
| 16t | 仅 `0xFFFF`（含 HT；`0x5555` 只有 8 LP，不用于 16t） |

所有 batch 串行执行，batch 之间空闲 5 s；每批 5 个 Spend/Output 证明或 6 笔交易，丢弃 run 1，其余为 warm。亲和性在启动后读回并记录。

---

## 2. 验收与执行偏差

### 2.1 验收

分析器输出 `results/tables/msm_scaling_acceptance_msm_scaling_20261022.csv`，**14/14 PASS**：

- A1：Spend 每 batch 5 行、5/5 `verified=true`；
- A2：每 batch 40 条 MSM call、40 条 inner-stage、5 条 G16 stage；
- A3：`abs(stage_sum − create_proof_body) ≤ 0.01 ms`；
- A4：S-Window 的 H-query `window` 与请求 `c` 一致；
- A5：Output 每 batch 5 行、5/5 verified；
- A6：交易每 batch 6 行、6/6 verified、`tx_bytes=2377`、V5、1 spend + 2 outputs；
- A7：亲和性读回精确匹配；
- A8：`rayon_threads` 等于请求值；
- A9：单一 git HEAD、预注册哈希、冻结参数哈希；
- A10 / A10-invocations：44 行 manifest、各组 batch 数符合 §3.3；
- A11：44 个唯一 batch ID、冻结 tag；
- A12：分析器对 18/18 行（含 mock）独立复检结构字段。
- A0：manifest tag 与预注册哈希存在。

### 2.2 实际发生的偏差（必须保留）

1. **第一次 campaign 在 invocation 17 中止。** 前 16 批（12 个 S-Scale + 4 个 S-ABBA）已完成，但编排器在失败前没有导出 manifest。中止原因是运行时修改了 tracked 的 `scripts/README.md`，工作树变脏；同时 orchestration 的 `2>&1` 在 `$ErrorActionPreference='Stop'` 下把子进程 stderr 当作终止错误。日志保留为 `experiments/raw/logs/msm_scaling_campaign_20261022.orchestrator.log`。前 16 行 manifest 由该日志的 `[n]` 块和 `Batch ID:` 重建，`start_utc`/`end_utc` 为空；没有覆盖任何原始 CSV。
2. **第二次续跑在 S-Window `c=13` 中止。** `run_spend_combined_profile.ps1` 的 `expectedWindow` 断言只按 signed recoding 的“每 query 最优 c”计算，没有读取 `SAPLING_MSM_WINDOW_C` 覆盖；实际 window=13 与断言期望的 3/12 等不一致，runner 在写完整 profile 前抛错。该失败 batch `1792658853429` 只留下 5 行 raw prove 行，没有 stage/MSM/metadata；其 raw CSV 被原样改名保留为 `experiments/raw/csv/sapling_spend_prover_runs_msm_scaling_20261022_spend_t8_0x5555_c13.failed_1792658853429.csv`，失败的 manifest 行保留为 `experiments/metadata/msm_scaling_manifest_msm_scaling_20261022.attempt2_failed_row21.csv`。该 batch 不计入 44 条数据。
3. **第三次续跑（从 21 开始）完成 44 次。** S-Window 使用一个临时 runner 副本，唯一改动是让 expected window/bucket/chunk 读取 `SAPLING_MSM_WINDOW_C`；该修复随后已等价提交到 `scripts/run_spend_combined_profile.ps1`。二进制、参数和计时路径未变。日志保留为 `.resume.log`（第二次失败）和 `.resume2.log`（最终完成）。
4. **分析实现修正（未改阈值）。** 首版分析器把 warm 样本直接合并取中位；预注册 §4.1 要求“先每 batch 取 warm 中位，再对 batch 中位取中位”。在结果文档定稿前已改为 batch-median-of-medians，并把 batch 作为 bootstrap 单位；同时补上 G16 stage 指标的聚合和 `0x...` mask 解析。预注册的阈值、主比较和 H1–H4 规则未改。
5. **交易 baseline 的 8t 数字与本次不一致。** 历史 baseline 的 8t `0xFFFF` 为 **1,176.0 ms**（3.65×），本次 T-ABBA 的 8t `0xFFFF` 为 **872.36 ms**、`0x5555` 为 **814.30 ms**；二进制 SHA-256 相同。两者不混合，本文以本次 44 批为 Stage 0 的测量事实；历史 8t 只作为“未复现的基线批次”记录（见 §7.3）。

---

## 3. Spend 线程扩展

`prove_ms` 为每 batch warm 中位，再对 batch 中位取中位；1t 为 `0x1`，8t 为 `0x5555` 的 ABBA 组，16t 为 `0xFFFF`。

| 配置 | prove 中位 (ms) | speedup vs 1t | 并行效率 |
|---|---:|---:|---:|
| 1t `0x1` | 3,336.76 | 1.00× | 100% |
| 2t `0xFFFF` | 1,910.95 | 1.75× | 87.3% |
| 2t `0x5555` | 1,781.91 | 1.87× | 93.6% |
| 4t `0xFFFF` | 1,067.15 | 3.13× | 78.2% |
| 4t `0x5555` | 1,023.85 | 3.26× | 81.5% |
| 8t `0xFFFF` | 756.74 | 4.41× | 55.1% |
| 8t `0x5555` | 724.80 | 4.60× | 57.5% |
| 16t `0xFFFF` | 700.61 | 4.76× | 29.8% |

读法：

- 2t/4t 的 `0x5555` 比 `0xFFFF` 快 6.8%/4.1%，方向与 SMT 一致；8t 只有 4.2%（见 §4）。
- 8t → 16t 只再降 **3.3%**（724.80 → 700.61 ms），而线程数翻倍；16t 的并行效率仅 29.8%。**默认运行点不应选 16t**。
- 8t 的 4.60× 仍显著低于 8×；线程扩展在 8t 已明显变平，但这不是“8t 只有 3.65×”的历史数字（见 §7.3）。

---

## 4. H2：SMT / 放置（主检验：8t Spend）

ABBA 顺序为 `FFFF, 5555, 5555, FFFF, FFFF, 5555, 5555, FFFF`，每 mask 4 个 batch、16 个 warm 证明。

| 指标 | `0xFFFF` | `0x5555` | Δ（FFFF−5555）/FFFF | 90% CI | 判定 |
|---|---:|---:|---:|---:|---|
| Spend `prove_ms` | 756.74 ms | 724.80 ms | **+4.22%** | −23.40 … +102.65 ms（跨 0） | **部分支持** |
| Spend `fill_per_chunk` | 84.57 ms | 80.93 ms | +4.30% | — | 低于 8% 门槛 |
| Output `prove_ms` | 92.07 ms | 88.24 ms | **+4.15%** | +2.42 … +5.22 ms（不跨 0） | 方向一致，<5% |
| 交易 `build_ms` | 872.36 ms | 814.30 ms | **+6.66%** | +53.34 … +62.78 ms（不跨 0） | 交易层次要证据 |

判定：

- 预注册 H2 的“支持”要求 `Δ_prove ≥ 5%`、CI 下界 >0、且 `Δ_fill ≥ 8%`。Spend 的 Δ=4.22%、CI 跨 0、Δ_fill=4.30%，**不满足“支持”**；但 2% ≤ Δ < 5%，按预注册属于 **部分支持**。
- Output 的 4.15% 方向一致且 CI 不跨 0，但仍低于 5%；交易层 6.66% 是唯一超过 5% 的分量。交易层不是 H2 主检验，且 T-ABBA 只有每 mask 2 个 batch，不能据此把 SMT 升级为主因。
- 结论：**8t 的放置有可测的小幅收益，但不是 8t 扩展损失的主要解释**。Stage 1 应把 `0x5555` 作为控制变量/基线，而不是把“SMT 是主因”写成既成结论。

---

## 5. H1：H-query 窗口尾部（主检验：8t `0x5555`）

窗口扫描 `c ∈ {10,11,12,13}`，每 c 两个 batch，回文顺序 `13, 11, 12, 10, 10, 12, 11, 13`。`W = floor(255/c)+1`；`T = W / (P·ceil(W/P))`，P=8。

| c | W | T | prove 中位 (ms) | speedup | `ns_per_add` | 对 c=13 的 R | 90% CI | `max_conc` | bucket payload |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 26 | 81.25% | 676.93 | 4.93× | 122.50 | 0.707* | — | 8.0 | 0.59 MB |
| 11 | 24 | **100%** | **657.81** | **5.07×** | 127.21 | **0.7345** | 0.7007–0.7715 | 8.0 | 1.18 MB |
| 12 | 22 | 91.67% | 662.55 | 5.04× | 139.37 | **0.8047** | 0.7666–0.8465 | 8.0 | 2.36 MB |
| 13 | 20 | 83.33% | 751.51 | 4.44× | 173.20 | 1.000 | — | 8.0 | 4.72 MB |

\* c=10 的 R 由中位数直接计算，未在预注册中要求 CI；只作描述。

判定：

- 主比较 `c=12` 对 `c=13`：**R=0.8047，90% CI 上界 0.8465 < 1.00，且 `max_conc=8` ⇒ H1 支持。**
- 次要比较 `c=11` 对 `c=13`：R=0.7345，CI 上界 0.7715 <1 ⇒ 也支持。预注册因此允许记录“尾部存在，且本负载的最佳窗口是 c=11”；但**不直接改默认值**。
- 实际 wall 最好的是 **c=11**（657.81 ms），不是 `ns_per_add` 最低的 c=10（676.93 ms）。c=10 的 bucket 更小但 W 更多、尾部只剩 81.25%；c=11 同时满足 W=24（8 的整数倍）、T=100%、payload 1.18 MB。**c=11 是 Stage 1 的首选候选**，c=12 是次选；c=13 是当前默认，明显受尾部拖累。
- c=13 的 `fill_imbalance=1.307` 显著高于 c=11 的 1.081；c=13 的 `fill_parallel_eff=0.389`，c=11 为 0.532。尾部与负载不均衡的方向一致。

---

## 6. H3：串行/低扩展阶段

串行项定义为 `circuit_synthesis_constraints + qap_fft_h_exponent_prep + proof_scalar_terms`；body 为 `create_proof_body_ms`。8t 使用 `0x5555`。

| P | prove (ms) | 串行项 (ms) | 占 body | `wait_and_assembly` (ms) |
|---:|---:|---:|---:|---:|
| 1 | 3,336.76 | 469.87 | 14.08% | 596.18 |
| 2 | 1,781.91 | 335.75 | 18.84% | 1,443.61 |
| 4 | 1,023.85 | 252.12 | 24.63% | 768.15 |
| 8 | 724.80 | 228.37 | **31.51%** | 491.48 |
| 16 | 700.61 | 253.55 | 36.19% | 443.65 |

`t(P)=a+b/P` 在 P∈{1,2,4,8} 上拟合：

- `a=370.889 ms`，`b=2,980.288 ms`，串行分数 `a/(a+b)=0.1107`；
- 16t 预测 `557.16 ms`，实测 `700.61 ms`，误差 **−20.48%**。

判定：串行占比 ≥15%，但 Amdahl 两参数模型对 16t 的误差 >10% ⇒ **部分支持**。原因不是单一串行分数：1t 默认走串行 FFT、2t+ 走并行 FFT（1→2t 有路径切换），16t 又有 HT 争用；`wait_and_assembly` 也包含等待并行任务的时间，不是纯串行。Stage 1 若做“串行阶段重叠/流水化”，需要单独建模，不能只用 `a+b/P`。

---

## 7. Output 与真实交易

### 7.1 Output

| 配置 | prove 中位 (ms) | speedup vs 1t |
|---|---:|---:|
| 1t `0x1` | 478.51 | 1.00× |
| 8t `0xFFFF` | 92.07 | 5.20× |
| 8t `0x5555` | **88.24** | **5.42×** |
| 16t `0xFFFF` | 88.87 | 5.38× |

Output 的 8t `0x5555` 略好于 16t `0xFFFF`（88.24 vs 88.87 ms）；16t 没有收益。Output 的 SMT 差 4.15%，方向与 Spend 一致但低于 5%。

### 7.2 真实交易（1 spend + 2 outputs）

| 配置 | `build_ms` 中位 | `sum_proofs_ms` 中位 | speedup vs 1t |
|---|---:|---:|---:|
| 1t `0x1` | 4,328.61 | 4,328.61 | 1.00× |
| 8t `0xFFFF` | 872.36 | 871.96 | 4.96× |
| 8t `0x5555` | **814.30** | **813.86** | **5.32×** |
| 16t `0xFFFF` | 1,044.32 | 1,043.83 | 4.14× |

交易构造的非证明部分 <1 ms，`build_ms` 与 `sum_proofs_ms` 基本相等；因此交易层的扩展就是 spend + 2 outputs 的证明扩展。8t `0x5555` 最好；16t 反而比 8t `0x5555` 慢 **28%**，是明确的过订阅/HT 反例。交易层 `0xFFFF`→`0x5555` 为 6.66%，是 H2 的次要支持证据。

### 7.3 与历史交易 baseline 的差异

历史 baseline（`sapling_tx_construction_results_20261022.md`，A1/A2/A3）在同一二进制 SHA-256 下记录：

- 1t `0x1`：`build_ms=4,292.70`；
- 8t `0xFFFF`：`build_ms=1,176.05`，约 3.65×；
- mock 1t：4.83 ms。

本次 T-Scale 的 1t 为 4,328.61 ms（比历史高 0.8%），但 8t `0xFFFF` 为 872.36 ms、`0x5555` 为 814.30 ms，明显快于历史 8t。二进制 SHA、参数 SHA、交易形状均相同；差异更可能来自**批次时的频率/热状态、后台负载或历史 8t 批次的偶然慢态**，而不是代码或交易结构。本文不把两者混合，也不据此改写历史 baseline；Stage 0 的扩展结论以本次 44 批为准。这个差异同时说明：**“8t 只有 3.65×”并不是一个稳定的、可重复的上界**；本次 8t 已到 4.6×（Spend）/5.3×（交易），但离 8× 仍远。

---

## 8. H4：内存/带宽/竞争（次要）

- 8t `c=13` 的 H-query `ns_per_add=173.20`，1t 为 490.33；比值 **0.353**，不满足 H4 的“每 add 变慢 ≥20%”预测。8t 的 H-query 本身仍有并行收益，不是“每 add 更贵”。
- 但窗口扫描中，bucket payload 与 `ns_per_add` 同向下降：

| c | payload | `ns_per_add` | `fill_parallel_eff` |
|---:|---:|---:|---:|
| 10 | 0.59 MB | 122.50 | 0.571 |
| 11 | 1.18 MB | 127.21 | 0.532 |
| 12 | 2.36 MB | 139.37 | 0.481 |
| 13 | 4.72 MB | 173.20 | 0.389 |

  c=10/c=11 的 footprint 更小、`ns_per_add` 更低；c=13 的 payload 最大、`fill_imbalance=1.307`。这与“bucket 足迹/缓存竞争影响窗口选择”一致，但 c 同时改变 W、尾部和 bucket 数，**不能把 footprint 单独判为因果**。H4 只作为 Stage 1 的约束项：自适应策略应带内存上限，不能只看 `W mod P`。

---

## 9. Stage 1 选择（按预注册 §6.5）

| H2 | H1 | H3 | 第一优先 | 本文对应 |
|---|---|---|---|---|
| 部分支持 | **支持** | 部分支持 | **自适应窗口/窗口内切分**（`W mod P` 感知；在 Spend/Output/交易验证） | §5、§7 |

具体建议（Stage 1 需单独预注册，不在本文件实现）：

1. **首选策略：按 P、n、W mod P 和 bucket 内存上限选择 c。** 本负载 8t/n=131071 的最佳实际 wall 是 `c=11`（W=24，T=100%，657.81 ms），`c=12` 次之（662.55 ms）；`c=13` 当前默认为 751.51 ms。策略不能只拟合“ns/add 最小”（那会选 c=10），而要以 **prove wall** 为主目标，并记录 payload 上限。
2. **窗口内切分/多 MSM 调度**：在 c 固定时，把 H-query 的 24 个 chunk 按 P 切成整数块，减少 `W mod P` 的尾部；同时评估 L/G2 多 MSM 的并发是否会挤占 H-query 的 chunk 带宽。预注册中“窗口内切分”是第一优先的一部分，不能只做静态 c 常量。
3. **放置基线**：Stage 1 使用 `0x5555` 作为 8t 基线，避免 SMT 混淆；把 `0xFFFF` 作为对照。H2 主检验为部分支持，不能直接写“SMT 是主因”，但交易层 6.66% 值得在 Stage 1 复核。
4. **不要默认 16t**：16t 相对 8t `0x5555` 仅 +3.3%（Spend），交易层反而慢 28%；除非 Stage 1 证明有新的调度/放置能消除 HT 争用。
5. **H3 第二优先**：串行项占 31.5%、Amdahl 误差 −20.5%；若窗口策略落地后 MSM 墙下降，串行阶段重叠/流水化会成为下一个杠杆。Stage 1 不应同时改窗口和串行阶段，否则无法归因。

---

## 10. 限制

1. 只覆盖 i7-14700 + Windows 11 + 当前 rustc；不外推到其他 CPU/OS。
2. H2 的 5% 阈值是预注册的“最小可操作效应”；Spend 的 4.22% 在统计上 CI 跨 0，不能写成“SMT 已证实”。交易层的 6.66% 只有每 mask 2 个 batch，且 T-ABBA 的 CV 为 6.8%（FFFF），需要 Stage 1 复核。
3. `0x5555` 只是“每个 P 核一个 LP”的亲和性约束；Windows 仍可能迁移线程，不能证明每个 worker 内部没有迁移。H2 的结论是“在该 mask 下可测的差异”，不是 SMT 微架构的因果证明。
4. `ns_per_add` 使用 signed recoding 的模型 `W·(n+2·2^(c−1))`；c=10 的 bucket 更小，模型对“每 add 成本相同”的假设更弱。H1 的判定同时看实际 prove 和 `fill_per_chunk`，不只看 `ns_per_add`。
5. 窗口扫描改变 c 同时改变 bucket 数、W、payload 和尾部利用率；c=10/c=11 的 footprint 信号与 H1 尾部混叠，Stage 1 需要额外的固定 footprint/固定 W 对照（若 vendor 接口允许）来分离。
6. 交易 baseline 的 8t 差异未完全归因；本文保留历史数字，不用它做 Stage 0 的对照。
7. 阶段计时受 `SAPLING_PROFILE=1` 影响；Spend 的绝对值不与无 profiling 的交易 baseline 混合。

---

## 11. 产物与复现

### 11.1 清单与原始数据

- 预注册：[`sapling_msm_scaling_diagnosis_preregistration_20261022.md`](sapling_msm_scaling_diagnosis_preregistration_20261022.md)
- Manifest（44 行）：[`msm_scaling_manifest_msm_scaling_20261022.csv`](msm_scaling_manifest_msm_scaling_20261022.csv)
- 第一次 campaign 日志：[`../raw/logs/msm_scaling_campaign_20261022.orchestrator.log`](../raw/logs/msm_scaling_campaign_20261022.orchestrator.log)
- 第二次失败日志：[`../raw/logs/msm_scaling_campaign_20261022.resume.log`](../raw/logs/msm_scaling_campaign_20261022.resume.log)
- 最终续跑日志：[`../raw/logs/msm_scaling_campaign_20261022.resume2.log`](../raw/logs/msm_scaling_campaign_20261022.resume2.log)
- 失败的 c=13 partial raw：[`../raw/csv/sapling_spend_prover_runs_msm_scaling_20261022_spend_t8_0x5555_c13.failed_1792658853429.csv`](../raw/csv/sapling_spend_prover_runs_msm_scaling_20261022_spend_t8_0x5555_c13.failed_1792658853429.csv)
- 失败的 manifest 行：[`msm_scaling_manifest_msm_scaling_20261022.attempt2_failed_row21.csv`](msm_scaling_manifest_msm_scaling_20261022.attempt2_failed_row21.csv)
- Spend raw：`experiments/raw/csv/sapling_spend_*_<batch_id>.csv` 与 `sapling_spend_prover_runs_msm_scaling_20261022_*.csv`
- Output raw：`experiments/raw/csv/sapling_output_prover_runs_msm_scaling_20261022_output.csv`
- 交易 raw：`experiments/raw/csv/sapling_tx_scaling_runs_msm_scaling_20261022.csv`
- 每 batch metadata：`experiments/metadata/sapling_spend_combined_profile_<batch_id>.md`

### 11.2 派生表（由分析脚本重建）

- [`results/tables/msm_scaling_acceptance_msm_scaling_20261022.csv`](../../results/tables/msm_scaling_acceptance_msm_scaling_20261022.csv)
- [`results/tables/msm_scaling_summary_msm_scaling_20261022.csv`](../../results/tables/msm_scaling_summary_msm_scaling_20261022.csv)
- [`results/tables/msm_scaling_stage_summary_msm_scaling_20261022.csv`](../../results/tables/msm_scaling_stage_summary_msm_scaling_20261022.csv)
- [`results/tables/msm_scaling_hquery_summary_msm_scaling_20261022.csv`](../../results/tables/msm_scaling_hquery_summary_msm_scaling_20261022.csv)
- [`results/tables/msm_scaling_smt_abba_msm_scaling_20261022.csv`](../../results/tables/msm_scaling_smt_abba_msm_scaling_20261022.csv)
- [`results/tables/msm_scaling_window_sweep_msm_scaling_20261022.csv`](../../results/tables/msm_scaling_window_sweep_msm_scaling_20261022.csv)
- [`results/tables/msm_scaling_amdahl_msm_scaling_20261022.csv`](../../results/tables/msm_scaling_amdahl_msm_scaling_20261022.csv)

### 11.3 图

- [Spend 扩展](../../results/figures/msm_scaling_spend_prove_msm_scaling_20261022.png)
- [H-query fill/chunk](../../results/figures/msm_scaling_hquery_fill_per_chunk_msm_scaling_20261022.png)
- [窗口扫描](../../results/figures/msm_scaling_window_sweep_msm_scaling_20261022.png)
- [SMT ABBA](../../results/figures/msm_scaling_smt_abba_msm_scaling_20261022.png)
- [Output](../../results/figures/msm_scaling_output_prove_msm_scaling_20261022.png)
- [交易](../../results/figures/msm_scaling_tx_build_msm_scaling_20261022.png)

### 11.4 复现命令

```powershell
# 需在干净 tracked worktree 上；追加输出允许
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run_msm_scaling_campaign.ps1 `
  -RepoRoot D:\Research\zcash-sapling-engineering `
  -ResumeThrough 0

# 仅重建派生表/图（不重新测量）
python scripts/analyze_msm_scaling_diagnosis.py
```

> 本次 S-Window 的 c=13 失败与续跑记录见 §2.2；正常全量运行应在干净 HEAD 上一次完成。`-ResumeThrough` 只用于中断后续跑，不改变批次数或配置顺序。

---

**结论：** Stage 0 没有实现优化；它把 8t 的损失分解为“窗口尾部/负载不均衡（H1 支持）”+“SMT/放置（H2 部分支持）”+“串行/低扩展阶段（H3 部分支持）”。Stage 1 的第一优先是**自适应窗口/窗口内切分**，而不是继续堆静态基线；`c=11`/`c=12` 与 `W mod P`、bucket footprint 的联合策略是下一个可通过实验检验的算法/系统问题。
