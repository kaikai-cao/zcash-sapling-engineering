[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$ParameterPath = 'D:\Research\zcash-params\sapling-spend.params',
    [ValidateRange(1, 128)]
    [int]$Threads = 1,
    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-GitValue {
    param([string[]]$GitArgs)
    $value = & git -C $RepoRoot @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed: $($value -join ' ')"
    }
    return (($value | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Get-Sha256 {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required artifact is missing: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Median {
    param([double[]]$Values)
    $sorted = @($Values | Sort-Object)
    if ($sorted.Count -eq 0) { throw 'Cannot calculate median of an empty set.' }
    $mid = [int][Math]::Floor($sorted.Count / 2)
    if (($sorted.Count % 2) -eq 1) { return [double]$sorted[$mid] }
    return ([double]$sorted[$mid - 1] + [double]$sorted[$mid]) / 2.0
}

function Get-RowsFromCsv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "CSV not found: $Path"
    }
    return @(Import-Csv -LiteralPath $Path)
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$manifest = Join-Path $RepoRoot 'experiments\prover-smoke\Cargo.toml'
$exe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\spend_prover_smoke.exe'
$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
$metadataDir = Join-Path $RepoRoot 'experiments\metadata'
$sourceCsv = Join-Path $rawDir 'sapling_spend_prover_runs_release.csv'
$bellmanSource = Join-Path $RepoRoot 'vendor\bellman\src\multiexp.rs'
$groth16Source = Join-Path $RepoRoot 'vendor\groth16\src\prover.rs'

foreach ($path in @($manifest, $ParameterPath, $sourceCsv, $bellmanSource, $groth16Source)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file not found: $path" }
}

$branch = Get-GitValue -GitArgs @('branch', '--show-current')
$head = Get-GitValue -GitArgs @('rev-parse', 'HEAD')
$initialStatus = Get-GitValue -GitArgs @('status', '--porcelain')
$dirtyAtStart = -not [string]::IsNullOrWhiteSpace($initialStatus)
if ($dirtyAtStart -and -not $AllowDirtyWorktree) {
    throw @"
Worktree is not clean. Commit/stash your work before a provenance-grade measurement.
If you intentionally need an exploratory run, pass -AllowDirtyWorktree; its dirty state will be recorded.
Current status:
$initialStatus
"@
}

$parameterItem = Get-Item -LiteralPath $ParameterPath
$parameterHash = Get-Sha256 -Path $ParameterPath
if ([long]$parameterItem.Length -ne 47958396) {
    throw "Unexpected Spend parameter size: $($parameterItem.Length) bytes (expected 47958396)."
}
$expectedParameterHash = '8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13'
if ($parameterHash -ne $expectedParameterHash) {
    throw "Spend parameter SHA-256 differs from the validated repository reference. Expected $expectedParameterHash; got $parameterHash."
}

New-Item -ItemType Directory -Force -Path $rawDir, $logDir, $metadataDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$buildStdout = Join-Path $logDir "sapling_spend_combined_profile_build_$stamp.stdout.log"
$buildStderr = Join-Path $logDir "sapling_spend_combined_profile_build_$stamp.stderr.log"
$stdoutPath = Join-Path $logDir "sapling_spend_combined_profile_$stamp.stdout.log"
$stderrPath = Join-Path $logDir "sapling_spend_combined_profile_$stamp.stderr.log"

$cargo = (Get-Command cargo -ErrorAction Stop).Source
$buildArgs = 'build --release --manifest-path "{0}" --bin spend_prover_smoke' -f $manifest
$buildProc = Start-Process -FilePath $cargo -ArgumentList $buildArgs -WorkingDirectory $RepoRoot -PassThru -Wait -RedirectStandardOutput $buildStdout -RedirectStandardError $buildStderr
if ($buildProc.ExitCode -ne 0) {
    throw "Release build failed with exit code $($buildProc.ExitCode). Build logs preserved: $buildStdout ; $buildStderr"
}
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Release executable missing after build: $exe" }

$beforeRows = Get-RowsFromCsv -Path $sourceCsv
$beforeIds = @{}
foreach ($row in $beforeRows) { if ($row.batch_id) { $beforeIds[[string]$row.batch_id] = $true } }

$oldProfile = [Environment]::GetEnvironmentVariable('SAPLING_PROFILE', 'Process')
$oldThreads = [Environment]::GetEnvironmentVariable('RAYON_NUM_THREADS', 'Process')
$runStarted = (Get-Date).ToString('o')
$exitCode = -1
$stdout = ''
$stderr = ''
try {
    $env:SAPLING_PROFILE = '1'
    $env:RAYON_NUM_THREADS = [string]$Threads
    $process = Start-Process -FilePath $exe -WorkingDirectory $RepoRoot -PassThru -Wait -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $exitCode = $process.ExitCode
    $stdout = if (Test-Path -LiteralPath $stdoutPath) { [IO.File]::ReadAllText($stdoutPath) } else { '' }
    $stderr = if (Test-Path -LiteralPath $stderrPath) { [IO.File]::ReadAllText($stderrPath) } else { '' }
}
finally {
    if ($null -eq $oldProfile) { Remove-Item Env:SAPLING_PROFILE -ErrorAction SilentlyContinue } else { $env:SAPLING_PROFILE = $oldProfile }
    if ($null -eq $oldThreads) { Remove-Item Env:RAYON_NUM_THREADS -ErrorAction SilentlyContinue } else { $env:RAYON_NUM_THREADS = $oldThreads }
}
$runEnded = (Get-Date).ToString('o')

if ($exitCode -ne 0) { throw "Prover exited with code $exitCode. Preserve output logs: $stdoutPath ; $stderrPath" }
if ($stdout -notmatch 'SPEND_PROOF_EXPERIMENT=PASS') { throw "Success marker missing. Preserve logs: $stdoutPath ; $stderrPath" }

$stdoutBatch = [regex]::Match($stdout, '(?m)^batch_id=(\d+)\s*$')
if (-not $stdoutBatch.Success) { throw "Could not parse batch_id from stdout. Preserve logs: $stdoutPath" }
$batchId = $stdoutBatch.Groups[1].Value

$allRows = Get-RowsFromCsv -Path $sourceCsv
$newRows = @($allRows | Where-Object { $_.batch_id -and -not $beforeIds.ContainsKey([string]$_.batch_id) })
$newBatchIds = @($newRows | Select-Object -ExpandProperty batch_id -Unique)
if ($newBatchIds.Count -ne 1 -or [string]$newBatchIds[0] -ne $batchId) {
    throw "The raw prover CSV does not uniquely match stdout batch ID $batchId. Preserve source CSV and logs for inspection."
}
$batchRows = @($newRows | Where-Object { [string]$_.batch_id -eq $batchId } | Sort-Object { [int]$_.run })
if ($batchRows.Count -ne 5) { throw "Expected five prover runs for batch $batchId; got $($batchRows.Count)." }
if (@($batchRows | Where-Object { $_.verified.ToLowerInvariant() -ne 'true' }).Count -ne 0) { throw "At least one proof did not verify in batch $batchId." }
$recordedThreadCounts = @($batchRows | Select-Object -ExpandProperty rayon_threads -Unique)
if ($recordedThreadCounts.Count -ne 1 -or [string]$recordedThreadCounts[0] -ne [string]$Threads) {
    throw "Requested Threads=$Threads but prover CSV recorded rayon_threads=$($recordedThreadCounts -join ','). Preserve logs and investigate."
}

$msmRegex = [regex]'BELLMAN_MSM_PROFILE call_id=(\d+) exponent_count=(\d+) density_map_size=(None|Some\(\d+\)) window=(\d+) task_start_delay_ms=([\d.]+) elapsed_ms=([\d.]+)'
$submitRegex = [regex]'BELLMAN_MSM_SUBMIT_PROFILE call_id=(\d+) submit_elapsed_ms=([\d.]+)'
$stageRegex = [regex]'G16_STAGE_PROFILE circuit_synthesis_constraints_ms=([\d.]+) worker_vk_setup_ms=([\d.]+) qap_fft_h_exponent_prep_ms=([\d.]+) h_query_access_dispatch_ms=([\d.]+) assignment_query_prep_dispatch_ms=([\d.]+) proof_scalar_terms_ms=([\d.]+) wait_and_assembly_ms=([\d.]+) create_proof_body_ms=([\d.]+)'

$msmMatches = $msmRegex.Matches($stderr)
$submitMatches = $submitRegex.Matches($stderr)
$stageMatches = $stageRegex.Matches($stderr)
if ($msmMatches.Count -ne 40) { throw "Expected 40 BELLMAN_MSM_PROFILE records; found $($msmMatches.Count). Preserve logs and do not publish partial profile data." }
if ($submitMatches.Count -ne 40) { throw "Expected 40 BELLMAN_MSM_SUBMIT_PROFILE records; found $($submitMatches.Count). Preserve logs and do not publish partial profile data." }
if ($stageMatches.Count -ne 5) { throw "Expected 5 G16_STAGE_PROFILE records; found $($stageMatches.Count). Preserve logs and do not publish partial profile data." }

$submitByCall = @{}
foreach ($m in $submitMatches) {
    $call = [int]$m.Groups[1].Value
    if ($submitByCall.ContainsKey($call)) { throw "Duplicate submit call ID: $call" }
    $submitByCall[$call] = [double]$m.Groups[2].Value
}

$queries = @(
    @{ Name = 'H_query_G1'; Group = 'G1'; Count = 131071 },
    @{ Name = 'L_query_G1'; Group = 'G1'; Count = 98638 },
    @{ Name = 'A_input_G1'; Group = 'G1'; Count = 8 },
    @{ Name = 'A_aux_G1'; Group = 'G1'; Count = 98638 },
    @{ Name = 'B_G1_input'; Group = 'G1'; Count = 8 },
    @{ Name = 'B_G1_aux'; Group = 'G1'; Count = 98638 },
    @{ Name = 'B_G2_input'; Group = 'G2'; Count = 8 },
    @{ Name = 'B_G2_aux'; Group = 'G2'; Count = 98638 }
)
$msmObjects = @()
$seenCalls = @{}
foreach ($m in $msmMatches) {
    $callId = [int]$m.Groups[1].Value
    if ($seenCalls.ContainsKey($callId)) { throw "Duplicate MSM call ID: $callId" }
    $seenCalls[$callId] = $true
    if (-not $submitByCall.ContainsKey($callId)) { throw "Missing submit timing for MSM call ID $callId" }
    $run = [int][Math]::Floor(($callId - 1) / 8) + 1
    $query = $queries[($callId - 1) % 8]
    $actualExponentCount = [int]$m.Groups[2].Value
    $actualWindow = [int]$m.Groups[4].Value
    $expectedWindow = if ($query.Count -lt 32) { 3 } else { 12 }
    if ($actualExponentCount -ne [int]$query.Count -or $actualWindow -ne $expectedWindow) {
        throw "Call $callId does not match the expected Groth16 query mapping ($($query.Name)): exponent_count=$actualExponentCount, window=$actualWindow."
    }
    $msmObjects += [PSCustomObject]@{
        batch_id = $batchId
        run = $run
        call_id = $callId
        query = $query.Name
        group = $query.Group
        exponent_count = [int]$m.Groups[2].Value
        density_map_size = $m.Groups[3].Value
        window = [int]$m.Groups[4].Value
        task_start_delay_ms = [double]$m.Groups[5].Value
        elapsed_ms = [double]$m.Groups[6].Value
        submit_elapsed_ms = [double]$submitByCall[$callId]
        threads = $Threads
        build_profile = 'release'
    }
}
if ($seenCalls.Count -ne 40 -or @($seenCalls.Keys | Where-Object { $_ -lt 1 -or $_ -gt 40 }).Count -gt 0) { throw 'MSM call ID set is incomplete or outside 1..40.' }

$stageFieldNames = @(
    'circuit_synthesis_constraints_ms', 'worker_vk_setup_ms', 'qap_fft_h_exponent_prep_ms',
    'h_query_access_dispatch_ms', 'assignment_query_prep_dispatch_ms', 'proof_scalar_terms_ms',
    'wait_and_assembly_ms', 'create_proof_body_ms'
)
$stageObjects = @()
$perRun = @()
for ($i = 0; $i -lt $stageMatches.Count; $i++) {
    $m = $stageMatches[$i]
    $vals = @(); for ($g = 1; $g -le 8; $g++) { $vals += [double]$m.Groups[$g].Value }
    $stageObj = [ordered]@{ batch_id = $batchId; run = $i + 1 }
    for ($g = 0; $g -lt $stageFieldNames.Count; $g++) { $stageObj[$stageFieldNames[$g]] = $vals[$g] }
    $stageObjects += [PSCustomObject]$stageObj
    $stageSum = ($vals[0..6] | Measure-Object -Sum).Sum
    $bodyMs = $vals[7]
    $runMsm = @($msmObjects | Where-Object { $_.run -eq ($i + 1) })
    if ($runMsm.Count -ne 8) { throw "Run $($i+1) has $($runMsm.Count) MSM calls; expected 8." }
    $msmSum = [double](($runMsm | Measure-Object -Property elapsed_ms -Sum).Sum)
    $proveMs = [double]$batchRows[$i].prove_ms
    $perRun += [PSCustomObject]@{
        batch_id = $batchId
        run = $i + 1
        prove_ms = $proveMs
        create_proof_body_ms = $bodyMs
        stage_sum_ms = [double]$stageSum
        stage_sum_minus_body_ms = [double]($stageSum - $bodyMs)
        msm_elapsed_sum_ms = $msmSum
        msm_share_of_body_pct = 100.0 * $msmSum / $bodyMs
        msm_share_of_outer_prove_pct = 100.0 * $msmSum / $proveMs
        all_verified = 'true'
    }
}

$maxStageClosureMs = [double](@($perRun | ForEach-Object { [Math]::Abs([double]$_.stage_sum_minus_body_ms) } | Measure-Object -Maximum).Maximum)
if ($maxStageClosureMs -gt 0.01) {
    throw "Stage timing does not close within 0.01 ms (max difference $maxStageClosureMs ms). Preserve logs and investigate before treating this batch as complete."
}

$stageCsv = Join-Path $rawDir "sapling_spend_stage_profile_$batchId.csv"
$msmCsv = Join-Path $rawDir "sapling_spend_msm_call_profile_$batchId.csv"
$summaryCsv = Join-Path $rawDir "sapling_spend_profile_run_summary_$batchId.csv"
$metadataPath = Join-Path $metadataDir "sapling_spend_combined_profile_$batchId.md"
if ((Test-Path $stageCsv) -or (Test-Path $msmCsv) -or (Test-Path $summaryCsv) -or (Test-Path $metadataPath)) {
    throw "Output artifact for batch $batchId already exists. Do not overwrite previous experiment data."
}
$stageObjects | Export-Csv -LiteralPath $stageCsv -NoTypeInformation -Encoding UTF8
$msmObjects | Export-Csv -LiteralPath $msmCsv -NoTypeInformation -Encoding UTF8
$perRun | Export-Csv -LiteralPath $summaryCsv -NoTypeInformation -Encoding UTF8

$system = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue
$cpu = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }) -join '; '
$os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue
$saplingRepo = 'D:\Research\zcash-sapling-crypto'
$saplingCommit = 'not available'
if (Test-Path -LiteralPath (Join-Path $saplingRepo '.git')) {
    try { $saplingCommit = (& git -C $saplingRepo rev-parse HEAD 2>&1).ToString().Trim(); if ($LASTEXITCODE -ne 0) { throw $saplingCommit } } catch { $saplingCommit = 'unavailable: ' + $_.Exception.Message }
}
$threadMedian = Get-Median -Values @($batchRows | ForEach-Object { [double]$_.prove_ms })
$bodyMedian = Get-Median -Values @($stageObjects | ForEach-Object { [double]$_.create_proof_body_ms })
$shareMedian = Get-Median -Values @($perRun | ForEach-Object { [double]$_.msm_share_of_body_pct })
$submitMedian = Get-Median -Values @($msmObjects | ForEach-Object { [double]$_.submit_elapsed_ms })
$taskDelayMedian = Get-Median -Values @($msmObjects | ForEach-Object { [double]$_.task_start_delay_ms })
$msmElapsedMedian = Get-Median -Values @($msmObjects | ForEach-Object { [double]$_.elapsed_ms })

$dependencyStatus = 'not recorded'
if (Test-Path -LiteralPath (Join-Path $saplingRepo '.git')) {
    $dependencyStatus = ((& git -C $saplingRepo status --porcelain 2>&1) -join "`n").Trim(); if ($LASTEXITCODE -ne 0) { throw "Cannot query Sapling dependency git status: $dependencyStatus" }
    if ([string]::IsNullOrWhiteSpace($dependencyStatus)) { $dependencyStatus = 'clean' } else { $dependencyStatus = 'dirty: ' + $dependencyStatus }
}

$report = @"
# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: $batchId
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=$Threads; SAPLING_PROFILE=1
- Run start: $runStarted
- Run end: $runEnded
- Repository branch: $branch
- Engineering repository HEAD at start: $head
- Engineering worktree dirty at start: $dirtyAtStart
- Engineering source commit is the recorded HEAD; profiler worktree status at start: $initialStatus
- Sapling dependency repository: $saplingRepo
- Sapling dependency HEAD: $saplingCommit
- Sapling dependency worktree: $dependencyStatus
- CPU: $cpu
- Installed physical memory (bytes): $($system.TotalPhysicalMemory)
- OS: $($os.Caption) ($($os.Version), build $($os.BuildNumber))
- Rust: $((&rustc --version 2>&1) -join ' ')
- Cargo: $((&cargo --version 2>&1) -join ' ')

## Parameter identity

- Parameter path: $ParameterPath
- Parameter bytes: $($parameterItem.Length)
- Parameter SHA-256: $parameterHash

## Instrumented source identity

- vendor/bellman/src/multiexp.rs SHA-256: $(Get-Sha256 $bellmanSource)
- vendor/groth16/src/prover.rs SHA-256: $(Get-Sha256 $groth16Source)
- spend_prover_smoke.rs SHA-256: $(Get-Sha256 (Join-Path $RepoRoot 'experiments\prover-smoke\src\bin\spend_prover_smoke.rs'))
- Runner SHA-256: $(Get-Sha256 $PSCommandPath)
- Cargo manifest SHA-256: $(Get-Sha256 $manifest)

## Result summary

- Outer Prove median (ms): $([Math]::Round($threadMedian, 3))
- create_proof_body_ms median (ms): $([Math]::Round($bodyMedian, 3))
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: $([Math]::Round($shareMedian, 2))%
- task_start_delay_ms median across MSM calls (ms): $([Math]::Round($taskDelayMedian, 3))
- elapsed_ms median across MSM calls (ms): $([Math]::Round($msmElapsedMedian, 3))
- submit_elapsed_ms median across MSM calls (ms): $([Math]::Round($submitMedian, 3))

The three MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_release.csv (filtered by this batch ID)
- Prover run CSV SHA-256: $(Get-Sha256 $sourceCsv)
- Stage CSV: experiments/raw/csv/$(Split-Path $stageCsv -Leaf)
- Stage CSV SHA-256: $(Get-Sha256 $stageCsv)
- MSM call CSV (includes submit timing): experiments/raw/csv/$(Split-Path $msmCsv -Leaf)
- MSM call CSV SHA-256: $(Get-Sha256 $msmCsv)
- Per-run ratio summary CSV: experiments/raw/csv/$(Split-Path $summaryCsv -Leaf)
- Per-run ratio summary CSV SHA-256: $(Get-Sha256 $summaryCsv)
- Prover stdout: experiments/raw/logs/$(Split-Path $stdoutPath -Leaf)
- Prover stdout SHA-256: $(Get-Sha256 $stdoutPath)
- Prover stderr / source instrumentation records: experiments/raw/logs/$(Split-Path $stderrPath -Leaf)
- Prover stderr SHA-256: $(Get-Sha256 $stderrPath)
- Build stdout: experiments/raw/logs/$(Split-Path $buildStdout -Leaf)
- Build stdout SHA-256: $(Get-Sha256 $buildStdout)
- Build stderr: experiments/raw/logs/$(Split-Path $buildStderr -Leaf)
- Build stderr SHA-256: $(Get-Sha256 $buildStderr)

## Validation

- New raw prover batch rows: $($batchRows.Count) / 5
- MSM call records: $($msmObjects.Count) / 40
- Submit timing records: $($submitMatches.Count) / 40
- Stage timing records: $($stageObjects.Count) / 5
- Proof verification: 5/5 passed
- Maximum absolute per-run stage-sum minus body timing (ms): $([Math]::Round($maxStageClosureMs, 3))

No algorithm changes were made as part of this run. Results are diagnostic profile data and are not an optimization claim.
"@
[System.IO.File]::WriteAllText($metadataPath, $report, [System.Text.UTF8Encoding]::new($false))

Write-Host ''
Write-Host '=== Spend combined profile complete ==='
Write-Host "Batch ID: $batchId"
Write-Host "Outer Prove median: $([Math]::Round($threadMedian, 3)) ms"
Write-Host "Body median: $([Math]::Round($bodyMedian, 3)) ms"
Write-Host "MSM elapsed/body share median: $([Math]::Round($shareMedian, 2))%"
Write-Host "Stage CSV: $stageCsv"
Write-Host "MSM CSV: $msmCsv"
Write-Host "Per-run summary: $summaryCsv"
Write-Host "Metadata report: $metadataPath"
Write-Host 'All logs are preserved under experiments/raw/logs.'
