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
