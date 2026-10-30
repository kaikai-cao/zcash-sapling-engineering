# 可行性门禁（Gate）偏差记录 — 2026-10-30 11:00:42

> 本文件封存 **confirmatory 实验的第一次可行性门禁**（`--mode gate`）结果。
> 门禁未达到通过标准（10/10 全匹配），失败原因为**执行器构造缺陷**，与 Sapling 协议能力无关。
> 本文件只记录事实与边界，**不构成对预注册 §4 矩阵的修订**；矩阵修订须按 §4.2 另行完成并冻结。

---

## 0. 溯源信息（全部可独立核对）

| 项 | 值 |
|---|---|
| 预注册文件 | `experiments/metadata/sapling_e2e_regtest_confirmatory_preregistration_20261030.md` |
| 预注册提交 | `a1277a7`（本次门禁期间**未修改**） |
| 执行器 | `experiments/e2e_testnet_tx/confirmatory_bench.py` |
| 执行器提交 | `020383e694bc7ec72e939d96d29c11174999236d` |
| 分支 | `experiments/e2e-testnet-tx-harness`（`refs/pull/24/head` = 同一 SHA） |
| 快照 | `z3_regtest_h32297_20261029_145710.tar.gz`，SHA256 `ca35201887b8041b44c483ad258a718f4a74787c02c4ff9dbbb202857b09510c` |
| 恢复脚本 | `/mnt/d/Research/z3/wsl/snapshot_restore.sh`，SHA256 `2df7cd8bd4890963d925711912aa280f944156319d2b6aa5fa2b53c35a720e11` |
| 快照目标高度 | 32297 |
| 运行命令 | `python3 confirmatory_bench.py --mode gate`（无任何 `--allow-*`、无 `--no-restore`） |
| 运行时段 | 2026-10-30 11:00:42 → 11:05:34（4m52s） |
| 产物目录 | `experiments/e2e_testnet_tx/raw/confirmatory_20261030/_feasibility_gate/run_20261030_110042/` |
| meta 关键字段 | `mode=gate, dry_run=false, real_tx=true, restore_enabled=true, meta_stage=run_end, rows_total=10, rows_with_txid=7` |
| 两个 SHA 校验 | `snapshot_sha256_match=true`, `restore_script_sha256_match=true` |

预注册 §4 冻结矩阵（原文，未改）：

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

---

## 1. 门禁结论：未通过

| | 数量 |
|---|---|
| 尝试 | 10（每形态 1 次，无重试） |
| 有效成功（`tx_success & form_match & fee_match`） | **7** |
| 失败 | **3** |

按 predregistration §4.1 的判定内容，门禁要求 10 个形态逐一验证"实际 Spend/Output 是否符合预期、交易是否成功构造、手续费是否符合 ZIP 317"。3 个形态连交易都未被接受，故**门禁不通过**。

### 1.1 逐形态结果

| # | (S,O) | 结果 | pipeline | 实际 (spends/outputs) | form | fee | txid（前 16） |
|---|---|---|---|---|---|---|---|
| 1 | (1,2) | 成功 | 1528.0 ms | 1 / 2 | ✅ | ✅ | `891b5ffa58c48f23` |
| 2 | (2,2) | 成功 | 2116.5 ms | 2 / 2 | ✅ | ✅ | `1a51cb4fbd43ddf7` |
| 3 | (4,2) | 成功 | 3393.2 ms | 4 / 2 | ✅ | ✅ | `0678e3b3329d1876` |
| 4 | (7,2) | 成功 | 5282.9 ms | 7 / 2 | ✅ | ✅ | `bfb77822623a6f25` |
| 5 | (10,2) | 成功 | 7149.6 ms | 10 / 2 | ✅ | ✅ | `62edefd688fa8355` |
| 6 | (17,2) | 成功 | 11407.2 ms | 17 / 2 | ✅ | ✅ | `3418d3a63ebd7744` |
| 7 | (1,9) | **失败** | — | — | — | — | — |
| 8 | (3,2) | 成功 | 2768.5 ms | 3 / 2 | ✅ | ✅ | `9b2b8e47e377703a` |
| 9 | (3,3) | **失败** | — | — | — | — | — |
| 10 | (4,3) | **失败** | — | — | — | — | — |

**观察：7 个成功形态的 `O` 全部等于 2；3 个失败形态的 `O` 全部 ≥ 3。** 失败与 `O` 一一对应，与 `S` 无关（(1,9) 的 S 最小仍失败，(17,2) 的 S 最大仍成功）。

---

## 2. 失败原因（逐条原始错误）

三例 `failure_class` 均为 `rpc_policy_rejected`，错误体完全同型：

```
round 7  (S=1,O=9) recipients=8:
  z_sendmany -> {"code": -8, "message": "Invalid parameter, duplicated recipient address: uregtest18w74lh5uyurp33xrqrz8j30f6ny56z6jh5sqg3ullraz84au3ux3jr56xcsamzwxnewyaqa7fhpfk82e346ev3kkvzqly9gkeg9c..."}

round 9  (S=3,O=3) recipients=2:
  z_sendmany -> {"code": -8, "message": "Invalid parameter, duplicated recipient address: uregtest1z548jw29869nxu6s0u5tdauj0458qxzanz7g8dfpttd5p6hdd82xg5mspryjz4ejpghvuf4hjtjmye0wfl5z725jk8yzmtds5gh57p5..."}

round 10 (S=4,O=3) recipients=2:
  z_sendmany -> {"code": -8, "message": "Invalid parameter, duplicated recipient address: uregtest1tqpu0p9gq29n04z2ys6sumu02n3n702euv5ztlm9pwx80zhr65fxpx267nvne8xndrwz7th267ew4u5z5fan46w94xd3e35zhg2..."}
```

### 2.1 根因（代码定位）

`confirmatory_bench.py` · `run_one()` 第 462 行：

```python
recipients = [from_ua] * n_recip          # 收款地址全部指向恢复后钱包同一 UA（自转/自收）
```

配合 `pick_amount_zat()` 第 356 行：

```python
n_recip = max(1, O - 1)
```

因此：

| 目标 O | `n_recip = O-1` | 收款地址列表 | zebra 行为 |
|---|---|---|---|
| 2 | 1 | `[ua]` | 合法 |
| 3 | 2 | `[ua, ua]` | 拒绝（duplicated recipient address） |
| 9 | 8 | `[ua] × 8` | 拒绝（duplicated recipient address） |

`z_sendmany` 对同一收款地址出现多次一律拒绝，**与金额是否相同无关**。这正是 7 成功 / 3 失败的完整解释。

### 2.2 这是执行器缺陷，不是形态不可行

- 缺陷位于**地址生成**，不在 Sapling 协议、不在 zebra 的 Sapling 能力、不在 ZIP 317 手续费规则。
- 修复方向明确：为 `n_recip` 生成 **n_recip 个互不相同的收款地址**，而非重复同一 UA。
- 修复不涉及 `form_match` / `fee_match` / `pick_amount_zat` / `note_inventory_detailed` / `restore_snapshot` 的任何统计口径。

---

## 3. dry-run 的验证盲区（本次最重要的方法论发现）

**此前的 10 次 `--dry-run` 全绿（10/10）是假阳性。**

原因：`confirmatory_bench.py` · `run_one()` 第 476–481 行，dry-run 分支在构造完成后直接返回：

```python
if dry_run:
    print("  [dry-run] 不实际发交易（已恢复+核验+选定金额）")
    row.update({"dry_run": 1, ...})
    return row, None
```

`z_sendmany` 在 dry-run 路径上**从未被调用**（调用点在 L484 之后）。因此：

- dry-run 验证的只是：快照恢复成功、链高正确、note 清单可读、金额边界可满足、`build_amounts` 本地能生成结构。
- dry-run **完全没有**验证：收款地址是否重复、地址是否被钱包接受、`z_sendmany` 参数是否合法、交易能否真正构造/签名/广播。
- 结论：**dry-run 通过率不能用于论证形态可行或交易可执行**。它在本次事件中给出了与真实结果相反的表面信号（10/10 vs 7/10）。

这一盲区必须写进正式报告，作为对"可行性门禁"方法本身的修正。

---

## 4. 末态只读取证（B 方案：未恢复快照）

门禁结束后按用户决定的 B 方案保留末态，先取证、后另行决定是否恢复。

### 4.1 钱包 DB 与快照归档逐表比对：7/7 相同

| 指标 | 归档 | 末态 | 判定 |
|---|---|---|---|
| transactions | 50 | 50 | SAME |
| sapling_received_notes | 50 | 50 | SAME |
| sapling_received_note_spends | 14 | 14 | SAME |
| unspent（可花费 Sapling note） | 36 | 36 | SAME |
| unspent_zat | 11999980000 | 11999980000 | SAME |
| max(mined_height) | 32296 | 32296 | SAME |
| max(blocks.height) | 32297 | 32297 | SAME |

### 4.2 字节级 SHA256：**不一致**（须在报告中注明）

| | SHA256 |
|---|---|
| 归档内 `data/zallet/wallet.db` | `4fb0a7918f950518e3354a9cebd0763ef7cbba44b1b29eb136237fec8bd68df4` |
| 末态 `~/z3-regtest/data/zallet/wallet.db` | `1512cf95f3c5ff46e7e54882357cebfc3135085c772dfb87338e7e844b0f3e02` |

- **语义一致、字节不一致**：zallet 启动时重写 SQLite 页（页布局/空闲页/WAL checkpoint），但表级计数与金额完全不变。
- 报告措辞必须写成"表级语义一致"，**不得**写成"文件完全一致"或"字节相等"。

### 4.3 RPC 取证是"重启服务后补采"，不是门禁结束瞬间采集

必须先说清楚的事实：

1. 门禁以 `wsl -d Ubuntu -e bash -lc` 后台任务方式运行。**任务结束后 WSL 实例关闭**，restore 脚本经 `setsid nohup` 拉起的 `zebrad` / `zallet-zaino` 被一并回收；40232/18232 端口不再监听，`data/zallet/.cookie` 随 zallet 退出被删除。
2. 因此**门禁结束瞬间的 RPC 现场没有保留**（进程已不存在）。
3. 为补齐用户要求的取证项，用**同一份 data 目录**重新拉起 zebrad/zallet（**未执行快照恢复**），取得只读 RPC 值后即结束进程。
4. 该补采**未改变数据**：DB 计数在补采前后均为 transactions 50 / notes 50 / spends 14。

补采所得值：

| 项目 | 值 |
|---|---|
| `getblockcount` | 32297 |
| `getrawmempool` | `[]` |
| `z_getnotescount([1])` | `{"sprout":0,"sapling":36,"orchard":0,"ironwood":1}` |
| `z_getbalanceforaccount`（sapling） | `11999980000` zat |
| `getwalletstatus` | `wallet_tip=32297`, `fully_synced_height=32297`, `node_tip=31296`（启动瞬间陈旧，属正常） |

### 4.4 三份产物文件互相一致

- `gate_summary.csv` 10 行，`tx_success=1` 的 7 行、`0` 的 3 行；
- `rounds.csv` 10 行，其中带 `txid` 的 7 行；
- `meta.json`：`rows_total=10`、`rows_with_txid=7`、`attempts_per_form` 10 项全为 1、`valid_successes_per_form` 7 项全为 1。

三者交叉核对一致，无矛盾。

---

## 5. 本记录明确**不**支持以下结论

1. **不得**得出"O≥3 的 Sapling 交易不可行"。三例失败均为地址重复导致，与协议能力无关。
2. **不得**得出"O=3 / O=9 的构造与手续费符合 ZIP 317"。这三格从未被真正验证过。
3. **不得**使用本次 7 个成功样本对 `T = f(S,O)` 做任何回归或系数估计：
   - 全部样本 `O=2`，`O` 维度无变异；
   - 每形态 `n=1`，无重复测量，无法估计方差；
   - 本次为门禁探测，按 §4.1 明确规定**不计入**正式 50 次样本。
4. **不得**据本记录直接删除预注册 §4 矩阵中的 (1,9)/(3,3)/(4,3)。预注册 §4 规定：关键形态无法构造时，须将 H_B 标为"无法按原设计检验"或在使用前完成有记录的方案修订。本次属**工具缺陷导致门禁未完成**，应走"修复后重新门禁"，而非"剔除形态"。

---

## 6. 处置建议（待决策，本文件不预设结论）

| 方案 | 内容 | 代价 |
|---|---|---|
| 1（拟采纳） | 修复 `recipients` 地址生成 → 独立最小验证（O=2 无退化 / O=3 / O=9）→ 重新执行门禁 → 再启动正式采集 | 需新增代码提交 + 第二次门禁 run；预注册须记录 §4.2 修订依据 |
| 2 | 不修复，矩阵限定 O=2 的 7 个形态 | 丧失 `O` 维度，`T=f(S,O)` 退化为单变量 |
| 3 | 仅留存本次门禁作为"执行器能力边界"证据，O 维度另行设计实验 | 时间成本最高 |

**计数口径提醒（用户明确要求）**：本次 3 个失败形态是**执行器缺陷下的失败记录**，不是修复后实验的有效尝试。修复后的正式实验必须按预注册 §4 独立重新计数（每格最多 8 次、目标 ≥5 次有效成功），**不得**把本次的 1 次尝试抵扣或补足。旧门禁数据与新 confirmatory 数据必须分属不同 run ID / 目录，不得混算。

---

## 7. 未改动声明

- 未覆盖、未修改 `run_20261030_110042/` 下任何既有文件（rounds.csv / gate_summary.csv / meta.json / run.log / memory_timeseries.csv 均原样）。
- 未修改预注册（仍为 `a1277a7`）。
- 未修改执行器（仍为 `020383e`）。
- 未合并 PR #24；未启动正式采集；未执行快照恢复。
