# Sapling 端到端成本模型 · 补充验证预注册（Regtest，Confirmatory）

> 候选方案冻结日期：2026-10-29
> 关联实验分支：`experiments/e2e-testnet-tx-harness`（PR #24，未合并）
> 性质声明：**本文件是 2026-10-30 启动的一轮"补充验证"实验的候选预注册（confirmatory pre-registration），不是对 2026-10-29 试点数据的追溯性改写。** 试点数据（29 轮 / 11 形态）保持独立，作为估计样本量的依据，不并入本轮分析。
> **两次冻结**：① 本次提交冻结的是**候选实验协议与事先规定的决策规则**（形态矩阵、可行性判据、失败规则、统计方法）；② 可行性门禁完成后，依据预先规定的规则记录结果并冻结**最终测量矩阵**（见 §4.3）。在 ② 完成前，最终矩阵不视为已定。

---

## 0. 为什么需要这一轮（与既有记录的衔接）

- `DEVIATIONS.md §0` 已确认：2026-10-29 的端到端实验**从未事先创建预注册文件**，模型选择（M1/M2/M3 中选 M3）与 output 边际数值（91.5 ms）属**探索性**，结论强度需打折。
- `DEVIATIONS.md §3` 给出升级路径："把 29 轮作为试点，冻结模型形式、形态网格、每格样本数、离群点规则、判据，再补测。"
- 本预注册即执行该路径：用**独立重复样本**把探索性发现升级为可辩护结论。
- 环境边界见 `DEVIATIONS.md §1 (D1)`：本轮**仍是 WSL2 离线 Regtest**，不是 Testnet。
- **可移植性降级声明**：本轮估计的是**特定钱包版本（Zallet Beta）与离线 Regtest 环境**下的 Spend / Output 边际成本差异。该相对比值在不同网络、不同钱包版本、不同部署环境中的可迁移性**尚未验证**，不得声称可直接外推主网。

---

## 1. 环境与可复现边界（冻结，不得在中途变更）

| 项 | 冻结值 |
|---|---|
| 环境 | WSL2 离线 regtest，原生进程（非 docker compose） |
| 节点 | Zebra 6.2.3（`zebrad` 二进制指纹见 `raw/ENV_binaries.txt`） |
| 钱包 | Zallet Beta（`zallet` / `zallet-zaino` launcher+prover） |
| 测量执行器 | `experiments/e2e_testnet_tx/confirmatory_bench.py`（本次 gate 执行 HEAD `8a9a90e`；文件 blob `f19f0d6c…`，与当前 `cec4fd0` 相同） |
| 分析脚本 | `experiments/e2e_testnet_tx/fit_sapling_e2e_model.py`（同 HEAD；阶段三前需加 `--raw-dir`，仅改参数、不改模型） |
| 计时时钟 | Python `time.monotonic()`（见脚本第 288–311、395 行） |
| 轮询间隔 | `0.02 s`（`time.sleep(0.02)`，脚本第 316 行）→ `pipeline` 量化误差 ≤ 20 ms（已核对脚本，非沿用旧值） |


> **版本与复现锚定（如实记录限制）**
> 本次 gate 执行版本为 `8a9a90e`。由于执行元数据**未记录** `git_head`，该版本依据执行时间线（gate 起于 15:23:41，位于 `8a9a90e` 15:23:09 与 `cec4fd0` 15:30:36 之间）与 Git 提交记录确定；执行器文件与当前 `cec4fd0` 的 blob SHA 一致（`f19f0d6c…`）。
> 本次 gate **未记录二进制哈希**，属实验记录限制。`meta.json` 无 `git_head`，run 目录内无每轮版本或二进制记录；`raw/ENV_binaries.txt` 为 2026-10-29 试点快照，**不覆盖**本次执行。
> **源码 blob SHA 不替代二进制哈希**，两者分别描述，本记录不声称已完成二进制级复现锚定。

> **历史说明**：冻结①（`a1277a7`，2026-10-29 20:50）引用 `sapling_e2e_bench.py` 是当时实况；`confirmatory_bench.py` 首次提交 `b790514` 在 21:02，晚 12 分钟。两者**职责不同，不是同一脚本的两个版本**：前者为试点（pilot）脚本，后者为确认性执行器（z_sendmany 路径）。

> **门禁核验表**：六项核验见 F5 验证文档附四（D1，8/8 通过）；本次记录：链高 32297（20/20 次快照恢复一致）、可花费 note 36、余额 11999980000 zat、addresses 38 行，与 §1 末表一致。

> **补测前待整改（本次不授权改动执行器）**：
> 1. `meta.json` 记录 `git_head`；
> 2. 记录执行器文件 SHA-256；
> 3. 若实际执行依赖编译二进制，再记录相应二进制 SHA-256。

### 快照（唯一冻结值，以文件 + 哈希为准）

| 字段 | 冻结值 |
|---|---|
| 快照文件 | `z3_regtest_h32297_20261029_145710.tar.gz` |
| SHA-256 | `ca35201887b8041b44c483ad258a718f4a74787c02c4ff9dbbb202857b09510c` |
| 大小 | 13,167,422 B |
| 恢复后链高（预期） | 32297（文件名 `h32297` 编码；**门禁首次恢复时以 `getblockchaininfo.blocks` 复核并填入下表**） |
| 钱包状态（待门禁核验） | 门禁首次恢复后以 `z_getbalanceforaccount` / `listunspent` 核验可花费 Sapling note 数与余额，填入下表 |
| 资金条件 | 计划最大 S=17 需 ≥17 个可花费 Sapling note；试点曾用同快照构造 S 达 17 的形态（`DEVIATIONS.md D4`），门禁复核确切 note 数 |
| ZIP 212 激活高度 | 32257（仅协议激活门槛，**不是**本快照链高，二者不得混淆） |

> **门禁核验后填写（恢复即定，确定性）：**
> | 核验项 | 值 |
> |---|---|
> | 实际恢复链高 | 32297（20/20 次快照恢复一致） |
> | 可花费 Sapling note 数 | 36 |
> | Sapling 余额（zat） | 11999980000 |
> | 是否支持 S=17 | 是（36 note ≥ 17，余额相容） |

> 任何一项环境/脚本/快照在中途变更，必须记 `DEVIATIONS` 新条目并重算，不得"悄悄换环境"。

---

## 2. 试点数据回顾（仅用于设计，不进入本轮分析）

| 指标 | 试点值 |
|---|---|
| 成功轮数 | 29 |
| 形态数 | 11 种 (S,O) |
| 模型 | `T ≈ 589.9·S + 91.5·O + 424.2 ms`，R²=0.9998，RMSE=39.6 ms |
| spend/output 成本比 | ≈ 6.45 : 1（bootstrap 比值 CI [4.04, 6.60]） |
| 等量替换对照 | (3S,3O) 中位 2445.1 ms vs (4S,2O) 中位 2993.0 ms，差 ≈ 548 ms（各仅 1 次成功） |

**薄弱点（本轮要补的）：** 重复样本集中在 (1,2)/(2,2)/(1,9)；其余形态多只有 1 次成功；(3,3) vs (4,2) 的 548 ms 差仅有单次支撑。

---

## 3. 研究问题与假设（冻结，分析时不增删）

### 问题 A：Spend 与 Output 的边际成本确实不同吗？
- **H_A**：Spend 边际成本 > Output 边际成本（即 `a_S > c_O`）。判据见 §9。
- 试点支撑：589.9 vs 91.5。

### 问题 B：相同证明数量，是否仍存在可重复耗时差？
- 重点对照：**(3S,3O) vs (4S,2O)**，两者证明数均为 S+O=6。
- **H_B**：两形态 `pipeline` 中位耗时之差在新重复样本中仍显著且同号。判据见 §9。

### 问题 C：双变量模型是否优于"按总证明数计费"？
- **H_C**（明确口径）：`M3` 相对 `M1` 的按形态 LOO RMSE 达到预定幅度下降（相对 ≥10% 且绝对 ≥20 ms），**且** `M3` 的 LOO RMSE < `M2`（说明 Output 项提供了额外预测信息）。
- 说明：`M2` 在此处的角色是证明"Output 项有增量信息"，不要求 `M2` 也满足同幅度阈值；若后续要声称 `M3` 对 `M1`、`M2` 均有达到实际意义的改善，须另行为 `M2` 设置明确相对/绝对门槛（本预注册不预先主张该更强结论）。
- 试点支撑：M3 的 LOO 误差低于 M1/M2。

---

## 4. 形态矩阵（冻结；可行性门禁见 §4.1）

| # | S | O | 主要目的 |
|---|---|---|---|
| 1 | 1 | 2 | 基线 |
| 2 | 2 | 2 | 小规模 spend 增量 |
| 3 | 4 | 2 | spend 阶梯 |
| 4 | 7 | 2 | 中间规模 |
| 5 | 10 | 2 | 较大规模 |
| 6 | 17 | 2 | 高规模端点 |
| 7 | 1 | 9 | 多 output 对照 |
| 8 | 3 | 2 | output 对照基线 |
| 9 | 3 | 3 | output 增量 + 等证明数对照（vs #10） |
| 10 | 4 | 3 | 第二组 output 增量 |

- **每格目标：≥ 5 次成功测量。** 10 格 × 5 = **目标 50 次成功样本**。
- **每格最多尝试次数（预先冻结）：8 次。** 在 ≤8 次尝试内争取 ≥5 次有效样本；达到 8 次仍不足 5 次，则该格标记为"**样本不足**"（underpowered），如实报告，不无限重测至得到满意数据。
- 三优点：O=2 spend 阶梯覆盖小→大规模；3S2O/3S3O 与 4S2O/4S3O 重复检验 output 增量；(3,3) vs (4,2) 独立验证等证明数耗时差。

### 关键形态失败的处理（预先冻结，不可事后变通）
- (3,3) 与 (4,2) 是 H_B 的核心对照。若门禁中**任一**无法构造：
  - 不得在矩阵中悄悄删除后声称"H_B 得到验证"；
  - 必须将 **H_B 标为"无法按原设计检验"**，并在 §4.2 记录原因；或
  - 在**正式采集开始前**完成有记录的方案修订（例如改用其他等证明数形态对），修订写入 §4.2 后方可生效。

### 4.1 可行性门禁（冻结前必须执行；称"可执行性探测"，非"稳定生成"）
- 对 10 种候选形态**逐一**从同一快照恢复后构造 1 次，判定**可执行性**（注意：单次探测仅证明当时可构造，不证明"稳定"，稳定性由后续正式重复样本判断）。
- 判定内容：实际 Spend/Output 数是否符合预期、交易是否成功构造、实际手续费是否符合 ZIP 317（见 §7）、是否出现 RPC 或钱包错误。**不得因某形态耗时较长而将其排除。**
- 构造失败的形态：记录原因（如 note 不足、output 上限、钱包报错），按 §4.2 处理，不硬凑到 50。
- 门禁通过后，依 §4.3 冻结最终矩阵；不得再临时加形态。
- **门禁与正式分离**：门禁探测每形态仅 1 次，**不计入**正式每格 ≥5 的成功样本；其日志单独存于 `raw/confirmatory_20261030/_feasibility_gate/`，在主分析中显式排除，绝不并入正式确认性数据。

### 4.2 门禁导致的矩阵修订记录（冻结后填）

| 形态 (S,O) | 门禁结果 | 处理 | 原因 |
|---|---|---|---|
| 17,2 | 可构造 | 保留 | outputs=2，fee=85000=5000·max(17,2)，size=8010 |
| 3,3 | 可构造 | 保留 | outputs=3，fee=15000，H_B 保持原设计检验 |
| 4,2 | 可构造 | 保留 | outputs=2，fee=20000，H_B 保持原设计检验 |
| 1,2 | 可构造 | 保留 | outputs=2，fee=10000 |
| 2,2 | 可构造 | 保留 | outputs=2，fee=10000 |
| 7,2 | 可构造 | 保留 | outputs=2，fee=35000 |
| 10,2 | 可构造 | 保留 | outputs=2，fee=50000 |
| 1,9 | 可构造 | 保留 | outputs=9（8 收款+1 找零），fee=45000 |
| 3,2 | 可构造 | 保留 | outputs=2，fee=15000 |
| 4,3 | 可构造 | 保留 | outputs=3，fee=20000 |

> **矩阵零修订**：10 格全部可构造，无任何剔除；对照事实按收敛口径——本次结果支持「地址去重解决了这三种多收款形态此前遇到的重复地址拒绝问题」（不写「必要且充分」）。`(3,3)` 与 `(4,2)` 均可构造，H_B **不降级**，保持原设计检验。

> 若门禁使正式矩阵变化，先在此记录修订及原因，再冻结最终测量矩阵；未在此登记的变化一律无效。

### 4.3 两次冻结（本预注册的执行纪律）
- **冻结①（本次提交）**：候选实验协议——10 种候选形态、可行性判据、失败与重测规则、统计方法与判据、时间边界。锁定于 PR #24。
- **冻结②（门禁后）**：依据 §4.1–§4.2 预先规定的规则记录门禁结果；若形态不可执行则按"关键形态失败处理"修订；**在开始正式每格 5 次采集前**，在 §4.2 填妥最终矩阵并固定版本。此后矩阵不再变动。

---

## 5. 计时边界与记录字段（冻结，全部追溯到 `confirmatory_bench.py`，行号锚定 `cec4fd0`）

主指标与辅助指标（`confirmatory_bench.py`，行号锚定版本 `cec4fd0`；该文件与 gate 执行的 `8a9a90e` blob 相同 `f19f0d6c…`，故行号对 gate 同样成立；A/B/C 分类）：

- **`submit`**：从发出 `z_sendmany` RPC 请求到拿到成功返回的 `opid`（`send_frozen()`，`t0` @567 → `t_submit` @593）。
- **`pipeline`（主指标）**：从 `opid` 返回后，到首次观察到操作状态为 `success`（`t_pipeline` @618）。含 build+prove+sign+broadcast（即 Sapling Groth16 证明+签名+广播），**不含区块确认**。轮询量化误差 ≤ 20 ms（已核对 `time.sleep(0.02)` @626）。
- **`mine`**：对应挖块阶段耗时（`advance()`，实际 `generate` n 块，轮询 `getblockchaininfo.blocks` 确认链高增量）。
- **`sync`**：钱包达到规定同步条件所用时间（`wait_sync()`）。同步条件：钱包 `wallet_tip.height >= max(node_tip.height, zebrad blocks)`。
- **`total`**：单轮从**前置同步结束后**（`run_one()` 内 `t_round` 起点）到本轮结束的墙钟 = submit + pipeline + mine + 后置 sync。**注意：每轮开始前的 `wait_sync()` 不计入 `total`**；该前置同步是测量前提，非交易耗时。
- 每轮至少记录：`S, O, 证明数(=S+O)`、`submit, pipeline, mine, sync, total`、实际手续费与交易大小、链高、钱包同步状态、资金池快照标识、成功/失败状态及日志、二进制哈希+脚本版本(git HEAD)+代码提交。

> 禁止：把各阶段中位数相加冒充 `total`；把 `total`（含确认）当主指标报告；在采集过程中修改上述计时逻辑。
> 行号仅用于定位，计时定义不变；行号锚定 `cec4fd0`，与其余冻结上下文一致。

---

## 6. 状态控制与执行顺序（冻结）

- **状态控制**：每轮测量**前**从 §1 固定快照 `z3_regtest_h32297_20261029_145710.tar.gz` 恢复，确保链高、可花费 note 数、钱包状态一致。恢复动作必须**写入测量脚本循环内部**，不得依赖人工操作。
- **样本顺序**：10 格 × 5 = 50 次测量以**随机顺序**执行（预先生成随机序列并落盘），避免"先小后大"的顺序偏差。
- **失败分类与处理**（冻结规则；本轮走 z_sendmany 路径，故 PCZT 专属错误不计为本轮常规失败示例）：
  - 失败类别：① RPC 失败（连接/超时/协议错误）；② opid 最终状态失败（`z_getoperationstatus` 返回 `failed`）；③ 超时（pipeline 轮询 600 s 内未 success）；④ 实际形态或手续费不符（构造出的 S/O 或 fee 与计划不一致）；⑤ 已确认的环境瞬时故障（如节点未就绪、快照恢复异常）。
  - 所有尝试（含失败）**全部保留**原始日志与原因，计入 FAILURES 记录；**不得为凑成功数删除不喜欢的耗时值**。
  - 重测条件：仅 ⑤ 环境瞬时故障可重测同形态（计入该格 8 次尝试上限）；形态性失败（①④）按 §4.1/§4.2 处理，不重测掩盖。
- 新数据目录：`experiments/e2e_testnet_tx/raw/confirmatory_20261030/`，**不覆盖**试点 `raw/sapling_e2e_*`；门禁探测存 `_feasibility_gate/`（§4.1）。

---


---

### 6-A 三维正交

失败分类的三个维度相互独立，不得相互推导：

- **`failure_class`（原因）**：分类器判定的失败类别，见 §4 与下表 6-D。
- **`stage`（阶段）**：失败发生的执行阶段（prep / state / sync / submit / status_poll / opid_failed / opid_timeout），属事实字段。
- **`submit_state`（提交状态）**：`not_submitted` / `unknown` / `submitted` 三态，仅存于 sidecar `errors.jsonl`，经 `attempt_id=<run_id>:<round>` 与主 CSV 关联。**三态的语义是「操作结果的可判定性」，不是「钱包是否受理过 `z_sendmany`」**：`not_submitted` = 已知未创建 opid；`submitted` = 已知已创建且处于**确定状态**（在途 pending / opid 终态失败 / 已上链成功）；`unknown` = 已取得 opid 但轮询窗口内**未确认终态、结果不可判定**（仅 `opid_timeout` 属此态）。因此 `status_poll`（opid 在途、状态可知）记 `submitted` 与 `opid_timeout`（结果悬而未决）记 `unknown` 并不矛盾。**`submitted` 与 `unknown` 均以「钱包已受理该异步操作（`z_sendmany` 已返回 opid）」为前提**，二者区分在**状态是否可知**；两态**均不等于**交易已广播或已被链上/网络确认——该确认须由 G4 外部裁决核验。

`submit_state` 是重试 / 替换权限的唯一技术前提；字段缺失须标「无法判定」，不得默认 `not_submitted`。`rpc_transport_error` 可跨 `not_submitted` / `unknown` / `submitted` 三态，故其重试裁决按 ①/D1a 逐态判定，不按类别一概而论。

### 6-A′ ⑤ 的适用范围（新增）

> **⑤ 环境瞬时故障**：仅指具有**瞬时性、可恢复性**，且**不表明实验快照或目标形态存在结构性问题**的环境故障。例如：节点尚未就绪、短暂 RPC 不可用、可恢复的同步异常。
>
> **以下不属于 ⑤**：
> - `state_height_mismatch`：恢复后链高与预注册目标不一致，属**快照状态结构性不一致**；
> - **D3-C**：目标形态在当前 Note 状态下不可构造，属**前置可行性失败**；
> - **D3-B**：恢复态完整性校验失败，按**独立的受控恢复规则**处理，不得仅凭其发生在恢复阶段就认定为 ⑤。
>
> 因此，**⑤ 的重试授权不适用于上述结构性或前置可行性失败**；D3-B 的继续权限来自受控恢复规则本身（每形态限 1 次），不来自 ⑤。

### 6-B 两类标签来源

- **`failure_class`**：异常类别标签，由分类器在失败路径写出，属「发生了什么」。
- **结果不匹配标签**（`form_mismatch` / `fee_mismatch`）：交易已成功提交（`submit_state=submitted`，`txid` 佐证），但回查形态或手续费与计划不一致；它**不是失败类别**，不进入失败分类计数，仅在统计报告中单列。

### 6-C 双锚点（代码位置 + 消息前缀）

`fail_row` 的调用点（1507 / 1512 / 1518 / 1541 / 1547 / 1555）未传异常对象，故若 sidecar 缺失 `stage` / `submit_state`，按 D3 约定**以固定版本代码位置授权**，报告不得称 sidecar 证实 `not_submitted`；字段缺失须标「无法判定」。

### 6-D 32 条裁决记录

| # | `failure_class` | `stage` | `submit_state` | 类别 | ① campaign 继续 | ② 人工替换 |
|---|---|---|---|---|---|---|
| 1 | `recipient_error` | prep | not_submitted | 五类外·前置准备 | 否 | 否 |
| 2 | `recipient_derivation_failed` | prep | not_submitted | 五类外·前置准备 | 否 | 否 |
| 3 | `recipient_validation_failed` | prep | not_submitted | 五类外·前置准备 | 否 | 否 |
| 4 | `state_height_mismatch` | null | null | 五类外·结构性 | 否 | 否 |
| 5 | `state_verification_failed`@A | null | null | ⑤ 瞬时环境 | 是（无条件） | 否 |
| 6 | `state_verification_failed`@B | null | null | **五类外·受控恢复** | 是（条件：每形态限 1 次） | 否 |
| 7 | `state_verification_failed`@C | null | null | 五类外·前置可行性 | 否 | 否 |
| 8 | `env_transient_sync` | sync | not_submitted | ⑤ 瞬时环境 | 是（无条件） | 是* |
| 9 | `rpc_transport_error` | submit | not_submitted | ① / D1a | 是（无条件） | 是* |
| 10 | `rpc_transport_error` | submit | unknown | ① / D1a | 条件：G4 确认未受理后可继续 | 否 |
| 11 | `rpc_transport_error` | status_poll | submitted | ① / D1a | 否 | 否 |
| 12 | `rpc_duplicated_recipient` | submit | not_submitted | ① / D1b | 否 | 否 |
| 13 | `rpc_duplicated_recipient` | status_poll | submitted | ① / D1b | 否 | 否 |
| 14 | `rpc_privacy_policy_rejected` | submit | not_submitted | ① / D1b | 否 | 否 |
| 15 | `rpc_privacy_policy_rejected` | status_poll | submitted | ① / D1b | 否 | 否 |
| 16 | `rpc_invalid_parameter` | submit | not_submitted | ① / D1b | 否 | 否 |
| 17 | `rpc_invalid_parameter` | status_poll | submitted | ① / D1b | 否 | 否 |
| 18 | `rpc_insufficient_funds` | submit | not_submitted | ① / D1b | 否 | 否 |
| 19 | `rpc_insufficient_funds` | status_poll | submitted | ① / D1b | 否 | 否 |
| 20 | `rpc_insufficient_funds` | opid_failed | submitted | ① / D1b | 否 | 否 |
| 21 | `rpc_wallet_error` | submit | not_submitted | ① / D1b | 否 | 否 |
| 22 | `rpc_wallet_error` | status_poll | submitted | ① / D1b | 否 | 否 |
| 23 | `rpc_invalid_address_or_key` | submit | not_submitted | ① / D1b | 否 | 否 |
| 24 | `rpc_invalid_address_or_key` | status_poll | submitted | ① / D1b | 否 | 否 |
| 25 | `rpc_request_schema_invalid` | submit | not_submitted | ① / D1b | 否 | 否 |
| 26 | `rpc_request_schema_invalid` | status_poll | submitted | ① / D1b | 否 | 否 |
| 27 | `rpc_error_<N>` | submit | not_submitted | ① / D1b | 否 | 否 |
| 28 | `rpc_error_<N>` | status_poll | submitted | ① / D1b | 否 | 否 |
| 29 | `opid_terminal_failed` | opid_failed | submitted | ② | 否 | 否 |
| 30 | `opid_timeout` | opid_timeout | unknown | ③ | 条件：G4 确认未受理后可继续 | 否 |
| 31 | `other` | null | null | 五类外·未映射 | 否 | 否 |
| 32 | `form_mismatch` / `fee_mismatch` | 无 sidecar | submitted（`txid` 佐证） | ④ | 否 | 否 |

\* G5 三重条件：`not_submitted` **且** `invoked=False` **且** 每形态 ≤ 1 次。

> **G4 外部裁决的授权范围（仅限两行）**：G4 裁决文件（`--g4-verdicts`）**只在第 10 行（`rpc_transport_error`@submit@`unknown`）与第 30 行（`opid_timeout`）**生效，二者的「① campaign 继续」列均为「条件：G4 确认未受理后可继续」。**其余各行一律不受理 G4 裁决**，按该行原列执行——特别地，第 11/13/15/17/19/22/24/26/28 行（`status_poll`，`submit_state=submitted`）恒为「否」，即使 G4 给出 `unaccepted` 也不得继续（`status_poll` 阶段 opid 已取得、状态可知，无「未受理」可裁决）。实现中 `_campaign_continue` 的 G4 分支仅匹配 `stage=="submit"` 且 `submit_state=="unknown"`，`opid_timeout` 为独立分支，二者之外无任何路径读取 G4 裁决。

> 第 32 条合并两个标签，理由：二者**判决相同**（停止该形态）且**可在同一行共现**（形态不符时手续费通常也不符）；统计时 `fee_mismatch` 单独计数。若拆为两条会与「一记录一判决」的计数口径冲突。
>
> **双重不匹配的优先级（明确 tie-break）**：当同一轮 `form_match=false` **且** `fee_match=false` 同时成立时，`failure_class` 记 `fee_mismatch`（**手续费优先**）。理由：`fee_mismatch` 是已单列统计的模型偏离事件（§6-F），优先归入它可保持手续费偏离的计数不被形态偏离稀释；`form_mismatch` 在此情形下**不另立类别**，其信息由 `rounds.csv` 的 `form_match` 列（`false`）与 `fee_match` 列（`false`）**逐列保留**，不因 `failure_class` 的单值化而丢失。
>
> `insufficient_notes`：0 个可达组合，保留在类别清单，标注「未使用标签」。

### 6-E 两种机制边界

- **机制①（campaign 内继续）**：同一形态下 ≤ 8 次尝试内自动继续（非重试），受 6-D 的「① campaign 继续」列约束。
- **机制②（人工替换 `--replaces`）**：须满足 G5 三重条件（`not_submitted` + `invoked=False` + 每形态 ≤ 1 次），在独立 run 目录追加记录，原记录永久保留（G2）。

### 6-F 统计口径

- `underpowered` 是**样本不足状态**，不是失败类别。形态采集**终止时**，若有效成功次数不足目标次数（默认 5 次），在 `summary_by_shape.csv` 标记 `TRUE`；达到目标次数则标记 `FALSE`。无论因达到最大尝试次数还是因不可重试错误**提前停止**，均按**终止时的有效成功次数**判定，并完整保留该形态及其全部尝试记录。
- `fee_mismatch` 单列为**手续费模型偏离事件**，不并入失败计数。
- `other` 单列为**未映射失败**，不并入五类。
- 任何情形**不得剔除**已记录的尝试行。

---

## 7. 模型定义（显式，避免与试点崩塌 M1 混淆）

> 注意：本预注册 M1 与 2026-10-29 试点中"崩塌的 M1（`a·proofs+b` 负截距，因 proofs 曾被误取 O=2~3）"**不是同一模型**。此处严格定义；且 `S+O` 仅称"总证明数"，**不称**"ZIP 317 逻辑动作数"。

- **M1（按总证明数计费）**：`T = a·(S+O) + b`，其中证明总数 = S+O（Sapling 每 spend、每 output 各证一次 Groth16）。
- **M2（忽略 output）**：`T = a·S + b`。
- **M3（双变量）**：`T = a·S + c·O + b`。

- **手续费核对（独立于模型）**：ZIP 317 规则为 `fee = 5000 × max(S, O)` zat，用于交叉验证钱包实际构造，与 M1 的总证明数定义**分开表述**，不得混用。

分析时三模型**同时拟合**，比较其样本外表现，不预先挑出"最优"。

---

## 8. 分析三层（冻结，不事后改方法）

**第一层 · 直接对照**：每形态报告成功样本数 n、中位数、IQR、范围。重点展示：
- output 增量：(3,2)→(3,3) 与 (4,2)→(4,3) 的 output 边际；
- 等证明数：(3,3) vs (4,2) 的差值是否稳定。

**第二层 · 重估三模型**：对 confirmatory 数据拟合 M1/M2/M3，报告：
- RMSE；
- 按交易形态留一交叉验证（LOO）误差（定义见下）；
- `a_S`、`c_O` 及其差值的不确定性（bootstrap 95% CI，方法见下）。

**第三层 · 结论强度**：按 §9 判据逐条判定，不支持的假设如实报告"未能确认"，不继续挑模型/挑样本/加测到显著。

### Bootstrap 具体做法（冻结）
- 每次 bootstrap：在**同一形态**的成功测量中**有放回重采样**，重算该形态的中位数；用这些中位数组成数据集重新拟合 M3，得到一组 `(a_S, c_O, b)`。
- 对 H_A：每次 bootstrap 计算 `Δ = a_S − c_O`，取其分布；重复 **≥ 4000 次**，使用**预先固定随机种子 `seed=20261030`**，95% 区间采用**百分位数 Bootstrap（2.5 / 97.5 百分位）**。
- 对 H_B：对 (4,2) 与 (3,3) 分别独立重采样其成功测量中位数，计算两中位数之差的 Bootstrap 95% 区间（同种子、同算法）。
- 若还需成本比，单独对 `a_S / c_O` 的 Bootstrap 分布计算 95% 区间；**不声称**该比值区间与"两独立系数区间不重叠"等价。

### LOO 定义（冻结，三模型一致）
- 每一折**留出一种 (S,O) 形态**；用其余形态的成功测量**中位数**拟合模型，预测被留出形态的中位数；以 `|预测 − 实际中位|` 汇总为 LOO RMSE。
- M1 / M2 / M3 使用**相同形态集合**与**相同评估方法**，方可比较。

### 失败分类与重测（与 §6 一致，写入分析）
- 失败类别、阶段、提交状态的三维划分与 32 条裁决记录见 **§6（6-D）**；本轮**不在此重复列举**，以免与 §6 出现两套失败分类口径。
- 结果记录中 `form_mismatch` / `fee_mismatch` 属「已提交成功但形态/手续费不符」，单列于统计报告（§6-F），**不计入失败类别**，亦不进入五类重测判定。
- `MissingProofGenerationKey` / `sapling_signed=0` 属此前 PCZT 路径错误，**不列为本轮常规失败示例**。
- 每次尝试（含最终不进入模型的失败）均保留日志。

---

## 9. 假设判据（数值化，冻结）

- **H_A 接受** ⇔ `Δ = a_S − c_O` 的 Bootstrap 95% 置信区间**下界严格大于 0**（每次 bootstrap 直接计算 Δ，非依赖两独立系数区间是否重叠）。否则记为"未能重复确认"。
- **H_B 接受** ⇔ (3,3) 与 (4,2) 两形态 `pipeline` 中位数之差的 Bootstrap 95% CI（各形态内重采样）**不含 0**，且点估计保持同号；差值量级落在 **[300, 800] ms** 视为"稳定"，否则记为"方向一致但量级不稳"。若门禁判定 (3,3) 或 (4,2) 不可构造，则 H_B 直接标为"无法按原设计检验"。
- **H_C 接受** ⇔ M3 相对 M1 的按形态 LOO RMSE **相对下降 ≥ 10% 且绝对差 ≥ 20 ms**，且 M3 的 LOO RMSE < M2（Output 项提供增量信息）。
- 任一假设不满足上述判据 → 如实报告"未能被重复确认"，并在结论中降级为探索性发现。

---

## 10. 本轮不做的事（冻结，避免范围蔓延）

- 不追 Testnet / 真实网络（除非导师明确要求）。
- 不重开大范围优化开关扫描。
- 不修复 E2E 内存采样器缺口（漏采 `zallet-zaino` 子进程）；本轮内存数据不作为完整端到端内存结论。
- 阶段四 Builder 内部计时修正（另一仓库、需 cargo 构建）列为**可选**，且仅在阶段一至三完成后、有余力时做；其区间只能标"归因阶段"，不得标"纯证明直接测量"。

---

## 11. 交付物（冻结）

1. **本预注册文件**（候选协议冻结①；门禁后补 §4.2 最终矩阵冻结②）。
2. **独立原始数据 + 分析报告**：`raw/confirmatory_20261030/`（rounds.csv 等）+ `FIT.md`，报告可从 CSV 重新生成；不与试点混算；门禁探测存 `_feasibility_gate/` 且排除。
3. **结果判定文档**：哪些结论获重复支持 / 哪些仍属探索性 / 哪些需更多样本，逐条明确。
4. **与数据一致的 PPT 修订**：明确区分完整端到端总时间、本地构造时间、纯证明时间估计、内部进度区间；相对成本比标注"Regtest + Zallet Beta 特定环境，可迁移性未验证"。

---

## 12. 执行里程碑（状态如实标注）

- **阶段一 · 候选协议冻结（本次）**：方案 + 可行性判据 + 失败规则 + 统计方法 + 时间边界已冻结①；已提交 PR #24。✅ 候选协议已冻结。
- **阶段一 · 可行性门禁**：`run_20261030_152341`，10/10 形态全部可构造、形态与手续费精确匹配（form_match / fee_match 10/10），0 失败、0 重测；按 §4.2 冻结最终矩阵②（零修订）。✅ 已执行。
- **阶段二 · 正式补测**：每格 ≤8 次尝试争取 ≥5 成功，随机顺序、每轮快照恢复，独立保存。⬜ 未执行。
- **阶段三 · 分析**：三层分析 + 假设判据 + 复现检查（fit 脚本加 `--raw-dir` 指向 confirmatory 目录）。⬜ 未执行。
- **阶段四（可选）**：Builder 内部计时修正，更新报告/PPT/PR 三者一致。⬜ 未执行。

> 分析调用示例（阶段三）：
> `python experiments/e2e_testnet_tx/fit_sapling_e2e_model.py --raw-dir experiments/e2e_testnet_tx/raw/confirmatory_20261030 --md experiments/e2e_testnet_tx/raw/confirmatory_20261030/FIT.md`

---

## 13. 修改记录（冻结②回填）

| # | 变更 | 对成功判据 | 对执行 / 统计口径 |
|---|---|---|---|
| M1 | 测量脚本 → `confirmatory_bench.py`@`8a9a90e` | 不变 | 补充版本证据 |
| M2 | 核验手段 → DB 只读 + schema 断言 + 双 RPC | 不变 | 核验更强，排除 `listunspent` 截断风险 |
| M3 | §5 定位 → 函数名 + 行号（锚 `cec4fd0`） | 不变 | 仅定位方式 |
| M4 | §1 四项待填 → 32297 / 36 / 11999980000 / 是 | 不变 | 补充门禁证据 |
| M5 | §4.2 → 10/10 可构造，零修订 | 不变 | 矩阵固定，H_B 不降级 |
| **M6** | §6 失败处理重构（D1a/D1b 拆分、D3 A/B/C、④ 停止、⑤ 要件化） | **不变** | **改变失败处理、重试资格与样本获取过程**；部分形态可能提前停止并标 `underpowered` |
| **M7** | 新增 `form_mismatch` / `fee_mismatch` | **不变** | **改变统计报告分类口径**；手续费偏离单列 |
| M8 | 版本锚定整改（`git_head` / 执行器 SHA-256 / 二进制 SHA-256） | 不变 | 待补测前落实，本轮记为已知限制 |

> 结论口径：**性能模型的数学定义、假设与成功判据未变；执行规则与统计报告分类口径已变。** 不得表述为「纯文档补充」。

> 文档回填范围：本次（冻结②回填）仅修改本预注册文本（§1 / §4.2 / §5 / §6 附录 / §8 / §12 / §13），未改动任何 `.py` 执行器；M6/M7/M8 的代码实现与第二次冻结仍需单独授权。

> **执行器后续修正（冻结②回填之后，待干净克隆复跑验证，未提交）**：
> - **D2**：修正 `opid_timeout` 的 `submit_state` 由 `submitted` 改为 `unknown`（已取得 opid，但轮询窗口内未确认终态、结果不可判定）；新增 G4 外部裁决入口——`--g4-verdicts <path>` 读取 `{<run_id>:<round>: unaccepted|accepted|undecided}` 的 JSON，默认全部 `undecided`→停止，仅外部明确裁决「未受理」才允许继续；执行器不自动计算 G4。
> - **D1a-unknown 的 G4 先行落地**：第 10 行 `rpc_transport_error`@submit@`unknown` 由原先「仅停止」改为与 `opid_timeout` 同机制——默认停止，仅当外部 G4 裁决明确为 `unaccepted` 才允许继续；裁决入口同为 `--g4-verdicts`，执行器不自动计算 G4，不扩大自动恢复范围之外的其它路径。
> - **G4 裁决文件输入加固（fail-closed）**：`--g4-verdicts` 的 JSON 采用整份校验——存在重复键、verdict 值非精确 `unaccepted`/`accepted`/`undecided`、顶层非 JSON 对象、文件缺失或解析失败时，**整份文件失效**（等价空映射），所有轮次按 `undecided` 停止；其它 run 的键与当前 run 未命中的键仅打印诊断，**绝不影响当前轮次**（当前轮次只按 `<run_id>:<round>` 精确匹配）。
> - **submit_state 语义澄清**：三态语义统一为「操作结果的可判定性」（见 §4 字段定义），而非「钱包是否受理过 `z_sendmany`」；`status_poll` 记 `submitted`、`opid_timeout` 记 `unknown` 属既定口径，未因此改动任何裁决行。
> - **M7 结果不匹配标签的证据校验修正（提交前核对发现）**：M7 把 `form_mismatch` / `fee_mismatch` 写入主 CSV 的 `failure_class` 列，但证据完整性校验（§4.9 条件 2/3）原按「任何非空 `failure_class` 即失败轮」要求其有 sidecar 记录，而第 32 行规定该二者**无 sidecar**、L214 规定其**不是失败类别**、§6-F 规定其**不并入失败计数**。二者冲突的后果是：正式采集中出现一次形态/手续费不符 → 校验 `SystemExit` → 整个 run 被标 `run_aborted` / `usable_as_sample=False` → 该 run 全部样本被 `fit_sapling_e2e_model` 剔除。修正：校验时将这两个标签**排除**出「失败轮 ↔ sidecar」双向核对，并单独计入 `meta.json` 的 `mismatch_rows`（不计入 `failure_rows`，痕迹不丢失）。此修正只改证据校验口径，**不改 M7 的分类、不改 tie-break、不改任何裁决行**。
> - **underpowered**：判定由「用满 8 次尝试仍不足 5 次」改为「采集终止时有效成功次数 < 目标次数」（提前停止亦标 `TRUE`），措辞已于 §6-F 同步澄清。
> 以上属对 M6/M7/M8 原落地的**修正**，尚未经干净克隆复跑验证，不得视为已通过验证。
