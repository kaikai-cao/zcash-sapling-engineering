# Sapling E2E —— F5 失败分类规则与下一轮 gate 证据要求（冻结版 v1）

- 版本：**冻结版 v1**，2026-10-30 14:4x（本地）
- 状态：规则冻结，**代码未实施**。代码库仍为 `2eb6442`，**未改代码、未发交易、未启动 gate**
- 冻结内容：§4 分类规则 + §5 不变量 + §8 G1–G7 + §9 重试边界 + §10 人工替换流程 + §12 样本字段
- 冻结方式：本文件提交入仓，作为下一轮 gate 的规则依据；依 G7，**冻结后不得事后修改**，如需修改须另起 v2 并写明触发原因与生效范围，**不得追溯适用于已完成的 run**
- 对象：`experiments/e2e_testnet_tx/confirmatory_bench.py`（`send_frozen` / `_classify` / `fail_row` / `_summary_note` / 主循环）
- 关联：`sapling_e2e_final_code_review_20261030.md`（F5 登记处）、`sapling_e2e_gate_deviation_20261030_110042.md`（3 条失败的真实记录）、`sapling_e2e_regtest_confirmatory_preregistration_20261030.md`

---

## 0. 结论摘要

| # | 结论 | 影响 |
|---|---|---|
| 1 | F5 的危害大于初判。不是「个别样本被误标」，而是**发送阶段的一切失败都会被标成 `rpc_policy_rejected`** | 任何 `z_sendmany` 失败都被读成「策略拒绝」，进而可能被读成「该形态在 FullPrivacy 下不可行」 |
| 2 | 权威码表已取得（zallet 源码），`-6 = WalletInsufficientFunds` **确认** | 可进入设计，但**必须结合 message 判断**，不能只认 code（§2.2） |
| 3 | `z_sendmany` 的**资金不足很可能以 `-4` 出现**：`propose_transfer` 失败被映射为 `LegacyCode::Wallet`（-4），而非 `-6` | 资金不足需按 **code + message 双条件**识别 |
| 4 | **`-8` 同时承载「参数错误」和「隐私策略拒绝」**：`impl From<IncompatiblePrivacyPolicy>` 用的就是 `InvalidParameter` | 按 code 无法区分；报告不得声称「策略拒绝率可由 code 统计」 |
| 5 | 第二个误判实例：`operation timeout (policy=FullPrivacy)` 因括号内含 `policy` 被判为策略拒绝 | 超时被记成策略拒绝，**污染计时口径**（超时样本本应被剔除） |
| 6 | 判定改为「**阶段 → 码 → 文本**」三层，`rpc_policy_rejected` 从默认值改为**需举证标签** | 与 F1 同源：不让带倾向性的默认标签替实验下结论 |
| 7 | 分类器只写**事实层**，不写解释层（§4.10） | 归因降级为需举证的结论 |
| 8 | 「**RPC 拒绝**」与「**提交状态不明**」必须彻底分开（§9） | 新增 `submit_state` 三态，作为重试边界的唯一技术前提 |
| 9 | 「未截断原文」成为硬要求，原「不加列」建议作废 | 改走 sidecar `errors.jsonl`：主 CSV 36 列不变，原文不截断另存（§4.9） |
| 10 | 替换为**人工触发**，脚本内不自动重试 | 复用现有 `--matrix`，替换在独立 run 目录完成，主循环零改动（§10） |

**与 F1 的关系**：F1 修的是「地址准备失败 → 被读成形态不可行」；F5 是同一类错误的第二处——「发送失败 → 被读成策略不可行」。共同病根是**失败标签的默认值带有归因倾向**。

---

## 1. 证据

### 1.1 权威码表（A 级：源码）

`zallet-core/src/components/json_rpc/server/error.rs`（zcash/zallet，`main` 分支，2026-10-30 取得，**未固定 commit**）：

```rust
/// Bitcoin RPC error codes
/// Drawn from <.../src/rpc/protocol.h#L32-L80>.
#[derive(Default, Debug)]
pub enum LegacyCode {
    Misc = -1,                       ForbiddenBySafeMode = -2,
    Type = -3,                       InvalidAddressOrKey = -5,
    OutOfMemory = -7,                InvalidParameter = -8,
    Database = -20,                  Deserialization = -22,
    Verify = -25,                    VerifyRejected = -26,
    VerifyAlreadyInChain = -27,      InWarmup = -28,
    // Wallet errors
    Wallet = -4,                     /// Unspecified problem with wallet
    WalletInsufficientFunds = -6,    /// Not enough funds in wallet or account
    WalletAccountsUnsupported = -11, WalletKeypoolRanOut = -12,
    WalletUnlockNeeded = -13,        WalletPassphraseIncorrect = -14,
    WalletWrongEncState = -15,       WalletEncryptionFailed = -16,
    WalletAlreadyUnlocked = -17,     WalletBackupRequired = -18,
}

impl From<LegacyCode> for ErrorCode {
    fn from(code: LegacyCode) -> Self { Self::ServerError(code as i32) }
}
```

zallet 显式声明沿用 zcashd 码表，数字可直接引用。**这是 `-6` 语义的正式来源**。

### 1.2 实测数据点（A 级：本项目真实运行）

| 数据点 | code | message 特征 | 来源 |
|---|---|---|---|
| 门禁 3 条失败 | `-8` | `Invalid parameter, duplicated recipient address: uregtest1...` | `run_20261030_110042/rounds.csv` |
| 地址派生探测 | `-4` | `cannot generate an address with the requested receivers` / `was already generated with different receiver types` | `sapling_e2e_address_derivation_probe_20261030.md` |

两个实测点与 §1.1 码表语义一致，说明码表对该版本 `zallet-v0.1.0-beta.3` 成立。

### 1.3 二进制旁证（B 级）

`zallet-v0.1.0-beta.3-linux-amd64/zallet-zebra` 内的字符串：

| 字符串 | 意义 |
|---|---|
| `Invalid parameter, duplicated recipient address: ` | 与实测错误逐字一致，确认被测二进制即产出该消息的版本 |
| `err-privpol-no-privacy-not-allowed`、`err-privpol-fully-transparent-not-allowed` 等 9 个 | **真正的策略拒绝有专属消息族**，可据此刻意区分 |
| `Insufficient funds for transaction construction; need an additional `、`Insufficient balance (have `、`Insufficient funds: required ` | 资金不足有多种措辞，跨版本可能变化 |

旁证作用：证明「策略拒绝」在消息层可识别，**但依据是 `err-privpol-*` 措辞，不是子串 `policy`**。

---

## 2. 三个结构性发现

### 2.1 `-8` 是「参数错误」与「隐私策略拒绝」的共用码

`payments.rs`：

```rust
impl From<IncompatiblePrivacyPolicy> for ErrorObjectOwned {
    fn from(e: IncompatiblePrivacyPolicy) -> Self {
        LegacyCode::InvalidParameter.with_message(match e {
            IncompatiblePrivacyPolicy::NoPrivacy => fl!("err-privpol-no-privacy-not-allowed", ...),
            ...
        })
    }
}
```

策略拒绝返回 **`-8`**，与「地址重复」「amounts 为空」「memo 超长」**同一个码**。推论：

- 「策略拒绝率」**不可**由 code 统计；
- 不可用子串 `policy` 判定——`privacyPolicy` 参数名会出现在**所有**策略相关消息里，包括 `err-privacy-policy-unknown`（策略名拼错，属**参数错误**）。

### 2.2 资金不足有两条路径，code 不同

```rust
.map_err(|e| {
    LegacyCode::Wallet.with_message(fl!("err-propose-transaction-failed", error = e.to_string()))
})
```

而 `Wallet = -4`。资金不足发生在提案阶段时，表现为 **`-4` + `Insufficient funds for transaction construction; ...`**，**不是 `-6`**。

`-6` 语义明确，但本项目 z_sendmany 路径**尚无实测样本**证明会走 `-6`。

**结论**：资金不足判据必须是 **`code ∈ {-4, -6}` 且 message 命中资金措辞**。这正是「`-6` 认可进入设计但必须结合消息判断」的技术依据。

### 2.3 当前判定顺序让「策略拒绝」成为默认值

```python
def _classify(err):
    e = err.lower()
    if "被拒" in e or "policy" in e:
        return "rpc_policy_rejected"
    ...
```

而 `send_frozen` 把所有 `z_sendmany` 异常包成同一前缀：

```python
except RuntimeError as e:
    raise PreTxError("policy=%s 被拒: %s" % (policy, str(e)[:200]))
```

前缀同时含 `policy=` 与 `被拒`，第一个分支**无条件命中**。分类器看到的不是错误本身，而是包装语。

---

## 3. 当前判定矩阵（用真实 `_classify()` 实测，非推演）

| 输入（错误文本） | 当前分类 | 应为 |
|---|---|---|
| `...被拒: z_sendmany -> {"code": -8, "message": "Invalid parameter, duplicated recipient address: ..."}` | `rpc_policy_rejected` | ✗ 参数错误（地址重复） |
| `...被拒: z_sendmany -> {"code": -6, "message": "Insufficient funds"}` | `rpc_policy_rejected` | ✗ 资金不足 |
| `...被拒: z_sendmany -> {"code": -4, "message": "cannot generate an address"}` | `rpc_policy_rejected` | ✗ 钱包错误 |
| `...被拒: z_sendmany -> {"code": -8, "message": "Privacy policy ... not allowed"}` | `rpc_policy_rejected` | ✓（**巧合**：靠 `policy=` 前缀命中，非识别策略） |
| `operation timeout (policy=FullPrivacy)` | `rpc_policy_rejected` | ✗ 超时 |
| `operation failed: {"code": -6, "message": "Insufficient funds"}` | `opid_terminal_failed` | △ 阶段对，资金语义丢失 |
| `operation failed: {"code": -1, "message": "boom"}` | `opid_terminal_failed` | ✓ |
| `查询 opid 状态失败: Connection refused` | `other` | ✗ 应为传输错误 |
| `前置同步超时` | `env_transient_sync` | ✓（靠「同步」命中，非靠 timeout） |

**读法**：凡进入 `send_frozen` 的失败，一律 `rpc_policy_rejected`。这不是「部分样本失真」，而是**该路径上的失败样本整体不可用于原因统计**。

---

## 4. 分类规则（冻结）

### 4.1 设计原则

| 原则 | 落地方式 |
|---|---|
| 优先解析结构化 JSON-RPC 错误 | `send_frozen` 改用同文件已有的 `z_raw()` 取 `(result, error)`；`_classify` 优先读属性，不读字符串 |
| 不把所有 `z_sendmany` 错误称为策略拒绝 | 删除 `policy=%s 被拒` 包装语；异常消息只记录事实（阶段 + code + RPC 原文） |
| 保留原始文本与 code | 异常持有 `code:int`、`raw_error:dict`（**原对象，不截断**）、`stage`；CSV 的 `error` 列沿用截断文本以保持列格式兼容，未截断原文另存 sidecar（§4.9） |
| 不改策略 / 不加 fallback / 不改行为 | `z_sendmany` 的 params 逐字节不变；仍只用 `FullPrivacy`；失败仍 `return row, None` |
| 用真实错误回放验证 | §6.1 用 3 条历史错误原文 + §6.3 传输层 mock |

### 4.2 唯一标识：`attempt_id`

- 定义：`attempt_id = "<run_id>:<round>"`，`run_id` 为 run 目录名（如 `run_20261030_110042`），`round` 为 `rounds.csv` 首列（自增、不复用）。
- **sidecar 一律通过 `attempt_id` 关联主 CSV，不依赖行号**——替换尝试或追加记录会导致行号漂移。
- 替换 run 有自己的 `run_id`，`attempt_id` 天然不冲突。

### 4.3 阶段命名（统一；本次先统一 `stage`，`failure_class` 命名见 T3）

| `stage` | 含义 | 产生位置 |
|---|---|---|
| `prep` | 收款地址派生与校验 | `prepare_recipients` |
| `state` | 快照恢复与状态核验 | `restore_snapshot` / `verify_state` |
| `sync` | 前置同步等待 | `wait_sync` |
| `submit` | `z_sendmany` 调用 | `send_frozen` |
| `status_poll` | `z_getoperationstatus` 查询 | `send_frozen` |
| `opid_failed` | 操作终态 `failed` | `send_frozen` |
| `opid_timeout` | 轮询超时 | `send_frozen` |

`stage` 是 sidecar 的**事实字段**；`failure_class` 是其上的**分类标签**。两者分层，不混用。T3 只涉及「`failure_class` 中原 `timeout` 是否改名」，与本节无关。

### 4.4 三层判定优先级

```
第 1 层  阶段判别（不看文本）
         stage=opid_timeout           -> opid_timeout
         stage=submit + transport     -> rpc_transport_error
         stage=status_poll + transport-> rpc_transport_error

第 2 层  code 映射（表驱动，见 4.5）
         code 已知 -> 对应类别；code 未知 -> rpc_error_<code>（保留原码，不猜语义）

第 3 层  仅当 code 为 None 且非传输非超时，才退回文本判定
         「策略拒绝」不参与文本兜底 —— 无 code 时不得标 policy_rejected
```

第 1 层置于最前，直接消灭 §3 中「超时被判策略拒绝」这一类错误：超时由阶段决定，与文本内容无关。

### 4.5 `failure_class` 取值表

| 条件 | 新值 | 说明 |
|---|---|---|
| `stage=opid_timeout` | `opid_timeout` | 原 `timeout`；改名与否见 T3 |
| 传输层异常（任一阶段） | `rpc_transport_error` | 新增 |
| `code=-8` 且 message 命中 `duplicated recipient address` | `rpc_duplicated_recipient` | **从 `-8` 独立**。语义**仅为**「重复收款地址导致 RPC 拒绝」这一事实；**不得**写成「执行器未去重」，那须由 `recipients` 字段另行证明（§4.10） |
| `code=-8` 且 message 命中 `err-privpol-*` 措辞 | `rpc_privacy_policy_rejected` | **唯一**允许表达「策略」的类别 |
| `code=-8`（其余） | `rpc_invalid_parameter` | 参数错误 |
| `code=-4`/`-6` 且 message 命中资金措辞 | `rpc_insufficient_funds` | 见 §2.2，双条件 |
| `code=-4`（其余） | `rpc_wallet_error` | |
| `code=-5` | `rpc_invalid_address_or_key` | 码表已确认 |
| `code=-32602` | `rpc_request_schema_invalid` | jsonrpsee 请求 schema 不符 → 执行器传参缺陷 |
| 其它 code | `rpc_error_<code>` | **保留原码，不给语义标签** |
| 无 code、非传输、非超时 | `other` | 兜底，不得升级为带归因的标签 |

**为什么未知码用 `rpc_error_<code>`**：`-20`/`-22`/`-25` 等在码表里语义明确但未实测；保留原码使事后重分类无损，笼统归类会丢掉唯一定位线索。

### 4.6 `-8` 子类细分的稳定性风险

message 是自由文本，跨版本可能改措辞。因此：

- 文本细分只用于**区分 `-8` 子类**，不作为唯一证据；
- 未命中子类特征的 `-8` 一律落 `rpc_invalid_parameter`，**不落 policy**；
- 报告须同时给出 code 分布与子类分布，让读者看到「有多少 `-8` 未被细分」。

### 4.7 与 `_summary_note` 的衔接

分流条件是 `startswith("recipient_")`，新值均不以此开头，故分流逻辑无需改动。但：

- note 对 `rpc_duplicated_recipient` 追加「重复收款地址导致 RPC 拒绝，不代表形态不可行」——与 F1 对 `recipient_*` 的口径一致；
- **不做「执行器未去重」的因果断言**（T4 已定：采用事实描述）。

### 4.8 提交状态三态（`submit_state`）

仅凭 `failure_class` 无法判断「是否可能已提交」，而这一点直接决定能否替换（§9）。

| 状态 | 判定条件 | 含义 | 处置 |
|---|---|---|---|
| `not_submitted` | ① 未调用 `z_sendmany`；② 调用后收到 JSON-RPC error 响应（未拿到 opid） | 交易**未被受理** | 可否替换按 §9 边界 |
| `unknown` | 请求已发出、但未收到任何可解析的 JSON-RPC 响应 | **可能已被受理** | **不得重发**，必须先完成核验 |
| `submitted` | 已拿到 `opid` | 已受理，进入异步执行 | 按 opid 终态/超时处理；**超时不得重发** |

**`not_submitted` 的表述边界**：只陈述「交易未被受理」，**不得**表述为「什么都没发生」。请求可能已触发日志、审计或其它非交易状态变化；执行器无从知晓，报告也不应扩大解释。

`unknown` 的核验步骤（缺一不可，须留痕）：

1. 读钱包 `transactions` 表，比对投递前后最大 rowid / txid 集合是否新增；
2. 比对 Sapling 余额与 note 集（`sapling_zat` + note inventory），确认无新增支出；
3. 查 mempool（`getrawmempool`）是否含可疑交易；
4. 任一歩发现疑似交易 → 用 `z_viewtransaction` 回读确认，按 `submitted` 处理；
5. 四步皆无痕迹，方可判为「可替换」，**核验过程须写入记录**。

设计要点：**「证明未触及提交阶段」本身需要证据**，不能由「没有 txid」或「我以为没发出去」推定。

### 4.9 Sidecar：未截断证据的存放

**三条硬性技术条件（本次冻结新增）：**

**条件 1｜原始错误必须真正原样保留。**

- 在 **RPC 响应解析位置**保存原始 JSON-RPC 错误对象：`z_raw()` 返回的 `error` dict **原对象**挂到异常上（`raw_error: dict | None`），不在中途 `json.dumps` + 截断。
- 传输异常保存 **异常类型 + 原始信息**：`raw_transport = {"type": type(e).__name__, "repr": repr(e), "errno": getattr(e, "errno", None)}`，**不截断**。
- 落盘用 `json.dumps(..., ensure_ascii=False)`，JSONL 天然不截断。
- 明确禁止：只保存 `str(RuntimeError)` 或 `str(e)[:200]`。

**条件 2｜必须通过 `attempt_id` 与主 CSV 一一关联。**

- sidecar 每条记录含 `attempt_id`（§4.2），不使用行号。
- 校验：`{sidecar.attempt_id}` 必须等于 `{rounds.csv 中失败行的 attempt_id}`，双向无遗漏。

**条件 3｜sidecar 写入失败必须阻止实验继续（fail-closed）。**

- 每产生一条失败记录**立即**追加写入 sidecar 并 flush；写入异常 → `raise SystemExit("[fatal] ...")`，与 `confirmatory_bench.py` 现有自洽性校验（`raise SystemExit("[fatal] dry_run=True 却出现…")`）同构。
- 顺序保证：**先写 sidecar，再落 rounds.csv 行**，避免出现「CSV 有失败记录、证据却丢失」。
- 收尾新增 `verify_run_artifacts(rundir)`，校验：① JSONL 每行可解析；② `attempt_id` 双向齐全；③ 行数 == 失败轮数。任一不满足 → `SystemExit`。

> 注：先前稿件写的 `final_check.py` **在本项目中不存在**（那是 PLONK 演示项目的脚本）。本项目的校验一律通过**自检脚本 + 运行时断言**完成，故改为上文的 `verify_run_artifacts()` 与 `failure_class_selftest.py`。

**sidecar 文件与字段**：`<run_dir>/errors.jsonl`，每失败轮一行。

| 字段 | 内容 | 用途 |
|---|---|---|
| `attempt_id` | `<run_id>:<round>` | 关联主 CSV（条件 2） |
| `round` / `run_id` | 分解值，便于人工阅读 | 冗余，便于核对 |
| `stage` | §4.3 七值之一 | 第 1 层依据 |
| `code` | `int` 或 `null` | 第 2 层依据 |
| `raw_error` | **原始 JSON-RPC error 对象（原样）** | 条件 1 |
| `raw_transport` | 异常类型 + repr + errno，或 `null` | 条件 1 |
| `rpc_message` | 从 `raw_error.message` 取出的完整文本 | 子类判定 |
| `submit_state` | §4.8 三态 | 决定能否替换 |
| `z_sendmany_invoked` | `true`/`false` | 区分「未触及」与「被拒」 |
| `opid` | 拿到则记录 | 追溯异步操作 |
| `recipients` | 完整收款地址列表 | 证明重复地址是否存在 |
| `amounts_zat` | 金额列表 | 与 recipients 一一对应 |
| `policy` / `minconf` / `from_ua` | 发送参数 | 证明策略与参数未变 |
| `replaces` | 被替换的 `attempt_id`，或 `null` | 人工替换溯源（§10） |
| `wrapper_text` | 旧包装文本（若存在） | **仅供对照，不得作为分类依据** |

### 4.10 事实层与解释层必须分离

| 层 | 内容 | 由谁产生 |
|---|---|---|
| 事实层 | `code`、`raw_error`、`stage`、`submit_state`、`recipients`、发送参数 | 分类器自动写入，**只陈述发生了什么** |
| 解释层 | 「执行器未去重」「该形态不可行」「策略过严」 | 只能由分析阶段撰写，且须引用事实层证据 |

规则：分类器与汇总 note 的产出物中**不得出现解释层措辞**。`rpc_duplicated_recipient` 是事实层标签，「执行器未去重」是解释层结论，两者不可合并。

---

## 5. 不变量（必须由测试守住）

| # | 不变量 | 守它的方式 |
|---|---|---|
| I1 | `z_sendmany` 的 params 逐字节不变：`[from_ua, amounts, 1, null, "FullPrivacy"]`，且 timeout 仍为 120s | mock `_post`，断言 payload 全等（含键顺序与 `1`/`null` 字面量）与 timeout 实参 |
| I2 | 计时区间不变：`t0` 在调用 `z_sendmany` 之前，`t_submit` 在其返回之后 | 读 diff + 断言 `submit` 字段由同一对 `time.monotonic()` 夹出 |
| I3 | 成功路径 row 字段与统计口径不变 | 用历史成功行（7 条）回放，断言 `tx_success`/`form_match`/`fee_match`/`all_match` 全等 |
| I4 | `COLUMNS` 不变（36 列，前 30 列同序） | 断言 `len(COLUMNS)==36` 且 `COLUMNS[:30]` 与 `2eb6442` 逐项相等 |
| I5 | `recipient_*` 分类不受影响 | 回放地址准备失败路径，断言仍为 `recipient_derivation_failed` / `recipient_validation_failed` |
| I6 | 无 `z_sendmany` 失败时行为与 `2eb6442` 完全一致 | dry-run 路径比对全部字段 |
| I7 | sidecar 行数 == 失败轮数，且 `raw_error` 未经截断 | 构造 message 长度 > 300 的用例，断言落盘长度等于原长 |
| I8 | `attempt_id` 双向齐全 | 运行时 `verify_run_artifacts()` + 用例 S3 |

---

## 6. 测试矩阵（离线，无网络、无交易、不启动服务）

### 6.1 真实错误回放（A 级）

从 `run_20261030_110042/rounds.csv` 取 3 条 `error` 原文：

- 断言 `rpc_duplicated_recipient`；断言 `code == -8`；断言原文仍在 `error` 列。
- 已知限制：历史原文在 200 字符处截断（实测 len=223，地址未完），**不能**从历史文本反推地址；此限制须写入报告。

### 6.2 构造用例（B 级，按源码形态构造）

| 用例 | 构造输入 | 期望 |
|---|---|---|
| 资金不足经提案 | `code=-4`, `"Insufficient funds for transaction construction; need an additional 5000000 zats"` | `rpc_insufficient_funds` |
| 资金不足经 -6 | `code=-6`, `"Insufficient balance (have ...)"` | `rpc_insufficient_funds` |
| 策略拒绝 | `code=-8`, `"Privacy policy: NoPrivacy not allowed here (privacyPolicy)"` | `rpc_privacy_policy_rejected` |
| 参数错误-地址格式 | `code=-8`, `"Invalid parameter, unknown address format: ..."` | `rpc_invalid_parameter` |
| 参数错误-策略名拼错 | `code=-8`, `"Invalid parameter, unknown privacy policy: FooPolicy"` | `rpc_invalid_parameter`（**反向用例**：含 `policy` 但不是策略拒绝） |
| 地址或密钥 | `code=-5` | `rpc_invalid_address_or_key` |
| 未知码 | `code=-9999` | `rpc_error_-9999` |
| 请求 schema | `code=-32602` | `rpc_request_schema_invalid` |

### 6.3 传输层 mock（C 级）

Monkeypatch `_post` 使 `z_sendmany` 抛下列异常，各断言 `rpc_transport_error`、`stage=submit`、**`submit_state=unknown`**：

- `ConnectionRefusedError`
- `socket.timeout` / `TimeoutError`
- `http.client.RemoteDisconnected`
- `json.JSONDecodeError`（服务端返回非 JSON：请求确已到达，必须 `unknown`）

同时断言：不产生 `txid`、不写 `opid`。

### 6.4 回归用例

| 用例 | 期望 |
|---|---|
| `前置同步超时` | `env_transient_sync`（不变） |
| `operation failed: {"code": -1, ...}` | `opid_terminal_failed`（不变） |
| `operation timeout (policy=FullPrivacy)` | `opid_timeout`（**改进**：原为 `rpc_policy_rejected`） |
| 地址准备失败 | `recipient_derivation_failed`（不变，I5） |

### 6.5 明确不测什么

- 不通过真实 RPC 制造 `-6`/`-5`/`-32602`（需发请求/交易，超出本轮边界）；
- 因此 §6.2 全部为**按源码构造**，证据等级 B，报告须标注「未在真实环境复现」；
- 不验证 `-8` 子类在其它 zallet 版本上的稳定性。

### 6.6 自检脚本

新增 `failure_class_selftest.py`（沿用 `recipient_derivation_selftest.py` 模式：纯离线、逐条 `PASS/FAIL`、失败退出码非 0）：

| 组 | 编号 | 覆盖 |
|---|---|---|
| 构造 | C1–C8 | §6.2 码映射与子类判定（含反向用例） |
| 回放/回归 | R1–R4 | §6.1 + §6.4 |
| 不变量 | I1–I8 | §5 八项 |
| 状态与证据 | S1–S6 | 见下 |

| 编号 | 用例 | 期望 |
|---|---|---|
| S1 | submit 阶段传输异常 | `submit_state=unknown`，且判定为不可替换 |
| S2 | `z_sendmany` 返回 -8 | `submit_state=not_submitted`、`z_sendmany_invoked=true` |
| S3 | sidecar 完整性 | 行数 == 失败轮数，`attempt_id` 双向齐全，JSONL 每行可解析 |
| S4 | 超长 message（>300 字符） | `raw_error.message` 落盘长度等于原长 |
| S5 | sidecar 写入失败（mock 抛 OSError） | 进程以 `SystemExit` 终止，**不**继续写 rounds.csv |
| S6 | 人工替换记录 | `replaces` 指向原 `attempt_id`，原记录仍在原 run 目录 |

---

## 7. 对历史数据的影响声明

1. **历史 `failure_class` 不可重分类后复用。** `run_20261030_110042` 的 3 条 `rpc_policy_rejected` 应理解为「发送阶段失败，具体原因未正确记录」；正确原因只能从 `error` 原文读出。
2. `gate_summary.csv` 中按 `failure_class` 的聚合，**不得**用于「策略拒绝率」等表述。
3. 历史 `error` 列在 200 字符处截断，但 `code` 位于文本开头未丢失，3 条失败**仍可**人工判定为 `-8`。
4. 该截断对下一轮不再存在（§4.9）；历史 run 无 sidecar，属不可补救的既有局限，报告须注明。
5. 新旧 `failure_class` **不可混算**，分析脚本须按 run 目录区分口径。

---

## 8. 冻结规则 G1–G7

| 编号 | 规则 | 技术落地 |
|---|---|---|
| G1 | 不要求 gate 达到 10/10 | 通过判据见 §11，按「记录完备性」判定 |
| G2 | 每条尝试必须可追溯，失败不得被覆盖 | `attempt_id` 为唯一标识；被替换尝试**永久保留**在原 run 目录，不删除、不改写 |
| G3 | 触及 `z_sendmany` 并收到拒绝，不得重试 | `submit_state=not_submitted` 且 `z_sendmany_invoked=true` → 计入失败样本，禁止替换 |
| G4 | 提交状态不明，不得直接重新发送 | `submit_state=unknown` → 先执行 §4.8 五步核验；核验未通过则停止 |
| G5 | 只有能证明未触及交易提交阶段的环境失败，才允许最多替换一次 | `z_sendmany_invoked=false`，或核验后确认无遗留交易；每形态上限 1 次 |
| G6 | Gate 通过 ≠ 正式实验通过 | §11 两概念分离，汇总须分别标注 |
| G7 | 不得事后改变形态、成功标准和失败处理规则 | 三者随本文件一并冻结 |

**G4 是执行器硬约束，不是报告注意事项**：`submit_state` 必须由执行器计算并落盘，`unknown` 状态下执行器拒绝自动继续；任何替换须人工确认。

---

## 9. 重试边界（五类，按失败阶段划分）

| # | 失败阶段 | 是否允许重试 | 记录要求 | 技术前提 |
|---|---|---|---|---|
| 1 | 地址派生失败 | **不进入交易提交阶段**，属准备阶段失败；是否重新派生须按预注册预算（64 次/轮）执行 | 派生次数、失败类别 | 走 `recipient_*` 路径，不经 `send_frozen` |
| 2 | 环境准备失败，尚未触及提交阶段 | **有条件允许，最多替换一次** | 原始失败记录必须保留 | `z_sendmany_invoked=false`，或核验后证明无遗留交易 |
| 3 | RPC 明确拒绝 | **不重试** | 保留 code、原始错误对象、发送参数 | `z_sendmany_invoked=true`，`submit_state=not_submitted` |
| 4 | 提交状态不明 | **停止当前实验**，核验前不得继续发送 | 核验过程全程留痕 | `submit_state=unknown` |
| 5 | 已提交（含确认超时） | **不得把确认超时当作发送失败**，也不得直接重发 | 等待并核实交易状态 | `submit_state=submitted` |

**第 3、4 行的区别（本节核心）**：

- 第 3 行：服务端**明确拒绝**了本次请求，未产生 opid。此时**只能说「交易未被受理」**，不得说「什么都没发生」——请求可能已触发日志、审计等非交易状态变化。
- 第 4 行：连响应都没拿到。请求**可能已被受理**，交易可能已在内存池或已上链。若当作环境失败重发，会产生第二笔交易，**破坏实验独立性，并使 `(S,O)` 的 note 消耗无法解释**。
- 第 5 行：已拿到 opid，说明**确定已受理**。确认超时只是「我们还不知道结果」，不是「失败」，更不能据以重发。

因此 G5 的替换前提是：**能证明该次尝试既未触及提交阶段，也未遗留未确认的交易**。仅凭「没有 txid」不足以证明。

---

## 10. 人工替换流程（脚本内不自动重试）

选择人工触发的原因：这是研究实验，不是高可用交易系统。自动重试会扩大主循环与 plan 的改动范围，并增加意外重复发送的风险。

```
原始 gate 执行
   ↓
保留全部成功与失败记录（原 run 目录只读）
   ↓
人工审查环境失败（逐条看 sidecar 的 stage / submit_state）
   ↓
确认未触及提交阶段（§4.8 五步核验，留痕）
   ↓
单独授权替换尝试
   ↓
以独立 run 目录追加记录（新 attempt_id，meta 记 replaces）
```

流程要点：

1. **替换在独立 run 目录完成**，不向原 `rounds.csv` 追加行。原记录永久保留（G2），无需改动主循环与 plan 结构。
2. 复用现有 `--matrix` 参数：替换时传入只含该形态的 CSV（两列 S,O）。
3. 新增 `--replaces <attempt_id>` 参数，写入 `meta.json` 与 sidecar 的 `replaces` 字段，实现机器可读的替换溯源。
4. 替换仍受 G5 限制：**每形态最多一次**；须先人工确认 `submit_state=not_submitted` 且无遗留交易。
5. 替换 run 的 `round` 从 1 重新计数，但 `attempt_id` 因 `run_id` 不同而全局唯一。

---

## 11. 两种「通过」必须分开表述

| 概念 | 定义 | 7/10 时的结论 |
|---|---|---|
| **流程可行性通过** | 流程能产生有效样本，失败记录可信、可追溯、可重算 | 可声称「流程具备可行性」并列出失败类别 |
| **正式实验可用** | 达到预注册要求的有效样本数量与实验条件 | **不能**声称已达正式实验要求 |

禁止的推论：

- 不得由「流程可行性通过」推出「正式实验可用」；
- 不得因某形态在 gate 中失败而**事后降低**其样本要求（如把「每形态 ≥5」改成 ≥3）；
- 不得用 gate 成功率替代正式实验的样本量论证。

---

## 12. 样本最低字段

### 12.1 成功样本

| # | 字段 | 现状 |
|---|---|---|
| 1 | `(S,O)` 形态 + `attempt_id` | 已有（`round`），需补 run_id 组合规则 |
| 2 | 收款地址数量 + 验证结果 | 已有（`recipient_count` / `recipient_validation` / `recipient_receivers`） |
| 3 | `txid` | 已有 |
| 4 | 交易回读结果（`z_viewtransaction`） | 已有 |
| 5 | 金额、手续费 + `form_match` / `fee_match` | 已有 |
| 6 | 完整计时字段（`submit`/`pipeline`/`mine`/`sync`/`total`） | 已有 |
| 7 | 快照恢复、链高、钱包状态检查结果 | 已有（`restored_height` / `restored_note_count` / `restored_sapling_zat` / `snapshot_sha256`） |

结论：成功样本字段在 `2eb6442` 已完备，**F5 不为成功路径新增任何字段**（与 I3 一致）。

### 12.2 失败样本

| # | 字段 | 存放位置 | 现状 |
|---|---|---|---|
| 1 | 失败阶段 | `errors.jsonl: stage` | **新增** |
| 2 | `failure_class` | `rounds.csv` | 已有（分类规则待修） |
| 3 | 原始 RPC code | `errors.jsonl: code` | **新增** |
| 4 | **未截断**原始错误（含原始 error 对象） | `errors.jsonl: raw_error` / `raw_transport` | **新增** |
| 5 | 是否调用过 `z_sendmany` | `errors.jsonl: z_sendmany_invoked` | **新增** |
| 6 | 是否可能已提交交易 | `errors.jsonl: submit_state` | **新增** |
| 7 | 是否发生替换、被替换记录 | `errors.jsonl: replaces` + 原 run 保留 | **新增** |
| 8 | 发送参数摘要 | `errors.jsonl: recipients` / `amounts_zat` / `policy` | **新增** |

第 4 项是本次冻结的硬要求：现有 `str(e)[:200]` 与 `msg[:300]` 双重截断会让事后重分类失去依据。历史 run 无法补救，新 run 必须完整保存。

---

## 13. 停止条件（预先声明，非事后决定）

1. 任一形态连续 2 次 `rpc_transport_error` → 暂停检查服务，不计为形态结论；
2. 出现任一 `rpc_request_schema_invalid`（`-32602`）→ 立即停止，视为执行器传参缺陷，修完重来；
3. 出现任一 `submit_state=unknown` 且五步核验未能证明「无遗留交易」→ **立即停止**，人工确认链上与钱包状态；
4. 累计环境性失败超过轮次数 20% → 停止，判定环境不可用；
5. 钱包真值偏离快照基线（note 数 / 余额 / 高度任一不符）→ 立即停止。

---

## 14. 明确不得得出的结论

1. 不得由 `failure_class` 分布推断「FullPrivacy 策略导致的失败率」——除非全部为 `rpc_privacy_policy_rejected`；
2. 不得把 gate 成功率当作「Sapling 多收款地址可行性」的量化结论；
3. 不得把 `-8 duplicated recipient` 写成「zebra 拒绝多收款地址」——它是参数级去重检查；
4. 不得在 F5 未修的情况下，用新一轮 gate 的 `failure_class` 做原因统计；
5. 不得把 `rpc_duplicated_recipient` 直接解释为「执行器未去重」——须先由 `recipients` 证明存在重复项；
6. 不得把 `submit_state=not_submitted` 表述为「什么都没发生」，只陈述「交易未被受理」；
7. 不得因某形态失败而事后放宽其样本要求或成功标准（G7）。

---

## 15. T1 改动范围（对照 `2eb6442` 实际核对，**不实施**）

### 15.1 文件与函数

| # | 文件 | 位置（`2eb6442` 行号） | 改动 | 类型 |
|---|---|---|---|---|
| 1 | `confirmatory_bench.py` | ~155–175（`PreTxError` 附近） | 新增 `RpcCallError(PreTxError)`、`TransportError`，持有 `stage`/`code`/`raw_error`/`raw_transport`/`submit_state` | 新增 |
| 2 | 同 | 467–495 `send_frozen()` | 改用 `z_raw()`（保留 `timeout=120`）；捕获 `OSError`/`HTTPException`/`JSONDecodeError` → `TransportError(submit_state=unknown)`；删除 `"policy=%s 被拒: "` 包装语 | 重写 |
| 3 | 同 | 805–817 `_classify()` | 三层判定；`rpc_policy_rejected` 仅在 `-8` + `err-privpol-*` 时出现 | 重写 |
| 4 | 同 | 820–822 `fail_row()` | 增加可选 `err` 参数；row 内携带 sidecar 字段 | 改签名 |
| 5 | 同 | 746–752（`run_one` 的 `except PreTxError`） | 传 `err` 给 `fail_row` | 小改 |
| 6 | 同 | 1036–1041、1073–1077（主循环两处 `except`） | 同上；`except Exception` 兜底保留 | 小改 |
| 7 | 同 | 1086 之前 | 新增 `_emit_failure_sidecar(rundir, rec)`，**每失败轮立即写 + flush**，异常即 `SystemExit` | 新增 |
| 8 | 同 | 1121–1126 附近 | 新增 `verify_run_artifacts(rundir)`（JSONL 可解析、`attempt_id` 双向齐全、行数一致） | 新增 |
| 9 | 同 | 970 附近（`argparse`） | 新增 `--replaces <attempt_id>` | 新增 |
| 10 | 同 | 906–922 `COLUMNS` | **零改动**（守住 I4） | 无 |
| 11 | 同 | 473–478（计时区间） | **零改动**（守住 I2） | 无 |
| 12 | 同 | `pick_amount_zat` / `form_match` / `fee_match` / 手续费公式 / `note_inventory_detailed` / `restore_snapshot` | **零改动**（沿用 F1/F4 边界） | 无 |
| 13 | 新增 `failure_class_selftest.py` | 新文件 | C1–C8 / R1–R4 / I1–I8 / S1–S6 | 新增 |

### 15.2 三个必须留意的实现细节

1. **`z_raw` 的 timeout**：`z_raw(method, params, timeout=60)` 默认 60s，而原调用是 `z(..., timeout=120)`。改用时**必须显式传 120**，否则 I1 破坏。
2. **`_post` 的四类失败模式**：连接层 `OSError`、`socket.timeout`、`http.client.HTTPException`、`json.JSONDecodeError`。前三者可能请求未到达，第四者**请求已到达但响应不可解析**——四者一律 `submit_state=unknown`（不确定即从严）。
3. **`extrasaction="ignore"`**：`csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")`（1088 行）会**静默丢弃** row 中不在 `COLUMNS` 的键。这正是把 sidecar 字段挂在 row 上而不改列结构的安全通道；但也意味着**如果忘记单独写 sidecar，证据会静默消失**——故 sidecar 必须独立写出，不能依赖 row 落盘。

### 15.3 预计规模与验证

- 代码：约 +150/−25（第 2 项与第 3 项为主）。
- 测试：新增约 26 条用例；回归另跑 `recipient_derivation_selftest.py`（30 条）与 `reporting_patch_selftest.py`。
- 验证顺序：静态 diff → 自检脚本全绿 → 历史 3 条真实错误回放 → dry-run 全字段比对（I6）。

---

## 16. 待授权事项（当前状态）

| 编号 | 事项 | 你的决定 | 落地位置 |
|---|---|---|---|
| T1 | 实施 F5 | **暂不授权** | §15 已列范围，等授权 |
| T2 | `-6` 分类 | 认可进入设计，**必须结合消息判断** | §4.5（`code ∈ {-4,-6}` + message 双条件） |
| T3 | `failure_class` 中 `timeout` 改名 | **暂不决定**，先统一阶段命名 | §4.3 已统一 `stage`；`failure_class` 名待定 |
| T4 | 汇总 note 文案 | 采用**事实描述**，禁止未证明归因 | §4.7 |
| T5 | 新增 CSV 列 | **不增加**，使用 sidecar | §4.9 |
| T6 | 零副作用负向探测取 `-6`/`-5` 样本 | 未批准 | §6.5 明确不测 |
| T7 | `submit_state` | **必须实现** | §4.8 + §15 第 1/2 项 |
| — | 替换机制 | **人工触发** | §10 |

---

## 17. 冻结后的执行顺序

| 步骤 | 内容 | 状态 |
|---|---|---|
| 1 | 分类规则（§4） | 冻结 |
| 2 | 证据要求（§8–§14） | 冻结 |
| 3 | 测试矩阵（§6） | 冻结（用例待编写） |
| 4 | 实施 F5（T1） | **未授权** |
| 5 | 新 gate | **未授权**；须先恢复快照并重新核验六项 |

---

## 附：证据出处

| 证据 | 位置 | 取得方式 |
|---|---|---|
| `LegacyCode` 码表 | `zallet-core/src/components/json_rpc/server/error.rs`（`main`，2026-10-30） | 源码读取；**未固定 commit**，引用须注明 |
| `-8` 承载策略拒绝 | `zallet-core/src/components/json_rpc/payments.rs`，`impl From<IncompatiblePrivacyPolicy>` | 同上 |
| 资金不足经提案 → `Wallet`（-4） | 同上，`propose_and_check` 的 `map_err` | 同上 |
| 3 条 `-8` 实测 | `raw/confirmatory_20261030/_feasibility_gate/run_20261030_110042/rounds.csv` | 本地只读 |
| `-4` 实测 | `sapling_e2e_address_derivation_probe_20261030.md` | 本地只读 |
| 消息族字符串 | `zallet-v0.1.0-beta.3-linux-amd64/zallet-zebra` | `strings` 只读扫描 |
| 判定矩阵 9 行 | 用 `2eb6442` 的 `_classify()` 实际调用 | `python -c` 本地运行 |
| `extrasaction="ignore"` | `confirmatory_bench.py:1088` | 源码只读 |

**证据等级**：A = 源码或真实运行数据；B = 按源码构造的用例或二进制字符串；C = 假设性构造。码映射为 A 级；资金不足路径为 A（源码）但缺实测样本；`-32602` 为 B 级。
