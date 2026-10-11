# Sapling Measurement Campaign Closure

- Report generated: 2026-10-11T14:32:22+08:00
- Repository: kaikai-cao/zcash-sapling-engineering
- Branch at report generation: main
- HEAD at report generation: c4f4befaaa73bba750663a8d005f10dd437bda4d
- This working tree contained uncommitted and untracked experiment artifacts when the campaign was being assembled. Each experiment's own metadata/logs remain the source of truth for its measurement-time revision and conditions.
- Parameter sizing report: experiments\metadata\sapling_parameter_size_breakdown_20261011_142729.md
- Parameter sizing detail CSV: experiments\raw\csv\sapling_parameter_size_breakdown_20261011_142729.csv
- Parameter sizing summary CSV: experiments\raw\csv\sapling_parameter_size_summary_20261011_142729.csv

## Parameter serialization size

| Measurement | Spend | Output |
|---|---:|---:|
| Parameter file bytes | 47958396 | 3592860 |
| Groth16 Parameters body bytes (VK + five query vectors) | 47905560 | 3540024 |
| Embedded VK serialized bytes | 1636 | 1444 |
| Query-vector fields serialized bytes (not a standalone PK file) | 47903924 | 3538580 |
| MPC trailer bytes | 52836 | 52836 |
| MPC contributors in trailer | 97 | 97 |
| Parser reached exact EOF | True | True |

Spend parameter SHA-256: 8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13

Output parameter SHA-256: 2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4

These are serialized byte counts, not process memory consumption. The embedded VK size is not evidence of a separate standalone VK file, and the five query vectors are not reported as a separately serialized PK artifact.

## Cold/warm process comparison (exploratory; three pairs per circuit)

- Supplemental Output cache-condition campaign recorded: 2026-10-11T14:57:37+08:00
- Output process batches were run from engineering commit 2124efc090d7fd7c353d5bf3ad5e463f9af09c1c, with a clean worktree at experiment start. Each process generated five proofs, all verified; each batch recorded 40 MSM profile records.
- The cold condition attempted a Windows standby-list clear; the warm condition pre-read the parameter file. These are operational approximations, not perfect isolation of every operating-system cache.

| Circuit | Pair | Cold batch | Warm batch | Cold Prove median (ms) | Warm Prove median (ms) | Warm − cold (ms) | Relative difference | Cold load/validate (ms) | Warm load/validate (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|| Spend | 1 | 1791688828413 | 1791688872855 | 3440.69 | 3472.58 | +31.88 | 0.93% | 24042.95 | 23960.44 |
| Spend | 2 | 1791688962305 | 1791688917416 | 3444.30 | 3460.21 | +15.91 | 0.46% | 24018.81 | 24043.25 |
| Spend | 3 | 1791689006965 | 1791689051396 | 3429.33 | 3455.48 | +26.15 | 0.76% | 24086.97 | 24068.97 |
| Output | 1 | 1791701501974 | 1791701509616 | 515.79 | 513.90 | -1.89 | -0.37% | 1821.81 | 1804.32 |
| Output | 2 | 1791701524775 | 1791701517163 | 516.46 | 513.82 | -2.64 | -0.51% | 1810.56 | 1795.92 |
| Output | 3 | 1791701532382 | 1791701539994 | 517.52 | 518.46 | +0.95 | 0.18% | 1815.11 | 1810.35 |

Across the three Spend pairs, warm-minus-cold Prove median differences were approximately +0.93%, +0.46%, and +0.76%. Across the three Output pairs, the differences were approximately -0.37%, -0.51%, and +0.18%. The direction is not consistent across the two circuits, and each comparison has only three pairs. These results do not show a large, stable proving-time benefit from pre-reading the parameter files under the tested conditions; they do not prove cache state has no effect.

The parameter read/validation stage was approximately 24 seconds for Spend and approximately 1.8 seconds for Output in these process-level runs. This stage includes the experiment harness's parameter load and validation, not merely raw disk throughput. The measured Prove phase is separate from that stage.

Raw cache comparison: experiments/raw/csv/sapling_cache_condition_raw.csv.
## Repeated process peak working set (six independent processes)

| Circuit | Samples (MiB) | Median (MiB) | Range (MiB) | Proof verification |
|---|---|---:|---:|---|
| Spend | 101.45, 101.29, 101.29 | 101.29 | 101.29–101.45 | All runs passed |
| Output | 22.36, 20.86, 20.79 | 20.86 | 20.79–22.36 | All runs passed |

Raw memory measurements: experiments/raw/csv/sapling_process_memory_raw.csv.

## CPU diagnostic and measurement limits

The instrumented Spend CPU diagnostic batch had a Prove median of 3524.678 ms across five proofs. Its 39 CPU-counter samples included 36 valid samples and three counter errors. Median process CPU on a one-logical-processor scale was 97.91%; the p95 was 100.12%. Median sampled active-core maximum frequency was 5365.68 MHz. These samples are diagnostic evidence for that batch only; they do not retrospectively explain slower runs where the diagnostic was not active.

A separate first-repeat run showed substantially slower proving (around 6.7 seconds median according to its campaign summary). The available samples do not establish a unique cause for the variation. Treat CPU scheduling/frequency as a possible source of noise, not a proven causal explanation.

Raw CPU diagnostic CSV: experiments/raw/csv/sapling_spend_cpu_diagnostic_20261011_111424_930.csv.

Raw system-wide CPU samples: experiments/raw/csv/sapling_system_load_samples.csv.

## Same-source Spend / Output MSM profile (exploratory; instrumented build)

| Circuit | Prove median (ms) | MSM-sum median (ms) | Median per-run MSM share | Proof size | Verification |
|---|---:|---:|---:|---:|---|
| Spend | 6858.210 | 5932.749 | 87.06% | 192 bytes | 5/5 passed |
| Output | 885.491 | 850.428 | 93.32% | 192 bytes | 5/5 passed |

These figures come from instrumented profile runs and must not be combined with the frozen formal baseline as if they were the same measurement configuration. Output showed notable run-to-run variance; the median profile indicates MSM is a major measured cost in these batches, but the variation remains worth investigating before making a causal performance claim.

Comparison metadata: experiments/metadata/sapling_same_source_msm_comparison_20261011.md.

## Frozen formal baseline is separate

The previously frozen formal batches remain separate from the exploratory profiles:

- Spend: Prove median 3385.716 ms; Verify median 2.790 ms; 192-byte proof; 5/5 verified.
- Output: Prove median 514.853 ms; Verify median 2.150 ms; 192-byte proof; 5/5 verified.

Do not overwrite these formal records with the instrumented cache, CPU, memory, or MSM exploratory runs.

## Documentation and provenance note

The initial parameter-sizing run correctly recorded the script SHA-256, but its Markdown input-path and point-size lines displayed escaped variable names literally. The generated report has been corrected to show the actual paths and 96/192-byte point-size assumptions. The generator script was also patched for future runs. The SCRIPT_SHA256 inside the measurement report remains the historical hash of the exact script version used for that original run; it was intentionally not rewritten to pretend the corrected source produced the earlier artifacts.

## Artifact manifest

experiments/metadata/sapling_measurement_artifact_manifest_20261011.csv records repository-local paths, byte sizes, SHA-256 hashes, and Git status for the working-tree artifacts seen when this closure script ran. The manifest excludes itself to avoid a recursive self-hash.

## Remaining caveats

- Cold/warm labels are approximate process-level conditions; only three pairs were sampled.
- Peak working-set repeats establish short-run repeatability for this host/session, not a universal memory bound.
- The CPU diagnostic applies to its own batch and cannot explain other batches without synchronized measurements.
- MSM profiling used instrumented vendor code, so timing figures are not pristine upstream library timings.
- Parameter-file size is not CRS generation cost, runtime memory, or proof size.

## Pre-commit whitespace normalization

Before commit, the whitespace check identified extra blank lines at end-of-file in the parameter sizing report, the RAMMap cold-pilot log, and the parameter-sizing generator script. Only trailing newline bytes were normalized; experiment contents and measured values were not changed. The artifact manifest's byte counts and SHA-256 values were refreshed for the normalized files and this closure document.
