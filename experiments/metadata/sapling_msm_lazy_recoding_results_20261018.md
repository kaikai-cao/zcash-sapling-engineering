# 结果：H query 窗口化表示「去物化」（优化目标 a）— 2026-10-18

> 对应预注册 `sapling_msm_lazy_recoding_preregistration_20261018.md`（冻结提交 `85ffb0d`）。
> 预注册的阈值与判定规则**未做任何修改**；本文只记录测量、归因与按冻结规则得出的判定。
> 目标 b 的结果见 `sapling_msm_signed_digit_results_20261017.md`，两者互不影响语义。

---

## 0. 判定摘要

| 项 | 结果 | 冻结判据 | 判定 |
|---|---|---|---|
| **主指标**：`prove_peak_abs_bytes` 中位下降 | **12,933,401 B（−12.55%）** | ≥ 15 MB（预期 ~23.8 MB） | **未达标** |
| 辅助指标 1a：H query `exponent_prep_live_delta_bytes` 下降 | **23,789,344 B** | ≥ 20 MB | 达标 |
| 辅助指标 1b：进位位图字节数 | **327,680 B** | ≤ 0.4 MB | 达标 |
| 辅助指标 2：Spend 1t@`0x1` 端到端 | **−4.60%**（更快） | 不退化 >1% | 达标 |
| 辅助指标 3：8t@`0xFFFF` / Output 1t@`0x1` | **−8.52% / −1.90%**（更快） | 不退化 >1% | 达标 |
| 正确性 ①②③④ | 全过 | 全部必须 | 达标 |
| **通过判据** | 主指标未达标 | 主指标 ∧ 辅助 2/3 ∧ 正确性 | **PASS = False** |

**按预注册 §4 的回退条款**：主指标 < 15 MB ⇒ 记为「局部改动未转化为峰值下降」，归档，**开关默认值保持 `0`**（物料化）。本节以下所有内容都是对这一判定的证据与解释。

三点必须同时说清楚，否则会误读这个结果：

1. **改动本身完全按设计生效**：H query 的窗口化表示在实测中从 24,117,064 B（外层 + 堆，毛值）降到 327,680 B 的进位位图；该调用的现场瞬态下降 23,789,344 B，是判据 1a 要求的两倍有余。
2. **峰值确实下降了，只是幅度是 12.93 MB 而不是 23.79 MB**：这是一个真实的改进（−12.55%），不是「没效果」。
3. **未转化到 15 MB 的原因已用独立探针直接测出，不是推测**：prove 期本来就存在一个 **90.13 MB 的独立天花板**（`qap_fft_h_exponent_prep` 阶段，见 §3.3），该天花板与窗口化表示无关，**在两臂中逐字节相同**。改动只移除了天花板之上的那部分，因此峰值下降 = 103.06 − 90.13 = 12.93 MB。被移除的 24.1 MB 中有约 11 MB 本来就处在天花板之下，从来没有出现在峰值里。

---

## 1. 预注册与提交

| 阶段 | 提交 | 说明 |
|---|---|---|
| 预注册（先于任何代码改动） | `85ffb0d` | 阈值与判定规则冻结于此 |
| 实现（`vendor/bellman/src/multiexp.rs` + 微基准门禁） | `01ec647` | 开关 `SAPLING_MSM_LAZY_RECODING`，默认 `0` |
| 驱动脚本参数化 | `e0a13d4` | `-SwitchVar`，target b 命令行与 CSV 名不受影响 |
| 门禁 + 台账原始数据 | `d1b1d99` | |
| 阶段归因探针 + 分析器 | `13123b9` | `SAPLING_G16_MEM_PHASE_PROBE`，默认关闭 |
| 战役 + 归因 + 诊断原始数据 | `b690513` | |

---

## 2. 正确性

| 项 | 证据 | 结果 |
|---|---|---|
| ① 每批 5/5 `verified=true` 且 `proof_bytes=192` | 台账 2 臂 × 5 run（`sapling_prove_memory_ledger_msm_lazy_recoding_{off,on}_20261018.csv`）+ 3 个臂集共 120 次证明 | 全过 |
| ② 两种实现的 MSM 结果在 c = 2..=20、n = 131,071 下**逐位相同** | `msm_window_bench_lazy_ab_20261018.log`，19 条 `correctness=lazy_equals_materialised c=… ok` | 全过 |
| ③ 64 项前缀与朴素 double-and-add 相同 | 同日志，`naive_prefix` 16 条（c∈{1,3,5,8} × signed × lazy 全组合）+ `naive_n8` 4 条 | 全过 |
| ④ 参数哈希与电路规模不变 | spend `8e48ffd2…`、output `2f0ebbcb…`，2 臂集 CSV 中一致 | 全过 |

补强项（冻结清单之外、同一次门禁里跑的）：跨重编码一致性 `cross_recoding` 6 条、内建窗口规则与显式扫描一致 7 条。全日志 52 条 `correctness=… ok`，**stderr 为空**（无 panic）。

> 首次运行门禁时抓到一个真实缺陷并已修复：fill 循环改为只遍历 density map 后越界（`multiexp.rs:313`）。`FullDensity::iter()` 是 `iter::repeat(true)`，原实现靠 `exponents.iter().zip(…)` 截断；现改为 `.take(exponent_count)`。这正是「两种实现逐位相同」这条断言的用处——它在整规模下第一次运行就命中了。

---

## 3. 主指标：prove 期峰值，及其归因

### 3.1 台账（1t @ `0x1`，`SAPLING_PROFILE=1 SAPLING_MEM_PROBE=1`，每臂 5 run）

| run | A（物料化）`peak_abs` | B（进位位）`peak_abs` |
|---:|---:|---:|
| 1 | 103,062,917 | 90,130,276 |
| 2 | 103,064,485 | 90,130,324 |
| 3 | 103,062,965 | 90,130,324 |
| 4 | 103,064,485 | 90,130,324 |
| 5 | 103,062,965 | 90,130,324 |
| **暖态中位（run 2–5）** | **103,063,725** | **90,130,324** |

- **峰值下降 12,933,401 B = 12.93 MB（−12.55%）**；`prove_peak_delta_bytes` 同步下降 12,934,160 B。
- A 臂暖态中位复现冻结基线 103,062,954 B（差 +771 B，分配器粒度），说明物料化路径未被改动。
- 用加入阶段探针后重建的二进制、探针关闭时复测（`…_rebuild_check_off_20261018.csv`）：103,064,499 / 103,062,979，与基线一致 ⇒ 重建与探针**未扰动**物料化路径。

### 3.2 H query 的现场瞬态（辅助指标 1）

`BELLMAN_MSM_MEM_PROBE`，call 1 / n = 131,071 / c = 13 / 20 chunks，每臂 5 次采样取中位：

| 字段 | A | B |
|---|---:|---:|
| `exponent_prep_live_delta_bytes` | 23,873,080 | **83,736** |
| `carry_bitset_bytes` | — | 327,680 |
| `chunked_exponents` | 131,071 | 0 |
| `nonzero_chunk_slots` | 2,620,825 | 0 |
| `max_aux_prep_bytes`（非 H query 的最大值） | 6,940,312 | 246,680 |

毛值口径（见 §7）：24,117,064 B → 327,680 B，下降 **23,789,384 B**；两个实现（`Arc<Vec<Exponent>>` 物料化 / 进位位图）都保留 `Exponent::Zero/One` 短路，因此 0/1 语义不变。

### 3.3 峰值归因（新增 `SAPLING_G16_MEM_PHASE_PROBE`，两臂各 5 run）

`phase_peak_abs_bytes` = 该阶段内出现过的最高 live 值（绝对值，与台账同刻度）；取 run 2–5：

| 阶段 | A（物料化） | B（进位位） |
|---|---:|---:|
| `pre_body` | 69,126,089 | 69,126,088 |
| `circuit_synthesis` | 86,184,617 | 86,184,616 |
| `worker_vk_setup` | 85,935,913 | 85,935,912 |
| **`qap_fft_h_exponent_prep`** | **90,130,337** | **90,130,336** |
| `h_query_access_dispatch` | 83,867,537 | 78,924,712 |
| **`assignment_query_prep_dispatch`** | **103,064,497** | 82,870,336 |
| `proof_scalar_terms` | 73,099,593 | 73,095,400 |
| `wait_and_assembly` | 81,216,523 | 74,522,890 |

读法与结论：

1. **B 臂的全局峰值恰好就是 `qap_fft_h_exponent_prep` 阶段的峰值**（90,130,336 B，与台账 90,130,324 B 差 12 B），而**该阶段峰值在两臂逐字节相同**（90,130,337 / 90,130,336 B）。⇒ 改动把 90.13 MB 天花板之上的一切都移除干净了，天花板本身一点没动。
2. A 臂更高的那个 103.06 MB 峰值落在 `assignment_query_prep_dispatch` 区间（比该区间起点的 live 73,099,593 B 高 29,964,904 B），即**窗口化表示存活的窗口**（H query 的 job 在该窗口内由 worker 执行）。这与 3.2 中独立测到的 23.87 MB 现场瞬态相互印证。
3. 因此 `103.06 − 90.13 = 12.93 MB` 就是**物理上可转化**的上限：24.1 MB 的缓冲里有约 11 MB 处于 90.13 MB 天花板之下，从来不计入峰值。

> 探针会重设水位线，所以在这两个归因 run 的 CSV 里，台账自身的 `prove_peak_abs_bytes` 列**不可用**（它等于最后一次重设时的 live 值，69,125,641）。这两份 CSV 仅作为 stderr 的原始载体保留；权威全局值取自 §3.1，`running_max_abs_bytes` 字段给出阶段法重组的同值交叉验证。

---

## 4. 辅助指标 2/3：端到端时间守门（`SAPLING_MSM_LAZY_RECODING=0/1`，同一二进制）

`scripts/run_msm_signed_digit_campaign.ps1 -SwitchVar SAPLING_MSM_LAZY_RECODING`，3 轮交错 `ABBA,ABBA,BAAB`，每批 5 次证明，丢弃每臂首批与每批 run 1。

| 臂集 | 池化批中位 A | 池化批中位 B | 变化 | 配对 n=5 中位 | B 更快 | 精确符号检验 p |
|---|---:|---:|---:|---:|---:|---:|
| Spend 1t @ `0x1`（主） | 3511.2 ms | 3349.6 ms | **−4.60%** | −5.30% | 5/5 | 0.0625 |
| Spend 8t @ `0xFFFF` | 894.8 ms | 818.6 ms | **−8.52%** | −6.87% | 4/5 | 0.3750 |
| Output 1t @ `0x1` | 498.2 ms | 488.7 ms | **−1.90%** | −1.42% | 5/5 | 0.0625 |

- 主臂另报：池化证明中位 3515.7 → 3341.2 ms（−4.96%，MWU 双侧 p < 0.0001）。
- 主臂敏感性（不作首批丢弃，n=6 对）：中位 −5.04%，**6/6 更快，p = 0.0312**。
- 漂移守门：主臂前半→后半 A +2.6% / B +1.2%（同向，不构成臂效应）。
- 全部 120 次证明 `verified=true`。
- 结论：**三个臂集都不退化，且都更快**。预注册只要求「不退化 >1%」，实测反而有 1.9%–8.5% 的加速——因为去物化省掉了 131,071 次小分配与 20.97 MB 的堆写入/跨步读（预注册 §2.4 只承诺「中性或略好、幅度 <3%」，实测在 MSM 层面更大）。

---

## 5. 微基准（n = 131,071，1t @ LP0，同进程，暖态中位 3 次）

| 窗口 c | 物料化 (ms) | 进位位 (ms) | 变化 |
|---:|---:|---:|---:|
| 8 | 2227.4 | 2037.0 | −8.5% |
| 10 | 1832.4 | 1677.1 | −8.5% |
| 12 | 1562.7 | 1452.5 | −7.1% |
| **13（当前默认）** | **1488.4** | **1371.8** | **−7.8%** |
| 14 | 1520.1 | 1397.8 | −8.0% |
| 16 | 1868.5 | 1784.4 | −4.5% |

同一进程内两臂交替计时，因此不含重建与批次间漂移；c = 13 的物料化值 1488.4 ms 与目标 b 微基准（有符号 c=13）的 1478 ms 一致，交叉验证了测量本身。

---

## 6. 口径修正（取代此前的三个不一致数字）

此前同一缓冲出现过 26.2 / 22.0 / 19.9 MB 三个数字。原因已查明并冻结在预注册 §2.2：`exponent_prep_live_delta_bytes` 是**净值**，测点时源 `Vec<Scalar>`（4,194,304 B = 精确 4 MiB 容量）若已释放，整体就少 4 MiB。

| 数字 | 出处 | 口径 |
|---:|---|---|
| 26.2 MB | 普查 run（c=12） | 毛值 |
| 22.0 MB | 台账 off 臂（c=12） | 毛值 − 源 |
| 19.9 MB | 台账 on 臂（c=13） | 毛值 − 源 |

**引用时必须写「外层 + 堆」的毛值**：

| 配置 | 外层（24 B × n） | 堆（8 B × n × chunks） | 合计 |
|---|---:|---:|---:|
| 无符号 c=12（历史规则） | 3,145,704 | 23,068,496 | 26,214,200 B |
| 有符号 c=13（本次基线） | 3,145,704 | 20,971,360 | **24,117,064 B** |

两者之和与实测净值的差恒为 4,194,304 B（±4,696 B 分配器残差），闭合。

---

## 7. 实验要素

| 项 | 值 |
|---|---|
| 主机 | i7-14700，Windows 11，PowerShell 5.1，`rustc 1.98.1`（host `x86_64-pc-windows-gnu`） |
| 掩码 | 1t = `0x1`（LP0）；8t = `0xFFFF`（P 核） |
| 参数 | `ZCASH_PARAMS_DIR=D:\Research\zcash-params`；spend `8e48ffd2…`、output `2f0ebbcb…` |
| 环境变量 | `SAPLING_PROFILE=1`、`SAPLING_MEM_PROBE=1`、`SAPLING_MSM_LAZY_RECODING=0/1`、`SAPLING_G16_MEM_PHASE_PROBE=0/1`、`RAYON_NUM_THREADS`、`SAPLING_PROVER_RUNS_CSV` |
| 二进制（战役所用，**未含**阶段探针） | ledger `2867bca38c080f2134e8d563f87adc32b79ad1836ff5134f991afb0d6d84c437`；spend `a27f640776fd2e63682f02bee11c80d6f82d400510e539756410b8ac7bfc99eb`；output `e0149ba3d8bcc78d70ff8d53797b2a0410baee5ad1f778e79499a63b9c67015e`；bench `3d9c569ac36538aeb2965288ddb4c12dbd25fe0853287a9092426e738464e77c` |
| 二进制（阶段探针加入后，**仅供归因诊断**） | ledger `e9ef3ff33430d87374ded59d46ce1f39b056400c2c90aedb53825f12d4b21e42`；spend `13eddc203a9c12d2621c02d01bf2f95650e4d7710a31b1222d5115a4da1ba99a`；output `aa75f57dac7b0b5f0553f9ae195f59667759db29e0d7cc2d9a757b856d497034`；bench `a57aec27f98011731ba1eaecca205c67ac837deee815eabf1928806d1d978d3f` |
| 重建 | `cargo --offline --locked build --release --bins`（全量；上一目标曾因单 `--bin` 重建导致台账作废） |

新增原始数据文件（均不覆盖既有文件）：

```
experiments/raw/csv/sapling_prove_memory_ledger_msm_lazy_recoding_{off,on}_20261018.csv
experiments/raw/csv/sapling_prove_memory_ledger_msm_lazy_recoding_{rebuild_check_off,phase_probe_off,phase_probe_on}_20261018.csv
experiments/raw/logs/msm_window_bench_lazy_ab_20261018.log                 （+ .stderr.log，空）
experiments/raw/logs/sapling_prove_memory_ledger_msm_lazy_recoding_*_20261018.{log,stderr.log}
experiments/raw/csv/sapling_{spend,output}_prover_runs_msm_lazy_recoding_{primary,pcores,output}_{off,on}[_summary].csv
experiments/raw/logs/driver_sapling_msm_lazy_recoding_abba_t{spend_1_0x1,spend_8_0xFFFF,output_1_0x1}_20261018-*.log
experiments/raw/logs/sapling_{spend,output}_msm_lazy_recoding_*_t*_b1.{stdout,stderr}.log
results/tables/sapling_msm_lazy_recoding_{memory,abba}_20261018.csv
```

---

## 8. 复现步骤

```powershell
# 0) 构建（全量 bins）并记录哈希
cd experiments\prover-smoke
cargo --offline --locked build --release --bins

# 1) 正确性门禁 + 微基准（1t @ LP0，约 4 分钟）
$env:RAYON_NUM_THREADS='1'
# msm_window_bench.exe，stdout 重定向到 msm_window_bench_lazy_ab_20261018.log

# 2) 主指标：内存台账（每臂 5 run，1t @ LP0）
$env:SAPLING_PROFILE='1'; $env:SAPLING_MEM_PROBE='1'
# prove_memory_ledger.exe，SAPLING_MSM_LAZY_RECODING=0 / 1，
# CSV → sapling_prove_memory_ledger_msm_lazy_recoding_{off,on}_20261018.csv

# 3) 阶段归因（默认关闭，诊断用；其台账列不可用）
$env:SAPLING_G16_MEM_PHASE_PROBE='1'
# 同 2)，只看 stderr 里的 G16_MEM_PHASE 行

# 4) 端到端守门（同一二进制 + 开关）
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\scripts\run_msm_signed_digit_campaign.ps1 -Prover spend -Threads 1  -AffinityMask 0x1    -Orders ABBA,ABBA,BAAB -LabelPrefix msm_lazy_recoding_primary -SwitchVar SAPLING_MSM_LAZY_RECODING
& .\scripts\run_msm_signed_digit_campaign.ps1 -Prover spend -Threads 8  -AffinityMask 0xFFFF -Orders ABBA,ABBA,BAAB -LabelPrefix msm_lazy_recoding_pcores  -SwitchVar SAPLING_MSM_LAZY_RECODING
& .\scripts\run_msm_signed_digit_campaign.ps1 -Prover output -Threads 1 -AffinityMask 0x1    -Orders ABBA,ABBA,BAAB -LabelPrefix msm_lazy_recoding_output  -SwitchVar SAPLING_MSM_LAZY_RECODING

# 5) 分析与判定
python scripts\analyze_msm_lazy_recoding_experiment.py
```

---

## 9. 偏差、教训与边界

| 项 | 说明 |
|---|---|
| 微基准日志文件名偏离预注册 | 预注册写的是 `msm_window_bench_final_lazy_{off,on}_20261018.log` 两份；实现后该 bin 能在**同一进程内**断言两种实现逐位相同，证据强于分两次运行，因此合并为一份 `msm_window_bench_lazy_ab_20261018.log`。 |
| 主臂首次启动被中断 | 驱动在首个 batch 后使工作区变脏、第二次调用被拒；该次残留按「不覆盖」原则改名保存为 `*_aborted_false_start*`，随后以 `-AllowDirtyWorktree` 整轮重跑（与目标 b 同惯例，summary 中 `dirty_worktree=True`）。 |
| 阶段探针在测量之后加入 | 属于诊断性、默认关闭的新增（`13123b9`），物料化路径未变（§3.1 的探针关闭复测为证）；因此战役数据用的是探针之前的二进制哈希，两者都记录在 §7。 |
| **方法论教训（重要）** | 预注册的 15 MB 阈值建立在「峰值 ≈ 该缓冲 + 其它」的单点模型上，**没有先做阶段分解**。正确做法：内存类目标立项时，应先用阶段探针测出「次高阶段」的高度 `H2`，再把阈值设在 `min(缓冲毛值, 峰值 − H2)` 的量级上。本例中 `H2 = 90.13 MB`，可转化上限从一开始就只有 12.93 MB，15 MB 在物理上无法达到。 |
| 不可外推的边界 | 结论只在 Spend/Output 两个电路、本机 i7-14700、单线程与 8 线程两种配置下成立；进位位图大小随 `n × chunks` 线性增长，`chunks` 很大（c 很小）时位图会变大，需重新评估。 |

---

## 10. 结论与后续

**按冻结规则：不通过（主指标 12.93 MB < 15 MB），归档，开关默认保持 `0`。** 同时，本目标产出了三项可继续使用的资产：

1. **一个可复用的峰值归因探针**（`SAPLING_G16_MEM_PHASE_PROBE`，默认关闭），把「prove 峰值」从一个数字变成一张按阶段的表。
2. **prove 期内存主因已更新**：新的主因不是 H query 窗口化缓冲，而是 **`qap_fft_h_exponent_prep` 阶段（QAP/FFT 域向量 + H 指数转换）的 90.13 MB 绝对峰值**，它比阶段起点高 11.53 MB，且与重编码开关完全无关。这是下一步内存优化的自然目标（例如 `h_exponents` 的现场转换瞬态、三个域向量 `a/b/c` 的同时驻留）。
3. **一个已验证更快的改动**：端到端 1t −4.60%、8t −8.52%、Output −1.90%，MSM 层面 −7.8%，且峰值下降 12.93 MB。

**是否需要把默认值改为 `1` 属于所有者决策，冻结判据本身不授权这样做**：冻结规则在「主指标 <15 MB」时要求归档并保持默认 `0`，而该规则是在不知道存在 90.13 MB 天花板的情况下设定的。两种处置都可辩护，但必须显式选择并记录：

- **保持 `0`（严格遵循冻结规则）**：改动归档，作为「已验证的候选」保留；等 §10 第 2 项的天花板目标一并处理后，再以「组合收益」重新立项验收。
- **改为 `1`（工程收益优先）**：动因是三项时间守门全部更快、峰值下降 12.93 MB、正确性全过；代价是默认值在冻结判据未达标的情况下被改动，需要在 README 与报告里明确记录「该默认值变更不由冻结判据授权，属于所有者决策」。
