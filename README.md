# Zcash Sapling Engineering Study

A reproducible engineering study on the Groth16 zkSNARK proving pipeline used in Zcash Sapling.

This repository focuses on understanding the implementation details, performance characteristics, and engineering structure of a real-world SNARK system.

The goal is not to optimize the system directly at this stage, but to establish a reliable experimental baseline for future research on zkSNARK proving cost reduction.

---

## 1. Research Motivation

zkSNARK systems provide short and efficient zero-knowledge proofs, but the prover side usually introduces significant computational overhead.

Modern SNARK systems mainly face challenges including:

- Large proving time
- High memory consumption
- Expensive elliptic curve operations
- Scalability problems for large circuits

This project studies a practical Groth16 implementation through the Zcash Sapling engineering ecosystem.

The main objectives are:

1. Understand the complete proving pipeline.
2. Reproduce proof generation experiments.
3. Measure important performance metrics.
4. Identify expensive components inside the prover.
5. Provide a baseline for future optimization research.

---

## 2. Experimental Environment

Hardware:

```
CPU:
Intel Core i7-14700

Logical processors:
28

Memory:
32 GB
```

Software:

```
OS:
Windows 11

Rust:
1.98.1

Build mode:
release

Curve:
BLS12-381

SNARK:
Groth16

Library:
bellman
```

---

## 3. Project Structure

```
zcash-sapling-engineering/

├── experiments/
│   └── raw/
│       ├── logs/
│       │   └── raw experimental logs
│       │
│       └── csv/
│           └── extracted experimental data
│

├── results/
│   ├── tables/
│   │   └── summarized experiment results
│   │
│   └── figures/
│       └── generated figures
│

├── scripts/
│   └── data processing scripts
│

└── README.md
```

---

## 4. Current Achievements

### 4.1 Groth16 Proof Generation

Successfully reproduced the Sapling Groth16 proving workflow.

The experiment verifies:

- Circuit synthesis
- Witness generation
- Proof generation
- Proof verification

Example result:

```
verified=true
proof_bytes=192
```

---

## 5. Multi-thread Proving Experiment

The proving time was measured under different worker thread configurations.

Median proving time:

| Threads | Prove Time |
|---------|------------|
| 1       | 512.951 ms |
| 2       | 270.691 ms |
| 4       | 165.925 ms |
| 8       | 99.003 ms |
| 20      | 89.835 ms |

Observation:

Increasing parallelism significantly reduces proving time.

However, the speedup becomes limited after increasing the number of threads, indicating that some components are not fully parallel scalable.

---

## 6. MSM Profiling

The prover internally relies heavily on Multi Scalar Multiplication (MSM).

The project adds instrumentation to observe:

- MSM task submission
- Worker task start delay
- MSM execution time
- Internal stages

Collected information includes:

```
BELLMAN_MSM_SUBMIT_RETURN

BELLMAN_MSM_TASK_START

BELLMAN_MSM_PROFILE

BELLMAN_MSM_STAGE_PROFILE
```

Example:

```
BELLMAN_MSM_STAGE_PROFILE

chunks=85

parallel_chunks_wall_ms

sequential_chunks_ms

bucket_sum_sum_ms

inner_elapsed_ms
```

---

## 7. Current Observations

### 7.1 Parallel Scaling

The proving pipeline benefits from multi-thread execution.

However:

- 1 → 8 threads provides significant improvement.
- 8 → 20 threads improvement becomes smaller.

This suggests that:

- Some parts are parallelizable.
- Some parts remain sequential or have synchronization overhead.

---

### 7.2 MSM Behavior

Initial profiling shows:

- MSM execution dominates important parts of proving.
- Different query types have different costs.
- G2 MSM operations are generally more expensive than G1 MSM operations.

However, these observations are only baseline measurements.

No optimization is proposed at this stage.

---

## 8. Research Direction

Future work will focus on:

1. Understanding the complete Groth16 proving pipeline.

2. Studying:

- MSM
- FFT
- Polynomial operations
- CRS structure

3. Comparing different SNARK systems:

- Groth16
- PLONK
- Halo2

4. Investigating possible directions for reducing:

- Prover computation cost
- Memory usage
- Proof generation overhead

---

## 9. Current Status

Completed:

- [x] Build environment setup
- [x] Sapling engineering reproduction
- [x] Groth16 proof generation
- [x] Verification testing
- [x] Thread scaling experiment
- [x] MSM instrumentation
- [x] Raw experiment collection

Next steps:

- Study Zcash Sapling architecture.
- Analyze circuit size and CRS size.
- Understand practical deployment scenarios.
- Build a complete SNARK performance evaluation framework.

---

## 10. Notes

This repository is an experimental baseline for academic research.

The current goal is understanding and measurement rather than direct optimization.