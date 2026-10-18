[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$ParameterPath = '',
    [ValidateRange(1, 128)]
    [int]$Threads = 1,
    [ValidateSet('enabled', 'disabled')]
    [string]$BranchCounters = 'enabled',
    [ValidateSet('enabled', 'disabled')]
    [string]$InnerStageTiming = 'enabled',
    [switch]$ForceAsyncWorker,
    # Optional processor-affinity mask for the prover process (0 = leave the OS
    # scheduler free). On hybrid CPUs, leaving it free lets the single-threaded
    # worker land on a P-core or an E-core, which changes prove time by ~2x.
    [long]$AffinityMask = 0,
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,39}$')]
    [string]$RunDataLabel = 'release',
    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Resolve the repository root after script initialization.
# Avoid using $PSScriptRoot inside a parameter default expression.
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $runnerPath = $MyInvocation.MyCommand.Path

    if ([string]::IsNullOrWhiteSpace($runnerPath)) {
        throw "Cannot resolve runner script path. Pass -RepoRoot explicitly."
    }

    $runnerDirectory = Split-Path -Parent $runnerPath
    $RepoRoot = (
        Resolve-Path -LiteralPath (Join-Path $runnerDirectory '..')
    ).Path
}

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
    if ($sorted.Count -eq 0) {
        throw 'Cannot calculate median of an empty set.'
    }

    $mid = [int][Math]::Floor($sorted.Count / 2)
    if (($sorted.Count % 2) -eq 1) {
        return [double]$sorted[$mid]
    }

    return ([double]$sorted[$mid - 1] + [double]$sorted[$mid]) / 2.0
}

function Get-RowsFromCsv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "CSV not found: $Path"
    }

    return @(Import-Csv -LiteralPath $Path)
}

# Resolve paths.
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

if ([string]::IsNullOrWhiteSpace($ParameterPath)) {
    if (-not [string]::IsNullOrWhiteSpace($env:ZCASH_PARAMS_DIR)) {
        $parameterDirectory = $env:ZCASH_PARAMS_DIR
    }
    else {
        $parameterDirectory = 'D:\Research\zcash-params'
    }

    $ParameterPath = Join-Path $parameterDirectory 'sapling-spend.params'
}

$ParameterPath = [System.IO.Path]::GetFullPath($ParameterPath)

$manifest = Join-Path $RepoRoot 'experiments\prover-smoke\Cargo.toml'
$exe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\spend_prover_smoke.exe'
$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
$metadataDir = Join-Path $RepoRoot 'experiments\metadata'
if ($RunDataLabel -eq 'release') {
    $sourceCsv = Join-Path $rawDir 'sapling_spend_prover_runs_release.csv'
}
else {
    $sourceCsv = Join-Path $rawDir ("sapling_spend_prover_runs_{0}.csv" -f $RunDataLabel)
}
$bellmanSource = Join-Path $RepoRoot 'vendor\bellman\src\multiexp.rs'
$workerSource = Join-Path $RepoRoot 'vendor\bellman\src\multicore.rs'
$groth16Source = Join-Path $RepoRoot 'vendor\groth16\src\prover.rs'

$requiredPaths = @($manifest, $ParameterPath, $bellmanSource, $workerSource, $groth16Source)
if ($RunDataLabel -eq 'release') {
    $requiredPaths += $sourceCsv
}
foreach ($path in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file not found: $path"
    }
}

# Record engineering repository identity and worktree status before building.
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

if ($dirtyAtStart) {
    $worktreeStatusLabel = 'dirty'
    $worktreeStatusDetails = $initialStatus -replace "`r?`n", '; '
}
else {
    $worktreeStatusLabel = 'clean'
    $worktreeStatusDetails = 'none'
}

# Validate the Spend parameter file.
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

# Resolve the dependency identity from Cargo's locked dependency graph.
# Do not infer the actual dependency revision from a separate local checkout.
$metadataOutput = & $cargo metadata `
    --format-version 1 `
    --locked `
    --manifest-path $manifest 2>$null

if ($LASTEXITCODE -ne 0) {
    throw 'cargo metadata failed. Verify Cargo dependencies and Cargo.lock before profiling.'
}

$metadataText = ($metadataOutput -join "`n")

try {
    $cargoMetadata = $metadataText | ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "Could not parse cargo metadata output: $($_.Exception.Message)"
}

$saplingPackages = @(
    $cargoMetadata.packages |
    Where-Object {
        $_.name -eq 'sapling-crypto' -and $_.version -eq '0.9.0'
    }
)

if ($saplingPackages.Count -ne 1) {
    throw "Expected exactly one resolved sapling-crypto 0.9.0 package; found $($saplingPackages.Count)."
}

$saplingSource = [string]$saplingPackages[0].source

$saplingSourcePattern = (
    '^git\+https://github\.com/zcash/sapling-crypto' +
    '(?:\.git)?(?:\?.*)?#([0-9a-f]{40})$'
)

$saplingSourceMatch = [regex]::Match(
    $saplingSource,
    $saplingSourcePattern
)

if (-not $saplingSourceMatch.Success) {
    throw "sapling-crypto is not resolved from the expected official Git source: '$saplingSource'."
}

$saplingCommit = $saplingSourceMatch.Groups[1].Value
$saplingRepoUrl = 'https://github.com/zcash/sapling-crypto'

# Build with --locked so the profiling build cannot silently rewrite Cargo.lock.
$buildArgs = 'build --release --locked --manifest-path "{0}" --bin spend_prover_smoke' -f $manifest

$buildProc = Start-Process `
    -FilePath $cargo `
    -ArgumentList $buildArgs `
    -WorkingDirectory $RepoRoot `
    -PassThru `
    -Wait `
    -RedirectStandardOutput $buildStdout `
    -RedirectStandardError $buildStderr

if ($buildProc.ExitCode -ne 0) {
    throw "Release build failed with exit code $($buildProc.ExitCode). Build logs preserved: $buildStdout ; $buildStderr"
}

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Release executable missing after build: $exe"
}

# Create a dedicated labeled data CSV only after recording that the starting
# source worktree was clean. This file is never the formal release baseline.
if (-not (Test-Path -LiteralPath $sourceCsv -PathType Leaf)) {
    $csvHeader = "batch_id,run,params_read_validate_ms,prepare_vk_ms,input_prep_ms,prove_ms,verify_ms,proof_bytes,verified,rayon_threads,build_profile`n"
    [System.IO.File]::WriteAllText($sourceCsv, $csvHeader, [System.Text.UTF8Encoding]::new($false))
}

# Snapshot existing batch IDs so this run cannot accidentally reuse old records.
$beforeRows = Get-RowsFromCsv -Path $sourceCsv
$beforeIds = @{}

foreach ($row in $beforeRows) {
    if ($row.batch_id) {
        $beforeIds[[string]$row.batch_id] = $true
    }
}

$oldProfile = [Environment]::GetEnvironmentVariable('SAPLING_PROFILE', 'Process')
$oldThreads = [Environment]::GetEnvironmentVariable('RAYON_NUM_THREADS', 'Process')
$oldSpendParams = [Environment]::GetEnvironmentVariable('SAPLING_SPEND_PARAMS', 'Process')
$oldBranchCounters = [Environment]::GetEnvironmentVariable('SAPLING_MSM_BRANCH_COUNTS', 'Process')
$oldInnerStageTiming = [Environment]::GetEnvironmentVariable('SAPLING_MSM_STAGE_TIMING', 'Process')
$oldForceAsyncWorker = [Environment]::GetEnvironmentVariable('BELLMAN_FORCE_ASYNC_WORKER', 'Process')
$oldProverRunsCsv = [Environment]::GetEnvironmentVariable('SAPLING_PROVER_RUNS_CSV', 'Process')

$runStarted = (Get-Date).ToString('o')
$exitCode = -1
$stdout = ''
$stderr = ''

try {
    $env:SAPLING_PROFILE = '1'
    $env:RAYON_NUM_THREADS = [string]$Threads
    $env:SAPLING_SPEND_PARAMS = $ParameterPath
    $env:SAPLING_PROVER_RUNS_CSV = $sourceCsv
    if ($BranchCounters -eq 'enabled') {
        $env:SAPLING_MSM_BRANCH_COUNTS = '1'
    }
    else {
        $env:SAPLING_MSM_BRANCH_COUNTS = '0'
    }
    if ($InnerStageTiming -eq 'enabled') {
        $env:SAPLING_MSM_STAGE_TIMING = '1'
    }
    else {
        $env:SAPLING_MSM_STAGE_TIMING = '0'
    }
    if ($ForceAsyncWorker) {
        $env:BELLMAN_FORCE_ASYNC_WORKER = '1'
    }
    else {
        $env:BELLMAN_FORCE_ASYNC_WORKER = '0'
    }

    # Use System.Diagnostics.Process directly instead of Start-Process: it lets
    # us set processor affinity right after launch and still read the exit code
    # reliably. (Start-Process -PassThru without -Wait does not populate
    # ExitCode on Windows PowerShell 5.1.)
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $exe
    $startInfo.WorkingDirectory = $RepoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()

    if ($AffinityMask -gt 0) {
        try {
            $process.ProcessorAffinity = [IntPtr]$AffinityMask
        }
        catch {
            throw "Failed to set processor affinity mask $AffinityMask on the prover process: $($_.Exception.Message)"
        }
    }

    # Drain both pipes concurrently to avoid deadlocking on a full pipe buffer.
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()

    $stdout = $stdoutTask.Result
    $stderr = $stderrTask.Result
    $exitCode = $process.ExitCode

    [IO.File]::WriteAllText($stdoutPath, $stdout, [System.Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($stderrPath, $stderr, [System.Text.UTF8Encoding]::new($false))
}
finally {
    if ($null -eq $oldProfile) {
        Remove-Item Env:SAPLING_PROFILE -ErrorAction SilentlyContinue
    }
    else {
        $env:SAPLING_PROFILE = $oldProfile
    }

    if ($null -eq $oldThreads) {
        Remove-Item Env:RAYON_NUM_THREADS -ErrorAction SilentlyContinue
    }
    else {
        $env:RAYON_NUM_THREADS = $oldThreads
    }

    if ($null -eq $oldSpendParams) {
        Remove-Item Env:SAPLING_SPEND_PARAMS -ErrorAction SilentlyContinue
    }
    else {
        $env:SAPLING_SPEND_PARAMS = $oldSpendParams
    }

    if ($null -eq $oldBranchCounters) {
        Remove-Item Env:SAPLING_MSM_BRANCH_COUNTS -ErrorAction SilentlyContinue
    }
    else {
        $env:SAPLING_MSM_BRANCH_COUNTS = $oldBranchCounters
    }

    if ($null -eq $oldInnerStageTiming) {
        Remove-Item Env:SAPLING_MSM_STAGE_TIMING -ErrorAction SilentlyContinue
    }
    else {
        $env:SAPLING_MSM_STAGE_TIMING = $oldInnerStageTiming
    }

    if ($null -eq $oldForceAsyncWorker) {
        Remove-Item Env:BELLMAN_FORCE_ASYNC_WORKER -ErrorAction SilentlyContinue
    }
    else {
        $env:BELLMAN_FORCE_ASYNC_WORKER = $oldForceAsyncWorker
    }

    if ($null -eq $oldProverRunsCsv) {
        Remove-Item Env:SAPLING_PROVER_RUNS_CSV -ErrorAction SilentlyContinue
    }
    else {
        $env:SAPLING_PROVER_RUNS_CSV = $oldProverRunsCsv
    }
}

$runEnded = (Get-Date).ToString('o')

if ($exitCode -ne 0) {
    throw "Prover exited with code $exitCode. Preserve output logs: $stdoutPath ; $stderrPath"
}

if ($stdout -notmatch 'SPEND_PROOF_EXPERIMENT=PASS') {
    throw "Success marker missing. Preserve logs: $stdoutPath ; $stderrPath"
}

$stdoutBatch = [regex]::Match($stdout, '(?m)^batch_id=(\d+)\s*$')

if (-not $stdoutBatch.Success) {
    throw "Could not parse batch_id from stdout. Preserve logs: $stdoutPath"
}

$batchId = $stdoutBatch.Groups[1].Value

$allRows = Get-RowsFromCsv -Path $sourceCsv
$newRows = @(
    $allRows |
    Where-Object {
        $_.batch_id -and
        -not $beforeIds.ContainsKey([string]$_.batch_id)
    }
)

$newBatchIds = @($newRows | Select-Object -ExpandProperty batch_id -Unique)

if ($newBatchIds.Count -ne 1 -or [string]$newBatchIds[0] -ne $batchId) {
    throw "The raw prover CSV does not uniquely match stdout batch ID $batchId. Preserve source CSV and logs for inspection."
}

$batchRows = @(
    $newRows |
    Where-Object { [string]$_.batch_id -eq $batchId } |
    Sort-Object { [int]$_.run }
)

if ($batchRows.Count -ne 5) {
    throw "Expected five prover runs for batch $batchId; got $($batchRows.Count)."
}

if (@($batchRows | Where-Object { $_.verified.ToLowerInvariant() -ne 'true' }).Count -ne 0) {
    throw "At least one proof did not verify in batch $batchId."
}

$recordedThreadCounts = @($batchRows | Select-Object -ExpandProperty rayon_threads -Unique)

if ($recordedThreadCounts.Count -ne 1 -or [string]$recordedThreadCounts[0] -ne [string]$Threads) {
    throw "Requested Threads=$Threads but prover CSV recorded rayon_threads=$($recordedThreadCounts -join ','). Preserve logs and investigate."
}

$msmRegex = [regex]'BELLMAN_MSM_PROFILE call_id=(\d+) exponent_count=(\d+) density_map_size=(None|Some\(\d+\)) window=(\d+) task_start_delay_ms=([\d.]+) elapsed_ms=([\d.]+)'
$submitRegex = [regex]'BELLMAN_MSM_SUBMIT_PROFILE call_id=(\d+) submit_elapsed_ms=([\d.]+)'
$stageRegex = [regex]'G16_STAGE_PROFILE circuit_synthesis_constraints_ms=([\d.]+) worker_vk_setup_ms=([\d.]+) qap_fft_h_exponent_prep_ms=([\d.]+) h_query_access_dispatch_ms=([\d.]+) assignment_query_prep_dispatch_ms=([\d.]+) proof_scalar_terms_ms=([\d.]+) wait_and_assembly_ms=([\d.]+) create_proof_body_ms=([\d.]+)'
$innerStageRegex = [regex]'BELLMAN_MSM_STAGE_PROFILE call_id=(\d+) exponent_count=(\d+) window=(\d+) bucket_count=(\d+) chunk_count=(\d+) bucket_element_size_bytes=(\d+) exponent_chunk_prep_ms=([\d.]+) chunk_parallel_wall_ms=([\d.]+) bucket_init_sum_ms=([\d.]+) bucket_init_max_ms=([\d.]+) bucket_fill_sum_ms=([\d.]+) bucket_fill_max_ms=([\d.]+) bucket_reduce_sum_ms=([\d.]+) bucket_reduce_max_ms=([\d.]+) max_concurrent_chunk_regions=(\d+) bucket_payload_at_max_concurrency_estimate_bytes=(\d+) result_merge_ms=([\d.]+)'
$workerFallbackRegex = [regex]'BELLMAN_WORKER_FALLBACK previous_count=(\d+) max_count=(\d+) rayon_threads=(\d+)'
$workerAsyncOverrideRegex = [regex]'BELLMAN_WORKER_ASYNC_OVERRIDE previous_count=(\d+) max_count=(\d+) rayon_threads=(\d+)'

$msmMatches = $msmRegex.Matches($stderr)
$submitMatches = $submitRegex.Matches($stderr)
$stageMatches = $stageRegex.Matches($stderr)
$innerStageMatches = $innerStageRegex.Matches($stderr)
$workerFallbackMatches = $workerFallbackRegex.Matches($stderr)
$workerAsyncOverrideMatches = $workerAsyncOverrideRegex.Matches($stderr)

if ($msmMatches.Count -ne 40) {
    throw "Expected 40 BELLMAN_MSM_PROFILE records; found $($msmMatches.Count). Preserve logs and do not publish partial profile data."
}

if ($submitMatches.Count -ne 40) {
    throw "Expected 40 BELLMAN_MSM_SUBMIT_PROFILE records; found $($submitMatches.Count). Preserve logs and do not publish partial profile data."
}

if ($stageMatches.Count -ne 5) {
    throw "Expected 5 G16_STAGE_PROFILE records; found $($stageMatches.Count). Preserve logs and do not publish partial profile data."
}

if ($innerStageMatches.Count -ne 40) {
    throw "Expected 40 BELLMAN_MSM_STAGE_PROFILE records; found $($innerStageMatches.Count). Preserve logs and do not publish partial profile data."
}

$submitByCall = @{}

foreach ($m in $submitMatches) {
    $call = [int]$m.Groups[1].Value

    if ($submitByCall.ContainsKey($call)) {
        throw "Duplicate submit call ID: $call"
    }

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

    if ($seenCalls.ContainsKey($callId)) {
        throw "Duplicate MSM call ID: $callId"
    }

    $seenCalls[$callId] = $true

    if (-not $submitByCall.ContainsKey($callId)) {
        throw "Missing submit timing for MSM call ID $callId"
    }

    $run = [int][Math]::Floor(($callId - 1) / 8) + 1
    $query = $queries[($callId - 1) % 8]
    $actualExponentCount = [int]$m.Groups[2].Value
    $actualWindow = [int]$m.Groups[4].Value
    $expectedWindow = if ($query.Count -lt 32) { 3 } else { 12 }

    if ($actualExponentCount -ne [int]$query.Count -or $actualWindow -ne $expectedWindow) {
        throw "Call $callId does not match the expected Groth16 query mapping ($($query.Name)): exponent_count=$actualExponentCount, window=$actualWindow."
    }

    $msmObjects += [PSCustomObject]@{
        batch_id            = $batchId
        run                 = $run
        call_id             = $callId
        query               = $query.Name
        group               = $query.Group
        exponent_count      = [int]$m.Groups[2].Value
        density_map_size    = $m.Groups[3].Value
        window              = [int]$m.Groups[4].Value
        task_start_delay_ms = [double]$m.Groups[5].Value
        elapsed_ms          = [double]$m.Groups[6].Value
        submit_elapsed_ms   = [double]$submitByCall[$callId]
        threads             = $Threads
        build_profile       = 'release'
    }
}

if ($seenCalls.Count -ne 40 -or @($seenCalls.Keys | Where-Object { $_ -lt 1 -or $_ -gt 40 }).Count -gt 0) {
    throw 'MSM call ID set is incomplete or outside 1..40.'
}

$innerStageObjects = @()
$seenInnerStageCalls = @{}

foreach ($m in $innerStageMatches) {
    $callId = [int]$m.Groups[1].Value

    if ($callId -lt 1 -or $callId -gt 40) {
        throw "Inner-stage call ID $callId is outside expected range 1..40."
    }
    if ($seenInnerStageCalls.ContainsKey($callId)) {
        throw "Duplicate inner-stage call ID: $callId"
    }
    $seenInnerStageCalls[$callId] = $true

    $run = [int][Math]::Floor(($callId - 1) / 8) + 1
    $query = $queries[($callId - 1) % 8]

    $exponentCount = [int]$m.Groups[2].Value
    $window = [int]$m.Groups[3].Value
    $bucketCount = [int]$m.Groups[4].Value
    $chunkCount = [int]$m.Groups[5].Value
    $elementSize = [int]$m.Groups[6].Value
    $expectedWindow = if ($query.Count -lt 32) { 3 } else { 12 }
    $expectedBucketCount = [int]([Math]::Pow(2, $expectedWindow) - 1)
    $expectedChunkCount = [int][Math]::Ceiling(255.0 / $expectedWindow)
    $expectedElementSize = if ($query.Group -eq 'G1') { 144 } else { 288 }
    $maxConcurrent = [int]$m.Groups[15].Value
    $bucketPayloadEstimate = [long]$m.Groups[16].Value
    $expectedBucketPayloadEstimate = [long]$maxConcurrent * $bucketCount * $elementSize

    if ($exponentCount -ne [int]$query.Count) {
        throw "Inner-stage call $callId ($($query.Name)) exponent_count mismatch: $exponentCount."
    }
    if ($window -ne $expectedWindow -or $bucketCount -ne $expectedBucketCount) {
        throw "Inner-stage call $callId ($($query.Name)) has unexpected window/bucket count."
    }
    if ($chunkCount -ne $expectedChunkCount) {
        throw "Inner-stage call $callId ($($query.Name)) chunk_count mismatch: $chunkCount; expected $expectedChunkCount."
    }
    if ($elementSize -ne $expectedElementSize) {
        throw "Inner-stage call $callId ($($query.Name)) element size mismatch: $elementSize; expected $expectedElementSize."
    }
    if ($maxConcurrent -lt 1 -or $maxConcurrent -gt $chunkCount) {
        throw "Inner-stage call $callId ($($query.Name)) reports invalid concurrent chunk count: $maxConcurrent."
    }
    if ($bucketPayloadEstimate -ne $expectedBucketPayloadEstimate) {
        throw "Inner-stage call $callId ($($query.Name)) bucket payload estimate mismatch."
    }

    $innerStageObjects += [PSCustomObject]@{
        batch_id = $batchId
        run = $run
        call_id = $callId
        query = $query.Name
        group = $query.Group
        exponent_count = $exponentCount
        window = $window
        bucket_count = $bucketCount
        chunk_count = $chunkCount
        bucket_element_size_bytes = $elementSize
        exponent_chunk_prep_ms = [double]$m.Groups[7].Value
        chunk_parallel_wall_ms = [double]$m.Groups[8].Value
        bucket_init_sum_ms = [double]$m.Groups[9].Value
        bucket_init_max_ms = [double]$m.Groups[10].Value
        bucket_fill_sum_ms = [double]$m.Groups[11].Value
        bucket_fill_max_ms = [double]$m.Groups[12].Value
        bucket_reduce_sum_ms = [double]$m.Groups[13].Value
        bucket_reduce_max_ms = [double]$m.Groups[14].Value
        max_concurrent_chunk_regions = $maxConcurrent
        bucket_payload_at_max_concurrency_estimate_bytes = $bucketPayloadEstimate
        result_merge_ms = [double]$m.Groups[17].Value
        threads = $Threads
        build_profile = 'release'
    }
}

if ($seenInnerStageCalls.Count -ne 40) {
    throw "Expected 40 unique inner-stage call IDs; found $($seenInnerStageCalls.Count)."
}

if ($Threads -eq 1 -and $ForceAsyncWorker) {
    if ($workerFallbackMatches.Count -ne 0) {
        throw "Forced-async batch still emitted $($workerFallbackMatches.Count) fallback events."
    }
    if ($workerAsyncOverrideMatches.Count -eq 0) {
        throw 'Forced-async mode did not record any fallback override; the intervention was not shown to activate.'
    }
}
elseif ($Threads -eq 1) {
    if ($workerFallbackMatches.Count -eq 0) {
        throw 'One-thread control emitted no worker fallback events; the control condition was not shown to activate.'
    }
    if ($workerAsyncOverrideMatches.Count -ne 0) {
        throw "Control batch unexpectedly emitted $($workerAsyncOverrideMatches.Count) forced-async override events."
    }
}

$innerStageSummaryObjects = @()
foreach ($query in $queries) {
    $queryRows = @(
        $innerStageObjects |
        Where-Object { $_.query -eq $query.Name } |
        Sort-Object run
    )
    if ($queryRows.Count -ne 5) {
        throw "Expected five inner-stage records for $($query.Name); found $($queryRows.Count)."
    }

    $prep = @($queryRows | ForEach-Object { [double]$_.exponent_chunk_prep_ms })
    $wall = @($queryRows | ForEach-Object { [double]$_.chunk_parallel_wall_ms })
    $init = @($queryRows | ForEach-Object { [double]$_.bucket_init_sum_ms })
    $fill = @($queryRows | ForEach-Object { [double]$_.bucket_fill_sum_ms })
    $reduce = @($queryRows | ForEach-Object { [double]$_.bucket_reduce_sum_ms })
    $merge = @($queryRows | ForEach-Object { [double]$_.result_merge_ms })
    $concurrent = @($queryRows | ForEach-Object { [double]$_.max_concurrent_chunk_regions })
    $bucketEstimate = @($queryRows | ForEach-Object { [double]$_.bucket_payload_at_max_concurrency_estimate_bytes })

    $innerStageSummaryObjects += [PSCustomObject]@{
        batch_id = $batchId
        query = $query.Name
        group = $query.Group
        exponent_count = $query.Count
        window = [int]$queryRows[0].window
        bucket_count = [int]$queryRows[0].bucket_count
        chunk_count = [int]$queryRows[0].chunk_count
        bucket_element_size_bytes = [int]$queryRows[0].bucket_element_size_bytes
        runs = $queryRows.Count
        median_exponent_chunk_prep_ms = Get-Median -Values $prep
        median_chunk_parallel_wall_ms = Get-Median -Values $wall
        median_bucket_init_sum_ms = Get-Median -Values $init
        median_bucket_fill_sum_ms = Get-Median -Values $fill
        median_bucket_reduce_sum_ms = Get-Median -Values $reduce
        median_result_merge_ms = Get-Median -Values $merge
        median_max_concurrent_chunk_regions = Get-Median -Values $concurrent
        max_concurrent_chunk_regions_observed = [int](($queryRows | Measure-Object -Property max_concurrent_chunk_regions -Maximum).Maximum)
        median_bucket_payload_estimate_bytes = Get-Median -Values $bucketEstimate
        max_bucket_payload_estimate_bytes = [long](($queryRows | Measure-Object -Property bucket_payload_at_max_concurrency_estimate_bytes -Maximum).Maximum)
        note = $(if ($InnerStageTiming -eq 'enabled') {
            'Fine-grained stage timers enabled. Stage sums aggregate chunk timings; chunk_parallel_wall_ms is wall time. Payload estimate is not measured process peak memory.'
        }
        else {
            'Fine-grained stage timers disabled (SAPLING_MSM_STAGE_TIMING=0); phase timing fields are zero placeholders. Active chunk counts and payload estimates remain instrumented; payload estimate is not measured process peak memory.'
        })
    }
}

$stageFieldNames = @(
    'circuit_synthesis_constraints_ms',
    'worker_vk_setup_ms',
    'qap_fft_h_exponent_prep_ms',
    'h_query_access_dispatch_ms',
    'assignment_query_prep_dispatch_ms',
    'proof_scalar_terms_ms',
    'wait_and_assembly_ms',
    'create_proof_body_ms'
)

$stageObjects = @()
$perRun = @()

for ($i = 0; $i -lt $stageMatches.Count; $i++) {
    $m = $stageMatches[$i]
    $vals = @()

    for ($g = 1; $g -le 8; $g++) {
        $vals += [double]$m.Groups[$g].Value
    }

    $stageObj = [ordered]@{
        batch_id = $batchId
        run      = $i + 1
    }

    for ($g = 0; $g -lt $stageFieldNames.Count; $g++) {
        $stageObj[$stageFieldNames[$g]] = $vals[$g]
    }

    $stageObjects += [PSCustomObject]$stageObj

    $stageSum = ($vals[0..6] | Measure-Object -Sum).Sum
    $bodyMs = $vals[7]
    $runMsm = @($msmObjects | Where-Object { $_.run -eq ($i + 1) })

    if ($runMsm.Count -ne 8) {
        throw "Run $($i + 1) has $($runMsm.Count) MSM calls; expected 8."
    }

    $msmSum = [double](($runMsm | Measure-Object -Property elapsed_ms -Sum).Sum)
    $proveMs = [double]$batchRows[$i].prove_ms

    $perRun += [PSCustomObject]@{
        batch_id                     = $batchId
        run                          = $i + 1
        prove_ms                     = $proveMs
        create_proof_body_ms         = $bodyMs
        stage_sum_ms                 = [double]$stageSum
        stage_sum_minus_body_ms      = [double]($stageSum - $bodyMs)
        msm_elapsed_sum_ms           = $msmSum
        msm_share_of_body_pct        = 100.0 * $msmSum / $bodyMs
        msm_share_of_outer_prove_pct = 100.0 * $msmSum / $proveMs
        all_verified                 = 'true'
    }
}

$maxStageClosureMs = [double](
    @(
        $perRun |
        ForEach-Object {
            [Math]::Abs([double]$_.stage_sum_minus_body_ms)
        } |
        Measure-Object -Maximum
    ).Maximum
)

if ($maxStageClosureMs -gt 0.01) {
    throw "Stage timing does not close within 0.01 ms (max difference $maxStageClosureMs ms). Preserve logs and investigate before treating this batch as complete."
}

$stageCsv = Join-Path $rawDir "sapling_spend_stage_profile_$batchId.csv"
$msmCsv = Join-Path $rawDir "sapling_spend_msm_call_profile_$batchId.csv"
$summaryCsv = Join-Path $rawDir "sapling_spend_profile_run_summary_$batchId.csv"
$metadataPath = Join-Path $metadataDir "sapling_spend_combined_profile_$batchId.md"
$innerStageCsv = Join-Path $rawDir "sapling_spend_msm_inner_stage_profile_$batchId.csv"
$innerStageSummaryCsv = Join-Path $rawDir "sapling_spend_msm_inner_stage_summary_$batchId.csv"

if (
    (Test-Path $stageCsv) -or
    (Test-Path $msmCsv) -or
    (Test-Path $summaryCsv) -or
    (Test-Path $innerStageCsv) -or
    (Test-Path $innerStageSummaryCsv) -or
    (Test-Path $metadataPath)
) {
    throw "Output artifact for batch $batchId already exists. Do not overwrite previous experiment data."
}

$stageObjects | Export-Csv -LiteralPath $stageCsv -NoTypeInformation -Encoding UTF8
$msmObjects | Export-Csv -LiteralPath $msmCsv -NoTypeInformation -Encoding UTF8
$perRun | Export-Csv -LiteralPath $summaryCsv -NoTypeInformation -Encoding UTF8
$innerStageObjects | Export-Csv -LiteralPath $innerStageCsv -NoTypeInformation -Encoding UTF8
$innerStageSummaryObjects | Export-Csv -LiteralPath $innerStageSummaryCsv -NoTypeInformation -Encoding UTF8

$system = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue
$cpu = @(
    Get-CimInstance -ClassName Win32_Processor -ErrorAction SilentlyContinue |
    ForEach-Object { $_.Name }
) -join '; '

$os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue

$threadMedian = Get-Median -Values @(
    $batchRows | ForEach-Object { [double]$_.prove_ms }
)

$bodyMedian = Get-Median -Values @(
    $stageObjects | ForEach-Object { [double]$_.create_proof_body_ms }
)

$shareMedian = Get-Median -Values @(
    $perRun | ForEach-Object { [double]$_.msm_share_of_body_pct }
)

$submitMedian = Get-Median -Values @(
    $msmObjects | ForEach-Object { [double]$_.submit_elapsed_ms }
)

$taskDelayMedian = Get-Median -Values @(
    $msmObjects | ForEach-Object { [double]$_.task_start_delay_ms }
)

$msmElapsedMedian = Get-Median -Values @(
    $msmObjects | ForEach-Object { [double]$_.elapsed_ms }
)

$maxConcurrentChunkRegions = [int](
    ($innerStageObjects | Measure-Object -Property max_concurrent_chunk_regions -Maximum).Maximum
)
$maxBucketPayloadEstimateBytes = [long](
    ($innerStageObjects | Measure-Object -Property bucket_payload_at_max_concurrency_estimate_bytes -Maximum).Maximum
)

$report = @"
# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: $batchId
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=$Threads; SAPLING_PROFILE=1
- Run data label: $RunDataLabel
- Branch counters: $BranchCounters
- Fine-grained MSM inner-stage timing: $InnerStageTiming
- Force async worker: $($ForceAsyncWorker.IsPresent)
- Processor affinity mask: $AffinityMask
- Worker fallback records: $($workerFallbackMatches.Count)
- Forced-async override records: $($workerAsyncOverrideMatches.Count)
- Run start: $runStarted
- Run end: $runEnded
- Repository branch: $branch
- Engineering repository HEAD at start: $head
- Engineering worktree dirty at start: $dirtyAtStart
- Engineering worktree status at start: $worktreeStatusLabel
- Engineering worktree status details: $worktreeStatusDetails
- Sapling dependency repository: $saplingRepoUrl
- Sapling dependency HEAD: $saplingCommit
- Sapling dependency source: $saplingSource
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
- vendor/bellman/src/multicore.rs SHA-256: $(Get-Sha256 $workerSource)
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
- MSM inner-stage records: $($innerStageObjects.Count) / 40
- Per-query MSM inner-stage summary rows: $($innerStageSummaryObjects.Count) / 8
- Maximum observed concurrent chunk regions within one MSM call: $maxConcurrentChunkRegions
- Maximum estimated bucket payload for observed concurrency (bytes): $maxBucketPayloadEstimateBytes

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set `-BranchCounters disabled` for paired runs so per-slot counter increments do not contaminate the timing comparison. `-ForceAsyncWorker` suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/$(Split-Path $sourceCsv -Leaf) (filtered by this batch ID)
- Prover run CSV SHA-256: $(Get-Sha256 $sourceCsv)
- Stage CSV: experiments/raw/csv/$(Split-Path $stageCsv -Leaf)
- Stage CSV SHA-256: $(Get-Sha256 $stageCsv)
- MSM call CSV (includes submit timing): experiments/raw/csv/$(Split-Path $msmCsv -Leaf)
- MSM call CSV SHA-256: $(Get-Sha256 $msmCsv)
- Per-run ratio summary CSV: experiments/raw/csv/$(Split-Path $summaryCsv -Leaf)
- Per-run ratio summary CSV SHA-256: $(Get-Sha256 $summaryCsv)
- MSM inner-stage CSV: experiments/raw/csv/$(Split-Path $innerStageCsv -Leaf)
- MSM inner-stage CSV SHA-256: $(Get-Sha256 $innerStageCsv)
- MSM inner-stage per-query summary CSV: experiments/raw/csv/$(Split-Path $innerStageSummaryCsv -Leaf)
- MSM inner-stage per-query summary CSV SHA-256: $(Get-Sha256 $innerStageSummaryCsv)
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
- MSM inner-stage records: $($innerStageObjects.Count) / 40
- MSM inner-stage query summary rows: $($innerStageSummaryObjects.Count) / 8
- Proof verification: 5/5 passed
- Maximum absolute per-run stage-sum minus body timing (ms): $([Math]::Round($maxStageClosureMs, 3))

No algorithm changes were made as part of this run. Results are diagnostic profile data and are not an optimization claim.
"@

[System.IO.File]::WriteAllText(
    $metadataPath,
    $report,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host ''
Write-Host '=== Spend combined profile complete ==='
Write-Host "Batch ID: $batchId"
Write-Host "Outer Prove median: $([Math]::Round($threadMedian, 3)) ms"
Write-Host "Body median: $([Math]::Round($bodyMedian, 3)) ms"
Write-Host "MSM elapsed/body share median: $([Math]::Round($shareMedian, 2))%"
Write-Host "Stage CSV: $stageCsv"
Write-Host "MSM CSV: $msmCsv"
Write-Host "Per-run summary: $summaryCsv"
Write-Host "MSM inner-stage CSV: $innerStageCsv"
Write-Host "MSM inner-stage query summary: $innerStageSummaryCsv"
Write-Host "Fine-grained MSM inner-stage timing: $InnerStageTiming"
Write-Host "Metadata report: $metadataPath"
Write-Host "Worker fallback records: $($workerFallbackMatches.Count)"
Write-Host "Forced-async override records: $($workerAsyncOverrideMatches.Count)"
Write-Host 'All logs are preserved under experiments/raw/logs.'