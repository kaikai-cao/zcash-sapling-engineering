# F5 实施验证记录（T1）

- 记录时间：2026-10-30 14:4x（本地）
- 代码提交：`97769be`（父提交 `9700e49` = 冻结稿）
- 状态：**已实施并通过离线验证**；本轮**未发交易、未启动 gate、未改预注册、未触碰历史原始数据**
- 对象：`experiments/e2e_testnet_tx/confirmatory_bench.py`、新增 `failure_class_selftest.py`
- 依据：`sapling_e2e_f5_error_classification_design_20261030.md`（冻结稿，**不修改**，本文件只追加实施事实）
- 授权顺序（用户口径）：静态 diff → 离线自检 → 历史回放 → dry-run 验证 → 独立提交

---

## 1. 结论摘要

| 项目 | 结果 |
|---|---|
| 分类器 | 改为三层（阶段 → code → 文本），`rpc_policy_rejected` 不再作默认值 |
| 未截断证据 | 新增 `errors.jsonl`，`raw_error` 为 JSON-RPC 错误对象原样；`attempt_id` 双向关联；写入失败 fail-closed |
| 提交状态 | `submit_state` 三态 + `replacement_allowed()`，`unknown`/`submitted` 一律不可替换 |
| 不变量 | `COLUMNS` 36 列全等；`z_sendmany` params 逐字节不变、timeout 仍 120；计时区间不变；成功路径字段零新增 |
| 自检 | 新增 27/27；回归 30/30；reporting 全通过（含 numpy 解释器） |
| 历史回放 | 3 条真实 `-8` 由 `rpc_policy_rejected` 纠正为 `rpc_duplicated_recipient`；note 不再写「形态不可行」 |

**本文件不构成新 gate 的授权依据。** 真实 `--dry-run`（会触发快照恢复与服务启动）留到 gate 授权后作为第一步执行。

---

## 2. 改动面（对照 §15）

| # | 位置 | 实际改动 |
|---|---|---|
| 1 | `PreTxError` + 新增 `RpcCallError` / `TransportError` | 异常携带 `stage`/`raw_error`/`raw_transport`/`code`/`rpc_message`/`opid`/`z_sendmany_invoked`/`submit_state` |
| 2 | `send_frozen()` | 改用 `z_raw(..., timeout=120)`；删除「policy=%s 被拒」包装语；传输异常→`TransportError`；opid 终态/超时/轮询错误全部结构化 |
| 3 | `_classify()` | 三层判定；策略拒绝需 `-8` + `err-privpol` 或「privacy policy + 否定措辞」 |
| 4 | `fail_row()` | 新增可选 `err`；**先写 sidecar 再返回**；`msg` 统一 `str()` 化 |
| 5 | `run_one()` 两处 | 地址准备失败与提交前失败都写 sidecar；`wait_sync` 失败带 `stage=sync` |
| 6 | 主循环两处 `except PreTxError` | 传入异常对象而非字符串 |
| 7 | 新增 `_emit_failure()` / `init_sidecar()` | 每条失败立即 append + flush + fsync；`OSError` → `SystemExit` |
| 8 | 新增 `verify_run_artifacts()` | JSONL 可解析、`attempt_id` 双向齐全不重复、行数 == 失败轮数 |
| 9 | `--replaces` | 记录被替换的 `attempt_id`；非法格式在 preflight 之前拒绝 |
| 10–12 | `COLUMNS` / 计时区间 / 六项禁止修改逻辑 | **零改动**（见 §3） |
| 13 | `failure_class_selftest.py` | 新增，27 条用例 |

规模：`+423/−29`（代码）+627（自检）。冻结稿 §15.3 估 `+150/−25`，实际约为其 2.8 倍，原因全部是注释与 docstring：设计稿每一条判定规则都在代码里标注了来源条款与反例，未增加任何判定分支之外的逻辑。

---

## 3. 静态比对（逐函数，非肉眼）

用 AST 取 `9700e49` 与当前版本的函数体逐字节比较：

| 函数 | 结果 |
|---|---|
| `pick_amount_zat` / `restore_snapshot` / `note_inventory_detailed` / `verify_state` | 同 |
| `prepare_recipients` / `derive_sapling_recipient` / `account_unified_addresses` / `_addr_hash` | 同 |
| `preflight` / `write_meta_json` / `do_one_attempt` | 同 |
| `_summary_note` | **已改**：仅在存在 `rpc_duplicated_recipient` 时追加一句事实描述（§4.7 要求），其余分支逐字未动 |
| `COLUMNS` | 36 列，前 30 列同序，**全等** |
| 计时区间五处关键语句 | `params`/`t0`/`t_submit`/`t1`/`t_pipeline` 各 1 处，位置与表达式不变 |

`git diff -U0` 对 `pick_amount_zat|form_match|fee_match|5000 * max|note_inventory_detailed|def restore_snapshot|COLUMNS` 零命中。

---

## 4. 自检结果

| 脚本 | 系统 python3 | 带 numpy 的解释器 |
|---|---|---|
| `failure_class_selftest.py`（新） | 27/27，0 跳过 | 27/27，0 跳过 |
| `recipient_derivation_selftest.py` | 26/26，4 跳过（A 组需 numpy） | **30/30，0 跳过** |
| `reporting_patch_selftest.py` | 全部通过 | 全部通过 |

用例覆盖：C1–C8 码映射（含 `unknown privacy policy: FooPolicy` 反向用例）、R1–R4 历史回放与三条回归、I1–I8 全部不变量、S1–S7 状态与证据。

---

## 5. 历史回放（3 条真实 `-8`）

用 `git show 9700e49:...confirmatory_bench.py` 的 `_classify` 函数本体（AST 提取，非手抄）作对照：

| 形态 | 旧 `failure_class` | 新 `failure_class` |
|---|---|---|
| (1,9) | `rpc_policy_rejected` | `rpc_duplicated_recipient` |
| (3,3) | `rpc_policy_rejected` | `rpc_duplicated_recipient` |
| (4,3) | `rpc_policy_rejected` | `rpc_duplicated_recipient` |

note 对照（同一批行）：

- 旧：`无成功构造（形态不可行或环境/策略失败）`
- 新：`交易构造/发送阶段失败 1 条（rpc_duplicated_recipient），未产生 txid；其中重复收款地址导致 RPC 拒绝，不代表该形态不可行`

**已知限制**：历史 `error` 原文在 223 字符处截断（地址未完），不是合法 JSON，**不能** `json.loads`。回放只用正则恢复 `code` 与 `message` 前缀，`message` 中包含 `duplicated recipient address` 足以判定子类。该限制须写入最终报告，且不可通过重跑历史 run「补齐」。

---

## 6. 边界路径实测（stub，无网络）

| 场景 | 分类 | stage | submit_state |
|---|---|---|---|
| `z_sendmany` 返回无 result 无 error | `rpc_transport_error` | submit | unknown |
| 轮询返回 `result=null` | `rpc_transport_error` | status_poll | submitted |
| opid 终态 `failed` 且 `error=null` | `opid_terminal_failed` | opid_failed | submitted |
| opid 终态 `failed` + `-6 Insufficient funds` | `rpc_insufficient_funds` | opid_failed | submitted |
| opid 一直 `executing`（超时） | `opid_timeout` | opid_timeout | submitted |

后两种是旧实现会崩溃（`AttributeError`）或误判的路径。

---

## 7. 与冻结稿的三处必要衔接（实施时发现，均已显式落码并写注释）

1. **`opid_failed` 的归属**：§4.4 第 1 层只列了 `opid_timeout` 与两类传输异常，但 §6.4 R2 要求 `operation failed {"code":-1}` 仍为 `opid_terminal_failed`。若严格按第 2 层 code 映射会得到 `rpc_error_-1`。处理：`stage=opid_failed` 单独成一档，命中 `-4/-6` + 资金措辞时上移为 `rpc_insufficient_funds`（同时修正 §3 表格里标 `△` 的那行），否则一律 `opid_terminal_failed`，原始 code 仍在 sidecar 中可重分类。
2. **sidecar 不挂在 row 上**：§15 第 4 项写「row 内携带 sidecar 字段」，实际改为 emit 时立即落盘并返回记录。理由是 §15.2 第 3 项自己指出的风险：`extrasaction="ignore"` 会静默丢弃 row 中不在 `COLUMNS` 的键，挂在 row 上等于把证据交给一个会静默吞掉它的通道。
3. **多一条流程级用例 S7**：§6 的 26 条全是函数级，S7 用 stub 跑完整 `main()`，验证 sidecar 由执行器自己写出且 `verify_run_artifacts` 通过。超出编号 1 条，属验证加强，不涉及代码范围。

---

## 8. 本轮发现的问题

1. **`reporting_patch_selftest.py` 存在陈旧断言**：第 122 行仍断言 F1 之前的 dry-run 文案 `dry-run：未发交易，仅验证构造`，而 `247f855` 已改成 `dry-run：地址准备与构造已完成…`。即该用例**自 247f855 起就是失败的**，上一轮「自检全绿」的结论因此不成立。已就地修正断言。**撰写本节时该文件仍未入仓；后已入仓，见附录 A2。**
2. **`failure_class_selftest.py` 的 I6 原设计不可执行**：想用历史 dry-run 目录逐行复现 note，但那个 run 产出于 F1 之前，note 是旧口径。改为「列结构全等 + 当前口径复现 + 显式承认旧口径差异」三段断言。
3. **测试文件的跟踪状态**（先前的判断有误，此处更正）：
   - `recipient_derivation_selftest.py` 是**已跟踪**文件，其 T9 直接调用 `run_one()`，而 F5 后失败路径会写 sidecar，故必须同步加 `init_sidecar()`，否则该跟踪测试在 HEAD 上直接崩（`[fatal] sidecar 未初始化`）。此修改已作为补提交入仓，属 F5 的必要连带改动，不是范围扩大。
   - 撰写本节时的未跟踪清单：`reporting_patch_selftest.py`、`a_prime_selftest.py`、`a_note_scan_diag.py`、`raw/confirmatory_20261030/`。
     **后续处置见附录 A2/A3**：前两项已入仓（`6cd58de` / `e910789`）；后两项仍不入仓——`a_prime_selftest.py` 依赖运行中的节点（`z`/`height`）属在线诊断，其产物 `_note_scan_diag/` 一并排除。
   - S7 已加守卫：缺 `reporting_patch_selftest.py` 时 SKIP 而非报错。

---

## 9. 未做的事

- 未执行真实 `--dry-run`（会触发快照恢复 + 服务启动）；S7 与 reporting T1 用 stub 覆盖了同样的流程分支。
- 未发任何交易、未启动 `--mode gate`、未恢复快照。
- 未修改预注册、未修改历史 run 目录、未重分类历史 `failure_class`（§7 口径声明继续有效）。
- 本节撰写时未把 `reporting_patch_selftest.py` 入仓；该文件后于 `6cd58de` 入仓（见附录 A2）。

---

## 10. 下一步（均需单独授权）

1. 新正式 gate：须先恢复冻结快照并重新核验六项（快照 SHA、脚本 SHA、addresses 38、notes 36、余额 11999980000、高度 32297），且新 run 独立目录、不覆盖 `run_20261030_110042/`。
2. 决定是否为三个测试辅助文件单独开一个 docs/test 提交。
3. T3（`failure_class` 中 `opid_timeout` 是否改名）仍未裁定；当前实现按 §6.4 R3 取 `opid_timeout`，若要保留旧名只需改 `CLS_OPID_TIMEOUT` 一处常量。

---

# 附：提交级审查与收尾（2026-10-30 15:0x，审阅后补）

> 本节回应「T1 实现基本完成、进入验证收尾」这一判断。审查对象为 `97769be → 3eac226 → 9494bb5`
> 及其后的收尾提交。**本轮仍未发交易、未启动 gate、未改预注册、未覆盖历史 run 目录。**

## A1. 三个提交的实际边界（对照冻结稿，无越界）

| 提交 | 内容 | 与冻结稿 §15 对照 |
|---|---|---|
| `97769be` | `confirmatory_bench.py` +452/−29；新增 `failure_class_selftest.py` | 全部落在 §15 清单内；禁止修改区（`pick_amount_zat`/`form_match`/`fee_match`/手续费公式/`note_inventory_detailed`/`restore_snapshot`/`prepare_recipients`/`account_unified_addresses`/`derive_sapling_recipient`）AST 逐函数比对全同 |
| `3eac226` | 验证记录 138 行 | 纯文档 |
| `9494bb5` | 跟踪测试 T9 加 `init_sidecar` + 3 条 sidecar 断言 | §15.2 未列此项，但属**必要连带**：T9 直接调 `run_one()`，F5 后失败路径必写 sidecar，不初始化则该测试在 HEAD 上直接崩 |

`COLUMNS` 36 列全等、计时五处语句逐字节不变、`z_sendmany` params 未变——三项禁改均通过 AST 与子串双重比对。

## A2. 干净检出：首检不通过，修复后全绿

从本地仓库 `git clone --single-branch` 到临时目录（只含已跟踪文件）后复跑，**首检结果推翻了我上一轮「27/27」的可复现性**：

| 套件 | 干净检出（修复前） | 干净检出（修复后） |
|---|---|---|
| `failure_class_selftest` | 23 通过 / 0 失败 / **4 跳过**（R1、I3、I6、S7） | **28/28，0 跳过** |
| `recipient_derivation_selftest` | 29 通过 / **1 硬失败**（A5） | **30/30** |
| `reporting_patch_selftest` | 文件不在仓内，无法运行 | 全部通过（有/无 numpy 皆可） |

根因两条，均已修：

1. **`reporting_patch_selftest.py` 从未入仓**。它的被测对象（F1 报告层）本身在 PR 里，测试却不在，导致 S7 永远走 SKIP、F1 的「dry-run 下地址失败不被掩盖」没有任何可执行载体。已入仓（`6cd58de`）。
2. **历史 `raw/confirmatory_20261030/` 未入仓**，而 R1/I3/I6/A5 是**回放真实证据**的用例。已在 `e910789` 按 `raw/pczt_cold_v1` 的既有惯例入库。

## A3. 数据入仓的边界：`wallet.db.sealed` 已排除

| 文件 | 处置 | 理由 |
|---|---|---|
| `run_*/{meta.json,rounds.csv,gate_summary.csv,memory_timeseries.csv}` | 入库 | 与 `pczt_cold_v1` 同惯例；是 R1/I3/I6 的输入 |
| `run_*/run.log` | 不入库 | 同惯例 |
| `laststate_seal_*/README.md`、`addresses_before.tsv` | 入库 | 封存说明与 39 行地址清单，是 F4「派生游标不受快照约束」的取证依据 |
| `laststate_seal_*/wallet.db.sealed` | **禁止入库** | regtest 钱包库字节副本，**含支出密钥** |
| `laststate_seal_*/{filelist.tsv,sha256.txt}` | 不入库 | 仅描述被排除的库与 `.cookie` 哈希，脱离库本体无价值 |
| `_note_scan_diag/*.json` | 不入库 | live-node 诊断产物，脚本未入仓、不可复现 |

排除规则写在 `raw/confirmatory_20261030/.gitignore`。**踩坑记录**：首版写 `laststate_seal_*/*`、`run_*/run.log` 完全没生效——含 `/` 的模式相对 `.gitignore` 所在目录**锚定**，匹配不到 `_feasibility_gate/` 下的嵌套路径，必须加 `**/` 前缀。入库前已用 `git diff --cached --name-only` 逐项确认无 `wallet.db`。

## A4. 两套缺失约定已统一（A5）

A5 原本 `assert os.path.isdir(root)`，干净检出时**硬失败**——把「数据不在」误报成「实现有错」，与 R1/I3/I6 的 SKIP 约定不一致。已加 `check_hist(name, fn, need)`，缺失时 SKIP 并打印原因；尾部汇总改为逐条打印跳过原因（原先一律提示「需要 numpy」，而跳过可能因缺数据）。`6162d65`。

## A5. T3 裁定：保留 `opid_timeout`，不改名

按你给的判据（不影响分类正确性/统计口径/报告解释即可保留）：

- **不影响分类正确性**：`stage=opid_timeout` 是第 1 层判别键，与名称字符串无关；
- **不影响统计口径**：`tx_success`/`form_match`/`fee_match` 不读 `failure_class`；
- **报告解释的风险已消除**：真正的误读不在词本身，而在汇总文案（见 A6）。`_summary_note` 现在把该类写成「提交状态不明…请求可能已被受理」，S8 守护；
- **改名有代价无收益**：会让本常量与冻结稿 §4.4 / §6.4 R3 的表述脱节。

语义已在 `CLS_OPID_TIMEOUT` 处固化：**「客户端轮询窗口耗尽，结果未知」，不是服务端超时，也不是发送失败**。

## A6. 审查发现的同族缺陷（F6，已修 `391789a`）

`opid_timeout` 与 `rpc_transport_error` 此前落在 `other` 桶，note 写成：

> 交易构造/发送阶段失败 1 条（opid_timeout），未产生 txid

两处均不成立：`opid_timeout` 已拿到 opid（`submit_state=submitted`）、submit 阶段的传输异常为 `unknown`，交易**可能已上链**。「未产生 txid」是无法由记录支撑的断言，且与 G4（提交状态不明不得重发）直接冲突——与 F1/F5 完全同源：默认标签替实验下了没有证据支撑的结论。

修复：新增 `CLS_UNKNOWN_STATE = {opid_timeout, rpc_transport_error}`，note 单列「提交状态不明 N 条（…）」。判据用 `failure_class` 而非 `rows.submit_state`——36 列已冻结，sidecar 的 `submit_state` 不在主表内，汇总函数读不到。新增 **S8** 四条断言（纯超时/纯传输/混合分段/其它类别不被误并）。自检 28/28；历史 7 个成功形态 note 不变。

## A7. fail-closed 的实测（不是读代码）

用 stub 跑完整 `main()`（10 形态），第 3 次 sidecar 写入注入 `OSError(28, No space left on device)`：

| 观测 | 结果 |
|---|---|
| 进程行为 | `SystemExit: [fatal] sidecar 写入失败，拒绝继续实验` —— 实验立即中止，无后续尝试 |
| 已写入证据 | 前 2 条在 `errors.jsonl` 中，`flush`+`fsync` 已落盘 |
| `meta_stage` | 仍为 `run_start`，与完成态（`run_end`）可区分 |
| **`rounds.csv`** | **不存在——此前已发送成功的 2 笔交易的 txid 无任何本地记录** |

结论：**fail-closed 成立**（写入失败确实终止、不留「CSV 有失败但证据丢失」）。但暴露 F7（下条）。

## A8. F7（新发现，未修，待授权）

`rounds.csv` 是**循环结束后整体落盘**（`1489` 行）。因此 sidecar 中途写入失败时，此前**已经真实发送**的成功尝试只存在于钱包/链上，run 目录内无 txid 记录。触发条件罕见（磁盘满、权限异常），但与 G2「每条尝试可追溯」不一致。

建议的最小修法（**不改变正常路径任何行为**）：把落盘抽成函数，在主循环外包 `try/finally`，异常终止时用同一份 `rows` 落盘一次。代价：中止的 run 会留下**不完整 CSV**，需靠 `meta_stage != run_end` 与 `verify_run_artifacts` 识别——因此必须同时声明「中止的 run 不得作为样本」。

另一种做法是逐行追加写 CSV（更贴合 §4.9「先写 sidecar 再落 CSV 行」的字面），但改动落在正常路径上，风险更大。

## A9. 本轮提交链

`9494bb5`（T1 收尾）→ `e910789`（数据）→ `6cd58de`（reporting 测试入仓）→ `6162d65`（A5 跳过语义）→ `391789a`（F6）。

## A10. 仍未做

真实 `--dry-run`（会恢复快照并启动服务）、新 gate、预注册修改、历史数据覆盖。这三项继续等你单独授权。

---

# 附二：F7 最小修复（用户授权后实施，2026-10-30 15:0x）

> 授权范围（原话要点）：抽出落盘函数；正常路径行为与结果不变；异常退出用 try/finally
> 尽可能落盘已完成尝试；不改交易逻辑/分类规则/sidecar 格式/36 列/计时区间/实验矩阵；
> 落盘失败不得覆盖原始异常并须标记产物不完整；加故障注入测试；明确中止 run 不得作为
> 正式样本。**本轮仍未发交易、未启动 gate、未改预注册、未碰历史 run 目录。**

## B1. 缺陷与实测证据

`rounds.csv` 原先只在主循环末尾一次性写出。sidecar 写入失败触发 `SystemExit` 时
（磁盘满 / 权限异常），**此前已真实发送并拿到 txid 的成功尝试在 run 目录内没有任何记录**
——与 G2「每次尝试可追溯」冲突。实测（stub 跑完整 `main()`，第 3 次 sidecar 写入注入
`OSError(28)`）：目录只剩 `errors.jsonl` + `meta.json`，2 笔已发送交易的 txid 只存在于
钱包与链上。

## B2. 改动（四处：两处新增、一处 `main`、一处下游守卫）

| 位置 | 改动 | 性质 |
|---|---|---|
| 新增 `write_rounds_csv(rundir, rows)` | 把原内联块原样抽出，字段/列序/`extrasaction` 不变 | 纯抽取 |
| 新增 `mark_run_aborted(...)` | 尽力落盘 + 打标记；**内部全程吞异常**，绝不掩盖原始异常 | 新增（只在异常路径被调用） |
| `main()` | `records_flushed` 标志；`except BaseException` 记录后原样 `raise`；`finally` 中若 `meta_stage != run_end` 则调 `mark_run_aborted` | 仅异常路径 |
| `fit_sapling_e2e_model.load_all()` | 新增 `usable_sample()` 守卫 | 下游强制「中止 run 不作样本」 |

`confirmatory_bench.py` 的 diff 共 **4 个 hunk**：1 个新增两个函数（`@@ -1257`）、
3 个落在 `main()`（标志初始化、落盘替换、`except`+`finally`）。**没有第五处。**所有 `except` 分支（含 `except Exception`）都不吞 `SystemExit`
（它是 `BaseException`），因此 sidecar 写入失败仍会立即中止实验。

## B3. 正常路径等价性（这是本轮最关键的验证）

- **落盘字节级等价**：同一份 rows 分别用 HEAD 的内联块与新函数写出，两文件**逐字节相同**
  （803 字节全等，`EXTRA_KEY` 均被 `extrasaction="ignore"` 丢弃）。
- **AST 逐函数比对**（对 `976d1e9`）：新增 2 个函数、删除 0 个、修改 1 个（`main`）。
  禁改区全同：`send_frozen` **逐字节一致**（params 与计时五处语句命中数 1→1）、
  `_classify`/`_map_code`/`_text_fallback`/`_emit_failure`/`fail_row`/`verify_run_artifacts`/
  `do_one_attempt`/`restore_snapshot`/`prepare_recipients`/`_summary_note` 全部未变。
- **常量**：`COLUMNS`（36 列）、`MATRIX`/形态表、`SNAPSHOT_SHA256`、
  `RESTORE_SCRIPT_SHA256`、`SNAPSHOT_TARGET_HEIGHT` 全部相等。

## B4. 中止时的行为（S9/S10 实测，非读代码）

| 时序 | CSV | sidecar | meta |
|---|---|---|---|
| 2 成功 → 首次 sidecar 写入失败 | 2 行，`tx1`/`tx2` 均在 | 0 行 | `run_aborted` / `partial` / `usable_as_sample=False` / `records_complete=True` |
| 2 成功 + 2 失败 → 第 3 次写入失败 | 4 行（2 成功 + 2 失败） | 2 行，`attempt_id` = `:<3>`、`:<4>` | 同上，`abort_rows=4` |
| 2 成功 → 写入失败且 **CSV 补写也失败** | 不存在 | 0 行 | 追加 `csv_flush_error`，`records_complete=False`，**对外异常文本仍只含 sidecar 失败原因** |

第三种情形专门验证「落盘失败不覆盖原始异常」：`run_main` 返回的仍是
`SystemExit: [fatal] sidecar 写入失败…`，磁盘错误只出现在 `meta.csv_flush_error` 里。

**异常路径不写 `gate_summary.csv`**：证据不全时产出汇总最容易被误读（与既有的
「拒绝写出可被误读的汇总」一致），且该表可由 `rounds.csv` 重算。

## B5. 「中止的 run 不得作为正式样本」已在代码里强制

`load_all()` 逐个 run 目录读 `meta.json`：显式 `usable_as_sample=False` → 跳过并打印；
无 `meta.json` 的旧 run → 视为可用（**向后兼容，历史 pilot 数据不受影响**）；
`meta.json` 存在但不可解析 → 保守排除。S11 同时验证这三条。

## B6. 自检与干净克隆

| 套件 | 本地（有 numpy） | 干净克隆（有 numpy） | 无 numpy |
|---|---|---|---|
| `failure_class_selftest` | **31/31** | **31/31，0 跳过** | 30 通过 / 1 跳过（S11 需 numpy） |
| `recipient_derivation_selftest` | 30/30 | 30/30 | 26 通过 / 4 跳过（A 组需 numpy） |
| `reporting_patch_selftest` | 全通过 | 全通过 | 全通过 |

干净克隆：`git clone --single-branch`（只含已跟踪文件，0 项未跟踪）后直接跑，无需任何
本地残留。新增用例 S9（两种时序）/ S10（双重失败）/ S11（拟合侧排除），共 3 条，均在
用户授权范围内。

## B7. 已知限制（记录，不再扩展）

1. **F7 只覆盖可捕获的异常路径**：断电、OOM killer、进程被 SIGKILL 时 `finally` 不执行，
   仍可能丢记录。此类情形须靠链上钱包状态反查，不属本轮可解范围。
2. **中止 run 的 `verify_run_artifacts` 会判不一致**（sidecar 多、CSV 少）——这是**正确**
   的拒绝行为，识别中止 run 一律靠 `meta_stage` / `usable_as_sample`，不要用
   `verify_run_artifacts` 去判「记录完整」。
3. **中止 run 的 `gate_summary.csv` 缺失**，汇总须从 `rounds.csv` 重算。
4. 本轮**未执行真实 `--dry-run`**（涉及快照恢复与服务重启），异常路径行为全部由 stub
   注入验证——真实环境下的磁盘错误未被实际触发过。

## B8. 提交

`a0ecbda`：`confirmatory_bench.py`（+85/−8）、`failure_class_selftest.py`（+159）、
`fit_sapling_e2e_model.py`（+31）。PR #24 保持 open，未合并，未进 `origin/main`。

---

# 附三：F7 验收结论与代码冻结（2026-10-30 15:09，用户裁定后补）

本附三只固化**审查结论**，不改任何 `.py`、不改冻结稿 `sapling_e2e_f5_error_classification_design_20261030.md`、
不改预注册、不触碰历史 run 目录。它本身是文档追加，不构成代码变更。

## C1. F7 验收：六项授权要求逐项通过

| 验收项 | 实现位置 | 验证方式 | 结果 |
|---|---|---|---|
| 抽取 CSV 落盘函数 | 新函数（纯抽取，无逻辑变更） | 与 HEAD 内联块逐字节比对 | 通过，803 字节完全一致 |
| 正常路径行为与结果不变 | 同上 | 字节级等价 + `COLUMNS` 36 列全等 | 通过 |
| 异常路径保留此前成功记录 | `main()` 的 `finally` 分支 | S9 两种中止时序 | 通过 |
| sidecar 失败仍立即终止 | 未改动该路径 | S10 双重失败 | 通过 |
| CSV 补写失败不覆盖原始异常 | 补写包独立 try，只记 `csv_flush_error` | S10 断言对外异常仅含 sidecar 原因 | 通过 |
| 中止 run 不作为正式样本 | `mark_run_aborted` 写 `usable_as_sample=False`；拟合侧守卫 | S9 + S11 | 通过 |

第二种故障注入（两条成功 + 两条失败记录在 sidecar 写失败后仍全部保留，且 `attempt_id` 关联关系
双向可查）是本轮最关键的证据：它证明「已完成尝试」不会因后续写入失败而整体丢失。

## C2. 「异常路径不生成 `gate_summary.csv`」——正式结论：认可，不改代码

**判定：这是显式设计，不是遗漏，也**不是**遗留缺陷。**

三条理由（按重要性排序）：

1. **语义诚实性。** `gate_summary.csv` 是「本轮已完成」的完成态产物。中止 run 若也产出它，
   几周后的自己或外部审阅者会把「跑完的汇总」当成事实，而真正的事实是「跑到一半停了」。
   `rounds.csv` 是逐条流水，缺行本身就是未完成的自证；汇总不是。
2. **信息不损失。** 汇总可由 `rounds.csv` 无条件重算（纯派生，无需任何运行期状态）。
   少一个汇总，只是少一个缓存；多一个伪造完整的汇总，才是丢信息。
3. **与 G4 / G6 同一条纪律。** 宁可留下「不完整但真实」的证据，也不产出「完整但可能被误读」的产物。

落码事实（可核对，不是自述）：`main()` 中汇总只在正常完成路径写出；`except BaseException`
分支只调用 `mark_run_aborted(...)` 后原样 `raise`，异常路径下 `write_gate_summary` 根本不可达。
因此「没有汇总」是流程决定的必然结果，而非条件判断写错。

**判据口径（重要，避免后续误用）：** 识别中止 run 的唯一权威口径是 `meta.json` 中的
`meta_stage == "run_aborted"` / `usable_as_sample == False`；`fit_sapling_e2e_model.py` 已据此排除。
**不得**用「`gate_summary.csv` 是否存在」去反推 run 是否中止——缺汇总只是症状，不是判据
（正常完成的旧 run 若因其他原因缺汇总，同样会误导）。

## C3. 三方 SHA 独立复核（本轮只读，未做任何环境操作）

| 位置 | SHA | 获取方式 |
|---|---|---|
| 本地 `HEAD` | `0c5d7a1` | `git rev-parse HEAD` |
| 远端分支 `experiments/e2e-testnet-tx-harness` | `0c5d7a1` | `git ls-remote origin`（网络实测，非读缓存 ref） |
| `origin/main` | `1fb6cc1` | 同上，且 `merge-base --is-ancestor` 判 HEAD **未**入 main |
| PR #24 head | 未独立查询 | 本机无 `gh`，无法直接读取 PR 元数据 |

PR #24 的 head 分支即上表远端分支，故按分支 SHA 认定为 `0c5d7a1`；这一条是**推断**，
不属独立核验。工作区未跟踪项仅 `a_prime_selftest.py`、`a_note_scan_diag.py`（依赖运行中节点，
属在线诊断，不入仓）。

## C4. 代码冻结声明

- **冻结基线**：`0c5d7a1`（本附三的父提交）。
- **冻结对象**：`confirmatory_bench.py`、`fit_sapling_e2e_model.py`、三套自检脚本、
  冻结稿 §1–§15、预注册 §1/§4.2。此后不再有代码提交，也不再新增 F8/F9 或扩大自检范围。
- **允许的唯一改动类型**：文档追加（本记录、最终实验报告）。
- **解冻条件**（唯一）：真实 `--dry-run` 或 gate 暴露**影响实验正确性 / 证据完整性 / 可复现性**
  的真实缺陷，且须单独立项授权。风格、命名、可读性、覆盖率等一律记为已知限制，不触发解冻。
- 已知限制清单以 B7 为准，冻结期内不再增补。

## C5. 当前工程状态与下一入口

已具备：① Sapling proving 性能剖析与优化；② 端到端耗时/内存测量；③ 失败分类 + 证据留存 +
中止保护；④ 离线自检 + 干净克隆复现；⑤ 明确的 gate 与正式实验边界。

**下一入口只有一个动作**：在单独授权后 → 恢复冻结快照 → 重核六项（快照 SHA、脚本 SHA、
`addresses` 38、`notes` 36、余额 `11999980000`、高度 `32297`）→ 在**独立 run 目录**执行
`--mode gate --dry-run`。dry-run 通过后再单独决定是否启动新 gate。本轮**未执行任何环境操作**。

---

# 附四：真实环境 dry-run 执行记录（2026-10-30 15:15–15:17）

**授权范围**：第一阶段真实环境 `--dry-run`。第二阶段真实 gate **未授权**，本轮未启动。
**代码冻结仍然有效**：本附四为文档追加，`git diff` 对 `*.py` 为空；未改冻结稿、预注册、历史数据。

## D1. 前置：六项状态独立重核（不采信恢复脚本的打印）

恢复命令 `snapshot_restore.sh --yes <frozen snapshot>`（15:15:22 起，6s 完成）。随后用独立只读脚本
重新计算，**没有**读恢复脚本的输出作为结论：

| # | 项目 | 实测 | 期望 | 结果 |
|---|---|---|---|---|
| 1 | 快照 SHA256 | `ca35201887b8041b…` | `ca352018…b09510c` | PASS |
| 2 | 恢复脚本 SHA256 | `2df7cd8bd4890963…` | `2df7cd8b…a720e11` | PASS |
| 3 | 链高（`getblockchaininfo`） | 32297 | 32297 | PASS |
| 4 | 可花费 Note 数（钱包 DB 只读） | 36 | 36 | PASS |
| 5 | 余额（DB 求和） | 11999980000 | 11999980000 | PASS |
| 6 | `addresses` 表行数 | 38 | 38 | PASS |
| 附 | `z_getnotescount.sapling` == DB 条数 | 36 == 36 | 相等 | PASS |
| 附 | `z_getbalanceforaccount` == DB 求和 | 11999980000 | 相等 | PASS |

四个量两两一致（DB 条数 / DB 金额 / 两个 RPC），说明清单完整、无截断——这正是 A′ 要防的
「能跑但错」。**8/8 通过。**

## D2. 执行与产物

- run 目录：`raw/confirmatory_20261030/_feasibility_gate/run_20261030_151545/`（新建，独立目录）
- argv：`confirmatory_bench.py --mode gate --dry-run`（policy=FullPrivacy，restore=True）
- `meta.json`：`dry_run=True`、`real_tx=False`、`restore_enabled=True`、`meta_stage=run_end`、
  快照/脚本哈希 `match=True`
- 每形态各 1 次恢复，共 **10 次**；单次恢复 **7.9–8.1s**（regtest 钱包追平极快）
- `rounds.csv`：36 列、10 行；`dry_run=1` 10 行；**带 txid 的行 0 条**
- `errors.jsonl`：**不存在**（0 条失败 → 惰性创建，`verify_run_artifacts` 判「失败轮=0 / sidecar 行=0」一致）
- `gate_summary.csv`：10 行，note 统一为「dry-run：地址准备与构造已完成，未发交易（无 txid 属预期；
  L3 未覆盖，不构成形态可行性证据）」

## D3. 逐形态计划（全部自洽）

| 轮 | (S,O) | 收款数 | 计划金额 zat | 预留手续费 | 5000·max(S,O) | note 数 |
|---|---|---|---|---|---|---|
| 1 | (1,2) | 1 | 249,870,000 | 10,000 | 10,000 ✓ | 36 |
| 2 | (2,2) | 1 | 549,870,000 | 10,000 | 10,000 ✓ | 36 |
| 3 | (4,2) | 1 | 1,149,860,000 | 20,000 | 20,000 ✓ | 36 |
| 4 | (7,2) | 1 | 2,062,345,000 | 35,000 | 35,000 ✓ | 36 |
| 5 | (10,2) | 1 | 2,999,830,000 | 50,000 | 50,000 ✓ | 36 |
| 6 | (17,2) | 1 | 5,187,295,000 | 85,000 | 85,000 ✓ | 36 |
| 7 | (1,9) | 8 | 249,835,000 | 45,000 | 45,000 ✓ | 36 |
| 8 | (3,2) | 1 | 849,865,000 | 15,000 | 15,000 ✓ | 36 |
| 9 | (3,3) | 2 | 849,865,000 | 15,000 | 15,000 ✓ | 36 |
| 10 | (4,3) | 2 | 1,149,860,000 | 20,000 | 20,000 ✓ | 36 |

`收款数 = O−1` 全部成立；`手续费 = 5000·max(S,O)` **10/10 相符**；每轮 note 数均为 36
（恢复后状态可复现）。金额边界由 `verify_state` 打印，10 轮全部落在合法区间。

## D4. 覆盖边界：dry-run 证明了什么、没证明什么

- **已覆盖（10/10 通过）**：快照恢复可重复（10 次）、六项状态核验、金额边界构造、
  `O−1` 个互不相同 Sapling-only UA 的派生、L1 去重 / L1.5 账户地址集合一致性 / L2 receiver 校验、
  前置同步、36 列与 sidecar 的产物契约。
- **未覆盖（脚本自己在日志里声明，不是事后解释）**：**L3 — `z_sendmany` 是否接受该多地址组合**。
  dry-run 不发交易，因此**不构成任何形态可行性证据**。

### 这一条对 gate 授权的实际含义（重要，务请注意）

查历史 gate 的 `rounds.csv`：`run_20261030_110042` 是唯一有真实 tx 成功的一轮，成功形态是
**全部 O=2（单收款地址）**；其 O∈{3,9} 三格失败于 `-8 duplicated recipient address`，且该轮
`diversifier_indices` 列全空——也就是说它用的是 `[from_ua]*n_recip` 的重复地址，**不是**派生地址。

结论：**多收款形态（`(3,3)`、`(4,3)`、`(1,9)` 共 3 格）从未被 `z_sendmany` 接受过。**
gate 将是这条路径的**第一次真实检验**，且按 G1 口径，失败即如实记录、不重试、不改规则。
这不是缺陷，但必须在授权前说清楚：**gate 有真实概率在这 3 格上给出否定结果**，
而否定结果同样是有价值的结论（`O>2` 在该钱包/RPC 版本下不可行）。

## D5. 不改动证明

- `run_20261030_110042/` 全文件指纹前后一致：`f07542a2639b5198a7b4ee6934b0ba8bdc604ed8820e44c053b19d5fae27ad7b`。
- 预注册、冻结稿、所有历史 run 目录均未写入；本轮唯一新增目录是 `run_20261030_151545/`。
- 服务侧：恢复脚本按设计把旧 `data` 改名为 `data/*.bak.20261030_1515xx`（未删除），快照解包覆盖。

## D6. 观察到的事实（记录，不作结论）

1. **派生 index 游标继续单调上升**：本轮 10 轮为 4610670495 → 4610670568，与代码注释记载的
   「无参派生游标不受快照恢复约束」一致。**不影响测量**（index 不参与构造与计时），但再次确认
   「每轮钱包状态完全一致」这句话不能写进报告。
2. **派生跳过率**：10 轮共尝试 **39 次**派生、得到 **19 个**地址（3,1,1,2,3,1,22,1,2,3，对应地址数
   1,1,1,1,1,1,8,1,2,2）；其中 `(1,9)` 一格用了 22 次才凑到 8 个地址（预算 64）。与既往
   「约 53% 跳过」的观测同量级。
3. **第二次 dry-run 结果一致**：同日 11:30 的 `run_20261030_113002` 也是 `--dry-run`，同样 10 形态、
   0 失败；本次是**独立第二次**，两次结论一致，说明该路径可重复。
4. `errors.jsonl` 惰性创建：0 失败时文件不存在。`verify_run_artifacts` 已按「失败轮数 == sidecar 行数」
   判定一致，故不构成证据缺口；但若首次失败时磁盘不可写，该次失败记录会随 run 中止一并缺失
   （已知限制 B7 第 1 条的弱化版），**记录在案，不在冻结期修改**。

## D7. 本轮结论

dry-run **通过**：环境可恢复、状态可核验、10 个形态的构造与地址准备全部成立、产物契约与
36 列口径未被破坏、历史数据未被触碰。真实 gate 的第一阶段前置条件已满足。

**但 gate 的实际不确定性集中在 L3**（多收款形态从未被接受过），授权时应对否定结果有预期。
