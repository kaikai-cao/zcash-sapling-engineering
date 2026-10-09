# Zcash Sapling Engineering Study

A reproducible engineering study of the historical Sapling Groth16 proving
workflow in Zcash.

This repository is a learning and measurement project. Its purpose is to
understand how a real zero-knowledge proving system is integrated into an
engineering codebase, how its parameters and proofs are handled, and how
its costs can be measured reproducibly.

**The goal is not to optimize Sapling or claim a new proving-system improvement.**

Sapling uses Groth16. Orchard uses the Halo 2 proving system with
PLONKish arithmetization. Results from this Sapling experiment should not
be treated as benchmarks for Orchard or other proving systems.

## 1. Objectives

This project studies the following aspects of the Sapling engineering workflow:

1. Compile and run a real Sapling proof-generation example.
2. Understand the Spend and Output circuits and their parameter files.
3. Measure circuit scale, parameter size, proving time, verification time,
   and proof size.
4. Distinguish parameter loading and input preparation from proof generation.
5. Trace how Sapling proof generation and verification fit into the
   surrounding Zcash transaction workflow.
6. Compare a real engineering workload with a frozen synthetic Groth16
   baseline, while keeping their differences explicit.

The project prioritizes reproducibility and source-code understanding over
optimization.

## 2. Experimental Environment

| Item | Configuration |
|---|---|
| Operating system | Windows 11 |
| CPU | Intel Core i7-14700 |
| Logical processors | 28 |
| Memory | 32 GB |
| Rust | 1.98.1 |
| Build profile | Release |
| Curve | BLS12-381 |
| Proving system | Groth16 |
| Sapling library | `sapling-crypto` 0.9.0 |
| Bellman | 0.15.0 |
| Groth16 crate | 0.2.0 |

The Sapling source is maintained separately at:

https://github.com/zcash/sapling-crypto

The experiment uses the source revision recorded in the experiment notes.
The vendored Bellman and Groth16 sources are used for local reproducibility.

## 3. Current Results

### 3.1 Output Proof Generation and Verification

The Output smoke experiment successfully generated and verified five proofs
after restoring the experimental profiling modifications in the vendored
proving code.

| Metric | Result |
|---|---:|
| Parameter read and validation | 1807.789 ms |
| Prepared verifying-key setup | 1.009 ms |
| Input preparation | 12.091 ms |
| Median proving time | 514.853 ms |
| Median verification time | 2.150 ms |
| Serialized proof size | 192 bytes |
| Successful verifications | 5 / 5 |

The five proving times were:

`560.162, 519.158, 511.584, 507.096, 514.853 ms`

The proving-time median is 514.853 ms.

These measurements were collected in one batch with one Rayon thread.
The parameter file was read and validated once before the five proof runs.
This experiment is not yet a complete cold-versus-warm benchmark.

**Verification scope:** each generated Output proof was checked through the
Sapling Output verification context. This is not a full Zcash transaction
validation test.

The raw runs are recorded in:

- `experiments/raw/csv/sapling_output_prover_runs_release.csv`
- `experiments/raw/logs/sapling_output_after_restore_1thread.log`

### 3.2 Parameter Files

The local parameter files were checked against their expected file sizes
and BLAKE2b-512 hashes.

| Parameter file | Size in bytes | Approximate size |
|---|---:|---:|
| `sapling-spend.params` | 47,958,396 | 45.74 MiB |
| `sapling-output.params` | 3,592,860 | 3.43 MiB |

The validation results are recorded in:

`experiments/metadata/parameter_validation.csv`

The parameter files are stored outside this repository and must not be
committed to Git.

File size should not automatically be described as the size of a CRS,
proving key, or verifying key. These are distinct objects, and any reported
size must identify the object being measured.

## 4. Repository Structure

```text
zcash-sapling-engineering/
├── docs/
│   └── smoke-check.md
├── experiments/
│   ├── metadata/
│   │   └── parameter_validation.csv
│   ├── prover-smoke/
│   │   ├── Cargo.toml
│   │   └── src/
│   └── raw/
│       ├── csv/
│       └── logs/
├── results/
│   ├── figures/
│   └── tables/
├── scripts/
└── vendor/
    ├── bellman/
    └── groth16/
```

- `experiments/raw/` contains experimental runs and extracted raw data.
- `experiments/metadata/` contains parameter validation records.
- `results/tables/` contains summarized results.
- `results/figures/` contains generated plots.
- `scripts/` contains data-processing scripts.
- `vendor/` contains local copies of the proving libraries.

## 5. Reproducing the Output Experiment

The parameter files are expected at:

`D:\Research\zcash-params\`

From the repository root, run the following commands in PowerShell:

```powershell
$env:RAYON_NUM_THREADS = "1"

cargo run --release `
  --manifest-path experiments/prover-smoke/Cargo.toml 2>&1 |
  Tee-Object -FilePath experiments/raw/logs/sapling_output_after_restore_1thread.log
```

The experiment appends five rows to the raw CSV file. Check the CSV before
rerunning it if you need to preserve a clean record of each batch.

For reproducibility, record the repository commit, the Sapling source
revision, the Rust version, the thread configuration, and the parameter
file hashes alongside each formal experiment.

## 6. Exploratory MSM Profiling

Earlier experiments instrumented MSM calls, worker-task scheduling, and
internal execution stages in Bellman and Groth16.

Those artifacts are retained for educational traceability in the raw logs,
tables, figures, and analysis scripts.

However, some profiling experiments also changed the execution path for
very small MSMs. Their timings therefore must not be mixed with measurements
from the restored proving code or presented as evidence of an effective
optimization.

No general optimization conclusion is claimed by this repository.

## 7. Remaining Work

The engineering study is not yet complete.

The remaining tasks are:

- Record the actual Spend and Output circuit constraint counts, variable
  counts, and domain information where the APIs expose them.
- Add SHA-256 checksums for the parameter files and preserve the existing
  validation records.
- Measure parameter loading, proving, verification, proof size, and peak
  memory with clearly documented measurement boundaries.
- Investigate the Spend proof workflow, subject to available inputs and
  the official API.
- Document the source call paths from Sapling proving interfaces to
  Groth16 proof generation and verification.
- Compare engineering scale and cost structure with the frozen synthetic
  Groth16 baseline without treating absolute timings from different
  workloads or configurations as directly interchangeable.
- Prepare a concise final report summarizing measured facts, limitations,
  and lessons learned.

## 8. Scope and Limitations

This repository is a learning-stage engineering study of Sapling's
Groth16 implementation. It is not an implementation of Orchard or Halo 2.

The current results establish that an Output proof can be generated and
verified in the tested local environment. They do not establish that every
planned performance metric has been measured, that the full Zcash
transaction workflow has been reproduced, or that a proving optimization
has been demonstrated.

The next stage is to complete the planned measurements and source-code
analysis rather than extend the experimental optimization work.