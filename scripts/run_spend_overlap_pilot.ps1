#Requires -Version 5.1
<#
.SYNOPSIS
    Stage 3 pilot: overlap independent Sapling Spend proofs on one 8-thread pool.

.DESCRIPTION
    Frozen by
      experiments/metadata/sapling_spend_overlap_pilot_preregistration_20261023.md

    Eight Spend batches in two ABBA cycles:
      S0, S1, S1, S0, S0, S1, S1, S0

    S0 runs one proof at a time. S1 runs two independent proofs concurrently
    inside one process, sharing the same 8-thread Rayon pool.

    This pilot measures BATCH THROUGHPUT, not single-proof latency. It does not
    run Output/transaction, does not change a library default, and does not
    overwrite an existing raw artifact.

    Each process loads the Spend parameters once, runs one warmup proof, then
    eight measured proofs. The batch wall reported by the binary covers only
    the eight measured proofs.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_spend_overlap_pilot.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,30}$')]
    [string]$Tag = 'spend_overlap_pilot_20261023',
    [string]$PreregPath = 'experiments/metadata/sapling_spend_overlap_pilot_preregistration_20261023.md',
    [int]$Proofs = 8,
    [int]$Warmups = 1,
    [int]$BetweenBatchSeconds = 5
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
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ''
    }
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetFullPath($RepoRoot)
    if ($full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relative = $full.Substring($root.Length).TrimStart('\', '/')
        return $relative.Replace('\', '/')
    }
    return $Path
}

$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
$metadataDir = Join-Path $RepoRoot 'experiments\metadata'
$binary = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\spend_overlap_pilot.exe'
$preregFull = if ([System.IO.Path]::IsPathRooted($PreregPath)) {
    $PreregPath
} else {
    Join-Path $RepoRoot $PreregPath
}
$manifest = Join-Path $metadataDir "spend_overlap_pilot_manifest_${Tag}.csv"
$campaignLog = Join-Path $logDir "${Tag}_campaign.log"
$rawCsv = Join-Path $rawDir "sapling_spend_overlap_pilot_${Tag}.csv"

foreach ($path in @($binary, $preregFull)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file is missing: $path"
    }
}
foreach ($path in @($manifest, $campaignLog, $rawCsv)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing pilot artifact: $path"
    }
}

$leftover = @(Get-Process -Name 'spend_overlap_pilot' -ErrorAction SilentlyContinue)
if ($leftover.Count -gt 0) {
    throw "A spend_overlap_pilot process is already running (PID(s): $($leftover.Id -join ', ')). Stop it before starting the pilot."
}

$head = (& git -C $RepoRoot rev-parse HEAD 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "git rev-parse HEAD failed: $head"
}
$dirty = (& git -C $RepoRoot status --porcelain 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "git status --porcelain failed: $dirty"
}
if (-not [string]::IsNullOrWhiteSpace($dirty)) {
    throw "Working tree is not clean. Commit the prereg, binary, runner and analyzer before the formal pilot.`n$dirty"
}

$paramsPath = $env:SAPLING_SPEND_PARAMS
if ([string]::IsNullOrWhiteSpace($paramsPath)) {
    $paramsPath = 'D:\Research\zcash-params\sapling-spend.params'
}
if (-not (Test-Path -LiteralPath $paramsPath -PathType Leaf)) {
    throw "Spend parameters not found: $paramsPath"
}

$buildStdout = Join-Path $logDir "${Tag}_prebuild.stdout.log"
$buildStderr = Join-Path $logDir "${Tag}_prebuild.stderr.log"
foreach ($path in @($buildStdout, $buildStderr)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing prebuild log: $path"
    }
}
$cargo = (Get-Command cargo -ErrorAction Stop).Source
$buildArgs = 'build --release --locked --manifest-path "{0}" --bin spend_overlap_pilot' -f (Join-Path $RepoRoot 'experiments\prover-smoke\Cargo.toml')
$buildProc = Start-Process `
    -FilePath $cargo `
    -ArgumentList $buildArgs `
    -WorkingDirectory $RepoRoot `
    -PassThru `
    -Wait `
    -RedirectStandardOutput $buildStdout `
    -RedirectStandardError $buildStderr
if ($buildProc.ExitCode -ne 0) {
    throw "Prebuild failed with exit code $($buildProc.ExitCode). Logs: $buildStdout ; $buildStderr"
}

$preregSha = Get-Sha256 $preregFull
$binarySha = Get-Sha256 $binary
$paramsSha = Get-Sha256 $paramsPath

$plan = @(
    [PSCustomObject]@{ Order = 1; Arm = 'S0'; Label = "${Tag}_s0_b1" },
    [PSCustomObject]@{ Order = 2; Arm = 'S1'; Label = "${Tag}_s1_b2" },
    [PSCustomObject]@{ Order = 3; Arm = 'S1'; Label = "${Tag}_s1_b3" },
    [PSCustomObject]@{ Order = 4; Arm = 'S0'; Label = "${Tag}_s0_b4" },
    [PSCustomObject]@{ Order = 5; Arm = 'S0'; Label = "${Tag}_s0_b5" },
    [PSCustomObject]@{ Order = 6; Arm = 'S1'; Label = "${Tag}_s1_b6" },
    [PSCustomObject]@{ Order = 7; Arm = 'S1'; Label = "${Tag}_s1_b7" },
    [PSCustomObject]@{ Order = 8; Arm = 'S0'; Label = "${Tag}_s0_b8" }
)

# Policy-changing switches must not leak in from the parent shell.
$policyEnvNames = @(
    'SAPLING_MSM_WINDOW_C',
    'SAPLING_MSM_WINDOW_MIN_N',
    'SAPLING_MSM_ADAPTIVE_WINDOW',
    'SAPLING_MSM_WINDOW_SPLIT',
    'SAPLING_MSM_WINDOW_SPLIT_MODE',
    'SAPLING_MSM_SIGNED_DIGITS',
    'SAPLING_FFT_PATH',
    'SAPLING_IN_SITU_CONVERSION_PROBE',
    'SAPLING_MSM_STAGE_TIMING'
)
$savedEnv = @{}
foreach ($name in $policyEnvNames) {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

$rows = @()
$failed = $false

Add-Content -LiteralPath $campaignLog -Encoding utf8 -Value @(
    "Stage 3 independent Spend overlap pilot",
    "tag=$Tag",
    "head=$head",
    "prereg=$PreregPath",
    "prereg_sha256=$preregSha",
    "binary=$binary",
    "binary_sha256=$binarySha",
    "params=$paramsPath",
    "params_sha256=$paramsSha",
    "proofs=$Proofs",
    "warmups=$Warmups",
    "prebuild_stdout=$buildStdout",
    "prebuild_stderr=$buildStderr",
    "start=$((Get-UtcNow))"
)

try {
    foreach ($name in $policyEnvNames) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    $env:RAYON_NUM_THREADS = '8'
    $env:SAPLING_PROFILE = '0'
    $env:SAPLING_SPEND_PARAMS = $paramsPath
    $env:SAPLING_OVERLAP_CSV = $rawCsv
    $env:SAPLING_OVERLAP_PROOFS = [string]$Proofs
    $env:SAPLING_OVERLAP_WARMUPS = [string]$Warmups
    $env:SAPLING_OVERLAP_AFFINITY = '0x5555'
    $env:SAPLING_OVERLAP_GIT_HEAD = $head

    foreach ($item in $plan) {
        $env:SAPLING_OVERLAP_ARM = $(if ($item.Arm -eq 'S0') { 'seq' } else { 'conc2' })

        $started = Get-UtcNow
        $stdoutPath = Join-Path $logDir ("{0}.stdout.log" -f $item.Label)
        $stderrPath = Join-Path $logDir ("{0}.stderr.log" -f $item.Label)
        foreach ($path in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $path) {
                throw "Refusing to overwrite existing batch log: $path"
            }
        }

        Write-Host ("[{0}/8] {1} arm={2} proofs={3} warmups={4}" -f $item.Order, $item.Label, $item.Arm, $Proofs, $Warmups)
        $proc = Start-Process `
            -FilePath $binary `
            -WorkingDirectory $RepoRoot `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -PassThru `
            -WindowStyle Hidden
        $proc.ProcessorAffinity = [IntPtr]0x5555
        $proc.WaitForExit()
        $exitCode = $proc.ExitCode
        $ended = Get-UtcNow

        $text = if (Test-Path -LiteralPath $stdoutPath) {
            (Get-Content -LiteralPath $stdoutPath -Raw)
        } else {
            ''
        }
        if ($null -eq $text) { $text = '' }
        $errText = if (Test-Path -LiteralPath $stderrPath) {
            (Get-Content -LiteralPath $stderrPath -Raw)
        } else {
            ''
        }
        if ($null -eq $errText) { $errText = '' }

        $batchId = ''
        $match = [regex]::Match($text, '(?m)^batch_id=(\d+)\s*$')
        if ($match.Success) {
            $batchId = $match.Groups[1].Value
        }
        $batchWall = ''
        $wallMatch = [regex]::Match($text, '(?m)^batch_wall_ms=([0-9.]+)\s*$')
        if ($wallMatch.Success) {
            $batchWall = $wallMatch.Groups[1].Value
        }

        Add-Content -LiteralPath $campaignLog -Encoding utf8 -Value @(
            "",
            "=== batch $($item.Order): $($item.Label) arm=$($item.Arm) ===",
            $text,
            $errText,
            "=== exit_code=$exitCode batch_id=$batchId batch_wall_ms=$batchWall ==="
        )

        $rows += [PSCustomObject]@{
            order        = $item.Order
            arm          = $item.Arm
            label        = $item.Label
            batch_id     = $batchId
            exit_code    = $exitCode
            start_utc    = $started
            end_utc      = $ended
            proofs       = $Proofs
            warmups      = $Warmups
            threads      = 8
            affinity     = '0x5555'
            head         = $head
            prereg_sha   = $preregSha
            binary_sha   = $binarySha
            params_sha   = $paramsSha
            raw_csv      = Get-RepoRelative $rawCsv
            stdout_log   = Get-RepoRelative $stdoutPath
            stderr_log   = Get-RepoRelative $stderrPath
            batch_wall_ms = $batchWall
        }

        if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($batchId)) {
            $failed = $true
            break
        }

        if ($item.Order -lt $plan.Count) {
            Start-Sleep -Seconds $BetweenBatchSeconds
        }
    }
}
finally {
    foreach ($name in $policyEnvNames) {
        $value = $savedEnv[$name]
        if ($null -eq $value) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$name" $value
        }
    }

    if ($rows.Count -gt 0) {
        $rows | Export-Csv -LiteralPath $manifest -NoTypeInformation -Encoding UTF8
    }
    Add-Content -LiteralPath $campaignLog -Encoding utf8 -Value @(
        "",
        "end=$((Get-UtcNow))",
        "failed=$failed",
        "rows=$($rows.Count)"
    )
}

if ($failed) {
    throw 'At least one pilot batch failed or did not produce a batch ID. Preserve all raw artifacts; do not rerun with the same tag.'
}

$uniqueIds = @($rows | ForEach-Object { $_.batch_id } | Sort-Object -Unique)
if ($rows.Count -ne 8 -or $uniqueIds.Count -ne 8) {
    throw "Expected 8 unique batches; got rows=$($rows.Count), unique_ids=$($uniqueIds.Count)."
}

if (Test-Path -LiteralPath $rawCsv) {
    $rawRows = @(Import-Csv -LiteralPath $rawCsv)
    $expected = 8 * $Proofs
    if ($rawRows.Count -ne $expected) {
        throw "Expected $expected raw proof rows; got $($rawRows.Count)."
    }
} else {
    throw "Raw CSV was not created: $rawCsv"
}

Write-Host ''
Write-Host '=== Stage 3 Spend overlap pilot complete ==='
Write-Host "Manifest: $manifest"
Write-Host "Raw CSV: $rawCsv"
Write-Host "Campaign log: $campaignLog"
Write-Host 'Next: run scripts/analyze_spend_overlap_pilot.py against this manifest.'
