#Requires -Version 5.1
<#
.SYNOPSIS
    Drive one real transaction-construction scaling batch (1 spend + 2 outputs).

.DESCRIPTION
    Stage 0 scaling-diagnosis helper. Each invocation runs the frozen
    transaction benchmark for one (threads, affinity) configuration and appends
    REPEATS=6 rows to a new raw CSV. Run 1 is dropped later by the analysis.

    The script sets and reads back the processor affinity, and fails loudly if:
      * the affinity readback does not match the request;
      * the invocation does not append exactly 6 rows;
      * any row fails cryptographic verification;
      * tx_bytes / version / spend-output shape differ from the frozen shape.

    It does not modify the transaction binary or any existing baseline CSV.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_tx_scaling_campaign.ps1 `
        -Threads 8 -AffinityMask 0x5555 -Tag msm_scaling_20261022_tx_t8_0x5555_b1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',

    [ValidateRange(1, 64)]
    [int]$Threads = 8,

    [long]$AffinityMask = 0x1,

    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,79}$')]
    [string]$Tag = 'msm_scaling_20261022_tx',

    [ValidateRange(1, 50)]
    [int]$Batches = 1,

    # Optional raw CSV override (smoke tests only; the Stage 0 campaign uses the
    # frozen path below).
    [string]$RawCsv = '',

    [switch]$AllowDirtyWorktree,

    # Ignore untracked append-only outputs (raw CSVs, logs, derived tables) when
    # checking worktree cleanliness. Modified tracked files still block the run.
    [switch]$AllowUntrackedOutputs
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $scriptPath = $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($scriptPath)) {
        throw 'Cannot resolve script path. Pass -RepoRoot explicitly.'
    }
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $scriptPath) '..')).Path
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

$dirtyRaw = @((& git -C $RepoRoot status --porcelain 2>$null) | Where-Object { $_ -and $_.Trim() })
$ignoredOutputStatus = @()
if ($AllowUntrackedOutputs) {
    $ignoredOutputStatus = @($dirtyRaw | Where-Object {
            $_ -match '^\?\? (experiments/raw/|experiments/metadata/|results/)'
        })
    $dirtyRaw = @($dirtyRaw | Where-Object {
            $_ -notmatch '^\?\? (experiments/raw/|experiments/metadata/|results/)'
        })
}
if (-not $AllowDirtyWorktree -and $dirtyRaw.Count -gt 0) {
    throw "Working tree is dirty. Commit first, or pass -AllowDirtyWorktree (records a caveat)."
}

$exe = Join-Path $RepoRoot 'experiments\transaction-smoke\target\release\tx_construct_bench.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Missing binary: $exe (run cargo build --release in experiments\transaction-smoke)"
}

$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
foreach ($dir in @($rawDir, $logDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$paramsDir = if ([string]::IsNullOrWhiteSpace($env:ZCASH_PARAMS_DIR)) {
    'D:\Research\zcash-params'
}
else {
    $env:ZCASH_PARAMS_DIR
}
foreach ($name in @('sapling-spend.params', 'sapling-output.params')) {
    $paramsPath = Join-Path $paramsDir $name
    if (-not (Test-Path -LiteralPath $paramsPath -PathType Leaf)) {
        throw "Missing parameter file: $paramsPath"
    }
}

$logicalProcessors = [Environment]::ProcessorCount
$maskLimit = 1L -shl $logicalProcessors
if ($AffinityMask -le 0 -or $AffinityMask -ge $maskLimit) {
    throw ("Affinity mask 0x{0:X} is invalid for {1} logical processors (max 0x{2:X})." -f $AffinityMask, $logicalProcessors, ($maskLimit - 1))
}

$rawCsv = if ([string]::IsNullOrWhiteSpace($RawCsv)) {
    Join-Path $rawDir 'sapling_tx_scaling_runs_msm_scaling_20261022.csv'
}
else {
    $candidate = if ([IO.Path]::IsPathRooted($RawCsv)) { $RawCsv } else { Join-Path $RepoRoot $RawCsv }
    [IO.Path]::GetFullPath($candidate)
}
$maskTag = '0x{0:X}' -f $AffinityMask
$exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$spendHash = (Get-FileHash -LiteralPath (Join-Path $paramsDir 'sapling-spend.params') -Algorithm SHA256).Hash.ToLowerInvariant()
$outputHash = (Get-FileHash -LiteralPath (Join-Path $paramsDir 'sapling-output.params') -Algorithm SHA256).Hash.ToLowerInvariant()
$gitHead = (& git -C $RepoRoot rev-parse HEAD).Trim()
$dirtyAtStart = $dirtyRaw.Count -gt 0
$ignoredOutputCount = $ignoredOutputStatus.Count

$oldArm = [Environment]::GetEnvironmentVariable('TX_SMOKE_ARM', 'Process')
$oldTag = [Environment]::GetEnvironmentVariable('TX_SMOKE_TAG', 'Process')
$oldAffinity = [Environment]::GetEnvironmentVariable('TX_SMOKE_AFFINITY', 'Process')
$oldCsv = [Environment]::GetEnvironmentVariable('TX_CONSTRUCT_CSV', 'Process')
$oldThreads = [Environment]::GetEnvironmentVariable('RAYON_NUM_THREADS', 'Process')

$hadRawCsv = Test-Path -LiteralPath $rawCsv
$rowOffset = 0
if ($hadRawCsv) {
    $rowOffset = @(Import-Csv -LiteralPath $rawCsv).Count
}

Write-Host ("exe={0}" -f $exe)
Write-Host ("exe_sha256={0}" -f $exeHash)
Write-Host ("spend_params_sha256={0}" -f $spendHash)
Write-Host ("output_params_sha256={0}" -f $outputHash)
Write-Host ("git_head={0}" -f $gitHead)
Write-Host ("raw_csv={0}" -f $rawCsv)
Write-Host ("threads={0} affinity={1} batches={2}" -f $Threads, $maskTag, $Batches)

try {
    $env:TX_SMOKE_ARM = 'real'
    $env:RAYON_NUM_THREADS = "$Threads"
    $env:TX_SMOKE_AFFINITY = $maskTag
    $env:TX_CONSTRUCT_CSV = $rawCsv

    for ($batch = 1; $batch -le $Batches; $batch++) {
        $batchTag = '{0}_b{1}' -f $Tag, $batch
        $env:TX_SMOKE_TAG = $batchTag
        $stdoutLog = Join-Path $logDir ("$batchTag.stdout.log")
        $stderrLog = Join-Path $logDir ("$batchTag.stderr.log")

        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $exe
        $startInfo.WorkingDirectory = $RepoRoot
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        [void]$process.Start()

        try {
            $process.ProcessorAffinity = [IntPtr]([int64]$AffinityMask)
            $effectiveAffinity = [int64]$process.ProcessorAffinity
        }
        catch {
            $process.Kill()
            throw ("Failed to set/read processor affinity {0}: {1}" -f $maskTag, $_.Exception.Message)
        }
        if ($effectiveAffinity -ne [int64]$AffinityMask) {
            $process.Kill()
            throw ("Processor affinity did not take effect: requested {0}, read back 0x{1:X}." -f $maskTag, $effectiveAffinity)
        }

        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $exit = $process.ExitCode
        [IO.File]::WriteAllText($stdoutLog, $stdoutTask.Result, [System.Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText($stderrLog, $stderrTask.Result, [System.Text.UTF8Encoding]::new($false))

        if ($exit -ne 0) {
            if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog -Tail 40 }
            throw ("Transaction scaling batch failed (threads={0} affinity={1} batch={2} exit={3})." -f $Threads, $maskTag, $batch, $exit)
        }

        $allRows = @(Import-Csv -LiteralPath $rawCsv)
        $newRows = @($allRows | Select-Object -Skip $rowOffset)
        $rowOffset = $allRows.Count

        if ($newRows.Count -ne 6) {
            throw ("Expected 6 transaction rows for threads={0} affinity={1} batch={2}; got {3}." -f $Threads, $maskTag, $batch, $newRows.Count)
        }

        $bad = @($newRows | Where-Object {
                $_.verified -ne 'true' -or
                $_.tx_version -ne 'V5' -or
                $_.spend_count -ne '1' -or
                $_.output_count -ne '2' -or
                $_.tx_bytes -ne '2377' -or
                $_.rayon_threads -ne "$Threads"
            })
        if ($bad.Count -gt 0) {
            throw ("Transaction structural/verification assertion failed in {0} row(s) for threads={1} affinity={2} batch={3}." -f $bad.Count, $Threads, $maskTag, $batch)
        }

        $distinctBytes = @($newRows | ForEach-Object { $_.tx_bytes } | Sort-Object -Unique)
        if ($distinctBytes.Count -ne 1) {
            throw ("tx_bytes is not constant within the batch for threads={0} affinity={1} batch={2}." -f $Threads, $maskTag, $batch)
        }

        $build = @($newRows | ForEach-Object { [double]$_.build_ms })
        Write-Host ("  batch={0} batch_id={1} tx_bytes={2} build_ms=[{3}]" -f `
                $batch, $newRows[0].batch_id, $distinctBytes[0], (($build | ForEach-Object { '{0:F1}' -f $_ }) -join ' '))
    }
}
finally {
    if ($null -eq $oldArm) { Remove-Item Env:TX_SMOKE_ARM -ErrorAction SilentlyContinue } else { $env:TX_SMOKE_ARM = $oldArm }
    if ($null -eq $oldTag) { Remove-Item Env:TX_SMOKE_TAG -ErrorAction SilentlyContinue } else { $env:TX_SMOKE_TAG = $oldTag }
    if ($null -eq $oldAffinity) { Remove-Item Env:TX_SMOKE_AFFINITY -ErrorAction SilentlyContinue } else { $env:TX_SMOKE_AFFINITY = $oldAffinity }
    if ($null -eq $oldCsv) { Remove-Item Env:TX_CONSTRUCT_CSV -ErrorAction SilentlyContinue } else { $env:TX_CONSTRUCT_CSV = $oldCsv }
    if ($null -eq $oldThreads) { Remove-Item Env:RAYON_NUM_THREADS -ErrorAction SilentlyContinue } else { $env:RAYON_NUM_THREADS = $oldThreads }
}

Write-Host '=== transaction scaling batch complete ==='
Write-Host ("raw csv: {0}" -f $rawCsv)
