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

## Cold/warm process comparison (exploratory; three pairs)

The comparison used independent processes, an attempted standby-list clear for the approximate cold condition, and a pre-read of the parameter file for the approximate warm condition. These are operational approximations, not perfect isolation of every operating-system cache.

| Pair | Cold Prove median (ms) | Warm Prove median (ms) | Warm minus cold (ms) | Relative difference |
|---|---:|---:|---:|---:|
| 1 | 3440.69 | 3472.57 | +31.88 | +0.93% |
| 2 | 3444.30 | 3460.21 | +15.91 | +0.46% |
| 3 | 3429.33 | 3455.48 | +26.15 | +0.76% |

Within this small sample, warm runs were slightly slower, not faster. This does not establish that caching has no effect; it shows no large consistent improvement under these specific conditions. The measured load/validation phase remained approximately 24 seconds in these process runs, so it should not be confused with a simple file-read-only timing.

Raw cache comparison: xperiments/raw/csv/sapling_cache_condition_raw.csv.

## Repeated process peak working set (six independent processes)

| Circuit | Samples (MiB) | Median (MiB) | Range (MiB) | Proof verification |
|---|---|---:|---:|---|
| Spend | 101.45, 101.29, 101.29 | 101.29 | 101.29–101.45 | All runs passed |
| Output | 22.36, 20.86, 20.79 | 20.86 | 20.79–22.36 | All runs passed |

Raw memory measurements: xperiments/raw/csv/sapling_process_memory_raw.csv.

## CPU diagnostic and measurement limits

The instrumented Spend CPU diagnostic batch had a Prove median of 3524.678 ms across five proofs. Its 39 CPU-counter samples included 36 valid samples and three counter errors. Median process CPU on a one-logical-processor scale was 97.91%; the p95 was 100.12%. Median sampled active-core maximum frequency was 5365.68 MHz. These samples are diagnostic evidence for that batch only; they do not retrospectively explain slower runs where the diagnostic was not active.

A separate first-repeat run showed substantially slower proving (around 6.7 seconds median according to its campaign summary). The available samples do not establish a unique cause for the variation. Treat CPU scheduling/frequency as a possible source of noise, not a proven causal explanation.

Raw CPU diagnostic CSV: xperiments/raw/csv/sapling_spend_cpu_diagnostic_20261011_111424_930.csv.

Raw system-wide CPU samples: xperiments/raw/csv/sapling_system_load_samples.csv.

## Same-source Spend / Output MSM profile (exploratory; instrumented build)

| Circuit | Prove median (ms) | MSM-sum median (ms) | Median per-run MSM share | Proof size | Verification |
|---|---:|---:|---:|---:|---|
| Spend | 6858.210 | 5932.749 | 87.06% | 192 bytes | 5/5 passed |
| Output | 885.491 | 850.428 | 93.32% | 192 bytes | 5/5 passed |

These figures come from instrumented profile runs and must not be combined with the frozen formal baseline as if they were the same measurement configuration. Output showed notable run-to-run variance; the median profile indicates MSM is a major measured cost in these batches, but the variation remains worth investigating before making a causal performance claim.

Comparison metadata: xperiments/metadata/sapling_same_source_msm_comparison_20261011.md.

## Frozen formal baseline is separate

The previously frozen formal batches remain separate from the exploratory profiles:

- Spend: Prove median 3385.716 ms; Verify median 2.790 ms; 192-byte proof; 5/5 verified.
- Output: Prove median 514.853 ms; Verify median 2.150 ms; 192-byte proof; 5/5 verified.

Do not overwrite these formal records with the instrumented cache, CPU, memory, or MSM exploratory runs.

## Documentation and provenance note

The initial parameter-sizing run correctly recorded the script SHA-256, but its Markdown input-path and point-size lines displayed escaped variable names literally. The generated report has been corrected to show the actual paths and 96/192-byte point-size assumptions. The generator script was also patched for future runs. The SCRIPT_SHA256 inside the measurement report remains the historical hash of the exact script version used for that original run; it was intentionally not rewritten to pretend the corrected source produced the earlier artifacts.

## Artifact manifest

xperiments/metadata/sapling_measurement_artifact_manifest_20261011.csv records repository-local paths, byte sizes, SHA-256 hashes, and Git status for the working-tree artifacts seen when this closure script ran. The manifest excludes itself to avoid a recursive self-hash.

## Remaining caveats

- Cold/warm labels are approximate process-level conditions; only three pairs were sampled.
- Peak working-set repeats establish short-run repeatability for this host/session, not a universal memory bound.
- The CPU diagnostic applies to its own batch and cannot explain other batches without synchronized measurements.
- MSM profiling used instrumented vendor code, so timing figures are not pristine upstream library timings.
- Parameter-file size is not CRS generation cost, runtime memory, or proof size.

## Pre-commit whitespace normalization

Before commit, the whitespace check identified extra blank lines at end-of-file in the parameter sizing report, the RAMMap cold-pilot log, and the parameter-sizing generator script. Only trailing newline bytes were normalized; experiment contents and measured values were not changed. The artifact manifest's byte counts and SHA-256 values were refreshed for the normalized files and this closure document.
