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
## `bls12_381/` — Phase D experiment (2026-11-02)

A verbatim copy of `bls12_381` 0.9.0 from crates.io with **one addition** in
`src/g1.rs`: the `G1BucketXyzz` type (XYZZ bucket coordinates) plus its
`add_mixed_assign` / `add_mixed_assign_unchecked` / `add_xyzz_assign` /
`double_assign` / `into_projective` methods, and the `pub use` in `src/lib.rs`.
Nothing else in the crate was modified; `rs`-level diffs against the published
0.9.0 are limited to those two files. `benches/` and `tests/` are kept as
shipped but are not exercised here.

It is wired in only through `experiments/prover-smoke`'s `[patch.crates-io]`,
so the dependency graph still holds exactly one BLS12-381.

Why a local copy was needed: `G1Projective`'s coordinates and the `Fp` type are
`pub(crate)`, so an external crate cannot read them; an XYZZ bucket has to live
inside the curve crate.

Status: **experiment closed with NO_GO** — see
`experiments/metadata/sapling_msm_phase_d_xyzz_results_20261102.md`.
`G1BucketXyzz` is not used by any production path.
