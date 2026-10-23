# Run the exploratory unit-cost decomposition probe (single P-core, 0x1).
#
# Exploratory only: no pre-registered gates. It splits the Phase C finding
# (bellman_1t / blst_1t = 1.90x on H-query G1 with matched modelled op
# counts) by layer: fill add, reduce add/double, affine conversion, field
# multiplication. Output: experiments/raw/logs/msm_arith_probe_20261023.*.log

[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [long]$AffinityMask = 0x1
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $runnerPath = $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($runnerPath)) {
        throw 'Cannot resolve runner script path. Pass -RepoRoot explicitly.'
    }
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $runnerPath) '..')).Path
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

$exe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\msm_arith_probe.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Required artifact is missing: $exe (build with: cargo build --release --bin msm_arith_probe)"
}

$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.WorkingDirectory = $RepoRoot
$startInfo.UseShellExecute = $false
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true

$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.ProcessorAffinity = [IntPtr]([int64]$AffinityMask)
$readback = [int64]$proc.ProcessorAffinity
if ($readback -ne [int64]$AffinityMask) {
    $proc.Kill()
    throw ("Affinity read-back mismatch: requested 0x{0:X}, got 0x{1:X}" -f $AffinityMask, $readback)
}

$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()

Set-Content -LiteralPath (Join-Path $logDir 'msm_arith_probe_20261023.stdout.log') -Value $stdout -Encoding utf8
Set-Content -LiteralPath (Join-Path $logDir 'msm_arith_probe_20261023.stderr.log') -Value $stderr -Encoding utf8

Write-Host "affinity_readback=0x$($readback.ToString('X')) exit=$($proc.ExitCode)"
$stdout | Write-Host
