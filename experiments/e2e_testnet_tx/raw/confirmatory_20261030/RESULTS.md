# Sapling 端到端确认性实验 · 结果判定（2026-10-30）

> 本文件是预注册 `sapling_e2e_regtest_confirmatory_preregistration_20261030.md`
> §11 交付物 3「结果判定文档」。所有数值可由本目录 `rounds.csv` 重新生成（见末节复现命令）。

## 1. 执行摘要

| 项 | 值 |
|---|---|
| run 目录 | `raw/confirmatory_20261030/run_20261030_201124` |
| 模式 | `--mode confirm`（`dry_run=False`, `real_tx=True`） |
| 样本 | **50 轮 / 10 形态，每形态 5 次全成功（0 失败、0 重试）** |
| 失败分类 | 无（`failure_rows=0`, `sidecar_rows=0`, `mismatch_rows=0`） |
| 样本资格 | `meta_stage=run_end`，`rows_with_txid=50/50`，无 run 被中止 |
| 三个假设 | **H_A 接受 · H_B 接受（稳定）· H_C 接受** |

## 2. 环境与版本锚定

| 字段 | 值 |
|---|---|
| 环境 | WSL2 离线 regtest（非 Testnet） |
| 节点 | zebrad **6.2.3**，sha256 `baf0b2cd31110c7fe7c05809fd7323d07548489be78d31caeccc91e1469cc6a7`（183,943,408 B） |
| 钱包后端 | `zallet-zaino`（**测量实际执行者**），sha256 `e602e4a3d4e919c155b8f05dae29f0b9311631f167eaf25455166edf268208a7`（108,392,112 B） |
| 钱包 launcher | `zallet`（只做 dispatch，不参与测量），sha256 `523bf86a14cba2dfb1ea048c3a3d6ccc68bde0dbb92da60d44ce12568dea1c5a` |
| 快照 | `z3_regtest_h32297_20261029_145710.tar.gz` |
| 快照 SHA-256 | `ca35201887b8041b44c483ad258a718f4a74787c02c4ff9dbbb202857b09510c` |
| 恢复脚本 SHA-256 | `2df7cd8bd4890963d925711912aa280f944156319d2b6aa5fa2b53c35a720e11` |
| 恢复后链高 | **32297**（50/50 轮一致；`bestblockhash=60fc362b…`） |
| 可花费 Sapling note | **36**（DB 只读清单 + `z_getnotescount` 双校验一致） |
| Sapling 余额 | **11999980000 zat** |
| 代码版本 | `git_head=30e531b02fcfd52b5899c768f8965364284fb564` |
| 执行器 SHA-256 | `41f3a75d10f3258b05f09d837ef218a6bc9ee2a6e1a39f332e4b89a797c36459` |
| 策略 / 种子 | `FullPrivacy` / `20261030` |

> 每轮测量**前**均从同一快照恢复（恢复动作在 `do_one_attempt` 循环内部，非人工操作），
> 故 50 轮的链高、note 数、余额完全同源。

**二进制哈希的证据等级**（详见 `raw/ENV_binaries_confirm_20261030.txt`）。
`meta.json` 的 `binary_sha256` 为 `None`——执行时两个二进制都不在 PATH 上，自动采集失败。
上表三个哈希**不是** run 时刻由执行器写入的，而是事后补证，覆盖范围要分清：

| 覆盖 | 等级 | 依据 |
|---|---|---|
| 第 50 轮（末轮） | **进程级实测**（事后 26 分钟补采） | 恢复脚本每轮 kill 并重启节点，故末轮进程（zebrad pid 29511 / zallet-zaino pid 29815，20:41:11–18 启动）此后未被替换；其 `/proc/PID/exe` 哈希 = 磁盘哈希 |
| 第 1–49 轮 | **同文件推定** | 每轮重启均从同一路径加载；磁盘 mtime 停在 2026-10-29 09:32（早于 run 起始 34.7 小时），哈希与 10-29 pilot 采集逐位一致 |
| 全程逐轮进程级采样 | **未做到** | 执行器未逐轮采集 `/proc/PID/exe`，属已知限制 |

> 因此**不得**表述为「50 轮的二进制哈希已逐轮实测验证」；可表述为「末轮运行时实测，
> 全部 50 轮加载同一路径同一文件（mtime 与哈希未变），故版本可确定」。

## 3. 第一层：直接对照

每形态 5 次，pipeline 取中位数（完整表见 `FIT.md`）：

| (S,O) | proofs | n | pipeline 中位(ms) | min | max | tx_size(B) |
|---:|---:|---:|---:|---:|---:|---:|
| 1,2 | 3 | 5 | 1540.3 | 1528.7 | 1586.0 | 2378 |
| 1,9 | 10 | 5 | 2203.9 | 2143.4 | 2397.6 | 9014 |
| 2,2 | 4 | 5 | 2130.6 | 2015.6 | 2277.5 | 2730 |
| 3,2 | 5 | 5 | 2807.3 | 2770.3 | 2814.3 | 3082 |
| 3,3 | 6 | 5 | 2825.9 | 2696.6 | 2953.5 | 4030 |
| 4,2 | 6 | 5 | 3458.8 | 3388.7 | 3596.8 | 3434 |
| 4,3 | 7 | 5 | 3548.8 | 3483.7 | 3595.8 | 4382 |
| 7,2 | 9 | 5 | 5184.1 | 5147.9 | 5382.5 | 4490 |
| 10,2 | 12 | 5 | 7306.2 | 7279.0 | 7590.2 | 5546 |
| 17,2 | 19 | 5 | 11786.2 | 11741.2 | 11825.8 | 8010 |

关键对照：

- **output 边际**：(3,2)→(3,3) = +18.6 ms；(4,2)→(4,3) = +90.0 ms。两处均为正但量级差异大，
  单点估计不稳定，故下文的双变量模型与 H_B 才是有判别力的证据。
- **等证明数**（6 个证明）：(3,3)=2825.9 vs (4,2)=3458.8，差 **632.9 ms**。
  证明个数相同而耗时显著不同 → **「按证明个数计费」被直接否证**。
- **ZIP 317 手续费交叉验证**：`fee = 5000 × max(spends, outputs)` 吻合 **50/50** 轮。
- **字节数解析式**：`tx_size = 352·spends + 948·outputs + 130`，最大残差 **0 B**。

## 4. 第二层：三模型重估（confirmatory 数据）

| 模型 | 形式 | 系数 | R² | RMSE(ms) | LOO-RMSE(ms) |
|---|---|---|---:|---:|---:|
| M1 | a·proofs + b | 614.3 ms/proof + −697.0 ms | 0.8592 | 1114.6 | 1490.1 |
| M2 | a·spends + b | 626.7 ms/spend + 1020.3 ms（output 免费） | 0.9952 | 205.9 | 275.0 |
| M3 | a·spends + c·outputs + b | **641.5 ms/spend + 101.0 ms/output + 650.5 ms** | **0.9996** | **59.9** | **83.3** |

加权（按形态 n）后 M3 系数不变，结论不受采样不均衡影响。

**成本结构**：每 Spend ≈ **641.5 ms**，每 Output ≈ **101.0 ms**，固定开销 ≈ **650.5 ms**，
Spend/Output 比值 ≈ **6.35 : 1**。

字节与算力必须分开建模：spend 352 B / 641.5 ms（1.82 ms/B），
output 948 B / 101.0 ms（0.106 ms/B）——output 体积是 spend 的 2.7 倍，
时间却只有其约 1/6.4。

## 5. 第三层：假设判定（按 §9 冻结判据）

### H_A：Spend 与 Output 单位成本不相等 —— **接受**

- 点估计 Δ = a_S − c_O = **540.57 ms**
- Bootstrap（B=4000，seed=20261030，形态内重采样，百分位法）
  95% CI = **[513.11, 552.96] ms**
- 判据「CI 下界严格 > 0」→ **满足**
- 附带：比值 a_S/c_O 的 95% CI = [5.52, 7.21]，远离 1（不声称等价于两系数区间不重叠）

### H_B：等证明数下 (4,2) 与 (3,3) 耗时存在稳定差异 —— **接受（稳定）**

- (4,2) 中位 3458.8 ms，(3,3) 中位 2825.9 ms，点估计差 **+632.90 ms**
- Bootstrap 95% CI = **[483.10, 783.20] ms**，**不含 0**，点估计同号
- 量级 |633| 落在预注册「稳定」区间 **[300, 800] ms** 内
- 判定：**接受 H_B，且量级稳定**

### H_C：M3 相对 M1 提供实质增量信息 —— **接受**

- LOO-RMSE：M1 = 1490.12 ms，M2 = 275.04 ms，M3 = **83.31 ms**
- M3 相对 M1 相对下降 **94.4%**（判据 ≥10%），绝对差 **1406.8 ms**（判据 ≥20 ms）
- M3 (83.31) **< M2 (275.04)**（Output 项确有增量信息）
- 判定：**接受 H_C**

## 6. 结论强度与外推边界

**获重复支持的结论**（本轮 confirmatory 数据，预注册判据全部满足）：

1. Sapling 端到端构造耗时可被 `a·spends + c·outputs + b` 精确刻画（R²=0.9996，LOO RMSE 83 ms）。
2. Spend 与 Output 单位成本显著不等，约 **6.35:1**（H_A）。
3. 等证明数形态之间耗时存在稳定且可量化的差异（H_B，633 ms 量级）。
4. 「按证明个数计费」这一常见简化被直接否证（M1 LOO 误差为 M3 的 17.9 倍）。

**必须声明的限制**：

- 环境为 **WSL2 离线 regtest + Zallet Beta**，相对成本比的可迁移性**尚未验证**，
  不得外推至主网或其它钱包版本。
- 单机单次会话测量，`sync` 项（15.0–21.8 s）占比很大，属环境特定开销。
- 每形态 n=5，形态级 bootstrap 区间较宽（output 系数形态级 CI 为 [32.1, 336.9]）；
  轮级 CI 更紧但依赖采样结构假设。
- `mismatch` 类（`form_mismatch`/`fee_mismatch`）本轮**出现 0 次**，无可报告条目。
- **样本顺序为「形态块随机化」，与预注册 §6 的「逐次随机」不完全一致**（`DEVIATIONS.md §6`）。
  探索性敏感性诊断（`ORDER_SENSITIVITY.txt`，轮次级，非预注册分析）：
  Δ = a_S − c_O 由 540.20 → **528.36 ms**（−2.2%，仍远大于 0）；`c_O` 由 101.52 →
  **111.48 ms**（**+9.8%**），顺序项本身约 +17.8 ms/块。故「output 边际 101.0 ms」
  应作**区间量**引用（±10% 量级的顺序敏感），不宜当精确点值；
  H_A / H_B / H_C 三条判定不受影响。
- `rounds.csv` **未记录逐轮墙钟时间戳**，只有 `round` 序号，故顺序效应只能用序号
  作时间代理，无法做真实 drift 分析。

## 7. 交付物与复现

| 文件 | 内容 |
|---|---|
| `run_20261030_201124/rounds.csv` | 50 轮 × 36 列原始测量 |
| `run_20261030_201124/meta.json` | 版本、快照、策略、种子、失败计数、样本资格 |
| `run_20261030_201124/summary_by_shape.csv` | 每形态尝试/成功/匹配计数、underpowered |
| `run_20261030_201124/memory_timeseries.csv` | 内存时间序列 |
| `FIT.md` | 三模型拟合与三层分析报告（由 CSV 生成） |
| `RESULTS.md` | 本文件：结果判定 |
| `ORDER_SENSITIVITY.txt` | 顺序敏感性诊断输出（探索性，非预注册分析；脚本 `order_sensitivity.py`） |
| `run_20261030_201124/run.log` | 执行日志（**本地排除**，`**/run_*/run.log`；不进 `MANIFEST.sha256`） |

证据清单分两份（2026-10-30 审计后拆分）：

| 清单 | 覆盖 | 校验方式 |
|---|---|---|
| `raw/MANIFEST.sha256` | **只含 git 跟踪文件**，干净克隆 100% 可校验 | `cd experiments/e2e_testnet_tx && sha256sum -c raw/MANIFEST.sha256` |
| `raw/MANIFEST.local-excluded.sha256` | 本地存在但有意不入库的 14 个文件（钱包库副本、`run.log`、诊断 JSON），**本地证据** | `sha256sum -c raw/MANIFEST.local-excluded.sha256`（仅本工作区有效） |

复现命令（在工作目录 `experiments/e2e_testnet_tx/` 下）：

```bash
# 1) 拟合报告（仅正式数据：_feasibility_gate 自动排除；--require-match 排除无 form/fee 列的试点）
python3 fit_sapling_e2e_model.py --raw-dir raw/confirmatory_20261030 --require-match --md raw/confirmatory_20261030/FIT.md

# 2) 系数与比值 bootstrap（B=4000, seed=20261030）
python3 bootstrap_sapling_ci.py --raw-dir raw/confirmatory_20261030 --B 4000 --seed 20261030

# 3) H_A / H_B / H_C 判据（输入已固定到唯一正式 run，且要求 txid ∧ form_match ∧ fee_match）
python3 h_ab_bootstrap.py

# 4) 顺序敏感性诊断（探索性；写 ORDER_SENSITIVITY.txt）
python3 order_sensitivity.py > raw/confirmatory_20261030/ORDER_SENSITIVITY.txt
```

依赖：Python 3.13 + NumPy（分析与 bootstrap 脚本需要；钉版本见
`experiments/e2e_testnet_tx/requirements-analysis.txt`）。`confirmatory_bench.py`
与 `failure_class_selftest.py` 只用标准库，不依赖 NumPy。

> 重跑实验本身：`python3 confirmatory_bench.py --mode confirm`
> （每轮前自动从冻结快照恢复；需 WSL 内 zebrad/zallet-zaino 可用）。
