# zcash-sapling-engineering

A reproducible engineering study of Zcash Sapling zk-SNARK proving performance.

本项目用于分析 Zcash Sapling 证明系统在实际工程实现中的性能开销，重点关注 Groth16 prover 端的计算瓶颈，包括：

* Prover pipeline 分阶段耗时
* MSM（Multi-Scalar Multiplication）调用分布
* Bellman Groth16 内部 MSM 开销
* Spend / Output 两类证明流程对比
* 后续潜在优化方向分析

当前阶段目标：

> 在不修改密码协议正确性的前提下，通过工程剖析定位 Sapling zk-SNARK proving 过程中的主要成本来源，为后续压缩证明成本、降低计算开销的研究提供实验基础。

---

## 1. Environment

实验环境：

| 项目         | 配置                        |
| ---------- | ------------------------- |
| OS         | Windows 11                |
| Rust       | 1.88.0                    |
| Build      | Release                   |
| Curve      | Jubjub / Sapling Groth16  |
| Thread     | Rayon controlled          |
| Repository | zcash-sapling-engineering |

主要依赖：

```toml
sapling-crypto = 0.9.0
bellman = 0.15.0
groth16 = 0.2.0
```

---

## 2. Repository Structure

```text
zcash-sapling-engineering
│
├── experiments
│   ├── metadata
│   │   └── 实验说明、分析记录
│   │
│   ├── raw
│   │   ├── csv
│   │   │   └── 原始实验数据
│   │   │
│   │   └── logs
│   │       └── profiling 日志
│   │
│   └── figures
│       └── 实验结果图
│
├── prover-smoke
│   └── Sapling Spend / Output 测试程序
│
├── vendor
│   ├── bellman
│   └── groth16
│
└── README.md
```

---

# 3. Completed Experiments

## 3.1 Sapling Output Prover Baseline

完成 Sapling Output proof generation 基准测试。

测试内容：

* 参数读取
* VK preparation
* proof generation
* proof verification
* proof size

实验结果：

```text
Output proof:

prove:
    millisecond level profiling completed

verify:
    ~2 ms range

proof size:
    192 bytes
```

验证结果：

```text
verified = true
```

---

# 4. Groth16 Prover Pipeline Analysis

通过源码插桩分析 Groth16 prover 内部阶段。

主要观察：

```text
Circuit synthesis
        |
        v
QAP construction
        |
        v
FFT / polynomial operations
        |
        v
MSM
        |
        v
Proof assembly
```

其中 MSM 是主要计算热点。

---

# 5. MSM Profiling

## Instrumentation

修改位置：

```text
vendor/bellman/src/multiexp.rs
```

增加：

```text
BELLMAN_MSM_PROFILE
BELLMAN_MSM_SUBMIT_PROFILE
```

记录：

* exponent_count
* density_map_size
* window size
* task scheduling delay
* MSM execution time

示例：

```text
BELLMAN_MSM_PROFILE

exponent_count=98638
window=12
elapsed_ms=xxx
```

---

# 6. Spend / Output Same Source MSM Comparison

实验目的：

在相同源码、相同 Release 构建、单线程环境下，对比 Sapling Spend 与 Output 的 MSM 开销。

实验条件：

```text
Build:
    Release

Rayon:
    1 thread

Repeat:
    5 runs

Algorithm modification:
    none
```

---

## Spend Result

```text
Median prove time:

6858.210 ms


Median MSM accumulated time:

5932.749 ms


MSM / Prove:

87.06%
```

---

## Output Result

```text
Median prove time:

885.491 ms


Median MSM accumulated time:

850.428 ms


MSM / Prove:

93.32%
```

---

## Observation

当前实验支持：

```text
MSM occupies the majority of Sapling proving time.
```

因此：

* MSM 是当前最值得深入分析的性能对象；
* 优化 MSM 可能影响主要 prover 成本；
* 但当前实验不能直接推出优化收益。

注意：

```text
MSM profiling time
!=
complete optimization potential
```

---

# 7. Current Research Findings

目前得到的阶段性认识：

## 1. 性能瓶颈定位

Sapling Groth16 prover 中：

```text
MSM
|
+-- large scalar multiplication workload
|
+-- dominates proving cost
```

因此后续研究重点：

* MSM 算法优化
* MSM 并行策略
* 内存访问优化
* 大规模证明场景优化

---

## 2. Spend vs Output

实验发现：

```text
Spend:

Prove ≈ seconds level

Output:

Prove ≈ sub-second level
```

二者差异主要来自：

* witness规模
* circuit复杂度
* MSM规模

---

# 8. Reproducibility

运行示例：

```powershell
cargo run --release --bin spend_prover_smoke
```

Output：

```text
SPEND_PROOF_EXPERIMENT=PASS
```

检查实验数据：

```powershell
Get-ChildItem experiments/raw
```

---

# 9. Current Limitations

当前实验仍未完成：

* MSM 内部 bucket 分布分析
* 不同 window 参数影响
* MSM memory footprint 分析
* FFT 与 MSM 的精细比例分析
* 优化方案验证

因此目前结论：

```text
已完成性能瓶颈定位，
尚未进入优化阶段。
```

---

# 10. Next Research Direction

下一阶段计划：

1. 继续分析 bellman MSM 实现细节

重点：

```text
multiexp
    |
    +-- bucket accumulation
    |
    +-- window selection
    |
    +-- parallel scheduling
```

2. 建立优化基线：

比较：

```text
baseline
    |
    v
modified MSM implementation
    |
    v
performance evaluation
```

3. 最终目标：

探索：

```text
How to reduce SNARK proving cost
```

---

# 11. Experimental Philosophy

本项目遵循：

```text
Measure first,
Optimize second.
```

所有优化必须回答：

1. 优化对象是什么？
2. 当前占总代价多少？
3. 优化后收益是多少？
4. 是否引入额外成本？

---

## Status

Current status:

```text
Sapling Spend / Output
        |
        v
Groth16 prover profiling completed
        |
        v
MSM identified as primary target
        |
        v
Optimization research preparation stage
```
