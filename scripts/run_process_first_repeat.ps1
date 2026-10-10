param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Spend", "Output")]
    [string]$Circuit,

    [ValidateRange(1, 10)]
    [int]$Processes = 3
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
$env:RAYON_NUM_THREADS = "1"

$manifest = Join-Path $repoRoot "experiments\prover-smoke\Cargo.toml"
$rawDir = Join-Path $repoRoot "experiments\raw\csv"
$logDir = Join-Path $repoRoot "experiments\raw\logs"
$resultCsv = Join-Path $rawDir "sapling_process_first_repeat_raw.csv"
$loadCsv = Join-Path $rawDir "sapling_system_load_samples.csv"

switch ($Circuit) {
    "Spend" {
        $binary = "spend_prover_smoke"
        $exeName = "spend_prover_smoke.exe"
        $sourceCsv = Join-Path $rawDir "sapling_spend_prover_runs_release.csv"
        $passMarker = "SPEND_PROOF_EXPERIMENT=PASS"
    }
    "Output" {
        $binary = "sapling-output-smoke"
        $exeName = "sapling-output-smoke.exe"
        $sourceCsv = Join-Path $rawDir "sapling_output_prover_runs_release.csv"
        $passMarker = "OUTPUT_PROOF_EXPERIMENT=PASS"
    }
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "=== Build: $Circuit ==="
& cargo build --release --manifest-path $manifest --bin $binary
if ($LASTEXITCODE -ne 0) {
    throw "编译失败，停止实验。"
}

$exe = Join-Path $repoRoot "experiments\prover-smoke\target\release\$exeName"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "找不到可执行文件：$exe"
}
if (-not (Test-Path -LiteralPath $sourceCsv)) {
    throw "找不到原始运行 CSV：$sourceCsv"
}

function Get-MedianValue {
    param([double[]]$Values)

    $sorted = @($Values | Sort-Object)
    if ($sorted.Count -eq 0) { return $null }

    $middle = [int][Math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2 -eq 1) {
        return [Math]::Round($sorted[$middle], 3)
    }

    return [Math]::Round(
        ($sorted[$middle - 1] + $sorted[$middle]) / 2,
        3
    )
}

function Save-SystemSamples {
    param(
        [object[]]$Samples,
        [string]$Path,
        [string]$CircuitName,
        [int]$ProcessIndex,
        [string]$BatchId
    )

    if ($Samples.Count -eq 0) {
        Write-Warning "本次没有采集到系统负载样本。"
        return
    }

    $rows = @(
        foreach ($sample in $Samples) {
            [PSCustomObject]@{
                timestamp           = $sample.timestamp
                circuit             = $CircuitName
                process_index       = $ProcessIndex
                batch_id            = $BatchId
                system_cpu_pct      = $sample.system_cpu_pct
                cpu_sample_status   = $sample.cpu_sample_status
                process_memory_mib  = $sample.process_memory_mib
            }
        }
    )

    if (Test-Path -LiteralPath $Path) {
        $rows | Export-Csv -LiteralPath $Path -NoTypeInformation -Encoding UTF8 -Append
    } else {
        $rows | Export-Csv -LiteralPath $Path -NoTypeInformation -Encoding UTF8
    }
}

$priorResultRows = @()
if (Test-Path -LiteralPath $resultCsv) {
    $priorResultRows = @(Import-Csv -LiteralPath $resultCsv)
}
$priorCircuitRows = @($priorResultRows | Where-Object { $_.circuit -eq $Circuit })
if ($priorCircuitRows.Count -gt 0) {
    $nextIndex = [int](($priorCircuitRows | Measure-Object -Property process_index -Maximum).Maximum) + 1
} else {
    $nextIndex = 1
}

$summary = @()

for ($offset = 0; $offset -lt $Processes; $offset++) {
    $processIndex = [int]$nextIndex + $offset
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
    $logPath = Join-Path $logDir ("sapling_{0}_first_repeat_{1}_{2}.log" -f $Circuit, $processIndex, $timestamp)
    $stderrPath = "$logPath.stderr"

    # Record which batches already exist before launching the new process.
    $beforeIds = @{}
    foreach ($row in (Import-Csv -LiteralPath $sourceCsv)) {
        if ($row.batch_id) { $beforeIds[[string]$row.batch_id] = $true }
    }

    Write-Host "`n=== $Circuit process $($offset + 1) / $Processes ==="
    Write-Host "Log: $logPath"

    $cpuSamples = @()
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process `
        -FilePath $exe `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    while ($true) {
        $p.Refresh()
        if ($p.HasExited) { break }

        $cpuPct = $null
        $cpuStatus = "ok"
        try {
            $counter = Get-CimInstance `
                -ClassName Win32_PerfFormattedData_PerfOS_Processor `
                -Filter "Name='_Total'" `
                -ErrorAction Stop
            if ($null -ne $counter) {
                $cpuPct = [double]$counter.PercentProcessorTime
            } else {
                $cpuStatus = "counter_unavailable"
            }
        } catch {
            $cpuStatus = "counter_error"
        }

        $p.Refresh()
        $memoryMiB = $null
        try { $memoryMiB = [Math]::Round($p.WorkingSet64 / 1MB, 3) } catch {}

        $cpuSamples += [PSCustomObject]@{
            timestamp = (Get-Date).ToString("o")
            system_cpu_pct = $cpuPct
            cpu_sample_status = $cpuStatus
            process_memory_mib = $memoryMiB
        }

        Start-Sleep -Milliseconds 500
    }

    $p.WaitForExit()
    $p.Refresh()
    $exitCode = $p.ExitCode
    $timer.Stop()

    $stdout = Get-Content -LiteralPath $logPath -Raw
    $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }

    # The Output and Spend binaries do not print batch_id to stdout.
    # Identify the new batch by comparing the source CSV before and after the run.
    $batchId = ""
    try {
        $rowsAfter = @(Import-Csv -LiteralPath $sourceCsv)
        $newRows = @(
            $rowsAfter | Where-Object {
                $id = [string]$_.batch_id
                $id -and -not $beforeIds.ContainsKey($id)
            }
        )
        $newBatchIds = @($newRows | Select-Object -ExpandProperty batch_id -Unique)

        if ($newBatchIds.Count -ne 1) {
            throw "无法从源 CSV 唯一识别本次新增批次；发现 $($newBatchIds.Count) 个新批次。"
        }
        $batchId = [string]$newBatchIds[0]
    } finally {
        # Save samples even when batch identification fails, so measurements are not lost.
        Save-SystemSamples `
            -Samples $cpuSamples `
            -Path $loadCsv `
            -CircuitName $Circuit `
            -ProcessIndex $processIndex `
            -BatchId $batchId
    }

    if ($exitCode -ne 0) {
        throw "实验进程退出码为 $exitCode。请检查日志：$logPath`n$stderr"
    }
    if ($stdout -notmatch [regex]::Escape($passMarker)) {
        throw "日志中没有成功标记 $passMarker。请保留日志：$logPath"
    }

    $batchRows = @(
        $newRows | Where-Object { $_.batch_id -eq $batchId } | Sort-Object { [int]$_.run }
    )
    if ($batchRows.Count -ne 5) {
        throw "批次 $batchId 应有 5 次运行，实际为 $($batchRows.Count)。请检查原始 CSV。"
    }

    $parsedRows = @(
        foreach ($row in $batchRows) {
            [PSCustomObject]@{
                circuit                  = $Circuit
                process_index            = $processIndex
                batch_id                 = $batchId
                process_exit_code        = $exitCode
                params_read_validate_ms = [double]$row.params_read_validate_ms
                prepare_vk_ms            = [double]$row.prepare_vk_ms
                input_prep_ms            = [double]$row.input_prep_ms
                run                      = [int]$row.run
                run_mode                 = if ([int]$row.run -eq 1) { "first_prove_in_process" } else { "repeat_prove_same_process" }
                prove_ms                 = [double]$row.prove_ms
                verify_ms                = [double]$row.verify_ms
                proof_bytes              = [int]$row.proof_bytes
                verified                 = [bool]::Parse([string]$row.verified)
                rayon_threads            = 1
                build_profile            = "release"
            }
        }
    )

    if (@($parsedRows | Where-Object { -not $_.verified }).Count -gt 0) {
        throw "批次 $batchId 存在验证失败。请保留原始数据并检查日志。"
    }

    if (Test-Path -LiteralPath $resultCsv) {
        $parsedRows | Export-Csv -LiteralPath $resultCsv -NoTypeInformation -Encoding UTF8 -Append
    } else {
        $parsedRows | Export-Csv -LiteralPath $resultCsv -NoTypeInformation -Encoding UTF8
    }

    $laterProves = @($parsedRows | Where-Object { $_.run -gt 1 } | ForEach-Object { [double]$_.prove_ms })
    $validCpuSamples = @($cpuSamples | Where-Object { $null -ne $_.system_cpu_pct } | ForEach-Object { [double]$_.system_cpu_pct })

    $cpuMax = $null
    if ($validCpuSamples.Count -gt 0) {
        $cpuMax = ($validCpuSamples | Measure-Object -Maximum).Maximum
    }

    $summary += [PSCustomObject]@{
        Circuit             = $Circuit
        Process             = $processIndex
        Batch               = $batchId
        ParameterLoad_ms    = $parsedRows[0].params_read_validate_ms
        FirstProve_ms       = $parsedRows[0].prove_ms
        LaterProveMedian_ms = Get-MedianValue $laterProves
        LaterRunCount       = $laterProves.Count
        CPU_Samples         = $validCpuSamples.Count
        CPU_Median_pct      = Get-MedianValue $validCpuSamples
        CPU_Max_pct         = $cpuMax
        AllVerified         = $true
        ExitCode            = $exitCode
        Duration_s          = [Math]::Round($timer.Elapsed.TotalSeconds, 2)
        Log                 = $logPath
    }

    Write-Host "Batch: $batchId | AllVerified: True | ExitCode: $exitCode"
    if ($offset -lt ($Processes - 1)) { Start-Sleep -Seconds 5 }
}

Write-Host "`n=== Process first/repeat summary ==="
$summary | Format-Table -AutoSize
Write-Host "`nRaw results: $resultCsv"
Write-Host "System load samples: $loadCsv"
Write-Host "Raw logs: $logDir"
