#Requires -Version 5.1
<#
.SYNOPSIS
    Stage 2 pilot: real Sapling Spend, static c=12 for n >= 16384 vs default.

.DESCRIPTION
    Frozen by
      experiments/metadata/sapling_msm_c12_pilot_preregistration_20261023.md

    Four Spend batches in ABBA order (C0, C1, C1, C0). C0 leaves all
    SAPLING_MSM_WINDOW_* variables unset. C1 sets
      SAPLING_MSM_WINDOW_C=12
      SAPLING_MSM_WINDOW_MIN_N=16384
    so only the large MSMs change; the tiny input MSMs keep their default
    size-derived window.

    This is a pilot only. It does not run Output/transaction, does not change a
    default, and does not overwrite any existing raw artifact.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_msm_c12_pilot.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,30}$')]
    [string]$Tag = 'msm_c12_pilot_20261023',
    [string]$PreregPath = 'experiments/metadata/sapling_msm_c12_pilot_preregistration_20261023.md'
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
$runner = Join-Path $RepoRoot 'scripts\run_spend_combined_profile.ps1'
$binary = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\spend_prover_smoke.exe'
$preregFull = if ([System.IO.Path]::IsPathRooted($PreregPath)) {
    $PreregPath
} else {
    Join-Path $RepoRoot $PreregPath
}
$manifest = Join-Path $metadataDir 'msm_c12_pilot_manifest_20261023.csv'
$campaignLog = Join-Path $logDir "${Tag}_campaign.log"

foreach ($path in @($runner, $binary, $preregFull)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file is missing: $path"
    }
}
foreach ($path in @($manifest, $campaignLog)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing pilot artifact: $path"
    }
}

$head = (& git -C $RepoRoot rev-parse HEAD 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "git rev-parse HEAD failed: $head"
}

$buildStdout = Join-Path $logDir "${Tag}_prebuild.stdout.log"
$buildStderr = Join-Path $logDir "${Tag}_prebuild.stderr.log"
foreach ($path in @($buildStdout, $buildStderr)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing prebuild log: $path"
    }
}
$cargo = (Get-Command cargo -ErrorAction Stop).Source
$buildArgs = 'build --release --locked --manifest-path "{0}" --bin spend_prover_smoke' -f (Join-Path $RepoRoot 'experiments\prover-smoke\Cargo.toml')
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

$plan = @(
    [PSCustomObject]@{ Order = 1; Arm = 'C0'; Label = "${Tag}_c0_b1"; WindowC = $null; WindowMinN = 0 },
    [PSCustomObject]@{ Order = 2; Arm = 'C1'; Label = "${Tag}_c1_b2"; WindowC = 12; WindowMinN = 16384 },
    [PSCustomObject]@{ Order = 3; Arm = 'C1'; Label = "${Tag}_c1_b3"; WindowC = 12; WindowMinN = 16384 },
    [PSCustomObject]@{ Order = 4; Arm = 'C0'; Label = "${Tag}_c0_b4"; WindowC = $null; WindowMinN = 0 }
)

$envNames = @(
    'SAPLING_MSM_WINDOW_C',
    'SAPLING_MSM_WINDOW_MIN_N',
    'SAPLING_MSM_ADAPTIVE_WINDOW',
    'SAPLING_MSM_WINDOW_SPLIT',
    'SAPLING_MSM_WINDOW_SPLIT_MODE',
    'SAPLING_MSM_SIGNED_DIGITS'
)
$oldEnv = @{}
foreach ($name in $envNames) {
    $oldEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

$rows = @()
$failed = $false

Add-Content -LiteralPath $campaignLog -Encoding utf8 -Value @(
    "Stage 2 c=12 pilot",
    "tag=$Tag",
    "head=$head",
    "prereg=$PreregPath",
    "prereg_sha256=$preregSha",
    "binary=$binary",
    "binary_sha256=$binarySha",
    "prebuild_stdout=$buildStdout",
    "prebuild_stderr=$buildStderr",
    "start=$((Get-UtcNow))"
)

try {
    foreach ($item in $plan) {
        foreach ($name in $envNames) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        if ($null -ne $item.WindowC) {
            $env:SAPLING_MSM_WINDOW_C = [string]$item.WindowC
        }
        if ($item.WindowMinN -gt 0) {
            $env:SAPLING_MSM_WINDOW_MIN_N = [string]$item.WindowMinN
        }

        $started = Get-UtcNow
        $childArgs = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', $runner,
            '-RepoRoot', $RepoRoot,
            '-Threads', '8',
            '-AffinityMask', '0x5555',
            '-RunDataLabel', $item.Label,
            '-AllowUntrackedOutputs'
        )

        Write-Host ("[{0}/4] {1} {2} window_c={3} min_n={4}" -f $item.Order, $item.Label, $item.Arm, $item.WindowC, $item.WindowMinN)
        $childOutput = @(& powershell.exe @childArgs 2>&1)
        $exitCode = $LASTEXITCODE
        $text = ($childOutput | ForEach-Object { [string]$_ }) -join "`n"
        Add-Content -LiteralPath $campaignLog -Encoding utf8 -Value @(
            "",
            "=== batch $($item.Order): $($item.Label) arm=$($item.Arm) window_c=$($item.WindowC) min_n=$($item.WindowMinN) ===",
            $text,
            "=== exit_code=$exitCode ==="
        )

        $batchId = ''
        $match = [regex]::Match($text, 'Batch ID:\s*(\d+)')
        if ($match.Success) {
            $batchId = $match.Groups[1].Value
        }

        $stageCsv = ''
        $stageMatch = [regex]::Match($text, 'Stage CSV:\s*(.+)')
        if ($stageMatch.Success) { $stageCsv = $stageMatch.Groups[1].Value.Trim() }

        $msmCsv = ''
        $msmMatch = [regex]::Match($text, 'MSM CSV:\s*(.+)')
        if ($msmMatch.Success) { $msmCsv = $msmMatch.Groups[1].Value.Trim() }

        $metadataPath = ''
        $metaMatch = [regex]::Match($text, 'Metadata report:\s*(.+)')
        if ($metaMatch.Success) { $metadataPath = $metaMatch.Groups[1].Value.Trim() }

        $ended = Get-UtcNow
        $rawCsv = Get-RepoRelative (Join-Path $rawDir ("sapling_spend_prover_runs_{0}.csv" -f $item.Label))

        $rows += [PSCustomObject]@{
            order        = $item.Order
            arm          = $item.Arm
            label        = $item.Label
            batch_id     = $batchId
            exit_code    = $exitCode
            start_utc    = $started
            end_utc      = $ended
            window_c     = $(if ($null -eq $item.WindowC) { '' } else { $item.WindowC })
            window_min_n = $item.WindowMinN
            threads      = 8
            affinity     = '0x5555'
            head         = $head
            prereg_sha   = $preregSha
            binary_sha   = $binarySha
            raw_csv      = $rawCsv
            stage_csv    = Get-RepoRelative $stageCsv
            msm_csv      = Get-RepoRelative $msmCsv
            metadata     = Get-RepoRelative $metadataPath
        }

        if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($batchId)) {
            $failed = $true
            break
        }

        Start-Sleep -Seconds 5
    }
}
finally {
    foreach ($name in $envNames) {
        $value = $oldEnv[$name]
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
if ($rows.Count -ne 4 -or $uniqueIds.Count -ne 4) {
    throw "Expected 4 unique batches; got rows=$($rows.Count), unique_ids=$($uniqueIds.Count)."
}

Write-Host ''
Write-Host '=== Stage 2 c=12 pilot complete ==='
Write-Host "Manifest: $manifest"
Write-Host "Campaign log: $campaignLog"
Write-Host 'Next: run scripts/analyze_msm_c12_pilot.py against this manifest.'
