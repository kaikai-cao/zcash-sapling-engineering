# Zcash Sapling / Groth16 工程阶段总结

**阶段定位：** 真实工程基线已建立；完整研究计划尚未结项。  
**实验日期：** 2026-10-10  
**源码版本：** `sapling-crypto 0.9.0`，commit `88a7946b4a3066787776e11f0a502654167e022d`  
**正式基线配置：** Windows 11，Intel Core i7-14700，Rust 1.98.1（本地记录），release，`RAYON_NUM_THREADS=1`

## 1. 工程规模与参数

| 指标 | Sapling Spend | Sapling Output |
|---|---:|---:|
| 约束数量 | 98,777 | 7,827 |
| 辅助变量 | 98,638 | 7,821 |
| 估算 domain size | 131,072 | 8,192 |
| 参数文件大小 | 45.737 MiB | 3.426 MiB |
| 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |

约束和变量来自 Counting ConstraintSystem；domain size 是按约束数向上取整到 2 的幂得到的估算值，而非直接读取的域大小。参数文件大小不等价于理论 CRS、proving key 或 verifying key 的独立大小。

## 2. 正式性能基线

正式汇总只选择下列两个批次，每种电路各有 5 次证明和验证测量。

| 指标 | Spend | Output |
|---|---:|---:|
| 正式 batch ID | `1791613854129` | `1791549582046` |
| Prove 中位数 | 3,385.716 ms | 514.853 ms |
| Verify 中位数 | 2.790 ms | 2.150 ms |
| Proof size | 192 bytes | 192 bytes |
| 验证成功 | 5/5 | 5/5 |

Prove 计时不包含参数加载、VK 准备与见证构造；Verify 只表示实验中单次证明检查的耗时，不是完整 Zcash 交易的端到端验证时间。

参数元数据程序分别测得 Spend 24,326.502 ms、Output 1,774.506 ms 的读取与验证耗时，但每种参数只有一次测量。这些数据不能作为稳定的冷／热加载统计。

## 3. 内存和探索性首次／重复调用观测

此前每种电路各有一次整进程 Peak Working Set 观测：Spend 101.31 MiB、Output 22.22 MiB。它包括参数加载、验证、证明与验证过程，不是 Prove 单独使用的内存；重复内存测量尚未完成。

后续首次／重复调用实验发现运行环境存在波动：部分 Output 进程后续证明与验证时间同时明显升高；部分 Spend 补测的参数加载和证明时间也显著高于正式基线。所有记录批次的证明检查均通过，但这些异常不能解释为算法性能变化。系统 CPU 采样间隔较稀疏，且是整机指标；当前证据无法确定是微信、CPU 频率、电源管理或其他系统因素导致。

因此，这些补充批次只保留为探索性数据，不纳入正式性能汇总。首次调用发生在参数和输入准备之后，后续调用也没有控制操作系统文件缓存，**当前还不能宣称完成了严格的冷／热缓存对照**。

## 4. 工程理解与研究边界

已跑通 Spend / Output 真实证明生成与检查，记录电路规模、参数哈希和大小，生成汇总 CSV 与图表，并梳理 Zcash 交易构造到 Sapling Prover / Groth16 的关键源码调用链。当前实验直接调用证明 API，不是完整钱包交易构造与共识验证测试。

已完成 Frozen synthetic Groth16 baseline 与真实 Sapling 的第一轮规模／成本结构对照，记录在 `docs/baseline_comparison.md` 和 `results/tables/baseline_cost_structure_comparison.csv`。合成基线的一次带剖析记录中，MSM 累计耗时占 Prove 约 91.60%；该比例不能直接推广到 Sapling。

Sapling Output 的单线程剖析已找到具体瓶颈证据：两份较轻量日志的后续运行中，8 次 MSM 调用耗时合计约占 Prove 的 93.2%–93.4%。按源码调用顺序映射后，单次耗时最高的是 B-G2 auxiliary query（中位约 152.7 ms），其次是 H query（约 129.1 ms）；更细粒度日志表明 bucket fill 约占 MSM 内部阶段计时的 73%–74%，但该细粒度插桩会明显增加总运行时间，因此只用于内部成本定位。

尚未完成：
- 严格定义且受控的冷／热运行基准；
- 可报告波动范围的重复内存测量；
- 对 Sapling Spend 完成同口径阶段剖析，确认相同调用排序是否成立；多线程下不能直接累加重叠的调用 elapsed 来算占比。

## 5. 面向导师的三句话

**工程事实：** Sapling Spend 约有 98,777 个约束、参数文件约 45.737 MiB；Output 约有 7,827 个约束、参数文件约 3.426 MiB。

**性能事实：** 在固定 Sapling 源码版本、release、单线程设置下，正式批次的 Prove 中位数分别为 3385.716 ms 和 514.853 ms，Verify 中位数分别为 2.790 ms 和 2.150 ms；两者证明大小均为 192 bytes。

**研究结论：** 已有证据支持 MSM 主导当前测得的 Sapling Output 单线程证明路径，且 bucket fill 是优先调查的内部成本段；这一结论尚不能直接推广到 Spend 或多线程模式。下一步应完成 Spend 同口径剖析和 G1/G2 调用映射，再依据实际成本决定优化方向；冷／热测量与重复内存统计仍作为基线完善项。
