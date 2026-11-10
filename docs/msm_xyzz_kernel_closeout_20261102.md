# MSM 内核 Phase D 结项：XYZZ 桶坐标（2026-11-02）

**一句话**：把 Bellman G1 MSM 的桶从 Jacobian 换成 XYZZ，正确性 100% 通过，
但完整 H-query 慢 **6.7%**（`S_MSM = 0.9368`，95% CI [0.9353, 0.9384]，
A/A 漂移 0.03%），判定 **NO_GO**。归因显示「公式本身持平、退化检查吃掉全部余量」，
因此与 blst 的 1.9× 差距不在坐标系统，而在 Fp 乘法核。

## 1. 这件事为什么值得做

阶段 C 把 Bellman 与 blst 的 1.90× 差距定位到 bucket fill 的混合点加
（477 ns vs 反推 253 ns），并给出一个自然假设：blst 用 XYZZ，Bellman 用 Jacobian，
换成 XYZZ 就能收回一部分差距。

这是本仓库第一次**自己实现并验证一个候选优化**，而不是继续测量既有代码。
结论无论是正是负，都能把「差距在哪」从推测变成事实。

## 2. 做了什么

| 项 | 内容 |
|---|---|
| 曲线层 | `vendor/bls12_381`（0.9.0 本地副本）新增 `G1BucketXyzz`：XYZZ 单位元、混合加/减、XYZZ+XYZZ、转 Jacobian（单次求逆） |
| MSM 层 | `vendor/bellman` 新增 feature `msm-xyzz-g1` 与 `multiexp` 的 G1 专用实现（复用同一套窗口 / signed digit / lazy recoding 逻辑）；**原 `multiexp_inner` 零改动** |
| 正确性 | `msm_xyzz_gate`：C1–C8 共 16 项，含 n = 8 / 1024 / 131,071 的完整 MSM **逐字节**等价 |
| 性能 | `msm_xyzz_ab`：12 区组配对 A/B（jac_A / jac_B / xyzz），1 线程、亲和掩码 0x1 |
| 归因 | `msm_xyzz_attrib`：把公式成本与退化检查成本分开测量 |

## 3. 关键数字

| 指标 | 值 |
|---|---|
| 正确性 | 16/16 PASS |
| `S_MSM` = T_jac / T_xyzz | **0.9368**（[0.9353, 0.9384]） |
| A/A 漂移 | +0.030% |
| 公式层（unchecked XYZZ vs Jacobian） | −0.5% ~ +0.7%，**持平** |
| 退化检查成本 | +3.1% ~ +5.6% |
| 桶内存 | 144 → 192 B（单数组 +196,608 B） |

## 4. 结论与它的边界

1. **XYZZ 在本实现上最多持平**：`unchecked` 版本只快 0.7%，而它算错退化输入，
   不可用。可用的实现必然带检查，必然更慢。
2. **差距在 Fp 乘法核**：单次混合加 910 ns ÷ 11 个 Fp 乘法 ≈ 83 ns/mul；
   blst 反推约 23 ns/mul。改写坐标不改变这个数字。
3. **不构成对 blst 的否定**：blst 的 XYZZ 实现与其汇编乘法核是一体的，
   单独把公式搬过来不成立。
4. **未做侧信道评估**：本实现用真实分支处理退化情形（与 blst 同类的非
   constant-time 语义），已在代码注释与预注册 §7 中登记。

## 5. 下一步（若继续这条线）

按本次归因，唯一有量级空间的方向是 **Fp 乘法实现**：
ADX/MULX 汇编、AVX-512 IFMA 的 52 位分块、降低 Montgomery 归约延迟。
这是独立课题，不属于 Phase D；且应作为新分支新预注册启动，不再复用本次代码。

## 6. 复现

```bash
cd experiments/prover-smoke
cargo build --release --bin msm_xyzz_gate --bin msm_xyzz_ab --bin msm_xyzz_attrib

# 正确性 + 内存账本
RAYON_NUM_THREADS=1 ./target/release/msm_xyzz_gate

# 归因（公式 vs 退化检查）
RAYON_NUM_THREADS=1 ./target/release/msm_xyzz_attrib

# A/B（单核亲和；Windows 用 SetProcessAffinityMask，见 scripts 说明）
RAYON_NUM_THREADS=1 XYZZ_AB_BLOCKS=12 XYZZ_AB_RUNS=3 \
  XYZZ_AB_CSV=../raw/csv/msm_xyzz_h_query_20261102.csv \
  ./target/release/msm_xyzz_ab
python3 ../../scripts/analyze_msm_xyzz_ab.py
```

产物：`experiments/raw/csv/msm_xyzz_h_query_20261102.csv`（108 行）、
`..._analysis.md`、`experiments/raw/logs/msm_xyzz_h_query_20261102.log`、
`experiments/raw/logs/msm_xyzz_attribution_20261102.log`。

详细判定与归因见 `experiments/metadata/sapling_msm_phase_d_xyzz_results_20261102.md`。
