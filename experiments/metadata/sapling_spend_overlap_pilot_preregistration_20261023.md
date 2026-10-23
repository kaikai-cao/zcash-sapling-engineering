# 预注册（Stage 3 pilot）：独立 Spend 证明的批次吞吐重叠（2026-10-23）

> 性质：**pilot / go-no-go 筛选**。它不是正式 campaign，不改变任何默认值，也不把 pilot 数据并入此前的 Stage 1b / Stage 2。
> 本文件在 Stage 3 pilot 的正式测量之前冻结。实现提交后，runner、分析器、二进制、HEAD 和预注册 SHA-256 记录在 manifest 中；本文件不回写 SHA。
> 关联：Stage 2 已关闭 c=12 窗口线（`sapling_msm_c12_pilot_results_20261023.md`）；本 pilot 不再调整 MSM 窗口参数。

---

## 1. 背景与问题

Stage 2 的 4 批 pilot 没有通过稳健性门槛，c=12 窗口线关闭。Stage 1b 的 8t
Spend 阶段分解显示，单次证明 body 中约 **34%** 是 QAP/FFT 与电路合成等非 H-MSM
阶段（C0 中位：synthesis 118.7 ms + QAP/FFT 110.2 ms + scalar terms 1.8 ms，body
680.2 ms）。这些阶段在**单次证明内部**不能被 H-MSM 隐藏：

- H-MSM 的指数来自完整 QAP/FFT 结果，必须先完成 QAP/FFT 才能提交；
- L/A/B 等较小 MSM 已经与 H-MSM 在同一个 `create_proof` 内异步重叠；
- `proof_scalar_terms` 只有约 2 ms，装配等待是 H-MSM 的关键路径；
- 因此“把串行阶段塞进同一证明的 H-MSM 空档”没有可用的数据依赖。

仍可检验的是**独立证明之间**的重叠：当证明 A 的 H-MSM 正在使用 8 线程池时，
证明 B 的 synthesis/QAP 可以使用同一 Rayon 池的空闲 worker。这个方向改变的是
**批次吞吐**，不是单次证明延迟；并发 proof 的单次延迟会变长。

本 pilot 只回答一个 go/no-go 问题：

> **在固定的 8 个 P 核、`0x5555`、8 个 Rayon worker 下，让两个独立 Spend 证明
> 共享同一 Rayon 池并动态取任务，是否能把每证明的批处理墙钟时间降低至少 5%，
> 且两个并发批次都不慢于两个顺序批次？**

如果答案是否定，就关闭“独立证明重叠”线，不再为串行阶段投入正式 campaign。
如果答案肯定，才另写正式 Stage 3 预注册，扩展到更多批次和交易级验证；**pilot
本身不授权任何默认切换**。

## 2. 设计

### 2.1 臂

| 臂 | 进程内调度 | 说明 |
|---|---|---|
| `S0` | 顺序 | 一个 proof 完成后再开始下一个；当前 `spend_prover_smoke` 的形态 |
| `S1` | 2 个 worker 动态取任务 | 两个独立 proof 共享同一个 8 线程 Rayon 池；一个 worker 完成一个 proof 后立即取下一个 |

`S1` 的并发是在**进程内**通过 `std::thread::scope` 实现的；两个 worker 都调用
`SpendParameters::create_proof`，共享 Rayon 池，不创建第二个线程池。任务队列只
保护取 circuit 的短暂临界区，proof 生成本身不持锁。

`SAPLING_OVERLAP_ARM=seq|conc2` 只存在于新实验二进制
`spend_overlap_pilot`，不进入默认 prover 路径。生产 runner 和库默认值不变。

### 2.2 批次与顺序

- 8 个 Spend 批次，每臂 4 个；顺序固定为两轮 ABBA：
  **`S0, S1, S1, S0, S0, S1, S1, S0`**，以平衡系统漂移。
- 每个进程先做 **1 个 warmup proof**（不记录），再做 **8 个 measured proofs**。
- 批次墙钟 `batch_wall_ms` 从 warmup 之后、第一个 measured proof 提交前开始，
  到最后一个 proof 完成并验证后结束；包含 8 个 proof 的生成与验证，不包含参数
  读取、VK 准备和进程启动。
- 估计量：每个批次先算 `ms_per_proof = batch_wall_ms / 8`；对每臂 4 个批次取中位，
  得到 `m0` / `m1`；`R = m1 / m0`。
- 8 个 P 核，CPU 亲和掩码 `0x5555`；`RAYON_NUM_THREADS=8`；`SAPLING_PROFILE=0`。
- 批次之间间隔 5 秒；同一参数文件、同一二进制、同一工作树。
- 不运行 Output/交易；本 pilot 只测 Spend 的多证明吞吐。交易级混合证明是正式
  Stage 3 的事，不在本文件中判定。

### 2.3 唯一变量

`S0` 与 `S1` 只差进程内并发度（1 vs 2 个 proof worker）。以下变量在两类批次中
完全相同并逐批记录：

- `RAYON_NUM_THREADS=8`；
- 亲和掩码 `0x5555`；
- 参数文件 SHA-256、二进制 SHA-256、git HEAD、预注册 SHA-256；
- 所有 `SAPLING_MSM_*` / `SAPLING_FFT_*` 开关均未显式设置，保持当前默认。

runner 在启动前清空会改变策略的 `SAPLING_*` 环境变量，避免父进程污染。

## 3. 验收项（测量前冻结）

| ID | 检查 | 通过条件 |
|---|---|---|
| A1 | 批次数与唯一性 | 8/8 批，8 个唯一 batch ID，全部 `exit_code=0` |
| A2 | 每批 proof 行 | 每批 8 条 measured raw 行，proof index 0–7 各一次，8/8 `verified=true` |
| A3 | 臂与环境 | 每批 arm 与预注册顺序一致；`rayon_threads=8`；亲和掩码 `0x5555`；HEAD/预注册/二进制/参数哈希在 8 批中一致 |
| A4 | 原始数据保护 | 不覆盖任何既有 raw CSV/log；失败批次保留并记录；不复用旧 batch ID |
| A5 | 计时边界 | `batch_wall_ms` 只覆盖 warmup 之后的 8 个 measured proofs；warmup 不出现在 raw 行中 |
| A6 | 默认值不变 | 生产默认值、`spend_prover_smoke` 和正式 runner 未被修改；实验只通过新二进制和环境变量启用 |

若任一验收项失败，pilot 判为 **INVALID**，不进入 go/no-go 判断；保留现场，另开
修复轮次，不修改本预注册。

## 4. Go/no-go 规则（测量前冻结）

先计算：

- `m0` = `S0` 四个批次 `ms_per_proof` 的中位；
- `m1` = `S1` 四个批次 `ms_per_proof` 的中位；
- `R = m1 / m0`。

**GO（值得正式 Stage 3）当且仅当同时满足：**

1. A1–A6 全部通过；
2. `R ≤ 0.95`（并发臂每证明批处理墙钟至少低 5%）；
3. **四个 `S1` 批次的 `ms_per_proof` 都低于四个 `S0` 批次**（即
   `max(S1_batch_ms_per_proof) < min(S0_batch_ms_per_proof)`，无批次反转）。

**NO-GO（关闭独立证明重叠线）当且仅当：**

- 验收通过，但不满足第 2 或第 3 条。

若 `R ≤ 0.95` 但存在批次反转，仍判 **NO_GO**，不因“差一点”而重跑 pilot。
若需要重跑，必须写新的预注册并说明原因。

pilot 的 `R` 只是筛选统计量，不报告 90% CI，也不作为正式收益声明。正式 Stage 3
若启动，必须重新冻结样本量、交易级不回归规则和正式收益阈值。

## 5. 解释边界（必须与结果一起报告）

- 本 pilot 的判定量是 **batch throughput**，不是单次 proof 延迟；
- 并发臂的单次 proof 延迟预计变长，pilot 会记录并报告为描述性结果；
- 本 pilot **不能**支持“单个 Spend 证明变快”或“默认值应切换”的结论；
- 本 pilot 不测试 Output/交易；交易级混合证明只能由后续正式 Stage 3 判定；
- 若 GO，下一步是正式 Stage 3（更多批次 + 1 spend/2 outputs 交易级验证），
  仍不直接切换默认值。

## 6. 预期产物

- 本预注册：`experiments/metadata/sapling_spend_overlap_pilot_preregistration_20261023.md`。
- 实验二进制：`experiments/prover-smoke/src/bin/spend_overlap_pilot.rs`。
- runner：`scripts/run_spend_overlap_pilot.ps1`。
- 分析器：`scripts/analyze_spend_overlap_pilot.py`。
- 原始数据：`experiments/raw/csv/sapling_spend_overlap_pilot_<tag>.csv`、
  `experiments/raw/logs/*overlap_pilot_<tag>*`。
- manifest：`experiments/metadata/spend_overlap_pilot_manifest_<tag>.csv`。
- 结果记录：`experiments/metadata/sapling_spend_overlap_pilot_results_<tag>.md`。

## 7. 不做什么

- 不切换任何生产默认值；
- 不把批次吞吐收益写成单次证明延迟收益；
- 不把 pilot 的 8 批并入此前任何正式 campaign；
- 不对 Output/交易作任何结论；
- 不在看到 pilot 结果后修改本文件的阈值、方向或样本量。
