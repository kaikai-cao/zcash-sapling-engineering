# PCZT 四阶段端到端测量报告（regtest / zallet v0.1.0-beta.3）

> 数据目录：`raw/pczt_pool_v1/run_20261029_145043/`
> 采集时间：2026-10-29 14:50:43 – 14:51:2x（本地时间）
> 轮次：N = 5，全部成功

## 1. 环境与参数

| 项 | 值 |
|---|---|
| 节点 | Zebra 6.2.3（二进制 mtime 2026-07-28） |
| 钱包 | zallet **v0.1.0-beta.3**（+ zallet-zaino 后端） |
| 网络 | regtest，离线（127.0.0.1，无外部网络参与） |
| 链高（测量期间） | 32287 → 32296 |
| 共识分支 | `37a5165b`（NU6.3），tx version 6 |
| 账户 | `5fd7056a-…-d80b0556fea9`（account index 0，`has_spend_key=1`，birthday=308） |
| 资金池 | ironwood（orchard 家族接收者）；sapling 池仅作对照基线 |
| 隐私策略 | `AllowRevealedAmounts`（跨池注资必需，见 §5.2） |
| 每轮金额 / minconf | 3 ZEC / 1 |
| 挖块 | 每轮 2 块（`mine` 阶段） |

## 2. 方法

单轮严格按 PCZT 角色顺序执行，每阶段单独计时（`time.monotonic()` 前后夹逼）：

```
pczt_create  → pczt_sign → pczt_prove → pczt_extract → broadcast → mine ×2 → confirm
```

- 收款地址在循环外一次性解析并复用（避免透明地址 gap limit=16）
- 每轮前后各做一次同步等待，判据为 `wallet_tip >= node_tip`（忽略 `locked` 字段）
- 挖块判据为**链高增量**，不使用 `generate` 返回值（见 §5.3）

## 3. 结果（N=5，单位 ms）

| 阶段 | 中位数 | min | max | σ | 说明 |
|---|---:|---:|---:|---:|---|
| pczt_create | **27.7** | 26.7 | 28.1 | 0.6 | 选币 + 构造 + 手续费 + 找零 |
| pczt_sign | **10.0** | 9.8 | 10.1 | 0.1 | 1 个真实 action 签名（dummy 已在创建时签） |
| pczt_prove | **1421.3** | 1403.1 | 1513.2 | 53.2 | 2 个 ironwood action 的证明 |
| pczt_extract | **54.7** | 30.7 | 74.9 | 16.4 | 序列化 + 钱包记账（方差最大） |
| broadcast | 168.3 | 152.7 | 169.4 | 7.0 | zallet → zaino → zebra，含本地 RPC |
| mine | 2041.2 | 2002.7 | 2056.5 | 25.3 | 2 块，≈ **1020.6 ms/块** |
| confirm | 0.9 | 0.8 | 0.9 | 0.0 | mempool 内查确认 |
| **total（含挖块）** | **3706.7** | 3674.3 | 3823.0 | 67.8 | |

### 派生指标

- **钱包侧成本**（create+sign+prove+extract+broadcast）= **1681.3 ms**，其中 prove 占 **84.5%**
- **纯 PCZT 角色链**（create+sign+prove+extract）= **1513.7 ms**，其中 prove 占 **93.9%**
- 挖块（2041.2 ms）是本机 regtest 的出块开销，**不属于钱包成本**，报告中应单列
- 交易形态：`11134 B`、2 个 ironwood action（1 真实 + 1 padding dummy）、fee 20000 zat

### 形态一致性校验（决定中位数是否有效）

5 轮以下字段**完全相同**，可视为同一形态的重复测量：

| 字段 | 5 轮取值 |
|---|---|
| size_bytes | 11134 ×5 |
| size_b64 | 9224 ×5 |
| fee_zat | 20000 ×5 |
| ironwood.actions | 2 ×5 |
| ironwood_signed | 1 ×5 |
| confirmations | 2 ×5 |

### 内存（75 采样 @0.25 s，`VmRSS`）

| 进程 | min | 中位 | max |
|---|---:|---:|---:|
| zebrad | 796.5 MB | 809.3 MB | 906.6 MB |
| zallet | 349.9 MB | 379.7 MB | 438.2 MB |

## 4. 对照基线（非 PCZT 路径）

同一钱包、同一 Sapling 池，用 `z_sendmany` 完成「构造+证明+签名+广播」的合并耗时：

- **3.01 s**（2026-10-29 14:44，txid `fb27193b…`，10 ZEC 自转，含 4 个 Sapling spend）

与 PCZT 的分阶段之和（wallet 侧 1681 ms）不可直接比较：池不同、spend 数不同、且 `z_sendmany` 是同步阻塞到广播完成。仅作量级参考。

## 5. 工具链发现（可独立引用）

### 5.1 Sapling PCZT 在 zallet v0.1.0-beta.3 不可用

**证据链（实测 + 代码级）**：

1. `pczt_create` 成功（4 个 Sapling spend，金额/找零/手续费全部正确，`value_balance_zat=20000`）
2. `pczt_sign` 返回 `sapling_signed=0`、`unsigned_sapling=[0,1,2,3]`，`strict=true` 时报 "4 sapling … remain unsigned"
3. `pczt_prove` 报 `Failed to create Sapling proofs: Prover(MissingProofGenerationKey)`
4. 签名 hint 完好（`seed_fingerprint` 与钱包 `hd_seed_fingerprint` 一致），不是 hint 丢失
5. 同一钱包、同一批 note，`z_sendmany` 3.01 s 成功 → **密钥与 note 完全可用**
6. 根因：Sapling 的 `ask` 与 `nsk` 是两把独立密钥，`proof_generation_key=(ak, nsk)` 只能由持有完整 `expsk` 的角色写入；`pczt_sign` 的 API 只传 `ask`，结构上无法补写；`zallet` 的 `pczt_create` 走 `create_pczt_from_proposal::<…, Infallible, …>`（密钥源为 `Infallible`，即完全不触碰私钥）
7. 上游侧同样未闭环：`pczt::sapling::Spend` 的公开接口只有 `cv()` / `nullifier()` / `rk()` / `witness()` / `proprietary()`，**没有 PGK 读取器**

> 对照：同一版本下 Orchard 家族池的 `ironwood_signed=1`、`ironwood_proven=true`，四阶段全通 —— 说明 PCZT 机制本身可用，缺口专属于 Sapling 的双密钥结构。

### 5.2 跨池注资必须放宽隐私策略

向 orchard/ironwood UA 转账，`FullPrivacy` 被拒：

```
Could not send to the Ironwood shielded pool without spending non-Ironwood
funds, which would reveal transaction amounts. THIS MAY AFFECT YOUR PRIVACY.
Resubmit with the 'privacy_policy' ...
```

改为 `AllowRevealedAmounts` 后成功（注资 30 ZEC，10.03 s）。**这是测量口径的一部分**：本轮所有交易都携带该策略，故金额对第三方可见，不能当作 FullPrivacy 交易的性能代表。

### 5.3 `generate` 的 gossip 报错是假失败

```
failed to send mined block to gossip task: no available capacity
```

8 次连续报错，但链高实际 32279 → 32287（+8），交易拿到 8 个确认。**判据必须改为链高增量**，否则会把成功误判为失败。

## 6. 口径限制（引用时必须注明）

1. **池不对应**：本轮测量对象是 ironwood（orchard 家族，Halo 2 递归证明），**不是 Sapling（Groth16）**。prove 一列不能当作 Sapling 证明成本使用；create/sign/extract 的管线开销与池相关性较弱，可作参考。
2. **证明缓存已预热**：正式测量前（14:49）已成功 prove 一次，5 轮均为稳态，不含证明密钥冷启动。冷启动单次实测 2857.7 ms（同形态 2 action、同 11134 B）。
3. **单机离线**：broadcast 只含本地 RPC + zaino 内部链路，不含 P2P 传播；mine 为本机 CPU 出块，不代表真实网络出块时间。
4. **N=5**：extract 的 σ 相对均值达 30%，若报告需要强结论，建议 N ≥ 15。
5. **所有交易带 `AllowRevealedAmounts`**，非 FullPrivacy 交易。

## 7. 未解问题 / 下一步

1. **冷启动 vs 真实 spend 数的归因未定**：首次 prove 2857.7 ms（2 个真实 action）vs 稳态 1421.3 ms（1 真实 + 1 dummy），两者 action 数、交易体积相同。要分离两个因素，需做：
   - 重启 zallet 后立刻跑 1 轮（冷启动复现），或
   - 预先拆细 note，构造 2/4 个真实 spend 的稳态测量（scaling 曲线）
2. **Sapling 侧只能给端到端**：PCZT 分阶段不可得（§5.1），可考虑编译 `zcash/wallet` main 验证 PGK 是否已修，但上游 `Spend` 无 PGK 访问器，成功概率不高。
3. **重复性**：建议把链数据打快照（当前链高 32296，已过 ZIP 212 grace period），避免以后为新实验重挖 3.2 万块（本次一次性成本约 4 小时，实测 2.2 blk/s）。

## 8. 复现

```bash
# 1) 注资（首次，或目标池余额不足时）
python3 /mnt/d/Research/z3/wsl/pczt_orchard2.py --fund-zec 30 --send-zec 5

# 2) 5 轮四阶段测量
cd /mnt/d/Research/zcash-sapling-engineering/experiments/e2e_testnet_tx
python3 pczt_bench_pool.py --rounds 5 --send-zec 3 --outdir ./raw/pczt_pool_v1
```

产物：`stage_timings.csv`（长表）、`rounds.csv`（宽表）、`summary.csv`（统计）、`memory_timeseries.csv`、`meta.json`。
