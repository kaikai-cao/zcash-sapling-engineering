# 预注册：阶段 D — XYZZ 桶坐标 G1 MSM 内核（2026-11-02）

**状态**：冻结于任何性能测量之前。
**基线**：`main` @ `1fb6cc1`（分支 `experiment/msm-phase-d-xyzz-20261102` 自此切出）。
**上游依据**：阶段 C 已确认 Bellman 单线程 H-query G1 MSM 相对 blst 为
1.9005×（95% CI [1.8894, 1.9151]），复现轮 1.9063×，且差距被定位到
bucket fill 的混合点加（Bellman Jacobian 约 477 ns/add，blst XYZZ 反推约 253 ns/add）。

---

## 0. 一句话

在**不改任何生产默认值**的前提下，实现一条可独立启用的
「BLS12-381 G1 → XYZZ 桶 + XYZZ 归并」MSM 路径，先用群元素逐字节等价性证明其正确，
再用配对 A/B 测量它相对现有 Jacobian 路径的 H-query 加速比，
达到门槛才继续做完整 Spend Prove，否则按 NO_GO/MARGINAL 归档。

## 1. 边界（不做什么）

1. **不做**软件预取（software prefetch）。它会同时改变缓存访问特征与标量相关性，混入本次结论。
2. **不做**批量仿射转换（Montgomery trick）。它是正交优化，混合后无法归因。
3. **不调**窗口宽度 `c`、不调线程数、不改自适应窗口策略。这些是已冻结的既有结论。
4. **不碰** G2 路径（保持 projective fallback）。
5. **不改**生产默认：所有新代码在 feature `msm-xyzz-g1` 之后，且运行时开关
   `SAPLING_MSM_XYZZ=1` 未设置时走原路径，逐字节不变。
6. **不合入** `main`；结果以独立 PR 呈现，生产默认关闭。
7. 本次**不评估**侧信道语义的充分性，只标注已知风险（§7）。

## 2. 实现方案（结构在测量前冻结）

### 2.1 为什么不是「trait 关联类型 + 运行时开关」

`multiexp_inner` 的桶类型来自泛型 `G: PrimeCurve`。若给 `G` 加
`BucketOps { type Bucket }`，关联类型是**编译期**确定的，无法由运行时环境变量改变；
若把 `Bucket` 做成 `enum { Jacobian, Xyzz }`，则 A 臂（基线）也会被换成 union，
基线本身被污染，A/B 不再是「原实现 vs 新实现」。

因此采用：**G1 专用函数 + 调用点分派**。

### 2.2 代码落点

| 文件 | 变更 |
|---|---|
| `vendor/bls12_381/`（新增，0.9.0 本地副本） | 新增 `G1BucketXyzz`：单位元、`add_mixed_assign(P, subtract)`、`add_xyzz_assign`、`into_projective` |
| `vendor/bellman/src/xyzz_g1.rs`（新增，feature `msm-xyzz-g1`） | `multiexp_g1_xyzz()`：复用既有窗口/有符号数字/惰性重编码逻辑，桶数组改为 `Vec<G1BucketXyzz>`，fill 走 XYZZ 混合加，reduce 在 XYZZ 内完成，仅在返回前转换一次 |
| `vendor/bellman/src/multiexp.rs` | 仅新增 `pub use`/开关读取函数；`multiexp_inner` **零改动** |
| `vendor/groth16/src/prover.rs` | H-query 调用点：开关打开时调用 `multiexp_g1_xyzz`，否则原调用 |
| `experiments/prover-smoke/Cargo.toml` | `[patch.crates-io] bls12_381 = { path = "../../vendor/bls12_381" }`；bellman 开 `msm-xyzz-g1` |
| `experiments/prover-smoke/src/bin/msm_xyzz_ab.rs`（新增） | A/B 基准；不改动阶段 C 已冻结的 `msm_kernel_bench.rs` |

### 2.3 XYZZ 表示与公式（实现前冻结）

`x_affine = X / ZZ`，`y_affine = Y / ZZZ`，其中 `ZZ = z²`、`ZZZ = z³`。
单位元：四个坐标全零。仿射初始化：`ZZ = 1, ZZZ = 1`。负点：`Y ← −Y`，其余不变。

**混合加（XYZZ + affine）**，由 EFD `madd-2007-bl` 用 XYZZ 消去 `Z1²` 与 `(Z1+H)²`：

```
U2  = x2·ZZ1          (M)
S2  = y2·ZZZ1         (M)
H   = U2 − X1
HH  = H²              (S)
I   = 4·HH
J   = H·I             (M)
r   = 2·(S2 − Y1)
V   = X1·I            (M)
X3  = r² − J − 2V     (S)
Y3  = r·(V − X3) − 2·Y1·J   (2M)
ZZ3  = 4·(ZZ1·HH)     (M)
ZZZ3 = 8·(ZZZ1·H·HH)  (2M)
```

共 9M + 2S，对照当前 `add_mixed`（Algorithm 8, eprint 2015/1060）13M。
减法通过 `subtract` 标志对 `y2` 取负实现，不额外做 affine 取负。

**XYZZ + XYZZ**（桶归并）：标准 `add-2007-bl`，同样用 `ZZ`/`ZZZ` 省去两次平方，
并维护 `ZZZ3 = ZZZ1·ZZ2·…` 的立方关系。

**转回 Jacobian**：一次求逆即可。令 `t = ZZ·ZZZ`、`inv = 1/t`，则
`1/ZZ = ZZZ·inv`、`1/ZZZ = ZZ·inv`，得仿射 `(X/ZZ, Y/ZZZ)`，再构造 `G1Projective`。
单位元单独返回。

### 2.4 归并必须在 XYZZ 内完成

若逐桶转回 Jacobian 再求和，会引入 4096 次求逆，必然抵消收益。
`running_sum` 与 `acc` 都在 XYZZ 内，**整个 chunk 只转换一次**。

## 3. 负载与运行条件（冻结）

| 项 | 值 |
|---|---|
| 主负载 | `h_query` G1，`n = 131,071`，dense |
| 标量 | 既有确定性 xorshift fixture（`msm_kernel_bench` 同一 seed 规则） |
| 窗口 `c` | 13（生产默认规则在该 n 下的取值，不覆盖） |
| 窗口数 | 20（signed，`ceil(255/13)`） |
| 桶数 | 4,096（`2^(c−1)`，signed） |
| 有符号窗口 | 开（生产默认） |
| 惰性重编码 | 开（生产默认） |
| 自适应窗口 | 关（不触发，`c` 不覆盖） |
| 线程 | 1（`RAYON_NUM_THREADS=1`），进程亲和性固定单 P 核 |
| 机器 | 与前序阶段同一台（结果文档记录 CPU 型号与核号） |

**次要观察**（不进主统计）：`l_query`、`ab_aux`（G1，含 0/1 稀疏）、`g2_aux`（G2，验证未受影响）、8 线程。

## 4. 正确性门禁（C 级，任一失败整轮作废）

| 编号 | 内容 |
|---|---|
| C1 | `identity + P == P`（XYZZ 与 Jacobian 各自的 identity 均测） |
| C2 | `P + Q` 与 Jacobian 混合加结果逐字节一致 |
| C3 | `P − Q` 与 Jacobian 混合减结果逐字节一致 |
| C4 | `P + P` 与 `double()` 一致 |
| C5 | `P + (−P) == identity` |
| C6 | `identity + identity == identity` |
| C7 | 连续 1024 个随机仿射点累加，与 `G1Projective` 累加逐字节一致 |
| C8 | **完整 MSM 等价**：同 fixture 下 `multiexp`（Jacobian）与 `multiexp_g1_xyzz` 输出经非压缩序列化后逐字节相等；对 `n = 8 / 1024 / 131,071` 三个规模各测一次 |

边界用例（并入 C7/C8 的专门分支）：首桶加点、桶内单点、全零标量、
signed digit 为正、为负、跨窗口进位、末窗口仅少量有效位。

**比较曲线群元素，不以「程序不报错」代替正确性。**

## 5. 性能门禁（P 级）

### 5.1 微基准

配对区组设计：每区组内 A（Jacobian）、B（XYZZ）各 1 次预热 + 3 次测量，
顺序按冻结 seed 平衡；每臂取区组内中位数；至少 8 区组，时间允许扩到 12。

主指标：

```
S_MSM = median_block(T_jacobian) / median_block(T_xyzz)
```

| 判定 | 条件 |
|---|---|
| **GO** | `S_MSM ≥ 1.15` |
| **MARGINAL** | `1.08 ≤ S_MSM < 1.15` |
| **NO_GO** | `S_MSM < 1.08` |

MARGINAL 与 GO 都继续做完整证明；NO_GO 停止扩展，直接归档。

### 5.2 完整证明

| 判定 | 条件 |
|---|---|
| **PROVE_GO** | Spend Prove 中位数降幅 ≥ 5%，且配对 bootstrap 95% CI 下界 > 0 |
| **PROVE_WEAK** | 降幅 ∈ (0%, 5%)，方向一致但不足门槛 |
| **PROVE_NO_GO** | 降幅 ≤ 0% 或方向不稳 |

Output 证明只做**不回退检查**（降幅不得 < −3%），不宣称加速。

## 6. 内存

- 记录：桶数组实测分配字节（`4096 × size_of::<Bucket>`）、`max_concurrent_chunk_regions`、
  桶 payload 估算、Spend Prove 峰值（既有 `prove_memory_ledger` 口径）。
- 预期增量：单桶 144 → 192 B，单桶数组 +196,608 B；8 个并发 chunk 约 +1.5 MiB。
- **硬约束**：Prove 峰值内存增幅 > 5% 时，即使 `S_MSM` 达标也降级为 MARGINAL，
  不得以「快一点、内存翻倍」结项。

## 7. 已知风险（登记，不在本次评估范围）

1. **XYZZ 加法非 constant-time**：与现有 Jacobian `add_mixed` 一样含
   identity / 同点 / 互逆点条件分支（当前实现用 `conditional_select`）。
   本次不引入新的数据相关内存访问（不预取），但分支语义未做侧信道评估。
2. **不构成生产建议**：本实验默认关闭；进入生产需单独的数据相关分支与内存访问评估。
3. **内核加速 ≠ 证明加速**：阶段 C 的教训。必须走完 `点加 → MSM → Spend Prove` 三层，
   只有最后一层达标才可称为证明器优化成果。

## 8. 停止条件

任一条成立即停止并归档，不做补救性追测：

1. C1–C8 任一失败且 24 小时内不能修复（说明实现路线有结构性障碍）。
2. `S_MSM < 1.08`（NO_GO）。
3. Prove 峰值内存增幅 > 5% 且无法通过缩小桶数组并发解决。
4. 完整 Prove 降幅 ≤ 0%（PROVE_NO_GO），不再尝试调参挽救。

## 9. 交付物

1. `vendor/bls12_381` 的 `G1BucketXyzz` 与单元测试；
2. `vendor/bellman` 的 `msm_g1_xyzz` 路径（feature-gated，默认关）；
3. `experiments/prover-smoke/src/bin/msm_xyzz_ab.rs` 与原始 CSV/日志；
4. Spend Prove A/B 数据；
5. 内存账本；
6. `experiments/metadata/sapling_msm_phase_d_xyzz_results_20261102.md`（GO/NO_GO/MARGINAL + 限制）；
7. `docs/msm_xyzz_kernel_closeout_20261102.md`（结项说明）。

## 10. 与既有文档的关系

- 阶段 C（`sapling_msm_kernel_stagec_preregistration_20261023.md`）的 A/A 校准与
  blst 对照结论不变，本阶段只在其定位的差距点上做**实现侧**验证。
- 三个已认证优化开关（signed digits、lazy recoding、FFT scratch）**全部保持开启**，
  不参与本次对照。
- MSM 内核 Phase D 在 `20261026` 范围文件中被标记为暂停；本文档记录其**主动重启**，
  重启理由为阶段 C 已完成归因，具备可执行的实现假设。

## 11. 冻结签名

| 项 | 值 |
|---|---|
| 冻结时间 | 2026-11-02 |
| 基线提交 | `1fb6cc1` |
| 分支 | `experiment/msm-phase-d-xyzz-20261102` |
| 测量开始前是否存在性能数据 | **否**（本文件提交时尚未运行任何 XYZZ 计时） |
