# Scripts Index

This directory contains scripts for parameter validation, Sapling proof-generation experiments, profiling, data processing, visualization, and research artifact management.

The scripts have different side effects. Some only analyze existing data; others run proving workloads, append measurements, write result files, or commit and push repository changes. Read the relevant section before running a script.

## 1. Parameter Validation and Campaign Management

| Script | Purpose | Important behavior |
|---|---|---|
| `verify_params.py` | Verify the expected sizes and BLAKE2b-512 hashes of the Sapling Spend and Output parameter files. | Parameter directory precedence: `--param-dir` > `ZCASH_PARAMS_DIR` > the legacy Windows default. Writes `experiments/metadata/parameter_validation.csv` by default and overwrites the selected output CSV. Use `--output-csv` to preserve existing records. |
| `record_sapling_parameter_size_breakdown.ps1` | Analyze the serialized layout and size breakdown of the Spend and Output parameter files. | Repository root is resolved relative to the script. Explicit `-SpendParamsPath` and `-OutputParamsPath` values take precedence; otherwise parameter files are resolved from `ZCASH_PARAMS_DIR`, falling back to the legacy Windows parameter directory. Writes timestamped CSV and Markdown artifacts; does not generate proofs. |
| `finalize_sapling_measurement_campaign.ps1` | Validate and finalize the specific 2026-10-11 measurement campaign. | Defaults to fixed, date-stamped input and output artifacts. It edits the parameter-sizing report, may patch the generator script, and writes a closure report and manifest. It refuses to overwrite existing closure or manifest files unless `-AllowOverwriteArtifacts` is explicitly supplied. This is not a read-only audit command. |
| `commit_sapling_measurement_campaign.ps1` | Perform the final Git archival operation for the original 2026-10-11 campaign. | **Historical one-off helper, not a general-purpose commit command.** It requires branch `main`, a hardcoded expected HEAD, and a fixed artifact set. It normalizes trailing blank lines, refreshes the manifest, stages and commits the audited files, and pushes to `origin main` unless `-SkipPush` is supplied. The expected HEAD no longer matches the current branch; do not run without deliberately reviewing and redesigning its historical guards. |

## 2. Proof-Generation and System Measurements

| Script | Purpose | Main artifacts or side effects |
|---|---|---|
| `run_spend_combined_profile.ps1` | Run five Sapling Spend proof-generation trials and collect stage and MSM timing records. | Writes raw CSVs, standard output/error logs, and a batch metadata report. Accepts a thread count and parameter path. Requires a clean worktree by default. |
| `run_spend_thread_scaling.ps1` | Measure Spend proving performance across selected Rayon thread counts. | Runs actual proving workloads and records the measurements and logs needed for scaling comparisons. |
| `run_spend_cpu_frequency_diagnostic.ps1` | Sample CPU utilization, processor frequency, and performance counters during a single-thread Spend run. | Runs a proving workload and writes time-series CSV data and logs. Requires suitable Windows performance counters. |
| `measure_process_peak_working_set.ps1` | Measure process memory usage for either Spend or Output. | Requires `-Circuit Spend` or `-Circuit Output`. Runs the relevant executable and records memory measurements and logs. |
| `run_process_first_repeat.ps1` | Study the first proving repeat and process/system load behavior. | Requires `-Circuit Spend` or `-Circuit Output`; accepts `-Processes` to control the number of processes. Runs actual proving workloads. |
| `run_sapling_cache_condition_comparison.ps1` | Compare proving under different cache conditions. | Requires `-Circuit Spend` or `-Circuit Output`; accepts `-Pairs`, `-RamMapPath`, `-SpendParamsPath`, and `-OutputParamsPath`. Parameter paths also support `SAPLING_SPEND_PARAMS`, `SAPLING_OUTPUT_PARAMS`, and `ZCASH_PARAMS_DIR`; RAMMap supports `SAPLING_RAMMAP_PATH`. Requires an elevated PowerShell session, invokes RAMMap for the approximate cold condition, runs real proof-generation processes, and appends records to the cache-comparison CSV. Do not run for syntax or documentation checks. |

## 3. MSM and Worker-Execution Analysis

| Script | Purpose | Main artifacts or side effects |
|---|---|---|
| `parse_msm_profile.py` | Parse existing Output MSM profiling logs into call-level records, summaries, and plots. | Produces MSM-call and stage CSVs, summary data, and figures. Its current source log is selected in the script. |
| `parse_msm_stage_comparison.py` | Compare Output MSM-stage measurements across configured thread-count batches. | Validates the logged calls and proof results, then updates derived stage-comparison tables and figures while preserving unrelated historical batches. |
| `parse_worker_task_start.py` | Analyze Output worker task-start delay, submission timing, MSM elapsed time, and synchronous fallback records. | Produces call-level CSV data, summary tables, and a task-start-delay figure. Reads configured historical logs. |
| `compare_msm_thread_profiles.py` | Compare MSM calls and proof measurements from existing multi-thread profiling logs. | Produces derived comparison data and visualizations; inspect the configured log inputs before rerunning. |

## 4. Output and Spend Comparisons

| Script | Purpose | Main artifacts or side effects |
|---|---|---|
| `compare_output_threads.py` | Compare selected historical Output proof batches across thread configurations. | Reads `sapling_output_prover_runs_release.csv` and uses batch IDs selected in the source code. Check those IDs before interpreting the result. |
| `compare_spend_thread_profiles.py` | Compare two provenance-linked Spend diagnostic batches. | Reads existing raw stage/MSM CSVs and batch metadata; generates comparison CSVs, PNGs, and a Markdown report. Does not generate new proofs. |
| `plot_output_prover.py` | Summarize and visualize Output proving and verification performance. | Reads the Output run CSV, selects the latest recorded batch, and writes an exploratory summary and plots. |
| `plot_spend_bottleneck_figures.py` | Rebuild Spend thread-scaling, MSM-call, and stage-timing figures from existing raw CSV files. | Generates three summary tables and three figures. The default output tag contains a generation timestamp; the script refuses to overwrite any existing target output. It does not generate proofs. |

## 5. Engineering-Level Summaries

| Script | Purpose | Main artifacts or side effects |
|---|---|---|
| `summarize_engineering.py` | Consolidate selected formal-baseline measurements for engineering-level comparisons. | Reads configured circuit-scale, parameter, performance, and memory CSVs; generates derived result tables and figures. The selected baseline batch IDs and dependency identity are defined in the source code. |

## 6. Typical Workflow

The overall workflow is:

1. Validate parameter files.
2. Check the source revision, configuration, and required inputs.
3. Run the intended proving or system-measurement experiment.
4. Preserve the original CSV measurements and logs.
5. Parse and compare existing records.
6. Generate derived tables, plots, and metadata reports.
7. Verify the outputs and their provenance before committing them.

Raw measurements and logs are the primary experimental evidence. Summary tables and figures are derived artifacts and should not replace the raw records.

## 7. Safety and Reproducibility Notes

### Distinguish analysis from experiments

Python utilities that parse existing CSVs or logs generally do not run proof generation. PowerShell scripts beginning with `run_` or `measure_` commonly launch real workloads and can append new measurement rows or create new logs.

Do not run an experiment merely to check whether its script parses or imports successfully.

### Check historical input selection

Several analysis scripts intentionally use fixed log names, batch IDs, or historical CSV paths. Before reusing them, verify that the selected inputs correspond to the experiment you want to analyze.

Some legacy utilities write to fixed output filenames or update existing derived CSVs. The overwrite protection in `plot_spend_bottleneck_figures.py` does not automatically apply to other utilities.

### Check machine-specific dependencies

Some scripts retain legacy Windows defaults or fixed historical input files, so a fresh checkout may require configuration before use.

The following utilities support parameter-path configuration:

- `verify_params.py`: `--param-dir`, then `ZCASH_PARAMS_DIR`, then its legacy default directory.
- `record_sapling_parameter_size_breakdown.ps1`: explicit per-file path parameters, then `ZCASH_PARAMS_DIR`, then its legacy default directory.
- `run_spend_combined_profile.ps1`: `-ParameterPath`, then `ZCASH_PARAMS_DIR`, then its legacy default directory.
- `run_sapling_cache_condition_comparison.ps1`: explicit per-file parameters, corresponding `SAPLING_SPEND_PARAMS` / `SAPLING_OUTPUT_PARAMS` environment variables, then `ZCASH_PARAMS_DIR`; RAMMap can be configured with `-RamMapPath` or `SAPLING_RAMMAP_PATH`.

These settings do not make every legacy script portable. Check each script's fixed input batch IDs, output names, expected repository revision, external tools, and overwrite behavior before running it.

### Preserve provenance

For each research-grade measurement, retain the relevant source revision, dependency revision, parameter-file identity, environment, thread configuration, raw CSV records, original logs, and proof-verification status.

Do not combine formal baseline measurements and instrumented diagnostic measurements into the same statistical group unless the distinction is explicitly accounted for.

### Dependencies

The proving experiments require the pinned Rust/Cargo dependency graph and the corresponding parameter files, which are stored outside this repository.

Python plotting utilities require `matplotlib`. Install it in the project environment when necessary:

`python -m pip install matplotlib`

Check each script's own arguments and required inputs before execution. This index summarizes current roles; it does not make legacy scripts portable or guarantee that every derived artifact can be regenerated without the original inputs.