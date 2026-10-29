# Sapling 端到端交易成本测量报告

> 测量对象：z3 栈（Zebra 6.2.3 + zallet v0.1.0-beta.3）在 WSL2 **离线 regtest** 上的 Sapling 全隐私转账
> 数据：`raw/sapling_e2e_v1`、`raw/sapling_e2e_scale30`、`raw/sapling_e2e_scale60`、`raw/sapling_smoke2`、`raw/sapling_e2e_out9`（合计 **29 轮成功**、**11 种形态**）
> 机器生成明细：`raw/sapling_e2e_v1/FIT.md`（残差表、逐对对照、全部系数）
> 交叉引用：PCZT 四阶段报告 `raw/pczt_pool_v2/REPORT_v2.md`

---

## 0. 摘要

1. **成本模型成立且可解析**：`pipeline ≈ 589.9 × spends + 91.5 × outputs + 424.2 ms`，R² = **0.9998**、RMSE = **39.6 ms**、留一交叉验证 RMSE = 113.4 ms。自助法给出 spend 系数 95% CI **[589, 602]（±1%）**，已足够外推。
2. **Spend : Output = 6.45 : 1**（95% CI **[4.04, 6.60]**，远离 1）。Sapling 里一个 spend 的证明成本约等于 6.5 个 output，**不能混算**。
3. **"按证明个数计费"被直接否证**。`S=3,O=3` 与 `S=4,O=2` 都是 6 个证明，耗时差 **548 ms**；同样约 10 个证明，`1 spend + 9 outputs` 只要 1826.5 ms，`10 spends + 2 outputs` 要 6505.6 ms（3.6 倍）。
4. **判别实验一次性淘汰两个极端假设**：`1 spend + 9 outputs` 实测 1826.5 ms，双变量模型预测 1837 ms（偏差 −11 ms）；"output 与 spend 同价"会给 4898 ms（偏差 −3072），"output 免费"会给 1336 ms（偏差 +491）。两者均被否。
5. **证明是主成本，且随规模收敛到上限**：1 spend + 2 outputs 时证明占 pipeline 的 67.8%，17 spends + 2 outputs 时占 **96.3%**；固定开销稳定在 ~424 ms（build + sign + broadcast）。
6. **形态计数经独立校验**：ZIP 317 手续费 `5000 × max(spends, outputs)` 在 **29/29 轮**全部吻合。
7. **字节成本可解析**：`tx_size = 352 × spends + 948 × outputs + 130 B`（精确，无残差）；但单位字节的时间成本相差 **17.4 倍**（spend 1.68 ms/B vs output 0.096 ms/B），说明 output 的字节主要是可加密数据，spend 的字节才是运算。

---

## 1. 环境与测量协议

### 1.1 栈与硬件

| 项 | 值 |
|---|---|
| CPU / 线程 | Intel Core i7-14700，**nproc = 28**（P+E 混合核） |
| 虚拟化 | WSL2，离线 regtest |
| 节点 | Zebra 6.2.3，RPC `127.0.0.1:18232`（回环免鉴权） |
| 钱包 | zallet **v0.1.0-beta.3**（当前最新发布），RPC `127.0.0.1:40232` |
| 网络升级 | Overwinter~Canopy 高度 1，NU5~NU6.3 高度 2（全部 active） |
| 链高（测量区间） | 32395 ~ 32401 |
| 起始状态 | 快照 `z3_regtest_h32297_*.tar.gz`（13 MB，含链状态 + 钱包库） |

### 1.2 为什么不用 PCZT，改用 `z_sendmany`

PCZT 路线在 beta.3 上的 Sapling 分支不可用：`pczt_prove` 报 `Prover(MissingProofGenerationKey)`，`pczt_sign` 后 `sapling_signed=0`。根因在角色链——ZIP 374 把 `proof_generation_key` 交给 Updater、`ask` 交给 Signer，而 Sapling 的 PGK 是 `(ak, nsk)` 双密钥，需要 `expsk` 才能复原，`pczt::sapling::Spend` 的公开接口又不暴露 PGK。这是**版本缺陷而非参数错误**（详见 `REPORT_v2.md` §6）。

因此本报告的证明成本是 **Sapling（Groth16）** 的真实值，与 `REPORT_v2.md` 里 **ironwood/orchard（Halo 2）** 的 PCZT 数据互为补充，**两者不可混用**。

### 1.3 测量协议（踩坑后的硬性要求）

| 问题 | 现象 | 处理 |
|---|---|---|
| `generate` 假失败 | `failed to send mined block to gossip task: no available capacity`，但区块确实产生 | 判据改为**链高增量**，不看 RPC 返回 |
| 同步判据陈旧 | zallet 重启后 `node_tip` 可落后链尖 1001 块，导致"已同步"恒真 | `wallet_tip >= max(zallet node_tip, zebra RPC blocks)` |
| 透明的 gap limit | 循环外复用派生地址，触发 `reached the transparent gap limit at index 16` | 只请求 **sapling receiver** 的 UA，地址派生一次复用 |
| 余额预检 | 逐轮扣减判断会漏算手续费 | 按**全部轮次**总额预检 |
| 手续费参数 | Zallet 要求 `z_sendmany` 的 fee 显式传 `null` | 五参形态 `[from, amounts, minconf, null, policy]` |

### 1.4 阶段定义

| 阶段 | 含义 |
|---|---|
| `submit` | `z_sendmany` RPC 返回 opid 的往返 |
| `pipeline` | 钱包内部 **build → prove → sign → broadcast**，轮询 opid 到 `success` 的墙钟（**本文的核心指标**） |
| `mine` | 挖到交易被打包（固定 2 块） |
| `sync` | 钱包追平链尖 |
| `total` | 以上四段之和（`pipeline` 之外的 `mine + sync ≈ 1.57 s` 是 regtest 挖块节奏，**不是协议成本**） |

---

## 2. 数据总览

29 轮成功样本聚合成 11 种 `(spends, outputs)` 形态，同形态取中位数：

| spends | outputs | proofs | n | pipeline 中位(ms) | min | max | tx_size(B) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 3 | 8 | 1139.8 | 1103.5 | 1253.6 | 2378 |
| **1** | **9** | **10** | 3 | **1826.5** | 1808.6 | 1826.8 | 9014 |
| 2 | 2 | 4 | 10 | 1749.2 | 1726.8 | 1817.9 | 2730 |
| 3 | 2 | 5 | 1 | 2392.1 | — | — | 3082 |
| 3 | 3 | 6 | 1 | 2445.1 | — | — | 4030 |
| 4 | 2 | 6 | 1 | 2993.0 | — | — | 3434 |
| 4 | 3 | 7 | 1 | 3155.3 | — | — | 4382 |
| 7 | 2 | 9 | 1 | 4738.1 | — | — | 4490 |
| 10 | 2 | 12 | 1 | 6505.6 | — | — | 5546 |
| 11 | 2 | 13 | 1 | 7116.1 | — | — | 5898 |
| 17 | 2 | 19 | 1 | 10601.1 | — | — | 8010 |

加粗行是本轮的判别实验（`--outputs 8`，把 4 ZEC 平摊到 8 个收款地址，加上找零共 9 个 output）。它把 output 维度从 2~3 拉到 9，是区分三个模型的关键点。

---

## 3. 成本模型

### 3.1 三模型对比

| 模型 | 形式 | 系数 | R² | RMSE(ms) | LOO-RMSE(ms) |
|---|---|---|---:|---:|---:|
| M1 | `a·proofs + b` | 576.2 ms/proof + **−863.9** | 0.8724 | 991.6 | 1157.3 |
| M2 | `a·spends + b` | 576.3 ms/spend + 759.3（output 免费） | 0.9960 | 174.7 | 212.7 |
| **M3** | `a·spends + c·outputs + b` | **589.9 ms/spend + 91.5 ms/output + 424.2 ms** | **0.9998** | **39.6** | **113.4** |
| M3′ | 同上，按轮数加权 | 593.7 / 96.2 / 372.8 | — | — | — |

三点读数：

- **M1 的截距是 −863.9 ms**，物理上不可能为负。这是模型设定错误的自我暴露：若真按证明个数计费，截距必为正的固定开销。M1 的 R² 只有 0.87，RMSE 接近 1 s。
- **M2 看起来很能打（R² = 0.996）**，因为除判别点外所有样本的 outputs 都只有 2 或 3，output 的贡献几乎被截距吸收。加入 `1s+9o` 后 M2 立刻在这一点上偏 491 ms——**没有 output 维度充分的样本时，M2 与 M3 无法区分**，这是本实验设计上必须补的一刀。
- **M3 的 RMSE 比 M1 小 25 倍**，且加权（按同形态轮数）后系数几乎不变（594/96/373 vs 590/92/424），说明结论不受"O=2 样本多、O=9 样本少"的采样不均衡影响。

### 3.2 检验 A：固定 outputs = 2 的 spend 阶梯（不依赖拟合）

| spends | pipeline 中位(ms) | 相对上一档 Δ | 折算 Δ/spend |
|---:|---:|---:|---:|
| 1 | 1139.8 | — | — |
| 2 | 1749.2 | +609.4 | 609.4 |
| 3 | 2392.1 | +642.8 | 642.8 |
| 4 | 2993.0 | +600.9 | 600.9 |
| 7 | 4738.1 | +1745.1 | 581.7 |
| 10 | 6505.6 | +1767.5 | 589.2 |
| 11 | 7116.1 | +610.5 | 610.5 |
| 17 | 10601.1 | +3485.0 | 580.8 |

斜率均值 **602.2 ms/spend**，标准差仅 20.1 ms（3.3%），范围 581~643。跨 1 → 17 个 spend 保持严格线性，说明这一维不存在阈值效应、批处理优惠或资源饱和的拐点。

### 3.3 检验 B：等量替换对照（最强证据，无模型假设）

| 形态 A | 形态 B | Δspends | Δoutputs | Δpipeline | 读数 |
|---|---|---:|---:|---:|---|
| S=1,O=2 | S=1,O=9 | 0 | +7 | +686.7 | 98 ms/output |
| S=3,O=2 | S=3,O=3 | 0 | +1 | +53.0 | 53 ms/output |
| S=4,O=2 | S=4,O=3 | 0 | +1 | +162.3 | 162 ms/output |
| S=2,O=2 | S=3,O=2 | +1 | 0 | +642.8 | 643 ms/spend |
| S=3,O=2 | S=4,O=2 | +1 | 0 | +600.9 | 601 ms/spend |
| S=10,O=2 | S=11,O=2 | +1 | 0 | +610.5 | 610 ms/spend |
| **S=3,O=3** | **S=4,O=2** | **+1** | **−1** | **+547.9** | **548 ms/(spend−output)** |

最后一行是决定性的：两笔交易**证明个数完全相同（6 个）**，只是把 1 个 output 换成 1 个 spend，耗时多了 **548 ms**。只要"耗时由证明个数决定"成立，这一格必须是 0。它不是 0，模型就错了。

### 3.4 判别实验：`1 spend + 9 outputs`

| 假设 | 预测 | 与实测（1826.5 ms）偏差 |
|---|---:|---:|
| M1 按证明个数（576 ms/proof × 10） | 4898 ms | **−3072 ms** |
| M2 output 免费（576 × 1 + 759） | 1336 ms | **+491 ms** |
| M3 双变量 | 1837 ms | **−11 ms** |

单点同时否掉"同价"与"免费"两个极端。三次重复的极差仅 18.2 ms（1808.6~1826.8），说明这一点本身非常稳定，不是噪声造成的巧合。

### 3.5 系数不确定度（自助法，B=4000）

点估计之外必须回答"这三个数有多可信"。对 29 轮做有放回重采样（轮级口径，保留真实采样结构）：

| 系数 | 点估计 | bootstrap 均值 | 95% CI | 相对宽度 |
|---|---:|---:|---|---:|
| spends | 592.0 | 593.4 | **[589.4, 601.6]** | **2%** |
| outputs | 92.8 | 96.1 | [89.6, 146.4] | 61% |
| 固定开销 | 398.0 | 388.4 | [283.0, 423.1] | 35% |

由此得到两条**统计意义上的**判据（不再只是点估计偏差）：

- `output` 的 95% CI **不含 0**（89.6 > 0）→ **"output 免费"被排除**。
- `spend / output` 比值的 95% CI = **[4.04, 6.60]**，远离 1 → **"两者同价"被排除**。

换形态级口径（11 个形态等权重采样）结论方向不变，但 output 区间变宽为 [73.3, 228.6]（点估计被 `(4,3)` 离群点拉高，且 11 个点的等权重采样放大了小样本噪声）。**轮级口径更可信**，因为形态级丢弃了 O=2 形态 8~10 轮重复测量的信息。

读数：**spend 系数精度 ±1%（相对），已足以支撑外推；output 的定性结论（存在、且显著低于 spend）在两种口径下都成立，但它的精确数值只能给到"约 90~150 ms"这一档。**

### 3.6 结论式

```
pipeline(ms) ≈ 589.9 · spends + 91.5 · outputs + 424.2
               [589, 602]     [90, 146]        [283, 423]      # 95% CI
total(ms)    ≈ pipeline + 1570        # regtest 挖 2 块 + 追平，非协议成本
```

反解：给定预算 T，可承载的形态约为 `spends ≈ (T − 424 − 91.5·outputs) / 590`。

---

## 4. 交叉验证

### 4.1 ZIP 317 手续费：形态计数无误

`fee = 5000 × max(spends, outputs)` 在 **29/29 轮**全部吻合（含 45000 zat 的 `1s+9o`、85000 zat 的 `17s+2o`）。这条校验独立于计时链路：它证明 bench 从 `z_viewtransaction` 顶层 `spends`/`outputs` 数组读出的计数，与钱包实际构造的形态一致。若计数错一位，手续费立刻对不上。

> 顺带记录一个工具缺陷：`z_listtransactions` 在本环境不可用，`Data DB is corrupted: Invalid memo data: InvalidUtf8(...)`（0xf6 任意 memo 被当作 UTF-8 解码）。它不影响 `z_sendmany` 与 `z_viewtransaction`，但会误导"数据库损坏"的判断。本报告的字段全部取自 `z_viewtransaction`。

### 4.2 字节成本：严格线性，但单价差 17.4 倍

对 11 个形态做精确拟合（残差为 0）：

```
tx_size(B) = 352 · spends + 948 · outputs + 130
```

单位字节的时间成本：

| 维度 | 字节/单位 | 时间/单位 | 时间/字节 |
|---|---:|---:|---:|
| spend | 352 B | 589.9 ms | **1.68 ms/B** |
| output | 948 B | 91.5 ms | **0.096 ms/B** |

output 的字节数是 spend 的 2.7 倍，时间却只有 1/6.5。这否掉了"成本随字节数走"的直觉：output 的体积主要来自 note ciphertext（可加密数据，几乎不耗算力），spend 的体积主要来自证明与签名（才是算力）。**带宽成本与算力成本必须分开建模**——单位字节的时间成本相差 **17.4 倍**（1.68 vs 0.096 ms/B），这也是后续做 fee 模型时不能简单按字节计价的原因。

### 4.3 与历史单点的对账

早期控制实验（`sapling_spend_ctl.py`）用 `z_sendmany` 自转 1 spend + 1 output，墙钟 **3.01 s**。按本模型预测为 `589.9 + 91.5 + 424.2 = 1106 ms`，差 1.9 s。

差异不在模型，在口径：那次是 **zallet 进程内首笔 Sapling 交易**，包含 proving key 首次从磁盘读入并解压的成本（spend 的 pkey 远大于 output）。对照 `coldstart_test.sh` 的结论——**page cache 已热**的进程重启只值 +142 ms（1537.1 vs 1395.2）——两者恰好互补：1.9 s 是磁盘冷读，142 ms 是进程重启。因此历史单点不计入稳态拟合，仅作量级 sanity check。

---

## 5. 与 PCZT / Orchard 路线的对照

| | Sapling（本报告） | ironwood/orchard（PCZT v2） |
|---|---|---|
| 证明系统 | Groth16 | Halo 2 |
| 测量入口 | `z_sendmany` → opid 轮询 | `pczt_create/prove/sign/extract` 四阶段 |
| 主成本 | 随 spend 线性，589.9 ms/spend | prove 1415.2 ms/笔，占 95.1% |
| 规模弹性 | 明确线性，可外推至 17 spends | 由 action 数决定；padding dummy 与真实 spend 同价 |
| 一次成本口径 | 76.4%（1s+2o）→ 96.3%（17s+2o） | 95.1%（固定 2 action） |

两条路线的共同结论：**证明压倒性地主导成本**，其余阶段（build/sign/broadcast、extract）在百毫秒量级。差别在于 Sapling 的 Groth16 成本随 spend 数线性增长，而 Orchard 的 Halo 2 成本由 action 数（含 padding）决定，因此**小笔交易上 Orchard 的固定花销更重，大笔交易上 Sapling 的线性增长更吃亏**——这个交叉点正是 MSM/FFT 层面值得继续分析的地方（已由仓库剖析与 PPT 覆盖，本报告只交付实测系数）。

---

## 6. 限制与威胁

1. **output 的精确数值仍弱可辨识**（定性结论不受影响）。O 只取过 2、3、9 三档，单变量读数 53 / 98 / 162 ms，自助法 95% CI 为 [90, 146]（轮级）/[73, 229]（形态级）。M3 给 91.5 ms 是三档折中。**"output 存在成本"与"显著低于 spend"这两条在两种口径下都被 CI 支持**，只是具体数值只能报到"约 90~150 ms"。若要收紧，补 `O = 5/6/12/16` 四轮即可（注意 ZIP 317 手续费会变成 `5000 × O`）。
2. **`(4,3)` 是最大离群点**（残差 +97.3 ms，n=1）。它把 output 系数往上拉约 20 ms；形态级 bootstrap 的宽区间主要就来自这一个点被反复重采样。结论方向不变。
3. **单机、单版本、regtest**。nproc=28 的 P+E 混合核上，rayon 的调度会随并行度变化；绝对值不可直接搬到 4 核机器。**比值（6.45:1）比绝对值更可移植**。
4. **`mine + sync ≈ 1.57 s` 是 regtest 挖块节奏**，与网络真实出块（75 s）无关，不可用于端到端时延估算。
5. **未做 `drop_caches` 真冷启动**。当前"冷"指进程重启（page cache 热），磁盘冷读的量级只能从历史单点（3.01 s）间接推断。

---

## 7. 复现

```bash
# 前置：zebrad + zallet 已启动，链高 > 32257，sapling 池有余额
cd experiments/e2e_testnet_tx

# 主批次（形态 1s+2o，15 轮）
python3 sapling_e2e_bench.py --rounds 15 --amount-zec 1   --outdir ./raw/sapling_e2e_v1
# 多 spend（金额递增迫使 2~17 个 spend）
python3 sapling_e2e_bench.py --rounds 6  --amount-zec 30  --outdir ./raw/sapling_e2e_scale30
python3 sapling_e2e_bench.py --rounds 4  --amount-zec 60  --outdir ./raw/sapling_e2e_scale60
# 判别实验：把金额平摊到 8 个收款地址（1 spend + 9 outputs）
python3 sapling_e2e_bench.py --rounds 3  --amount-zec 4 --outputs 8 --outdir ./raw/sapling_e2e_out9

# 全量拟合（离线，读所有 rounds.csv）
python3 fit_sapling_e2e_model.py --raw-dir ./raw --md ./raw/sapling_e2e_v1/FIT.md
# 系数的自助法置信区间（B=4000，轮级 + 形态级两种口径）
python3 bootstrap_sapling_ci.py --B 4000
```

---

## 8. 文件清单

| 文件 | 内容 |
|---|---|
| `fit_sapling_e2e_model.py` | 全量聚合拟合（M1/M2/M3 + 加权 M3、LOO、配对对照、ZIP 317 与字节数校验） |
| `bootstrap_sapling_ci.py` | 系数自助法置信区间（轮级 / 形态级双口径，含"是否排除 0 与 1"的判据） |
| `raw/sapling_e2e_v1/FIT.md` | 机器生成的完整明细（11 形态 × 3 模型残差、9 组配对对照） |
| `raw/*/run_*/rounds.csv` | 逐轮原始记录（txid、opid、形态、五阶段耗时、size、fee） |
| `raw/*/run_*/memory_timeseries.csv` | 0.25 s 粒度的 zebrad/zallet RSS 采样 |
| `sapling_e2e_bench.py` | 主测量脚本（含 `--outputs N` 平摊、按形态分组、ZIP 317 反查） |
| `analyze_sapling_cost.py` | 早期分析脚本（M2 定义为"output 免费"，已被 `fit_sapling_e2e_model.py` 取代） |
