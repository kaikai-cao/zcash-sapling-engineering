# MSM 相关工作文献对照（2026-10-23）

> 目的：在修改 `vendor/bellman/src/multiexp.rs` 之前，确认已有工作的边界与本项目的差异，避免重复造轮子。
> 方法：摘要级调研（2026-10-23 完成）；标注 [全文待验证] 的条目因 ePrint Cloudflare 拦截需下载全文后核对，见 §5。
> 关联：[`msm_kernel_research_plan_20261023.md`](msm_kernel_research_plan_20261023.md)（阶段 A 状态冻结，本文献对照是其 §4.1 候选排序的依据）。

## 1. 四组资料的六维对照表

| 对照维度 | Fan, Kuchta, Sica, Xu — JoC 2025（ePrint 2024/750） | SimdMSM — TCHES 2025 | blst 批量点累加实现 | Fixed-Base MSM 预印本（2026，未评审） |
|---|---|---|---|---|
| **算法贡献** | 广义**最优桶集合构造**（给定乘子集 M 求使时间最小的桶集 B）；修正 Luo et al. 2023 的 Property 1；用高效 **endomorphism** 同时降运行时与存储 | AVX512-IFMA 实例化的六种 SIMD 点加引擎（三坐标系统 × G1/G2）；无写冲突 MSM 架构 + 三层缓冲；**点去重**；"Three-Stage" 内存优化 | Pippenger：**Booth 重编码**标量；**xyzz（缓存 Z²/Z³）桶坐标** + `xyzz_dadd_affine` 混合加；填充循环内**下一桶软件预取**；**批量仿射转换**（Montgomery trick，单次域求逆）；小 n 走 wbits 预计算表路径 | 扩展 BGMW：桶内点对/三点组的**预计算查表**替代点加；chunk 化预计算提供内存-时间权衡 |
| **适用场景** | 固定基（proving-key 式）大 MSM [全文待验证：具体规模] | 大 MSM（已集成进 libsnark/Groth16） | 通用：≥32 点 Pippenger；<32 点固定窗表；BLS 签名验证 | **小规模**固定基 MSM |
| **曲线与硬件** | pairing-friendly 曲线；参考实现 `MSM_blst_ext` 基于 blst [全文待验证：实验曲线，预计 BLS12-381] | **BLS12-381**（RELIC 基础）；依赖 **AVX-512 IFMA** | **BLS12-381**；x86-64 ADX/BMI 汇编 + ARMv8 + portable C 回退 | [全文待验证：曲线] |
| **性能指标** | 对 Pippenger 有理论 + 实验改进 [全文待验证：具体数字] | AVX-MSM 对 Pippenger 最高 **27.86×**；AVX-ZK 对 libsnark 11.53×–20.26× | 生态标杆（第三方基准中普遍快于 arkworks 后端） | 对小 MSM 对 Fixed Window 最高 **3×** |
| **存储代价** | endomorphism 以预计算点摊薄；论文 Note 4：预计算点可压缩存储（一个坐标 + 1 bit） | 论文表述 "constant memory overhead" | wbits 表 = npoints·2^(wbits−1) 个仿射点（wbits=8 时数 MB；源码注释：表复用场景才对 ≤~16K 点更快） | 随 chunk 参数近线性增长；以内存换运行时 |
| **与本项目的区别** | 优化在**桶集合构造与标量分解**层；本项目已关闭的 Stage 1b / c=12 是**窗口宽度**层——不同层，不构成重复 | 加速比来自 AVX-512；**i7-14700 无 AVX-512**，实现与数字均不可直接移植；点去重对 Sapling H-query（点基本互异）收益存疑 | 已知成熟实现，**不是新算法**；但其 fill 内核技术（xyzz 桶坐标、预取、批量仿射转换）与本项目 bellman 实现（标准投影桶、无预取、无批量转换）存在明确**实现级**差异，且不依赖 SIMD | 只覆盖 8 标量槽的输入相关小查询，**不解释 H-query** |

## 2. 逐篇要点

### 2.1 Fan, Kuchta, Sica, Xu — Journal of Cryptology 38(2):21, 2025（ePrint 2024/750）

-  revisit Luo-Fu-Gong（TCHES 2023(2):358–380）的预计算式 MSM，给出**一般化的最优桶集合构造**：给定乘子集 M，算法给出使计算时间最小的桶集 B；修正前作 Property 1 并给出实验验证。
- 进一步提出 **efficient endomorphism**：论文 Note 1 表明 endomorphism 情形下范数 |q|² 取代原 q 的角色（大小相同、h 相同）——即通过曲线自同态做标量/指数分解、缩短有效位长，同时降低存储需求；Note 4：预计算点可用压缩存储（一个坐标 + 一个符号位）。
- 实现：`github.com/xinxin-crypto/MSM_blst_ext`（blst 扩展，Apache-2.0，仓库无 README 细节）；前作实现 `github.com/LuoGuiwen/MSM_blst`。
- 与本项目关系：H-query 是固定 proving-key 查询点上的大 MSM，正是该框架的目标场景。注意其优化层（桶集合构造 / 标量分解）与本仓库已关闭的窗口宽度实验不是同一层。

### 2.2 SimdMSM — TCHES 2025(2):681–704（Jiang, Peng, Luo, Chen, He）

- AVX512-IFMA 实例化六种点加引擎（三种坐标系统 × G1/G2）；无写冲突架构 + 任务级/循环级并行 + 三层缓冲；点去重与 "Three-Stage" 内存优化。
- 结果：AVX-MSM 对 Pippenger 最高 27.86×（BLS12-381 / RELIC）；AVX-ZK 集成 libsnark 后对 libsnark 11.53×–20.26×。
- **硬件约束（关键）**：依赖 AVX-512 IFMA；i7-14700 官方规格只有 AVX2（Intel ARK 页明示指令集扩展为 SSE4.1 / SSE4.2 / AVX2），因此**实现与加速比均不可直接移植**。可借鉴的是与硬件无关的思想（点去重、内存分级），但 Sapling H-query 的点基本互异，点去重收益存疑，需在阶段 C 用真实输入分布验证。
- artifact：`github.com/oooldmoon/SimdMSM`（GPL-3.0；许可证有传染性，仅作参考，勿并入 vendor）。

### 2.3 blst 的批量点累加实现（src/multi_scalar.c，2026-10-23 读取核查）

- **Booth 重编码**：Pippenger 与 wbits 两条路径都用 `booth_encode` 做有符号数字重编码——与本仓库 target b（balanced-signed recoding）同族。即该层面的优化本项目已采纳。
- **xyzz 桶坐标**：桶为私有 `POINTonE1xyzz`（X, Y, ZZ, ZZZ 缓存 Z²/Z³），填充用 `xyzz_dadd_affine`（仿射点加入投影桶）；窗口归约用 `integrate_buckets` 的运行和（Σ x[i−1]·i）直接在 xyzz 上完成，不逐桶转仿射。
- **批量仿射转换**：`blst_p1s_to_affine` 用 Montgomery trick（Z 坐标乘积树 + 单次 `reciprocal_` 域求逆 + 回代乘法）批量转仿射；wbits 预计算路径同样批量转换。
- **软件预取**：填充循环对下一个 Booth 索引对应的桶 `vec_prefetch`，隐藏随机桶访问的缓存延迟。
- **窗口规则**：`pippenger_window_size(n)`：wbits = ⌊log2 n⌋，>12 时 −3；n = 131,071 → wbits = **13**，与本仓库"c=13 时间最优"的实测一致。
- **小 n 路径**：n < 32 且 scratch 允许时走 wbits=4 预计算表（BGMW 式）。
- **侧信道语义**：本次核查 `src/multi_scalar.c`、`bindings/blst.h`、README 与 Rust crate 文档，均未见 constant-time 声明；该实现结构上不是 constant-time（桶索引、Booth 查表、预取均依赖标量数值），生态按非 constant-time 使用（Constantine 基准明确要求以随机数据测量 blst MSM，否则 doubling 路径会显得异常快）。迁移前必须评估侧信道语义——bellman 现有路径同样不做 constant-time 保证，威胁模型（证明端 witness 标量为秘密）须在预注册中写明。

### 2.4 Optimizing Multi-Scalar Multiplication Over Fixed Bases（preprints.org 202604.0045，2026，未经同行评审）

- 面向**小规模**固定基 MSM：扩展 BGMW，用点组合的结构化预计算把桶内多次点加换成查表；chunk 化预计算提供内存-时间权衡。对小 MSM 对 Fixed Window 最高 3×。
- 与本项目关系：只适用于输入相关小查询（8 标量槽）与验证端，不能解释 H-query（n = 131,071）的大 MSM。列为小查询专用候选，优先级低。

### 2.5 关联工作（顺带发现，供后续跟踪）

- **Luo, Fu, Gong（TCHES 2023）**：Fan et al. 的前作；BLS12-381 + blst 实现；理论分析对 Pippenger 桶法省 >21%、对流行变体省 2.6–9.6%；实测对 blst Pippenger 省 >17.7%（n = 2^e, 10≤e≤21）、对流行 Pippenger 变体省 3.1–9.2%。量级与本项目 5% 目标匹配，是最直接的算法级参照。
- **SRE（arXiv 2610.27452，2026-10）**：点合并（point merging）去重；点操作 −25%、Pippenger 运行时 +30%、ZKP 系统 10–20%。对 Sapling H-query 的点重复率需实测后判断收益。
- **Dutta, Kuchta, Sica（ePrint 2026/966）**：抗计时攻击的新 MSM 方法——若进入侧信道敏感场景需跟踪。
- **Constantine（Nim，BLS12-381）MSM 开发记录（issue #220）**：两个与本项目直接相关的观察——n ≈ 2^17（131,071，正是 H-query 规模）处开始触及 L1 cache 限制与 64K aliasing 冲突边界；c > 16 因内存带宽不再有收益。支持"bucket fill 在 n = 2^17 处于缓存行为转折点"的判断。

## 3. 关键问题的回答

> 是否存在一种已有算法，与当前实现存在明确差异，并且在 i7-14700、BLS12-381、真实 Sapling 查询规模、现有内存条件下仍有值得验证的性能空间？

**有；且必须用阶段 C 的对照基准定量，不能只凭文献数字：**

1. **blst 式 fill 内核 vs 当前 bellman 实现**：差异明确且为实现级（xyzz 桶坐标与混合加公式、软件预取、批量仿射转换），不依赖 AVX-512，可在 i7-14700 上直接验证。但要注意：blst 的域运算是手写汇编，`462 ns/混合加` 的对手可能强在 Fp 乘法而非 MSM 结构——这正是阶段 C"单位操作级 profiling"要分离的变量。
2. **Fan et al. 2025 / Luo et al. 2023 的最优桶集合 + endomorphism**：算法级差异（桶集合构造与标量分解，而非窗口宽度）；前作在 BLS12-381 + blst 上 3.1–9.2%（对流行变体）的实测与 5% 目标同量级；存储代价（3nh 量级预计算点、可压缩）需对照 86.18 MB 内存基线评估。
3. **SimdMSM**：加速比不可移植（AVX-512）；点去重思想对 H-query 可能无效（点基本互异）——降级为观察项。
4. **Fixed-base 预印本**：不适用于 H-query，仅小查询备用。

**结论：候选存在且可区分，进入阶段 C（A/A 校准 + `msm-kernel-bench`，含 blst 对照实现）。用"当前实现与成熟实现的差距主要来自群运算公式、数据布局还是输入访问方式"的数据结论，决定是否进入阶段 D。**

## 4. 引用清单

- Fan X., Kuchta V., Sica F., Xu L. *Speeding Up Multi-scalar Multiplications for Pairing-Based zkSNARKs*. Journal of Cryptology 38(2):21, 2025. DOI 10.1007/s00145-025-09540-x；ePrint 2024/750；实现 `github.com/xinxin-crypto/MSM_blst_ext`
- Jiang R., Peng C., Luo M., Chen R., He D. *SimdMSM: SIMD-accelerated Multi-Scalar Multiplication Framework for zkSNARKs*. TCHES 2025(2):681–704. DOI 10.46586/tches.v2025.i2.681-704；artifact `github.com/oooldmoon/SimdMSM`
- blst（Supranational LLC）：`src/multi_scalar.c`、`bindings/blst.h`（2026-10-23 读取）
- *Optimizing Multi-Scalar Multiplication Over Fixed Bases*. Preprints.org 202604.0045, 2026（未经同行评审）
- Luo G., Fu S., Gong G. *Speeding Up Multi-Scalar Multiplication over Fixed Points Towards Efficient zkSNARKs*. TCHES 2023(2):358–380
- Ku J. et al. *SRE: Accelerating Zero-Knowledge Proofs via Scalar Redundancy Elimination in Multi-Scalar Multiplication*. arXiv:2610.27452, 2026-10
- Dutta A., Kuchta V., Sica F. *A New Multiscalar Multiplication Method Resistant to Timing Attacks*. ePrint 2026/966
- Constantine（mratsim）MSM 开发记录，issue #220：n = 2^17 缓存边界与 c > 16 带宽饱和观察
- Intel ARK：Core i7-14700 产品规格（指令集扩展 SSE4.1 / SSE4.2 / AVX2，无 AVX-512）

## 5. 待全文验证事项

ePrint 2024/750 的 PDF 受 Cloudflare 机器人验证拦截（2026-10-23 多次尝试：curl 直连、浏览器请求头、jina reader、Springer PDF、IACR 中国镜像均未取得全文）。以下条目需用浏览器下载全文后核对并更新本表：

1. Fan et al. 的实验曲线（预计 BLS12-381：前作与 `MSM_blst_ext` 均基于 blst）；
2. 实验硬件与相对 Pippenger 的具体加速比；
3. endomorphism 的存储 / 预计算细节（在线 vs 离线计算）；
4. 最优桶集合构造本身的算法开销（是否随乘子集 M 变化）。
