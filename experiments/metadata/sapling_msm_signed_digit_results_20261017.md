# 结果：H query G1 MSM 的有符号窗口重编码（优化目标 b）— 2026-10-17

> 预注册：`experiments/metadata/sapling_msm_signed_digit_preregistration_20261017.md`
> （冻结提交 `c507e0e`，**先于任何算法改动**）。本文件只填结果，不修改预注册的阈值与判据。
> 复核协议：`experiments/metadata/sapling_optimization_validation_protocol_20261017.md`。

---

## 0. 判定摘要

**通过（adopt）。**

| 冻结项 | 阈值 | 实测 | 判定 |
|---|---|---|---|
| 主指标：Spend 1t @ `0x1` 中位下降 | ≥ 3% | **−6.63%（批中位）/ −6.05%（单次）/ −6.94%（配对，5/5）** | **达标** |
| 辅助 1：H query `bucket_fill` / `bucket_reduce` 中位下降 | 改善 | **−12.92% / −13.45%** | 达标 |
| 辅助 2：Spend 8t @ `0xFFFF` 不退化 >1% | ≥ −1% | **−2.37%**（配对 −1.18%，4/7） | 达标（未发现退化） |
| 辅助 3：Output 1t @ `0x1` 不退化 >1% | ≥ −1% | **−11.35%**（配对 −8.78%，5/5） | 达标（且改善） |
| 内存：`prove_peak_abs_bytes` 不上升 | ≤ 0% | **−1.99%（−2.00 MB）** | 达标（且下降） |
| 正确性 ①②③④ | 全过 | 78/78 `verified`、2..=20 全宽度逐位相同、前缀/小查询对照、参数哈希不变 | 达标 |

一句话：**把 22 个 12-bit 无符号窗口换成 20 个 13-bit 平衡有符号窗口（桶数 4095→4096），
Spend 端到端 1 线程证明时间下降约 6%，Output 下降约 11%，峰值内存下降 2.0 MB，
且每一层证据（群加次数模型、阶段计时、内存字节差、两种编码逐位相同）都指向同一机制。**

---

## 1. 交付物与提交

| 内容 | 位置 / 提交 |
|---|---|
| 算法 | `vendor/bellman/src/multiexp.rs` — 提交 `03909b5` |
| 微基准与正确性门 | `experiments/prover-smoke/src/bin/msm_window_bench.rs` — 提交 `03909b5` |
| 战役驱动 | `scripts/run_msm_signed_digit_campaign.ps1` — 提交 `5e82594`、`d3851b7` |
| 分析脚本 | `scripts/analyze_msm_signed_digit_experiment.py` |
| 原始数据 | 提交 `63cf747` + 本次追加 |
| 派生表 | `results/tables/sapling_msm_signed_digit_abba_20261017.csv`、`…_stage_profile_20261017.csv` |
| 报告 | `docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md` §20 |

---

## 2. 正确性

| 项 | 证据 |
|---|---|
| ① 真实证明全通过 | 主指标 30+30、8t 40+40、Output 30+30、内存 5+5、烟测 5+5 —— **全部 `verified=true` 且 `proof_bytes=192`** |
| ② 两种编码逐位相同 | `msm_window_bench` 在 **c = 2..=20 每个宽度**、n = 131,071 整规模下断言有符号结果 == 无符号结果 |
| ③ 朴素对照 | 64 项前缀 == 逐点 double-and-add（c = 1/3/5/8 × 两种编码）；n = 8（`n < 32 → c = 3` 路径）两种编码 |
| ④ 参数与规模 | spend `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13`、output `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |

调试构建断言（`debug_assert`）：末位进位必须为 0、被截断窗口必须全为"零数字"、被丢弃的位必须为零 —— 在 c = 2..20、n = 8192 下全部通过。

---

## 3. 主指标：Spend 1t @ `0x1`（ABBA / ABBA / BAAB，各 6 批 × 5 次）

A = `SAPLING_MSM_SIGNED_DIGITS=0`，B = `=1`；同一二进制 `e498c605…`；每轮 4 次单批调用交错，末轮反转轮内顺序；
半随"弃首批 + 弃每次 run 1"约定。

| 口径 | A | B | 变化 |
|---|---:|---:|---:|
| 批中位 pooled | 3903.6 ms | 3644.9 ms | **−6.63%** |
| 单次证明 pooled 中位（n=20 vs 20） | 3887.9 ms | 3652.6 ms | **−6.05%**，MWU 双侧 **p < 1e-4** |
| 配对中位（n=5，按轮内序号配对） | — | — | **−6.94%**，**5/5 全 B 更快** |
| 敏感性：不弃首批（n=6） | — | — | **−6.04%**，**6/6**，精确符号检验 **p = 0.0312** |
| 漂移（前half→后half 批中位） | 3886.4→3903.6（**+0.4%**） | 3644.8→3658.9（**+0.4%**） | 轮内基本对称 |

**关于 n=5 的符号检验**：5 对全对的最小可能双侧 p 就是 0.0625，因此冻结口径下的 p 值不是"不显著的反证"，
而是**配对样本量被压在下限**；单次证明层面（每臂 20 次）的 MWU 与不弃首批的 6/6 均显著。二者方向一致。

主机状态：每臂开始前采样总 CPU 占用 0–13%（28 逻辑核），测量期间无其它负载。

---

## 4. 辅助指标

### 4.1 H query 阶段计时（`SAPLING_MSM_STAGE_PROFILE`，n = 131,071，5 次中位）

| 相位 | A（c=12，22 chunk，4095 桶） | B（c=13，20 chunk，4096 桶） | 变化 |
|---|---:|---:|---:|
| `bucket_fill_sum_ms` | 1561.1 | **1359.3** | **−12.92%** |
| `bucket_reduce_sum_ms` | 102.5 | **88.7** | **−13.45%** |
| `exponent_chunk_prep_ms` | 44.6 | 50.3 | +12.9%（绝对 +5.7 ms） |
| `bucket_payload_at_max_concurrency_estimate_bytes` | 589,680 | 589,824 | +144 B（桶数组 4095→4096） |

l query（n = 98,638，20 次中位）：fill 292.4 → 258.6（−11.5%）、reduce 101.3 → 89.7（−11.5%）。
小查询（n = 8）：fill 不变（0.009 ms），reduce 0.729 → 0.395 ms（桶数 7→4）。

**采集顺序声明**：本项是 off→on 的顺序采集（非交错），且 `SAPLING_PROFILE=1` 会拖慢本身，
因此只作方向性证据，不参与主指标判定（与 §18 的约定一致）。

### 4.2 Spend 8t @ `0xFFFF`（非退化检查）

| 口径 | A | B | 变化 |
|---|---:|---:|---:|
| 批中位 pooled（n=7 vs 7） | 1099.7 ms | 1073.7 ms | **−2.37%** |
| 单次证明 pooled 中位 | 1078.7 ms | 1063.0 ms | −1.46%，MWU p = 0.566 |
| 配对（n=7） | — | — | −1.18%，B 更快 4/7，p = 1.000 |
| 漂移 | 979.1→1218.7（**+24.5%**） | 1073.7→1047.2（−2.5%） | 极不对称 |

8 线程批间波动自身 ±20%，A 臂后半段出现 +24.5% 漂移。**结论只能是"未发现退化"，不能声称改善。**

### 4.3 Output 1t @ `0x1`（非退化检查）

| 口径 | A | B | 变化 |
|---|---:|---:|---:|
| 批中位 pooled | 562.0 ms | 498.3 ms | **−11.35%** |
| 单次证明 pooled 中位 | 557.3 ms | 503.5 ms | −9.65%，MWU **p < 1e-4** |
| 配对（n=5） | — | — | **−8.78%**，**5/5** |
| 敏感性（n=6） | — | — | −8.60%，6/6，p = 0.0312 |
| 漂移 | 561.5→562.0（+0.1%） | 511.4→498.3（−2.6%） | — |

Output 的 H query n = 8191 仍取 c = 10（`best_signed_window` 与无符号规则同值），
但**桶数 1023 → 512**，reduce 直接减半 ⇒ 收益大于 Spend。

---

## 5. 内存

`prove_memory_ledger.exe`（重建后 `0055ff01…`），1t @ `0x1`，n = 5，两臂同插桩（`SAPLING_PROFILE=1`、`SAPLING_MEM_PROBE=1`）。

| 口径 | A | B | 变化 |
|---|---:|---:|---:|
| `prove_peak_abs_bytes` 中位 | 105,160,251 | **103,062,954** | **−2,097,297 B（−1.99%）** |
| H query `exponent_prep_live_delta_bytes` | 22,024,592 | **19,927,456** | −2,097,136 B |
| H query `nonzero_chunk_slots` | 2,864,709 | 2,620,825 | −8.5% |

预期值：少 2 个窗口 × 131,071 指数 × 8 B = **2,097,136 B**，与 `exponent_prep_live_delta_bytes`
的差值**逐字节吻合**；进程峰值差（2,097,297 B）与之相差 161 B（分配器抖动）。

---

## 6. 微基准（n = 131,071，1t @ LP0，暖态中位 3 次）

| 配置 | chunk | 桶数 | 建模群加 | MSM ms | ns/建模群加 |
|---|---:|---:|---:|---:|---:|
| 无符号 c=12（冻结基线） | 22 | 4095 | 3,063,742 | 1627.9 | 531.3 |
| 有符号 c=11 | 24 | 1024 | 3,194,856 | 1714.8 | 536.7 |
| 有符号 c=12 | 22 | 2048 | 2,973,674 | 1594.6 | 536.2 |
| **有符号 c=13（新默认）** | 20 | 4096 | **2,785,260** | **1478.2** | 530.7 |
| 有符号 c=14 | 19 | 8192 | 2,801,645 | 1497.9 | 534.6 |

−9.20%（c=13 vs 冻结基线），单次建模群加成本基本不变 ⇒ 收益来自次数。
`best_signed_window` 在 n = 131,071 选 c = 13、在 n = 8191 选 c = 10，与穷举最小值一致。

---

## 7. 实现要点

1. **窗口数公式**：`windows = bits / c + 1`（整除下取整 +1），不是 `ceil(bits/c)`。
   当 `c | bits` 时最高窗口满宽度、末位进位非零，多出的一个窗口吸收它（§20.3 / 本文件 §2）。
2. **桶下标**：`|d| − 1`，`bucket_count = 2^(c−1)`；零数字标记为偏移量 `2^(c−1)`（有符号路径的"空槽"）。
3. **负数字**：走 `AddAssignFromSource::sub_assign_from_source`（`SubAssign<&Self::Affine>`，
   即混合加 `self + (−rhs)`，成本与加相同）；`PrimeCurve: Curve: GroupOpsOwned<Self::Affine>` 已提供该约束。
4. **reduce 不改**：summation-by-parts 对带符号桶天然正确（权重仍是 `j+1`）。
5. **开关**：`SAPLING_MSM_SIGNED_DIGITS`（默认 `1`）；`=0` 恢复逐位相同的旧编码。
   `set_msm_window_c` / `set_msm_signed_digits` 供基准二进制编程控制。
   插桩行新增 `signed=` 字段（`BELLMAN_MSM_STAGE_PROFILE` 与 `BELLMAN_MSM_MEM_PROBE`）。

---

## 8. 复现步骤

```powershell
# 1) 构建
cd experiments\prover-smoke
cargo --offline --locked build --release --bins

# 2) 正确性 + 微基准（n=131071，1t@LP0）
$env:RAYON_NUM_THREADS='1'; $env:MSM_WINDOW_BENCH_N='131071'; $env:MSM_WINDOW_BENCH_REPS='3'
$env:MSM_WINDOW_BENCH_SIGNED='1'; $env:MSM_WINDOW_BENCH_C='11,12,13,14'
.\target\release\msm_window_bench.exe     # 全部正确性门 + 扫描

# 3) 主指标战役（ABBA/ABBA/BAAB）
$env:ZCASH_PARAMS_DIR='D:\Research\zcash-params'
& .\scripts\run_msm_signed_digit_campaign.ps1 -Prover spend -Threads 1 -AffinityMask 1 `
    -Orders ABBA,ABBA,BAAB -LabelPrefix msm_signed_primary -AllowDirtyWorktree

# 4) 分析与派生表
python scripts\analyze_msm_signed_digit_experiment.py
```

---

## 9. 偏差、教训与边界

1. **作废的中间件（保留）**：首次内存台账误用**未重建**的 `prove_memory_ledger.exe`
   （pre-target-b 二进制），两臂得到相同结果且插桩行缺 `signed=` 字段。已改名
   `sapling_prove_memory_ledger_msm_signed_{off,on}_20261017_stale_binary.csv` /
   `prove_memory_ledger_msm_signed_{off,on}_20261017_stale_binary*.log` **原样保留**并重跑。
   教训：`--bin` 只重建指定二进制，插件式依赖改动后必须 `--bins` 全量重建并核对哈希。
2. **阶段计时非交错**：辅助 1 为顺序采集，只作方向性证据（见 §4.1）。
3. **8t 口径功效不足**：8 线程批间波动 ±20%，8 批/臂不足以认证改善，只能做非退化检查。
4. **配对符号检验功效**：冻结约定"弃首批"把主指标配对数压到 5（最小 p = 0.0625）；
   已在报告中同时给出不弃首批的 6/6（p = 0.031）作为敏感性分析，但**不改变冻结判据**。
5. **未做**：wNAF（内存不可接受）、底层 `Fp` 算术（换库/写汇编）、指数物化方式（属目标 a）。
