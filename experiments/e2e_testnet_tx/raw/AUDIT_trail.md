# 实验留痕审计（Plan 2 · Sapling + PCZT）

> 审计时间：2026-10-29 15:36（UTC+8）
> 审计对象：`D:\Research\zcash-sapling-engineering`（分支 `experiments/e2e-testnet-tx-harness`）+ `D:\Research\z3`（main）
> 结论摘要：**数据在磁盘上完整，但未进版本库；运行日志与失败轮次没有留痕。**

---

## 1. 现状总表

| 类别 | 状态 | 位置 |
|---|---|---|
| 原始测量数据（sapling 29 轮） | ✅ 完整 | `raw/sapling_*/run_*/rounds.csv` |
| 原始测量数据（pczt 24 轮） | ✅ 完整 | `raw/pczt_*/run_*/rounds.csv` |
| 内存采样（0.25 s 粒度） | ✅ 完整 | 各 run 的 `memory_timeseries.csv` |
| 环境指纹 | ⚠️ 部分 | `meta.json` 有 nproc / cpu_model / pids / pools_before |
| 正式报告 | ✅ 4 份 | `raw/sapling_e2e_v1/REPORT_sapling.md`、`FIT.md`、`raw/pczt_pool_v2/REPORT_v2.md`、`raw/pczt_pool_v1/REPORT.md` |
| 分析脚本 | ✅ 6 个 | `fit_sapling_e2e_model.py`、`bootstrap_sapling_ci.py`、`sapling_e2e_bench.py`、`make_manifest.py`、`pczt_bench_pool.py`、`analyze_sapling_cost.py` |
| 基础设施脚本（WSL 侧） | ⚠️ 在磁盘、未进版本库 | `D:\Research\z3\wsl\`（30+ 个 .sh/.py） |
| 链快照（可复现前置） | ⚠️ 在磁盘、未进版本库 | `D:\Research\z3\snapshots\z3_regtest_h32297_20261029_145710.tar.gz`（13.2 MB） |
| **哈希清单** | ✅ **本次新增** | `raw/MANIFEST.sha256`（65 条）+ `raw/MANIFEST.md` |
| **版本库追踪** | ❌ **全部未跟踪** | 见 §2 |
| **运行日志** | ❌ **不存在** | 无任何 `.log` 文件 |
| **失败轮次** | ❌ **未结构化** | `rounds.csv` 只记成功轮，error 列全空 |

---

## 2. 版本库状态（最大风险）

### 2.1 `zcash-sapling-engineering`（分支 `experiments/e2e-testnet-tx-harness`）

```
 M experiments/e2e_testnet_tx/e2e_tx_bench.py
?? experiments/e2e_testnet_tx/analyze_sapling_cost.py
?? experiments/e2e_testnet_tx/bootstrap_sapling_ci.py
?? experiments/e2e_testnet_tx/e2e_tx_bench_v2.py
?? experiments/e2e_testnet_tx/fit_sapling_e2e_model.py
?? experiments/e2e_testnet_tx/make_manifest.py
?? experiments/e2e_testnet_tx/pczt_bench_pool.py
?? experiments/e2e_testnet_tx/raw/            ← 全部数据与报告
?? experiments/e2e_testnet_tx/sapling_e2e_bench.py
?? experiments/raw/e2e_testnet_tx/            ← 10-28 的旧 memory 采样（历史遗留）
```

**9 项未跟踪**。也就是说：全部数据、全部报告、全部本轮脚本，都只存在于工作区。一次 `git clean -fdx`、一次误删、一次磁盘故障，就没有任何可恢复副本。

### 2.2 `z3`（main）

```
?? wsl/          ← 30+ 个实验脚本（挖块、快照、恢复、注资、PCZT 探针…）
?? snapshots/    ← 13.2 MB 链快照
?? identity_local.txt / mnemonic_age_local.age / real.age   ← 密钥材料，不应入库
```

`git ls-files wsl/` 返回 **0**：这些脚本从未被追踪过。

> ⚠️ `identity_local.txt`、`mnemonic_age_local.age`、`real.age` 是 regtest 钱包的密钥材料。它们**不应该**进版本库，但也**不应该只存在磁盘一份**——建议单独加密备份到仓库之外。本次审计未改动、未读取这三个文件。

---

## 3. 真正的缺口（连磁盘都没有）

| # | 缺口 | 影响 | 补救 |
|---|---|---|---|
| 1 | **无运行日志**。所有 bench 输出只打印到终端，未重定向落盘 | 想复核某轮异常（如 2857.7 ms 那个离群点）时，只有 `rounds.csv` 的数字，没有当时上下文 | 后续运行统一加 `2>&1 \| tee raw/<batch>/run_<ts>/run.log`；已有批次无法补 |
| 2 | **失败轮次未结构化**。`pczt_prove` 的 5 次 `MissingProofGenerationKey`、`gap limit at index 16`、`generate` 8 次假失败，都只有报告里的文字描述 | 报告 §1.2 的"版本缺陷"结论，证据链只能追到会话记录，项目内无独立证据文件 | 见 §4 的 `FAILURES.md`（**事后重建，已明确标注**） |
| 3 | **中间探针输出未落盘**。`z_viewtransaction` 完整 JSON、`pczt_probe.py` 的结构 dump、`pczt_rca.sh` 的源码搜索结果 | 报告里"`spends`/`outputs` 是顶层数组""`fee` 单位是 ZEC 浮点"这类结构断言，无原始样本 | 可用 `viewtx_probe.py` 对任一笔已确认交易重跑（需要链在跑） |
| 4 | **二进制指纹未记**。报告写 "Zebra 6.2.3 + zallet v0.1.0-beta.3"，但没有二进制 SHA256 | 若上游重新发布同版本号的构建，无法确认是否同一份 | WSL 内执行 `sha256sum $(command -v zebrad) $(command -v zallet)`，追加进 `meta.json` 或本文件 |
| 5 | 空运行目录 `raw/pczt_pool_v2/run_20261029_150604` | 已在 MANIFEST 标出，无数据损失 | 保留（作为"曾经跑过但立即中断"的记录）比删除更诚实 |
| 6 | `raw/sapling_smoke/run_20261029_151423` 缺 `summary_by_shape.csv` | 单轮 smoke，脚本早期版本不生成该文件 | 无需补救，`rounds.csv` 完整 |

---

## 4. 结论 → 证据 的追溯链

这是本审计的核心产出：任何一条报告结论，都能定位到具体文件。

| 报告结论 | 证据文件 | 可否离线复核 |
|---|---|---|
| `pipeline ≈ 589.9·S + 91.5·O + 424.2`，R²=0.9998 | `raw/sapling_e2e_v1/REPORT_sapling.md` §3.1 + `FIT.md` | ✅ `fit_sapling_e2e_model.py` |
| 等量替换价差 548 ms | `FIT.md` 检验 B 表 | ✅ 同上 |
| 判别实验 1826.5 ms | `raw/sapling_e2e_out9/run_20261029_152313/rounds.csv` | ✅ 原始数据 |
| spend 系数 95% CI [589, 602] | `bootstrap_sapling_ci.py` 输出 | ✅ B=4000 可复算 |
| ZIP 317 手续费 29/29 | 各 `rounds.csv` 的 `fee_zat` / `fee_measured_zat` 列 | ✅ |
| `tx_size = 352·S + 948·O + 130` | 各 `rounds.csv` 的 `tx_size` 列 | ✅ |
| PCZT prove 1415.2 ms 占 95.1% | `raw/pczt_pool_v2/REPORT_v2.md` + `run_20261029_150438/rounds.csv` | ✅ |
| 冷启动仅 +142 ms | `raw/pczt_cold_v1/run_20261029_150648/rounds.csv` | ✅ |
| padding dummy 与真实 spend 同价 | `run_20261029_150438/rounds.csv` 的 `signed` 列 | ✅ |
| 快照 12 秒可恢复至 32297 | `D:\Research\z3\snapshots\*.tar.gz` + `wsl/snapshot_restore.sh` | ⚠️ 需 WSL |
| `z_listtransactions` 的 memo bug | 无独立文件，仅报告文字 | ❌ 见缺口 #2/#3 |

最后一行是唯一"结论存在但证据不在项目内"的条目，已在报告 §4.1 标注为已知工具缺陷、不影响主数据链路。

---

## 5. 已完成的补救（本次）

1. **`raw/MANIFEST.sha256`** —— 65 条记录，sha256sum 兼容，`sha256sum -c` 可直接校验；已实测 65/65 通过、0 失败。
2. **`raw/MANIFEST.md`** —— 人读版：按类别统计、run 目录完整性表（含空目录标记）、逐文件 mtime + 哈希前缀、外部资产（13.2 MB 快照的完整 SHA256）单独成节。
3. **`make_manifest.py`** —— 清单生成器，可重复执行；已排除自身避免自指，支持 `--extra` 纳入仓库外资产。
4. 本文件 `AUDIT_trail.md`。

MANIFEST 的作用：现在报告里的每个数字都绑定到了具体文件的哈希。将来若有人改动某个 `rounds.csv`，`sha256sum -c` 会立刻暴露。

---

## 6. 建议的下一步（需你确认）

| 动作 | 说明 | 风险 |
|---|---|---|
| **A. 提交到实验分支** | 把 `raw/`（0.11 MB）、6 个脚本、4 份报告提交到 `experiments/e2e-testnet-tx-harness` | 无。数据很小（0.11 MB），完全适合入库 |
| **B. 处理 `experiments/raw/e2e_testnet_tx/`** | 10-28 的旧采样（26 KB），已被新批次取代 | 建议保留并在 README 标注"历史遗留"，不删 |
| **C. 把 `z3/wsl/` 脚本纳入版本控制** | 30+ 个脚本是实验基础设施，但 `z3` 是 main 分支 | 需你决定分支策略；`identity_local.txt` 等 3 个密钥文件必须同时加进 `.gitignore` |
| **D. 补齐二进制指纹** | 需要 WSL 执行一条命令 | 需要你在 WSL 里跑（我这侧 `wsl.exe` 被安全策略阻断） |
| **E. 后续运行统一落盘日志** | 在 bench 脚本里把 stdout 同时写 `run.log` | 改动小，我可以直接做 |

**D 的命令**（在 WSL 里执行，把输出贴回来我写进 AUDIT）：

```bash
sha256sum "$(command -v zebrad)" "$(command -v zallet)"; \
  "$(command -v zebrad)" --version 2>&1 | head -1; \
  rustc --version 2>/dev/null; uname -a
```

我倾向先做 **A + E**：A 把现有成果固化进版本库（一次性消除最大风险），E 保证以后不再产生新的"无日志"缺口。C 涉及分支策略，等你定。B 只需加一行标注。
