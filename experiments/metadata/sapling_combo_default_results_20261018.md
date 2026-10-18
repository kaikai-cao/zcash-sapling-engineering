# 结果：组合目标 g——「`lazy=1` + 单线程 FFT scratch 消除」组合验收与默认值切换（2026-10-18）

**判定：通过（PASS）——冻结验收表全部达标，默认值切换已执行并复验。** 主指标 `prove_peak_abs_bytes` 从当前 shipped default 臂 (lazy=0, fix=0) 到拟新默认臂 (lazy=1, fix=1) 下降 **16,878,888 B（−16.38%）**，超过冻结阈值（≥ 15,000,000 B）1.88 MB——这正是目标 a 单独未能达到的 15 MB 门槛；三个时间臂集全部在 1% 非退化预算内且方向为负（更快）；正确性 100%；辅 3 翻转后复验三项全过。**两处开关默认值已于本目标翻转（`SAPLING_MSM_LAZY_RECODING` 与 `SAPLING_FFT_SERIAL_SINGLE_THREAD` 均 0 → 1），全局 prove 峰值 103.06 → 86.18 MB。**

## 0. 判定摘要（对照冻结验收表）

| # | 指标 | 冻结阈值 | 实测 | 判定 |
|---|---|---:|---:|:--:|
| **主** | `prove_peak_abs_bytes`：(lazy=0,fix=0) → (lazy=1,fix=1) | 中位下降 ≥ 15,000,000 B | **−16,878,888 B（−16.38%）**：103,063,495 → 86,184,607 B | **MET** |
| 辅 1 | 正确性：全部证明 `verified=true`、`proof_bytes=192` | 100% | 台账 10/10 + 时间战役 360/360 + 翻转后 5/5 | **PASS** |
| 辅 2 | 时间非退化：三臂集池化批中位 | 每臂 ≤ +1% | −5.81% / −3.95% / −2.35%（均为负） | **PASS** |
| 辅 3 | 切换后复验（不设任何开关） | (i)(ii)(iii) 全过 | 12/12 digest 一致；+7 B；5/5 验证 | **PASS** |
| 辅 4 | 数据卫生：新 label 不覆盖 | 全新 | label 前缀 `combo_default_*`，无既有文件被覆盖 | **PASS** |

`PASS = 主 ∧ 辅1 ∧ 辅2 ∧ 辅3 ∧ 辅4 = True`。

## 1. 预注册与提交链

| 步骤 | 提交 | 内容 |
|---|---|---|
| 预注册（冻结，先于任何测量） | `9e7ee2e` | `experiments/metadata/sapling_combo_default_preregistration_20261018.md` |
| 代码/脚本 | `593999b` | `scripts/run_combo_default_campaign.ps1`（双开关 ABBA 驱动）、`scripts/analyze_combo_default_experiment.py`（判定） |
| 原始数据（战役） | `a0b6256` | 两臂台账 + 三臂集 ABBA×3 原始 CSV/日志（31 文件） |
| 代码（翻转） | `d4ed1df` | `vendor/bellman/src/domain.rs`、`vendor/bellman/src/multiexp.rs` 默认值 0 → 1 + 重编译 |
| 原始数据（辅 3） | `f0de404` | 翻转后门禁日志、台账、批次（8 文件） |
| 文档 | 本提交 | 本文档 + 派生表 + 报告 §23 + README §7.5 + 周报 §16 + 协议状态更新 |

验收表与回退条款未做任何修改。目标 f 的四臂台账虽已含本目标两个臂，但产生于本预注册之前，**判定未自借证据**：两臂在本目标下同会话重测（重测值与目标 f 归档值的偏差见 §3.2）。

## 2. 正确性（辅 1）

| 项 | 结果 |
|---|---|
| 内存台账两臂（每臂 1 次进程调用 = 5 prove） | 10/10 `verified=true`，`proof_bytes=192`，参数 SHA-256 不变 |
| 时间战役（3 臂集 × 6 批/臂 × 5 prove） | 360/360 `verified=true`（runner 逐批强制校验，任一失败即抛错整批作废） |
| 辅 3 (i) 门禁 | 12 例（log_n ∈ {10, 13, 17} × {fft, ifft, coset_fft, icoset_fft}）digest 逐位一致，0 失配 |
| 辅 3 (iii) 翻转后批次 | 5/5 `verified=true` |

> 门禁口径说明：辅 3 (i) 的「on」臂是**不设环境变量**（走翻转后的新默认 serial 路径），「off」臂是显式 `=0`（四步法路径）。两者覆盖同一对代码路径，与目标 f 的门禁（显式 0 vs 显式 1）等价。首轮捕获因 shell 重定向写成了 UTF-16LE 导致判定脚本读不到 digest（脚本本身无问题，数据无损），已用 UTF-8 重新捕获；门禁是确定性的，digest 不变。

## 3. 主指标与内存归因（主 / 辅 4）

### 3.1 对照台账（1t @ `0x1`，每臂 5 run，弃 run 1，run 2–5 取中位）

| 臂 | 开关 | `prove_peak_abs_bytes` | `live_before_prove` | `prove_ms`（台账口径） |
|---|---|---:|---:|---:|
| A = 当前 shipped default | lazy=0, fix=0 | 103,063,495 B | 68,729,865 B | 3,707.9 |
| B = 拟新默认 | lazy=1, fix=1 | **86,184,607 B** | 68,729,865 B | 3,402.0 |

- **主指标**：103,063,495 → 86,184,607 B = **−16,878,888 B（−16.38%）** ≥ 15,000,000 B ⇒ **MET**（超门槛 1,878,888 B）。
- 两臂 `live_before_prove` 逐位相同（68,729,865 B），差异全部发生在 prove 阶段内部。

### 3.2 与目标 a/f 归档值的交叉核对（本目标重测 vs 先期归档）

| 臂 | 目标 f 台账（`1bc8bc7` 二进制） | 本目标重测 | 偏差 |
|---|---:|---:|---:|
| (lazy=0, fix=0) | 103,063,734 B | 103,063,495 B | −239 B |
| (lazy=1, fix=1) | 86,184,614 B | 86,184,607 B | −7 B |

偏差在分配器粒度量级（目标 f 已实测同配置跨批噪声 ±760 B），两个独立批次互相印证。

### 3.3 阈值方法论的收尾

预注册时预期 −16,879,120 B（= 目标 f 实测的可转化上限），实测 −16,878,888 B，差 232 B。阈值仍按预先冻结的 15,000,000 B 判定（不随预期上调）——「阶段分解 + min(可移除量, 峰值−次高阶段)」方法论（目标 a 的教训、目标 f 的第一次正向命中）在本目标得到第二次确认：**组合把两个改动各自够不到的收益合起来，越过了 15 MB 门槛**。

## 4. 时间守门（辅 2：三臂集，ABBA×3，A = 当前默认 / B = 拟新默认）

| 臂集 | 批中位 A → B | 池化批中位变化 | 配对中位（B 更快/总数，符号检验 p） | 证明中位 MWU p | 漂移守门（A / B） | 敏感性（不弃首批） |
|---|---:|---:|---:|---:|---|---|
| spend 1t @ `0x1`（主守门） | 3,640.3 → 3,428.9 ms | **−5.81%** | −6.74%（5/5，p=0.0625） | <0.0001 | −1.9% / −1.9% | −6.87%（6/6，p=0.0312） |
| spend 8t @ `0xFFFF` | 772.5 → 742.0 ms | **−3.95%** | −4.16%（5/5，p=0.0625） | 0.0004 | −0.2% / +3.1% | −4.53%（6/6，p=0.0312） |
| output 1t @ `0x1` | 479.5 → 468.3 ms | **−2.35%** | −2.00%（5/5，p=0.0625） | <0.0001 | −0.4% / +0.6% | −2.18%（6/6，p=0.0312） |

冻结判据是**池化批中位 ≤ +1%**，三臂全部通过（且均为负）。需要如实说明的三点：

1. **时间不是本目标的认证主指标**。预注册的辅 2 只验收非退化；上述负值是实测事实（统计口径全部达标：1t/8t 超过协议 §4 的 3% 可检测性 bar，output −2.35% 未超过），但按冻结范围**不应**引述为「目标 g 认证了端到端加速 X%」——它们是默认值切换的附加证据，与目标 a（lazy 的时间方向）和目标 f（fix 的时间方向）的既有证据一致。
2. **8t 臂与目标 f 的 8t 臂形态不同**：目标 f 的 8t 臂代码路径逐字节不变、批中位漂移 −13.1%，只能归因主机漂移；本目标 8t 臂的收益来自 lazy 重编码（目标 a 实测 8t −8.52%），配对 5/5 + 敏感性 6/6（p=0.0312）方向一致，B 臂批内漂移仅 +3.1%，是真实的臂效应。
3. 同会话 A 臂（3,640.3 ms）是唯一合法的「before」对照基准；与 2026-10-17 冻结基线（3,685.6 ms）的跨天比较不作为结论依据（协议 §2）。

## 5. 辅 3：默认值翻转与切换后复验

翻转（`d4ed1df`）：`vendor/bellman/src/domain.rs` 的 `unwrap_or(false)` → `unwrap_or(true)`；`vendor/bellman/src/multiexp.rs` 的 `MSM_LAZY_RECODING_DEFAULT: i32 = 0` → `1`。两个环境变量仍可双向覆盖默认值。重编译后（cargo 1.98.1，release）在**不设任何开关环境变量**的条件下：

| 复验项 | 结果 |
|---|---|
| (i) `fft_path_gate`：显式 `=0`（四步法） vs 不设（新默认 serial） | 12/12 digest 逐位一致，0 失配 |
| (ii) `prove_memory_ledger` 峰值 | 86,184,614 B（run 2–5 中位），与拟新默认臂的 86,184,607 B 相差 **+7 B**，在 ±8,192 B 分配器粒度容差内 |
| (iii) spend 批次（1t@`0x1`，5 prove） | 5/5 `verified=true`，`proof_bytes=192` |

即：翻转后的默认行为与预注册验收的 B 臂**逐字节等价**，切换落地。

## 6. 结论

1. **【通过】** 目标 g 按冻结验收表六项全过：组合 prove 峰值 −16,878,888 B（−16.38%），越过目标 a 未达到的 15 MB 门槛；正确性与时间守门全过；辅 3 复验确认翻转后的默认行为与验收臂逐位一致。
2. **【默认值已切换】** `SAPLING_MSM_LAZY_RECODING` 与 `SAPLING_FFT_SERIAL_SINGLE_THREAD` 默认值均为 `1`（提交 `d4ed1df`）。shipped default 的 prove 峰值 **103.06 → 86.18 MB（−16.4%）**；单线程端到端时间同会话对照 −5.81%（附证，非本目标认证项）。
3. **【候选清单状态】** 协议 §7 候选中：a（未通过、归档）、b/e/f 已完成、**g（组合验收 + 默认切换）已完成**；c（B-G2 aux，Output 时间）与 d（赋值转换并行化，预期 <3%）仍未做。
4. **【下一步候选】** 内存维度上，翻转后的 86.18 MB 峰值由 `circuit_synthesis` 阶段决定（目标 f §3.2 已测），下一内存目标应先做阶段分解再立阈值；时间维度上，H query G1 MSM（候选 b 的有符号重编码已吃下部分）与 worker fallback 隔离仍是开放项。

## 7. 实验要素

| 项 | 值 |
|---|---|
| 战役二进制（测量时） | `spend_prover_smoke.exe` `6b01cb76…946c`；`prove_memory_ledger.exe` `a5efb982…9e4f`；`fft_path_gate.exe` `d7072546…0475`；`sapling-output-smoke.exe` `214fbbf8…bf52`（= 目标 f 构建，HEAD `593999b`，源码自 `1bc8bc7` 起未变） |
| 翻转后二进制（辅 3） | `spend_prover_smoke.exe` `c259d6a8…e825`；`prove_memory_ledger.exe` `d69be4f6…c5f2`；`fft_path_gate.exe` `12b77c2a…3269`；`sapling-output-smoke.exe` `a779c4e2…f1fa`（HEAD `d4ed1df`） |
| Spend / Output 参数 SHA-256 | `8e48ffd2…fc13` / `2f0ebbcb…b0e4`（全程不变） |
| 工具链 | rustc 1.98.1 (48a229cea 2026-09-01)，cargo 1.98.1 (797e8a9bc 2026-08-05) |
| 平台 | Windows 11，Intel i7-14700（8P+12E），32 GB RAM |
| 战役期间主机负载 | 每批记录于 driver 日志（0–24.3%） |
| 判定脚本 | `scripts/analyze_combo_default_experiment.py`（冻结统计：池化中位、配对 ABBA、精确符号检验、MWU、漂移守门、不弃首批敏感性） |
| 派生表 | `results/tables/sapling_combo_default_memory_20261018.csv`、`results/tables/sapling_combo_default_abba_20261018.csv` |

## 8. 复现步骤

```powershell
# 0) 预注册与脚本（先于任何测量，见提交 9e7ee2e / 593999b）

# 1) 主指标：两臂内存台账（1t@0x1，每臂 5 run，无阶段探针）
#    arm A: SAPLING_MSM_LAZY_RECODING=0  SAPLING_FFT_SERIAL_SINGLE_THREAD=0
#    arm B: SAPLING_MSM_LAZY_RECODING=1  SAPLING_FFT_SERIAL_SINGLE_THREAD=1
#    prove_memory_ledger.exe，SAPLING_PROVER_RUNS_CSV 指向
#    sapling_prove_memory_ledger_combo_default_{lazy0fix0,lazy1fix1}_20261018.csv

# 2) 辅 2：三臂集时间战役（同二进制、同会话、ABBA x 3 轮）
& .\scripts\run_combo_default_campaign.ps1 -Prover spend  -Threads 1 -AffinityMask 0x1    -LabelPrefix combo_default_spend_1t  -AllowDirtyWorktree
& .\scripts\run_combo_default_campaign.ps1 -Prover spend  -Threads 8 -AffinityMask 0xFFFF -LabelPrefix combo_default_spend_8t  -AllowDirtyWorktree
& .\scripts\run_combo_default_campaign.ps1 -Prover output -Threads 1 -AffinityMask 0x1    -LabelPrefix combo_default_output_1t -AllowDirtyWorktree

# 3) 判定（primary + aux 1 + aux 2）
python scripts\analyze_combo_default_experiment.py

# 4) 若 PASS：翻转两处默认值（domain.rs / multiexp.rs），重编译后辅 3 复验
cd experiments\prover-smoke; cargo --offline --locked build --release --bins
#    (i) fft_path_gate：显式 =0 与不设环境变量各跑一次，digest 对照
#    (ii) prove_memory_ledger 不设开关，峰值对照 B 臂（容差 +/-8,192 B）
#    (iii) run_pinned_prover_campaign.ps1 不设开关跑 1 批，5/5 验证
#    然后重跑判定脚本，aux 3 三项应全部为 True
```

> 运行任何会追加 raw CSV 的程序前，先检查 batch ID 与输出路径；本战役所有批次的 batch ID、日志与 CSV 均已归档（见 §7 与预注册 §5）。

## 9. 边界与不外推声明

- 主指标是**内存**（prove 峰值）；端到端时间收益（−5.81%/−3.95%/−2.35%）按预注册范围只作附证，不构成本目标的认证声明；output 臂 −2.35% 低于协议 §4 的 3% 可检测性 bar，单独不可分辨。
- 时间结论限于**同二进制、同会话、同一天**的 A/B 对照；不得与 2026-10-17 及更早的冻结基线直接相减。
- 翻转只改变两个开关的**默认值**，环境变量仍可双向覆盖；`SAPLING_FFT_SERIAL_SINGLE_THREAD=0` 仍可强制四步法路径（门禁依赖此）。
- 86.18 MB 峰值的构成已由目标 f §3.2 测定（`circuit_synthesis` 阶段的既存 live + 一个域大小缓冲）；本目标不声称进一步压低它。
- 所有数字均为对应批次、对应配置下的观测值；本报告不构成通用内存/延迟保证。

---

*本报告为工程测量与受控优化验证记录。目标 g 的判定严格按预注册（`9e7ee2e`）冻结阈值给出（通过）；默认值切换已随本目标一并显式授权并复验落地。*
