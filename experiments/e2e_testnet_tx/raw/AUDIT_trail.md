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
| 环境指纹 | ✅ 完整（15:44 补齐二进制哈希） | `meta.json` 有 nproc / cpu_model / pids / pools_before；`raw/ENV_binaries.txt` 有 3 个二进制的 SHA256 |
| 正式报告 | ✅ 4 份 | `raw/sapling_e2e_v1/REPORT_sapling.md`、`FIT.md`、`raw/pczt_pool_v2/REPORT_v2.md`、`raw/pczt_pool_v1/REPORT.md` |
| 分析脚本 | ✅ 6 个 | `fit_sapling_e2e_model.py`、`bootstrap_sapling_ci.py`、`sapling_e2e_bench.py`、`make_manifest.py`、`pczt_bench_pool.py`、`analyze_sapling_cost.py` |
| 基础设施脚本（WSL 侧） | ⚠️ 在磁盘、未进版本库 | `D:\Research\z3\wsl\`（30+ 个 .sh/.py） |
| 链快照（可复现前置） | ⚠️ 在磁盘、未进版本库 | `D:\Research\z3\snapshots\z3_regtest_h32297_20261029_145710.tar.gz`（13.2 MB） |
| **哈希清单** | ✅ **15:36 新增** | `raw/MANIFEST.sha256`（65 条）+ `raw/MANIFEST.md` |
| **版本库追踪** | ✅ **15:38 已入库**（`477216a`） | 见 §2.3 |
| **运行日志** | ⚠️ 已有轮次缺失，新运行自动落盘 | 见缺口 #1 |
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

### 2.3 已解除（2026-10-29 15:38 起）

上述 `zcash-sapling-engineering` 的 9 项未跟踪已全部入库，两个提交：

| commit | 内容 | 文件数 |
|---|---|---:|
| `477216a` | 5 批原始数据 + 4 份报告 + 6 个分析脚本 + 哈希清单 + `.gitattributes` | 77 |
| `71cc965` | `sapling_e2e_bench.py` 内置 `tee_stdio()`，run 目录建好后即写 `run.log` | 2 |

**入库时发现并修掉一个会让留痕直接失效的坑**：仓库 `core.autocrlf=true`，而 `raw/` 下数据是 CRLF、`MANIFEST.sha256` 是 LF。若直接提交，git 会改写行结束符 → 哈希清单交付即失效。已加 `.gitattributes` 对 `raw/**` 禁用文本转换（`-text`），并实测**从 git 对象库读回的 65 个文件字节哈希与清单逐一相同，0 失败**。这一条比清单本身更关键：没有它，清单只是看起来对。

§2.1 / §2.2 保留为审计时点的历史快照，不再代表当前状态。`z3` 侧（`wsl/`、`snapshots/`）仍未纳管，见 §6-C。

---

## 3. 真正的缺口（连磁盘都没有）

| # | 缺口 | 影响 | 补救 |
|---|---|---|---|
| 1 | ~~**无运行日志**~~ **已在脚本层修复**（2026-10-29 15:40）。此前所有 bench 输出只打印到终端 | 想复核某轮异常（如 2857.7 ms 那个离群点）时，只有 `rounds.csv` 的数字，没有当时上下文 | `sapling_e2e_bench.py` 内置 `tee_stdio()`：run 目录建好后即把 stdout/stderr 同时写入 `run.log`，并记录 `[argv]`。**已有的 24 轮无法补日志** |
| 2 | ~~**失败轮次未结构化**~~ **已补（16:02）**。原状态：`pczt_prove` 的 5 次 `MissingProofGenerationKey`、`gap limit at index 16`、`generate` 8 次假失败，都只有报告里的文字描述 | 报告 §1.2 的"版本缺陷"结论，证据链只能追到会话记录，项目内无独立证据文件 | ✅ `raw/FAILURES.md`（**事后重建，逐条标注证据强度 A/B/C**，12 条） |
| 3 | **中间探针输出未落盘**。`z_viewtransaction` 完整 JSON、`pczt_probe.py` 的结构 dump、`pczt_rca.sh` 的源码搜索结果 | 报告里"`spends`/`outputs` 是顶层数组""`fee` 单位是 ZEC 浮点"这类结构断言，无原始样本 | 可用 `viewtx_probe.py` 对任一笔已确认交易重跑（需要链在跑） |
| 4 | ~~**二进制指纹未记**~~ **已于 15:44 闭合**。报告写 "Zebra 6.2.3 + zallet v0.1.0-beta.3"，原先没有 SHA256 | 若上游重新发布同版本号的构建，无法确认是否同一份 | ✅ 已采集，见 §5.2 + `raw/ENV_binaries.txt`；采集脚本 `z3/wsl/bin_fingerprint.sh` |
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
| `z_listtransactions` 的 memo bug | `raw/FAILURES.md` F6（证据等级 C：仅会话记录） | ⚠️ 可重跑 `viewtx_probe.py` 补实测，需链在跑 |

最后一行是唯一"结论存在但证据不在项目内"的条目，已在报告 §4.1 标注为已知工具缺陷、不影响主数据链路。

---

## 5. 已完成的补救（本次）

1. **`raw/MANIFEST.sha256`** —— 66 条记录（后随文件增补重生成），sha256sum 兼容，`sha256sum -c` 可直接校验；已实测 66/66 通过（并从远端对象库回读复核）、0 失败。
2. **`raw/MANIFEST.md`** —— 人读版：按类别统计、run 目录完整性表（含空目录标记）、逐文件 mtime + 哈希前缀、外部资产（13.2 MB 快照的完整 SHA256）单独成节。
3. **`make_manifest.py`** —— 清单生成器，可重复执行；已排除自身避免自指，支持 `--extra` 纳入仓库外资产。
4. 本文件 `AUDIT_trail.md`。
5. **提交入库**（`477216a` / `71cc965`）——见 §2.3。
6. **`tee_stdio()`**（缺口 #1）—— bench 每次运行自动写 `run.log`。

MANIFEST 的作用：现在报告里的每个数字都绑定到了具体文件的哈希。将来若有人改动某个 `rounds.csv`，`sha256sum -c` 会立刻暴露。

### 5.1 后续补充（16:02）

| 文件 | 作用 |
|---|---|
| `raw/FAILURES.md` | 12 条失败/异常的结构化重建，逐条标证据强度 A/B/C，含 3 条已纠正的分析错误（冷启动误归因、M1 负截距、陈旧 tip） |
| `DEVIATIONS.md`（上一级目录） | 方案偏离记录：5 条偏离 + **预注册从未创建**的声明与影响评估，区分确认性/探索性分析 |
| `README_runbook.md` | 加状态横幅：原 Testnet+PCZT 方案已废弃，三处失效表述逐条指向 `DEVIATIONS.md`；修正指向不存在预注册文件的死链 |

补这三个文件的原因：**仓库里原先同时存在两套互相矛盾的描述**——runbook 说"全程 Testnet、Regtest 不可用"，
而全部数据都是 Regtest；AUDIT 又引用了一个从未创建的 `FAILURES.md`。这类自相矛盾比缺少文档更危险，
因为它让人无法判断哪份可信。

### 5.2 二进制指纹（缺口 #4 已闭合）

采集时间 2026-10-29 15:44:19（UTC+8），WSL2 kernel `6.18.54.1-microsoft-standard-WSL2`，host `DESKTOP-GMELEIR`。

| 角色 | 文件 | 字节 | SHA256 | 版本 |
|---|---|---:|---|---|
| 链节点 | `~/z3-regtest/bin/zebrad` | 183,943,408 | `baf0b2cd31110c7f…69cc6a7` | zebrad 6.2.3 |
| 钱包 launcher | `~/z3-regtest/bin/zallet` | 4,956,560 | `523bf86a14cba2df…68dea1c5a` | —（仅 dispatcher） |
| 钱包后端（**实际测量对象**） | `~/z3-regtest/bin/zallet-zaino` | 108,392,112 | `e602e4a3d4e919c1…268208a7` | zallet 0.1.0-beta.3 |

完整 64 位哈希、mtime、glibc 版本见 `raw/ENV_binaries.txt`。

**采集过程中查明的两件事：**

1. **`zallet` 不是被测量的进程。** 4.9 MB 的 `zallet` 只是 launcher，真正跑的是 pid 239967 的 `zallet-zaino`（108 MB）。launcher 的 `--version` 报 `failed to run the backend binary 'zallet-zaino'…`，是因为它按"backend binary next to itself"的规则去找 `zallet-zebra`——本部署只装了 zaino 后端。**版本声明必须绑定 `zallet-zaino` 的哈希**；只记 launcher 的哈希无法证明真正参与 prove 的那份二进制。
2. **`command -v` 在 WSL 里返回空**（两者都不在 PATH）。首轮采集因此把两个空字符串传给了 `sha256sum`，报 `No such file or directory` ×2 + `Command '' not found`。改用 `/proc/PID/exe` 读取真实可执行文件才成功——副产品是这条路径比 PATH 更权威：它直接指向**当时在跑的那份文件**。

**时序校验**：三个二进制的 mtime 均为 09:32（部署时刻），首批 sapling 测量起于 15:17，期间未重新部署 → 本指纹覆盖全部 29 轮 sapling + 24 轮 pczt。

---

## 6. 建议的下一步（需你确认）

| 动作 | 状态 | 说明 |
|---|---|---|
| **A. 提交到实验分支** | ✅ **已做**（15:38） | `477216a` + `71cc965`，77 + 2 个文件；已用 `.gitattributes` 防住 CRLF 改写 |
| **B. 处理 `experiments/raw/e2e_testnet_tx/`** | ⏸ 待你定 | 10-28 的旧采样（26 KB），已被新批次取代。建议保留并标"历史遗留" |
| **C. `z3/wsl/` 与 `snapshots/` 纳管** | ⏸ 待你定 | 30+ 脚本是实验基础设施；涉及 `main` 分支策略。密钥文件必须同时进 `.gitignore` |
| **D. 补齐二进制指纹** | ✅ **已做**（15:44） | 见 §5.2；采集脚本 `z3/wsl/bin_fingerprint.sh` 可重跑 |
| **E. 运行自动落盘日志** | ✅ **已做**（15:40） | `tee_stdio()` 已自测：stdout + stderr 均入 `run.log` |

**A（入库）、D（指纹）、E（日志）均已闭合；仓储状态：已推送远端（2026-10-29 15:47）。**

| 检查项 | 结果 |
|---|---|
| 远端分支 HEAD | `21f1d6d`，与本地 HEAD 一致 |
| 远端 `raw/` 下文件数 | 69 |
| **远端对象库回读校验** | **清单 66 条 → 通过 66、哈希不符 0、缺失 0** |

最后一行是本审计唯一一次**完全绕开本地磁盘**的验证：`MANIFEST.sha256` 和每个被校验文件都取自 `origin/experiments/e2e-testnet-tx-harness` 的对象库（`git cat-file blob`），逐条比对 SHA256。结论：远端存储的字节与清单声明完全一致，`.gitattributes` 的 `-text` 规则在推送链路上确实生效——若 CRLF 被转换，这 66 条必然全数不符。

推送输出仅显示 `71cc965..21f1d6d`，因为 `477216a`/`71cc965` 在更早一次推送时已上远端；`04a8423` 及之前的 `1ad329c` 同批上去。

剩余待定项：§6-B（10-28 旧采样目录）、§6-C（`z3` 侧 `wsl/` 与 `snapshots/` 纳管）。两项均不影响数据安全。

C 的命令（若决定纳管，先在 `D:\Research\z3` 加忽略规则再 add）：

```bash
cd /d/Research/z3
cat >> .gitignore <<'EOF'

# 密钥材料：绝不入库
identity_local.txt
mnemonic_age_local.age
real.age

# 13MB 链快照：不入库，用 make_manifest.py --extra 纳入哈希即可
snapshots/*.tar.gz
EOF
git add .gitignore wsl/
git commit -m "chore(infra): 纳管 WSL regtest 实验脚本"
```

另外仍建议：三个密钥文件现在只有磁盘一份，加密备份到仓库外（U 盘 / 密码库）。这个只能你做。

---
