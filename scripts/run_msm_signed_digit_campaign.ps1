[CmdletBinding()]
param(
    # Which prover smoke binary to drive.
    [ValidateSet('spend', 'output')]
    [string]$Prover = 'spend',

    [int]$Threads = 1,

    [long]$AffinityMask = 1,

    # One entry per interleaved round; each round runs four single-batch
    # invocations in the given order, so N rounds of ABBA give 2N batches per
    # arm. The last round is order-reversed by default so a monotone host drift
    # cannot masquerade as an arm effect.
    [ValidateCount(1, 8)]
    [string[]]$Orders = @('ABBA', 'ABBA', 'BAAB'),

    # Raw CSV suffix prefix. The two arms land in
    #   sapling_<prover>_prover_runs_<LabelPrefix>_off.csv  (<SwitchVar>=0)
    #   sapling_<prover>_prover_runs_<LabelPrefix>_on.csv   (<SwitchVar>=1)
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,47}$')]
    [string]$LabelPrefix = 'msm_signed_abba',

    # Process-level environment switch that selects the arm. The default is the
    # target-b switch; target a reuses the same driver with
    #   -SwitchVar SAPLING_MSM_LAZY_RECODING
    # so the arm semantics (off = 0 = historical behaviour) are identical.
    [ValidatePattern('^[A-Z][A-Z0-9_]{2,63}$')]
    [string]$SwitchVar = 'SAPLING_MSM_SIGNED_DIGITS',

    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runner = Join-Path $PSScriptRoot 'run_pinned_prover_campaign.ps1'
$maskTag = '0x{0:X}' -f $AffinityMask
$logDir = Join-Path $repoRoot 'experiments\raw\logs'
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$driverLog = Join-Path $logDir ("driver_{0}_{1}_t{2}_{3}_{4}_{5}.log" -f $SwitchVar.ToLowerInvariant(), 'abba', $Prover, $Threads, $maskTag, (Get-Date).ToString('yyyyMMdd-HHmmss'))

function Get-HostCpuLoadPct {
    # Instantaneous total CPU load. Used only as the "is the host quiet" record;
    # it never enters the timing comparison.
    try {
        $samples = (Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 2 -ErrorAction Stop).CounterSamples
        return [math]::Round($samples[-1].CookedValue, 1)
    }
    catch {
        try {
            return [double](Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
        }
        catch {
            return -1
        }
    }
}

if ($Threads -gt 0) { $env:RAYON_NUM_THREADS = "$Threads" } else { Remove-Item Env:RAYON_NUM_THREADS -ErrorAction SilentlyContinue }
$env:ZCASH_PARAMS_DIR = if ($env:ZCASH_PARAMS_DIR) { $env:ZCASH_PARAMS_DIR } else { 'D:\Research\zcash-params' }

$orderList = @()
foreach ($order in $Orders) {
    if ($order -notmatch '^(ABBA|BAAB)$') {
        throw ("Round order '{0}' is not one of ABBA/BAAB." -f $order)
    }
    $orderList += $order
}
$roundCount = $orderList.Count

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add(("# ABBA driver switch={0}" -f $SwitchVar))
$lines.Add(("prover={0} threads={1} affinity={2} rounds={3} orders={4} label_prefix={5}" -f $Prover, $Threads, $maskTag, $roundCount, ($orderList -join '/'), $LabelPrefix))
$lines.Add(("git_head={0}" -f (& git -C $repoRoot rev-parse HEAD).Trim()))
$lines.Add(("host={0} logical_processors={1}" -f $env:COMPUTERNAME, [Environment]::ProcessorCount))

for ($round = 1; $round -le $roundCount; $round++) {
    $orderChars = $orderList[$round - 1].ToCharArray()
    $lines.Add(("round={0} order={1}" -f $round, $orderList[$round - 1]))
    for ($position = 1; $position -le 4; $position++) {
        $arm = if ($orderChars[$position - 1] -eq 'A') { 'off' } else { 'on' }
        $armValue = if ($arm -eq 'on') { '1' } else { '0' }
        [Environment]::SetEnvironmentVariable($SwitchVar, $armValue, 'Process')
        $label = '{0}_{1}' -f $LabelPrefix, $arm
        $load = Get-HostCpuLoadPct
        $stamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
        $header = ("round={0} pos={1} arm={2} {3}={4} label={5} start={6} host_cpu_load_pct={7}" -f `
                $round, $position, $arm, $SwitchVar, $armValue, $label, $stamp, $load)
        Write-Host "===== $header ====="
        $lines.Add($header)

        $runnerArgs = @{
            Prover             = $Prover
            Threads            = @($Threads)
            AffinityMasks      = @($AffinityMask)
            Batches            = 1
            Label              = $label
        }
        if ($AllowDirtyWorktree) { $runnerArgs['AllowDirtyWorktree'] = $true }

        $output = & $runner @runnerArgs 2>&1
        foreach ($line in $output) {
            if ($line -match 'median_prove_ms|batch failed|CAMPAIGN COMPLETE|Exception') {
                Write-Host ("  {0}" -f $line)
                $lines.Add('  ' + $line)
            }
        }
    }
}

[IO.File]::WriteAllLines($driverLog, $lines, [System.Text.UTF8Encoding]::new($false))
Write-Host ("driver log: {0}" -f $driverLog)
