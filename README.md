# Zcash Sapling Engineering

A reproducible performance analysis project for studying the bottlenecks of Zcash Sapling zk-SNARK proof generation.

The purpose of this project is to reproduce the Sapling proving workflow, measure the cost of different components, and identify potential performance bottlenecks.

This project focuses on **performance analysis and bottleneck identification**, not on optimizing the existing Sapling implementation.

---

# 1. Research Motivation

Zcash Sapling uses zk-SNARKs to provide privacy-preserving transactions.

Although zk-SNARK verification is highly efficient, proof generation remains computationally expensive. The proving process involves multiple stages, including:

- Circuit construction
- Witness generation
- Polynomial computation
- FFT operations
- Multi-Scalar Multiplication (MSM)
- Elliptic curve operations

Understanding the cost distribution of these components is an important step toward future research on improving zk-SNARK scalability.

This repository provides an experimental framework for analyzing the performance characteristics of the Sapling proving process.

---

# 2. Research Objective

The main objective of this project is:

> Build a reproducible experimental baseline and identify the dominant computational costs in Zcash Sapling proof generation.

The current research questions are:

## RQ1: What contributes most to Sapling proving cost?

Analyze the internal stages of proof generation and measure their execution time.

## RQ2: Which cryptographic operations dominate the workload?

Investigate expensive operations such as:

- Multi-Scalar Multiplication
- Elliptic curve operations
- Polynomial-related computation

## RQ3: How does the proving process scale?

Study the influence of:

- Circuit workload
- Thread parallelism
- Cryptographic primitive scaling

---

# 3. Background

A simplified Sapling proving workflow can be represented as:

```
Transaction Circuit
        |
        v
Circuit Synthesis
        |
        v
Witness Generation
        |
        v
Polynomial Construction
        |
        v
FFT Processing
        |
        v
MSM Computation
        |
        v
Proof Generation
```

The goal of this project is not to modify this workflow, but to understand where computational resources are consumed.

---

# 4. Research Workflow

The experimental workflow consists of several stages.

## Stage 1: Environment Preparation

Establish a reproducible Sapling development environment.

Tasks include:

- Rust toolchain setup
- Dependency verification
- Build configuration
- Runtime environment recording

---

## Stage 2: Parameter Validation

Verify Sapling proving parameters before experiments.

Validation includes:

- Parameter file integrity checking
- Cryptographic hash verification
- Recording parameter metadata

All validation information is stored under:

```
experiments/metadata/
```

---

## Stage 3: Baseline Benchmark

Measure the basic performance characteristics of Sapling proof generation.

Collected metrics include:

- Proving time
- Verification time
- Parameter loading cost
- Thread scaling behavior

---

## Stage 4: Internal Profiling

Analyze the internal execution stages of proof generation.

The profiling focuses on:

- Circuit synthesis
- Polynomial operations
- FFT-related computation
- MSM operations

---

## Stage 5: Bottleneck Analysis

Combine benchmark results and profiling data to identify dominant cost components.

The current goal is to provide evidence for:

- Where proving time is spent
- Which operations deserve further investigation
- Potential directions for future optimization research

---

# 5. Experimental Environment

Experiments are performed under a controlled environment.

## Hardware

Example:

```
CPU:
Memory:
Operating System:
```

## Software

```
Rust:
Build mode: release
Dependency versions:
```

Unless otherwise specified, experiments use optimized release builds.

---

# 6. Repository Structure

```
zcash-sapling-engineering/

├── experiments/
│   ├── raw/
│   │   └── csv/
│   │
│   └── metadata/
│
├── results/
│   ├── tables/
│   └── figures/
│
├── scripts/
│
├── vendor/
│
└── README.md
```

---

# 7. Experimental Data Organization

## Raw Data

All original measurements are stored in:

```
experiments/raw/
```

Raw data is preserved to ensure reproducibility and prevent loss of experimental evidence.

Examples include:

- Benchmark measurements
- Profiling results
- Micro-benchmark outputs

---

## Result Tables

Processed experiment summaries are stored in:

```
results/tables/
```

These files provide structured summaries of measurements.

---

## Visualization Results

Generated figures are stored in:

```
results/figures/
```

Figures are used to analyze:

- Performance trends
- Stage contribution
- Scaling behavior

---

# 8. Parameter Validation

Sapling parameters are validated before running performance experiments.

The validation process records:

- Parameter source
- File size
- Hash value
- Verification result

This ensures that performance results are generated from verified cryptographic parameters.

---

# 9. Benchmark Experiments

## 9.1 Sapling Output Benchmark

Purpose:

Establish a baseline for Sapling proof generation.

Measured metrics:

- Proof generation latency
- Verification latency
- Thread scaling behavior

---

## 9.2 Sapling Spend Benchmark

Purpose:

Analyze a more realistic and computationally intensive Sapling workload.

The experiment focuses on:

- Overall proving cost
- Internal execution stages
- Dominant computation components

---

## 9.3 Prover Stage Profiling

Purpose:

Understand the contribution of different proving stages.

Profiled components include:

- Circuit synthesis
- Polynomial processing
- FFT computation
- MSM computation

---

## 9.4 MSM Analysis

Multi-Scalar Multiplication is one of the key cryptographic operations in zk-SNARK proving.

This project analyzes:

- MSM execution time
- G1/G2 computation cost
- Scaling behavior
- Parallel execution impact

The goal is to determine whether MSM represents a dominant proving cost.

---

# 10. Dependency Instrumentation

This repository contains instrumented dependencies under:

```
vendor/
```

These modifications are introduced only for performance measurement and profiling.

The instrumentation does not change:

- Cryptographic algorithms
- Protocol logic
- Proof generation semantics

The purpose is to expose internal execution information for analysis.

---

# 11. Current Findings

Current experiments provide the following observations:

- Sapling proof generation is significantly more expensive than verification.
- The majority of proving cost comes from cryptographic computation.
- MSM operations represent an important candidate contributor to prover runtime.
- Parallel execution has a significant impact on proving performance.

Further profiling is used to refine the understanding of the proving cost distribution.

---

# 12. Reproducibility

Each experiment records:

- Source version
- Environment information
- Parameter information
- Execution command
- Raw measurements

The repository follows the principle:

```
Raw Data
    |
    v
Experiment Processing
    |
    v
Tables and Figures
    |
    v
Performance Analysis
```

This structure allows experiments to be reproduced and conclusions to be independently verified.

---

# 13. Future Work

Future work may include:

- More detailed performance analysis
- Comparison of different proving components
- Investigation of optimization opportunities based on measured bottlenecks

The current stage focuses on understanding the system behavior and establishing a reliable experimental baseline.

---

# 14. License and Acknowledgement

This project is based on open-source Zcash Sapling-related implementations.

The repository is intended for research and educational purposes, focusing on experimental analysis of zk-SNARK proving performance.