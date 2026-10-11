param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Spend", "Output")]
    [string]$Circuit,

    [ValidateRange(1, 5)]
    [int]$Pairs = 3
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
$env:RAYON_NUM_THREADS = "1"

$rammap = "D:\Tools\RAMMap\RAMMap64.exe"
$manifest = Join-Path $repoRoot "experiments\prover-smoke\Cargo.toml"
$rawDir = Join-Path $repoRoot "experiments\raw\csv"
$logDir = Join-Path $repoRoot "experiments\raw\logs"
$comparisonCsv = Join-Path $rawDir "sapling_cache_condition_raw.csv"

switch ($Circuit) {
    "Spend" {
        $binary = "spend_prover_smoke"
        $exeName = "spend_prover_smoke.exe"
        $paramPath = "D:\Research\zcash-params\sapling-spend.params"
        $sourceCsv = Join-Path $rawDir "sapling_spend_prover_runs_release.csv"
        $passMarker = "SPEND_PROOF_EXPERIMENT=PASS"
    }
    "Output" {
        $binary = "sapling-output-smoke"
        $exeName = "sapling-output-smoke.exe"
        $paramPath = "D:\Research\zcash-params\sapling-output.params"
        $sourceCsv = Join-Path $rawDir "sapling_output_prover_runs_release.csv"
        $passMarker = "OUTPUT_PROOF_EXPERIMENT=PASS"
    }
}

foreach ($path in @($rammap, $manifest, $paramPath, $sourceCsv)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file not found: $path"
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "请在管理员 PowerShell 中运行，以允许 RAMMap 清理 Standby List。"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null

Write-Host "=== Build check ==="
& cargo build --release --manifest-path $manifest --bin $binary
if ($LASTEXITCODE -ne 0) { throw "Release build failed; experiment stopped." }

$exe = Join-Path $repoRoot "experiments\prover-smoke\target\release\$exeName"
if (-not (Test-Path -LiteralPath $exe)) { throw "找不到可执行文件：$exe" }

# Record provenance before the experiment. A Cold run clears the resulting file cache.
$engineeringCommit = (& git rev-parse HEAD).Trim()
$gitStatusLines = @(& git status --porcelain)
$engineeringDirty = [bool]($gitStatusLines.Count -gt 0)
$runnerScriptHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
$bellmanPath = Join-Path $repoRoot "vendor\bellman\src\multiexp.rs"
$bellmanHash = (Get-FileHash -LiteralPath $bellmanPath -Algorithm SHA256).Hash
$paramsHash = (Get-FileHash -LiteralPath $paramPath -Algorithm SHA256).Hash
$paramsBytes = (Get-Item -LiteralPath $paramPath).Length

$saplingRepo = "D:\Research\zcash-sapling-crypto"
$saplingCommit = ""
if (Test-Path -LiteralPath (Join-Path $saplingRepo ".git")) {
    $saplingCommit = (& git -C $saplingRepo rev-parse HEAD).Trim()
}

# Read the parameter file into the Windows file cache before each Warm trial.
function Invoke-ParameterPreRead {
    param([string]$Path)
    $buffer = New-Object byte[] (1024 * 1024)
    $total = 0L
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    try {
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $total += $read
        }
    }
    finally {
        $stream.Dispose()
    }
    $timer.Stop()
    return [PSCustomObject]@{
        Bytes = $total
        ElapsedMs = [Math]::Round($timer.Elapsed.TotalMilliseconds, 3)
    }
}

function Get-Median {
    param([double[]]$Values)
    $sorted = @($Values | Sort-Object)
    if ($sorted.Count -eq 0) { return $null }
    $middle = [int][Math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2 -eq 1) { return [Math]::Round($sorted[$middle], 3) }
    return [Math]::Round(($sorted[$middle - 1] + $sorted[$middle]) / 2, 3)
}

$sessionId = Get-Date -Format "yyyyMMdd_HHmmss"
$sessionStart = (Get-Date).ToString("o")
$summary = @()
$sequenceNumber = 0

for ($pair = 1; $pair -le $Pairs; $pair++) {
    # Counterbalance condition order: C-W, W-C, C-W, ...
    if ($pair % 2 -eq 1) { $order = @("Cold", "Warm") }
    else { $order = @("Warm", "Cold") }

    foreach ($condition in $order) {
        $sequenceNumber++
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
        $stdoutPath = Join-Path $logDir ("sapling_{0}_{1}_cachecmp_{2}.log" -f $Circuit, $condition, $stamp)
        $stderrPath = "$stdoutPath.stderr"
        $clearPath = Join-Path $logDir ("rammap_{0}_cachecmp_{1}.log" -f $Circuit, $stamp)
        $preReadBytes = 0L
        $preReadMs = $null
        $cacheLabel = ""

        Write-Host "`n=== Pair $pair / $Pairs; sequence $sequenceNumber / $($Pairs * 2): $condition ==="

        if ($condition -eq "Cold") {
            $cacheLabel = "standby_list_cleared_approximate"
            # No parameter-file reads after this command and before launching the prover.
            & $rammap "-accepteula" "-Et" 2>&1 | Tee-Object -FilePath $clearPath
            $rammapExit = $LASTEXITCODE
            Write-Host "RAMMAP_EXIT_CODE=$rammapExit"
            if ($rammapExit -ne 0) { throw "RAMMap clear failed. Preserve logs; stopping." }
        }
        else {
            $cacheLabel = "parameter_file_preread_approximate"
            $preRead = Invoke-ParameterPreRead -Path $paramPath
            $preReadBytes = [long]$preRead.Bytes
            $preReadMs = [double]$preRead.ElapsedMs
            Write-Host "PREWARM_BYTES=$preReadBytes"
            Write-Host "PREWARM_READ_MS=$preReadMs"
        }

        # Identify the new proving batch without altering existing records.
        $beforeIds = @{}
        foreach ($row in (Import-Csv -LiteralPath $sourceCsv)) {
            if ($row.batch_id) { $beforeIds[[string]$row.batch_id] = $true }
        }

        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        $process = Start-Process `
            -FilePath $exe `
            -WorkingDirectory $repoRoot `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -PassThru
        $process.WaitForExit()
        $process.Refresh()
        $timer.Stop()
        $exitCode = $process.ExitCode

        $stdout = if (Test-Path -LiteralPath $stdoutPath) { [System.IO.File]::ReadAllText($stdoutPath) } else { "" }
        if ($exitCode -ne 0) { throw "Prover exit code $exitCode. Preserve logs and stop." }
        if ($stdout -notmatch [regex]::Escape($passMarker)) { throw "Success marker missing. Preserve logs and stop." }

        $rowsAfter = @(Import-Csv -LiteralPath $sourceCsv)
        $newRows = @(
            $rowsAfter | Where-Object {
                $_.batch_id -and -not $beforeIds.ContainsKey([string]$_.batch_id)
            }
        )
        $batchIds = @($newRows | Select-Object -ExpandProperty batch_id -Unique)
        if ($batchIds.Count -ne 1) { throw "Cannot uniquely identify this process batch; preserve logs and stop." }
        $batchId = [string]$batchIds[0]
        $batchRows = @($newRows | Where-Object { $_.batch_id -eq $batchId } | Sort-Object { [int]$_.run })
        if ($batchRows.Count -ne 5) { throw "Batch $batchId should contain 5 rows; found $($batchRows.Count)." }
        if (@($batchRows | Where-Object { $_.verified -ne "true" }).Count -gt 0) { throw "Batch $batchId contains failed verification." }

        $stderrText = if (Test-Path -LiteralPath $stderrPath) { [System.IO.File]::ReadAllText($stderrPath) } else { "" }
        $msmCalls = @(
            foreach ($line in ($stderrText -split "`r?`n")) {
                if ($line -match 'BELLMAN_MSM_PROFILE call_id=(\d+).*?elapsed_ms=([\d.]+)') {
                    [PSCustomObject]@{
                        CallId = [int]$Matches[1]
                        ElapsedMs = [double]$Matches[2]
                    }
                }
            }
        )
        if ($msmCalls.Count -ne 40) {
            Write-Warning "Expected 40 MSM timing records, found $($msmCalls.Count). Proof results will still be retained."
        }

        $rowsToAppend = @(
            foreach ($row in $batchRows) {
                $runNo = [int]$row.run
                $lowerCallId = ($runNo - 1) * 8 + 1
                $upperCallId = $runNo * 8
                $runCalls = @($msmCalls | Where-Object { $_.CallId -ge $lowerCallId -and $_.CallId -le $upperCallId })
                $msmSumMs = $null
                $msmSharePct = $null
                if ($runCalls.Count -eq 8) {
                    $msmSumMs = [Math]::Round(($runCalls | Measure-Object -Property ElapsedMs -Sum).Sum, 3)
                    $msmSharePct = [Math]::Round(100 * $msmSumMs / [double]$row.prove_ms, 2)
                }
                [PSCustomObject][ordered]@{
                    session_id = $sessionId
                    session_start = $sessionStart
                    circuit = $Circuit
                    pair = $pair
                    sequence = $sequenceNumber
                    cache_condition = $cacheLabel
                    process_batch_id = $batchId
                    run = [int]$row.run
                    params_read_validate_ms = [double]$row.params_read_validate_ms
                    prepare_vk_ms = [double]$row.prepare_vk_ms
                    input_prep_ms = [double]$row.input_prep_ms
                    prove_ms = [double]$row.prove_ms
                    msm_profile_count = $msmCalls.Count
                    msm_elapsed_sum_ms = $msmSumMs
                    msm_to_prove_pct = $msmSharePct
                    verify_ms = [double]$row.verify_ms
                    proof_bytes = [int]$row.proof_bytes
                    verified = [string]$row.verified
                    rayon_threads = 1
                    build_profile = "release"
                    process_exit_code = $exitCode
                    process_elapsed_ms = [Math]::Round($timer.Elapsed.TotalMilliseconds, 3)
                    preread_bytes = $preReadBytes
                    preread_elapsed_ms = $preReadMs
                    parameter_file_bytes = $paramsBytes
                    parameter_file_sha256 = $paramsHash
                    bellman_multiexp_sha256 = $bellmanHash
                    runner_script_sha256 = $runnerScriptHash
                    engineering_commit = $engineeringCommit
                    engineering_worktree_dirty_at_start = $engineeringDirty
                    sapling_crypto_commit = $saplingCommit
                    stdout_log = $stdoutPath.Replace($repoRoot + [System.IO.Path]::DirectorySeparatorChar, "")
                    stderr_log = $stderrPath.Replace($repoRoot + [System.IO.Path]::DirectorySeparatorChar, "")
                    rammap_log = if ($condition -eq "Cold") { $clearPath.Replace($repoRoot + [System.IO.Path]::DirectorySeparatorChar, "") } else { "" }
                }
            }
        )

        if (Test-Path -LiteralPath $comparisonCsv) {
            $rowsToAppend | Export-Csv -LiteralPath $comparisonCsv -NoTypeInformation -Encoding UTF8 -Append
        }
        else {
            $rowsToAppend | Export-Csv -LiteralPath $comparisonCsv -NoTypeInformation -Encoding UTF8
        }

        $proveValues = @($batchRows | ForEach-Object { [double]$_.prove_ms })
        $msmShares = @($rowsToAppend | Where-Object { $null -ne $_.msm_to_prove_pct } | ForEach-Object { [double]$_.msm_to_prove_pct })
        $summary += [PSCustomObject]@{
            Pair = $pair
            Sequence = $sequenceNumber
            Condition = $cacheLabel
            BatchId = $batchId
            ParamsReadValidateMs = [double]$batchRows[0].params_read_validate_ms
            ProveMedianMs = Get-Median $proveValues
            ProveMinMs = ($proveValues | Measure-Object -Minimum).Minimum
            ProveMaxMs = ($proveValues | Measure-Object -Maximum).Maximum
            MsmShareMedianPct = Get-Median $msmShares
            MsmProfileCount = $msmCalls.Count
            AllVerified = $true
            PreReadMs = $preReadMs
            ProcessElapsedMs = [Math]::Round($timer.Elapsed.TotalMilliseconds, 3)
            Log = $stdoutPath.Replace($repoRoot + [System.IO.Path]::DirectorySeparatorChar, "")
        }

        Write-Host "BATCH_ID=$batchId"
        Write-Host "ALL_VERIFIED=True"
        Write-Host "PROCESS_ELAPSED_MS=$([Math]::Round($timer.Elapsed.TotalMilliseconds, 3))"
        if ($pair -lt $Pairs -or $condition -eq $order[0]) { Start-Sleep -Seconds 3 }
    }
}

Write-Host "`n=== Cache-condition comparison summary ==="
$summary | Format-Table -AutoSize | Out-String -Width 220 | Write-Host
Write-Host "CACHE_CSV=$comparisonCsv"
Write-Host "RAW_PROVER_CSV=$sourceCsv"
Write-Host "ENGINEERING_COMMIT=$engineeringCommit"
Write-Host "ENGINEERING_WORKTREE_DIRTY_AT_START=$engineeringDirty"
Write-Host "BELLMAN_MULTEXP_SHA256=$bellmanHash"
Write-Host "RUNNER_SCRIPT_SHA256=$runnerScriptHash"
Write-Host "PARAMETER_FILE_SHA256=$paramsHash"
Write-Host "Completed $($summary.Count) independent processes; all passed unless this script threw an error."
