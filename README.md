Set-Location D:\Research\zcash-sapling-engineering

$path = (Resolve-Path ".\README.md").Path
$readme = [System.IO.File]::ReadAllText($path)

function Replace-Section {
    param(
        [string]$Text,
        [string]$StartHeading,
        [string]$NextHeading,
        [string]$Replacement
    )

    $start = $Text.IndexOf($StartHeading, [StringComparison]::Ordinal)
    if ($start -lt 0) {
        throw "找不到章节：$StartHeading"
    }

    $end = $Text.IndexOf(
        $NextHeading,
        $start + $StartHeading.Length,
        [StringComparison]::Ordinal
    )

    if ($end -lt 0) {
        throw "找不到后续章节：$NextHeading"
    }

    return $Text.Substring(0, $start) +
        $Replacement.TrimEnd() +
        "`r`n`r`n" +
        $Text.Substring($end)
}

function Replace-TailSection {
    param(
        [string]$Text,
        [string]$StartHeading,
        [string]$Replacement
    )

    $start = $Text.IndexOf($StartHeading, [StringComparison]::Ordinal)
    if ($start -lt 0) {
        throw "找不到章节：$StartHeading"
    }

    return $Text.Substring(0, $start) +
        $Replacement.TrimEnd() +
        "`r`n"
}

$section3 = @'
## 3. Current Results

The current engineering baseline uses the following fixed Sapling source revision:

- `sapling-crypto` 0.9.0
- Source commit: `88a7946b4a3066787776e11f0a502654167e022d`
- Build profile: release
- Rayon threads: 1

### 3.1 Circuit Scale

| Metric | Spend | Output |
|---|---:|---:|
| Constraints | 98,777 | 7,827 |
| Auxiliary variables | 98,638 | 7,821 |
| Public inputs excluding the constant one | 7 | 5 |
| Input variables including the constant one | 8 | 6 |
| Estimated domain size | 131,072 | 8,192 |

Constraint and variable counts were obtained through a counting
`ConstraintSystem`. Domain size is estimated by rounding the constraint
count up to the next power of two; it was not directly measured from the
underlying domain object.

Raw data: `experiments/raw/csv/sapling_circuit_scale_raw.csv`

### 3.2 Parameter Files

| Metric | Spend parameters | Output parameters |
|---|---:|---:|
| File size | 47,958,396 bytes | 3,592,860 bytes |
| Approximate size | 45.737 MiB | 3.426 MiB |
| SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| BLAKE2b-512 | Recorded in the parameter table | Recorded in the parameter table |

The metadata program measured parameter read and validation times of
24,326.502 ms for Spend and 1,774.506 ms for Output. Each is a single
observation, not a repeated cold/warm benchmark. Separate proving-process
runs recorded slightly different load times; those measurements should
not be merged as though they came from the same run.

The parameter files remain outside Git. File size is not automatically
equivalent to a theoretical CRS size or a separately measured proving-key
or verifying-key size.

Raw data: `experiments/raw/csv/sapling_parameter_metadata_raw.csv`  
Summary: `results/tables/engineering_parameters.csv`

### 3.3 Formal Proving and Verification Baseline

The formal summary selects one designated batch per circuit, with five
proof and verification measurements in each batch.

| Metric | Spend | Output |
|---|---:|---:|
| Proving median | 3,385.716 ms | 514.853 ms |
| Proving min / max | 3,377.138 / 3,484.750 ms | 507.096 / 560.162 ms |
| Verification median | 2.790 ms | 2.150 ms |
| Verification min / max | 2.775 / 2.797 ms | 2.102 / 2.195 ms |
| Encoded proof size | 192 bytes | 192 bytes |
| Successful verifications | 5 / 5 | 5 / 5 |
| Formal batch ID | `1791613854129` | `1791549582046` |

The `prove` timer excludes parameter loading, verifying-key preparation,
and test-witness construction. Verification time measures the proof-check
call in the experiment, not full transaction validation.

The summary script explicitly selects the two batch IDs above. Additional
runs retained in raw CSV files are not silently mixed into the formal
statistics.

Raw data:
- `experiments/raw/csv/sapling_spend_prover_runs_release.csv`
- `experiments/raw/csv/sapling_output_prover_runs_release.csv`

Summary: `results/tables/engineering_performance.csv`

### 3.4 Peak Working Set Memory

| Metric | Spend | Output |
|---|---:|---:|
| Peak working set | 101.31 MiB | 22.22 MiB |
| Rayon threads | 1 | 1 |
| Build profile | release | release |
| Process exit code | 0 | 0 |

These measurements use Windows `Process.PeakWorkingSet64`, sampled every
250 ms in an independent process. Each circuit has only one memory
measurement so far. The value covers the entire process lifetime,
including parameter loading, validation, proving, and verification; it
is not the memory used by the proving call alone.

Raw data: `experiments/raw/csv/sapling_process_memory_raw.csv`  
Summary: `results/tables/engineering_memory.csv`

### 3.5 Source Call Path

`docs/zcash_sapling_flow.md` documents the source call path from Zcash
transaction construction into Sapling Spend/Output proving and verification.

The current experiment calls the relevant proof-generation and
verification APIs directly. It does not reproduce the complete wallet
transaction-building and consensus-validation workflow.
'@

$section4 = @'
## 4. Repository Structure

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
│   └── summarize_engineering.py
└── vendor/
    ├── bellman/
    └── groth16/
```

- `experiments/raw/` contains raw measurements. Keep new measurements
  separate from the designated formal baseline batches.
- `results/tables/` contains generated summary CSV files.
- `results/figures/` contains generated plots.
- `docs/engineering_experiment_notes.md` records experiment methods,
  measured results, and limitations.
- `docs/zcash_sapling_flow.md` describes the Zcash/Sapling source call path.
- `scripts/summarize_engineering.py` regenerates the three scale,
  parameter, and performance tables and their seven plots.
- Parameter files remain outside this repository and must not be committed.
'@

$section5 = @'
## 5. Reproducing the Experiments

The parameter files are expected at:

`D:\Research\zcash-params\`

From the repository root, use PowerShell.

```powershell
$env:RAYON_NUM_THREADS = "1"

# Circuit constraints and variable counts
cargo run --release `
  --manifest-path experiments/prover-smoke/Cargo.toml `
  --bin circuit_scale

# Parameter file metadata and hashes
cargo run --release `
  --manifest-path experiments/prover-smoke/Cargo.toml `
  --bin parameter_metadata

# Spend proof generation and verification
cargo run --release `
  --manifest-path experiments/prover-smoke/Cargo.toml `
  --bin spend_prover_smoke

# Output proof generation and verification
cargo run --release `
  --manifest-path experiments/prover-smoke/Cargo.toml `
  --bin sapling-output-smoke

# Regenerate summaries and plots
python scripts/summarize_engineering.py
```

The measurement programs may append new rows to raw CSV files. Do not
rerun them merely to regenerate tables. Before starting a new measurement
batch, record its purpose and batch ID and check that the formal batch
selection in `scripts/summarize_engineering.py` remains unchanged.

For reproducibility, record the source commit, Rust toolchain, thread
configuration, parameter hashes, and the measurement boundaries.
'@

$section7 = @'
## 7. Remaining Work

The first real Sapling engineering baseline is recorded, but the full
study is not yet complete.

The next tasks are:

- Define and measure explicit cold and warm modes. Current repeated runs
  occur in one process after parameter loading; this is not by itself a
  controlled cold-versus-warm benchmark or proof of a cold OS file cache.
- Repeat peak-working-set measurements in independent processes and report
  the measurement count and variability.
- Inspect whether the available APIs allow useful separate reporting of
  parameter, proving-key, and verifying-key objects. Do not infer one
  object's size from another.
- Compare the real Sapling measurements with the frozen synthetic
  Groth16 baseline by scale and cost structure, not by treating absolute
  timings from different curves and workloads as a direct performance
  contest.
- If practical, examine real-prover MSM profiling after the engineering
  measurements are complete. If instrumentation is impractical, record
  the limitation rather than forcing a bottleneck conclusion.
- Produce `weekly_summary.md` or a one-page presentation for the advisor,
  clearly separating measured facts, limitations, and open questions.

Do not modify the frozen synthetic baseline or start optimization work as
part of this measurement stage.
'@

$section8 = @'
## 8. Scope and Limitations

This repository is a reproducible learning and measurement case for the
historical Sapling Groth16 workflow. It is not an implementation of
Orchard or Halo 2, and it does not claim a new proving-system optimization.

The current results establish that the tested Spend and Output proof
generation and verification calls succeed in the local environment. They
do not establish full end-to-end transaction performance, a controlled
cold/warm result, stable memory distributions, or the exact proving
bottleneck in real Sapling workloads.

Treat the current numbers as an engineering baseline. The next stage is
to improve the experimental protocol, compare cost structure with the
frozen synthetic baseline, and prepare a concise advisor-facing summary.
'@

$readme = Replace-Section `
    $readme "## 3. Current Results" "## 4. Repository Structure" $section3

$readme = Replace-Section `
    $readme "## 4. Repository Structure" "## 5. Reproducing the Output Experiment" $section4

$readme = Replace-Section `
    $readme "## 5. Reproducing the Output Experiment" "## 6. Exploratory MSM Profiling" $section5

$readme = Replace-Section `
    $readme "## 7. Remaining Work" "## 8. Scope and Limitations" $section7

$readme = Replace-TailSection `
    $readme "## 8. Scope and Limitations" $section8

[System.IO.File]::WriteAllText(
    $path,
    $readme,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "`n=== README 标题检查 ==="
Select-String -Path .\README.md -Pattern "^## |^### "

Write-Host "`n=== README 差异统计 ==="
git diff --stat -- README.md

Write-Host "`n=== 空白符检查 ==="
git diff --check -- README.md