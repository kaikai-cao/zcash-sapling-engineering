# Sapling Prover 性能分析阶段总结

- 日期：2026-10-11
- 项目：zcash-sapling-engineering
- Git Revision：1e599813e1cf15d50454e2d7517363c8f7ba626
- 构建模式：Release
- Rayon线程：1
- 分析对象：Sapling Spend / Output Groth16 Prover

---

# 1. 研究目标

本阶段目标是在真实 Zcash Sapling 工程环境下，对基于 Groth16 的证明生成流程进行复现和性能分析。

主要任务：

1. 建立可重复的 Sapling Spend / Output 证明生成实验基线；
2. 分析 Groth16 Prover 内部计算阶段；
3. 通过源码级 profiling 定位主要性能瓶颈；
4. 为后续 SNARK Prover 优化研究提供实验依据。

重点关注：

- Prover 端计算成本；
- MSM（Multi-Scalar Multiplication）性能；
- 不同证明类型之间的性能差异。

---

# 2. 实验环境

## 软件环境

| 项目 | 配置 |
|---|---|
| 操作系统 | Windows 11 |
| 编程语言 | Rust |
| 构建模式 | Release |
| Rayon线程 | 1 |
| 证明系统 | Groth16 |
| 曲线 | BLS12-381 |
| 工程 | zcash-sapling-engineering |

## 主要依赖

- sapling-crypto 0.9.0
- bellman 0.15.0
- groth16 0.2.0

源码位置：

```
vendor/bellman/src/multiexp.rs
```

---

# 3. Sapling Prover 基线测试

## 实验对象

选择 Sapling 中两类典型证明：

- Spend Proof
- Output Proof

记录指标：

- Prove 时间；
- Verify 时间；
- Proof Size。

---

# 4. 基线实验结果

## Spend

| 指标 | 结果 |
|---|---:|
| Prove 中位数 | 6858 ms |
| Verify 中位数 | 5 ms |
| Proof Size | 192 bytes |

---

## Output

| 指标 | 结果 |
|---|---:|
| Prove 中位数 | 885 ms |
| Verify 中位数 | 2 ms |
| Proof Size | 192 bytes |

---

## 初步观察

实验结果表明：

1. Groth16 Proof Size 保持固定，符合短证明特点；
2. Verify 成本明显低于 Prove；
3. Prover 是主要性能压力来源。

因此后续分析重点放在证明生成阶段。

---

# 5. Groth16 Prover 内部阶段分析

为了避免只观察端到端时间，本阶段进一步分析 Groth16 Prover 内部流程。

通过源码插桩记录：

- MSM调用次数；
- exponent数量；
- window参数；
- 单次MSM执行时间。

插桩位置：

```
vendor/bellman/src/multiexp.rs
```

新增日志：

```
BELLMAN_MSM_PROFILE
BELLMAN_MSM_SUBMIT_PROFILE
```

保持实验条件一致：

- Release构建；
- 单线程；
- 相同源码版本。

---

# 6. MSM 性能剖析方法

MSM累计耗时定义：

> 每轮证明过程中所有 BELLMAN_MSM_PROFILE 记录的 elapsed_ms 之和。

MSM占比定义：

> MSM累计耗时 / Prove时间。

---

# 7. Spend / Output 同源码 MSM 对照

## Spend

| Run | Prove(ms) | MSM(ms) | MSM / Prove |
|---:|---:|---:|---:|
|1|6886.682|5932.749|86.15%|
|2|6865.663|6002.708|87.43%|
|3|6755.116|5880.978|87.06%|
|4|6858.210|5984.795|87.26%|
|5|6782.222|5888.293|86.82%|

汇总：

| 指标 | 结果 |
|---|---:|
| Prove 中位数 | 6858.210 ms |
| MSM累计耗时中位数 | 5932.749 ms |
| MSM占比中位数 | 87.06% |

---

## Output

| Run | Prove(ms) | MSM(ms) | MSM / Prove |
|---:|---:|---:|---:|
|1|553.271|477.688|86.34%|
|2|507.648|473.712|93.32%|
|3|885.491|850.428|96.04%|
|4|995.708|935.886|93.99%|
|5|1051.759|980.647|93.24%|

汇总：

| 指标 | 结果 |
|---|---:|
| Prove 中位数 | 885.491 ms |
| MSM累计耗时中位数 | 850.428 ms |
| MSM占比中位数 | 93.32% |

---

# 8. 当前性能瓶颈判断

实验结果显示：

对于 Sapling Groth16 Prover：

- MSM 占据 Prove 阶段主要计算时间；
- Spend 和 Output 虽然证明规模不同，但性能结构一致；
- MSM 是当前最值得进一步研究的优化对象。

当前阶段结论：

> Sapling Groth16 Prover 的主要性能瓶颈位于 MSM 阶段，后续优化研究应优先围绕 MSM 展开。

---

# 9. 当前阶段完成内容

本阶段已经完成：

- [x] Sapling 工程环境搭建；
- [x] 参数文件验证；
- [x] Spend / Output Proof生成与验证；
- [x] Groth16 Prover流程分析；
- [x] bellman MSM源码定位；
- [x] MSM调用级profiling；
- [x] Spend / Output 同源码性能对照。

---

# 10. 当前尚未解决的问题

当前工作完成了第一层瓶颈定位：

> Prover慢在哪里？

答案：

> MSM。

但仍未完成第二层分析：

> MSM具体慢在哪里？

后续需要进一步研究：

- Pippenger MSM内部阶段；
- bucket累加；
- window参数选择；
- 多线程调度；
- cache与内存访问行为。


## Profiling Impact Analysis

A profiling-disabled validation run was performed
to verify the correctness of the measured performance.

The profiling-disabled implementation achieved:

- median proving time: ~7030 ms
- verification time: ~5.3 ms
- successful verification: 5/5

Compared with the profiling-enabled build,
the absolute proving time differs significantly.

This indicates that the current profiling instrumentation
changes internal execution behavior, especially around the
Bellman worker/MSM scheduling path.

Therefore:

- profiling-enabled results are used for internal stage
  attribution and bottleneck localization;
- profiling-disabled results are used as the performance
  reference baseline.

No algorithmic optimization has been introduced.
The current objective is only identifying dominant costs.

---

# 11. 后续研究方向

## 方向一：MSM算法优化

分析：

- window策略；
- bucket组织方式；
- scalar分布特点。

目标：

降低MSM计算成本。

---

## 方向二：并行化优化

分析：

- 多线程扩展效率；
- task调度开销；
- 并行粒度。

目标：

提高Prover吞吐。

---

## 方向三：内存优化

分析：

- bucket存储；
- cache locality；
- streaming MSM。

目标：

降低大规模证明中的内存压力。

---

# 12. 总结

本阶段完成了从理论学习到真实工程分析的迁移。

研究路线：

```
SNARK理论学习
        ↓
Groth16协议理解
        ↓
Sapling工程复现
        ↓
Prover性能测试
        ↓
源码级profiling
        ↓
MSM瓶颈定位
        ↓
后续优化研究
```

实验结果证明：

> 在 Sapling Groth16 Prover 中，MSM 是证明生成阶段的主要性能瓶颈，为后续针对 SNARK Prover 效率优化提供了明确方向。