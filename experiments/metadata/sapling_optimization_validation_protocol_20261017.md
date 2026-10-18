# Sapling 证明器优化验证协议（2026-10-17 冻结）

> 覆盖任务：**二-3 的前半段（测量协议 + 预声明验收标准 + 数据留存模板）**。
> **优化目标本身尚未选定**（留给项目负责人拍板，见 §7）。本文件的作用是：**在动任何代码之前**，把"怎么测、多少算成功、数据怎么留"钉死，避免事后挑阈值。
>
> **执行记录（2026-10-17，本协议冻结之后追加）**：负责人选定候选 **e**（配置级：线程数/亲和性）。预声明见 `sapling_default_config_experiment_preregistration_20261017.md`，结果见 `sapling_default_config_experiment_results_20261017.md` 与报告 §19。判定结论：**主指标未认证**（漂移守门触发），**串行参数读取阶段的 P 核收益稳健**，**降低线程数被认证为负结果**。本协议正文保持冻结、不改。

---

## 1. 为什么必须先冻结

本机是 P-core/E-core 混合架构，且已经实测出三类会污染结论的效应：

| 效应 | 量级 | 来源 |
|---|---|---|
| 核放置（P vs E） | **2.1×** | `sapling_pinned_baseline_and_thread_scaling_20261017.md` §3 |
| 不绑核时的**进程内迁移** | Output 批内极差 **70%** | 同上 |
| 冷启动（第 1 批 + 批内 run 1） | Spend **+5.8%** | 同上 §2 |
| 绑定范围（单核 vs 全部 P 核） | **+3.5%** | 同上 §3 |

在这些效应之下，"改了代码 → 时间变小了"极易是假信号。协议的目的就是**把不可控变成可控**。

---

## 2. 冻结基线（before）

| 电路 | 配置 | 取值 | 口径 |
|---|---|---:|---|
| Spend | 1t，掩码 `0x1` | **3685.6 ms** | 暖态中位（3 批×5，弃第 1 批与每次 run 1） |
| Output | 1t，掩码 `0x1` | **558.5 ms** | 同上 |

原始数据：`experiments/raw/csv/sapling_{spend,output}_prover_runs_pinned_baseline_20261017.csv`
派生：`results/tables/sapling_pinned_campaigns_20261017.csv`

> 该基线**同日、同二进制、同参数、同协议**才可比。跨天比较必须**重测 before**（见 §4 的 ABBA 配对）。

---

## 3. 测量协议（所有优化实验必须遵守）

1. **亲和性**：单线程一律掩码 `0x1`；多线程一律掩码 `0xFFFF`（仅 P 核）。**不得**使用不绑核数据做结论。
2. **线程数**：主口径 = 1 线程；辅口径 = 4 和 8 线程（已实测该区间并行效率 90%/59%，是真实优化空间所在，而非饱和后的 16/20）。
3. **批 × 次**：每配置 **≥3 批**，每批 = 1 次进程调用（内含 5 次 prove）；**丢弃第 1 批与每次 run 1**，有效 n ≥ 12。
4. **预热**：跑正式批次前先跑 1 批丢弃（等同 §2 的冷批处理）。
5. **机器状态**：测量期间不跑其它 CPU 负载；同一 before/after 对**在同一会话内**完成。
6. **诊断开关**：计时批次用 `SAPLING_PROFILE=0`。需要内存口径时另起 `prove_memory_ledger`（它会拖慢 prove，**不得**用于计时）。
7. **正确性**：每批必须 5/5 `verified=true` 且 `proof_bytes=192`，否则整批作废。
   > 注意：证明是随机化的（`r`、`s` 随机），所以**不能**要求 before/after 证明字节完全相同；只能要求"全部验证通过 + 固定长度"。

---

## 4. 噪声底线与可检测效应

- 绑核后单线程**暖态批中位**的复现性：Spend **1.3%**、Output **5.9%**（后者由 n=15 下的单点离群主导）。
- 结论：**1 线程下，小于约 3% 的端到端变化在没有加大样本量时不可分辨。** 多线程（4–8）信号更大但方差也更大。
- 因此：**验收阈值必须 ≥3%**；若预期收益 <3%，必须先声明"需要多少样本量"，或改用**分阶段计时**（`G16_STAGE_PROFILE` / `SAPLING_MSM_STAGE_TIMING`）来测**局部**变化，而不是端到端。
- 局部口径的可检测性更好（例如单次 MSM 调用时间），但必须声明"局部改善未转化为端到端改善"的风险。

---

## 5. 预声明验收标准（模板，填完再动代码）

在实现优化**之前**填写下表并提交（作为"预注册"）；**之后不得修改**。

| 字段 | 填写内容 |
|---|---|
| 目标（见 §7 候选） | `<待定>` |
| 改动文件 | `<文件列表>` |
| 假设 | `<为什么应该变快/变省>` |
| **主验收指标** | Spend 端到端 1t@0x1 暖态中位，**相对同日 before 变化 ≥ `X%`**（`X ≥ 3`） |
| 辅助指标 | 4t / 8t@0xFFFF 中位；`G16_STAGE_PROFILE` 中目标阶段的 ms |
| 内存指标（若涉及） | `prove_peak_abs_bytes`（`prove_memory_ledger`，n≥3）相对 before 下降 `Y%`，并给出峰值闭合账 |
| 正确性 | 100% `verified=true`，`proof_bytes=192`，且 circuit scale / 参数哈希不变 |
| 回退条件 | `<哪一步测出变慢/不通过就回退>` |
| 预期样本量 | before 3 批 + after 3 批（ABBA，见 §6） |
| 预声明日期 | `<yyyy-mm-dd>` |

**通过判据**：主指标达标 **且** 辅助指标无 >1% 的退化 **且** 正确性全过。
**不通过但有效**：主指标未达标但辅助指标显著改善 → 记为"局部改善，未转化为端到端"，仍然归档。

---

## 6. A/B 配对与数据留存

**ABBA 配对**（沿用本轮 fallback 消融已验证的形态）：同一次会话内按 A→B→B→A 各跑 ≥2 批，避免单侧漂移被算进效果；用中位数与 Mann–Whitney U（或等效非参检验）比较，并报告 p 值。

**留存模板**（每次实验必须新增，**不覆盖**任何既有文件）：

```
experiments/raw/csv/<prover>_prover_runs_<label>_<yyyymmdd>.csv           # 原始逐次数据
experiments/raw/csv/<prover>_prover_runs_<label>_<yyyymmdd>_summary.csv   # runner 派生汇总
experiments/raw/logs/<label>_<yyyymmdd>_*.{stdout,stderr}.log             # 每批日志
experiments/metadata/<label>_<yyyymmdd>.md                                # 结论 + 命令 + 哈希
```

每份 metadata 必须包含：exe SHA-256、参数 SHA-256、`git rev-parse HEAD`（+ 是否 dirty）、工具链版本、完整命令行、原始文件名、以及**该实验对应的预声明表**。

**提交拆分**（沿用本轮约定）：`code/scripts` → `raw data` → `docs/metadata`，三个提交。

---

## 7. 待定：优化目标（留给负责人拍板）

本协议不选定目标。候选与**已知证据**如下，供决策：

| # | 候选 | 已知证据 | 预期收益 | 风险/成本 |
|---|---|---|---|---|
| a | **H query 窗口化表示**（不物化 / bit-slice / 减小 c） | H 的窗口化缓冲 = **26.2 MB**，是 Spend 单线程峰值的最大单笔（占峰值 ~25%）；且**99.35% 槽非零** → 只能靠"不物化 / 换表示 / 减小 c" | 内存可省数 MB–20 MB 级；**时间收益不确定**（`c` 影响桶数 ∝2^c） | 改动在 `vendor/bellman`，需逐位正确性验证；可能拖慢时间 |
| b | **H query G1 MSM 时间** | 报告 §5：H query G1 是单笔最贵调用（约 1.45 s @1t） | 时间收益最直接 | 属算法级改动（signed digits / wNAF / 桶填充） |
| c | **B-G2 aux（Output）** | Output 最贵单次调用 | 只优化 Output（0.56 s 量级） | 收益绝对值小 |
| d | `vendor/groth16/src/prover.rs` 赋值转换并行化（原第 308 行 TODO） | 转换本身 ≤9 MB / 数十 ms 量级；in-situ 已量化 | 大概率 <3%，**可能测不出来** | 成本低，可作为"练手/证伪"实验 |
| e | **固定线程数为 4–8**（配置级，不改算法） | 已实测 8 线程并行效率 58.8%、16/20 线程几乎无增益且 20 线程更慢 | 端到端可达数倍（相对不绑核/高线程默认） | **不是算法优化**，属于部署/默认值调整，需说明清楚 |

> **建议顺序（供参考，不代替负责人决定）：e（零风险、立刻可验证）→ a（内存主因、已在报告 §9 排第 1）→ b（时间主因）**；d 可作为低成本的证伪实验。
>
> **状态更新（2026-10-17，后附）：** 负责人已选定并完成 **e** 与 **b**：e 见
> `sapling_default_config_experiment_results_20261017.md`（配置级：P 核绑定阶段收益认证、prove 配对显著性不足、反对降线程），
> b 见 `sapling_msm_signed_digit_results_20261017.md`（算法级：有符号窗口重编码，Spend 1t@`0x1` **−6.63%** 已认证、内存 −2.00 MB）。
> 候选 **a / c / d 仍未做**。本节上表的证据与预期收益保持原样，不改动。
>
> **状态更新（2026-10-18）：** 负责人第三个选定 **a**（内存级）并已完成：见
> `sapling_msm_lazy_recoding_results_20261018.md`（只预存进位位；H 缓冲 24.1 MB → 0.33 MB、现场瞬态 −23.79 MB、
> 端到端 1t −4.60% / 8t −8.52% / Output −1.90%，但 prove 峰值只降 **12.93 MB** < 预注册的 15 MB ⇒ **未通过、归档、默认保持 `0`**）。
> 该目标的副产品是一个**默认关闭的阶段峰值归因探针**（`SAPLING_G16_MEM_PHASE_PROBE`）和一条更新后的内存主因：
> **`qap_fft_h_exponent_prep` 阶段的 90.13 MB 绝对天花板**（与重编码开关无关，两臂逐字节相同）。
> **所有者决定（2026-10-18）：保持 a 的默认值 `0`，并新增候选 f 作为下一目标。** 候选 a/c/d 中 a 已完成（未通过），c/d 仍未做。
>
> | # | 候选 | 已知证据 | 预期收益 | 风险/成本 |
> |---|---|---|---|---|
> | f | **单线程 FFT 的 four-step scratch**（`vendor/bellman/src/domain.rs::best_fft`） | 阶段探针（`results/tables/sapling_qap_fft_subphase_peak_20261018.csv`）：`qap_fft_h_exponent_prep` 峰值 = 进入该阶段的 live（85.94 MB）+ 一个整域 scratch（**+4,194,424 B**）；`from_coeffs` 零净增、h 转换（+5.24 MB）**不是**峰值；`log_cpus == 0` 时四步法恒等却仍分配整域缓冲 + 两趟全量遍历 | 阶段峰值 −4.19 MB；`lazy=1` 全局峰值 −3.95 MB（可转化上限 = 90,130,325 − 86,184,605）；**组合**（`lazy=1` + 本改动）103.06 → 86.18 MB = **−16.88 MB** | 只对单线程生效（多线程路径逐字节不变，且其 scratch 总量已是理论最小值）；数值逐位等价，有门禁兜底 |
>
> 候选 f 的预注册（阈值按"阶段分解 + min(可移除量, 峰值−次高阶段)"设定，不重复目标 a 的阈值错误）见
> `sapling_qap_fft_scratch_preregistration_20261018.md`。

---

## 8. 与本轮其它文档的关系

- 基线与口径：`sapling_pinned_baseline_and_thread_scaling_20261017.md`
- 历史数据重构：`sapling_baseline_core_regime_restatement_20261017.md`
- 内存/转换 in-situ：`sapling_in_situ_conversion_and_exponent_density_20261017.md`
- 内存账本：`sapling_prove_memory_ledger_20261017.md`
- 主报告：`docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md`
