# 预注册：Groth16 prover 的 MSM 自适应窗口与窗口内切分（Stage 1，2026-10-22）

> 本文件在**写任何 Stage 1 代码、脚本、测量命令之前**冻结。Stage 0 只诊断了窗口尾部，没有实现优化；Stage 1 必须独立预注册、独立验收，不能把 Stage 0 的窗口扫描点直接当成收益。
>
> 预注册冻结后，§3 的策略、§4 的臂、§6 的验收项和 §7 的阈值与判定规则**不得修改**。若执行中发生偏差，只能在结果文档的“偏差”节追加说明，并保留原文件/原数据；不得覆盖原始 CSV、日志或失败批次。

---

## 1. 背景与可检验问题

Stage 0（[`sapling_msm_scaling_diagnosis_results_20261022.md`](sapling_msm_scaling_diagnosis_results_20261022.md)）在 8 个 P 核、`0x5555`、Spend H-query 上得到：

- 默认 `c=13` 时 `W=20`，8 个 worker 的理想尾部利用率 `20/(8×3)=83.3%`；
- `c=11` 时 `W=24`，正好 3 个满波，实际 prove 中位 **657.81 ms**，优于 `c=13` 的 **751.51 ms**；
- `c=10` 的 `ns/add` 最低，但 `W=26`，多出一个只有 2 个 worker 的尾波，实际 prove **676.93 ms**；
- Stage 0 的预注册映射（H2 部分支持 + H1 支持）把 **“自适应窗口 / 窗口内切分（`W mod P` 感知）”** 列为 Stage 1 第一优先。

Stage 1 只回答以下三个问题：

1. **Q1（主问题）**：在 8 个 P 核、`0x5555`、同一主机和参数下，按 `W(c) mod P` 与 bucket footprint 选择窗口，能否让 Spend prove 相对当前默认策略稳定降低至少 5%，并达到 Stage 0 `c=11` 的水平（以同 campaign 的 `c=11` 正对照为准；Stage 0 的 657.81 ms 只作历史参照）？
2. **Q2（机制问题）**：把每个窗口的指数范围切成 `s` 段、让 `W·s` 个任务填满 8 个 worker，能否单独解释窗口尾部的损失？在 `c=13, s=2` 和 `c=10, s=4` 两个固定臂上，是否至少有一个相对默认策略降低 5%？
3. **Q3（回归问题）**：自适应策略在 Output 和“1 spend + 2 outputs”真实交易构造上是否不回归（点估计 ≤ +3%，90% CI 上界 ≤ +5%）？

Stage 1 **不切换任何默认值**。环境变量未设置时，`bellman` 的行为必须与 Stage 0 的默认路径一致；所有实验臂都通过显式环境变量启用。

---

## 2. 冻结环境与数据边界

| 项 | 冻结值 |
|---|---|
| 主机 | Intel Core i7-14700，28 LP（LP0–15 = 8 P 核 × HT；LP16–27 = 12 E 核） |
| OS | Windows 11 Insider build 26220 |
| 工具链 | `rustc 1.98.1`，host `x86_64-pc-windows-gnu` |
| 参数目录 | `D:\Research\zcash-params` |
| Spend 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| Output 参数 SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 线程/亲和性 | `RAYON_NUM_THREADS=8`，`0x5555`（LP0,2,4,6,8,10,12,14） |
| 计时口径 | 暖态；每批丢弃 run 1；先取每批 warm 中位，再取 batch 中位的中位 |
| 批次间隔 | 每批结束后空闲 5 s |
| 证明数 | Spend/Output 每批 5 次 prove；交易每批 6 次构造 |
| 交易形状 | V5，1 spend + 2 outputs，`tx_bytes=2377` |

所有批次串行执行，启动后读回 `ProcessorAffinity` 并记录；读回不等于 `0x5555` 的批次作废。二进制、参数、预注册哈希和 git HEAD 必须在 manifest 中逐批记录。

---

## 3. 冻结策略（实现前定义）

### 3.1 自适应窗口（adaptive window）

仅对 balanced-signed recoding 生效。令：

```text
P       = rayon::current_num_threads()        // Stage 1 固定为 8
n       = exponent_count
c       ∈ {3,4,...,14}                        // 只测试 Stage 0 已覆盖的窗口附近；c>14 不进入
B(c)    = 2^(c-1)                             // signed bucket 数
W(c)    = 255 // c + 1                        // signed window 数
waves(c)= ceil(W(c) / P)
cost(c) = waves(c) * (n + 2*B(c))             // 每 worker 的窗口填充+归约模型
cap     = P * B(c) * sizeof(G) ≤ 16 MiB       // 并发 bucket 负载上限
```

在满足 `cap` 的候选中，选择 `cost(c)` 最小的 `c`；并列时选择较小的 `c`。若没有候选满足 `cap`，回退到现有 `best_signed_window` 的结果。`sizeof(G)` 使用 `std::mem::size_of::<G>()`，即 G1 为 144 B、G2 为 288 B。

该规则只使用 Stage 0 已冻结的“窗口数 + bucket 数 + 并发上限”，不读取任何 Stage 1 计时结果。

### 3.2 窗口内切分（intra-window split）

环境变量 `SAPLING_MSM_WINDOW_SPLIT=s`，`s ∈ {1,2,...,8}`，默认 `1`（关闭）。仅当 `s>1` 且 `n≥2` 时生效。

对每个窗口 `chunk ∈ [0,W)`，把指数范围 `[0,n)` 切成连续 `s` 段：

```text
base = n / s
rem  = n % s
start(k) = k*base + min(k, rem)
len(k)   = base + (1 if k < rem else 0)      // k = 0..s-1
```

每个任务 `(chunk,k)`：

1. 建立该窗口的 bucket 数组；
2. 只遍历全局指数下标 `[start(k), start(k)+len(k))`；
3. 对 density=false 的槽位不消费 base（保持既有 source 语义）；对 density=true 的槽位按 `resolve_slot` 处理；
4. 对该段做 bucket reduce，得到一个 `G` 元素。

所有段结果按窗口求和，再按现有方式乘以 `2^(c·chunk)` 并合并。该分解是**精确的**：`Σ_k Σ_{i∈seg_k} d_{i,chunk} B_i = Σ_i d_{i,chunk} B_i`，不改变群运算结果。

`SAPLING_MSM_WINDOW_SPLIT` 只影响任务划分，不改变 `c`、recoding 或最终权重。分段任务的 `chunk_count` 仍记为窗口数 `W`；另记 `task_count=W·s`。`s=1` 时必须走与 Stage 0 等价的单任务路径。

### 3.3 覆盖优先级与默认行为

```text
SAPLING_MSM_WINDOW_C          // 显式 c；优先级最高
SAPLING_MSM_ADAPTIVE_WINDOW=1 // 无显式 c 时启用 §3.1
否则                          // 现有 best_signed_window
SAPLING_MSM_WINDOW_SPLIT      // 独立；默认 1
```

未设置新环境变量时，`c` 和 `s` 必须与 Stage 0 默认路径一致。Stage 1 不改变 Sapling/Groth16 的默认参数、默认线程数或默认亲和性。

---

## 4. 实验臂、顺序与样本量

### 4.1 臂

| 臂 | Spend | Output | 交易 | 环境变量 |
|---|---|---|---|---|
| `C0` 默认对照 | ✓ | ✓ | ✓ | 不设 `ADAPTIVE`/`WINDOW_C`/`SPLIT`（即 `SPLIT=1`） |
| `C1` 自适应 | ✓ | ✓ | ✓ | `SAPLING_MSM_ADAPTIVE_WINDOW=1` |
| `C2` c13 切 2 段 | ✓ | — | — | `SAPLING_MSM_WINDOW_C=13`，`SAPLING_MSM_WINDOW_SPLIT=2` |
| `C3` c10 切 4 段 | ✓ | — | — | `SAPLING_MSM_WINDOW_C=10`，`SAPLING_MSM_WINDOW_SPLIT=4` |
| `C4` c11 正对照 | ✓ | ✓ | ✓ | `SAPLING_MSM_WINDOW_C=11`，`SPLIT=1` |

`C2`/`C3` 只用于 Spend 的机制检验：它们强制所有 query 使用同一个 `c`，因此不作为 Output/交易的策略回归臂。Output/交易的回归只比较 `C1`（和 `C4` 正对照）对 `C0`。

### 4.2 顺序

Spend 每块 10 批，按下列对称顺序；重复 2 块，共 20 批（每臂 4 批）：

```text
C0, C1, C2, C3, C4, C4, C3, C2, C1, C0
C0, C1, C2, C3, C4, C4, C3, C2, C1, C0
```

Output 和交易各 12 批，按下列对称顺序重复 2 块（每臂 4 批）：

```text
C0, C1, C4, C4, C1, C0
C0, C1, C4, C4, C1, C0
```

总计 **44 批**：Spend 20、Output 12、交易 12。先完成 Spend，再 Output，最后交易；每批一个独立进程，批间空闲 5 s。

### 4.3 样本量

- Spend：5 臂 × 4 批 × 5 proofs = 100 次 prove；丢弃每批 run 1 后 80 个 warm 样本，每臂 16 个。
- Output：3 臂 × 4 批 × 5 proofs = 60 次 prove；48 个 warm，每臂 16 个。
- 交易：3 臂 × 4 批 × 6 次构造 = 72 次；60 个 warm，每臂 20 个。

主分析单位是 batch（每批先取 warm 中位），不是单次 proof。

---

## 5. 测量与验收

### 5.1 验收项（冻结）

| 编号 | 验收内容 |
|---|---|
| A1 | Spend 每批 5 行，5/5 `verified=true`；每批恰有 40 条 MSM call、40 条 inner-stage、5 条 G16 stage |
| A2 | Output 每批 5 行，5/5 `verified=true` |
| A3 | 交易每批 6 行，6/6 `verified=true`，`tx_version=V5`，`spend_count=1`，`output_count=2`，`tx_bytes=2377` |
| A4 | 每批 `ProcessorAffinity` 读回精确等于 `0x5555`；`rayon_threads=8` |
| A5 | 每批只有一个 git HEAD；三个二进制和两个参数的 SHA-256 与 manifest 一致且全 campaign 不变 |
| A6 | 预注册 SHA-256 与 manifest/结果文档记录一致；tag 唯一 |
| A7 | 策略观测一致：`C1` 的 Spend H-query 观察到 `c=11`、`W=24`；`C2` 观察到 `c=13`、`W=20`、`split=2`、`task_count=40`；`C3` 观察到 `c=10`、`W=26`、`split=4`、`task_count=104`；`C4` 观察到 `c=11`、`W=24`、`split=1` |
| A8 | manifest 44 行，44 个唯一 batch ID；所有 invocation `exit_code=0`；无覆盖原始文件 |
| A9 | 失败/中止批次保留原文件并改名；不计入 44 批；结果文档记录原因 |
| A10 | 分析器可独立重跑，输出确定性表格/图；所有阈值与 §7 一致 |

A1–A10 全部 PASS 才进入策略结论；任何一项失败只报告“数据不足/执行失败”，不把部分数据当作 PASS。

### 5.2 预热与丢弃

沿用 Stage 0：每批第 1 个 run 丢弃，其余为 warm；不跨批合并 proof 样本。批次失败时不把已有行写入正式分析。

---

## 6. 估计量与统计

所有比较用**同 campaign、同批次日**的数据；不使用 Stage 0 的历史绝对值作为主比较。

- 每批指标：先对 warm 样本取中位；
- 臂指标：对 4 个 batch 中位取中位（median of batch medians）；
- 不确定性：以 batch 为 cluster，10,000 次 cluster bootstrap，报告 90% percentile CI；
- 比值：`R = 处理臂 / 对照臂`；`R<1` 表示处理更快；相对差 `Δ = 1-R`。

### 6.1 主检验（Spend 自适应）

```text
P1: R_C1/C0 = median(C1.prove_ms) / median(C0.prove_ms)
```

- **支持**：`R_C1/C0 ≤ 0.95` 且 90% CI 上界 `< 1.00`。
- **不支持**：点估计 `R_C1/C0 ≥ 0.98`，或 CI 下界 `>1.00`。
- **不确定**：其余情况。

### 6.2 机制检验（Spend 窗口内切分）

```text
P2: R_C2/C0 = median(C2.prove_ms) / median(C0.prove_ms)
P3: R_C3/C0 = median(C3.prove_ms) / median(C0.prove_ms)
```

每个分别按 P1 的阈值判定；`P2`/`P3` 是次要检验，不因多重比较改阈值，结论标注为“次要证据”。若 `P2` 或 `P3` 支持，说明该固定切分臂能解释尾部；若两者都不支持，则不能把“窗口内切分”写成已验证的 Stage 1 收益。

### 6.3 正对照与非劣效

```text
P4: R_C1/C4 = median(C1.prove_ms) / median(C4.prove_ms)
```

- **非劣效成立**：点估计 `≤1.02` 且 90% CI 上界 `≤1.05`。
- `C4` 是 `c=11` 正对照；若 `C1` 在 Spend 上确实选择 `c=11`，该检验主要验证“自适应选择没有引入实现开销”。

### 6.4 Output/交易回归

```text
P5: R_out = median(C1.prove_ms) / median(C0.prove_ms)        // Output
P6: R_tx  = median(C1.build_ms)  / median(C0.build_ms)        // 真实交易
```

- **不回归**：点估计 `≤1.03` 且 90% CI 上界 `≤1.05`。
- **强不回归**：点估计 `≤1.00` 且 90% CI 上界 `≤1.03`。
- 点估计 `>1.03` 或 CI 上界 `>1.05` 判为“回归/不确定”，不得写“Output/交易不受影响”。

### 6.5 历史参照（不是验收阈值）

Stage 0 的 `c=11` 657.81 ms 是历史点，Stage 1 的二进制、构建和 campaign 不同。结果文档报告 `C1` 的 Spend 中位是否 `≤657.81 ms`，仅作描述；**不作为 PASS/FAIL**。真正的“达到 c11 水平”用 P4（同 campaign 的 C4 正对照）判断。

### 6.6 判定组合

| P1 | P2/P3 | P5/P6 | Stage 1 结论 |
|---|---|---|---|
| 支持 | 任意 | 不回归 | 自适应窗口有证据；窗口内切分按 P2/P3 单独报告 |
| 支持 | 任意 | 回归/不确定 | 自适应窗口有 Spend 证据，但不能作为跨负载策略；需 Stage 2 重新设计 |
| 不支持 | 任一支持 | 不回归 | 只支持窗口内切分，不支持自适应选择 |
| 不支持 | 都不支持 | 任意 | 本 placement 下两条杠杆均未证实；不写优化器默认值 |
| 任意 | 任意 | A1–A10 失败 | 数据不足/执行失败；不作策略结论 |

Stage 1 **不**根据上表直接切换默认值；默认值切换需要单独的预注册和验收。

---

## 7. 代码与脚本边界

允许改动：

1. `vendor/bellman/src/multiexp.rs`：新增 §3 的 adaptive/split 实现、环境变量读取、stage profile 的 `split`/`task_count` 字段；默认关闭且 `s=1` 走等价路径。
2. `scripts/run_spend_combined_profile.ps1`：支持 adaptive/split 的期望 window/task 校验，记录 `split`/`task_count`；不改变 prove 口径。
3. 新增 `scripts/run_msm_adaptive_campaign.ps1`：Stage 1 编排器，按 §4 顺序设置环境变量、记录 manifest。
4. 新增 `scripts/analyze_msm_adaptive_experiment.py`：按 §6 口径重建表/图/验收。
5. 必要时新增 vendor 单元测试，验证 `s=1` 与旧行为一致、`s>1` 的群运算结果与 `s=1` 相同。

不允许：

- 修改 Stage 0 的原始 CSV、日志、manifest 或结果文档中的历史数字；
- 修改 Stage 0 预注册的阈值；
- 在 Stage 1 中改变默认 `c`、默认线程数或默认亲和性；
- 用未预注册的 `c`/`s` 组合替换失败的臂。

---

## 8. 执行与提交

1. 先提交本预注册文件，记录 SHA-256；
2. 再提交代码/脚本（单独 commit）；
3. 再提交原始数据、manifest、失败保留文件（单独 commit）；
4. 最后提交结果文档、表图、主报告/README/INDEX/weekly 更新（单独 commit）；
5. 通过分支 + PR 合并，不直接 push `main`。

结果文档必须逐项记录：偏差、失败、重跑、被排除的批次、与 Stage 0 的不一致，以及“哪些结论没有证据”。所有阈值沿用本文件；若必须偏离，先在结果文档写明原因，并保留原判定。

---

## 9. 预注册哈希

本文件提交后，使用 `Get-FileHash -Algorithm SHA256` 计算并记录到 manifest 与结果文档。此后任何修改都会使 Stage 1 campaign 失效，必须重新预注册。
