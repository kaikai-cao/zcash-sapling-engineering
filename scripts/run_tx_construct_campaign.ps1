#Requires -Version 5.1
<#
.SYNOPSIS
    Drive the Sapling transaction-construction benchmark (3 arms, one process each).

.DESCRIPTION
    Arms (frozen in
    experiments/metadata/sapling_tx_construction_preregistration_20261022.md §4):
      A1 real  RAYON_NUM_THREADS=1 affinity 0x1    (LP0, P-core)
      A2 real  RAYON_NUM_THREADS=8 affinity 0xFFFF (P-cores)
      A3 mock  RAYON_NUM_THREADS=1 affinity 0x1    (non-proving decomposition)

    Each invocation constructs REPEATS=6 transactions in one process; run 1 is
    dropped by the analysis (warm-up). Rows are appended to the arm CSV, logs
    go to experiments/raw/logs/tx_construct_<tag>.*.log.

    The launcher fails loudly if a run does not verify, if the row count is not
    6, or if the affinity mask did not take effect (pre-registration §4).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_tx_construct_campaign.ps1 `
        -Label tx_construct_20261022
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',

    # Batch label written into the CSV `tag` column and used in log filenames.
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,59}$')]
    [string]$Label = 'tx_construct_20261022',

    # Skip A2 (useful for a quick smoke run).
    [switch]$SkipEightThread,

    # Skip A3 (mock decomposition arm).
    [switch]$SkipMock,

    [switch]$AllowDirtyWorktree
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

if (-not $AllowDirtyWorktree) {
    $dirty = @((& git -C $RepoRoot status --porcelain 2>$null) | Where-Object { $_ -and $_.Trim() })
    if ($dirty.Count -gt 0) {
        throw "Working tree is dirty. Commit first, or pass -AllowDirtyWorktree (records a caveat)."
    }
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

$exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$spendHash = (Get-FileHash -LiteralPath (Join-Path $paramsDir 'sapling-spend.params') -Algorithm SHA256).Hash.ToLowerInvariant()
$outputHash = (Get-FileHash -LiteralPath (Join-Path $paramsDir 'sapling-output.params') -Algorithm SHA256).Hash.ToLowerInvariant()
$gitHead = (& git -C $RepoRoot rev-parse HEAD).Trim()
$dirtyAtStart = @((& git -C $RepoRoot status --porcelain 2>$null) | Where-Object { $_ -and $_.Trim() }).Count -gt 0
$rustcVersion = (& rustc --version 2>$null | Out-String).Trim()

$armSpecs = @(
    [PSCustomObject]@{ Name = 'A1'; Arm = 'real'; Threads = '1'; Mask = 0x1L;   Label = 'real_t1_0x1' }
    [PSCustomObject]@{ Name = 'A2'; Arm = 'real'; Threads = '8'; Mask = 0xFFFFL; Label = 'real_t8_0xFFFF' }
    [PSCustomObject]@{ Name = 'A3'; Arm = 'mock'; Threads = '1'; Mask = 0x1L;   Label = 'mock_t1_0x1' }
)
if ($SkipEightThread) { $armSpecs = @($armSpecs | Where-Object { $_.Name -ne 'A2' }) }
if ($SkipMock) { $armSpecs = @($armSpecs | Where-Object { $_.Name -ne 'A3' }) }

foreach ($spec in $armSpecs) {
    if ($spec.Mask -lt 0 -or $spec.Mask -ge $maskLimit) {
        throw ("Affinity mask 0x{0:X} is invalid for {1} logical processors." -f $spec.Mask, $logicalProcessors)
    }
}

$env:ZCASH_PARAMS_DIR = $paramsDir
$env:TX_SMOKE_GIT_HEAD = $gitHead

Write-Host ('==================================================')
Write-Host ("TX CONSTRUCT CAMPAIGN label={0}" -f $Label)
Write-Host ("repo={0}" -f $RepoRoot)
Write-Host ("git_head={0}{1}" -f $gitHead, $(if ($dirtyAtStart) { ' (dirty worktree)' } else { '' }))
Write-Host ("exe={0}" -f $exe)
Write-Host ("exe_sha256={0}" -f $exeHash)
Write-Host ("spend_params_sha256={0}" -f $spendHash)
Write-Host ("output_params_sha256={0}" -f $outputHash)
Write-Host ("rustc={0}" -f $rustcVersion)
Write-Host ("logical_processors={0}" -f $logicalProcessors)
Write-Host ('==================================================')

$summaryRows = New-Object System.Collections.Generic.List[object]

foreach ($spec in $armSpecs) {
    $csvPath = Join-Path $rawDir ("sapling_tx_construct_runs_{0}.csv" -f $spec.Arm)
    $tag = '{0}_{1}' -f $Label, $spec.Label
    $stdoutLog = Join-Path $logDir ("tx_construct_{0}.log" -f $tag)
    $stderrLog = Join-Path $logDir ("tx_construct_{0}.stderr.log" -f $tag)

    $hadCsv = Test-Path -LiteralPath $csvPath
    $rowOffset = 0
    if ($hadCsv) {
        $rowOffset = @(Import-Csv -LiteralPath $csvPath).Count
    }

    $env:TX_SMOKE_ARM = $spec.Arm
    $env:RAYON_NUM_THREADS = $spec.Threads
    $env:TX_SMOKE_TAG = $tag
    $env:TX_SMOKE_AFFINITY = ('0x{0:X}' -f $spec.Mask)
    $env:TX_CONSTRUCT_CSV = $csvPath

    $maskTag = '0x{0:X}' -f $spec.Mask
    Write-Host ''
    Write-Host ('--------------------------------------------------')
    Write-Host ("{0}: arm={1} threads={2} affinity={3} tag={4}" -f $spec.Name, $spec.Arm, $spec.Threads, $maskTag, $tag)
    Write-Host ('--------------------------------------------------')

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
        $process.ProcessorAffinity = [IntPtr]([int64]$spec.Mask)
    }
    catch {
        $process.Kill()
        throw ("Failed to set affinity {0}: {1}" -f $maskTag, $_.Exception.Message)
    }

    $effectiveMask = [int64]$process.ProcessorAffinity
    if ($effectiveMask -ne [int64]$spec.Mask) {
        $process.Kill()
        throw ("Affinity did not take effect: wanted 0x{0:X}, got 0x{1:X}." -f $spec.Mask, $effectiveMask)
    }

    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $exit = $process.ExitCode

    [IO.File]::WriteAllText($stdoutLog, $stdoutTask.Result, [System.Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($stderrLog, $stderrTask.Result, [System.Text.UTF8Encoding]::new($false))

    if ($exit -ne 0) {
        if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog -Tail 40 }
        throw ("{0} failed (exit={1}). See {2}" -f $spec.Name, $exit, $stderrLog)
    }

    $allRows = @(Import-Csv -LiteralPath $csvPath)
    $newRows = @($allRows | Select-Object -Skip $rowOffset)
    if ($newRows.Count -ne 6) {
        throw ("{0}: expected 6 rows, got {1}." -f $spec.Name, $newRows.Count)
    }

    $bad = @($newRows | Where-Object {
            ($spec.Arm -eq 'real' -and $_.verified -ne 'true') -or
            $_.tx_version -ne 'V5' -or
            $_.spend_count -ne '1' -or
            $_.output_count -ne '2' -or
            $_.fee_zats -ne '10000' -or
            $_.value_balance_zats -ne '10000'
        })
    if ($bad.Count -gt 0) {
        throw ("{0}: structural/verification assertion failed in {1} row(s)." -f $spec.Name, $bad.Count)
    }
    $distinctBytes = @($newRows | ForEach-Object { $_.tx_bytes } | Sort-Object -Unique)
    if ($distinctBytes.Count -ne 1) {
        throw ("{0}: tx_bytes is not constant across runs ({1} distinct values)." -f $spec.Name, $distinctBytes.Count)
    }

    $build = @($newRows | ForEach-Object { [double]$_.build_ms })
    $total = @($newRows | ForEach-Object { [double]$_.total_construct_ms })
    $warmBuild = @($build | Select-Object -Skip 1)
    Write-Host ("  batch_id={0} tx_bytes={1} build_ms=[{2}]" -f `
            $newRows[0].batch_id, $distinctBytes[0], (($build | ForEach-Object { '{0:F1}' -f $_ }) -join ' '))
    Write-Host ("  total_construct_ms=[{0}]" -f (($total | ForEach-Object { '{0:F1}' -f $_ }) -join ' '))
    Write-Host ("  warm build median={0:F3} ms (n={1}, run 1 dropped)" -f `
        ([double](@($warmBuild | Sort-Object)[[int][Math]::Floor($warmBuild.Count / 2)])), $warmBuild.Count)

    $summaryRows.Add([PSCustomObject]@{
            arm              = $spec.Arm
            arm_name         = $spec.Name
            tag              = $tag
            threads          = $spec.Threads
            affinity_mask    = $maskTag
            runs             = $newRows.Count
            tx_bytes         = $distinctBytes[0]
            fee_zats         = $newRows[0].fee_zats
            verified_all     = (($spec.Arm -eq 'real') -and (@($newRows | Where-Object { $_.verified -eq 'true' }).Count -eq $newRows.Count))
            median_build_ms  = [Math]::Round(([double](@($warmBuild | Sort-Object)[[int][Math]::Floor($warmBuild.Count / 2)])), 3)
            exe_sha256       = $exeHash
            spend_params_sha256  = $spendHash
            output_params_sha256 = $outputHash
            git_head         = $gitHead
            dirty_worktree   = $dirtyAtStart
            source_csv       = $csvPath
            log              = $stdoutLog
        })
}

$summaryCsv = Join-Path $rawDir ("sapling_tx_construct_campaign_{0}_summary.csv" -f $Label)
$summaryRows | Export-Csv -LiteralPath $summaryCsv -NoTypeInformation -Encoding UTF8

Write-Host ''
Write-Host ('==================================================')
Write-Host ("CAMPAIGN COMPLETE: {0} arm(s)" -f $summaryRows.Count)
Write-Host ("summary csv: {0}" -f $summaryCsv)
Write-Host ('==================================================')
