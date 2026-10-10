# Zcash Sapling Engineering Study

A reproducible engineering study of the **Sapling Groth16** proving workflow used in Zcash. The project measures real Spend and Output circuits, parameter files, proof/verification calls, source call paths, and MSM cost structure.

> **Status:** The first real-engineering baseline is frozen. Some planned measurements remain incomplete, and no algorithmic optimization has been implemented.

- Frozen snapshot: [`sapling-engineering-baseline-v1`](https://github.com/kaikai-cao/zcash-sapling-engineering/tree/sapling-engineering-baseline-v1)
- Frozen commit: [`281f1882bd1b8347f44f485f0f5dca296edafe08`](https://github.com/kaikai-cao/zcash-sapling-engineering/commit/281f1882bd1b8347f44f485f0f5dca296edafe08)
- Advisor-facing summary: [`weekly_summary.md`](weekly_summary.md)
- Historical harness milestone `f235818` is an earlier development commit, not the current frozen repository snapshot.

## What was measured

### Circuit scale and parameter files

| Metric | Sapling Spend | Sapling Output |
|---|---:|---:|
| Constraints | 98,777 | 7,827 |
| Auxiliary variables | 98,638 | 7,821 |
| Public inputs, excluding constant one | 7 | 5 |
| Input variables, including constant one | 8 | 6 |
| Estimated domain size | 131,072 | 8,192 |
| Parameter file | 47,958,396 bytes / 45.737 MiB | 3,592,860 bytes / 3.426 MiB |

The domain size is estimated as `next_power_of_two(constraints)`, not queried directly from the runtime domain object. A parameter file's size is **not** the theoretical CRS, Proving Key, or Verifying Key size. Full SHA-256/BLAKE2b-512 digests are recorded in [`results/tables/engineering_parameters.csv`](results/tables/engineering_parameters.csv); parameter validation evidence is in [`experiments/metadata/parameter_validation.csv`](experiments/metadata/parameter_validation.csv).

### Formal proof and verification baseline

The designated release-mode formal batches use one Rayon thread and five proof/verification measurements each.

| Metric | Spend | Output |
|---|---:|---:|
| Formal batch ID | `1791613854129` | `1791549582046` |
| Prove median | 3,385.716 ms | 514.853 ms |
| Prove min / max | 3,377.138 / 3,484.750 ms | 507.096 / 560.162 ms |
| Verify median | 2.790 ms | 2.150 ms |
| Encoded proof size | 192 bytes | 192 bytes |
| Successful proof checks | 5/5 | 5/5 |

The Prove timer excludes parameter loading, verifying-key preparation, and witness/input construction. Verify measures the experiment's proof-check call, not full transaction or consensus validation.

Peak working set was observed once per circuit: Spend 101.31 MiB and Output 22.22 MiB. These are whole-process peaks covering loading, validation, proving, and verification—not Prove-only memory measurements.

### What the profiling supports

- In two lower-overhead **single-thread Output** profiles, the eight MSM-call elapsed times sum to about **93.2%–93.4%** of Prove in later runs. This is evidence for the measured Output path, not proof that Spend or every Groth16 circuit has the same cost share.
- In the measured single-thread Output query mapping, **B-G2 auxiliary** is the slowest individual MSM call (profile-size median about 152.731 ms). A deeper-instrumentation analysis attributes about **70.11% of that call's internal elapsed total** to bucket fill. Heavy instrumentation changes absolute proving latency, so these values identify a candidate stage rather than predict end-to-end speedup.
- A subsequent exploratory Spend profile was collected in the separate local worktree `D:\Research\zcash-sapling-engineering-msm-profile` (batch `1791634015130`). Its five-run Prove median was **8,020.464 ms**; the median per-run sum of eight MSM-call elapsed times was **87.62% of Prove**. The five proofs verified, but this heavily instrumented run is not a replacement for the formal 3,385.716 ms baseline. Its raw files are not part of the frozen snapshot.
- Two separate five-run Output thread experiments measured 1→20 thread median Prove changes of 514.784→78.851 ms (**6.53x**) and 512.951→89.835 ms (**5.71x**). These are different batches/measurement paths; do not combine them into a universal speedup figure.
- Worker task-start logging shows a single-thread B-G1 auxiliary synchronous fallback in 5/5 samples, with median submit-stage elapsed around 326.755 ms in that specific experiment. This is an additional scheduling-path clue to investigate, not a proven root cause. Under multiple threads, per-call times overlap and must not be summed to calculate MSM share.

Detailed cost-structure comparison: [`docs/baseline_comparison.md`](docs/baseline_comparison.md). Source call path: [`docs/zcash_sapling_flow.md`](docs/zcash_sapling_flow.md).

## Plan completion: what remains open

- [x] Run real Sapling Spend and Output proving and verification.
- [x] Record constraints, variables, estimated domain size, parameter file sizes/hashes, and single-observation load/validation timing.
- [x] Collect five formal proof/verification samples for each circuit and keep exploratory data separate.
- [x] Document the source call path and compare against the frozen synthetic baseline without claiming an apples-to-apples speed contest.
- [x] Profile Output MSM calls and identify a single-thread candidate stage.
- [x] Publish an advisor-facing stage summary and freeze the snapshot.
- [ ] Complete a controlled cold-versus-warm protocol.
- [ ] Repeat peak-memory measurements to observe variability.
- [ ] Collect an equivalent Spend G1/G2/MSM call-level profile.
- [ ] Bind every future experimental batch to its exact local engineering commit/worktree revision.

PK/VK sizes were not independently measured; separating them was conditional on feasibility.

## Reproducing the measurements

### Prerequisites

The harness uses an external sibling checkout of `sapling-crypto` and parameter files outside this repository. For the original Windows layout, the expected paths are:

- Repository: `D:\Research\zcash-sapling-engineering`
- Sapling source: `D:\Research\zcash-sapling-crypto`, pinned to commit `88a7946b4a3066787776e11f0a502654167e022d`
- Parameter files: `D:\Research\zcash-params\sapling-spend.params` and `D:\Research\zcash-params\sapling-output.params`

First-time setup (run from `D:\Research`; clone the engineering repository only if it is not already present):

```powershell
if (-not (Test-Path .\zcash-sapling-engineering)) {
    git clone https://github.com/kaikai-cao/zcash-sapling-engineering.git zcash-sapling-engineering
}
if (-not (Test-Path .\zcash-sapling-crypto)) {
    git clone https://github.com/zcash/sapling-crypto.git zcash-sapling-crypto
}
Set-Location .\zcash-sapling-crypto
git checkout 88a7946b4a3066787776e11f0a502654167e022d
Set-Location ..\zcash-sapling-engineering
```

The upstream Sapling checkout's recorded test environment was Rust/Cargo 1.88.0 (see [`docs/smoke-check.md`](docs/smoke-check.md)); the local harness runs recorded Rust 1.98.1. The harness patches crates.io dependencies to the **vendored, instrumented** sources under `vendor/bellman` and `vendor/groth16`. Using pristine crates.io sources will not reproduce all profiler output.

Parameter files are not committed. Validate the parameter files and hashes before measurement; see [`scripts/verify_params.py`](scripts/verify_params.py). Keep generated proof batches separate from the designated formal batches.

### Commands

Run from the engineering repository root in PowerShell:

```powershell
$env:RAYON_NUM_THREADS = "1"

# Circuit constraints and variable counts
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin circuit_scale

# Parameter file metadata, validation, and hashes
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin parameter_metadata

# Spend proof generation and verification
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin spend_prover_smoke

# Output proof generation and verification
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin sapling-output-smoke

# Rebuild summary tables and figures from already-recorded data only
python scripts/summarize_engineering.py
```

Some experiment scripts append records to raw CSVs; others regenerate derived tables. Inspect the script and current batch IDs before rerunning. Do **not** rerun proving merely to regenerate existing summaries.

## Repository map

```text
docs/                  # experiment notes, source call path, baseline comparison, completion audit
experiments/
  prover-smoke/        # reproducible Rust harness and Cargo.lock
  metadata/            # parameter file validation evidence
  raw/csv/             # structured raw runs and profiling records
  raw/logs/            # preserved experiment logs
results/
  tables/              # derived CSV summaries
  figures/             # generated charts
scripts/               # validation, run control, parsers, summaries, plots
vendor/
  bellman/             # vendored source with local profiling instrumentation
  groth16/              # vendored Groth16 source
weekly_summary.md      # concise advisor-facing results
bellman_msm_call_profile.patch
```

## Interpretation limits

- Frozen synthetic baseline: BN254 / arkworks 0.6.0; Sapling: BLS12-381 / Bellman/Groth16. Their workloads differ, so compare scale and cost structure—not absolute speed.
- The formal baseline remains the designated uninstrumented batches. An exploratory Spend single-thread MSM profile is now available in a separate local worktree, but is not revision-bound or integrated into this frozen snapshot. Its 87.62% call-time share is provisional and applies only to that instrumented batch.
- Deep profiling overhead changes absolute Prove latency. Multi-thread MSM call timers overlap.
- First-versus-repeat observations do not constitute a controlled cold/warm experiment; the variation's cause remains unproven.
- No algorithmic optimization has been implemented or validated. The thread-count measurements are diagnostic observations, not an optimization objective or a claim that one thread configuration is universally optimal.

See [`docs/engineering_experiment_notes.md`](docs/engineering_experiment_notes.md) for experiment methods and additional observations, [`docs/baseline_comparison.md`](docs/baseline_comparison.md) for the profile analysis, and [`weekly_summary.md`](weekly_summary.md) for the advisor-facing stage conclusion.
