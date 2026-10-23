# Run the Phase C MSM kernel benchmark (A/A calibration + blst control).
#
# Frozen design: experiments/metadata/sapling_msm_kernel_stagec_preregistration_20261023.md
# Each condition runs ONE process; the binary itself performs all blocks in-process
# with the frozen ABBA-balanced arm order. This script only sets affinity (and reads
# it back), sets RAYON_NUM_THREADS, records provenance, and appends raw output.
#
# Usage:
#   powershell -File scripts\run_msm_kernel_bench.ps1 [-RepoRoot <path>] [-Tag msm_kernel_bench_20261023]

[CmdletBinding()]
param(
    [string]$RepoRoot = '',

    [string]$Tag = 'msm_kernel_bench_20261023',

    # Conditions: mask -> rayon threads -> raw csv suffix. 0x5555 = the 8 P-cores
    # (LP0,2,4,6,8,10,12,14; SMT siblings excluded); 0x1 = a single P-core.
    [object[]]$Conditions = @(
        @{ Mask = [long]0x5555; Threads = 8; Suffix = '8t' },
        @{ Mask = [long]0x1; Threads = 1; Suffix = '1t' }
    ),

    [int]$Blocks = 8,

    [switch]$AllowDirtyWorktree,
    [switch]$AllowUntrackedOutputs
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

$dirtyRaw = @(& git -C $RepoRoot status --porcelain 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "git status failed: $($dirtyRaw -join ' ')"
}
if ($AllowUntrackedOutputs) {
    $dirtyRaw = @($dirtyRaw | Where-Object {
            $_ -and $_.Trim() -and $_ -notmatch '^\?\? (experiments/raw/|experiments/metadata/|results/)'
        })
}
if (-not $AllowDirtyWorktree) {
    if (@($dirtyRaw | Where-Object { $_ -and $_.Trim() }).Count -gt 0) {
        throw 'Working tree is dirty. Commit first, or pass -AllowDirtyWorktree (records a caveat).'
    }
}

$exe = Join-Path $RepoRoot 'experiments\prover-smoke\target\release\msm_kernel_bench.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Required artifact is missing: $exe (build with: cargo build --release --bin msm_kernel_bench)"
}

$rawDir = Join-Path $RepoRoot 'experiments\raw\csv'
$logDir = Join-Path $RepoRoot 'experiments\raw\logs'
foreach ($dir in @($rawDir, $logDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$gitHead = (& git -C $RepoRoot rev-parse HEAD).Trim()
$dirtyAtStart = @($dirtyRaw | Where-Object { $_ -and $_.Trim() }).Count -gt 0
$rustcVersion = (& rustc -V).Trim()

# Reject affinity masks that cannot exist on this machine (same guard as the
# pinned prover campaign runner).
$logicalProcessors = [Environment]::ProcessorCount
$maskLimit = 1L -shl $logicalProcessors
foreach ($cond in $Conditions) {
    if ($cond.Mask -lt 0) {
        throw ("Affinity mask {0} is negative (a 32-bit literal overflows). Use the real mask for this {1}-logical-processor machine, max 0x{2:X}." -f $cond.Mask, $logicalProcessors, ($maskLimit - 1))
    }
    if ($cond.Mask -ge $maskLimit) {
        throw ("Affinity mask 0x{0:X} sets bits beyond the {1} logical processors on this machine (max 0x{2:X})." -f $cond.Mask, $logicalProcessors, ($maskLimit - 1))
    }
}

Write-Host "tag=$Tag"
Write-Host "exe=$exe"
Write-Host "exe_sha256=$exeHash"
Write-Host "git_head=$gitHead"
Write-Host "dirty_at_start=$dirtyAtStart"
Write-Host "rustc=$rustcVersion"
Write-Host "logical_processors=$logicalProcessors"
Write-Host "blocks=$Blocks"
Write-Host ''

$oldThreads = [Environment]::GetEnvironmentVariable('RAYON_NUM_THREADS', 'Process')

try {
    foreach ($cond in $Conditions) {
        $maskTag = '0x{0:X}' -f $cond.Mask
        $suffix = $cond.Suffix
        $rawCsv = Join-Path $rawDir ("{0}_{1}.csv" -f $Tag, $suffix)
        $stdoutLog = Join-Path $logDir ("{0}_{1}.stdout.log" -f $Tag, $suffix)
        $stderrLog = Join-Path $logDir ("{0}_{1}.stderr.log" -f $Tag, $suffix)

        $env:RAYON_NUM_THREADS = "$($cond.Threads)"
        $env:MSM_KB_BLOCKS = "$Blocks"
        $env:MSM_KB_CSV = $rawCsv

        Write-Host '=================================================='
        Write-Host "condition affinity_mask=$maskTag rayon_threads=$($cond.Threads) suffix=$suffix"
        Write-Host "raw_csv=$rawCsv"
        Write-Host '=================================================='

        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $exe
        $startInfo.WorkingDirectory = $RepoRoot
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.ProcessorAffinity = $cond.Mask

        $proc = [System.Diagnostics.Process]::Start($startInfo)
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()

        Set-Content -LiteralPath $stdoutLog -Value $stdout -Encoding utf8
        Set-Content -LiteralPath $stderrLog -Value $stderr -Encoding utf8
        $stdout | Write-Host

        if ($proc.ExitCode -ne 0) {
            throw ("bench exited {0} for affinity_mask={1} threads={2}; stderr: {3}" -f $proc.ExitCode, $maskTag, $cond.Threads, $stderr)
        }

        Write-Host ("condition_done affinity_mask={0} rayon_threads={1} exit=0" -f $maskTag, $cond.Threads)
        Write-Host ''
    }
}
finally {
    if ($null -ne $oldThreads) {
        $env:RAYON_NUM_THREADS = $oldThreads
    }
    else {
        Remove-Item Env:RAYON_NUM_THREADS -ErrorAction SilentlyContinue
    }
    Remove-Item Env:MSM_KB_BLOCKS -ErrorAction SilentlyContinue
    Remove-Item Env:MSM_KB_CSV -ErrorAction SilentlyContinue
}

Write-Host "MSM_KERNEL_BENCH_CAMPAIGN=DONE tag=$Tag"
