$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $repoRoot
$env:RAYON_NUM_THREADS = '1'

$exe = Join-Path $repoRoot 'experiments\prover-smoke\target\release\spend_prover_smoke.exe'
$sourceCsv = Join-Path $repoRoot 'experiments\raw\csv\sapling_spend_prover_runs_release.csv'
$rawCsvDir = Join-Path $repoRoot 'experiments\raw\csv'
$logDir = Join-Path $repoRoot 'experiments\raw\logs'

if (-not (Test-Path -LiteralPath $exe)) { throw "Spend executable not found: $exe" }
if (-not (Test-Path -LiteralPath $sourceCsv)) { throw "Spend CSV not found: $sourceCsv" }

New-Item -ItemType Directory -Force -Path $logDir, $rawCsvDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$stdoutPath = Join-Path $logDir "sapling_spend_cpu_diag_$stamp.log"
$stderrPath = "$stdoutPath.stderr"
$sampleCsv = Join-Path $rawCsvDir "sapling_spend_cpu_diagnostic_$stamp.csv"

$counterPaths = @(
    '\Processor Information(*)\Actual Frequency',
    '\Processor Information(*)\% Processor Performance',
    '\Processor Information(*)\% of Maximum Frequency',
    '\Processor Information(*)\% Processor Time',
    '\Processor(_Total)\% Processor Time',
    '\Process(*)\% Processor Time',
    '\Process(*)\ID Process'
)

function Get-Quantile {
    param([object[]]$Values, [double]$Quantile)
    $sorted = @($Values | Where-Object { $null -ne $_ } | ForEach-Object { [double]$_ } | Sort-Object)
    if ($sorted.Count -eq 0) { return $null }
    $index = [int][Math]::Floor(($sorted.Count - 1) * $Quantile)
    return [Math]::Round([double]$sorted[$index], 2)
}

Write-Host '=== Counter preflight (one sample; no proving process yet) ==='
$null = Get-Counter -Counter $counterPaths -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
Write-Host 'COUNTER_PREFLIGHT=PASS'

$beforeIds = @{}
Import-Csv -LiteralPath $sourceCsv | ForEach-Object {
    if ($_.batch_id) { $beforeIds[[string]$_.batch_id] = $true }
}

$engineeringCommit = (git rev-parse HEAD).Trim()
$rayonThreads = $env:RAYON_NUM_THREADS
$logicalProcessors = [Environment]::ProcessorCount

Write-Host "ENGINEERING_COMMIT=$engineeringCommit"
Write-Host "RAYON_THREADS=$rayonThreads"
Write-Host "LOGICAL_PROCESSORS=$logicalProcessors"
Write-Host "STDOUT_LOG=$stdoutPath"
Write-Host "STDERR_LOG=$stderrPath"
Write-Host "SAMPLE_CSV=$sampleCsv"
Write-Host "`n=== Starting one instrumented Spend process ==="

$process = Start-Process -FilePath $exe -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru

$timer = [System.Diagnostics.Stopwatch]::StartNew()
$sampleRows = [System.Collections.Generic.List[object]]::new()
$sampleErrors = 0

while ($true) {
    $process.Refresh()
    if ($process.HasExited) { break }

    $sampleTimestamp = (Get-Date).ToString('o')
    try {
        $snapshot = Get-Counter -Counter $counterPaths -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
        $cs = @($snapshot.CounterSamples)

        $frequency = @($cs | Where-Object {
            $_.Path -match '\\Processor Information\([^)]+\)\\Actual Frequency$' -and
            $_.InstanceName -notmatch 'Total' -and [double]$_.CookedValue -gt 0
        } | ForEach-Object { [double]$_.CookedValue })

        $performance = @($cs | Where-Object {
            $_.Path -match '\\Processor Information\([^)]+\)\\% Processor Performance$' -and
            $_.InstanceName -notmatch 'Total' -and [double]$_.CookedValue -ge 0
        } | ForEach-Object { [double]$_.CookedValue })

        $pctMaximum = @($cs | Where-Object {
            $_.Path -match '\\Processor Information\([^)]+\)\\% of Maximum Frequency$' -and
            $_.InstanceName -notmatch 'Total' -and [double]$_.CookedValue -ge 0
        } | ForEach-Object { [double]$_.CookedValue })

        $coreCpu = @($cs | Where-Object {
            $_.Path -match '\\Processor Information\([^)]+\)\\% Processor Time$' -and
            $_.InstanceName -notmatch 'Total' -and [double]$_.CookedValue -ge 0
        } | ForEach-Object { [double]$_.CookedValue })

        $systemCpuSample = $cs | Where-Object {
            $_.Path -match '\\Processor\(_Total\)\\% Processor Time$'
        } | Select-Object -First 1
        $systemCpu = if ($null -ne $systemCpuSample) { [Math]::Round([double]$systemCpuSample.CookedValue, 2) } else { $null }

        $pidSample = $cs | Where-Object {
            $_.Path -match '\\Process\([^)]+\)\\ID Process$' -and
            [int]$_.CookedValue -eq $process.Id
        } | Select-Object -First 1

        $processCpuSample = $null
        if ($null -ne $pidSample) {
            $processCpuSample = $cs | Where-Object {
                $_.InstanceName -eq $pidSample.InstanceName -and
                $_.Path -match '\\Process\([^)]+\)\\% Processor Time$'
            } | Select-Object -First 1
        }

        $processCpu = if ($null -ne $processCpuSample) { [Math]::Round([double]$processCpuSample.CookedValue, 2) } else { $null }
        $processMachinePct = if ($null -ne $processCpu) { [Math]::Round($processCpu / $logicalProcessors, 2) } else { $null }

        $sampleRows.Add([PSCustomObject][ordered]@{
            timestamp                         = $sampleTimestamp
            elapsed_seconds                   = [Math]::Round($timer.Elapsed.TotalSeconds, 2)
            pid                               = $process.Id
            system_cpu_pct                    = $systemCpu
            process_cpu_pct_one_core_scale    = $processCpu
            process_cpu_pct_machine_equiv     = $processMachinePct
            active_core_frequency_max_mhz     = (Get-Quantile -Values $frequency -Quantile 1.0)
            core_frequency_median_mhz         = (Get-Quantile -Values $frequency -Quantile 0.5)
            core_frequency_p95_mhz             = (Get-Quantile -Values $frequency -Quantile 0.95)
            processor_performance_max_pct     = (Get-Quantile -Values $performance -Quantile 1.0)
            processor_performance_median_pct  = (Get-Quantile -Values $performance -Quantile 0.5)
            pct_of_max_frequency_max_pct      = (Get-Quantile -Values $pctMaximum -Quantile 1.0)
            pct_of_max_frequency_median_pct   = (Get-Quantile -Values $pctMaximum -Quantile 0.5)
            core_cpu_time_max_pct             = (Get-Quantile -Values $coreCpu -Quantile 1.0)
            core_cpu_time_median_pct          = (Get-Quantile -Values $coreCpu -Quantile 0.5)
            sample_error                     = ''
        })
    }
    catch {
        $sampleErrors++
        $sampleRows.Add([PSCustomObject][ordered]@{
            timestamp = $sampleTimestamp
            elapsed_seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 2)
            pid = $process.Id
            system_cpu_pct = $null
            process_cpu_pct_one_core_scale = $null
            process_cpu_pct_machine_equiv = $null
            active_core_frequency_max_mhz = $null
            core_frequency_median_mhz = $null
            core_frequency_p95_mhz = $null
            processor_performance_max_pct = $null
            processor_performance_median_pct = $null
            pct_of_max_frequency_max_pct = $null
            pct_of_max_frequency_median_pct = $null
            core_cpu_time_max_pct = $null
            core_cpu_time_median_pct = $null
            sample_error = $_.Exception.Message
        })
        Start-Sleep -Milliseconds 250
    }

    $process.Refresh()
}

$process.WaitForExit()
$process.Refresh()
$timer.Stop()
$exitCode = $process.ExitCode
$sampleRows | Export-Csv -LiteralPath $sampleCsv -NoTypeInformation -Encoding UTF8

$stdout = Get-Content -LiteralPath $stdoutPath -Raw
$stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { '' }

$rowsAfter = @(Import-Csv -LiteralPath $sourceCsv)
$newRows = @($rowsAfter | Where-Object {
    $_.batch_id -and -not $beforeIds.ContainsKey([string]$_.batch_id)
})
$newBatchIds = @($newRows | Select-Object -ExpandProperty batch_id -Unique)
$batchId = if ($newBatchIds.Count -eq 1) { [string]$newBatchIds[0] } else { '' }
$batchRows = @($newRows | Where-Object { $_.batch_id -eq $batchId } | Sort-Object { [int]$_.run })

Write-Host "`n=== Process result ==="
Write-Host "PROVER_EXIT_CODE=$exitCode"
Write-Host "BATCH_ID=$batchId"
Write-Host "PROOF_ROWS=$($batchRows.Count)"
Write-Host "ALL_VERIFIED=$(@($batchRows | Where-Object { $_.verified -ne 'true' }).Count -eq 0 -and $batchRows.Count -eq 5)"
Write-Host "CPU_SAMPLES=$($sampleRows.Count)"
Write-Host "COUNTER_SAMPLE_ERRORS=$sampleErrors"
Write-Host "SAMPLE_CSV=$sampleCsv"

if ($batchRows.Count -gt 0) {
    Write-Host "`n=== Proof timings ==="
    $batchRows | Select-Object run, params_read_validate_ms, prove_ms, verify_ms, proof_bytes, verified | Format-Table -AutoSize
}

$validSamples = @($sampleRows | Where-Object { $_.sample_error -eq '' })
if ($validSamples.Count -gt 0) {
    $systemCpuValues = @($validSamples | ForEach-Object { $_.system_cpu_pct })
    $processCpuValues = @($validSamples | ForEach-Object { $_.process_cpu_pct_one_core_scale })
    $processMachineValues = @($validSamples | ForEach-Object { $_.process_cpu_pct_machine_equiv })
    $activeFreqValues = @($validSamples | ForEach-Object { $_.active_core_frequency_max_mhz })
    $perfValues = @($validSamples | ForEach-Object { $_.processor_performance_max_pct })

    Write-Host "`n=== CPU/frequency summary across time samples ==="
    $cpuSummary = [PSCustomObject][ordered]@{
        ValidSamples = $validSamples.Count
        SystemCpuMedianPct = (Get-Quantile -Values $systemCpuValues -Quantile 0.5)
        SystemCpuP95Pct = (Get-Quantile -Values $systemCpuValues -Quantile 0.95)
        ProcessCpuMedianPctOneCoreScale = (Get-Quantile -Values $processCpuValues -Quantile 0.5)
        ProcessCpuP95PctOneCoreScale = (Get-Quantile -Values $processCpuValues -Quantile 0.95)
        ProcessCpuP95MachineEquivalentPct = (Get-Quantile -Values $processMachineValues -Quantile 0.95)
        ActiveCoreFreqMaxMedianMHz = (Get-Quantile -Values $activeFreqValues -Quantile 0.5)
        ActiveCoreFreqMaxP95MHz = (Get-Quantile -Values $activeFreqValues -Quantile 0.95)
        ProcessorPerformanceMaxMedianPct = (Get-Quantile -Values $perfValues -Quantile 0.5)
        ProcessorPerformanceMaxP95Pct = (Get-Quantile -Values $perfValues -Quantile 0.95)
    }
    $cpuSummary | Format-List
}

$msmMatches = [regex]::Matches($stderr, 'BELLMAN_MSM_PROFILE call_id=(\d+).*?elapsed_ms=([\d.]+)')
Write-Host "`nMSM_PROFILE_COUNT=$($msmMatches.Count)"
if ($msmMatches.Count -eq 40 -and $batchRows.Count -eq 5) {
    Write-Host "`n=== MSM elapsed sums aligned to proof runs ==="
    $msmSummary = @(
        for ($i = 0; $i -lt 5; $i++) {
            $callStart = $i * 8 + 1
            $callEnd = $i * 8 + 8
            $callValues = @(
                foreach ($m in $msmMatches) {
                    $id = [int]$m.Groups[1].Value
                    if ($id -ge $callStart -and $id -le $callEnd) { [double]$m.Groups[2].Value }
                }
            )
            $sumMs = ($callValues | Measure-Object -Sum).Sum
            $proveMs = [double]$batchRows[$i].prove_ms
            [PSCustomObject]@{
                Run = $i + 1
                ProveMs = [Math]::Round($proveMs, 3)
                MsmElapsedSumMs = [Math]::Round($sumMs, 3)
                MsmToProvePct = [Math]::Round(100 * $sumMs / $proveMs, 2)
            }
        }
    )
    $msmSummary | Format-Table -AutoSize
}

Write-Host "`n=== File hashes ==="
Get-FileHash -Algorithm SHA256 -LiteralPath $stdoutPath, $stderrPath, $sampleCsv | Select-Object Path, Hash | Format-Table -AutoSize

if ($exitCode -ne 0) { throw "Spend process failed; keep all logs and raw data." }
if ($batchRows.Count -ne 5 -or @($batchRows | Where-Object { $_.verified -ne 'true' }).Count -gt 0) {
    throw 'Expected five verified proofs; inspect saved logs and CSV before doing anything else.'
}
