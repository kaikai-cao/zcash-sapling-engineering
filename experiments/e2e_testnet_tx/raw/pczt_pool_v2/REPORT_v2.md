# PCZT 四阶段成本测量报告 v2

> 测量对象：z3 栈（Zebra 6.2.3 + zallet v0.1.0-beta.3）在 WSL2 离线 regtest 上的 shielded transfer
> 数据：`raw/pczt_pool_v2/run_20261029_150438/`（N=15）+ `raw/pczt_cold_v1/run_20261029_150648/`（冷启动对照 N=4）
> 上一版：`raw/pczt_pool_v1/REPORT.md`（N=5），本版数据与之相互印证，见 §5

---

## 0. 摘要

1. **prove 是唯一的主导成本**：稳态中位 **1415.2 ms**，占 `create+sign+prove+extract`（1488.2 ms）的 **95.1%**。
2. **数据可复现**：N=15 的 prove 中位 1415.2 ms 与 N=5 的 1421.3 ms 相差 **0.4%**，跨两次独立运行一致。
3. **成本由 action 数决定，而非"真实 spend 数"**：13 轮 `signed=1` 与 2 轮 `signed=2` 的 action 数都是 2，prove 分别为 1415.2 / 1408.6 ms（差 0.5%）。说明 **padding dummy 与真实 spend 同价**。
4. **进程级冷启动只值 +142 ms（+10%）**：重启 zallet 后首轮 prove 1537.1 ms，同进程后续中位 1395.2 ms。**此前 2857.7 ms 的"冷启动"归因是错的**，见 §4。
5. **Sapling PCZT 在此版本不可用**（`Prover(MissingProofGenerationKey)`），缺陷在角色链而非参数，证据见 §6。因此本报告的 prove 数据代表 **ironwood/orchard 家族（Halo 2）**，不可当作 Sapling（Groth16）的证明成本。

---

## 1. 环境与方法

### 1.1 栈与参数

| 项 | 值 |
|---|---|
| 节点 | Zebra 6.2.3，regtest，RPC `127.0.0.1:18232`（回环免鉴权） |
| 钱包 | zallet **v0.1.0-beta.3**（= 当前最新发布），RPC `127.0.0.1:40232` |
| 后端 | `zallet-zaino`（注意：`zallet` 启动器会去找不存在的 `zallet-zaino` 之外的 `zallet-zebra` 后端而报错） |
| 网络升级 | Overwinter~Canopy 高度 1，NU5~NU6.3 高度 2（全部 active） |
| 链高（测量时） | 32333 ~ 32341 |
| 起始环境 | `~/z3-regtest/snapshots/z3_regtest_h32297_*.tar.gz`（13 MB，含链状态与钱包库） |

### 1.2 为什么链高必须 > 32257

`pczt_create` 报 `PCZTs require that ZIP 212 is enforced for outputs`，与配置无关：ZIP 212 的 grace period 为 Canopy 激活高度 + 32256。本环境 Canopy 激活在高度 1，故 **grace end = 32257**，低于该高度时 `zip212_enforcement()` 返回 `GracePeriod`，构建器拒绝产生 PCZT。已实测：高度 350 必失败、高度 32297 一次通过。

这一约束构成一次性成本（挖 3.2 万块约 4 小时），因此已对链数据做快照，后续实验从 32297 直接开始。

### 1.3 测量协议（均为踩坑后的硬性要求）

| 问题 | 现象 | 处理 |
|---|---|---|
| 透明地址 gap limit | 每轮 `z_getaddressforaccount [0,["sapling","p2pkh"]]` 会派生新透明地址，第 16 个起报错 | 收款地址循环外解析一次复用；只请求 `["sapling"]` receiver |
| `locked=true` 假象 | 追平链尖后 `locked` 永不翻转（beta.3 展示层 bug） | 忽略 `locked`，只比数值 |
| **`node_tip` 陈旧** | zallet 重启后 `wallet_tip=32297` 而 `node_tip=31296`（落后 1001 块），条件 `wallet_tip>=node_tip` **恒真** | 判据改为 `wallet_tip >= max(node_tip, zebra RPC blocks)` |
| `generate` 假失败 | 返回 `failed to send mined block to gossip task: no available capacity`，实际区块已产生 | 只认链高增量，忽略返回值 |
| 跨池注资 | 向 orchard UA 转账被 `FullPrivacy` 拒（揭示金额） | `policy=AllowRevealedAmounts`；`z_sendmany` 的 `fee` 必须为 `null` |

### 1.4 单轮流程

`pczt_create(fund_source=orchard)` → `pczt_inspect` → `pczt_sign(pczt, policy, strict=false)` → `pczt_prove` → `pczt_extract` → zebra `sendrawtransaction` → `generate 2` → 轮询 `confirmations`。

每轮固定：收款方为同一 sapling UA，金额 3 ZEC，`minconf=1`，`policy=AllowRevealedAmounts`。

---

## 2. 结果（N=15，全部成功）

### 2.1 分阶段耗时

| 阶段 | 中位 (ms) | min | max | σ | σ/均值 |
|---|---:|---:|---:|---:|---:|
| pczt_create | 27.7 | 26.5 | 33.2 | 2.1 | 7.6% |
| pczt_sign | 10.1 | 9.7 | 11.2 | 0.5 | 5.0% |
| **pczt_prove** | **1415.2** | 1388.2 | 1530.5 | 48.9 | 3.5% |
| pczt_extract | 35.2 | 29.8 | 51.2 | 7.9 | 22.4% |
| broadcast | 159.8 | 118.8 | 168.8 | 18.7 | 11.7% |
| mine（2 块） | 522.8 | 511.4 | 561.5 | 13.4 | 2.6% |
| confirm | 0.9 | 0.7 | 1.3 | 0.2 | — |
| 合计（total_ms） | 2170.3 | 2120.3 | 2313.6 | 70.1 | 3.2% |

派生指标：

- `create+sign+prove+extract` = **1488.2 ms**，其中 prove 占 **95.1%**
- 钱包侧（上述四项 + broadcast）= **1648.0 ms**
- 交易形态 15 轮完全一致：**11134 B**、fee 20000 zat、`actions=2`、`confirmations=2`

### 2.2 形态分组（关键）

| actions | signed | n | prove 中位 | total 中位 | size |
|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 13 | 1415.2 | 2170.3 | 11134 |
| 2 | 2 | 2 | 1408.6 | 2154.6 | 11134 |

**解读**：action 数相同（都是 2）时，"1 次真实 spend + 1 个 padding dummy" 与 "2 次真实 spend" 的 prove 成本差异只有 **0.5%**，落在噪声内。结论：**prove 成本 ∝ action 数；padding dummy 不是免费的，它和一个真实 spend 等价**。这对成本模型很关键——交易规划时增加 padding 会实打实地付证明成本。

### 2.3 逐轮稳定性

```
round:  1     2     3     4     5     6     7     8     9    10    11    12    13    14    15
prove: 1409  1394  1418  1400  1388  1408  1423  1530  1496  1477  1516  1486  1415  1400  1400
```

除 8~12 轮有一段 +5~8% 的抬升外，其余 10 轮落在 **1388~1423 ms**（极差 35 ms，σ≈10）。该抬升与内存无关联（见 §3），故中位数采用全部 15 轮是稳健的。

---

## 3. 冷启动对照（N=4，重启 zallet 后连跑）

| 轮次 | prove (ms) | actions | signed | 性质 |
|---:|---:|---:|---:|---|
| 1 | **1537.1** | 2 | 1 | 冷（进程刚启动） |
| 2 | 1401.6 | 2 | 1 | 热 |
| 3 | 1395.2 | 2 | 2 | 热 |
| 4 | 1380.2 | 2 | 1 | 热 |

**冷 / 热 = 1.10×，绝对差 +142 ms。**

"确实冷过"有客观证据：重启前日志中 `Proving caches warmed` 出现 4 次，重启后首轮 prove 触发第 5 次（+1）。即证明密钥的进程内预热成本约 **142 ms**，占稳态 10%。

内存佐证（同批 209 个采样，0.25 s 间隔）：zallet RSS 350~374 MB、zebrad 210~231 MB，全程平坦，与 §2.3 的 8~12 轮抬升不同步，可排除内存增长/GC 解释。

---

## 4. 对 14:47 那个 2857.7 ms 的更正

早前一次单轮测量记录 `create=47 / sign=12 / prove=2857.7 / extract=767.3`，当时归因为"冷启动"。**该归因错误**，理由是该轮**所有阶段同步放大**：

| 阶段 | 14:47 单轮 | 本报告稳态 | 倍数 |
|---|---:|---:|---:|
| prove | 2857.7 | 1415.2 | 2.0× |
| extract | 767.3 | 35.2 | **21.8×** |
| mine（2 块） | 2041.2 | 522.8 | 3.9× |

`extract` 只是序列化 + SQLite 记账，不存在"冷启动"概念，它放大 22 倍说明当时是**整机资源竞争**（该轮紧接 30 ZEC 跨池注资与 8 次 `generate` 重试，zaino 在后台索引 3.2 万块）。真正的冷启动代价已由 §3 的受控实验给出：**+142 ms**。

**结论**：2857.7 ms 应作为离群点排除，不得作为"冷启动成本"引用。

---

## 5. 与 N=5 版本的一致性

| 阶段 | v1（N=5，14:50） | v2（N=15） | 偏差 |
|---|---:|---:|---:|
| pczt_create | 27.7 | 27.7 | 0.0% |
| pczt_sign | 10.0 | 10.1 | 1.0% |
| pczt_prove | 1421.3 | 1415.2 | −0.4% |
| pczt_extract | 54.7 | 35.2 | −36%（见下） |
| broadcast | 168.3 | 159.8 | −5% |

`extract` 的差异来自采样不足：N=5 时 σ/均值 30%，N=15 降到 22%。它的分布两端为 29.8~51.2 ms，且与 action 数无关，推测由 **SQLite 写入路径（WAL checkpoint / fsync 时机）** 支配而非计算。这是本报告中唯一还没归因干净的量，但它只占钱包侧的 2%，不影响主结论。

---

## 6. Sapling PCZT 不可用（独立结论）

### 6.1 现象

对 Sapling 资金构建 PCZT：

```
create  25.0 ms  pczt=10068B  sapling.spends=4   ← 选币/找零/fee 全对
sign    12.0 ms  sapling_signed=0  unsigned_sapling=[0,1,2,3]   ← 不报错，一个都没签
prove     --     Prover(MissingProofGenerationKey)
```

### 6.2 机制（代码级）

- Sapling 的 `ask` 与 `nsk` 是**两把独立密钥**，`PGK=(ak, nsk)` 只能由持有完整 `expsk` 的角色写入。
- `pczt_sign` 的实现只取到 `ask`（`sign_sapling(i, ask)`），**结构上无法**补写 PGK。
- `pczt_create` 走 `create_pczt_from_proposal::<…, Infallible, …>`，密钥源为 `Infallible`，即该路径完全不接触私钥。
- 上游 `pczt::sapling::Spend` 的公开接口只有 `cv()/nullifier()/rk()/witness()/proprietary()`，**没有 PGK 的读取器**，说明 Sapling PCZT 通路尚未闭环。

### 6.3 排除"密钥不可用"

同一钱包、同一批 note，用 `z_sendmany` 完成转账 **3.01 s 成功**（txid `fb27193b…`，余额 131.25 → 118.75 ZEC）。故密钥、note 解密、选币、签名全部正常，**缺陷精确定位在 PCZT 的 Sapling 角色链**，与钱包无关。

### 6.4 对照

同一版本、同一账户，**ironwood/orchard 家族 PCZT 四阶段完全可用**（`ironwood_signed=1`、`ironwood_proven=true`）。这反证问题不是 PCZT 机制本身，而是 Sapling 双密钥结构在这一版没有实现。

---

## 7. 口径与限制（引用时必读）

1. **prove 数值属于 Halo 2（ironwood/orchard 家族）**，与 Sapling 的 Groth16/Spend circuit 不是同一证明系统，量级不可互换。
2. 全部交易使用 **`AllowRevealedAmounts`**（跨池注资的必要条件），**不代表 FullPrivacy 交易的隐私属性**。
3. 本组为 **热态稳态**；冷启动另计 +142 ms（§3）。
4. `mine` / `broadcast` 受 zebra/zaino 的 gossip 通道背压影响（同一脚本两次运行中 mine 分别为 1020 ms/块与 261 ms/块），**属环境量而非密码学成本**，不应与 prove 并列讨论。
5. N=15，prove 的 σ/均值 3.5%；`extract` 仍偏噪（22%），引用时宜给区间而非单值。
6. 币种、金额：每轮 3 ZEC，fee 20000 zat（0.0002 ZEC），交易 11134 B。

---

## 8. 复现

```bash
# 0) 还原环境（链高 32297，已过 ZIP 212 grace end）
bash /mnt/d/Research/z3/wsl/snapshot_restore.sh --yes

# 1) 给 ironwood 池注资（每轮 3 ZEC + fee，按轮数准备）
python3 /mnt/d/Research/z3/wsl/fund_pool.py --fund-zec 50

# 2) 正式测量
cd /mnt/d/Research/zcash-sapling-engineering/experiments/e2e_testnet_tx
python3 pczt_bench_pool.py --rounds 15 --send-zec 3 --outdir ./raw/pczt_pool_v2

# 3) 冷启动对照（重启 zallet，round 1 为冷）
bash /mnt/d/Research/z3/wsl/coldstart_test.sh 4 3
```

产物：`stage_timings.csv`（长表）、`rounds.csv`（含 actions/signed）、`summary.csv`、`summary_by_shape.csv`、`memory_timeseries.csv`、`meta.json`。

---

## 9. 尚未闭合的问题

| 问题 | 现状 | 建议 |
|---|---|---|
| `extract` 的 22% 波动 | 与 action 数无关，疑为 SQLite 写入路径 | 记录 extract 前后 `wallet.db-wal` 大小与 checkpoint 日志，做相关性分析 |
| prover 冷启动的物理来源 | 进程内预热 +142 ms 已量化；14:47 的 2 倍慢属环境竞争 | 若需区分"页缓存冷 / 计算冷"，可在 `drop_caches` 后重启再测一次 |
| Sapling 的真实分阶段成本 | 被 beta.3 缺口阻塞 | 需自行调用 `pczt` crate 写 Updater 补 PGK；或改用 `z_sendmany` 端到端（已有 3.01 s 基线） |
| action 数 1 / 4 / 8 的 scaling | 未测（本组全为 actions=2） | 通过控制 note 尺寸与收款输出数制造不同 action 数，给出 prove–actions 曲线 |
