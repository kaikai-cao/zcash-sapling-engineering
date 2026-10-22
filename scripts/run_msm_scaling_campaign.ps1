#Requires -Version 5.1
<#
.SYNOPSIS
    Stage 0 orchestrator: MSM scaling-knee diagnosis campaign.

.DESCRIPTION
    Frozen by
    experiments/metadata/sapling_msm_scaling_diagnosis_preregistration_20261022.md
    (commit hash recorded at run time). This script does not change algorithms
    or defaults; it only runs the existing instrumented binaries in the frozen
    order and records a manifest.

    Arms (see preregistration section 3.3):
      S-Scale   Spend  1t 0x1, 2t/4t/16t 0xFFFF, 2t/4t 0x5555 (2 batches/config)
      S-ABBA    Spend  8t 0xFFFF vs 0x5555 (ABBA, 4 batches/mask)
      S-Window  Spend  8t 0x5555, c = 10/11/12/13 (2 batches/c)
      O-Scale   Output 1t 0x1, 16t 0xFFFF (2 batches/config)
      O-ABBA    Output 8t 0xFFFF vs 0x5555 (ABBA, 2 batches/mask)
      T-Scale   Tx     1t 0x1, 16t 0xFFFF (2 batches/config)
      T-ABBA    Tx     8t 0xFFFF vs 0x5555 (ABBA, 2 batches/mask)

    No analysis is performed here. The analyzer independently rechecks the raw
    data and computes the preregistered metrics.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_msm_scaling_campaign.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',

    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,39}$')]
    [string]$Tag = 'msm_scaling_20261022',

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
    $dirty = @((& git -C $RepoRoot status --porcelain 2>$null) | Where-Object {
            $_ -and $_.Trim() -and $_ -notmatch '^\?\? (experiments/raw/|experiments/metadata/|results/)'
        })
    if ($dirty.Count -gt 0) {
        throw "Working tree is dirty. Commit Stage 0 scripts first, or pass -AllowDirtyWorktree (records a caveat)."
    }
}

$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
$metadataDir = Join-Path $RepoRoot 'experiments\metadata'
foreach ($dir in @($rawDir, $logDir, $metadataDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

if ($Tag -ne 'msm_scaling_20261022') {
    throw "Stage 0 is frozen to tag 'msm_scaling_20261022'; refusing to run with tag '$Tag'."
}

$manifestPath = Join-Path $metadataDir ("msm_scaling_manifest_{0}.csv" -f $Tag)
if (Test-Path -LiteralPath $manifestPath) {
    throw "Manifest already exists; refusing to overwrite: $manifestPath"
}

$spendRunner = Join-Path $RepoRoot 'scripts\run_spend_combined_profile.ps1'
$outputRunner = Join-Path $RepoRoot 'scripts\run_pinned_prover_campaign.ps1'
$txRunner = Join-Path $RepoRoot 'scripts\run_tx_scaling_campaign.ps1'
foreach ($runner in @($spendRunner, $outputRunner, $txRunner)) {
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw "Missing runner: $runner"
    }
}

$spendExe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\spend_prover_smoke.exe'
$outputExe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\sapling-output-smoke.exe'
$txExe = Join-Path $RepoRoot 'experiments\transaction-smoke\target\release\tx_construct_bench.exe'
foreach ($exe in @($spendExe, $outputExe, $txExe)) {
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Missing binary: $exe (build release binaries first)"
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

$gitHead = (& git -C $RepoRoot rev-parse HEAD).Trim()
$worktreeDirty = @((& git -C $RepoRoot status --porcelain 2>$null) | Where-Object {
        $_ -and $_.Trim() -and $_ -notmatch '^\?\? (experiments/raw/|experiments/metadata/|results/)'
    }).Count -gt 0
$hostInfo = "$([Environment]::MachineName) / $([Environment]::ProcessorCount) LP / $((Get-CimInstance Win32_Processor).Name)"
$preregPath = Join-Path $metadataDir 'sapling_msm_scaling_diagnosis_preregistration_20261022.md'
$preregHash = (Get-FileHash -LiteralPath $preregPath -Algorithm SHA256).Hash.ToLowerInvariant()

Write-Host ('=' * 70)
Write-Host 'Stage 0 MSM scaling-knee diagnosis'
Write-Host ('=' * 70)
Write-Host ("git_head={0}" -f $gitHead)
Write-Host ("worktree_dirty={0}" -f $worktreeDirty)
Write-Host ("host={0}" -f $hostInfo)
Write-Host ("preregistration_sha256={0}" -f $preregHash)
Write-Host ("manifest={0}" -f $manifestPath)
Write-Host ''

$manifest = New-Object System.Collections.Generic.List[object]
$order = 0

function Get-SpendBatchIds {
    $ids = New-Object System.Collections.Generic.HashSet[string]
    Get-ChildItem -LiteralPath $rawDir -Filter 'sapling_spend_stage_profile_*.csv' -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.BaseName -match '^sapling_spend_stage_profile_(\d+)$') {
            [void]$ids.Add($Matches[1])
        }
    }
    return , $ids
}

function Get-OutputBatchIds {
    $path = Join-Path $rawDir 'sapling_output_prover_runs_msm_scaling_20261022_output.csv'
    $ids = New-Object System.Collections.Generic.HashSet[string]
    if (Test-Path -LiteralPath $path) {
        Import-Csv -LiteralPath $path | ForEach-Object {
            if ($_.batch_id) { [void]$ids.Add([string]$_.batch_id) }
        }
    }
    return , $ids
}

function Get-TxBatchIds {
    $path = Join-Path $rawDir 'sapling_tx_scaling_runs_msm_scaling_20261022.csv'
    $ids = New-Object System.Collections.Generic.HashSet[string]
    if (Test-Path -LiteralPath $path) {
        Import-Csv -LiteralPath $path | ForEach-Object {
            if ($_.batch_id) { [void]$ids.Add([string]$_.batch_id) }
        }
    }
    return , $ids
}

function Diff-Ids {
    param(
        [System.Collections.Generic.HashSet[string]]$Before,
        [System.Collections.Generic.HashSet[string]]$After
    )
    $new = New-Object System.Collections.Generic.List[string]
    foreach ($id in $After) {
        if (-not $Before.Contains($id)) { $new.Add($id) }
    }
    return ($new | Sort-Object)
}

function Invoke-StageRunner {
    param(
        [Parameter(Mandatory = $true)][string]$Arm,
        [Parameter(Mandatory = $true)][string]$Config,
        [Parameter(Mandatory = $true)][string]$Runner,
        [Parameter(Mandatory = $true)][string[]]$RunnerArgs,
        [string]$EnvName = '',
        [string]$EnvValue = '',
        [string]$Kind = 'spend'
    )

    $script:order++
    $order = $script:order
    $start = (Get-Date).ToUniversalTime()
    Write-Host ('-' * 70)
    Write-Host ("[{0}] arm={1} config={2} kind={3}" -f $order, $Arm, $Config, $Kind)
    Write-Host ("    runner={0}" -f (Split-Path -Leaf $Runner))
    Write-Host ("    args={0}" -f ($RunnerArgs -join ' '))
    if ($EnvName) { Write-Host ("    env {0}={1}" -f $EnvName, $EnvValue) }

    # Snapshot batch-id universe before the child runs.
    $before = if ($Kind -eq 'spend') { Get-SpendBatchIds } elseif ($Kind -eq 'output') { Get-OutputBatchIds } else { Get-TxBatchIds }

    $oldEnv = $null
    if ($EnvName) {
        $oldEnv = [Environment]::GetEnvironmentVariable($EnvName, 'Process')
        [Environment]::SetEnvironmentVariable($EnvName, $EnvValue, 'Process')
    }

    try {
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Runner @RunnerArgs 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        if ($EnvName) {
            if ($null -eq $oldEnv) { Remove-Item "Env:$EnvName" -ErrorAction SilentlyContinue }
            else { [Environment]::SetEnvironmentVariable($EnvName, $oldEnv, 'Process') }
        }
    }

    $end = (Get-Date).ToUniversalTime()
    $output | ForEach-Object { Write-Host $_ }

    $after = if ($Kind -eq 'spend') { Get-SpendBatchIds } elseif ($Kind -eq 'output') { Get-OutputBatchIds } else { Get-TxBatchIds }
    $newIds = Diff-Ids -Before $before -After $after

    $envOverride = if ($EnvName) { "$EnvName=$EnvValue" } else { '' }
    $manifest.Add([PSCustomObject]@{
            tag             = $Tag
            order           = $order
            arm             = $Arm
            config          = $Config
            kind            = $Kind
            runner_args     = ($RunnerArgs -join ' ')
            env_override    = $envOverride
            start_utc       = $start.ToString('o')
            end_utc         = $end.ToString('o')
            exit_code       = $exitCode
            new_batch_ids   = ($newIds -join ';')
            batch_count     = @($newIds).Count
            git_head        = $gitHead
            prereg_sha256   = $preregHash
        })

    if ($exitCode -ne 0) {
        $manifest | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding UTF8
        throw ("Runner failed (arm={0} config={1} exit={2}). Manifest preserved at {3}." -f $Arm, $Config, $exitCode, $manifestPath)
    }
    if (@($newIds).Count -eq 0) {
        $manifest | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding UTF8
        throw ("Runner produced no new batch id (arm={0} config={1}). Manifest preserved at {2}." -f $Arm, $Config, $manifestPath)
    }

    Start-Sleep -Seconds 5
}

# ---------------------------------------------------------------------------
# Arm S-Scale: 2 batches per config, ascending then descending.
# ---------------------------------------------------------------------------
$sScaleConfigs = @(
    [PSCustomObject]@{ t = 1; m = 0x1; label = "${Tag}_spend_t1_0x1" },
    [PSCustomObject]@{ t = 2; m = 0xFFFF; label = "${Tag}_spend_t2_0xffff" },
    [PSCustomObject]@{ t = 4; m = 0xFFFF; label = "${Tag}_spend_t4_0xffff" },
    [PSCustomObject]@{ t = 16; m = 0xFFFF; label = "${Tag}_spend_t16_0xffff" },
    [PSCustomObject]@{ t = 2; m = 0x5555; label = "${Tag}_spend_t2_0x5555" },
    [PSCustomObject]@{ t = 4; m = 0x5555; label = "${Tag}_spend_t4_0x5555" }
)

foreach ($batchPass in @(1, 2)) {
    $configs = if ($batchPass -eq 1) { $sScaleConfigs } else { @($sScaleConfigs | Sort-Object -Property t -Descending) }
    foreach ($cfg in $configs) {
        $maskTag = '0x{0:X}' -f $cfg.m
        $runnerArgList = @(
            '-RepoRoot', $RepoRoot,
        '-AllowUntrackedOutputs',
            '-Threads', "$($cfg.t)",
            '-AffinityMask', "$($cfg.m)",
            '-BranchCounters', 'disabled',
            '-InnerStageTiming', 'enabled',
            '-RunDataLabel', $cfg.label
        )
        Invoke-StageRunner -Arm 'S-Scale' -Config ("t{0}_{1}_pass{2}" -f $cfg.t, $maskTag, $batchPass) `
            -Runner $spendRunner -RunnerArgs $runnerArgList -Kind 'spend'
    }
}

# ---------------------------------------------------------------------------
# Arm S-ABBA: 8t FFFF vs 5555, 4 batches per mask.
# ---------------------------------------------------------------------------
$abbaMasks = @(0xFFFF, 0x5555, 0x5555, 0xFFFF, 0xFFFF, 0x5555, 0x5555, 0xFFFF)
for ($i = 0; $i -lt $abbaMasks.Count; $i++) {
    $mask = $abbaMasks[$i]
    $maskTag = '0x{0:X}' -f $mask
    $label = "${Tag}_spend_t8_$($maskTag.TrimStart('0x').ToLower())"
    $runnerArgList = @(
        '-RepoRoot', $RepoRoot,
        '-AllowUntrackedOutputs',
        '-Threads', '8',
        '-AffinityMask', "$mask",
        '-BranchCounters', 'disabled',
        '-InnerStageTiming', 'enabled',
        '-RunDataLabel', $label
    )
    Invoke-StageRunner -Arm 'S-ABBA' -Config ("t8_{0}_abba{1}" -f $maskTag, ($i + 1)) `
        -Runner $spendRunner -RunnerArgs $runnerArgList -Kind 'spend'
}

# ---------------------------------------------------------------------------
# Arm S-Window: 8t 5555, c = 13,11,12,10,10,12,11,13 (palindrome).
# ---------------------------------------------------------------------------
$windowOrder = @(13, 11, 12, 10, 10, 12, 11, 13)
foreach ($c in $windowOrder) {
    $label = "${Tag}_spend_t8_0x5555_c$c"
    $runnerArgList = @(
        '-RepoRoot', $RepoRoot,
        '-AllowUntrackedOutputs',
        '-Threads', '8',
        '-AffinityMask', '0x5555',
        '-BranchCounters', 'disabled',
        '-InnerStageTiming', 'enabled',
        '-RunDataLabel', $label
    )
    Invoke-StageRunner -Arm 'S-Window' -Config ("t8_0x5555_c{0}" -f $c) `
        -Runner $spendRunner -RunnerArgs $runnerArgList -EnvName 'SAPLING_MSM_WINDOW_C' -EnvValue "$c" -Kind 'spend'
}

# ---------------------------------------------------------------------------
# Arms O-Scale / O-ABBA (Output).
# ---------------------------------------------------------------------------
function Invoke-OutputRunner {
    param([string]$Arm, [string]$Config, [int]$Threads, [long]$Mask, [int]$Batches, [string]$Label)

    $runnerArgList = @(
        '-RepoRoot', $RepoRoot,
        '-AllowUntrackedOutputs',
        '-Prover', 'output',
        '-Threads', "$Threads",
        '-AffinityMasks', "$Mask",
        '-Batches', "$Batches",
        '-Label', $Label
    )
    Invoke-StageRunner -Arm $Arm -Config $Config -Runner $outputRunner -RunnerArgs $runnerArgList -Kind 'output'
}

foreach ($pass in @(1, 2)) {
    $seq = if ($pass -eq 1) { @(1, 16) } else { @(16, 1) }
    foreach ($t in $seq) {
        $mask = if ($t -eq 1) { 0x1 } else { 0xFFFF }
        Invoke-OutputRunner -Arm 'O-Scale' -Config ("t{0}_pass{1}" -f $t, $pass) -Threads $t -Mask $mask -Batches 1 -Label "${Tag}_output"
    }
}
$outputAbba = @(0xFFFF, 0x5555, 0x5555, 0xFFFF)
for ($i = 0; $i -lt $outputAbba.Count; $i++) {
    $mask = $outputAbba[$i]
    $maskTag = '0x{0:X}' -f $mask
    Invoke-OutputRunner -Arm 'O-ABBA' -Config ("t8_{0}_abba{1}" -f $maskTag, ($i + 1)) -Threads 8 -Mask $mask -Batches 1 -Label "${Tag}_output"
}

# ---------------------------------------------------------------------------
# Arms T-Scale / T-ABBA (real transaction).
# ---------------------------------------------------------------------------
function Invoke-TxRunner {
    param([string]$Arm, [string]$Config, [int]$Threads, [long]$Mask, [string]$BatchTag)

    $runnerArgList = @(
        '-RepoRoot', $RepoRoot,
        '-AllowUntrackedOutputs',
        '-Threads', "$Threads",
        '-AffinityMask', "$Mask",
        '-Tag', $BatchTag,
        '-Batches', '1'
    )
    Invoke-StageRunner -Arm $Arm -Config $Config -Runner $txRunner -RunnerArgs $runnerArgList -Kind 'tx'
}

foreach ($pass in @(1, 2)) {
    $seq = if ($pass -eq 1) { @(1, 16) } else { @(16, 1) }
    foreach ($t in $seq) {
        $mask = if ($t -eq 1) { 0x1 } else { 0xFFFF }
        $maskTag = '0x{0:X}' -f $mask
        $batchTag = "${Tag}_tx_t${t}_$($maskTag.TrimStart('0x').ToLower())_pass${pass}"
        Invoke-TxRunner -Arm 'T-Scale' -Config ("t{0}_{1}_pass{2}" -f $t, $maskTag, $pass) -Threads $t -Mask $mask -BatchTag $batchTag
    }
}
$txAbba = @(0xFFFF, 0x5555, 0x5555, 0xFFFF)
for ($i = 0; $i -lt $txAbba.Count; $i++) {
    $mask = $txAbba[$i]
    $maskTag = '0x{0:X}' -f $mask
    $batchTag = "${Tag}_tx_t8_$($maskTag.TrimStart('0x').ToLower())_abba$($i + 1)"
    Invoke-TxRunner -Arm 'T-ABBA' -Config ("t8_{0}_abba{1}" -f $maskTag, ($i + 1)) -Threads 8 -Mask $mask -BatchTag $batchTag
}

$manifest | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding UTF8
Write-Host ''
Write-Host ('=' * 70)
Write-Host ("CAMPAIGN COMPLETE: {0} runner invocations" -f $manifest.Count)
Write-Host ("manifest: {0}" -f $manifestPath)
Write-Host ('=' * 70)
