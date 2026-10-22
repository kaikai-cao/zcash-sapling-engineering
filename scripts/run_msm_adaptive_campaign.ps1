#Requires -Version 5.1
<#
.SYNOPSIS
    Stage 1b orchestrator: gated adaptive window + tail-only intra-window split.

.DESCRIPTION
    Frozen by
      experiments/metadata/sapling_msm_adaptive_stage1b_preregistration_20261022.md

    The script only sets the preregistered environment variables and invokes the
    existing runners in the frozen order. It does not change any default value.
    Each invocation is one batch; the manifest records the batch ID, exit code,
    git HEAD, hashes, and environment.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_msm_adaptive_campaign.ps1 `
        -Tag msm_adaptive_20261022
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,30}$')]
    [string]$Tag = 'msm_adaptive_20261022',
    [string]$PreregPath = 'experiments/metadata/sapling_msm_adaptive_stage1b_preregistration_20261022.md',
    # Smoke-only truncation. The frozen formal campaign uses the default 44.
    [ValidateRange(1, 44)]
    [int]$MaxBatches = 44,
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

$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
$metadataDir = Join-Path $RepoRoot 'experiments\metadata'
foreach ($dir in @($rawDir, $logDir, $metadataDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$preregFullPath = if ([IO.Path]::IsPathRooted($PreregPath)) { $PreregPath } else { Join-Path $RepoRoot $PreregPath }
if (-not (Test-Path -LiteralPath $preregFullPath -PathType Leaf)) {
    throw "Missing preregistration: $preregFullPath"
}
$preregSha = (Get-FileHash -LiteralPath $preregFullPath -Algorithm SHA256).Hash.ToLowerInvariant()

# Worktree policy: tracked modifications block the campaign; append-only outputs
# are allowed and are recorded in the manifest through their batch IDs.
$dirty = @((& git -C $RepoRoot status --porcelain 2>$null) | Where-Object { $_ -and $_.Trim() })
$ignored = @($dirty | Where-Object { $_ -match '^\?\? (experiments/raw/|experiments/metadata/|results/)' })
$dirty = @($dirty | Where-Object { $_ -notmatch '^\?\? (experiments/raw/|experiments/metadata/|results/)' })
if (-not $AllowDirtyWorktree -and $dirty.Count -gt 0) {
    throw "Tracked working tree is dirty. Commit first, or pass -AllowDirtyWorktree (records a caveat)."
}

$spendExe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\spend_prover_smoke.exe'
$outputExe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\sapling-output-smoke.exe'
$txExe = Join-Path $RepoRoot 'experiments\transaction-smoke\target\release\tx_construct_bench.exe'
foreach ($exe in @($spendExe, $outputExe, $txExe)) {
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Missing binary: $exe"
    }
}

$paramsDir = if ([string]::IsNullOrWhiteSpace($env:ZCASH_PARAMS_DIR)) {
    'D:\Research\zcash-params'
}
else {
    $env:ZCASH_PARAMS_DIR
}
$spendParams = Join-Path $paramsDir 'sapling-spend.params'
$outputParams = Join-Path $paramsDir 'sapling-output.params'
foreach ($path in @($spendParams, $outputParams)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing parameter file: $path"
    }
}

$gitHead = (& git -C $RepoRoot rev-parse HEAD).Trim()
$spendExeSha = (Get-FileHash -LiteralPath $spendExe -Algorithm SHA256).Hash.ToLowerInvariant()
$outputExeSha = (Get-FileHash -LiteralPath $outputExe -Algorithm SHA256).Hash.ToLowerInvariant()
$txExeSha = (Get-FileHash -LiteralPath $txExe -Algorithm SHA256).Hash.ToLowerInvariant()
$spendParamsSha = (Get-FileHash -LiteralPath $spendParams -Algorithm SHA256).Hash.ToLowerInvariant()
$outputParamsSha = (Get-FileHash -LiteralPath $outputParams -Algorithm SHA256).Hash.ToLowerInvariant()

$manifestPath = Join-Path $metadataDir ("msm_adaptive_manifest_{0}.csv" -f $Tag)
$campaignLog = Join-Path $logDir ("msm_adaptive_campaign_{0}.log" -f $Tag)
$txRawCsv = Join-Path $rawDir ("sapling_tx_scaling_runs_{0}.csv" -f $Tag)
if (Test-Path -LiteralPath $manifestPath) {
    throw "Manifest already exists for tag ${Tag}: $manifestPath. Use a fresh tag; never overwrite."
}

$manifestColumns = @(
    'tag', 'order', 'arm', 'kind', 'config', 'label', 'env',
    'start_utc', 'end_utc', 'exit_code', 'batch_id',
    'git_head', 'prereg_sha256',
    'spend_exe_sha256', 'output_exe_sha256', 'tx_exe_sha256',
    'spend_params_sha256', 'output_params_sha256', 'notes'
)

function Write-ManifestRow {
    param([hashtable]$Row)
    $ordered = [ordered]@{}
    foreach ($column in $manifestColumns) {
        $ordered[$column] = if ($Row.ContainsKey($column)) { $Row[$column] } else { '' }
    }
    $object = [PSCustomObject]$ordered
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        $object | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8
    }
    else {
        $object | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Append -Encoding utf8
    }
}

function Set-ArmEnvironment {
    param([string]$Arm)
    Remove-Item Env:SAPLING_MSM_ADAPTIVE_WINDOW -ErrorAction SilentlyContinue
    Remove-Item Env:SAPLING_MSM_WINDOW_C -ErrorAction SilentlyContinue
    Remove-Item Env:SAPLING_MSM_WINDOW_SPLIT -ErrorAction SilentlyContinue
    Remove-Item Env:SAPLING_MSM_WINDOW_SPLIT_MODE -ErrorAction SilentlyContinue

    switch ($Arm) {
        'C0' { }
        'C1' { $env:SAPLING_MSM_ADAPTIVE_WINDOW = '1' }
        'C2' {
            $env:SAPLING_MSM_WINDOW_C = '13'
            $env:SAPLING_MSM_WINDOW_SPLIT = '2'
            $env:SAPLING_MSM_WINDOW_SPLIT_MODE = 'tail'
        }
        'C3' {
            $env:SAPLING_MSM_WINDOW_C = '10'
            $env:SAPLING_MSM_WINDOW_SPLIT = '4'
            $env:SAPLING_MSM_WINDOW_SPLIT_MODE = 'tail'
        }
        'C4' { $env:SAPLING_MSM_WINDOW_C = '11' }
        default { throw "Unknown arm: $Arm" }
    }
}

function Get-ArmEnvironmentDescription {
    param([string]$Arm)
    switch ($Arm) {
        'C0' { return 'default' }
        'C1' { return 'SAPLING_MSM_ADAPTIVE_WINDOW=1' }
        'C2' { return 'SAPLING_MSM_WINDOW_C=13;SPLIT=2;MODE=tail' }
        'C3' { return 'SAPLING_MSM_WINDOW_C=10;SPLIT=4;MODE=tail' }
        'C4' { return 'SAPLING_MSM_WINDOW_C=11' }
    }
}

$spendOrder = @(
    'C0', 'C1', 'C2', 'C3', 'C4', 'C4', 'C3', 'C2', 'C1', 'C0',
    'C0', 'C1', 'C2', 'C3', 'C4', 'C4', 'C3', 'C2', 'C1', 'C0'
)
$outputOrder = @('C0', 'C1', 'C4', 'C4', 'C1', 'C0', 'C0', 'C1', 'C4', 'C4', 'C1', 'C0')
$txOrder = @('C0', 'C1', 'C4', 'C4', 'C1', 'C0', 'C0', 'C1', 'C4', 'C4', 'C1', 'C0')

$plan = New-Object System.Collections.Generic.List[object]
foreach ($arm in $spendOrder) {
    $plan.Add([PSCustomObject]@{ Kind = 'spend'; Arm = $arm })
}
foreach ($arm in $outputOrder) {
    $plan.Add([PSCustomObject]@{ Kind = 'output'; Arm = $arm })
}
foreach ($arm in $txOrder) {
    $plan.Add([PSCustomObject]@{ Kind = 'tx'; Arm = $arm })
}
if ($plan.Count -ne 44) {
    throw "Internal order error: expected 44 batches, got $($plan.Count)."
}
if ($MaxBatches -lt $plan.Count) {
    $plan = @($plan.GetRange(0, $MaxBatches))
}

$oldParams = $env:ZCASH_PARAMS_DIR
$oldAdaptive = $env:SAPLING_MSM_ADAPTIVE_WINDOW
$oldWindowC = $env:SAPLING_MSM_WINDOW_C
$oldSplit = $env:SAPLING_MSM_WINDOW_SPLIT
$oldSplitMode = $env:SAPLING_MSM_WINDOW_SPLIT_MODE

Set-Content -LiteralPath $campaignLog -Encoding utf8 -Value @(
    "campaign=$Tag",
    "start_utc=$([DateTime]::UtcNow.ToString('o'))",
    "git_head=$gitHead",
    "prereg_sha256=$preregSha",
    "spend_exe_sha256=$spendExeSha",
    "output_exe_sha256=$outputExeSha",
    "tx_exe_sha256=$txExeSha",
    "spend_params_sha256=$spendParamsSha",
    "output_params_sha256=$outputParamsSha",
    "ignored_untracked_outputs=$($ignored.Count)"
)

try {
    $env:ZCASH_PARAMS_DIR = $paramsDir
    $order = 0
    foreach ($item in $plan) {
        $order++
        $arm = $item.Arm
        $kind = $item.Kind
        $config = "8t_0x5555_$arm"
        $envDescription = Get-ArmEnvironmentDescription -Arm $arm
        Set-ArmEnvironment -Arm $arm

        $start = [DateTime]::UtcNow
        $startText = $start.ToString('o')
        $batchId = ''
        $exitCode = 1
        $notes = ''

        try {
            if ($kind -eq 'spend') {
                $label = "${Tag}_spend_$($arm.ToLowerInvariant())"
                $childArgs = @(
                    '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', (Join-Path $RepoRoot 'scripts\run_spend_combined_profile.ps1'),
                    '-RepoRoot', $RepoRoot,
                    '-Threads', '8',
                    '-AffinityMask', '0x5555',
                    '-RunDataLabel', $label,
                    '-AllowUntrackedOutputs'
                )
            }
            elseif ($kind -eq 'output') {
                $label = "${Tag}_output_$($arm.ToLowerInvariant())"
                $childArgs = @(
                    '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', (Join-Path $RepoRoot 'scripts\run_pinned_prover_campaign.ps1'),
                    '-RepoRoot', $RepoRoot,
                    '-Prover', 'output',
                    '-Threads', '8',
                    '-AffinityMasks', '0x5555',
                    '-Batches', '1',
                    '-Label', $label,
                    '-AllowUntrackedOutputs'
                )
            }
            else {
                $label = "${Tag}_tx_$($arm.ToLowerInvariant())"
                $childArgs = @(
                    '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', (Join-Path $RepoRoot 'scripts\run_tx_scaling_campaign.ps1'),
                    '-RepoRoot', $RepoRoot,
                    '-Threads', '8',
                    '-AffinityMask', '0x5555',
                    '-Tag', $label,
                    '-Batches', '1',
                    '-RawCsv', $txRawCsv,
                    '-AllowUntrackedOutputs'
                )
            }

            Write-Host ("[{0}/44] {1} {2} {3}" -f $order, $kind, $arm, $envDescription)
            $childOutput = @(& powershell.exe @childArgs 2>&1)
            $exitCode = $LASTEXITCODE
            $text = ($childOutput | Out-String)
            Add-Content -LiteralPath $campaignLog -Encoding utf8 -Value @(
                "--- order=$order kind=$kind arm=$arm start=$startText exit=$exitCode ---",
                $text
            )

            $match = [regex]::Match($text, 'Batch ID:\s*(\d+)')
            if (-not $match.Success) {
                $match = [regex]::Match($text, 'batch_id=(\d+)')
            }
            if ($match.Success) {
                $batchId = $match.Groups[1].Value
            }
            if ($exitCode -ne 0) {
                $notes = "runner_exit=$exitCode"
                throw "Batch failed: order=$order kind=$kind arm=$arm exit=$exitCode"
            }
            if ([string]::IsNullOrWhiteSpace($batchId)) {
                throw "Could not parse batch ID from runner output (order=$order kind=$kind arm=$arm)."
            }
        }
        catch {
            if ($_.Exception.Message -notmatch '^Batch failed:' -and $exitCode -eq 0) { $exitCode = 1 }
            $notes = ($notes + '; ' + $_.Exception.Message).Trim('; ')
            $endText = [DateTime]::UtcNow.ToString('o')
            Write-ManifestRow @{
                tag = $Tag; order = $order; arm = $arm; kind = $kind; config = $config;
                label = $label; env = $envDescription; start_utc = $startText; end_utc = $endText;
                exit_code = $exitCode; batch_id = $batchId; git_head = $gitHead;
                prereg_sha256 = $preregSha; spend_exe_sha256 = $spendExeSha;
                output_exe_sha256 = $outputExeSha; tx_exe_sha256 = $txExeSha;
                spend_params_sha256 = $spendParamsSha; output_params_sha256 = $outputParamsSha;
                notes = $notes
            }
            throw
        }

        $endText = [DateTime]::UtcNow.ToString('o')
        Write-ManifestRow @{
            tag = $Tag; order = $order; arm = $arm; kind = $kind; config = $config;
            label = $label; env = $envDescription; start_utc = $startText; end_utc = $endText;
            exit_code = $exitCode; batch_id = $batchId; git_head = $gitHead;
            prereg_sha256 = $preregSha; spend_exe_sha256 = $spendExeSha;
            output_exe_sha256 = $outputExeSha; tx_exe_sha256 = $txExeSha;
            spend_params_sha256 = $spendParamsSha; output_params_sha256 = $outputParamsSha;
            notes = $notes
        }

        if ($order -lt $plan.Count) {
            Start-Sleep -Seconds 5
        }
    }

    Add-Content -LiteralPath $campaignLog -Encoding utf8 -Value "end_utc=$([DateTime]::UtcNow.ToString('o'))"
    Write-Host ("Campaign complete: {0}/{0} batches" -f $plan.Count)
    Write-Host "manifest: $manifestPath"
}
finally {
    if ($null -eq $oldParams) { Remove-Item Env:ZCASH_PARAMS_DIR -ErrorAction SilentlyContinue } else { $env:ZCASH_PARAMS_DIR = $oldParams }
    if ($null -eq $oldAdaptive) { Remove-Item Env:SAPLING_MSM_ADAPTIVE_WINDOW -ErrorAction SilentlyContinue } else { $env:SAPLING_MSM_ADAPTIVE_WINDOW = $oldAdaptive }
    if ($null -eq $oldWindowC) { Remove-Item Env:SAPLING_MSM_WINDOW_C -ErrorAction SilentlyContinue } else { $env:SAPLING_MSM_WINDOW_C = $oldWindowC }
    if ($null -eq $oldSplit) { Remove-Item Env:SAPLING_MSM_WINDOW_SPLIT -ErrorAction SilentlyContinue } else { $env:SAPLING_MSM_WINDOW_SPLIT = $oldSplit }
    if ($null -eq $oldSplitMode) { Remove-Item Env:SAPLING_MSM_WINDOW_SPLIT_MODE -ErrorAction SilentlyContinue } else { $env:SAPLING_MSM_WINDOW_SPLIT_MODE = $oldSplitMode }
}
