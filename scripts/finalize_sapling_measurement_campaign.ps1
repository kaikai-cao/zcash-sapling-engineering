param(
    [string]$RepoPath = 'D:\Research\zcash-sapling-engineering',
    [string]$ParameterReport = 'experiments\metadata\sapling_parameter_size_breakdown_20261011_142729.md',
    [string]$ParameterDetailCsv = 'experiments\raw\csv\sapling_parameter_size_breakdown_20261011_142729.csv',
    [string]$ParameterSummaryCsv = 'experiments\raw\csv\sapling_parameter_size_summary_20261011_142729.csv'
)

$ErrorActionPreference = 'Stop'

function Get-GitText {
    param([string[]]$GitArgs)
    $result = & git -C $RepoPath @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed: $($result -join ' ')"
    }
    return (($result | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Get-RelativeSha256 {
    param([string]$RelativePath)
    $full = Join-Path $RepoPath $RelativePath
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        return 'MISSING'
    }
    return (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
    throw "Repository directory not found: $RepoPath"
}

$branch = Get-GitText -GitArgs @('branch', '--show-current')
$head = Get-GitText -GitArgs @('rev-parse', 'HEAD')
$metadataFull = Join-Path $RepoPath $ParameterReport
$detailFull = Join-Path $RepoPath $ParameterDetailCsv
$summaryFull = Join-Path $RepoPath $ParameterSummaryCsv

foreach ($required in @($metadataFull, $detailFull, $summaryFull)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required parameter-size artifact missing: $required"
    }
}

# Validate summary rows before editing or writing any report.
$summaryRows = @(Import-Csv -LiteralPath $summaryFull)
if ($summaryRows.Count -ne 2) {
    throw "Expected two parameter summary rows; got $($summaryRows.Count)."
}
$spendRow = $summaryRows | Where-Object { $_.Circuit -eq 'Spend' } | Select-Object -First 1
$outputRow = $summaryRows | Where-Object { $_.Circuit -eq 'Output' } | Select-Object -First 1
if ($null -eq $spendRow -or $null -eq $outputRow) {
    throw 'Parameter summary CSV must contain Spend and Output rows.'
}
if ($spendRow.ParserReachedExactEOF -ne 'True' -or $outputRow.ParserReachedExactEOF -ne 'True') {
    throw 'Parameter parser did not report exact EOF for both files.'
}
if ([long]$spendRow.VerifyingKeySerializedBytes -ne 1636 -or [long]$outputRow.VerifyingKeySerializedBytes -ne 1444) {
    throw 'Unexpected VK serialized-size values in summary CSV; refusing to continue.'
}
if ([long]$spendRow.MpcTrailerBytes -ne 52836 -or [long]$outputRow.MpcTrailerBytes -ne 52836) {
    throw 'Unexpected MPC trailer sizes in summary CSV; refusing to continue.'
}

# Fix the three literal-variable placeholders in the generated Markdown report.
$report = Get-Content -LiteralPath $metadataFull -Raw
$report = $report.Replace('- Spend parameter file: `$SpendParamsPath`', '- Spend parameter file: D:\Research\zcash-params\sapling-spend.params')
$report = $report.Replace('- Output parameter file: `$OutputParamsPath`', '- Output parameter file: D:\Research\zcash-params\sapling-output.params')
$report = $report.Replace('- Point encoding assumptions: G1 = `$G1Bytes` bytes; G2 = `$G2Bytes` bytes', '- Point encoding assumptions: G1 = 96 bytes; G2 = 192 bytes')
# Also handle the same text if a Markdown editor removed the backticks.
$report = $report.Replace('- Spend parameter file: $SpendParamsPath', '- Spend parameter file: D:\Research\zcash-params\sapling-spend.params')
$report = $report.Replace('- Output parameter file: $OutputParamsPath', '- Output parameter file: D:\Research\zcash-params\sapling-output.params')
$report = $report.Replace('- Point encoding assumptions: G1 = $G1Bytes bytes; G2 = $G2Bytes bytes', '- Point encoding assumptions: G1 = 96 bytes; G2 = 192 bytes')
Set-Content -LiteralPath $metadataFull -Value $report -Encoding utf8

# Fix the source script for future reruns (without falsifying the historical
# SCRIPT_SHA256 already recorded in the report: that hash identifies the version
# that actually generated the original measurement files).
$generatorRelative = 'scripts\record_sapling_parameter_size_breakdown.ps1'
$generatorFull = Join-Path $RepoPath $generatorRelative
$generatorPatched = $false
if (Test-Path -LiteralPath $generatorFull -PathType Leaf) {
    $source = Get-Content -LiteralPath $generatorFull -Raw
    $before = $source
    $source = $source.Replace('`$SpendParamsPath`', '$SpendParamsPath')
    $source = $source.Replace('`$OutputParamsPath`', '$OutputParamsPath')
    $source = $source.Replace('`$G1Bytes`', '$G1Bytes')
    $source = $source.Replace('`$G2Bytes`', '$G2Bytes')
    if ($source -ne $before) {
        Set-Content -LiteralPath $generatorFull -Value $source -Encoding utf8
        $generatorPatched = $true
    }
}

$timestamp = '20261011'
$closureRelative = "experiments\metadata\sapling_measurement_campaign_closure_$timestamp.md"
$closureFull = Join-Path $RepoPath $closureRelative
$manifestRelative = "experiments\metadata\sapling_measurement_artifact_manifest_$timestamp.csv"
$manifestFull = Join-Path $RepoPath $manifestRelative
$measuredAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')

$closure = @"
# Sapling Measurement Campaign Closure

- Report generated: $measuredAt
- Repository: kaikai-cao/zcash-sapling-engineering
- Branch at report generation: $branch
- HEAD at report generation: $head
- This working tree contained uncommitted and untracked experiment artifacts when the campaign was being assembled. Each experiment's own metadata/logs remain the source of truth for its measurement-time revision and conditions.
- Parameter sizing report: $ParameterReport
- Parameter sizing detail CSV: $ParameterDetailCsv
- Parameter sizing summary CSV: $ParameterSummaryCsv

## Parameter serialization size

| Measurement | Spend | Output |
|---|---:|---:|
| Parameter file bytes | $($spendRow.ParameterFileBytes) | $($outputRow.ParameterFileBytes) |
| Groth16 Parameters body bytes (VK + five query vectors) | $($spendRow.Groth16ParametersBodyBytes) | $($outputRow.Groth16ParametersBodyBytes) |
| Embedded VK serialized bytes | $($spendRow.VerifyingKeySerializedBytes) | $($outputRow.VerifyingKeySerializedBytes) |
| Query-vector fields serialized bytes (not a standalone PK file) | $($spendRow.QueryVectorsSerializedBytes) | $($outputRow.QueryVectorsSerializedBytes) |
| MPC trailer bytes | $($spendRow.MpcTrailerBytes) | $($outputRow.MpcTrailerBytes) |
| MPC contributors in trailer | $($spendRow.MpcContributorCount) | $($outputRow.MpcContributorCount) |
| Parser reached exact EOF | $($spendRow.ParserReachedExactEOF) | $($outputRow.ParserReachedExactEOF) |

Spend parameter SHA-256: $($spendRow.ParameterFileSHA256)

Output parameter SHA-256: $($outputRow.ParameterFileSHA256)

These are serialized byte counts, not process memory consumption. The embedded VK size is not evidence of a separate standalone VK file, and the five query vectors are not reported as a separately serialized PK artifact.

## Cold/warm process comparison (exploratory; three pairs)

The comparison used independent processes, an attempted standby-list clear for the approximate cold condition, and a pre-read of the parameter file for the approximate warm condition. These are operational approximations, not perfect isolation of every operating-system cache.

| Pair | Cold Prove median (ms) | Warm Prove median (ms) | Warm minus cold (ms) | Relative difference |
|---|---:|---:|---:|---:|
| 1 | 3440.69 | 3472.57 | +31.88 | +0.93% |
| 2 | 3444.30 | 3460.21 | +15.91 | +0.46% |
| 3 | 3429.33 | 3455.48 | +26.15 | +0.76% |

Within this small sample, warm runs were slightly slower, not faster. This does not establish that caching has no effect; it shows no large consistent improvement under these specific conditions. The measured load/validation phase remained approximately 24 seconds in these process runs, so it should not be confused with a simple file-read-only timing.

Raw cache comparison: `experiments/raw/csv/sapling_cache_condition_raw.csv`.

## Repeated process peak working set (six independent processes)

| Circuit | Samples (MiB) | Median (MiB) | Range (MiB) | Proof verification |
|---|---|---:|---:|---|
| Spend | 101.45, 101.29, 101.29 | 101.29 | 101.29–101.45 | All runs passed |
| Output | 22.36, 20.86, 20.79 | 20.86 | 20.79–22.36 | All runs passed |

Raw memory measurements: `experiments/raw/csv/sapling_process_memory_raw.csv`.

## CPU diagnostic and measurement limits

The instrumented Spend CPU diagnostic batch had a Prove median of 3524.678 ms across five proofs. Its 39 CPU-counter samples included 36 valid samples and three counter errors. Median process CPU on a one-logical-processor scale was 97.91%; the p95 was 100.12%. Median sampled active-core maximum frequency was 5365.68 MHz. These samples are diagnostic evidence for that batch only; they do not retrospectively explain slower runs where the diagnostic was not active.

A separate first-repeat run showed substantially slower proving (around 6.7 seconds median according to its campaign summary). The available samples do not establish a unique cause for the variation. Treat CPU scheduling/frequency as a possible source of noise, not a proven causal explanation.

Raw CPU diagnostic CSV: `experiments/raw/csv/sapling_spend_cpu_diagnostic_20261011_111424_930.csv`.

Raw system-wide CPU samples: `experiments/raw/csv/sapling_system_load_samples.csv`.

## Same-source Spend / Output MSM profile (exploratory; instrumented build)

| Circuit | Prove median (ms) | MSM-sum median (ms) | Median per-run MSM share | Proof size | Verification |
|---|---:|---:|---:|---:|---|
| Spend | 6858.210 | 5932.749 | 87.06% | 192 bytes | 5/5 passed |
| Output | 885.491 | 850.428 | 93.32% | 192 bytes | 5/5 passed |

These figures come from instrumented profile runs and must not be combined with the frozen formal baseline as if they were the same measurement configuration. Output showed notable run-to-run variance; the median profile indicates MSM is a major measured cost in these batches, but the variation remains worth investigating before making a causal performance claim.

Comparison metadata: `experiments/metadata/sapling_same_source_msm_comparison_20261011.md`.

## Frozen formal baseline is separate

The previously frozen formal batches remain separate from the exploratory profiles:

- Spend: Prove median 3385.716 ms; Verify median 2.790 ms; 192-byte proof; 5/5 verified.
- Output: Prove median 514.853 ms; Verify median 2.150 ms; 192-byte proof; 5/5 verified.

Do not overwrite these formal records with the instrumented cache, CPU, memory, or MSM exploratory runs.

## Documentation and provenance note

The initial parameter-sizing run correctly recorded the script SHA-256, but its Markdown input-path and point-size lines displayed escaped variable names literally. The generated report has been corrected to show the actual paths and 96/192-byte point-size assumptions. The generator script was also patched for future runs. The `SCRIPT_SHA256` inside the measurement report remains the historical hash of the exact script version used for that original run; it was intentionally not rewritten to pretend the corrected source produced the earlier artifacts.

## Artifact manifest

`experiments/metadata/sapling_measurement_artifact_manifest_20261011.csv` records repository-local paths, byte sizes, SHA-256 hashes, and Git status for the working-tree artifacts seen when this closure script ran. The manifest excludes itself to avoid a recursive self-hash.

## Remaining caveats

- Cold/warm labels are approximate process-level conditions; only three pairs were sampled.
- Peak working-set repeats establish short-run repeatability for this host/session, not a universal memory bound.
- The CPU diagnostic applies to its own batch and cannot explain other batches without synchronized measurements.
- MSM profiling used instrumented vendor code, so timing figures are not pristine upstream library timings.
- Parameter-file size is not CRS generation cost, runtime memory, or proof size.
"@
Set-Content -LiteralPath $closureFull -Value $closure -Encoding utf8

# Build a manifest from all current tracked modifications and untracked files.
# It intentionally includes relevant scripts/reports/logs and excludes only itself.
$statusLines = @(& git -C $RepoPath status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw 'git status failed while building manifest.' }
$manifestRows = [System.Collections.Generic.List[object]]::new()
foreach ($lineObject in $statusLines) {
    $line = [string]$lineObject
    if ($line.Length -lt 4) { continue }
    $statusCode = $line.Substring(0, 2)
    $relative = $line.Substring(3).Trim()
    if ($relative.StartsWith('"') -and $relative.EndsWith('"')) {
        $relative = $relative.Trim('"')
    }
    $relative = $relative.Replace('/', '\')
    if ($relative -eq $manifestRelative) { continue }
    # This campaign manifest targets file artifacts, not deleted paths.
    $full = Join-Path $RepoPath $relative
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
    $info = Get-Item -LiteralPath $full
    $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestRows.Add([PSCustomObject]@{
        GitStatus = $statusCode
        RelativePath = $relative.Replace('\', '/')
        Bytes = [long]$info.Length
        SHA256 = $hash
    })
}
$manifestRows.ToArray() | Sort-Object RelativePath | Export-Csv -LiteralPath $manifestFull -NoTypeInformation -Encoding utf8

# Check there are no unexpanded placeholders in the fixed parameter report.
$fixedReport = Get-Content -LiteralPath $metadataFull -Raw
if ($fixedReport.Contains('$SpendParamsPath') -or $fixedReport.Contains('$OutputParamsPath') -or $fixedReport.Contains('$G1Bytes') -or $fixedReport.Contains('$G2Bytes')) {
    throw 'Unexpanded parameter-sizing placeholders remain in the Markdown report.'
}

# Print only a compact audit summary (avoid pipelines directly after foreach statements).
$artifactChecks = @(
    [PSCustomObject]@{ Name = 'Parameter detail CSV'; Exists = (Test-Path -LiteralPath $detailFull); Bytes = (Get-Item -LiteralPath $detailFull).Length; SHA256 = (Get-RelativeSha256 -RelativePath $ParameterDetailCsv) },
    [PSCustomObject]@{ Name = 'Parameter summary CSV'; Exists = (Test-Path -LiteralPath $summaryFull); Bytes = (Get-Item -LiteralPath $summaryFull).Length; SHA256 = (Get-RelativeSha256 -RelativePath $ParameterSummaryCsv) },
    [PSCustomObject]@{ Name = 'Parameter metadata'; Exists = (Test-Path -LiteralPath $metadataFull); Bytes = (Get-Item -LiteralPath $metadataFull).Length; SHA256 = (Get-RelativeSha256 -RelativePath $ParameterReport) },
    [PSCustomObject]@{ Name = 'Campaign closure'; Exists = (Test-Path -LiteralPath $closureFull); Bytes = (Get-Item -LiteralPath $closureFull).Length; SHA256 = (Get-RelativeSha256 -RelativePath $closureRelative) },
    [PSCustomObject]@{ Name = 'Artifact manifest'; Exists = (Test-Path -LiteralPath $manifestFull); Bytes = (Get-Item -LiteralPath $manifestFull).Length; SHA256 = (Get-RelativeSha256 -RelativePath $manifestRelative) }
)

Write-Host ''
Write-Host '================ CAMPAIGN FINALIZATION ================'
Write-Host "BRANCH=$branch"
Write-Host "HEAD=$head"
Write-Host "PARAMETER_SUMMARY_ROWS=$($summaryRows.Count)"
Write-Host "VK_SPEND_BYTES=$($spendRow.VerifyingKeySerializedBytes)"
Write-Host "VK_OUTPUT_BYTES=$($outputRow.VerifyingKeySerializedBytes)"
Write-Host "PARSER_EOF_SPEND=$($spendRow.ParserReachedExactEOF)"
Write-Host "PARSER_EOF_OUTPUT=$($outputRow.ParserReachedExactEOF)"
Write-Host "GENERATOR_SCRIPT_PATCHED=$generatorPatched"
Write-Host "MANIFEST_ARTIFACT_COUNT=$($manifestRows.Count)"
Write-Host "PARAMETER_METADATA=$ParameterReport"
Write-Host "CAMPAIGN_CLOSURE=$closureRelative"
Write-Host "ARTIFACT_MANIFEST=$manifestRelative"
Write-Host ''
$artifactChecks | Format-Table -AutoSize
Write-Host ''
Write-Host '================ CURRENT GIT STATUS ================'
& git -C $RepoPath status --short
Write-Host 'STATUS=SUCCESS'
