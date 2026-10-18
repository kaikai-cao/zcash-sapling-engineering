# 侦察：当前默认配置的时间画像（时间线结项）— 2026-10-18

> 本文是**预注册前的侦察记录**，不是任何优化目标的判定。目的：在目标 g 翻转默认值后，
> 对新的 shipped default 做时间分解，确认剩余候选（c：B-G2 aux；d：赋值转换并行化）
> 是否存在机制干净的优化空间。结论：**时间线同样到达算术地板，不再设立时间目标**。
> 内存线的结项依据见 `sapling_default_stage_decomposition_20261018.md`。

---

## 0. 数据来源与口径

| 项 | 值 |
|---|---|
| 配置 | 翻转后默认，**不设任何开关环境变量**（= lazy=1 + fix=1） |
| 二进制 | spend_prover_smoke（翻转后重编译） |
| 剖析开关 | `SAPLING_PROFILE=1` + `SAPLING_MSM_STAGE_TIMING=1`（分支计数器关） |
| 线程/亲和 | RAYON_NUM_THREADS=1，亲和 0x1 |
| 原始数据 | `experiments/raw/logs/sapling_spend_msm_stage_recon_20261018.log`，`experiments/raw/csv/sapling_spend_prover_runs_msm_stage_recon_20261018.csv` |

**口径警告**：剖析本身有开销，绝对值不可直接与无剖析战役比较（本批 body 中位
3,625.2 ms vs 目标 g 无剖析臂集中位 ≈3,429 ms）。本文只用**阶段间比例**与
**同一批次内的相对量**。

---

## 1. 阶段墙时间（中位，每证明）

| 阶段 | 中位 ms | 占比 |
|---|---:|---:|
| circuit_synthesis | 120.5 | 3.3% |
| worker_vk_setup | ~0 | 0% |
| qap_fft_h_exponent_prep（6 次 FFT + 除式 + h 指数转换） | 385.8 | 10.6% |
| h_query_access_dispatch | ~0 | 0% |
| assignment_query_prep_dispatch（L/A/B1/B2 分发，1 线程下含队列排空） | 2,459.2 | 67.8% |
| proof_scalar_terms | 1.6 | 0% |
| wait_and_assembly（等待 worker 队列剩余部分） | 640.8 | 17.7% |
| **create_proof body 合计** | **3,625.2** | 100% |

1 线程执行模型实测：`multiexp` 分发不阻塞（h query 分发仅 0.05 ms），MSM 工作全部在
`assignment_query_prep_dispatch` 与 `wait_and_assembly` 两阶段被排空（合计 3,100 ms，
与 MSM 阶段剖面总量 3,138 ms 相符）。即 **MSM 占 prove 的 ≈85%**（与历史 87–93% 一致）。

## 2. MSM 内部按 query 分解（每证明，同一批次）

| Query | 曲线 | calls | wall ms | fill | fill 占 | reduce | reduce 占 |
|---|---|---:|---:|---:|---:|---:|---:|
| H query（131,071 指数，稠密） | G1 | 1 | 1,514.3 | 1,415.2 | 93.5% | 98.3 | 6.5% |
| aux 查询（98,638） | G1 | 3 | 986.5 | 683.8 | 69.3% | 300.7 | 30.5% |
| B-G2 aux（98,638） | G2 | 1 | 634.9 | 348.8 | 54.9% | 280.5 | 44.2% |
| IC（8 指数） | G1/G2 | 3 | 2.5 | — | — | — | — |

- fill 合计 2,448.1 ms/证明，reduce 合计 681.7 ms/证明。
- H query 每非零数字 **≈494 ns**（1,415.2 ms / 2,864,709 个非零窗口数字），与源码注释
  记录的 ~470 ns/次混合加一致 ⇒ **算术受限**（bls12_381 混合加 = 11 个 Fp 乘），
  非内存受限（桶阵列 589,824 B，在 L2 内，成本与阵列大小无关——注释中的微基准结论成立）。
- G2 每数字成本 ≈ G1 的 2.6×（Fp2 乘 = 3 个 Fp 乘），与分支×阶段合并分析（F2）一致。

## 3. 候选机制逐一核查

### 3.1 候选 c（B-G2 aux，635 ms/证明）

- fill（348.8 ms）：与 H query 同一个混合加循环，算术受限，无低级机制可挖
  （循环体已是有符号 Pippenger + 密度跳过的标准实现）。
- reduce（280.5 ms，占该 query 44%）：桶累加是 O(chunks × buckets) 的倍加，
  桶为空也不能跳过（位权需要），操作数固定。
- 窗口重调（`SAPLING_MSM_WINDOW_C`）：用操作数模型
  `ops(c) = ceil(256/c) × (n·d + 2·2^(c-1))` 核算三大 query，**c=13 均已最优**：
  - H query（n=131,071，d=1）：c=12 为 +6.8%，c=14 为 +0.6%；
  - G2 aux（n=98,638，d≈0.41）：c=12 为 +0.7%，c=14 为 +11%。
  且该 knob 是全局的，按 query 分别调窗需要在 bellman 内加按曲线/密度选窗的逻辑——
  而核算显示没有任何 query 能从中净获益。
- 结论：**无机制**。B-G2 aux 的 635 ms 是该查询在当前算法下的地板。

### 3.2 候选 d（赋值转换并行化）

- `collect_conversion`（input/aux/h_exponents 三次 `Scalar→Exponent` 的 map+collect）
  位于 `qap_fft_h_exponent_prep` 阶段（385.8 ms），其中转换本身占比很小：
  131,071 + 98,638 + 8 个元素的指数化构造，按 fill 同级单价估算 ≈25 ms 量级，
  **占 prove <1%**，低于协议 3% 的 bar。该阶段主体是 6 次 FFT + 除式的算术（固定）。
- 结论：**低于 bar，不立项**。

### 3.3 其他核查过的地方

- `wait_and_assembly` 的 640.8 ms 经追溯是 worker 队列尾部（MSM 排空），
  不是装配算术（`proof_scalar_terms` 仅 1.6 ms；终局的群加与 to_affine 可忽略）。
  也就是说它已包含在 §2 的 MSM 成本里，没有独立的"装配优化"空间。
- 合成 120.5 ms（3.3%）是电路求值本身，随 zcash_proofs 版本走，无工程余量。
- 多线程扩展（1→16 线程 5.92×）是既有实测属性，不是优化目标；
  其串行部分（合成 + FFT + 装配 ≈15%）随上述结论同样无干净机制。

---

## 4. 结论：时间线到达算术地板

1. prove 时间 ≈85% 是 MSM；MSM 的 78% 是 bucket fill；fill 是每数字 ~470–495 ns 的
   混合加，操作数由 Pippenger 算法固定（`windows × (n + 2×buckets)`），
   窗口 c=13 对全部三大 query 已验证最优。
2. 两轮 recoding 收益（目标 b 有符号数字、目标 a/g lazy recoding）均已落库；
   窗口重调上限 ≤3.7%（源码注释的既有结论），本次按 query 核算同样无净获益。
3. 候选 c 无机制、候选 d 低于 bar。**不再设立时间优化目标。**
4. 与内存线结项（`sapling_default_stage_decomposition_20261018.md`）合并陈述：
   本管线的两个优化维度均已到达各自的结构性地板/算术地板，
   优化战役 a–g 完结；后续价值在测量与复现性的维护，以及新算法族（如不同的
   承诺方案）的评估，而非继续在本管线内做工程微优化。
