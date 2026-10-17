[CmdletBinding()]
param(
    # Which prover smoke binary to drive.
    [ValidateSet('spend', 'output')]
    [string]$Prover = 'spend',

    [int]$Threads = 1,

    [long]$AffinityMask = 1,

    # Interleaved rounds. Each round runs four single-batch invocations in the
    # given order, so `Rounds` rounds of ABBA give 2*Rounds batches per arm.
    [ValidateRange(1, 8)]
    [int]$Rounds = 3,

    [ValidateSet('ABBA', 'BAAB')]
    [string]$Order = 'ABBA',

    # Raw CSV suffix prefix. The two arms land in
    #   sapling_<prover>_prover_runs_<LabelPrefix>_off.csv  (SAPLING_MSM_SIGNED_DIGITS=0)
    #   sapling_<prover>_prover_runs_<LabelPrefix>_on.csv   (SAPLING_MSM_SIGNED_DIGITS=1)
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,47}$')]
    [string]$LabelPrefix = 'msm_signed_abba',

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
$driverLog = Join-Path $logDir ("driver_target_b_{0}_t{1}_{2}_{3}.log" -f $Prover, $Threads, $maskTag, $LabelPrefix)

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

$orderChars = $Order.ToCharArray()
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# target b (signed-digit MSM) ABBA driver")
$lines.Add(("prover={0} threads={1} affinity={2} rounds={3} order={4} label_prefix={5}" -f $Prover, $Threads, $maskTag, $Rounds, $Order, $LabelPrefix))
$lines.Add(("git_head={0}" -f (& git -C $repoRoot rev-parse HEAD).Trim()))
$lines.Add(("host={0} logical_processors={1}" -f $env:COMPUTERNAME, [Environment]::ProcessorCount))

for ($round = 1; $round -le $Rounds; $round++) {
    for ($position = 1; $position -le 4; $position++) {
        $arm = if ($orderChars[$position - 1] -eq 'A') { 'off' } else { 'on' }
        $env:SAPLING_MSM_SIGNED_DIGITS = if ($arm -eq 'on') { '1' } else { '0' }
        $label = '{0}_{1}' -f $LabelPrefix, $arm
        $load = Get-HostCpuLoadPct
        $stamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
        $header = ("round={0} pos={1} arm={2} signed_digits={3} label={4} start={5} host_cpu_load_pct={6}" -f `
                $round, $position, $arm, $env:SAPLING_MSM_SIGNED_DIGITS, $label, $stamp, $load)
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
