# 完整 Sapling 交易构造计时（1 spend + 2 outputs，2026-10-22）

**状态：** 测量完成，7/7 判据 PASS（主判据 18/18）。本实验**不产生优化收益结论**，只回答"一笔固定形状的 Sapling 交易，从构造器入口到序列化字节，本地要多久、时间花在哪里"。

**预注册（先于任何代码与测量）：** [`sapling_tx_construction_preregistration_20261022.md`](sapling_tx_construction_preregistration_20261022.md)。冻结后的两处修订分别记录在该文档 §9（取消参照臂、主判据 18/18）与 §10（手续费口径，见本文 §9）。

**测量日期：** 2026-10-22（单批次 `tx_construct_20261022`）
**主机：** Windows 11、Intel Core i7-14700（8 P 核 ×HT + 12 E 核，28 LP）、32 GB RAM
**工具链：** `rustc 1.98.1 (48a229cea 2026-09-01)`，release
**实验二进制：** `experiments/transaction-smoke/target/release/tx_construct_bench.exe`，SHA-256 `836f0cd6c292eee7c8f21f5eb83cb5c3c7b8ad1bba8d2a6a101332ded1a76794`
**实验代码提交：** `39d0214bd736f728e050d765b7e8edb9df708a6e`（数据批次即在该提交上采集）

---

## 0. 一句话结论

在这台机器上，构造并序列化一笔 **1 spend + 2 outputs** 的 Sapling v5 交易：

| 指标 | 1 线程 @ LP0 | 8 线程 @ P 核 |
|---|---:|---:|
| **`t_total_construct`（中位）** | **4,292.7 ms** | **1,176.1 ms** |
| 其中 `t_build` | 4,292.7 ms | 1,176.0 ms |
| 其中 `t_serialize` | 0.022 ms | 0.024 ms |
| Groth16 证明部分（配对估计 `t_proving`） | 4,287.5 ms（**99.88%**） | —（本批次未做 8t mock 臂） |
| 非证明开销（mock 构造） | **4.83 ms（0.11%）** | — |
| 交易验证（不计入构造） | 10.4 ms | 13.8 ms |

**一句话：交易构造时间几乎全部是 Groth16 证明时间（99.88%）；sighash、Spend 授权签名、binding 签名、bundle 装配与序列化加在一起约 5 ms。** 8 线程把总构造时间压到 1/3.65，并行效率约 45.6%。

这是**本地交易构造时间**，不是广播、mempool 接纳、区块打包或上链确认时间，也不含钱包的输入选择、手续费迭代、note 解密与数据库 IO。

---

## 1. 测量对象与不可外推边界

| 项 | 本实验覆盖 | 明确不覆盖 |
|---|---|---|
| 交易形状 | 固定 1 Sapling spend + 2 Sapling outputs（1 收款 + 1 找零），无透明输入输出，无 Orchard/Ironwood | 其他输入/输出数量；透明或跨池交易 |
| 构造路径 | 真实 `zcash_primitives::transaction::builder::Builder::build(...)`，含 Sapling 证明、sighash、Spend 授权签名、binding 签名、bundle 装配 | 钱包的输入选择、手续费估算循环、note 发现/解密、数据库 |
| 见证状态 | **合成**：32 层随机 Merkle 节点、position 0、固定种子 note；anchor 由该路径推出 | 真实链上 note、真实 Merkle 树增量更新、witness 缓存 |
| 网络 | 无 | 广播、mempool、区块打包、确认 |
| 计时 | 单进程墙钟（`std::time::Instant`），CPU 亲和性绑定并读回核验 | 跨机/跨批次可移植性；功耗或热行为 |
| 版本 | `target_height = 1,700,000` ⇒ v5（NU5，branch `Nu5`） | 其他共识分支 |

> **合成状态声明：** spend note、Merkle 路径与 anchor 是自洽的测试状态，不对应任何真实钱包或链上 note。它们的计算成本与真实路径同阶（同样 32 层），但本实验**不**证明真实 note 的存在性，也**不**覆盖 witness 缓存/增量树维护成本。

---

## 2. 场景与冻结参数

| 项 | 值 |
|---|---|
| 网络 | `MAIN_NETWORK` |
| 目标高度 | `1_700_000` ⇒ v5 / `Nu5` |
| 花费 note | 100,000,000 zats |
| 收款输出 | 60,000,000 zats |
| 找零输出 | **39,990,000 zats** |
| 手续费 | **10,000 zats** |
| Sapling value balance | **+10,000**（有符号：输入 − 输出；手续费留在 Sapling 一侧） |
| 密钥 | 3 个 zip32 master key（spend / 收款 / 找零），固定种子 `0x11` / `0x12` / `0x13` |
| note rseed | `Rseed::AfterZip212([0x42; 32])` |
| 每进程 RNG | `StdRng::from_seed([0x42; 32])` |
| 参数文件 | `ZCASH_PARAMS_DIR` 下的 `sapling-spend.params` / `sapling-output.params` |

**手续费口径偏差（测量前发现，已留痕）：** 预注册初版按 "1 spend + 2 outputs = 3 个 logical actions" 估算 15,000 zats。实际 `zcash_primitives 0.31.0` 的 ZIP-317 规则是

```text
logical_actions = max(透明输入, 透明输出) + max(sapling spends, sapling outputs) + orchard + ironwood
                = 0 + max(1, 2) + 0 + 0 = 2
fee = 5,000 × max(grace=2, logical_actions=2) = 10,000
```

构造器因此在首次冒烟运行时以 `ChangeRequired(ZatBalance(5000))` 拒绝了 15,000 的预算。修正只涉及手续费与找零两个常量（以及 `value_balance` 的符号），发生在任何正式测量之前；预注册 §2/§5 原文保留，偏差与推导记录在预注册 §10 和本文 §9。交易形状、计时口径、臂设计与全部阈值均未改变。

**为什么是 1 spend + 2 outputs：** 这是 Sapling bundle 的最小"有找零"形状（`MIN_SHIELDED_OUTPUTS = 2`，`BundleType::DEFAULT` 不会额外填充），同时覆盖 Spend 与 Output 两条证明路径，使总时间可以拆成"1 大 + 2 小"。

---

## 3. 计时口径（冻结）

所有时间来自同一二进制写出的原始 CSV，单位 ms。

| 记号 | 边界 | 含 / 不含 |
|---|---|---|
| `t_setup_params` | 进程启动 → 两个参数文件读完并验证 | **不计入**；仅上下文（约 27.2–29.0 s） |
| `t_setup_vk` | → `prepared_verifying_key()` 完成 | **不计入**（约 2 ms） |
| `t_witness` | → note / 地址 / Merkle 路径 / anchor 就绪 | 进程级一次性准备（约 15 ms），**不计入** `t_build` |
| **`t_build`** | `Builder::build(...)` 进入 → 返回 | **含** Sapling 三份证明（见证装配、Groth16、证明编码）、sighash、Spend 授权签名、binding 签名、bundle 装配；**不含**序列化 |
| `t_serialize` | `tx.write(&mut Vec)` | 得到字节串 |
| **`t_total_construct`** | **`t_build + t_serialize`** | 本文主指标 |
| `t_mock_build` | 同一构造器、同一场景，mock prover | 构造器里**除 Groth16 之外**的全部开销 |
| **`t_proving`** | **`t_build − t_mock_build`（逐 run 配对）** | Groth16 证明部分的估计量 |
| `prove_spend` / `prove_output_{a,b}` | `Builder::with_progress_notifier` 打点 | 每份证明的 `prepare_circuit + create_proof + encode_proof` |
| `sum_proofs` | 三者之和 | 与 `t_proving` 互为独立估计 |
| `t_verify` | 构造完成后 `BatchValidator` 校验整个 bundle | **不属于构造时间**，只用于正确性 |

**不做的事：** 不把参数加载、`t_witness`、`t_verify` 加进构造时间；不把 `t_mock_build` 拆成"签名 X ms / 装配 Y ms"（它包含见证装配、编码、sighash、两类签名与装配，无法从这一路测量中分离）。

---

## 4. 测量设计

三个臂，各自独立进程，每进程构造 6 次，**丢弃 run 1**（首次页错误/分支预测冷启动），取 run 2–6 的中位。

| 臂 | 内容 | 线程 / 亲和性 | run 数 |
|---|---|---|---|
| **A1（主）** | 真实构造器 + 真实 proving 参数 | `RAYON_NUM_THREADS=1`，affinity `0x1`（LP0，P 核） | 6 |
| A2（辅） | 同 A1，多线程 | `RAYON_NUM_THREADS=8`，affinity `0xFFFF`（P 核） | 6 |
| A3（分解对照） | 同一构造器 + mock prover | `RAYON_NUM_THREADS=1`，affinity `0x1` | 6 |

- 亲和性由启动器在进程启动后设置，并**读回 `Process.ProcessorAffinity` 核验**；不一致或未生效则整批作废。三个臂的读回值分别等于 `0x1` / `0xFFFF` / `0x1`。
- 每 run 都重新构造交易（包括重新推进 RNG 生成 randomness），run 之间是独立构造，不是重复签名同一份交易。
- 每个臂一个进程、一个 `batch_id`：`1792650753956`（A1）/ `1792650808950`（A2）/ `1792650843767`（A3）。
- 参数加载约 27 s，明显长于单次构造，故置于计时窗口之外，只作上下文记录。

---

## 5. 原始结果

原始数据：`experiments/raw/csv/sapling_tx_construct_runs_{real,mock}.csv`；逐臂启动摘要：`experiments/raw/csv/sapling_tx_construct_campaign_tx_construct_20261022_summary.csv`；stdout/stderr：`experiments/raw/logs/tx_construct_tx_construct_20261022_*.log`（三个 stderr 均为空）。

### 5.1 主结果（暖态 run 2–6 中位）

| 阶段 | A1 真实 1t @ `0x1` | A2 真实 8t @ `0xFFFF` | A3 mock 1t @ `0x1` |
|---|---:|---:|---:|
| `t_witness`（进程级，不计入） | 14.908 ms | 15.925 ms | 14.246 ms |
| **`t_build`** | **4,292.699 ms** | **1,176.049 ms** | **4.832 ms** |
| `t_serialize` | 0.022 ms | 0.024 ms | 0.020 ms |
| **`t_total_construct`** | **4,292.720 ms** | **1,176.072 ms** | **4.888 ms**（mock 口径，仅对照） |
| `prove_spend` | 3,321.495 ms | 928.000 ms | 4.317 ms（mock） |
| `prove_output_a` | 480.232 ms | 132.704 ms | 0.026 ms（mock） |
| `prove_output_b` | 486.221 ms | 127.879 ms | 0.024 ms（mock） |
| `sum_proofs` | 4,292.703 ms | 1,175.588 ms | 4.367 ms（mock） |
| `t_verify`（不计入构造） | 10.384 ms | 13.826 ms | 未做（mock 证明不可做密码学校验） |

> `t_witness`、`t_setup_*` 是**每进程一次**的测量；CSV 为便于逐 run 对齐而复制到每行，故汇总表里它们的 sd 为 0、n 看似为 5。本文与结论都按"进程级单次"读数使用。

### 5.2 时间组成（A1，暖态中位）

| 组成 | 中位 (ms) | 占 `t_total_construct` | 定义 |
|---|---:|---:|---|
| `t_total_construct` | 4,292.720 | 100.00% | `t_build + t_serialize` |
| └ `t_build` | 4,292.699 | 100.00% | 构造器墙钟 |
| 　├ `t_proving`（配对估计） | 4,287.528 | **99.88%** | `t_build − t_mock_build` |
| 　└ `t_mock_build`（非证明开销） | 4.832 | **0.113%** | 见证装配 + 编码 + sighash + 两类签名 + bundle 装配 |
| └ `t_serialize` | 0.022 | 0.001% | `tx.write` |
| 每证明分解 | | | |
| ├ `prove_spend` | 3,321.495 | 77.38% | 1 份 Spend 证明 |
| ├ `prove_output_a` | 480.232 | 11.19% | 收款 Output 证明 |
| └ `prove_output_b` | 486.221 | 11.33% | 找零 Output 证明 |
| `sum_proofs` | 4,292.703 | 100.00% | 三份证明之和（独立估计） |

`t_build − sum_proofs = −0.004 ms`：两个量各自取中位后相减，残差在计时分辨率以下，说明 `t_build` 与三份证明之和在逐 run 上闭合（不是"负时间"）。sighash、授权签名、binding 签名与装配的总量体现在 `t_mock_build = 4.83 ms` 里，量级约为总构造时间的 0.1%。

### 5.3 双估计一致性

| 估计 | 值 (ms) | 与 `t_build` 的差 |
|---|---:|---:|
| `t_proving`（配对 `t_build − t_mock_build`） | 4,287.528 | 5.171（0.120%） |
| `sum_proofs`（进度打点求和） | 4,292.703 | 0.004（0.0001%） |

两者相差 5.17 ms，相对 `t_build` 为 **0.121%**，远低于冻结的 5% 门限。这说明"证明占 99.88%"不是单一估计量的假象。

### 5.4 稳定性

| 臂 | `t_build` CV | 范围 |
|---|---:|---|
| A1（1t） | **0.67%** | 4,238.5–4,316.2 ms |
| A2（8t） | 2.97% | 1,165.5–1,251.6 ms |
| A3（mock） | 4.14% | 4.609–5.171 ms |

A1 的逐 run 中位非常稳定；A2 的方差略大（2.97%），仍低于 5% 的臂内稳定门限（该门限只对 A1 冻结）。

### 5.5 多线程

| 量 | 1t | 8t | 加速比 |
|---|---:|---:|---:|
| `t_total_construct` | 4,292.720 ms | 1,176.072 ms | **3.65×** |
| `prove_spend` | 3,321.495 ms | 928.000 ms | 3.58× |
| `prove_output_a` | 480.232 ms | 132.704 ms | 3.62× |
| `prove_output_b` | 486.221 ms | 127.879 ms | 3.80× |

8 线程并行效率约 **45.6%**（3.65 / 8）。这与既有单证明实验的结论方向一致：Spend 的加速在 8 线程附近饱和，继续加线程收益很小；本实验不再重复扫描线程数。

### 5.6 交易结构常量

| 字段 | 值 |
|---|---|
| 交易版本 / branch | `V5` / `Nu5`（`tx_header = 2147483653`） |
| 序列化字节数 | **2,377 B**（全部 12 条真实 run 完全一致） |
| spend / output 数 | 1 / 2 |
| 手续费 | 10,000 zats |
| Sapling value balance | +10,000 zats |
| 密码学校验 | 12/12 `BatchValidator` 通过（A1 6/6、A2 6/6） |
| 反序列化 | 每 run 由二进制断言 txid 一致（exit=0） |

A1 与 A2 的逐 run txid 完全相同（`f1112a35…`、`534aefd5…`、…）：两个进程从同一 RNG 种子出发、构造同一场景，这是"两臂确实在测同一件事"的结构性证据，而不是 txid 唯一性检查。

---

## 6. 验收（冻结表 7/7 PASS）

| # | 判据 | 阈值 | 实测 | 结果 |
|---|---|---|---|---|
| 主 | 完整构造 + 结构断言 + 密码学校验 | 18/18 | 18/18（真实 12/12 校验通过；mock 6/6 结构通过） | **PASS** |
| 辅 1 | 结构常量性 | `tx_bytes` 全同、V5、1 spend、2 outputs、fee=10,000、balance=+10,000 | 2,377 B 全同；V5；1/2；10,000；+10,000 | **PASS** |
| 辅 2 | 证明占比 | `median(t_proving)/median(t_build) ≥ 0.90` | 0.9988 | **PASS** |
| 辅 3 | 双估计一致性 | 差 ≤ `t_build` 的 5% | 0.121% | **PASS** |
| 辅 4 | 非证明开销 | `median(t_mock_build) ≤ 100 ms` | 4.832 ms | **PASS** |
| 辅 5 | 臂内稳定性 | A1 `CV(t_build) ≤ 5%` | 0.668% | **PASS** |
| 辅 6 | 序列化一致性 | `total = build + serialize`；反序列化 txid 相同 | 最大残差 0.001 ms；二进制内断言通过 | **PASS** |

派生验收表：`results/tables/sapling_tx_construct_acceptance_20261022.csv`。重跑分析脚本输出 `TX_CONSTRUCT_EXPERIMENT=PASS`，退出码 0。

**PASS 的含义：** 只表示"这组测量与分解可用"，**不**表示某个开关应当切换、也不产生"优化收益"结论。本实验没有对照的优化前后臂，因此不涉及任何默认值变更。

---

## 7. 与既有单证明实验的对照（只作量级核对）

| 量 | 既有 pinned 基线（1t @ LP0，暖态） | 本实验 A1（1t @ LP0，暖态） | 差异 |
|---|---:|---:|---:|
| Spend 证明 | 3,685.6 ms | 3,321.5 ms | −9.9% |
| Output 证明（单份） | 558.5 ms | 480.2 / 486.2 ms | −14.0% / −12.9% |
| 交易构造总时间 | 无（未走构造器） | 4,292.7 ms | — |

本实验的每份证明比 2026-10-17 的 pinned 基线更快，与目标 b/g 已经改默认值（`SAPLING_MSM_SIGNED_DIGITS=1`、`SAPLING_MSM_LAZY_RECODING=1`、`SAPLING_FFT_SERIAL_SINGLE_THREAD=1`）以及构造器路径的差异一致；两个实验不是同一批次、也未做配对，因此**只作量级核对，不作为收益估计**。

另一个可核对的关系是：1t 的 `t_total_construct`（4,292.7 ms）≈ 单独调用三份证明的预期总和（3,321.5 + 480.2 + 486.2 = 4,287.9 ms）+ 约 5 ms 的非证明开销。这正好是"不能简单把单项证明耗时相加当作交易构造时间"的反面证据：在本场景下相加恰好接近，是因为构造器的额外开销只有约 5 ms；换形状（更多输入、透明输入、Orchard）后该等式不成立。

---

## 8. 复现

### 8.1 构建

```powershell
cd D:\Research\zcash-sapling-engineering\experiments\transaction-smoke
cargo build --release --locked
```

依赖固定：`zcash_primitives 0.31` / `zcash_protocol 0.11` / `sapling-crypto` git rev `88a7946b…`，`bellman`/`groth16` 通过 `[patch.crates-io]` 指向本仓库 `vendor/` 的插桩版（`Cargo.lock` 中这两个包无 `source` 行）。`--locked` 必须保留。

### 8.2 运行三个臂

```powershell
cd D:\Research\zcash-sapling-engineering
$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_tx_construct_campaign.ps1 -Label tx_construct_20261022
```

启动器会：设置 `RAYON_NUM_THREADS` 与 `TX_SMOKE_ARM`、启动进程中设亲和性并**读回核验**、检查每臂 6 行、校验结构常量与 `verified=true`、把 stdout/stderr 写入 `experiments/raw/logs/`。**它按臂追加到既有 CSV，绝不覆盖。**

手工单臂（不推荐，仅用于调试；写入临时 CSV）：

```powershell
$env:TX_SMOKE_ARM='real'; $env:RAYON_NUM_THREADS='1'
$env:TX_SMOKE_TAG='debug_real_t1_0x1'; $env:TX_SMOKE_AFFINITY='0x1'
$env:TX_CONSTRUCT_CSV="$env:TEMP\tx_debug.csv"
.\experiments\transaction-smoke\target\release\tx_construct_bench.exe
```

### 8.3 分析与出图

```powershell
python scripts\analyze_tx_construct_experiment.py
```

脚本按冻结的 `tag` 读取本批次，丢弃 run 1，重算 §5–§6 的全部数字并重写 `results/tables/sapling_tx_construct_*_20261022.csv` 与三张图；任何判据 FAIL 时退出码非 0。脚本内的 `TAG` 固定为本批次，重跑新批次应改 `TAG` 与输出文件名，**不要覆盖本批次**。

---

## 9. 偏差与解释边界

1. **手续费 15,000 → 10,000（测量前）：** 见 §2 与预注册 §10。`value_balance` 同时由 −15,000 更正为 **+10,000**：`ZatBalance` 是有符号量，定义为"输入 − 输出"，手续费留在 Sapling 一侧故为正。两处更正都发生在任何正式测量之前；阈值、臂设计与计时口径未改。
2. **`t_proving` 是估计量，不是直接测量：** mock prover 的 `prepare_circuit` 仍构造真实电路对象，其成本可能与真实 prover 略有差异；这一点用 `sum_proofs` 独立校验（差 0.121%）。
3. **`t_mock_build` 不能拆成"签名 X ms / 装配 Y ms"：** 它把见证装配、编码、sighash、Spend 授权签名、binding 签名与 bundle 装配合在一起。本文因此只报告"非证明开销 4.83 ms"，不给出未经直接测量的子项拆分。
4. **不含钱包与网络：** 不含输入选择、手续费估算迭代、note 解密、地址发现、数据库 IO、广播、mempool、打包与确认。
5. **合成见证：** Merkle 路径为随机节点 + position 0；计算成本与真实 32 层路径同阶，但不代表真实 note 的存在性，也不含 witness 缓存成本。
6. **单机单批次：** 时间只对该主机、该批次、该亲和性设置有效；跨机比较须重跑。
7. **A2 没有对应 mock 臂：** 本批次只做了 1t 的 mock 分解，因此 8t 的 `t_proving` 不能按配对差值给出；8t 的证明占比用 `sum_proofs / t_build` 参考（1,175.6 / 1,176.0 = 99.96%），不作为冻结判据。

---

## 10. 溯源

| 项 | 值 |
|---|---|
| 批次标签 | `tx_construct_20261022` |
| batch_id | A1 `1792650753956` / A2 `1792650808950` / A3 `1792650843767` |
| 实验代码提交 | `39d0214bd736f728e050d765b7e8edb9df708a6e`（干净工作树） |
| 二进制 SHA-256 | `836f0cd6c292eee7c8f21f5eb83cb5c3c7b8ad1bba8d2a6a101332ded1a76794` |
| spend 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| output 参数 SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 工具链 | `rustc 1.98.1 (48a229cea 2026-09-01)`，host `x86_64-pc-windows-gnu` |
| 原始 CSV | `experiments/raw/csv/sapling_tx_construct_runs_real.csv`、`..._runs_mock.csv` |
| 启动摘要 | `experiments/raw/csv/sapling_tx_construct_campaign_tx_construct_20261022_summary.csv` |
| 日志 | `experiments/raw/logs/tx_construct_tx_construct_20261022_{real_t1_0x1,real_t8_0xFFFF,mock_t1_0x1}{,.stderr}.log` |
| 派生表 | `results/tables/sapling_tx_construct_{summary,composition,acceptance}_20261022.csv` |
| 图 | `results/figures/sapling_tx_construct_{composition,per_proof,threads}_20261022.png` |
| 分析脚本 | `scripts/analyze_tx_construct_experiment.py` |
| 启动器 | `scripts/run_tx_construct_campaign.ps1` |
| 实验 crate | `experiments/transaction-smoke/`（独立于 `experiments/prover-smoke/`，不改既有二进制） |

**参数指纹与既有批次一致**（spend `8e48ffd2…`、output `2f0ebbcb…`），说明本实验与既有 Spend/Output 实验使用的是同一组参数文件。`Cargo.lock` 同时记录了 transaction 层与电路层的完整解析结果；`bellman`/`groth16` 无 `source` 行，确认走本仓库 `vendor/` 的 path 依赖，而非 crates.io 的另一份副本。

---

## 11. 结论

1. **一笔 1 spend + 2 outputs 的 Sapling 交易，单线程本地构造 + 序列化中位 4.29 s；8 线程（P 核）1.18 s，加速 3.65×。**
2. **构造时间几乎全部是 Groth16 证明：配对估计 99.88%；sighash、Spend 授权签名、binding 签名、bundle 装配与序列化合计约 5 ms（0.11%）。**
3. **在证明内部，Spend 一份占 77.4%，两份 Output 各占约 11.2% / 11.3%。** 交易形状每增加一个 Spend，边际成本约 3.3 s（1t）；增加一个 Output 约 0.48 s（1t）。
4. **序列化本身可忽略（0.02 ms），验证约 10 ms 且不属于构造时间。**
5. 这些数字是**本地构造时间**，不是上链确认时间；见证为合成状态，不含钱包与网络路径。跨机、跨形状外推须重测。
