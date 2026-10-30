# 地址派生能力探测记录 — 2026-10-30 11:16–11:24

> 目的：确认 zallet 的 `z_getaddressforaccount` 是否支持通过 diversifier index 派生出**同一账户下互不相同、且仅含 Sapling receiver** 的地址，为修复门禁暴露的 "duplicated recipient address" 缺陷提供依据。
> 授权范围：**只做地址派生探测**。不修改代码、不发送交易、不改预注册。

---

## 0. 前置动作与顺序（严格按用户指定顺序执行）

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1 | 封存门禁末态证据 | → `raw/confirmatory_20261030/_feasibility_gate/laststate_seal_20261030_1115/`（wallet.db 字节副本 + 1051 文件 SHA256 + addresses 39 行导出 + README） |
| 2 | 校验快照与恢复脚本哈希 | 快照 `ca352018…b09510c` ✅、脚本 `2df7cd8b…a720e11` ✅，均与预注册冻结值一致 |
| 3 | 恢复冻结快照 | 11:15:53 → 11:15:59 完成；链高 32297，sapling 余额 11999980000，`addresses=38` |
| 4–6 | 启动服务 → 探测 → `listaddresses`/`listunifiedreceivers` 校验 → 检查 DB 副作用 | 见下文 |
| 7 | 停止服务、封存记录 | 11:24 停服；`addresses=45`，其余表未变 |

**注意**：步骤 3 恢复了快照，因此当前环境**已不再是门禁末态**。门禁末态仅存于步骤 1 的封存目录中。

---

## 1. 结果表（对应委托方要求的 6 项检查）

| # | 检查项 | 预期 | 实测 | 判定 |
|---|---|---|---|---|
| 1 | 不同 diversifier index 得到不同 UA | 能得到不同 UA | **部分成立**：合法 index 能派生出不同地址（见 §2.2）；但**相当比例的 index 报 `-4`**"cannot generate an address with the requested receivers" | ⚠️ 需跳过无效 index |
| 2 | 同一 index 重复调用 | 返回相同 UA | **成立**：两次调用返回完全相同的地址，且 DB **不新增行** | ✅ |
| 3 | receiver 类型 | 仅 Sapling | **成立**：返回体 `receiver_types=["sapling"]`，DB `receiver_flags=4` | ✅ |
| 4 | 地址有效性校验 | `z_validateaddress` 通过 | **原方案不可用**：`z_validateaddress` 方法不存在；无前缀的 `validateaddress` 对**完整合法 UA 也返回 `isvalid=false`**；`z_listunifiedreceivers` 能正确解析 | ❌ 改用 `z_listunifiedreceivers` |
| 5 | 钱包 DB 副作用可识别 | 可识别 | **成立**：每次成功派生 `addresses` +1 行，`diversifier_index_be` 与返回的 `diversifier_index` 精确对应 | ✅ |
| 6 | 发送能力 | 本阶段不验证 | 未验证（未发送任何交易） | — |

---

## 2. 关键发现

### 2.1 无参数调用**不幂等**（推翻此前假设）

连续 3 次 `z_getaddressforaccount([0, ["sapling"]])`：

| 次 | 返回 `diversifier_index` | 备注 |
|---|---|---|
| 1 | 4610656263 | 新地址 |
| 2 | 4610656264 | 新地址 |
| 3 | 4610656265 | 新地址 |

三次返回 **3 个不同地址**，`addresses` 表 **+3 行**。

- 含义：`sapling_ua()` 每调用一次就推进一次地址索引。现有代码"每当一轮调用一次"因此是安全的，但**不存在"无参调用 = 固定地址"的保证**。
- 正面含义：若只想拿到 n 个互不相同的 Sapling-only UA，**循环调用无参数版本即可**，无需自己管理 index。

### 2.2 显式指定 index：可用，但必须容忍失败

| index | 结果 |
|---|---|
| 0 | ❌ `-4 cannot generate an address with the requested receivers` |
| 1 | ❌ 同上 |
| 2 | ❌ 同上 |
| 5 | ❌ `-4 address at diversifier index 5 was already generated with different receiver types` |
| 4610656239 | ✅ 成功，`receiver_types=["sapling"]` |
| 4610656240 | ✅ 成功 |
| 4610656241 | ❌ `-4 cannot generate an address with the requested receivers` |
| 1000000000000 | ✅ 成功 |

两点结论：

1. **index 0 不可用**。低 index 已被历史上派生过的**其他 receiver 组合**占用（如 `["orchard","sapling","p2pkh"]`），同一 index 不能再用 `["sapling"]` 重新派生。任何"从 0 开始递增"的实现都会立刻失败。
2. **并非每个 index 都能生成 Sapling 地址**。Sapling diversifier 需要能导出有效 Jubjub point，部分 index 天然无效（4610656241 就是）。因此按 index 递增必须带**跳过 `-4` 的重试逻辑**，不能假定连号可用。

### 2.3 index 不是 u32

`4610656238` 的 11 字节大端表示 `0000000000000112D107EE`，已超出 u32 范围；`1000000000000` 同样被接受。index 空间为 ZIP 316 的 11 字节域，量级约 2^88。

### 2.4 `validateaddress` 对 UA 返回 false —— L2 方案必须改

用 `listaddresses` 取到的**完整 113 字符合法 UA** 实测：

| 方法 | 输入 | 结果 |
|---|---|---|
| `validateaddress` | 完整合法 UA（113 字符） | `{"isvalid": false}` |
| `validateaddress` | 截断 80 字符 | `{"isvalid": false}` |
| `validateaddress` | `uregtest1zzzz` | `{"isvalid": false}` |
| `z_listunifiedreceivers` | 完整合法 UA | ✅ `{"sapling": "zregtestsapling1aejau7…"}` |
| `z_listunifiedreceivers` | 上述 44 字符截断串 | ❌ `-5 Invalid address` |

`validateaddress` 无法区分"合法 UA"与"垃圾串"，**不能作为 L2 判据**。
`z_listunifiedreceivers` 既能确认地址可解析，又能直接给出 receiver 组成，**是 L2 的正确工具**：

```python
r = z("z_listunifiedreceivers", [addr])          # 失败即抛错 → 无效
assert set(r.keys()) == {"sapling"}              # 强制 Sapling-only
```

### 2.5 zallet 的 RPC 方法表（`help` 实测，共 44 个）

```
decoderawtransaction  decodescript  getrawtransaction  getwalletinfo  getwalletstatus
help  listaddresses  pczt_combine  pczt_create  pczt_extract  pczt_inspect  pczt_prove
pczt_sign  rpc.discover  signmessage  stop  validateaddress  verifymessage  walletlock
walletpassphrase  z_converttex  z_exportkey  z_exportviewingkey  z_getaccount
z_getaddressforaccount  z_getbalanceforaccount  z_getbalances  z_getnewaccount
z_getnotescount  z_getoperationresult  z_getoperationstatus  z_gettotalbalance
z_importaddress  z_importkey  z_importviewingkey  z_listaccounts  z_listoperationids
z_listtransactions  z_listunifiedreceivers  z_listunspent  z_recoveraccounts
z_sendfromaccount  z_sendmany  z_shieldcoinbase  z_viewtransaction
```

注意：**`listaddresses` 无 `z_` 前缀**，`validateaddress` 也无前缀；`z_listaddresses` / `z_validateaddress` / `getaddressinfo` 均不存在。

`listaddresses` 返回结构（含 `diversifier_index` 与 `receiver_types`），可作为地址清单的权威来源：

```json
{"diversifier_index": 4610656239, "receiver_types": ["sapling"],
 "address": "uregtest1f0hrlnran79u46kaq38ss7pw9rcmdgqeg9k…"}
```

---

## 3. 对补丁设计的影响（尚未实施）

| 决策点 | 探测前假设 | 探测后结论 |
|---|---|---|
| 地址生成方式 | 显式指定 diversifier index | 两条可行路径：①循环无参调用（简单，zallet 自选可用 index）②显式 index + 跳过 `-4`（可控、可记录）。**建议 ②**，因为地址可预测、可写入 rounds.csv 溯源 |
| 起始 index | 从 0 开始 | **不可行**。应取当前最大已用 index + 1，或使用固定高位起点（如 `10**12`） |
| 无效 index 处理 | 未考虑 | **必须**捕获 `-4` 并顺延重试，设上限防死循环 |
| L2 校验方法 | `z_validateaddress` | **改为 `z_listunifiedreceivers` + 断言 keys=={"sapling"}** |
| L1 去重断言 | 需要 | 仍需要，且是**唯一不依赖 RPC 的兜底** |
| L3 覆盖 | dry-run 不覆盖 | 不变。`pczt_create` 在方法表中存在，但本仓库既有记录显示 `pczt_sign`/`pczt_prove` 失败（24 轮），不作为本阶段依据 |

---

## 4. 副作用与环境状态

- `addresses` 表：**38 → 45（+7）**。新增行 `id=39…45`，`receiver_flags` 全为 4（Sapling-only），`diversifier_index_be` 分别为
  `0112D107EE / 0112D10807 / 0112D10808 / 0112D10809 / 0112D107EF / 0112D107F0 / E8D4A51000`（末 28 位十六进制内）。
- `sapling_received_notes` = 50、`transactions` = 50、`max(blocks.height)` = 32297，**均未变化**。
- 探测后 `wallet.db` SHA256 = `9cd5e2e0597ed4356e1756d5dce55a9a9d29d0a2fd2494fd640bbabf4d58d66f`。
- 服务已停止（`zebrad` / `zallet-zaino` 均不在运行，40232/18232 无监听）。
- **当前环境不等同于冻结快照**（多出 7 条地址记录）。下次实验前必须重新恢复快照。

---

## 5. 本记录**不**支持以下结论

1. 不得据此认为"多收款地址交易已可行"——**未发送任何交易**，`z_sendmany` 对多地址的接受性仍未验证。
2. 不得据此认为"O=3 / O=9 的手续费符合 ZIP 317"——未构造、未广播。
3. 不得把 `validateaddress` 返回的 `false` 解释为"地址派生有缺陷"——该地址已被 `z_listunifiedreceivers` 与 `listaddresses` 双重确认为合法，`false` 是该方法的适用范围问题。
4. 不得用本次探测的 `addresses` 增长推断交易层面的行为。

---

## 6. 未做的事

- 未修改 `confirmatory_bench.py` 或任何执行器代码。
- 未发送交易、未执行 `--mode gate` / `--mode confirm`。
- 未修改预注册、未合并 PR #24。
- 未删除探测产生的 7 条地址记录（保留为证据；恢复快照即可清除）。
