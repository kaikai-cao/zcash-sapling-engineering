# Sapling Spend Groth16 Prover Bottleneck Analysis Report

Date: 2026-10-11

## 1. Research Objective

本阶段目标是基于 Zcash Sapling Spend Groth16 proving 流程，
建立可复现的性能分析环境，并定位证明生成过程中的主要性能瓶颈。

重点关注：

- Prover 时间组成
- MSM / FFT 等核心计算开销
- 多线程扩展能力
- 后续优化方向


---

## 2. Experimental Environment

Hardware:

- CPU: Intel i7-14700
- Physical cores: 20
- Memory: 32GB


Software:

- Rust release build
- Sapling crypto
- bellman 0.15.0
- groth16 0.2.0


Benchmark:

- Sapling Spend circuit
- Groth16 proving
- 5 repetitions per configuration


---

## 3. Profiling Method

为了分析 Groth16 Prover 内部开销，
对以下模块进行源码级插桩：

- groth16 prover.rs
- bellman multiexp.rs
- bellman multicore.rs


记录：

- circuit synthesis
- QAP FFT preparation
- MSM execution
- worker scheduling
- proof assembly


---

## 4. Prover Stage Breakdown

典型证明生成时间：

prove:

约 3.4s


其中：

| Stage | Time |
|---|---:|
| circuit synthesis | ~100ms |
| QAP FFT | ~380ms |
| MSM related operations | ~2900ms |
| other assembly | ~600ms |


实验表明：

MSM 是证明生成过程中的主要计算成本。


---

## 5. MSM Breakdown


主要 MSM 调用：

| Operation | Median Time |
|---|---:|
| H_query_G1 | 1446ms |
| B_G2_aux | 591ms |
| L_query_G1 | 399ms |
| A_aux_G1 | 278ms |
| B_G1_aux | 211ms |


MSM 总时间占 create_proof_body：

约 85%以上。


---

## 6. Thread Scaling Experiment


测试线程：

1,2,4,8,16,20


结果：

|Threads|Median Prove|
|-|-:|
|1|3499ms|
|2|1831ms|
|4|1008ms|
|8|770ms|
|16|591ms|
|20|596ms|


最高加速：

约 5.9x


说明：

MSM 已经能够充分利用 CPU 并行能力。

继续增加线程收益有限。


---

## 7. Bottleneck Conclusion


当前实验确认：

1. Sapling Spend Groth16 Prover 的主要瓶颈为 MSM；

2. MSM 成本主要来源于大量标量乘计算；

3. 多线程优化已经接近硬件限制；

4. 后续优化方向应从：

- 减少 MSM 输入规模
- 优化 MSM 算法
- 降低标量乘成本
- 改进证明系统结构

等方向展开。


---

## 8. Future Work


下一阶段考虑：

- MSM 输入压缩
- MSM batch optimization
- memory-efficient proving
- alternative proving systems comparison
