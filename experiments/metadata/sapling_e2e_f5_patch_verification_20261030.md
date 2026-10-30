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

1. **`reporting_patch_selftest.py` 存在陈旧断言**：第 122 行仍断言 F1 之前的 dry-run 文案 `dry-run：未发交易，仅验证构造`，而 `247f855` 已改成 `dry-run：地址准备与构造已完成…`。即该用例**自 247f855 起就是失败的**，上一轮「自检全绿」的结论因此不成立。已就地修正断言（该文件仍未入仓）。
2. **`failure_class_selftest.py` 的 I6 原设计不可执行**：想用历史 dry-run 目录逐行复现 note，但那个 run 产出于 F1 之前，note 是旧口径。改为「列结构全等 + 当前口径复现 + 显式承认旧口径差异」三段断言。
3. **三个测试辅助文件仍未跟踪**：`recipient_derivation_selftest.py`、`reporting_patch_selftest.py`、`a_prime_selftest.py`、`a_note_scan_diag.py`、`raw/confirmatory_20261030/`。本轮只提交了 `failure_class_selftest.py`（T1 第 13 项）。是否把其余文件入仓需单独决定；S7 已加守卫，缺 `reporting_patch_selftest.py` 时 SKIP 而非报错。

---

## 9. 未做的事

- 未执行真实 `--dry-run`（会触发快照恢复 + 服务启动）；S7 与 reporting T1 用 stub 覆盖了同样的流程分支。
- 未发任何交易、未启动 `--mode gate`、未恢复快照。
- 未修改预注册、未修改历史 run 目录、未重分类历史 `failure_class`（§7 口径声明继续有效）。
- 未把 `recipient_derivation_selftest.py` / `reporting_patch_selftest.py` 入仓。

---

## 10. 下一步（均需单独授权）

1. 新正式 gate：须先恢复冻结快照并重新核验六项（快照 SHA、脚本 SHA、addresses 38、notes 36、余额 11999980000、高度 32297），且新 run 独立目录、不覆盖 `run_20261030_110042/`。
2. 决定是否为三个测试辅助文件单独开一个 docs/test 提交。
3. T3（`failure_class` 中 `opid_timeout` 是否改名）仍未裁定；当前实现按 §6.4 R3 取 `opid_timeout`，若要保留旧名只需改 `CLS_OPID_TIMEOUT` 一处常量。
