# 多收款地址派生 —— 补丁设计说明（未实施）

> 状态：**设计稿，未写任何代码**。本文只描述拟议补丁的范围、算法、错误处理与测试，供审查。
> 依据材料：`sapling_e2e_address_derivation_probe_20261030.md`（11:16–11:24 实测）、`sapling_e2e_gate_deviation_20261030_110042.md`（门禁 7/10）。
> 本文不修改预注册 `a1277a7`，不改门禁产物，不改 PR #24。

---

## 0. 一句话结论

门禁失败的直接原因是 `confirmatory_bench.py` L462 的 `recipients = [from_ua] * n_recip`；但探测已证明**根因更深**：本仓库从来没有"同一账户派生 n 个互不相同 Sapling-only UA"的能力（`sapling_ua()` 只有无参数形式，且无参调用不幂等）。因此补丁不是改一行列表，而是**新增一段受控的地址准备流程**，并把它放在交易构造之前、可失败、可溯源、可硬停。

---

## 1. 现状：四处代码事实

| 位置 | 代码 | 问题 |
|---|---|---|
| `sapling_e2e_bench.py` L236–246 | `sapling_ua()` → `z("z_getaddressforaccount", [0, ["sapling"]])` | 只有一个返回值，无 index 参数；每次调用推进内部索引（实测 4610656263/264/265），**不幂等** |
| `confirmatory_bench.py` L462 | `recipients = [from_ua] * n_recip` | n_recip≥2 时地址重复 → zebra `-8 duplicated recipient address` |
| `confirmatory_bench.py` L476–481 | `if dry_run: ... return row, None` | 在 `build_amounts` 之后、`send_frozen` 之前返回，**从未触达 RPC 发送层**，也未校验地址合法性 |
| `sapling_e2e_bench.py` L115–121 | `z()` 把错误压成 `RuntimeError("%s -> %s" % (method, json.dumps(error)))` | JSON-RPC `code` 被降级为字符串，**无法结构化判断 `-4`**，必须绕开 |

第 4 条是设计上的关键约束：若直接在 `RuntimeError` 的字符串里做子串匹配，`-4` 与 `-8`、`-5` 乃至 gap-limit 错误会混在一起，违背"只对确认可恢复的 `-4` 顺延"的要求。

---

## 2. 拟议改动（6 项，全部在 `confirmatory_bench.py` 内）

| # | 改动 | 位置 | 性质 |
|---|---|---|---|
| A | 新增 `z_raw()` 结构化 RPC 调用 | 新增，紧邻 import 区 | 新增 |
| B | 新增 `derive_sapling_recipient()` | 新增，`run_one` 之前 | 新增 |
| C | 新增 `prepare_recipients()`（含 L1 / L1.5 / L2） | 新增 | 新增 |
| D | `recipients` 改为调用 C 的产物 | L462 | 替换一行 |
| E | dry-run 分支加 L3 未覆盖声明 + 记录字段 | L476–481 | 增补 |
| F | `COLUMNS` 末尾追加 4 列 | L606–613 | 追加（不重排） |

**不改**：`pick_amount_zat()`、`form_match` / `fee_match` 判定、手续费公式 `F=5000·max(S,O)`、`note_inventory_detailed()`、`restore_snapshot()`、`verify_state()`、gate/confirm 主循环、`gate_summary.csv` 表头与统计口径。

---

## 3. 算法

### 3.1 `z_raw(method, params)` —— 让错误码可判定

```python
from sapling_e2e_bench import _post, zauth, ZA          # 在 L60-64 的 import 块内追加

def z_raw(method, params, timeout=60):
    """返回 (result, error_dict)；不抛异常，便于按 JSON-RPC code 分类。"""
    d = _post(ZA[0], ZA[1], {"jsonrpc": "2.0", "method": method,
                             "params": params, "id": 1}, zauth(), timeout)
    return d.get("result"), d.get("error")
```

- 复用 `zauth()` 而非重写 cookie 逻辑，避免两套认证口径分叉。
- 导入私有名 `_post`：只读、无副作用，`confirmatory_bench.py` 本来就 import 同一模块的公开函数。
- **替代方案**（若不接受私有名导入）：把 `z_raw` 放进 `sapling_e2e_bench.py` 作为公开函数，代价是改动扩散到第二个文件。**建议取前者**，理由是本轮改动面越小越好审查。

### 3.2 `derive_sapling_recipient(start_index, account=0)`

```
输入：start_index（11 字节域内的整数）、account（默认 0）
输出：(address, used_index, receiver_types, attempts_consumed)
失败：抛 RecipientDerivationError(attempts, last_error)

循环 idx = start_index, start_index+1, ... 直到预算耗尽：
  1. 若 idx > 2**88-1        → 抛错（index 域越界，结构性）
  2. result, err = z_raw("z_getaddressforaccount", [account, ["sapling"], idx])
  3. err 为 None → 校验 result["receiver_types"] == ["sapling"]，
                    不符则抛错（不可恢复），否则返回
  4. err["code"] == -4 且 message 命中白名单 → idx += 1，continue
  5. 其它任何情况        → 抛错（fail-closed）
```

**`-4` 白名单（逐字来自实测，只认这两条）**

| message 子串 | 实测触发 | 处置 |
|---|---|---|
| `cannot generate an address with the requested receivers` | index 0/1/2、4610656241 | 跳过，继续 |
| `was already generated with different receiver types` | index 5 | 跳过，继续 |

白名单以外一律抛出，**包括** gap-limit 类错误（`sapling_ua()` 文档串记载的"撞上 gap limit=16 后直接报错"）和任何未知 code。这条是刻意 fail-closed：把未知错误当"无效 index"会静默吞掉真正的环境故障，且可能让重试在错误方向上耗尽预算。

**预算**：`DERIVE_ATTEMPT_BUDGET = 64`，**每轮共享**（不是每个地址各自 64）。依据：实测跳过率约 1/3（4610656239/240 成功、241 失败），n_recip 最大 8 时期望约 12 次；64 留 5 倍余量，同时把最坏耗时限制在 64 次本地 RPC（毫秒级）。
> **实测修正（2026-10-30 11:35）**：真实跳过率约 53%，n_recip=8 实测消耗 17–19 次，非 12 次。预算 64 仍成立（余量约 3.4 倍），未调整。

### 3.3 起始 index：`listaddresses` 的 max + 1

不使用常量（如 `10**12`）：探测已把 `10**12` 用掉，且快照换了常量就失效。不读钱包 DB：那会新增 schema 依赖。

```
addrs = z("listaddresses", [])                       # 权威清单，含 diversifier_index
start = max(e["diversifier_index"] for 所有 unified 地址) + 1
列表为空 → start = 0（随后由 -4 白名单自然跳过）
```

三条要点：

1. ~~**可复现**：每轮 attempt 开头都会恢复快照，`addresses` 回到 38 行，所以每轮起点相同、派生序列逐位相同。~~
   **该判断已被实测推翻（2026-10-30 11:33–11:35，见 `sapling_e2e_recipient_patch_verification_20261030.md` §5）**：
   `addresses` 确实回到 38 行，但 `sapling_ua()`（无参派生）使用的 index 游标**不受快照恢复约束**，
   两次相同恢复分别得到 4610657118 / 4610657129。由于 sender 先于收款地址派生、且起点取
   `max(listaddresses)+1`，每轮起点会随之抬升（实测 4610656953 → 4610657067）。
   **仍然成立的部分**：每轮实际使用的 index 全部写入 `rounds.csv` 的 `diversifier_indices`，
   可逐轮追溯；index 值本身不参与交易构造与计时，不影响被测指标。
2. **不需要精确**：即使起点偏低，撞上"已被其它 receiver 组合占用"也会命中白名单被跳过，安全性不依赖起点精度。
3. **不动 DB**：不新增 `DB_REQUIRED_SCHEMA` 条目，`SchemaMismatch` 语义保持原样。

### 3.4 `prepare_recipients(n_recip, sender)`

顺序执行，任一步失败即抛，**不产生任何交易构造**：

| 层 | 检查 | 失败抛 |
|---|---|---|
| 派生 | 连续调 `derive_sapling_recipient`，每次以上一次的 `used_index+1` 为起点，直到凑满 `n_recip` | `RecipientDerivationError` |
| L1 | `len(set(recipients)) == n_recip` | `RecipientValidationError("duplicate")` |
| L1.5 | 每个 `addr ∈ listaddresses` 的账户 0 unified 集合（确认属于本账户、非外部地址） | `RecipientValidationError("not_owned")` |
| L2 | 每个 `addr`：`z("z_listunifiedreceivers", [addr])` 成功且 `set(keys) == {"sapling"}` | `RecipientValidationError("not_sapling_only")` |

L1.5 是顺带加强项：`z_listunifiedreceivers` 对**任何**合法 UA 都会成功，无法区分"本账户的"与"别人的"。既然 §3.3 已经拿到 `listaddresses`，判定归属零成本。

`RecipientError` 建议继承 `PreTxError`，但**由 `run_one` 自行捕获并写成失败行**（见 §5），不改主循环的异常分支。

---

## 4. `run_one()` 内的新顺序

```
wait_sync()                          ← 不动
[NEW] recipients, rmeta = prepare_recipients(n_recip, from_ua)     ← 失败即返回失败行，不构造
[NEW] row 写入 rmeta（div_indices / addr_hash / receiver_types / derivation_attempts）
build_amounts(recipients, amount_zec) ← 不动（只换入参来源）
if dry_run: 打印 L1/L2 已通过、L3 未覆盖；返回 row
send_frozen(...)                     ← 不动
```

关键点：**地址准备在 `build_amounts` 之前**。因此"派生失败"这一状态在语义上不可能产出半构造的交易，也不可能产出 txid。

`sender` 仍是原 `sapling_ua()` 的返回值（即 `from_ua`），保持"从账户 0 的某个 Sapling UA 发出"不变。

---

## 5. 失败如何落记录

```python
try:
    recipients, rmeta = prepare_recipients(n_recip, from_ua)
except RecipientError as e:
    row["error"] = str(e)[:300]
    row["failure_class"] = e.cls          # recipient_derivation_failed / recipient_validation_failed
    row["derivation_attempts"] = e.attempts
    print("  [fail] %s" % row["error"])
    return row, None                      # 与现有 PreTxError 路径同构：无 txid、不计有效成功
```

- `failure_class` 是**显式赋值**，不经过 `_classify()`，避免字符串猜测。
- 该行 `txid` 为空 → gate/confirm 主循环的有效成功判定天然为 False，**无需改任何计数代码**。
- confirm 模式下这次尝试**照常计入 `attempts`**（一次恢复+构造就是一次尝试），但不计有效成功。这与预注册一致，不需要新规则。
- 失败时已派生的地址留在本轮钱包 DB 中，但**下一次 attempt 开头会恢复快照**，污染不跨轮累积。`--no-restore` 模式下会累积，需在报告注明（该模式本就标注"违反预注册 §6"）。

---

## 6. dry-run 的表述

`L476–481` 改为：

```python
if dry_run:
    print("  [dry-run] L1 去重 + L1.5 归属 + L2 Sapling-only 校验已通过")
    print("  [dry-run] L3（z_sendmany 是否接受该多地址组合）未覆盖，本次运行不构成可行性证据")
    row.update({"dry_run": 1, ...})
    return row, None
```

意义变化要说清：旧 dry-run 连"地址是否合法"都没碰；新 dry-run 至少把**本地可判**的两层做实，并且明确声明第三层未覆盖。**仍然不得**用 dry-run 通过率论证形态可行——这条口径不变。

---

## 7. 记录字段（追加，不重排）

`COLUMNS`（L606–613）末尾追加 4 列。现有列顺序与含义一律不动，`recipients` 仍表示**收款地址数**（不是地址串）。

| 新列 | 示例 | 用途 |
|---|---|---|
| `recipient_div_indices` | `4610656239;4610656240` | 实际使用的 index，可复现、可追溯 |
| `recipient_addr_hash` | `a1b2c3d4e5f60718;…` | `sha256(address)[:16]`，关联证据但不暴露完整地址 |
| `recipient_receivers` | `sapling;sapling` | 逐地址 receiver 组成，L2 的持久证据 |
| `derivation_attempts` | `3` | 共消耗几次派生（含被跳过的无效 index） |

**兼容性已验证**：`analyze_sapling_cost.py` L35、`fit_sapling_e2e_model.py` L57 均用 `csv.DictReader`，追加列不破坏解析；`gate_summary.csv` 表头与统计逻辑不动；`meta.json` 不动。

完整地址不写入 CSV；若审阅需要，可从 DB 中按 index 反查（恢复前的那份 DB 里存在）。

---

## 8. 测试计划（阶段 4，先离线后在线）

**离线（合成数据 + monkeypatch，不发交易、不需节点）**

| # | 用例 | 断言 |
|---|---|---|
| T1 | n_recip=1/2/8，fake 全部成功 | 地址互不相同；index 连续递增；`derivation_attempts == n_recip` |
| T2 | fake 对每个 index 都返回白名单 `-4` | 预算耗尽后抛 `RecipientDerivationError`；`send_frozen` 调用次数==0 |
| T3 | fake 返回 `-5` / `-8` / gap-limit message | **立即抛出**，重试次数==1（不得顺延） |
| T4 | fake 返回重复地址 | L1 抛出 `duplicate` |
| T5 | fake 返回 `{"sapling":..., "orchard":...}` | L2 抛出 `not_sapling_only` |
| T6 | `z_listunifiedreceivers` 抛错 | L2 抛出，不发交易 |
| T7 | dry_run=True | `send_frozen`==0；stdout 含"L3…未覆盖" |
| T8 | start_index = 2**88-1 | 越界抛错，不调 RPC |
| T9 | 失败行落盘 | `rounds.csv` 含新列且 `failure_class=recipient_derivation_failed`、`txid` 为空 |

**在线（阶段 5，独立验证，不产生 confirmatory 数据）**

1. 恢复快照 → `listaddresses` 取起点 → 为 O=2 / O=3 / O=9 分别准备地址 → 断言数量与 L2，**不发交易**；
2. 记录每形态的 index 列表与 `derivation_attempts`，确认起点在恢复后逐轮稳定（同形态两次派生得到同一组 index）；
3. 通过后才讨论是否用一次真实发送验证 `z_sendmany` 接受性（**需单独授权**）。

---

## 9. 需要你拍板的 4 个决策点

| # | 问题 | 选项 | 我的建议 |
|---|---|---|---|
| D1 | O=2（n_recip=1）是否也改用新派生地址？ | ①统一用新派生地址；②保留 `recipients=[from_ua]`（self-send） | **①**。否则 O=2 走自转、O≥3 走多地址，模型里 O 的系数会混入两种机制；且阶段 5 本就要重测 O=2 |
| D2 | 起始 index 来源 | ①`listaddresses` max+1；②钱包 DB `MAX(diversifier_index_be)+1`；③固定高位 | **①**。不新增 DB 依赖、可复现；②需要新增 schema 断言 |
| D3 | 派生失败是否计入 confirm 的 `attempts` | ①计入（不利有效成功）；②不计入 | **①**。一次恢复+构造就是一次尝试，与预注册一致，无需新规则 |
| D4 | 新列是否进 `rounds.csv` | ①追加 4 列；②只写 `run.log` | **①**。DictReader 兼容已验证，且审阅者能直接从 CSV 复核 L2 |

---

## 10. 风险与边界

| 风险 | 说明 | 缓解 |
|---|---|---|
| 地址派生污染钱包 DB | 每轮 +n_recip 行 `addresses` | 每 attempt 恢复快照；`--no-restore` 时在报告注明累积 |
| 派生推进 gap limit | `sapling_ua()` 文档串记载 p2pkh 撞限会报错 | 只请求 `["sapling"]`；未知错误 fail-closed 直接停 |
| 起点偏低导致连续跳过 | 白名单命中即跳过，最坏耗预算 | 预算 64；耗尽即抛，不静默降级 |
| `_post` 为私有名 | 依赖同模块内部实现 | 只读、无副作用；若不接受则改放 `sapling_e2e_bench.py` 公开函数（改动面 +1 文件） |
| 新地址改变钱包记账 | 同账户新地址仍由本钱包识别 | `form_match` 会兜住额外 output/找零；阶段 5 先只读验证 |

**明确不做**：不改 `pick_amount_zat`、不改 `form_match`/`fee_match`、不改手续费公式、不改 `note_inventory_detailed`、不改 `restore_snapshot`、不改主循环统计、不覆盖 `run_20261030_110042/`、不改预注册、不合并 PR #24。

**数据隔离**：修复后的正式实验必须使用新的 run 目录与新的编号；`run_20261030_110042/` 作为"执行器能力边界"证据永久保留，不得混入 confirmatory 数据集。

**三类材料不得合并成同一结论**：
1. 性能模型（proving / 端到端耗时）；
2. 门禁 7/10 的执行器缺陷证据（**不能**作为双变量模型的 confirmatory 结果）；
3. 地址派生能力探测（只证明"能派生"，**不证明** "O≥3 交易可行"）。

---

## 11. 本阶段未做的事

- 未修改 `confirmatory_bench.py` 或 `sapling_e2e_bench.py`；
- 未发送任何交易；
- 未恢复 / 改动门禁产物与封存目录；
- 未修改预注册、未合并 PR #24；
- 未删除探测产生的 7 条地址记录（保留为证据）。
