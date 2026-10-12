# Vendor Dependencies

This directory contains instrumented versions of selected dependencies used for performance analysis.

## Purpose

The vendored dependencies are included to enable internal profiling of the Sapling proving workflow.

The modifications are limited to:

- Performance measurement hooks
- Execution tracing
- Profiling information collection

## Design Principle

The instrumentation does not modify:

- Cryptographic algorithms
- Proof system logic
- Protocol behavior

The generated proofs and verification semantics remain unchanged.

## Reason

Some performance characteristics cannot be observed through external benchmarking alone.

Instrumenting internal components allows this project to analyze:

- Prover stage cost
- MSM contribution
- Cryptographic operation overhead

The vendor directory exists only for experimental analysis and reproducibility.