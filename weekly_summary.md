# Zcash Sapling / Groth16 工程基线：阶段总结

**阶段状态：** 第一轮真实工程基线与 Output 瓶颈定位已完成；本仓库进入基线冻结阶段。这里不是完整研究结项，也不是算法优化结果。  
**测量日期：** 2026-10-10  
**Sapling 源码：** `sapling-crypto 0.9.0`，commit `88a7946b4a3066787776e11f0a502654167e022d`  
**正式基线环境：** Windows 11、Intel Core i7-14700、32 GB RAM、Rust 1.98.1（本地记录）、Release、`RAYON_NUM_THREADS=1`、BLS12-381 Groth16。

## 1. 工程规模与参数文件

| 指标 | Spend | Output |
|---|---:|---:|
| R1CS 约束数量 | 98,777 | 7,827 |
| 辅助变量数量 | 98,638 | 7,821 |
| 公开输入（不含常数 1） | 7 | 5 |
| 输入变量（含常数 1） | 8 | 6 |
| 估算 domain size | 131,072 | 8,192 |
| 参数文件大小 | 45.737 MiB | 3.426 MiB |
| 参数文件 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |

约束与变量数量来自 counting ConstraintSystem。domain size 是按约束数向上取整到二次幂的估算值，并非直接读取实际运行时域对象。参数文件大小不等价于理论 CRS、Proving Key 或 Verifying Key 的独立大小；本项目没有将这些对象的尺寸混为一谈。

参数元数据程序分别测得 Spend 24,326.502 ms、Output 1,774.506 ms 的读取与验证时间，但每种参数只有一次测量。独立证明程序中的加载时间来自其他批次，不能混合当作同一组重复样本，也不能将其当作严格的冷／热缓存对照。

## 2. 正式证明与验证基线

正式汇总只选择预先指定的批次，每种电路各有 5 次证明与验证测量。

| 指标 | Spend | Output |
|---|---:|---:|
| 正式 batch ID | `1791613854129` | `1791549582046` |
| Prove 中位数 | 3,385.716 ms | 514.853 ms |
| Prove 最小 / 最大 | 3,377.138 / 3,484.750 ms | 507.096 / 560.162 ms |
| Verify 中位数 | 2.790 ms | 2.150 ms |
| Verify 最小 / 最大 | 2.775 / 2.797 ms | 2.102 / 2.195 ms |
| 序列化证明大小 | 192 bytes | 192 bytes |
| 验证成功 | 5 / 5 | 5 / 5 |

Prove 计时不包括参数加载、验证密钥准备和见证构造。Verify 统计的是实验中单个 Sapling 证明检查调用，不等于完整钱包交易或整套共识验证的端到端时间。

## 3. 内存和重复运行的限制

目前整进程 Peak Working Set 只有每种电路各一次观测：Spend 101.31 MiB、Output 22.22 MiB。该数值覆盖参数加载、验证、证明与验证过程，并非 Prove 独占内存；样本数不足以报告稳定的内存分布。

额外的首次／重复调用观察显示运行时间有波动，但实验没有清空操作系统文件缓存，首次 proving 前也已完成参数和输入准备。因此目前不能宣称完成了严格的 cold-versus-warm benchmark，也没有可靠证据将波动归因于某个具体系统进程或硬件因素。所有记录批次的证明检查均通过；探索性批次保留在原始数据中，不纳入指定的正式汇总。

## 4. Frozen Baseline 与 Sapling：成本结构对照

| 证据 | 测量结果 | 结论边界 |
|---|---|---|
| Frozen synthetic baseline（BN254 / arkworks 0.6.0） | 单次带插桩记录：Prove 3,075.022 ms；MSM 合计 2,816.798 ms，占 91.60% | 合成工作负载的一次记录 |
| Sapling Output（BLS12-381） | 两份较低开销单线程 profile 的稳态 MSM 调用时间占比中位数分别约 93.41% 和 93.19% | 支持 MSM 是已测 Output 单线程路径的主导成本 |
| Sapling Spend | 尚无可对账的同口径 MSM 占比 | 不将 Output 结论推广到 Spend |
| 多线程 Sapling | 调用级计时存在并行重叠 | 不能将并行调用耗时简单相加后计算 MSM / Prove 比例 |

BN254 合成基线与 BLS12-381 Sapling 使用不同曲线、工作负载和实现，因此这是一项规模与成本结构对照，不是两者绝对速度的竞赛。

## 5. Sapling Output：从整体 MSM 定位到具体调用

在较低开销的单线程 profile 中，Output 的八次 MSM 调用时间之和，在稳态轮次约占完整 Prove 的 93.2%–93.4%。按 vendored Groth16 prover 的调用顺序与日志字段映射，当前最高的单次调用是 **B-G2 auxiliary query**。

| MSM 调用 | 群 | 标量数量 | window | profile-size 稳态中位数 |
|---|---|---:|---:|---:|
| H query | G1 | 8,191 | 10 | 129.125 ms |
| L query | G1 | 7,821 | 9 | 82.987 ms |
| A input query | G1 | 6 | 3 | 0.938 ms |
| A auxiliary query | G1 | 7,821 | 9 | 65.012 ms |
| B G1 input query | G1 | 6 | 3 | 0.772 ms |
| B G1 auxiliary query | G1 | 7,821 | 9 | 53.180 ms |
| B G2 input query | G2 | 6 | 3 | 2.237 ms |
| **B G2 auxiliary query** | **G2** | **7,821** | **9** | **152.731 ms** |

这使研究对象从笼统的“G2 很慢”收敛为更具体的“Output 电路中辅助变量对应的 B-G2 MSM 路径”。它并不表示每一种 G2 MSM 都慢；例如只有 6 个标量的 B-G2 input query，耗时约 2.237 ms。

## 6. B-G2 auxiliary：内部阶段成本

在 `sapling_output_msm_stages_1threads.log` 中，重复的八次 MSM 调用序列里，`call_id=8,16,24,32,40` 对应 B-G2 auxiliary query。对这五条深度插桩记录的阶段计时进行汇总：

| call_id | Bucket fill (ms) | Bucket sum (ms) | inner elapsed (ms) | Fill 占比 | Sum 占比 |
|---:|---:|---:|---:|---:|---:|
| 8 | 129.89 | 52.72 | 185.96 | 69.85% | 28.35% |
| 16 | 135.45 | 53.90 | 191.90 | 70.58% | 28.09% |
| 24 | 124.61 | 50.84 | 177.90 | 70.04% | 28.58% |
| 32 | 110.67 | 44.78 | 157.56 | 70.24% | 28.42% |
| 40 | 110.72 | 45.72 | 158.65 | 69.79% | 28.82% |
| **按计时合计加权占比** | **611.34** | **247.96** | **871.97** | **约 70.11%** | **约 28.44%** |

这组比例以五次 `inner_elapsed_ms` 合计为分母。它来自更重的深度插桩：可用于比较该调用内部阶段的相对结构，不用于报告官方 Prove 延迟，也不意味着优化 Bucket fill 就会产生同等比例的端到端提速。Bucket fill 是当前观测中最大的候选成本段；真正的优化收益仍需未来受控地实现和测量。

此前报告的约 73%–74% 是深度插桩中多个 MSM 调用的内部阶段计时汇总；本节约 70.11% 专指 B-G2 auxiliary 这一条调用，两者统计范围不同，不能混用。

## 7. 工程调用链与研究边界

`docs/zcash_sapling_flow.md` 记录了从交易构建、Sapling bundle、SpendProver / OutputProver，到 Groth16 proof generation 与验证的关键源码调用链。当前实验直接调用证明和检查 API，并未复现完整钱包交易构建、签名、网络处理或全部共识验证。

### 已得到的阶段性结论

1. 真实 Sapling Spend / Output 证明生成与验证可以运行，且每个指定正式批次均 5/5 验证通过。
2. Spend 的约束规模约为 Output 的 12.62 倍；本次正式实验中，Spend 的 Prove 中位时间约为 Output 的 6.58 倍。耗时不与约束数量简单成比例。
3. MSM 主导成本的判断获得了已测 Output 单线程真实负载的支持，但尚不能推广到 Spend 或所有 Groth16 电路。
4. Output 的 B-G2 auxiliary 是当前八次调用中耗时最高的路径；其深度插桩中 Bucket fill 约占该调用内部计时的 70.11%，是下一阶段优先研究的成本段候选。
5. 本阶段完成了基线建立和候选热点定位，没有实现或验证算法优化。

### 留待后续阶段

- 对 Sapling Spend 做同口径、调用级 G1/G2 profile；
- 设计受控的冷／热测量，并增加内存重复样本；
- 若进行优化，分别衡量阶段局部耗时和完整 Prove 的端到端变化；
- 在实验方案中固定 commit、工具链、线程数和测量口径，避免混合正式数据与探索性记录。

## 8. 原始数据与复现

原始 CSV 和日志保存在 `experiments/raw/`；汇总表与图保存在 `results/tables/`、`results/figures/`。参数文件存放于仓库之外的 `D:\Research\zcash-params\`，不可提交至 Git。

重新生成汇总表与图表可运行：

```powershell
python scripts/summarize_engineering.py
```

该脚本只处理已有数据，不会重新运行证明实验。运行任何 proving 程序前，应先检查它是否会向 raw CSV 追加新记录。参数元数据、原始测量和探索性批次均应保留，不要为得到更整齐的数字而删除异常记录。
