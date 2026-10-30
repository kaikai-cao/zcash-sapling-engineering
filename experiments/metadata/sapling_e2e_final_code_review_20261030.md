# Sapling E2E 执行器——多收款地址补丁的最终代码审查

- 审查时间：2026-10-30 14:0x（本地）
- 审查对象：`efd12d2`（代码）+ `c2e2d76`（记录与自检）
- 审查范围：仅静态审查与只读核对；**未改代码、未发交易、未启动 gate**
- 基线：`020383e`（门禁实际使用的执行器版本，保留不动）

---

## 0. 结论摘要

| # | 审查项 | 结论 |
|---|---|---|
| 1 | 两笔提交的完整 diff | 通过（范围与声明一致） |
| 2 | `z_raw()` 的错误分支处理 | 通过（判定正确）／标注精度有 1 处不足（F2） |
| 3 | 64 次预算是否每轮共享且不可绕过 | 通过（另发现失败行计数偏小，F3） |
| 4 | 地址准备是否完全在 pipeline 计时区间之外 | 通过（计时器零改动） |
| 5 | 新增 CSV 字段的汇总/分析/失败记录适配 | 通过（汇总 note 措辞有 1 处遮蔽，F1） |

**阻塞级问题：0 项。** F1–F4 均为「不改变任何判定结果」的标注/记录层问题，但 F1 会让报告误读失败原因，建议在启动新一轮 gate 前修掉。

---

## 1. 提交范围核验

`efd12d2`：单文件 `confirmatory_bench.py`，+266/−4。8 个 hunk：

| hunk 位置 | 内容 |
|---|---|
| `@@ -17,9 +17,13 @@` | 模块 docstring（构造方式改为多地址） |
| `@@ -61,6 +65,10 @@` | import 增加 `_post` / `zauth` / `ZA` |
| `@@ -113,6 +121,24 @@` | `DERIVE_ATTEMPT_BUDGET` / `INDEX_DOMAIN_MAX` / 白名单 / 3 个异常类 |
| `@@ -133,6 +159,29 @@` | 异常类注释扩展 |
| `@@ -445,6 +494,180 @@` | 新增 `z_raw` / `account_unified_addresses` / `derive_sapling_recipient` / `prepare_recipients` / `_addr_hash` |
| `@@ -459,10 +682,36 @@` | `run_one` 收款地址准备（替换 `[from_ua]*n_recip`） |
| `@@ -475,6 +724,10 @@` | dry-run 的 L1/L1.5/L2 已覆盖 + L3 未覆盖声明 |
| `@@ -610,7 +863,16 @@` | `COLUMNS` 末尾追加 6 列 |

删除的 4 行：2 行过期 docstring、`recipients = [from_ua] * n_recip`、`COLUMNS` 收尾行。

`c2e2d76`：5 个新增文件，1356 行，全为 `.md` 与一个离线自检脚本，无生产代码。
自检脚本只把 `send_frozen` 猴子补丁成抛错以证明「dry-run 不得发送」，无网络调用。

预注册 `sapling_e2e_regtest_confirmatory_preregistration_20261030.md` 在 `020383e..HEAD` 区间内 **零改动**。

---

## 2. `z_raw()` 的错误分支

`z_raw()` 返回 `(result, error)` 而不抛异常。逐个分支：

| 情形 | 返回值 | 调用方行为 |
|---|---|---|
| 正常 | `(res, None)` | 继续 |
| JSON-RPC error | `(None, err)` | 按 `code` + 白名单判定 |
| 响应既无 result 也无 error | `(None, None)` | 派生：`addr` 为空 → 抛 `recipient_derivation_failed`；`listaddresses`：类型非 list → 抛；L2：非 dict → 抛 `recipient_validation_failed`。**三处均 fail-closed** |
| `_post` 抛（连接拒绝／超时／非 JSON 响应／cookie 缺失） | 异常穿透 | 见 F2 |

**关键判定正确性**：`derive_sapling_recipient` 的顺延条件是

```python
if code == -4 and any(p in msg for p in DERIVE_RETRYABLE_PATTERNS):
    idx += 1; continue
raise RecipientDerivationError(...)
```

即 `code == -4` **且** message 命中两条白名单才顺延；`-4` 不命中白名单、`-5`、`-8`、未知 code 一律 `raise`。与会话中确认的口径一致：**不会因为某个 index 无效就把其他错误当成 index 无效**。

---

## 3. 预算是否每轮共享、可否被绕过

- `DERIVE_ATTEMPT_BUDGET = 64`，只在 `prepare_recipients(budget=...)` 默认参数处出现；生产代码**从未**传入其他值（唯一覆盖在自检脚本 `budget=5`，用于测耗尽）。
- `prepare_recipients` 在整个仓库只有 1 个生产调用点：`run_one()` L691。
- 共享机制：`attempts` 在 `prepare_recipients` 内跨地址累加，每个地址只拿到 `remaining = budget - attempts`；`derive_sapling_recipient` 返回的 `att` 立即并入 `attempts`。
- 耗尽路径：`remaining <= 0` → 抛 `recipient_derivation_failed`，**不回落旧地址、不重复地址**。
- 预算作用域：`prepare_recipients` 在 `run_one` 内，而 `run_one` 每次 attempt 调一次 → 预算按 attempt 重置，符合「每轮 attempt 独立 64 次」。

**结论：通过。** 无绕过路径。

---

## 4. 计时区间（本轮最关键一项）

`run_one` 内的实际顺序：

| 行 | 动作 | 是否在计时区间内 |
|---|---|---|
| 691 | `prepare_recipients(n_recip, from_ua)` ← 派生 + L1 + L1.5 + L2 | **否** |
| 716 | `wait_sync()` | 否 |
| 720 | `build_amounts(...)` | 否 |
| 736 | `bal0 = sapling_zat()` | 否 |
| 737 | `t_round = time.monotonic()` | 计时起点（`total`） |
| 739 | `send_frozen(...)` | 是（`submit` / `pipeline` 在此内部计时） |
| 787 | `total_ms = now - t_round` | 计时终点 |

`pipeline` 来自 `send_frozen` 内部：`t0`（L472，提交前）→ `t_submit`（L477）→ `t1`（L479）→ 轮询至 success 得 `t_pipeline`（L488）。地址准备在 `t0` 之前 700 余行就已结束。

diff 层面复核：`git diff 020383e..HEAD` 中 `t_round` / `t0 = time` / `t_pipeline` / `t_submit` / `send_frozen` / `wait_sync` **零命中**——计时器与发送函数一行未动。

**结论：通过。地址准备时间不会混入 `pipeline`，也不会混入 `total`。**

补充：sender 的 `sapling_ua()` 在 `do_one_attempt` 里、`run_one` 之前调用，同样在计时区间之外。

---

## 5. CSV 字段适配

- `COLUMNS`：旧 30 列**逐项、同序**保留，新 6 列（`recipient_count` / `diversifier_indices` / `recipient_addresses_hash` / `recipient_receivers` / `derivation_attempts` / `recipient_validation`）全部追加在末尾 → 共 36 列。
- 写出用 `csv.DictWriter(..., extrasaction="ignore")`：多余键被忽略，缺失键写空 → `fail_row()` 只给 5 个键也不会崩。
- `gate_summary.csv` 表头**未变**（9 列），统计口径未变（`tx_success` / `form_match` / `fee_match` / `all_match` 定义与 `020383e` 相同）。
- 分析脚本：`analyze_sapling_cost.py` 过滤条件为 `if not r.get("txid") or r.get("error"): continue`，`fit_sapling_e2e_model.py` 的 `load_all` 同构 → 收款地址失败行（无 txid、有 error）被自然排除，不会污染拟合。两个脚本引用的列名全部是旧列，**不依赖任何新列**。

**结论：通过。** 例外见 F1。

---

## 6. 发现的问题

### F1（标注层，建议 gate 前修）汇总 note 会遮蔽地址准备失败

`gate_summary` 的 note 判定顺序是：

```python
if not tx_ok:
    if a.dry_run:
        note = "dry-run：未发交易，仅验证构造（无 txid 属预期，不代表形态不可行）"
    else:
        note = "无成功构造（形态不可行或环境/策略失败）"
```

而收款地址失败行同样 `tx_ok` 为空。因此：

- 正式模式下，`recipient_derivation_failed` 会被写成「形态不可行或环境/策略失败」——**把工具缺陷说成形态不可行**，正是上一轮门禁踩过的那个坑；
- dry-run 模式下问题更严重：会被写成「仅验证构造（无 txid 属预期，不代表形态不可行）」，**直接掩盖构造失败**。

`rounds.csv` 里的 `failure_class` 是准确的，所以数据本身可追溯；错的是给人看的汇总层。建议 gate 前把 note 改为按 `failure_class` 分流（例如出现 `recipient_*` 时写「收款地址准备失败（未构造、未发送）」）。**本轮未改。**

### F2（标注层，可接受）传输层异常未归入 `recipient_*`

`_post()` 会抛 `ConnectionRefusedError` / `socket.timeout` / `json.JSONDecodeError`，`zauth()` 在 cookie 缺失时抛 `FileNotFoundError`。`z_raw()` 不捕获这些，异常穿透 `derive_sapling_recipient` → `prepare_recipients` → `run_one` 的 `except RecipientError` 也不匹配 → 落到主循环 `except Exception` → `failure_class = "other"`。

**判定仍正确**（fail-closed：不构造、不发送、不倒查索引、不消耗后续预算），只是标注退化为 `other`，且 `derivation_attempts` 不落。属于诊断精度问题，不改变任何统计结果。

### F3（标注层，可接受）失败行的 `derivation_attempts` 偏小

`prepare_recipients` 只有在 `derive_sapling_recipient` **成功返回后**才 `attempts += att`。若第 k 个地址派生失败，抛出的异常携带的是**该次调用内部**的计数，不含此前已成功地址消耗的次数。

例：n_recip=8，前 7 个共用 10 次，第 8 个用 5 次后失败 → 落盘 `derivation_attempts=5`，真实为 15。

预算耗尽的路径（`remaining <= 0`）报告的是累计值，是对的。影响仅限失败行的诊断信息。

### F4（文档，建议下次动代码时一并修）代码注释里仍留着已被推翻的判断

- `account_unified_addresses()` docstring（L518–519）仍写「每轮 attempt 开头都恢复快照 → addresses 回到同一行数 → **起点逐轮相同，派生序列可复现**」。该判断已被实测推翻（两次相同恢复后无参派生分别为 4610657118 / 4610657129），设计稿已更正，**代码注释未同步**。
- L132–134 注释写「跳过率约 1/3，n_recip=8 期望约 12 次，64 留 5 倍余量」。实测跳过率 53%，实际消耗 17（独立验证）／19（dry-run 第 7 轮），余量约 3.4 倍。结论（64 够用）不变，数值需更正。

这类注释不影响运行，但会误导后续审阅者——尤其「起点可复现」正是本轮被发现并推翻的那条。

---

## 7. 附：`prepare_recipients` 的 `sender` 参数未使用

签名 `prepare_recipients(n_recip, sender=None, budget=...)`，`sender` 在函数体内从未被引用。调用点传入 `from_ua` 也无作用。无害，但属于可清理的死参数（不构成问题，仅登记）。

---

## 8. 本轮未做的事

- 未修改任何代码（F1–F4 全部只登记）；
- 未发送任何真实交易；
- 未启动新一轮 gate；
- 未改动 `run_20261030_110042/`、`laststate_seal_20261030_1115/`、预注册；
- 未 squash、未合并 PR #24。
