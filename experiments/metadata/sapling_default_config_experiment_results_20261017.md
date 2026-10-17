# 实验记录：优化目标 e — 出厂默认线程/亲和性 vs 绑 P 核 + 8 线程（2026-10-17）

- **预声明（跑前冻结）**：`sapling_default_config_experiment_preregistration_20261017.md`
- **协议**：`sapling_optimization_validation_protocol_20261017.md`（阈值 ≥3%、ABBA 配对、漂移守门、留存模板）
- **性质**：配置/部署级（线程数与处理器亲和性），**零算法代码改动**
- **报告对应章节**：`docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md` §19
- **分析脚本**：`scripts/analyze_default_config_experiment.py`
- **派生表**：`results/tables/sapling_default_vs_pinned_config_20261017.csv`

---

## 1. 环境与可追溯性

| 项 | 值 |
|---|---|
| 主机 | i7-14700，LP0–15 = 8 个 P 核 ×HT，LP16–27 = 12 个 E 核，31.7 GiB，Windows 11 |
| Spend exe SHA-256 | `e5cedd7b9ac3c37a887d945faef9945b3f4830b96a6dcafec33d4b10cb7c72f0` |
| Output exe SHA-256 | `64056f71c89548f9419636ea4c870e48fdcdbab578af4caeeef54ede8d6e3adb` |
| `sapling-spend.params` SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| `sapling-output.params` SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 构建 | `cargo build --release --locked --offline`（插桩全部默认关闭） |
| 运行器 | `scripts/run_pinned_prover_campaign.ps1`（本次新增 `-Threads 0` = 不设 `RAYON_NUM_THREADS`；并新增超范围蒙版检查） |
| 机器状态 | **繁忙桌面**（Edge / msedgewebview2 / 微信 / QQ / WorkBuddy / Suiyun / Defender 等同时运行，瞬时 CPU 负载约 15%）。这是本次实验的主要限制，见 §6。 |

> **注意 exe 变更**：§15.1 冻结基线测于 `df0de411…`；本轮因新增（默认关闭的）插桩后重新构建，exe 变为 `e5cedd7b…`。§5 给出重建中性对照。

---

## 2. 条件与命令

| 代号 | 亲和性蒙版 | `RAYON_NUM_THREADS` | 说明 |
|---|---|---|---|
| **A** | `0`（不设） | 0（不设 ⇒ 28） | 出厂默认 |
| **B** | `0xFFFF` | 8 | 候选 |
| C | `0xFFFF` | 16 | 参照 |
| D | `0xFFFFFFF` | 0（不设 ⇒ 28） | 参照：隔离"是否绑核" |
| E | `0xFFFFFFF` | 8 | 参照：隔离"是否禁止 E 核" |

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'
$r = '.\scripts\run_pinned_prover_campaign.ps1'
$root = "D:\Research\zcash-sapling-engineering"

# 第一轮（预声明顺序 A(2) B(2) B(2) A(2) C(2) D(2) E(2)）
& $r -RepoRoot $root -Prover spend -Threads 0 -AffinityMasks 0          -Batches 2 -Label default_threads_unbound_20261017 -AllowDirtyWorktree
& $r -RepoRoot $root -Prover spend -Threads 8 -AffinityMasks 0xFFFF     -Batches 2 -Label pinned8_pcore_20261017         -AllowDirtyWorktree
& $r -RepoRoot $root -Prover spend -Threads 0 -AffinityMasks 0xFFFFFFF  -Batches 2 -Label default_threads_all28_20261017 -AllowDirtyWorktree
& $r -RepoRoot $root -Prover spend -Threads 8 -AffinityMasks 0xFFFFFFF  -Batches 2 -Label pinned8_all28_20261017         -AllowDirtyWorktree
& $r -RepoRoot $root -Prover spend -Threads 16 -AffinityMasks 0xFFFF    -Batches 2 -Label pinned16_pcore_20261017        -AllowDirtyWorktree

# 交错轮次（每轮内 A、B、C 背靠背；用 & 调用，勿用 -File 传数组）
for ($i = 1; $i -le 5; $i++) {
  & $r -RepoRoot $root -Prover spend -Threads 0  -AffinityMasks 0        -Batches 1 -Label abab_unbound_default_20261017  -AllowDirtyWorktree
  & $r -RepoRoot $root -Prover spend -Threads 8  -AffinityMasks 0xFFFF   -Batches 1 -Label abab_pinned8_pcore_20261017   -AllowDirtyWorktree
  & $r -RepoRoot $root -Prover spend -Threads 0  -AffinityMasks 0        -Batches 1 -Label abab2_unbound_default_20261017 -AllowDirtyWorktree
  & $r -RepoRoot $root -Prover spend -Threads 8  -AffinityMasks 0xFFFF   -Batches 1 -Label abab2_pinned8_pcore_20261017  -AllowDirtyWorktree
  & $r -RepoRoot $root -Prover spend -Threads 16 -AffinityMasks 0xFFFF   -Batches 1 -Label abab2_pinned16_pcore_20261017 -AllowDirtyWorktree
}

# Output 参照与重建中性对照
& $r -RepoRoot $root -Prover output -Threads 16 -AffinityMasks 0xFFFF    -Batches 2 -Label pinned16_pcore_20261017        -AllowDirtyWorktree
& $r -RepoRoot $root -Prover output -Threads 0  -AffinityMasks 0xFFFFFFF -Batches 2 -Label default_threads_all28_20261017 -AllowDirtyWorktree
& $r -RepoRoot $root -Prover output -Threads 8  -AffinityMasks 0xFFFFFFF -Batches 2 -Label pinned8_all28_20261017         -AllowDirtyWorktree
& $r -RepoRoot $root -Prover spend  -Threads 1  -AffinityMasks 0x1       -Batches 2 -Label rebuild_control_1t_lp0_20261017 -AllowDirtyWorktree
```

原始数据（**全部新增，未覆盖任何既有文件**）：

- `experiments/raw/csv/sapling_spend_prover_runs_{default_threads_unbound,pinned8_pcore,default_threads_all28,pinned8_all28,pinned16_pcore}_20261017.csv`（+ 各自 `_summary.csv`）
- `experiments/raw/csv/sapling_spend_prover_runs_{abab,abab2}_*_20261017.csv`
- `experiments/raw/csv/sapling_output_prover_runs_{default_threads_unbound,pinned8_pcore,pinned16_pcore,default_threads_all28,pinned8_all28}_20261017.csv`
- `experiments/raw/csv/sapling_spend_prover_runs_rebuild_control_1t_lp0_20261017.csv`
- 对应 `experiments/raw/logs/*.stdout.log` / `*.stderr.log`

正确性：**全部批次 100% `verified=true`、`proof_bytes=192`**（证明随机化，不要求字节相同）。

---

## 3. 结果 1：参数读取阶段被 E 核拖慢 1.8–1.9×（稳健、单变量）

Spend `params_read_validate_ms` 中位（同配置各批一致）：

| 蒙版是否允许 E 核 | 配置 | 读取中位 ms |
|---|---|---|
| **允许** | A 不绑核，默认 28 t | **55,159** |
| **允许** | D 全 28 LP，默认 28 t | **53,622** |
| **允许** | E 全 28 LP，8 t | **51,833** |
| 禁止 | B `0xFFFF`，8 t | **29,165** |
| 禁止 | C `0xFFFF`，16 t | **27,052** |
| 禁止 | C（第二轮交错）`0xFFFF`，16 t | **27,950** |
| 禁止 | 重建对照 `0x1`，1 t | **26,042** |

⇒ 允许 E 核：51.8–55.2 s（3 个条件）；只允许 P 核：26.0–29.2 s（4 个条件）。
**与线程数（1/8/16/28）无关，只与蒙版有关** ⇒ 单变量、比值 **1.8–1.9×**。

**机制（假设，未单独验证）**：该阶段主体串行；蒙版一旦允许 E 核，该线程会被放到 E 核上执行（与 §15.2 中"单线程 E 核 → 54 s / P 核 → 25.5 s"的特征完全一致）。P 核限制即消除该风险。

**端到端**：Spend 单进程批总时长（读取 + 准备 vk + 输入 + 5×prove + 5×verify）中位 **A 60,582 ms vs B 35,490 ms（1.71×）**。
⚠️ 参数读取在真实钱包中通常**每进程一次**，不是每次证明都付。

---

## 4. 结果 2：Spend prove 阶段（未认证）

交错轮次（每轮内 A/B/C 背靠背，共 10 对 A–B）：

| 轮 | 对 1 | 对 2 | 对 3 | 对 4 | 对 5 |
|---|---|---|---|---|---|
| round1 B−A (ms) | +319.1 | +205.0 | −187.0 | −196.4 | −253.1 |
| round2 B−A (ms) | +295.3 | −114.6 | −111.7 | +4.8 | −53.9 |
| round2 C−A (ms) | +169.2 | +4.3 | +89.3 | −23.2 | −83.4 |

- 配对中位差 **B−A = −82.8 ms（−8.5%）**；候选更快 **6/10** 对；**精确符号检验 p = 0.754**。
- 合并 10 批 × 5 次（n = 50/组）中位：**A 978.9 ms vs B 863.7 ms（−11.77%）**；**Mann–Whitney U = 902.0，p = 0.0164**。
- **漂移守门触发**：同轮内首→末 B **−44.5%**（round1）、**−26.9%**（round2）；A −5.3% / +1.1%（预声明上限 3%）。
- C−A（round2）：配对中位 **+4.3 ms（+0.4%）**，符号检验 p = 1.000 ⇒ **16 线程 vs 默认线程在 prove 上无可分辨差异**。

全量（含非交错批次）归一：

| 配置 | 亲和性 | 线程 | prove 中位 ms | 参数读取 ms | 批总 ms |
|---|---|---|---|---|---|
| A | 不设 | 28 | 1,029.0 | 55,159 | 60,582 |
| B | P 核 | 8 | 1,272.7（含两批被干扰的 1,350/1,346） | 29,165 | 35,490 |
| C | P 核 | 16 | 726.5（早批）/ 979.7（交错轮） | 27,052 | 30,777 |
| D | 全 28 LP | 28 | 987.0 | 53,622 | 58,789 |
| E | 全 28 LP | 8 | 1,171.8 | 51,833 | 57,778 |
| 对照 | `0x1` | 1 | 3,785.7 | 26,042 | 45,116 |

⇒ **预声明主标准（Spend prove 中位降幅 ≥3%）点估计满足（−8.5% / −11.8%）、MWU 显著（p=0.0164），但预声明的配对符号检验不显著（p=0.754）且漂移守门触发 ⇒ 记为"未认证"，不修改默认配置。**

---

## 5. 结果 3：Output 反对降低线程数（认证级）

| 配置 | 亲和性 | 线程 | Output prove 中位 ms |
|---|---|---|---|
| A | 不设 | 28 | **80.6** |
| D | 全 28 LP | 28 | 83.4 |
| B | P 核 | 8 | 98.2 |
| C | P 核 | 16 | 102.5 |
| E | 全 28 LP | 8 | 103.9 |

⇒ Output 由**线程数**（需约 28 个 worker）决定，**蒙版几乎无影响**；把线程数降到 8/16 使 Output 慢 **22–29%**。
预声明配对 **B vs A = +21.8%，MWU p = 0.0102**（显著负结果）。Output 参数读取仅约 1.8 s，故"结果 1"对 Output 无意义。

### 重建中性对照

今日二进制 1 t @ `0x1`：中位 **3,785.7 ms**（批中位 3,788.5 / 3,782.9，极差 3.77%）。
相对 §15.1 冻结暖态基线 3,685.6 ms 偏 **+2.72%**；相对 pooled 3,711.5 ms 偏 **+2.00%** ⇒ 在 1.3% 噪声底线 + 会话偏移之内，**新增（默认关闭）插桩未改变性能**。

---

## 6. 结论（按依据强度分级）

1. **【稳健，建议采纳】把证明进程亲和性限制到 P 核集合（`0xFFFF`）**：消除读取阶段落到 E 核，Spend 单进程省约 **25 s**（该阶段 1.8–1.9×），prove 阶段无实测退化；对 Output 中性。
2. **【已认证，反对】不要降低线程数**：Output 慢 **21.8%（p=0.010）**，Spend 无可认证收益。
3. **【未认证】** P 核限制对 **Spend prove 中位**的影响：点估计有利（−8.5% / −11.8%），但本机噪声 ±30–45% 使 ≥3% 阈值无法认证。
4. **【方法学，重要】** 本机为繁忙桌面，交互应用与 P 核竞争，使**绑核**配置的批间波动达 **30–45%**；"不绑核 + 满线程"反而更稳。**这恰好验证了 §18.2 的漂移守门与 §18.3 的阈值要求**：prove 阶段的优化结论必须在**安静主机**上重测。
5. **【流程成立】** 预声明 → 漂移守门 → 追加交错轮次 → 按预声明判定"未认证"，整个流程无需事后修改标准，且成功**证否了作者自己的 H1 的一部分**（H1 声称 B 端到端更优；实际对 Output 更差）。

## 7. 未做的对照（明确边界）

- 未测"`0xFFFF` + 默认 28 线程"（在 16 个 P 逻辑核上过订阅）。
- 未测"`0xFFFFFFF` + 16 线程"（Output 侧隔离）。
- 未在**安静主机**上重跑 prove 阶段主对比；这是任何证明阶段结论的前置条件。
- 未分离"参数读取"内部的并行/串行比例（机制为假设）。
