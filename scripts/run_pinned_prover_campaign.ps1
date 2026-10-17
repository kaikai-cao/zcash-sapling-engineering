[CmdletBinding()]
param(
    [string]$RepoRoot = '',

    # Which prover smoke binary to drive.
    [ValidateSet('spend', 'output')]
    [string]$Prover = 'spend',

    # Rayon thread counts to test. Each entry is run for every affinity mask.
    [int[]]$Threads = @(1),

    # Processor-affinity mask(s) applied to the prover process. 0 = leave the
    # OS scheduler free. On hybrid CPUs this is the single most important knob:
    # an unbound single-threaded prove can land on a P-core or an E-core and
    # differ by ~2x.
    [long[]]$AffinityMasks = @(1),

    # How many independent process invocations (batches) per (mask, threads)
    # combination. Each batch itself performs 5 proofs inside the smoke binary.
    [ValidateRange(1, 50)]
    [int]$Batches = 3,

    # Raw CSV suffix. The raw rows go to
    #   experiments/raw/csv/sapling_<prover>_prover_runs_<Label>.csv
    # and the derived per-config table to
    #   experiments/raw/csv/sapling_<prover>_prover_runs_<Label>_summary.csv
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,59}$')]
    [string]$Label = 'pinned_baseline_20261017',

    [string]$ParameterPath = '',

    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------
# Resolve repository root.
# ---------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $runnerPath = $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($runnerPath)) {
        throw 'Cannot resolve runner script path. Pass -RepoRoot explicitly.'
    }
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $runnerPath) '..')).Path
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

if (-not $AllowDirtyWorktree) {
    $dirty = & git -C $RepoRoot status --porcelain 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed: $($dirty -join ' ')"
    }
    if (@($dirty | Where-Object { $_ -and $_.Trim() }).Count -gt 0) {
        throw "Working tree is dirty. Commit first, or pass -AllowDirtyWorktree (records a caveat)."
    }
}

if ([string]::IsNullOrWhiteSpace($ParameterPath)) {
    $parameterDirectory = if (-not [string]::IsNullOrWhiteSpace($env:ZCASH_PARAMS_DIR)) {
        $env:ZCASH_PARAMS_DIR
    }
    else {
        'D:\Research\zcash-params'
    }
    $paramFileName = if ($Prover -eq 'spend') { 'sapling-spend.params' } else { 'sapling-output.params' }
    $ParameterPath = Join-Path $parameterDirectory $paramFileName
}
$ParameterPath = [System.IO.Path]::GetFullPath($ParameterPath)

$exe = if ($Prover -eq 'spend') {
    Join-Path $RepoRoot 'experiments\prover-smoke\target\release\spend_prover_smoke.exe'
}
else {
    Join-Path $RepoRoot 'experiments\prover-smoke\target\release\sapling-output-smoke.exe'
}

$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
foreach ($dir in @($rawDir, $logDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$rawCsv = Join-Path $rawDir ("sapling_{0}_prover_runs_{1}.csv" -f $Prover, $Label)
$summaryCsv = Join-Path $rawDir ("sapling_{0}_prover_runs_{1}_summary.csv" -f $Prover, $Label)

foreach ($required in @($exe, $ParameterPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required artifact is missing: $required"
    }
}

function Get-Median {
    param([double[]]$Values)
    $sorted = @($Values | Sort-Object)
    if ($sorted.Count -eq 0) { throw 'Cannot take the median of an empty set.' }
    $mid = [int][Math]::Floor($sorted.Count / 2)
    if (($sorted.Count % 2) -eq 1) { return [double]$sorted[$mid] }
    return ([double]$sorted[$mid - 1] + [double]$sorted[$mid]) / 2.0
}

# ---------------------------------------------------------------------------
# Environment for the child. Parameter path is prover-specific.
# ---------------------------------------------------------------------------
$envVarName = if ($Prover -eq 'spend') { 'SAPLING_SPEND_PARAMS' } else { 'SAPLING_OUTPUT_PARAMS' }
$oldParams = [Environment]::GetEnvironmentVariable($envVarName, 'Process')
$oldThreads = [Environment]::GetEnvironmentVariable('RAYON_NUM_THREADS', 'Process')
$oldCsv = [Environment]::GetEnvironmentVariable('SAPLING_PROVER_RUNS_CSV', 'Process')
$oldProfile = [Environment]::GetEnvironmentVariable('SAPLING_PROFILE', 'Process')

$exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$paramsHash = (Get-FileHash -LiteralPath $ParameterPath -Algorithm SHA256).Hash.ToLowerInvariant()
$gitHead = (& git -C $RepoRoot rev-parse HEAD).Trim()
$dirtyAtStart = @((& git -C $RepoRoot status --porcelain 2>$null) | Where-Object { $_ -and $_.Trim() }).Count -gt 0

$summaryRows = New-Object System.Collections.Generic.List[object]
$batchCounter = 0

$hadRawCsv = Test-Path -LiteralPath $rawCsv
$rowOffset = 0
if ($hadRawCsv) {
    $rowOffset = @(Import-Csv -LiteralPath $rawCsv).Count
}

Write-Host ("prover={0} exe={1}" -f $Prover, $exe)
Write-Host ("exe_sha256={0}" -f $exeHash)
Write-Host ("params={0}" -f $ParameterPath)
Write-Host ("params_sha256={0}" -f $paramsHash)
Write-Host ("raw_csv={0}" -f $rawCsv)
Write-Host ("threads={0}" -f ($Threads -join ', '))
Write-Host ("affinity_masks={0}" -f (($AffinityMasks | ForEach-Object { '0x{0:X}' -f $_ }) -join ', '))
Write-Host ("batches_per_config={0}" -f $Batches)
Write-Host ''

try {
    # Disable diagnostic stderr noise; prove_ms is unaffected by the profile flag.
    $env:SAPLING_PROFILE = '0'
    $env:SAPLING_PROVER_RUNS_CSV = $rawCsv
    [Environment]::SetEnvironmentVariable($envVarName, $ParameterPath, 'Process')

    foreach ($mask in $AffinityMasks) {
        foreach ($threadCount in $Threads) {
            $env:RAYON_NUM_THREADS = "$threadCount"
            $maskTag = '0x{0:X}' -f $mask

            Write-Host ('==================================================')
            Write-Host ("config affinity_mask={0} rayon_threads={1}" -f $maskTag, $threadCount)
            Write-Host ('==================================================')

            $configRows = New-Object System.Collections.Generic.List[object]

            for ($batch = 1; $batch -le $Batches; $batch++) {
                $batchCounter++
                $tag = 'sapling_{0}_{1}_t{2}_{3}_b{4}' -f $Prover, $Label, $threadCount, $maskTag, $batch
                $stdoutLog = Join-Path $logDir ("$tag.stdout.log")
                $stderrLog = Join-Path $logDir ("$tag.stderr.log")

                $startInfo = New-Object System.Diagnostics.ProcessStartInfo
                $startInfo.FileName = $exe
                $startInfo.WorkingDirectory = $RepoRoot
                $startInfo.UseShellExecute = $false
                $startInfo.RedirectStandardOutput = $true
                $startInfo.RedirectStandardError = $true

                $process = New-Object System.Diagnostics.Process
                $process.StartInfo = $startInfo
                [void]$process.Start()

                # Pin after start; the prove phase has not begun yet.
                if ($mask -ne 0) {
                    try {
                        $process.ProcessorAffinity = [IntPtr]([int64]$mask)
                    }
                    catch {
                        throw "Failed to set processor affinity mask ${maskTag}: $($_.Exception.Message)"
                    }
                }

                # Drain both pipes concurrently to avoid deadlocking on a full pipe buffer.
                $stdoutTask = $process.StandardOutput.ReadToEndAsync()
                $stderrTask = $process.StandardError.ReadToEndAsync()
                $process.WaitForExit()

                $exit = $process.ExitCode
                [IO.File]::WriteAllText($stdoutLog, $stdoutTask.Result, [System.Text.UTF8Encoding]::new($false))
                [IO.File]::WriteAllText($stderrLog, $stderrTask.Result, [System.Text.UTF8Encoding]::new($false))

                if ($exit -ne 0) {
                    Write-Host ("batch failed affinity={0} threads={1} exit={2}" -f $maskTag, $threadCount, $exit)
                    if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog -Tail 40 }
                    throw "Prover invocation failed (affinity=$maskTag threads=$threadCount exit=$exit)."
                }

                # Pull the rows this invocation appended.
                $allRows = @(Import-Csv -LiteralPath $rawCsv)
                $newRows = @($allRows | Select-Object -Skip $rowOffset)
                $rowOffset = $allRows.Count

                if ($newRows.Count -ne 5) {
                    throw ("Expected 5 rows for affinity={0} threads={1} batch={2}; got {3}." -f $maskTag, $threadCount, $batch, $newRows.Count)
                }

                $bad = @($newRows | Where-Object { $_.verified -ne 'true' })
                if ($bad.Count -gt 0) {
                    throw ("Verification failed in affinity={0} threads={1} batch={2}." -f $maskTag, $threadCount, $batch)
                }

                foreach ($row in $newRows) { $configRows.Add($row) }

                $proveValues = @($newRows | ForEach-Object { [double]$_.prove_ms })
                Write-Host ("  batch={0} batch_id={1} prove_ms[{2}]" -f $batch, $newRows[0].batch_id, (($proveValues | ForEach-Object { '{0:F1}' -f $_ }) -join ' '))
            }

            $allProve = @($configRows | ForEach-Object { [double]$_.prove_ms })
            $allVerify = @($configRows | ForEach-Object { [double]$_.verify_ms })
            $medianProve = Get-Median -Values $allProve
            $medianVerify = Get-Median -Values $allVerify
            $minProve = ($allProve | Measure-Object -Minimum).Minimum
            $maxProve = ($allProve | Measure-Object -Maximum).Maximum

            Write-Host ("  => n={0} median_prove_ms={1:F3} min={2:F3} max={3:F3} spread_pct={4:F2}" -f `
                $allProve.Count, $medianProve, $minProve, $maxProve, `
                ((($maxProve - $minProve) / $medianProve) * 100.0))
            Write-Host ''

            $summaryRows.Add([PSCustomObject]@{
                    prover           = $Prover
                    label            = $Label
                    affinity_mask    = $maskTag
                    affinity_decimal = $mask
                    rayon_threads    = $threadCount
                    batches          = $Batches
                    proofs           = $allProve.Count
                    median_prove_ms  = [Math]::Round($medianProve, 3)
                    min_prove_ms     = [Math]::Round($minProve, 3)
                    max_prove_ms     = [Math]::Round($maxProve, 3)
                    spread_pct       = [Math]::Round(((($maxProve - $minProve) / $medianProve) * 100.0), 3)
                    median_verify_ms = [Math]::Round($medianVerify, 3)
                    all_verified     = $true
                    exe_sha256       = $exeHash
                    params_sha256    = $paramsHash
                    git_head         = $gitHead
                    dirty_worktree   = $dirtyAtStart
                    source_csv       = $rawCsv
                })
        }
    }
}
finally {
    if ($null -eq $oldParams) { Remove-Item "Env:$envVarName" -ErrorAction SilentlyContinue }
    else { [Environment]::SetEnvironmentVariable($envVarName, $oldParams, 'Process') }

    if ($null -eq $oldThreads) { Remove-Item Env:RAYON_NUM_THREADS -ErrorAction SilentlyContinue }
    else { $env:RAYON_NUM_THREADS = $oldThreads }

    if ($null -eq $oldCsv) { Remove-Item Env:SAPLING_PROVER_RUNS_CSV -ErrorAction SilentlyContinue }
    else { $env:SAPLING_PROVER_RUNS_CSV = $oldCsv }

    if ($null -eq $oldProfile) { Remove-Item Env:SAPLING_PROFILE -ErrorAction SilentlyContinue }
    else { $env:SAPLING_PROFILE = $oldProfile }
}

$summaryRows | Export-Csv -LiteralPath $summaryCsv -NoTypeInformation -Encoding UTF8

Write-Host ('==================================================')
Write-Host ("CAMPAIGN COMPLETE: {0} batch(es) run" -f $batchCounter)
Write-Host ("raw csv:     {0}" -f $rawCsv)
Write-Host ("summary csv: {0}" -f $summaryCsv)
Write-Host ('==================================================')
