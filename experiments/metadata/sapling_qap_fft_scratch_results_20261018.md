# 结果：单线程 FFT four-step scratch 消除（优化目标 f）— 2026-10-18

**判定：通过（PASS）——冻结验收表六项全过。** 主指标 `lazy=1` 配置 prove 全局峰值下降 **3,945,720 B（−4.38%）**，达到冻结阈值（≥3,500,000 B），且**逐字节命中预注册预测的可转化上限**；机制指标（`qap_ffts_done` 阶段峰值）下降 4,194,352 B；三个时间臂集全部在 1% 非退化预算内且方向为负（更快）；正确性门禁 12/12 逐位一致、20/20 证明验证通过；shipped default（`lazy=0`）峰值不上升（−760 B）。按预注册约定，开关默认保持 `0`，组合收益（`lazy=1` + 本改动 = 103.06 → 86.18 MB，−16.88 MB）的正式验收留待目标 g。

## 0. 判定摘要（对照冻结验收表）

| # | 指标 | 冻结阈值 | 实测 | 判定 |
|---|---|---:|---:|:--:|
| **主** | `prove_peak_abs_bytes` 下降（`lazy=1`，1t@`0x1`） | ≥ 3,500,000 B | **−3,945,720 B（−4.38%）**：90,130,334 → 86,184,614 B | **MET** |
| 辅 1 | `qap_ffts_done` 阶段峰值下降（机制生效） | ≥ 3,500,000 B | **−4,194,352 B**：90,130,332 → 85,935,980 B | **MET** |
| 辅 2a | 全部证明 `verified=true`、`proof_bytes=192` | 100% | 20/20（四组台账） | **PASS** |
| 辅 2b | `serial_fft` 与四步法逐位相同（n=2^10/2^13/2^17 × 4 操作） | 全过 | 12/12 digest 一致，0 失配 | **PASS** |
| 辅 3 | 时间守门（三个臂集，池化批中位） | 不退化 >1% | −3.31% / −3.17% / −0.20% | **PASS** |
| 辅 4 | `lazy=0`（shipped default）全局峰值不上升 | ≤ 0 B | −760 B | **PASS** |

`PASS = 主 ∧ 辅1 ∧ 辅2a ∧ 辅2b ∧ 辅3 ∧ 辅4 = True`。

## 1. 预注册与提交

- 预注册（冻结，先于任何算法改动）：`experiments/metadata/sapling_qap_fft_scratch_preregistration_20261018.md`（提交 `997016a`）。
- 实现与数据：提交 `1bc8bc7`（`vendor/bellman/src/domain.rs` 开关 `SAPLING_FFT_SERIAL_SINGLE_THREAD`，默认 `0`；`fft_path_gate.rs` 门禁；四组台账 + 两组探针 + 三个臂集原始数据）。
- 本文档 + 派生表修正：本提交。验收阈值与判据未做任何修改；实现与测量中发现的唯一口径问题记录于 §6。

## 2. 正确性（辅 2a / 2b）

| 项 | 结果 |
|---|---|
| 四组内存台账（`lazy`×`fix`）每次证明 | 20/20 `verified=true`，`proof_bytes=192`，参数 SHA-256 不变 |
| `fft_path_gate`：同输入两路径 digest 对照 | 12 例（log_n ∈ {10, 13, 17} × {fft, ifft, coset_fft, icoset_fft}）全部一致，0 失配 |
| 多线程路径 | 代码路径逐字节不变（`log_cpus ≥ 1` 不走新分支），8t 臂集正确性由时间守门批次连带覆盖（20/20） |

门禁日志：`experiments/raw/logs/fft_path_gate_{off,on}_20261018.log`。

## 3. 主指标与内存归因（主 / 辅 1 / 辅 4）

### 3.1 对照组台账（1t @ `0x1`，每臂 5 run，暖态 run 2–5 取中位）

| 臂（`lazy`×`fix`） | `prove_peak_abs_bytes` | `live_before_prove` | `prove_ms`（含探针开销） |
|---|---:|---:|---:|
| lazy0-fix0（= shipped default 现状） | 103,063,734 B | 68,729,865 B | 3,568.0 |
| lazy0-fix1 | 103,062,974 B | 68,729,865 B | 3,519.0 |
| lazy1-fix0（= 目标 a 的 `1` 配置） | 90,130,334 B | 68,729,865 B | 3,584.4 |
| **lazy1-fix1（本目标）** | **86,184,614 B** | 68,729,865 B | **3,355.6** |

- **主指标**：`lazy=1` 下 90,130,334 → 86,184,614 B = **−3,945,720 B（−4.38%）** ≥ 3,500,000 B ⇒ **MET**。
- **辅 4**：`lazy=0` 下 103,063,734 → 103,062,974 B = **−760 B**（不上升；该量级为分配器粒度噪声，远低于单线程 1.3% ≈ 1.2 MB 的复现性底线）⇒ **PASS**。

### 3.2 阶段探针（辅 1：机制确实生效）

`SAPLING_G16_MEM_PHASE_PROBE=1`，`lazy=1` 两臂各 5 run（run 2–5）：

| 臂 | `qap_ffts_done` 阶段峰值 | `circuit_synthesis` 峰值 | 全局 `running_max` |
|---|---:|---:|---:|
| fix0 | 90,130,332 B | 86,184,612 B | 90,130,332 B |
| fix1 | **85,935,980 B** | 86,184,612 B | **86,184,612 B** |

阶段下降 **4,194,352 B** ≥ 3,500,000 B ⇒ **MET**。且 fix1 的全局 `running_max`（86,184,612 B）已由 `circuit_synthesis` 峰值决定——与预注册 §1.3 的预测（"移掉 scratch 后全局峰值改由既存的 `circuit_synthesis` 峰值决定"）完全一致。

### 3.3 与预注册预测的对照（逐字节级）

| 预注册预测 | 实测 | 偏差 |
|---|---:|---:|
| 阶段峰值 −4,194,424 B | −4,194,352 B | 72 B（探针阶段计数边界） |
| 全局可转化上限 3,945,720 B（= 峰值 − 次高阶段） | **−3,945,720 B** | **0 B——恰好用尽物理上限** |
| fix1 后全局峰值 = `circuit_synthesis` 86,184,6xx B | 86,184,614 B | 一致（+2 B 残差） |

即：本目标把可转化上限**一分不差地全部拿到了**。这同时验证了目标 a 之后确立的阈值方法论（先做阶段分解、取 `min(可移除量, 峰值 − 次高阶段)`）。

## 4. 时间守门（辅 3：三个臂集，`lazy=1` 固定，ABBA×3 轮）

| 臂集 | 批中位 A → B | 池化批中位变化 | 配对中位（B 更快/总数，符号检验 p） | 证明中位 MWU p | 漂移守门（A / B） | 敏感性（不弃首批） |
|---|---:|---:|---:|---:|---|---|
| spend 1t @ `0x1`（主守门） | 3,317.5 → 3,207.8 ms | **−3.31%** | −3.16%（5/5，p=0.0625） | 0.0010 | −2.3% / −2.2% | −3.35%（6/6，p=0.0312） |
| spend 8t @ `0xFFFF` | 717.6 → 694.9 ms | **−3.17%** | +1.11%（2/5，p=1.0） | 0.4652 | −2.0% / −13.1% | −0.32%（3/6，p=1.0） |
| output 1t @ `0x1` | 473.3 → 472.4 ms | **−0.20%** | −0.61%（3/5，p=1.0） | 0.3720 | −0.7% / −0.2% | −0.33%（4/6，p=0.6875） |

冻结判据是**池化批中位 ≤ +1%**，三臂全部通过（且均为负）。需要如实说明的两点：

1. **8t 臂的池化批中位（−3.17%）与配对视角（+1.11%，仅 2/5）方向不一致**。该臂代码路径逐字节不变，差异只能来自主机漂移：B 臂批中位从 794.9 漂到 690.5（−13.1%），敏感性分析（不弃首批）为 −0.32%（3/6，p=1.0）。结论按冻结口径给出（通过），但 8t 臂**不应**被引述为"本改动让 8 线程更快"。
2. 1t 主守门 −3.31% 超出预注册"≈略快"的预期量级。方向与机制（少两趟全量遍历 + 少一次整域分配/清零）一致，且敏感性分析稳健（不弃首批仍为 −3.35%、6/6 全 B 更快）；但端到端时间不是本目标的主指标，引用时应以"未退化且方向为负"表述，不应把 −3.31% 当作本目标的认证收益。

## 5. 结论

按冻结验收表，**目标 f 通过（PASS）**：机制在单线程路径上消除一个整域 scratch（4,194,304 B），阶段峰值下降 4.19 MB，`lazy=1` 配置全局峰值下降 3.95 MB（−4.38%），恰好用尽预注册计算的物理可转化上限；正确性门禁与时间守门全过。按预注册 §2 的范围声明与目标 a 的所有者决定惯例，**开关默认保持 `0`**：本目标只负责把天花板本身降下来并给出可转化上限，**组合收益（`lazy=1` + 本改动 = 103.06 → 86.18 MB，−16.88 MB / −16.4%）的正式验收是目标 g 的事**，默认值切换需随组合一并显式授权。

## 6. 口径修正（派生表一处，不影响判定）

`results/tables/sapling_qap_fft_fix_memory_20261018.csv` 的 `lazy0_peak_unchanged` 字段在提交 `1bc8bc7` 中的值为 `False`，系按"峰值**严格不变**（恰好 0 B）"的旧读法生成；冻结预注册的辅 4 判据是"**不上升**（≤ 0 B）"，−760 B 满足该判据。本提交按冻结判据重新生成该派生表（`lazy0_peak_unchanged=True`，由 `scripts/analyze_qap_fft_fix_experiment.py` 重跑复现，其余字段不变）。该修正**不改变任何判定结论**（两种读法下辅 4 均非"上升"，且主/辅 1/2/3 与该项无关）。

## 7. 实验要素

| 项 | 值 |
|---|---|
| 工程仓库 HEAD（数据产生时） | `1bc8bc7`（构建 09:49–09:50，运行 09:52–10:0x，提交 10:29；构建后无源码改动） |
| `spend_prover_smoke.exe` SHA-256 | `6b01cb764d38099f62997e1d182f34888fb3df4ffade105b8a5b78efdcdd946c` |
| `prove_memory_ledger.exe` SHA-256 | `a5efb982a1ab2cfe12e66f03ca4f48ee96e73b1992ee7e9f16de518e20a39e4f` |
| `fft_path_gate.exe` SHA-256 | `d70725464f85a5ca5c2156b4aa252ad47bda93a75c883029be4e372fcf2a0475` |
| Spend 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| Output 参数 SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 工具链 | rustc 1.98.1 (48a229cea 2026-09-01)，cargo 1.98.1 (797e8a9bc 2026-08-05) |
| 平台 | Windows 11，Intel i7-14700（8P+12E），32 GB RAM |
| 派生脚本 | `scripts/analyze_qap_fft_fix_experiment.py`（冻结统计：池化中位、配对 ABBA、精确符号检验、MWU、漂移守门） |
| 派生表 | `results/tables/sapling_qap_fft_fix_memory_20261018.csv`、`results/tables/sapling_qap_fft_fix_abba_20261018.csv` |

## 8. 复现步骤

```powershell
# 0) 构建（全量 bins）并记录哈希
cd experiments\prover-smoke
cargo --offline --locked build --release --bins

# 1) 正确性门禁（辅 2b）：同一确定性输入，两路径 digest 对照
$env:RAYON_NUM_THREADS='1'
$env:SAPLING_FFT_SERIAL_SINGLE_THREAD='0'; .\target\release\fft_path_gate.exe > ..\..\experiments\raw\logs\fft_path_gate_off_20261018.log
$env:SAPLING_FFT_SERIAL_SINGLE_THREAD='1'; .\target\release\fft_path_gate.exe > ..\..\experiments\raw\logs\fft_path_gate_on_20261018.log

# 2) 主指标 + 辅 1 + 辅 4：四组内存台账（1t @ 0x1，每臂 5 run）
#    {SAPLING_MSM_LAZY_RECODING} x {SAPLING_FFT_SERIAL_SINGLE_THREAD} = {0,1}^2
#    prove_memory_ledger.exe → sapling_prove_memory_ledger_qap_fft_fix_lazy{0,1}_fix{0,1}_noprobe_20261018.csv
#    阶段探针两臂（其 prove_peak_abs_bytes 列不可用，只看 stderr 的 G16_MEM_PHASE 行）：
$env:SAPLING_G16_MEM_PHASE_PROBE='1'   # 仅 lazy1_fix{0,1}

# 3) 端到端时间守门（辅 3）：同一二进制 + 开关，lazy 固定 1，ABBA x 3 轮
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\scripts\run_msm_signed_digit_campaign.ps1 -Prover spend  -Threads 1  -AffinityMask 0x1    -Orders ABBA,ABBA,BAAB -LabelPrefix qap_fft_fix_spend_1t  -SwitchVar SAPLING_FFT_SERIAL_SINGLE_THREAD
& .\scripts\run_msm_signed_digit_campaign.ps1 -Prover spend  -Threads 8  -AffinityMask 0xFFFF -Orders ABBA,ABBA,BAAB -LabelPrefix qap_fft_fix_spend_8t  -SwitchVar SAPLING_FFT_SERIAL_SINGLE_THREAD
& .\scripts\run_msm_signed_digit_campaign.ps1 -Prover output -Threads 1  -AffinityMask 0x1    -Orders ABBA,ABBA,BAAB -LabelPrefix qap_fft_fix_output_1t -SwitchVar SAPLING_FFT_SERIAL_SINGLE_THREAD

# 4) 分析与判定（不重跑实验，只读归档原始数据）
python scripts\analyze_qap_fft_fix_experiment.py
```

> 运行任何会追加 raw CSV 的程序前，先检查 batch ID 与输出路径；本战役所有批次的 batch ID、日志与 CSV 均已归档（见 §7 与预注册 §5）。

## 9. 边界与不外推声明

- 本目标**只对单线程生效**（`log_num_threads() == 0`）；多线程下四步法是必需的，其 scratch 总量已是一个域大小（理论最小值），本目标不声称降低多线程峰值（8t 臂的作用仅是守门）。
- 节省量 = 一个域大小缓冲：Spend（2^17）4.19 MB，Output（2^13）仅 262,144 B——Output 的绝对值收益小（辅 3 的 output 臂 −0.20% 与此一致）。
- 位等价性结论依赖"四步法在 `log_cpus=0` 时恒等"的逐行可核对事实，并以 12 例 digest 门禁 + 20/20 真实证明验证兜底。
- 在 shipped default（`lazy=0`）下，全局峰值仍由 H query 窗口化缓冲所在区间决定（103.06 MB），本目标**不改变**该值（辅 4 仅要求不上升）；−16.88 MB 的组合收益属目标 g。
- 所有时间均为对应批次、对应插桩/配置下的观测值；本报告不构成通用延迟保证。

---

*本报告为工程测量与受控优化验证记录。目标 f 的判定严格按预注册冻结阈值给出（通过）；开关默认值保持 `0`，默认值切换随组合收益（目标 g）另行显式授权。*
