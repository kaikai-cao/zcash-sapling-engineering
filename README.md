# Zcash Sapling Engineering Study

A reproducible engineering study of the historical Sapling Groth16 proving workflow in Zcash.

This repository is a learning and measurement project. It examines real Spend and Output circuits, parameter files, proof-generation and verification costs, and the path from Zcash transaction construction to Sapling proof APIs.

**The current milestone is a first measured engineering baseline, not completion of the full study and not a proving-system optimization.** Sapling uses Groth16; Orchard uses a different proving system (Halo 2 with PLONKish arithmetization). Results here should not be treated as benchmarks for Orchard or another proving system.

## 1. Objectives and status

- [x] Run proof generation and verification for real Sapling Spend and Output circuits.
- [x] Record circuit constraints, variable counts, and an estimated domain size.
- [x] Record parameter file sizes, SHA-256/BLAKE2b hashes, and single-run load/validation times.
- [x] Collect five formal proof/verification measurements per circuit and summarize them separately from exploratory runs.
- [x] Collect one whole-process peak-working-set observation for each circuit.
- [x] Document the key Sapling source call path.
- [x] Draft a concise advisor-facing stage summary (`weekly_summary.md`).
- [ ] Complete a controlled cold-versus-warm measurement protocol.
- [ ] Repeat memory measurements to report variability.
- [ ] Compare scale and cost structure with the frozen synthetic Groth16 baseline.
- [ ] Investigate real Sapling MSM profiling if feasible; do not assume the synthetic baseline's hotspot must carry over.

## 2. Experimental environment and source revision

| Item | Configuration |
|---|---|
| Operating system | Windows 11 |
| CPU | Intel Core i7-14700 |
| Logical processors | 28 |
| Installed memory | 32 GB |
| Rust | 1.98.1 (recorded local toolchain) |
| Build profile | Release |
| Rayon threads for formal runs | 1 |
| Curve | BLS12-381 |
| Proving system | Groth16 |
| Sapling library | `sapling-crypto` 0.9.0 |
| Sapling source commit | `88a7946b4a3066787776e11f0a502654167e022d` |
| Local engineering commit | `f235818` (`feat: add Sapling engineering experiment baseline`) |

The official Sapling source is kept separately at `D:\Research\zcash-sapling-crypto`. Parameter files are stored outside this repository at `D:\Research\zcash-params\` and must not be committed to Git.

## 3. Circuit scale

| Metric | Spend | Output |
|---|---:|---:|
| Constraints | 98,777 | 7,827 |
| Auxiliary variables | 98,638 | 7,821 |
| Public inputs excluding the constant one | 7 | 5 |
| Input variables including the constant one | 8 | 6 |
| Estimated domain size | 131,072 | 8,192 |

Constraint and variable counts were measured using a counting `ConstraintSystem`. Domain size is estimated as `next_power_of_two(constraints)`; it was not directly queried from the underlying domain object.

Raw data: `experiments/raw/csv/sapling_circuit_scale_raw.csv`  
Summary: `results/tables/engineering_scale.csv`

## 4. Parameter files

| Metric | Spend parameters | Output parameters |
|---|---:|---:|
| File size | 47,958,396 bytes | 3,592,860 bytes |
| Approximate size | 45.737 MiB | 3.426 MiB |
| SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| Point encoding validation | Passed | Passed |
| Metadata-program load/validation time | 24,326.502 ms | 1,774.506 ms |
| Number of metadata timing samples | 1 | 1 |

Full BLAKE2b-512 digests and file paths are recorded in `results/tables/engineering_parameters.csv` and `experiments/raw/csv/sapling_parameter_metadata_raw.csv`.

These load/validation times are single observations, not cold/warm benchmark results. Separate proof-program runs recorded 23,967.432 ms for Spend and 1,807.789 ms for Output. Those values came from different runs and should not be combined as repeated measurements. A parameter file's byte size is not automatically the size of the theoretical CRS, proving key, or verifying key; these are distinct objects.

## 5. Formal proof-generation and verification baseline

The generated summary script selects one designated batch per circuit. Each selected batch has five proof-generation and verification measurements, using release mode and one Rayon thread.

| Metric | Spend | Output |
|---|---:|---:|
| Formal batch ID | `1791613854129` | `1791549582046` |
| Proving median | 3,385.716 ms | 514.853 ms |
| Proving min / max | 3,377.138 / 3,484.750 ms | 507.096 / 560.162 ms |
| Verification median | 2.790 ms | 2.150 ms |
| Verification min / max | 2.775 / 2.797 ms | 2.102 / 2.195 ms |
| Encoded proof size | 192 bytes | 192 bytes |
| Successful proof checks | 5 / 5 | 5 / 5 |

The proving timer covers the call that creates one proof. It excludes parameter loading, verifying-key preparation, and test-witness construction. Verification time covers the proof-check call in the experiment; it is not the total validation cost of a complete Zcash transaction.

The raw CSVs retain additional batches, including later runs performed to observe peak memory. The summary script deliberately selects only batch `1791613854129` for Spend and `1791549582046` for Output so that those later runs are not silently mixed into the formal statistics.

- Spend raw data: `experiments/raw/csv/sapling_spend_prover_runs_release.csv`
- Output raw data: `experiments/raw/csv/sapling_output_prover_runs_release.csv`
- Summary: `results/tables/engineering_performance.csv`

## 6. Peak working-set memory

| Metric | Spend | Output |
|---|---:|---:|
| Peak working set | 101.31 MiB | 22.22 MiB |
| Rayon threads | 1 | 1 |
| Build profile | release | release |
| Process exit code | 0 | 0 |
| Independent process samples | 1 | 1 |

Memory was observed through Windows `Process.PeakWorkingSet64`, polling every 250 ms. This is the whole process's peak working set over parameter loading, validation, proving, and verification, not memory used only by the proving call. There is currently only one observation for each circuit; treat these values as preliminary.

- Raw data: `experiments/raw/csv/sapling_process_memory_raw.csv`
- Summary: `results/tables/engineering_memory.csv`

## 7. Sapling call path

`docs/zcash_sapling_flow.md` records the source call path from transaction construction through Sapling bundle proof creation and Spend/Output prover APIs to Groth16 proof generation, along with the verification path.

The current experiment calls proof-generation and verification APIs directly. It does not reproduce the complete wallet transaction-building, signing, network, or consensus-validation workflow, so the reported timings are not end-to-end transaction timings.

## 8. Repository structure

```text
zcash-sapling-engineering/
├── docs/
│   ├── engineering_experiment_notes.md
│   └── zcash_sapling_flow.md
├── experiments/
│   ├── prover-smoke/
│   │   └── src/bin/
│   │       ├── circuit_scale.rs
│   │       ├── parameter_metadata.rs
│   │       └── spend_prover_smoke.rs
│   └── raw/csv/
├── results/
│   ├── figures/
│   └── tables/
├── scripts/
│   ├── measure_process_peak_working_set.ps1
│   ├── run_process_first_repeat.ps1
│   └── summarize_engineering.py
└── weekly_summary.md
```

- `experiments/raw/` stores original measurements. Keep newly collected batches clearly identified.
- `results/tables/` stores generated summary tables.
- `results/figures/` stores generated plots.
- `docs/engineering_experiment_notes.md` describes methods, data, and limitations.
- `docs/zcash_sapling_flow.md` describes the source call path.
- `scripts/summarize_engineering.py` creates the scale, parameter, and performance tables and seven charts. It intentionally selects the designated formal batches.
- `scripts/run_process_first_repeat.ps1` runs independent processes and records first-vs-repeat observations plus system-load samples.
- `scripts/measure_process_peak_working_set.ps1` records process peak working set.
- `weekly_summary.md` provides a concise advisor-facing stage summary.
- Parameter files are external and must not be committed.

## 9. Reproducing measurements

Run these commands from the repository root in PowerShell. The parameter files must be present at `D:\Research\zcash-params\`.

```powershell
$env:RAYON_NUM_THREADS = "1"

# Circuit constraints and variable counts
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin circuit_scale

# Parameter file metadata and hashes
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin parameter_metadata

# Spend proof generation and verification
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin spend_prover_smoke

# Output proof generation and verification
cargo run --release --manifest-path experiments/prover-smoke/Cargo.toml --bin sapling-output-smoke

# Regenerate summary tables and figures; does not run new proof experiments
python scripts/summarize_engineering.py

# Exploratory first-vs-repeat timing with system-load samples (starts new proof processes)
.\scripts\run_process_first_repeat.ps1 -Circuit Output -Processes 3

# Peak working-set measurement (starts a new proof process)
.\scripts\measure_process_peak_working_set.ps1 -Circuit Output
```

The measurement programs can append rows to raw CSV files. Check the current contents and record the batch ID before rerunning them. Do not rerun proof experiments just to regenerate tables. The first-vs-repeat runs are exploratory and are not strict cold/warm cache tests.

## 10. Frozen baseline comparison and limitations

A comparison against the synthetic Groth16 baseline is still pending. The synthetic baseline uses a different circuit and curve setup, while Sapling uses BLS12-381 and real Spend/Output circuits. Compare scale and cost structure, not absolute runtimes as if they were a same-workload contest.

A claim that MSM, G2, WNAF, or bucket accumulation is the dominant cost in real Sapling proving is not yet supported by the measurements recorded here. If real-prover instrumentation is infeasible through the available APIs, that limitation should be recorded rather than replaced with an assumption.

The current results establish a first engineering baseline: real Spend and Output proof generation and proof checks succeed, the main scale and parameter metadata are recorded, and a source call-path note exists. The study remains in progress until cold/warm conditions, memory repeatability, and frozen-baseline comparison have been addressed. A concise advisor-facing draft is available in `weekly_summary.md`.

## 11. Exploratory First-vs-Repeat Measurements

Additional independent-process runs were collected on 2026-10-10 to compare the first proving call with the following four calls in the same process. These are exploratory observations, not a controlled cold-versus-warm cache benchmark: parameters and inputs are prepared before the first proof, and the operating-system file cache is not forcibly cleared.

Several Output processes had stable later proving times near 0.51–0.52 s, while other processes showed later proving times near 0.96–1.15 s and simultaneously higher verification times. Subsequent Spend runs also showed substantially higher parameter-loading, proving, and verification times than the designated baseline. All recorded proof checks passed, but the runtime variation remains unexplained.

The sampling script waits 500 ms between system-load polling attempts. In the captured runs, actual samples were roughly 0.8 seconds apart because CIM/WMI query and processing time added overhead. The samples are whole-system CPU utilization, not CPU time attributable to a particular proving call. The available measurements do not establish that WeChat, power management, or any other single factor caused the variation.

Raw records:

- `experiments/raw/csv/sapling_process_first_repeat_raw.csv`
- `experiments/raw/csv/sapling_system_load_samples.csv`
- `experiments/raw/logs/`

Reproduction scripts:

- `scripts/run_process_first_repeat.ps1`
- `scripts/measure_process_peak_working_set.ps1`

The formal summary remains restricted to Spend batch `1791613854129` and Output batch `1791549582046`. Exploratory batches are retained but are not mixed into those formal statistics. A controlled cold/warm benchmark and a stable memory distribution remain open tasks.
