# 预注册：Sapling 完整交易构造（zcash_primitives Builder）本地耗时与证明占比 baseline — 2026-10-22

> 本文件按 `sapling_optimization_validation_protocol_20261017.md` §5 的模板，**在写任何实验代码之前**填写并冻结。
> 一旦冻结，验收判据**不得修改**；实现与测量中若发现口径写错，只能在结果文档里标注，不能在本文档里改。
>
> 与既有优化战役（目标 a–g）的关系：a–g 测的是**单份证明**在固定电路与固定参数下的耗时/内存。
> 本实验**不优化任何东西**，只把测量边界上移一层：在真实交易构造器
> `zcash_primitives::transaction::builder::Builder` 里构造一笔固定形状的 Sapling 交易，
> 测「一笔交易构造完要多久、Groth16 证明占其中多少」。因此本文没有"阈值达标 ⇒ 采用某个开关"的结构，
> 只有"测量成立 ⇒ 结论可用"的结构（验收表 §5）。

---

## 0. 一句话

用真实交易构造器（而非直接调 prover）构造一笔 **1 spend + 2 outputs** 的 Sapling 交易，
在 1 线程固定核（LP0）上测：完整构造墙钟、Groth16 证明部分、非证明部分（见证准备 + sighash + 签名 + 装配）、序列化与交易大小、以及构造后交易的密码学校验。
并明确声明：**这是本地交易构造时间，不是广播到网络确认的全流程时间。**

---

## 1. 目标、范围与非目标

### 1.1 要回答的问题

| # | 问题 | 对应指标 |
|---|---|---|
| Q1 | 一笔固定形状的 Sapling 交易，从"见证就绪"到"可序列化交易对象"要多久？ | `t_build`、`t_total_construct = t_build + t_serialize` |
| Q2 | 其中 Groth16 证明占多少？ | `t_proving = t_build − t_mock_build`，并与 `sum(per-proof)` 交叉验证 |
| Q3 | 非证明部分（见证准备、sighash、签名、装配）占多少、是否可忽略？ | `t_mock_build`，以及 `t_build − t_proving − sum(per-proof)` 残差 |
| Q4 | 交易对象是否结构正确、密码学有效？ | 结构常量 + 证明/签名/binding sig 全验 |
| Q5 | 与既有单证明基准是否自洽？ | A1 的 `prove_spend_ms` / `prove_output*_ms` 与既有 `spend_prover_smoke` / `sapling-output-smoke` 批次的中位对照（**描述性**，跨批次，不作判据） |

### 1.2 非目标（明确不做，避免误读）

1. **不测网络**：不广播、不连节点、不等确认。文中任何时间都不是"到账时间"。
2. **不测钱包**：不实现输入选择、不调用 `create_proposed_transaction`、不接钱包数据库/状态机。
3. **不用真实链上 note**：Merkle 路径是**合成**的（固定种子生成 32 层节点、position 0）。
   这只能证明"构造流程与证明成本"，**不能**声称代表某笔真实付款。
4. **不做跨机/跨 OS 外推**：单机（i7-14700 / Windows 11），单批次观测。
5. **不改任何算法**：本实验对 `vendor/bellman`、`vendor/groth16`、`sapling-crypto` **只读**。

### 1.3 与 `docs/zcash_sapling_flow.md` 的对应

该文档 §2 描述的链路是：`Builder::build` → Sapling builder → `create_proofs`（Spend/Output）→ 计算 sighash → 应用授权签名 → 完成交易。
本实验就是**把这条链路实际跑起来**并分段计时，而不是像既有实验那样直接调 `SpendParameters::create_proof`。

---

## 2. 冻结场景（固定交易）

| 项 | 冻结值 | 说明 |
|---|---|---|
| 代码层 | `zcash_primitives 0.31.0`（crates.io） | 依赖树解析已验证；`sapling-crypto ^0.9` 被 `[patch.crates-io]` 固定到本工程同一 git rev `88a7946b…` |
| 电路层 | `sapling-crypto 0.9.0` @ `88a7946b4a3066787776e11f0a502654167e022d` | 与既有 Spend/Output 实验**同一份代码** |
| 证明后端 | `vendor/bellman` 0.15.0 + `vendor/groth16` 0.2.0（path patch） | 通过 `[patch.crates-io]` 生效；构造器的证明**确实走本工程的插桩版 bellman** |
| 网络参数 | `MAIN_NETWORK`，`target_height = 1_700_000` | NU5 激活（1,687,104）之后 ⇒ 交易版本 **v5**，Sapling bundle 为 v4 格式，不涉及 Orchard/Ironwood 路径 |
| 输入 | 1 个 Sapling spend，note 面额 **100,000,000 zats** | ZIP-212 `Rseed::AfterZip212` |
| 输出 | **2 个** Sapling output：收款 **60,000,000**、找零 **39,985,000** | 两者 memo 均为空、`ovk = None` |
| 手续费 | **15,000 zats** | ZIP-317：`marginal_fee(5,000) × max(grace=2, logical_actions=3) = 15,000` |
| 平账 | 100,000,000 − 60,000,000 − 39,985,000 = 15,000 = fee | 构造器必须通过其内部平账检查 |
| Merkle 路径 | 32 层、position 0、节点由固定种子生成 | anchor 由该路径与 note 的 cmu 推出；显式标注为**合成状态** |
| 密钥 | 3 个 zip32 master key（spend / 收款 / 找零），种子固定 | spend note 的收款地址 = spend key 自己的默认地址 |
| 随机源 | `StdRng::from_seed([0x42; 32])`（每进程重置） | 结构可复现；Groth16 证明本身随机化，故证明字节不固定 |
| 参数文件 | `ZCASH_PARAMS_DIR` 下的 `sapling-spend.params` / `sapling-output.params` | SHA-256 与既有批次一致时在结果文档中记录 |
| 交易版本 | 由构造器按 target_height 自动选（预期 v5） | 结果 CSV 记录实际版本与 consensus branch id |

**为什么 1 spend + 2 outputs**：这是 Sapling bundle 的最小"有找零"形状（`MIN_SHIELDED_OUTPUTS = 2`，
`BundleType::DEFAULT` 不额外填充），既能覆盖 spend 与 output 两条证明路径，又让时间组成
（1 大 + 2 小）与既有单证明基准可直接相加核对。

---

## 3. 计时口径（冻结）

所有时间均为**单进程墙钟**（`std::time::Instant`），单位 ms，由同一二进制输出到原始 CSV。

| 记号 | 起点 → 终点 | 含什么 / 不含什么 |
|---|---|---|
| `t_setup_params_ms` | 进程内开始 → 两个参数文件读完并验证 | **不计入**构造时间（只作上下文） |
| `t_setup_vk_ms` | → 两个 `prepared_verifying_key()` 完成 | **不计入**构造时间 |
| `t_witness_ms` | → note / 地址 / Merkle 路径 / anchor / 见证材料就绪 | 构造器的**输入准备**，单列，不计入 `t_build` |
| **`t_build_ms`** | `Builder::build(...)` 进入 → 返回 `BuildResult` | **含** Sapling 每份证明（含见证装配与证明编码）、sighash 计算、spend auth 签名、binding 签名、bundle 装配；**不含**任何序列化 |
| `t_serialize_ms` | `tx.write(&mut Vec)` | 得到字节串 |
| `t_txid_ms` | `tx.txid()` | 单列（txid 不是构造所必需，但钱包需要） |
| **`t_total_construct_ms`** | **= `t_build_ms + t_serialize_ms`** | 本实验的**主指标载体** |
| `t_mock_build_ms` | 同一 `Builder`、同一场景，但传入 **mock prover**（`prepare_circuit` 真实、`create_proof` 返回占位字节） | = 构造器里**除 Groth16 之外**的全部开销 |
| **`t_proving_ms`** | **= `t_build_ms − t_mock_build_ms`**（配对差值） | **Groth16 证明部分的估计量** |
| `prove_spend_ms` / `prove_output{1,2}_ms` | 由 `Builder::with_progress_notifier` 的进度消息打点 | 每份证明的 `prepare_circuit + create_proof + encode_proof` 区间 |
| `sum_proofs_ms` | 上述三者之和 | 与 `t_proving_ms` 互为独立估计 |
| `t_verify_ms` | 构造完成后对整个 Sapling bundle 的密码学校验 | **不属于构造时间**，只用于正确性 |

**口径声明（预声明，避免混算）**：
- 主指标是 `t_total_construct_ms`，但**不把 `t_witness_ms`、参数加载、校验算进去**，也不把 `t_verify_ms` 算进去。
- `t_mock_build_ms` 是**估计量**，不是"签名耗时"的精确值：它包含见证装配、编码、sighash、两类签名与装配。因此报告中只写"非证明开销"，**不拆分成"签名 X ms / 装配 Y ms"**，除非另有直接测量。

---

## 4. 测量设计（3 个臂，各自独立进程）

| 臂 | 内容 | 线程/亲核 | run 数 |
|---|---|---|---|
| **A1（主）** | 真实构造器 + 真实 proving 参数 | 1t，`RAYON_NUM_THREADS=1`，affinity `0x1`（LP0） | 6（暖态 run 2–6） |
| A2（辅） | 同 A1，多线程 | 8t，`RAYON_NUM_THREADS=8`，affinity `0xFFFF`（P 核） | 6 |
| **A3（分解对照）** | 同一构造器 + mock prover | 1t，`0x1` | 6 |

> 修订说明：原设计的第四个臂（"不经构造器、直接调 `create_proof` 的参照臂"）已在**任何测量开始之前**取消，
> 理由与留痕见 §9。

- 每臂一个进程（`TX_SMOKE_ARM` 选择），进程内 `REPEATS = 6`，**丢弃 run 1**（首次包含页错误/分支预测冷启动），取 run 2–6 的中位。
- 每臂每 run 都重新构造交易（包括重新生成见证 randomness），因此 run 之间是独立构造，不是重复签名同一份交易。
- 亲和性由启动器设置（`Start-Process` 后设 `ProcessorAffinity`），与既有台账流程一致；亲和性未生效时该批次**作废**并在日志中记录。
- 主机负载不设人为压制，但记录同批次 CPU 负载；漂移检查用 A1 的首末批中位比较（阈值 ±5%，超出则在报告中标注为漂移而非结论）。

---

## 5. 验收表（冻结）

**这是测量实验**：主指标是"能否稳定地构造并验证出一笔符合预期结构的交易"，而不是"某个数变好"。

| # | 判据 | 阈值 | 判据类型 |
|---|---|---|---|
| **主** | 完整构造 + 结构断言 + 密码学校验 | **18/18**：A1 6/6 与 A2 6/6（构造成功 + `BatchValidator` 全验通过）；A3 6/6（构造成功 + 结构断言；mock 证明按定义不可做密码学校验） | 必须 |
| 辅 1 | 结构常量性：所有 A1/A2 run 的 `tx_bytes` **完全相同**，且 `tx_version = 5`、`spend_count = 1`、`output_count = 2`、`fee_zats = 15,000`、`value_balance = −15,000` | 全过 | 必须 |
| 辅 2 | 证明占比：`median(t_proving) / median(t_build) ≥ 0.90` | ≥ 0.90 | 必须 |
| 辅 3 | 双估计一致性：`\|median(sum_proofs) − median(t_proving)\| / median(t_build) ≤ 5%` | ≤ 5% | 必须 |
| 辅 4 | 非证明开销：`median(t_mock_build) ≤ 100 ms` | ≤ 100 ms | 必须 |
| 辅 5 | 臂内稳定性：A1 的 `CV(t_build) ≤ 5%`（`CV = sd/mean`，暖态） | ≤ 5% | 必须 |
| 辅 6 | 序列化一致性：`t_total_construct = t_build + t_serialize`，且反序列化得到的交易 `txid` 相同 | 全过 | 必须 |

**PASS 判据：主 ∧ 辅 1…辅 6。**

**回退条款（预声明）：**
- 主未达标（有任一 run 构造或校验失败）⇒ 记「**该场景下构造/校验不成立**」，不给出任何时间结论，先修工程问题再重测（新批次，不覆盖本批次）。
- 辅 2 或辅 3 未达标 ⇒ 记「**Groth16 占比估计不成立**」，只报告 `t_total_construct` 与 `t_mock_build`，**不**声称"证明占 X%"。
- 辅 4 未达标 ⇒ 非证明开销异常，先查是否把参数加载/校验混入 `t_build`。
- 辅 5 未达标 ⇒ 该臂噪声过大，只报告中位并显式标注，不用于跨臂比较。
- 辅 6 未达标 ⇒ 记录序列化/反序列化不一致，作为工程缺陷单列。

**预声明：本实验不产生"优化收益"结论**，因此没有 PASS ⇒ 采用/切换默认值这种动作；PASS 只表示"这组测量与分解可用"。

---

## 6. 不可外推边界

| 项 | 说明 |
|---|---|
| 交易形状 | 只覆盖 1 spend + 2 outputs；spend 数增加时 Groth16 占比线性上升，outputs 增加时占比缓慢下降。不外推到 "1-in-2-out 是典型钱包形状"。 |
| 合成见证 | Merkle 路径是随机节点 + position 0，pedersen 哈希成本与真实路径同阶（深度相同），但**不**代表真实 note 的存在性；且未覆盖 witness 缓存/增量树更新成本。 |
| 不含钱包 | 未包含输入选择、手续费估算迭代、note 解密、地址发现、数据库 IO。 |
| 不含网络 | 未包含广播、mempool 接纳、区块打包、确认。 |
| 单机单批次 | 时间只对该机器/该批次/该亲和性设置有效；跨机比较须重跑。 |
| `t_mock_build` 的语义 | mock prover 的 `prepare_circuit` 仍构造真实电路对象，其成本可能与真实 prover 的 `prepare_circuit` 略有差异；因此 `t_proving = t_build − t_mock_build` 带该量级的系统偏差，用辅 3 的 `sum_proofs` 作独立校验。 |

---

## 7. 产物与提交（预声明）

| 阶段 | 内容 |
|---|---|
| 本预注册 | 独立提交，**先于**实验代码 |
| 实现 | `experiments/transaction-smoke/`（新 crate，独立于 `prover-smoke`，不改既有二进制） |
| 原始数据 | `experiments/raw/csv/sapling_tx_construct_runs_*.csv`、`experiments/raw/logs/tx_construct_*.log` |
| 派生表 | `results/tables/sapling_tx_construct_*.csv` |
| 图表 | `results/figures/sapling_tx_construct_*.png`（时间组成、每证明分布、1t vs 8t） |
| 文档 | 结果文档 + 报告新章 + `docs/zcash_sapling_flow.md` §5 更新 + README/INDEX |
| 复现 | 一条 `cargo build --release` + 4 条启动命令 + 一条分析命令 |

---

## 8. 与既有口径的一处沿用说明

既有优化战役的"1t @ `0x1`、暖态取中位、丢弃每批 run 1"是对**证明器**的约定。本实验沿用同一约定，
但**主指标是交易构造墙钟**，因此额外要求：同一臂内 `tx_bytes` 完全一致（结构不变），
以保证 run 之间比较的是同一件事。

---

## 9. 修订记录（测量前）

| 日期 | 修订 | 理由 | 是否已有测量数据 |
|---|---|---|---|
| 2026-10-22 | 取消原 A4 参照臂（"直接调 `create_proof`"），主判据由 30/30 改为 18/18，删除原辅 6（与参照臂自洽） | ① A4 与 A1 内部 `prove_spend_ms` / `prove_output*_ms` 打点是**同一个调用**，增量信息为零；② 单份 output 证明的独立校验需要复刻构造器内部的 `epk`/`cmu` 计算（`EphemeralSecretKey` 的派生方法是 `pub(crate)`），会引入人工复刻误差；③ mock 臂（A3）的证明按定义不可通过密码学校验，原表中"30/30 含 A3 校验通过"自相矛盾 | **无**（本次修订早于任何实验代码与任何测量） |

修订只影响"如何判 PASS"的表述，**不改变**冻结场景（§2）、计时口径（§3）与主指标载体（`t_total_construct`）。
