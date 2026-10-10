param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Spend", "Output")]
    [string]$Circuit
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
$env:RAYON_NUM_THREADS = "1"

$rawDir = Join-Path $repoRoot "experiments\raw\csv"
$logDir = Join-Path $repoRoot "experiments\raw\logs"
$memoryCsv = Join-Path $rawDir "sapling_process_memory_raw.csv"

switch ($Circuit) {
    "Spend" {
        $exeName = "spend_prover_smoke.exe"
        $sourceCsv = Join-Path $rawDir "sapling_spend_prover_runs_release.csv"
    }
    "Output" {
        $exeName = "sapling-output-smoke.exe"
        $sourceCsv = Join-Path $rawDir "sapling_output_prover_runs_release.csv"
    }
}

$exe = Join-Path $repoRoot "experiments\prover-smoke\target\release\$exeName"

if (-not (Test-Path $exe)) {
    throw "找不到可执行文件：$exe"
}
if (-not (Test-Path $sourceCsv)) {
    throw "找不到原始运行 CSV：$sourceCsv"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# 保存运行前的批次号，用来识别本次运行追加的数据。
$beforeIds = @{}
foreach ($row in (Import-Csv -LiteralPath $sourceCsv)) {
    if ($row.batch_id) {
        $beforeIds[[string]$row.batch_id] = $true
    }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$logPath = Join-Path $logDir "sapling_${Circuit}_memory_${timestamp}.log"
$stderrPath = "$logPath.stderr"

Write-Host "Circuit: $Circuit"
Write-Host "Executable: $exe"
Write-Host "Log: $logPath"
Write-Host "Sampling PeakWorkingSet64 every 250 ms..."

$peakBytes = [long]0
$timer = [System.Diagnostics.Stopwatch]::StartNew()

$p = Start-Process `
    -FilePath $exe `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError $stderrPath `
    -PassThru

while ($true) {
    $p.Refresh()

    try {
        $currentPeak = [long]$p.PeakWorkingSet64
        if ($currentPeak -gt $peakBytes) {
            $peakBytes = $currentPeak
        }
    } catch {
        # Process may have exited while the sample was being read.
    }

    if ($p.HasExited) {
        break
    }

    Start-Sleep -Milliseconds 250
}

$p.WaitForExit()
$p.Refresh()
$timer.Stop()
$exitCode = $p.ExitCode

# 读取 OS 记录的峰值高水位，再做一次最终比较。
try {
    $finalPeak = [long]$p.PeakWorkingSet64
    if ($finalPeak -gt $peakBytes) {
        $peakBytes = $finalPeak
    }
} catch {}

# 从原始 CSV 识别本次进程产生的批次。
$rowsAfter = @(Import-Csv -LiteralPath $sourceCsv)
$newRows = @(
    $rowsAfter | Where-Object {
        $id = [string]$_.batch_id
        $id -and -not $beforeIds.ContainsKey($id)
    }
)
$newBatchIds = @($newRows | Select-Object -ExpandProperty batch_id -Unique)

$batchId = "unidentified-$timestamp"
$proofPass = $false

if ($newBatchIds.Count -eq 1) {
    $batchId = [string]$newBatchIds[0]
    $batchRows = @($newRows | Where-Object { $_.batch_id -eq $batchId })

    $proofPass = (
        $exitCode -eq 0 -and
        $batchRows.Count -eq 5 -and
        @($batchRows | Where-Object { $_.verified -ne "true" }).Count -eq 0
    )
}

$memoryMiB = [Math]::Round($peakBytes / 1MB, 2)

# Keep the column schema consistent with sapling_process_memory_raw.csv.
$record = [PSCustomObject][ordered]@{
    circuit              = $Circuit
    measurement_method   = "Windows Process.PeakWorkingSet64 sampled every 250ms"
    peak_working_set_mib = $memoryMiB
    rayon_threads        = 1
    build_profile        = "release"
    batch_id             = $batchId
    process_exit_code    = $exitCode
    proof_experiment_pass = $proofPass.ToString().ToLowerInvariant()
    scope_note           = "Whole process lifetime; includes parameter loading, validation, proving and verification"
}

if (Test-Path $memoryCsv) {
    $record | Export-Csv `
        -LiteralPath $memoryCsv `
        -NoTypeInformation `
        -Encoding UTF8 `
        -Append
} else {
    $record | Export-Csv `
        -LiteralPath $memoryCsv `
        -NoTypeInformation `
        -Encoding UTF8
}

Write-Host "`n=== Peak Working Set Result ==="
Write-Host "Circuit: $Circuit"
Write-Host "Batch: $batchId"
Write-Host ("Peak Working Set: {0:N2} MiB" -f $memoryMiB)
Write-Host "Process Exit Code: $exitCode"
Write-Host "Proof Experiment Pass: $proofPass"
Write-Host ("Process Duration: {0:N2} seconds" -f $timer.Elapsed.TotalSeconds)
Write-Host "Memory CSV: $memoryCsv"
Write-Host "Log: $logPath"

if ($exitCode -ne 0) {
    Write-Host "`n=== Standard Error ==="
    if (Test-Path $stderrPath) {
        Get-Content -LiteralPath $stderrPath
    }
    throw "证明进程退出码非零，请检查日志。"
}