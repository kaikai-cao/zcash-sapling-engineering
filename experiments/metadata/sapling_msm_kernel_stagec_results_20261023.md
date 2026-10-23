# 阶段 C 结果：A/A 测量稳定性校准与 MSM 内核基准（2026-10-23）

> 预注册（冻结门禁与本结果的全部判据来源）：
> `experiments/metadata/sapling_msm_kernel_stagec_preregistration_20261023.md`。
> 本文只应用冻结判据，不在看到数据后定义新门禁。
>
> 运行元数据：
> - 二进制 `msm_kernel_bench`，SHA-256 `a9192ccd24a0f725b50979bc15ada1ee7419eb0b71a7c8a61fa72fe8b2ca6219`
> - git HEAD `8a474a5fd59d1fe11d3f443797ec272c493e2b40`（分支 `experiment/msm-kernel-20261023`，dirty=false）
> - rustc 1.98.1 (48a229cea 2026-09-01)；28 logical processors（8 P + 12 E）
> - 条件 A：affinity `0x5555`（8 P 核 LP0,2,4,6,8,10,12,14，读回一致）、`RAYON_NUM_THREADS=8`
> - 条件 B：affinity `0x1`（读回一致）、`RAYON_NUM_THREADS=1`
> - 区组：8（预注册默认）；每臂每区组 1 预热 + 3 正式测量；臂顺序为冻结种子的前缀平衡抽样
> - 原始数据：`experiments/raw/csv/msm_kernel_bench_20261023_{8t,1t}.csv`、
>   `..._correctness.csv`（52 项检查）；日志 `experiments/raw/logs/msm_kernel_bench_20261023_*`
> - 派生表：`results/tables/msm_kernel_bench_20261023_{summary,aa}.csv`

---

## 0. 一句话

**当前 bellman 生产路径的单线程点运算成本约为 blst 的 2.0×（H-query G1 全 MSM：1,343.7 ms vs
707.7 ms，R = 1.9005，95% CI [1.8894, 1.9151]；24 区组复现轮 R = 1.9063 [1.8999, 1.9110]），
且 1t 测量系统的不确定性（A/A 配对差 95% CI 半宽 0.25%–1.29%）明显小于该差距**——按冻结
判据 P1 = **GO**。单位成本分解探针进一步定位：差距唯一可归因的层是 **fill 混合加的公式
实现**（bellman Jacobian madd 477 ns/数字 vs blst xyzz 路径反推 ≈ 253 ns/数字），域运算层与
reduce 层均无差距；8t 条件的测量噪声（主负载 24 区组 0.97%，中小负载 ~3%）本身也是一项
结论：生产条件的细粒度比较不能依赖本设计的 8t 绝对计时。

---

## 1. 正确性（C 级门禁）

52 项检查全部通过（`correctness=PASS`），覆盖 5 个负载 × {bellman vs blst 序列化字节相等、
bellman vs blst 群意义往返、每臂校验和稳定}，外加 `ic`（n=8）对朴素 double-and-add 的相等：

| 检查 | 结果 |
|---|---|
| bellman vs blst（未压缩字节相等） | 5/5 负载 ok |
| bellman vs blst（往返群意义相等，诊断项） | 5/5 负载 ok |
| 朴素 double-and-add（n = 8） | ok |
| 臂内校验和稳定（3 次正式测量一致） | 15/15 ok |

结论：两侧实现在同一输入上给出**同一个群元素**，性能比较的是算法而不是工作负载差异。

## 2. M 门禁：测量系统不确定性（A/A）

配对差 = 同一 bellman 实现的两个标签（`_A` − `_B`）的区组中位之差；bootstrap 95% CI（10,000 次，
种子 20261023）。半宽相对区组中位绝对值。

| 条件 | 负载 | median_diff (ms) | CI95 (ms) | 半宽 % | 门禁（≤1.5%） |
|---|---|---:|---|---:|---|
| 1t | h_query | −6.97 | [−11.84, 2.67] | **0.72** | PASS |
| 1t | l_query | −1.07 | [−3.64, 0.96] | **0.76** | PASS |
| 1t | ab_aux | −0.34 | [−1.76, 1.91] | **0.66** | PASS |
| 1t | g2_aux | +1.70 | [−4.02, 11.57] | **1.29** | PASS |
| 1t | ic（参考，不判定） | +0.06 | [−0.22, 0.75] | 47.5 | — |
| 8t | h_query | −2.74 | [−42.97, 1.34] | **15.89** | FAIL |
| 8t | l_query | +14.86 | [−0.99, 18.09] | **20.43** | FAIL |
| 8t | ab_aux | −0.57 | [−13.99, 16.58] | **24.38** | FAIL |
| 8t | g2_aux | +3.16 | [−2.32, 21.46] | **10.63** | FAIL |
| 8t | ic（参考，不判定） | −0.02 | [−0.05, 0.03] | 11.6 | — |

**1t：PASS。** 区组中位数的配对差 95% CI 半宽 0.66%–1.29%，明显小于 5% 的端到端目标收益
（预注册 M1/M2 的基本要求）。所有 1t 条件下的差值方向不一致、量级远小于差异本身，未见系统漂移。

**8t：FAIL。** 半宽 10.6%–24.4%，与 2026-10-23 窗口侦察记录的 10–16% 绝对漂移量级一致。
按预注册规则，8t 条件的绝对计时不得用于细粒度比较（包括 8t A/A 自身和 8t 与 blst 的对比），
只作为生产量级参考（见 §3 表）。8t 噪声的来源是 rayon 工作池调度与系统状态，不是 bench 缺陷：
1t 在同一二进制、同一 fixture、同一分析脚本下达到 <1.3%。

> 执行说明（预注册未限定的地方）：§4.1 的 M 门禁按全部负载报告，其中 `ic`（n=8，绝对耗时
> ~1 ms）的相对 CI 由计时粒度支配（预注册 §2.1 将其定位为"参考"负载），本文不将其纳入
> M 门禁判定；判定负载为 n ≥ 98,638 的四个。

## 3. 测量结果：区组中位（ms）

| 条件 | 负载 | 曲线 | n | bellman_A | bellman_B | blst_1t |
|---|---|---|---:|---:|---:|---:|
| 1t | h_query | G1 | 131,071 | **1,343.72** | 1,351.74 | **707.66** |
| 1t | l_query | G1 | 98,638 | 337.31 | 338.62 | 170.20 |
| 1t | ab_aux | G1 | 98,638 | 339.39 | 339.88 | 174.03 |
| 1t | g2_aux | G2 | 98,638 | 768.15 | 763.69 | 351.59 |
| 1t | ic | G1 | 8 | 1.46 | 1.05 | 0.29 |
| 8t | h_query | G1 | 131,071 | 253.16 | 258.74 | 727.37 |
| 8t | l_query | G1 | 98,638 | 77.60 | 63.27 | 210.26 |
| 8t | ab_aux | G1 | 98,638 | 70.33 | 67.48 | 210.85 |
| 8t | g2_aux | G2 | 98,638 | 172.05 | 162.49 | 400.55 |
| 8t | ic | G1 | 8 | 0.46 | 0.47 | 0.27 |

- 8t bellman 列仅供生产量级参考（其 M 门禁未过）；8t 与 blst_1t **不可比**（线程框架不同，
  blst 侧为 `no-threads` 单线程；预注册 §4.3 只以 1t 同线程数对照判定）。
- fixture 成本（计时区外）：h_query bases 2.56 s / bellman Exponent 5.5 ms / blst 转换 52.6 ms；
  持久内存：bases 13.63 MB + exponent 5.24 MB（bellman）、blst 临时 scratch 786,432 B。

## 4. P 门禁：bellman vs blst（同线程数，1t）

主指标 P1 = median(bellman_1t_A) / median(blst_1t)（区组中位）：

| 负载 | 曲线 | n | bellman_1t (ms) | blst_1t (ms) | R | 判定 |
|---|---|---:|---:|---:|---:|---|
| **h_query** | G1 | 131,071 | 1,343.72 | 707.66 | **1.9005**（CI95 [1.8894, 1.9151]） | **GO**（≥1.15） |
| l_query | G1 | 98,638 | 337.31 | 170.20 | 1.98 | 记录 |
| ab_aux | G1 | 98,638 | 339.39 | 174.03 | 1.95 | 记录 |
| g2_aux | G2 | 98,638 | 768.15 | 351.59 | 2.19 | 记录 |
| ic | G1 | 8 | 1.46 | 0.29 | ~5.0（计时粒度噪声大） | 记录 |

**P1 = GO**：1t M 门禁全过，R = 1.90 且 CI 完全位于 1.15 以上——bellman 的点运算路径与成熟
实现存在明确、可复现、量级约 2× 的单线程差距。该结论不是单一负载的偶然：三个主要 G1 负载一致
落在 1.90–1.98，G2 为 2.19。

## 5. 差距归因（预注册 §4.4 + 单位成本分解探针）

操作数模型（同一口径）：bellman signed 窗口 c = 13 → chunks = 20、桶 2^12 = 4,096；
`ops ≈ 20 × (131,071 + 2 × 4,096) ≈ 2.79 M`。blst 窗口规则 `pippenger_window_size(131,071) = 13`，
单线程 breakdown 后 wnd = 14、ny = 19、桶 2^13 = 8,192；`ops ≈ 19 × (131,071 + 2 × 8,192) ≈ 2.80 M`。
**两侧操作数相当（1.00×）**，因此 1.90× 的差距来自单位操作成本：
bellman ≈ 482 ns/窗口数字（全 MSM ÷ 模型 ops），blst ≈ 253 ns/op。

为定位这一单位成本差来自哪一层，补做了单位成本分解探针（`msm_arith_probe`，单核 0x1，
exploratory 无门禁；脚本 `scripts/run_msm_arith_probe.ps1`，日志
`experiments/raw/logs/msm_arith_probe_20261023.stdout.log`）：

| 层 | bls12_381 crate（bellman 路径） | blst | 比值 | 判读 |
|---|---:|---:|---|---|
| 域乘（代理：Scalar×Scalar vs blst_fp_mul） | 16.29 ns | 20.38 ns | 0.80× | **无差距**；blst crate 在该构建下并未更快（无 ADX 收益证据） |
| fill 混合加（Jacobian 桶 + 仿射点） | **477.02 ns** | 547.86 ns（`blst_p1_add_or_double_affine`，公开 Jacobian API） | 0.87× | 公开 API 无差距；blst 的优势在其 multiexp **内部的 xyzz 路径**（Rust 绑定不暴露） |
| 倍加 / 全加 | double 367.47 ns；add_or_double 464.02 ns | 464.02 ns | ≈1.0× | 无差距 |
| 点→仿射 | 单点 19,915 ns（一次域求逆） | 批量 4,096 点 158.59 ns/点（单次批量求逆摊销） | 0.008× | 125× 差距存在，但 bellman 生产 reduce **不用**单点 to_affine，对 H-query 无影响 |

**归因结论（更新了阶段 B 文献表项的权重）**：

1. **差距主体在 fill 层的点加公式实现**。bellman 的 Jacobian 混合加实测 477 ns/数字，
   而 11 次域乘的理论值仅 ≈ 179 ns（11 × 16.29）——约 2.7 倍于纯域乘流水，说明 bls12_381
   crate 的混合加实现含大量公式外开销（分支、规范化路径）。blst 全 MSM 反推的
   ≈ 253 ns/数字与其 xyzz 公式（8 乘 + 3 平方 ≈ 202 ns + 调用/循环开销）吻合。
   两者之比 1.89×，与实测 P1 = 1.90 一致——**fill 层（占 H-query MSM 的 93.5%）即可
   解释全部差距**。
2. **域运算层无差距**（探针proxy 显示 bls12_381 的标量乘反而更快）。阶段 B 文献表中
   "blst 用 ADX 汇编域运算"的猜测在本机构建条件下不成立；候选设计不应指向域运算替换。
3. **reduce 层无差距**：bellman 桶间倍加（≈ 400 ns/桶 × 163,840 桶 ≈ 65 ms）与 blst 的
   批量转仿射 + 混合加（≈ 159 ns/点 × 155,648 桶 + 行内混合加 ≈ 64 ms）相当。
4. **批量求逆转换的 125× 差距是真实的但不落在 H-query 路径上**（bellman 只在 IC/最终
   转换用单点 to_affine；若未来候选触及 reduce 改写，这是一笔可收割的已知收益）。

传导估计（仅用于阶段 D 定标，不构成端到端承诺）：fill 占 1t body 的 67.5%；若 fill 内核
达到 blst 级单位成本（477 → ~253 ns/数字，1.89×），理论上界约 body **−35%**；即使只兑现
其中 1/6（≈1.15× 内核），也对应 body ≈ −6%——这正是预注册把 P1 GO 线设在 1.15 的依据。
**任何端到端数字必须由阶段 E 的完整证明 A/B 验证。**

## 6. 判定与下一步

- M 门禁：1t PASS（0.66%–1.29%）；8t FAIL（10.6%–24.4%，仅作生产参考，不作细判）。
- C 门禁：52/52 PASS。
- P1：**GO**（R = 1.9005，CI95 [1.8894, 1.9151]；G1 主负载一致 1.90–1.98，G2 2.19）。

**结论：进入阶段 D。** 按预注册 §4.3 GO 分支，下一动作是写阶段 D 候选预注册。单位成本分解
探针（§5）把候选方向收敛为一句话：**bellman fill 循环的 Jacobian 混合加（477 ns/数字）是
唯一可定位的差距层，blst 的 xyzz 内部路径（≈ 253 ns/数字反推）是已验证的对照锚点；域运算层
与 reduce 层均无差距。** 候选即将 blst 类 xyzz 桶公式移植进 bellman fill 内核（默认关闭、
独立配置、正确性以群相等验证），先在独立内核上过筛选门槛，再接完整 Spend proof 做配对 A/B。

**给阶段 E 的测量设计输入**：本设计的 8t 绝对计时只有在主负载（h_query）且样本量足够
（24 区组，0.97%）时才达到 1.5%；中小 8t 负载停在 ~3%。阶段 E 的端到端 A/B 应以 1t 级
内核筛选结论为据，完整证明层面用配对区组/cluster bootstrap 并事前冻结区组数与顺序，
不得用 8t 微基准差值替代证明层收益。

## 7. 复现轮（24 区组，独立第二轮）

`msm_kernel_bench_20261023_v2`（exe 同哈希，HEAD `67e9801`，24 区组，其余协议不变）：

| 条件 | 负载 | median_diff (ms) | CI95 (ms) | 半宽 % | 门禁 |
|---|---|---:|---|---:|---|
| 1t | h_query | −0.65 | [−3.16, 4.66] | **0.39** | PASS |
| 1t | l_query | −0.20 | [−1.82, 1.94] | **0.64** | PASS |
| 1t | ab_aux | +0.38 | [−1.36, 3.14] | **0.82** | PASS |
| 1t | g2_aux | +0.88 | [−0.55, 2.83] | **0.25** | PASS |
| 8t | h_query | +0.27 | [−1.70, 2.98] | **0.97** | PASS |
| 8t | l_query | −1.24 | [−1.76, 0.47] | **2.90** | FAIL |
| 8t | ab_aux | +0.65 | [−0.38, 2.37] | **2.96** | FAIL |
| 8t | g2_aux | −1.26 | [−6.64, 2.78] | **3.88** | FAIL |

- **P1 复现**：R = **1.9063**，CI95 [1.8999, 1.9110]（首轮 1.9005 [1.8894, 1.9151]）——
  两轮独立测量一致，GO 判定稳固。
- 1t 区组中位：h_query bellman_A 1,363.18 ms / blst 714.99 ms；g2_aux 770.36 / 353.68 ms。
- 8t h_query（主负载）在 24 区组下达到 0.97%（首轮 8 区组为 15.89%）——噪声随样本量
  按 ~1/√B 缩放；8t 的中小负载（~70–140 ms 级）仍停在 ~3%，其绝对差值仍不可细用。
- 结论不变：**1t 是可信的比较条件；8t 绝对计时只作生产量级参考**（8t bellman h_query
  区组中位 280.0 ms，与历史 8t 剖面同量级）。

## 8. 与预注册的偏差记录

1. **臂数 5 → 3（实现约束）**：预注册 §3.3 字面列出每区组 5 臂（含 8t 进程内的 bellman 1t 臂）。
   bellman 的 `Worker` 使用进程全局 rayon 池，1 线程臂在 `RAYON_NUM_THREADS=8` 的进程中
   物理上不存在。每个条件改测 3 臂（自身两个 bellman 标签 + `blst_1t`）；两对 A/A 与 1t 同线程数
   P1 对照（bellman_1t_A vs blst_1t）按原冻结口径保留。
2. **ic 不纳入 M 门禁判定**：见 §2 执行说明（绝对耗时 ~1 ms，相对 CI 由计时粒度支配）。
3. **分析脚本缺陷修复**：首轮分析中 `half_width_pct` 被双重百分比化（放大约 100×），导致 M 门禁
   假性 FAIL；修复为重算绝对半宽后一次性百分比化（缺陷修复，非标准变更；冻结标准 1.5% 未动）。
4. **区组数**：首轮按预注册默认 8；复现轮 24（`MSM_KB_BLOCKS` 覆盖，记录于本文与日志）。

## 9. 数据入口

- 原始（轮 1）：`experiments/raw/csv/msm_kernel_bench_20261023_{8t,1t}.csv`、
  `..._correctness.csv`；日志 `experiments/raw/logs/msm_kernel_bench_20261023_*.log`
- 原始（轮 2，24 区组）：`experiments/raw/csv/msm_kernel_bench_20261023_v2_{8t,1t}.csv`、
  `..._v2_correctness.csv`；日志 `experiments/raw/logs/msm_kernel_bench_20261023_v2_*.log`
- 探针：日志 `experiments/raw/logs/msm_arith_probe_20261023.stdout.log`
- 派生：`results/tables/msm_kernel_bench_20261023_{summary,aa}.csv`、
  `results/tables/msm_kernel_bench_20261023_v2_{summary,aa}.csv`
- 代码：bench `experiments/prover-smoke/src/bin/msm_kernel_bench.rs`；探针
  `experiments/prover-smoke/src/bin/msm_arith_probe.rs`；运行脚本
  `scripts/run_msm_kernel_bench.ps1`、`scripts/run_msm_arith_probe.ps1`；分析脚本
  `scripts/analyze_msm_kernel_bench.py`
- 上游：预注册 `experiments/metadata/sapling_msm_kernel_stagec_preregistration_20261023.md`；
  计划 `docs/msm_kernel_research_plan_20261023.md`；文献 `docs/msm_literature_survey_20261023.md`
