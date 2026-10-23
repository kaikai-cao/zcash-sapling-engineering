# 预注册（Stage 2 pilot）：真实 Spend H-query 的 c=12 vs c=13（2026-10-23）

> 性质：**pilot / go-no-go 筛选**。它不是正式 44 批 campaign，不改变默认值，也不把 pilot 数据并入正式结果。
> 本文件在 Stage 2 pilot 的任何测量之前冻结。实现提交后，脚本、二进制、HEAD 和预注册 SHA-256 记录在 manifest 中；本文件不回写 SHA。
> 关联：Stage 1b 否定结果 `sapling_msm_adaptive_stage1b_results_20261022.md`；Stage 1c 探索性机制复核 `sapling_msm_adaptive_stage1c_mechanism_note_20261023.md`。

---

## 1. 背景与问题

Stage 1b 的正式对照已经否定“c=11 门控 + 尾部切分”：

- `C1/C0 = 1.019`（90% CI 0.958–1.077），不支持 5% 收益；
- 同 campaign 的强制 c=11 正对照 `C4/C0 = 0.999`，没有复现 Stage 0 的 `c=11` 657.81 ms；
- 尾切 `C2 = 1.117`、`C3 = 1.027`，均不支持。

Stage 1c 的同进程 8t 机制复核没有发现 c=11 的内在优势，但两次顺序都是 **c=12 最低**：

| 顺序 | c=10 | c=11 | c=12 | c=13 |
|---|---:|---:|---:|---:|
| forward | 333.078 | 274.621 | **262.940** | 270.372 |
| reverse | 374.110 | 317.262 | **295.556** | 298.613 |

c=12 相对 c=13 只有 **−2.75% / −1.02%**，且该 bench 使用 synthetic fixture，不能直接作为默认切换依据。Stage 2 pilot 只回答一个 go/no-go 问题：

> **在真实 Sapling Spend 证明、8 个 P 核、`0x5555` 下，只把 `n ≥ 16384` 的 MSM 从默认窗口切到 c=12，是否出现至少 3% 的端到端 prove 改善，且两个 c=12 批次都优于两个 c=13 批次？**

如果答案是否定，就关闭窗口线，不再为 1–3% 的探索信号投入正式 campaign。如果答案是肯定，才另写正式预注册，用更多批次和 Output/交易不回归检查确认。

## 2. 设计

### 2.1 臂

| 臂 | 环境 | 说明 |
|---|---|---|
| `C0` | 不设置任何 `SAPLING_MSM_WINDOW_*` | 当前默认：signed recoding，按 `best_signed_window` 逐 query 选窗口 |
| `C1` | `SAPLING_MSM_WINDOW_C=12`，`SAPLING_MSM_WINDOW_MIN_N=16384` | 只对 `n ≥ 16384` 的 MSM 使用 c=12；小 MSM 保持默认 |

`SAPLING_MSM_WINDOW_MIN_N` 是本次新增的**显式实验门控**，默认 0（等价于旧行为）。不为它设置环境变量时，代码路径与 Stage 1b 相同。

### 2.2 批次与顺序

- 4 个 Spend 批次，每臂 2 个；顺序固定为 **ABBA：`C0, C1, C1, C0`**，以平衡系统漂移。
- 每批 5 个 proof；丢弃 run 1，取 run 2–5 的中位，再取两个批次中位的中位作为该臂的 pilot 点估计。
- 8 个 P 核，CPU 亲和掩码 `0x5555`；`RAYON_NUM_THREADS=8`。
- 批次之间间隔 5 秒；同一参数文件、同一二进制、同一工作树。
- 不运行 Output/交易；pilot 只做 Spend，避免把未验证的策略外推到小 MSM。

### 2.3 唯一变量

C0 与 C1 只差 `SAPLING_MSM_WINDOW_C=12` 和 `SAPLING_MSM_WINDOW_MIN_N=16384`。所有其他环境变量清空，尤其是：

- `SAPLING_MSM_ADAPTIVE_WINDOW`；
- `SAPLING_MSM_WINDOW_SPLIT`；
- `SAPLING_MSM_WINDOW_SPLIT_MODE`；
- `SAPLING_MSM_SIGNED_DIGITS`。

默认 signed recoding（未设置即启用）保持不变。

## 3. 验收项（测量前冻结）

| ID | 检查 | 通过条件 |
|---|---|---|
| A1 | 批次数与唯一性 | 4/4 批，4 个唯一 batch ID |
| A2 | 每批 proof | 每批 5 条 raw prove 行，5/5 verified，exit code 0 |
| A3 | 窗口断言 | C0 的 H-query 为默认 c=13；C1 的 H-query 为 c=12；C1 的 `n < 16384` query 仍为默认窗口 |
| A4 | 环境/亲和性/溯源 | 每批记录 HEAD、预注册 SHA、二进制 SHA、`RAYON_NUM_THREADS=8`、亲和掩码 `0x5555`；无旧 batch ID 混入 |
| A5 | 原始数据保护 | 不覆盖任何既有 raw CSV/log；失败批次保留并记录 |

若任一验收项失败，pilot 判为 **INVALID**，不进入 go/no-go 判断；保留现场，另开修复轮次，不修改本预注册。

## 4. Go/no-go 规则（测量前冻结）

先计算：

- `m0` = C0 两个批次中位的中位；
- `m1` = C1 两个批次中位的中位；
- `R = m1 / m0`。

**GO（值得正式 Stage 2）当且仅当同时满足：**

1. A1–A5 全部通过；
2. `R ≤ 0.97`（C1 至少快 3%）；
3. **两个 C1 批次的中位都低于两个 C0 批次的中位**（即 `max(C1_batch_medians) < min(C0_batch_medians)`，无批次反转）。

**NO-GO（关闭窗口线）当且仅当：**

- 验收通过，但不满足第 2 或第 3 条。

若 `R ≤ 0.97` 但存在批次反转，仍判 **NO-GO**，不因“差一点”而重跑 pilot；这是为了避免用重复 pilot 追噪声。若确实需要重跑，必须写新的预注册并说明原因。

pilot 的 `R` 只是筛选统计量，不报告 90% CI，也不作为正式收益声明。正式 Stage 2 若启动，必须重新冻结 P1 阈值、样本量和 Output/交易不回归规则。

## 5. 预期产物

- 本预注册：`experiments/metadata/sapling_msm_c12_pilot_preregistration_20261023.md`。
- runner：`scripts/run_msm_c12_pilot.ps1`。
- 预注册分析器：`scripts/analyze_msm_c12_pilot.py`。
- 原始数据：`experiments/raw/csv/*msm_c12_pilot_20261023*`、`experiments/raw/logs/*msm_c12_pilot_20261023*`。
- manifest：`experiments/metadata/msm_c12_pilot_manifest_20261023.csv`。
- 结果记录：`experiments/metadata/sapling_msm_c12_pilot_results_20261023.md`。

## 6. 不做什么

- 不切换任何生产默认值；
- 不把 c=12 说成已证明的优化；
- 不把 pilot 的 4 批并入 Stage 1b 或任何正式 44 批；
- 不对 Output/交易作任何结论；
- 不在看到 pilot 结果后修改本文件的阈值、方向或样本量。
