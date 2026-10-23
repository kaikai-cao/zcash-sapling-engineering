#Requires -Version 5.1
<#
.SYNOPSIS
    Pinned microbenchmark runner for the FFT arithmetic scoping study.

.DESCRIPTION
    Frozen by
      experiments/metadata/sapling_fft_arith_scoping_preregistration_20261023.md

    Runs the standalone `fft_arith_bench` binary in separate 1-thread and
    8-thread processes.  Each process first checks exact equality against the
    production `EvaluationDomain::fft` path, then performs the ABBA-ordered
    timing runs.  The binary prints raw CSV to stdout; this script redirects it
    to immutable per-batch files and records provenance in a manifest.

    Measurement-only: no vendor file, production default, or parameter file is
    changed and no proof is produced.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_fft_arith_scoping.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,40}$')]
    [string]$Tag = 'sapling_fft_arith_scoping_20261023',
    [ValidateRange(1, 30)]
    [int]$Batches = 9,
    [string]$PreregPath = 'experiments/metadata/sapling_fft_arith_scoping_preregistration_20261023.md'
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

function Get-Sha256 {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required artifact is missing: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-UtcNow {
    return [DateTime]::UtcNow.ToString('o')
}

function Get-RepoRelative {
    param([string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetFullPath($RepoRoot)
    if ($full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $full.Substring($root.Length).TrimStart('\', '/').Replace('\', '/')
    }
    return $Path
}

$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
$metadataDir = Join-Path $RepoRoot 'experiments\metadata'
$binary = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\fft_arith_bench.exe'
$preregFull = if ([System.IO.Path]::IsPathRooted($PreregPath)) { $PreregPath } else { Join-Path $RepoRoot $PreregPath }
$manifest = Join-Path $metadataDir "fft_arith_scoping_manifest_${Tag}.csv"
$campaignLog = Join-Path $logDir "${Tag}_campaign.log"

foreach ($path in @($preregFull)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file is missing: $path"
    }
}

$leftover = @(Get-Process -Name 'fft_arith_bench' -ErrorAction SilentlyContinue)
if ($leftover.Count -gt 0) {
    throw "An fft_arith_bench process is already running (PID(s): $($leftover.Id -join ', '))."
}

$head = (& git -C $RepoRoot rev-parse HEAD 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed: $head" }
$dirty = (& git -C $RepoRoot status --porcelain 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "git status --porcelain failed: $dirty" }
if (-not [string]::IsNullOrWhiteSpace($dirty)) {
    throw "Working tree is not clean. Commit code/scripts and pre-registration before the formal run.`n$dirty"
}

$buildStdout = Join-Path $logDir "${Tag}_prebuild.stdout.log"
$buildStderr = Join-Path $logDir "${Tag}_prebuild.stderr.log"
foreach ($path in @($manifest, $campaignLog, $buildStdout, $buildStderr)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing artifact: $path"
    }
}

# Build with the committed lockfile.  The build log belongs to the raw record.
$cargo = (Get-Command cargo -ErrorAction Stop).Source
$buildArgs = 'build --release --locked --manifest-path "{0}" --bin fft_arith_bench' -f (Join-Path $RepoRoot 'experiments\prover-smoke\Cargo.toml')
$buildProc = Start-Process -FilePath $cargo -ArgumentList $buildArgs -WorkingDirectory $RepoRoot -PassThru -Wait `
    -RedirectStandardOutput $buildStdout -RedirectStandardError $buildStderr
if ($buildProc.ExitCode -ne 0) {
    throw "Prebuild failed with exit code $($buildProc.ExitCode). Logs: $buildStdout ; $buildStderr"
}
if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
    throw "Benchmark binary is missing after build: $binary"
}

$preregSha = Get-Sha256 $preregFull
$binarySha = Get-Sha256 $binary
$rustc = (& rustc -V 2>&1 | Out-String).Trim()
$cargoVersion = (& cargo -V 2>&1 | Out-String).Trim()
$logicalProcessors = [Environment]::ProcessorCount

# Stage 4 used 0x5555 for the 8-thread arm; the pre-registration's 0xFFFF
# was copied from the general 8-thread convention.  0x5555 is recorded as the
# primary 8t mask here, and the deviation is written into the manifest and
# results.  The 1t mask is exactly the frozen 0x1.
$plan = @(
    [PSCustomObject]@{ Arm = '1t'; Threads = 1; Mask = [int64]0x1; MaskTag = '0x1' },
    [PSCustomObject]@{ Arm = '8t'; Threads = 8; Mask = [int64]0x5555; MaskTag = '0x5555' }
)

$manifestRows = New-Object System.Collections.Generic.List[object]
$campaignLines = New-Object System.Collections.Generic.List[string]
$campaignLines.Add("tag=$Tag")
$campaignLines.Add("head=$head")
$campaignLines.Add("prereg_sha256=$preregSha")
$campaignLines.Add("binary_sha256=$binarySha")
$campaignLines.Add("rustc=$rustc")
$campaignLines.Add("cargo=$cargoVersion")
$campaignLines.Add("logical_processors=$logicalProcessors")
$campaignLines.Add("batches=$Batches")
$campaignLines.Add('8t_primary_mask=0x5555 (deviation from prereg 0xFFFF; Stage 4 matched)')

foreach ($entry in $plan) {
    foreach ($batch in 1..$Batches) {
        $rawCsv = Join-Path $rawDir "${Tag}_$($entry.Arm)_b${batch}.csv"
        $stderrLog = Join-Path $logDir "${Tag}_$($entry.Arm)_b${batch}.stderr.log"
        foreach ($path in @($rawCsv, $stderrLog)) {
            if (Test-Path -LiteralPath $path) {
                throw "Refusing to overwrite existing raw artifact: $path"
            }
        }

        $env:RAYON_NUM_THREADS = "$($entry.Threads)"
        $env:SAPLING_FFT_SERIAL_SINGLE_THREAD = '1'
        $env:SAPLING_PROFILE = '0'

        $started = Get-UtcNow
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $binary
        $psi.Arguments = "$($entry.Threads) all"
        $psi.WorkingDirectory = $RepoRoot
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        if (-not $process.Start()) {
            throw "Failed to start benchmark for arm=$($entry.Arm) batch=$batch."
        }

        $effectiveAffinity = 0L
        try {
            $process.ProcessorAffinity = [IntPtr]([int64]$entry.Mask)
            $effectiveAffinity = [int64]$process.ProcessorAffinity
        }
        catch {
            if (-not $process.HasExited) { $process.Kill() }
            throw "Failed to set processor affinity $($entry.MaskTag): $($_.Exception.Message)"
        }
        if ($effectiveAffinity -ne [int64]$entry.Mask) {
            if (-not $process.HasExited) { $process.Kill() }
            throw ("Processor affinity did not take effect: requested {0}, read back 0x{1:X}." -f $entry.MaskTag, $effectiveAffinity)
        }

        # Drain both pipes concurrently, then persist the binary's exact output.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result
        $exitCode = $process.ExitCode
        $finished = Get-UtcNow
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($rawCsv, $stdout, $utf8)
        [System.IO.File]::WriteAllText($stderrLog, $stderr, $utf8)
        if ($null -eq $exitCode) {
            throw "Could not read exit code for arm=$($entry.Arm) batch=$batch."
        }
        if ($exitCode -ne 0) {
            throw "Benchmark failed arm=$($entry.Arm) batch=$batch exit=$exitCode. Log: $stderrLog"
        }

        $rows = @(Import-Csv -LiteralPath $rawCsv)
        $expectedTimeRows = if ($entry.Threads -eq 1) { 4 * 2 * 9 * 2 } else { 1 * 2 * 9 * 2 }
        $expectedCorrectnessRows = 4 * 3
        $timeRows = @($rows | Where-Object { $_.kind -eq 'time' })
        $correctnessRows = @($rows | Where-Object { $_.kind -eq 'correctness' })
        if ($timeRows.Count -ne $expectedTimeRows) {
            throw ("Unexpected time-row count arm={0} batch={1}: got {2}, expected {3}." -f $entry.Arm, $batch, $timeRows.Count, $expectedTimeRows)
        }
        if ($correctnessRows.Count -ne $expectedCorrectnessRows) {
            throw ("Unexpected correctness-row count arm={0} batch={1}: got {2}, expected {3}." -f $entry.Arm, $batch, $correctnessRows.Count, $expectedCorrectnessRows)
        }
        $bad = @($correctnessRows | Where-Object { $_.exact_match -ne '1' })
        if ($bad.Count -gt 0) {
            throw "Correctness row failed arm=$($entry.Arm) batch=$batch."
        }

        $manifestRows.Add([PSCustomObject]@{
            tag = $Tag
            arm = $entry.Arm
            batch = $batch
            threads = $entry.Threads
            affinity_mask = $entry.MaskTag
            affinity_readback = ('0x{0:X}' -f $effectiveAffinity)
            raw_csv = Get-RepoRelative $rawCsv
            stderr_log = Get-RepoRelative $stderrLog
            time_rows = $timeRows.Count
            correctness_rows = $correctnessRows.Count
            binary_sha256 = $binarySha
            prereg_sha256 = $preregSha
            git_head = $head
            rustc = $rustc
            started_utc = $started
            finished_utc = $finished
        })
        $campaignLines.Add("batch arm=$($entry.Arm) batch=$batch affinity=$($entry.MaskTag) exit=0 rows=$($rows.Count)")
        Write-Host ("arm={0} batch={1} affinity={2} rows={3}" -f $entry.Arm, $batch, $entry.MaskTag, $rows.Count)
    }
}

$manifestRows | Export-Csv -LiteralPath $manifest -NoTypeInformation -Encoding UTF8
$campaignLines | Set-Content -LiteralPath $campaignLog -Encoding UTF8
Write-Host ("manifest={0}" -f (Get-RepoRelative $manifest))
Write-Host ("campaign_log={0}" -f (Get-RepoRelative $campaignLog))
