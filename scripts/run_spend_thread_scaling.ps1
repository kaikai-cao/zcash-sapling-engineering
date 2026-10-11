
$ErrorActionPreference = "Stop"

# ============================================================
# Sapling Spend Thread Scaling Experiment
# Goal: measure proving performance across Rayon thread counts.
# No algorithm or scheduling changes are performed by this script.
# Compatible with Windows PowerShell 5.1.
# ============================================================

# 1. Resolve repository root from this script's actual location.
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo

$manifest = Join-Path $repo "experiments\prover-smoke\Cargo.toml"
$rawDir = Join-Path $repo "experiments\raw\csv"
$formalCsv = Join-Path $rawDir "sapling_spend_prover_runs_release.csv"

if (!(Test-Path -LiteralPath $manifest)) {
    throw "Cargo manifest not found: $manifest"
}

if (!(Test-Path -LiteralPath $rawDir)) {
    New-Item -ItemType Directory -Path $rawDir -Force | Out-Null
}

$cargoCommand = Get-Command cargo -ErrorAction Stop
$cargoExe = $cargoCommand.Source

if ([string]::IsNullOrWhiteSpace($cargoExe)) {
    throw "Could not resolve the cargo executable path."
}

# 2. Create uniquely named output and log files.
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

$outputCsv = Join-Path $rawDir "sapling_spend_thread_scaling_$stamp.csv"
$partialCsv = "$outputCsv.partial"

$threadsToTest = @(1, 2, 4, 8, 16, 20)

# 3. Preserve current environment variables.
$oldProfile = [Environment]::GetEnvironmentVariable(
    "SAPLING_PROFILE", "Process"
)
$oldThreads = [Environment]::GetEnvironmentVariable(
    "RAYON_NUM_THREADS", "Process"
)

# 4. The smoke binary appends its own raw CSV.
# Back it up and restore it in finally, preventing contamination
# of the existing formal benchmark data.
$hadFormalCsv = Test-Path -LiteralPath $formalCsv
$backupCsv = Join-Path $env:TEMP "spend_formal_csv_backup_$stamp.csv"

if ($hadFormalCsv) {
    Copy-Item -LiteralPath $formalCsv -Destination $backupCsv -Force
}

$completedSuccessfully = $false

try {
    # SAPLING_PROFILE=0 disables diagnostic log output.
    # This is not the untouched upstream source; results should
    # be compared within this campaign, not silently merged with
    # historical batches collected under other instrumentation.
    $env:SAPLING_PROFILE = "0"

    $header = "batch_id,threads,run,prove_ms,verify_ms,proof_bytes,verified"
    [System.IO.File]::WriteAllText(
        $partialCsv,
        "$header`r`n",
        [System.Text.Encoding]::UTF8
    )

    Write-Host "Repository: $repo"
    Write-Host "Manifest:   $manifest"
    Write-Host "Output:     $outputCsv"
    Write-Host "Threads:    $($threadsToTest -join ', ')"
    Write-Host "Profile:    off"
    Write-Host ""

    foreach ($t in $threadsToTest) {
        Write-Host "========================================"
        Write-Host "Starting Spend batch: Rayon threads=$t"
        Write-Host "========================================"

        $env:RAYON_NUM_THREADS = "$t"

        $logTag = "sapling_spend_threads_${t}_$stamp"
        $stdoutLog = Join-Path $env:TEMP "$logTag.stdout.log"
        $stderrLog = Join-Path $env:TEMP "$logTag.stderr.log"

        # Use Start-Process so stderr output from Cargo is captured
        # as a log rather than accidentally terminating the script.
        $argumentLine = 'run --release --manifest-path "{0}" --bin spend_prover_smoke' -f $manifest

        $process = Start-Process `
            -FilePath $cargoExe `
            -ArgumentList $argumentLine `
            -WorkingDirectory $repo `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog

        if ($process.ExitCode -ne 0) {
            Write-Host "Cargo exited with code $($process.ExitCode)."
            Write-Host "STDOUT log: $stdoutLog"
            Write-Host "STDERR log: $stderrLog"

            if (Test-Path -LiteralPath $stderrLog) {
                Get-Content -LiteralPath $stderrLog -Tail 40
            }

            throw "Spend batch failed for Rayon threads=$t. Stopping; no automatic retry."
        }

        # Parse only completed proof-result lines from the application.
        $runRecords = @()

        foreach ($line in Get-Content -LiteralPath $stdoutLog) {
            if ($line -match 'run=(\d+),\s*prove_ms=([\d.]+),\s*verify_ms=([\d.]+),\s*proof_bytes=(\d+),\s*verified=(true|false)') {
                $runRecords += [PSCustomObject]@{
                    Run       = [int]$Matches[1]
                    ProveMs   = [double]$Matches[2]
                    VerifyMs  = [double]$Matches[3]
                    ProofBytes = [int]$Matches[4]
                    Verified  = $Matches[5]
                }
            }
        }

        if ($runRecords.Count -ne 5) {
            Write-Host "STDOUT log: $stdoutLog"
            Write-Host "STDERR log: $stderrLog"
            throw "Expected 5 proof results for threads=$t; found $($runRecords.Count). Incomplete batch rejected."
        }

        $badRecords = @($runRecords | Where-Object { $_.Verified -ne "true" })

        if ($badRecords.Count -gt 0) {
            throw "At least one proof did not verify for threads=$t. Batch rejected."
        }

        $runRecords = @($runRecords | Sort-Object Run)

        foreach ($record in $runRecords) {
            $row = '{0},{1},{2},{3:F3},{4:F3},{5},{6}' -f `
                "$stamp-$t", $t, $record.Run, `
                $record.ProveMs, $record.VerifyMs, `
                $record.ProofBytes, $record.Verified

            [System.IO.File]::AppendAllText(
                $partialCsv,
                "$row`r`n",
                [System.Text.Encoding]::UTF8
            )

            Write-Host (
                "threads={0} run={1} prove_ms={2:F3} verify_ms={3:F3} verified={4}" -f `
                $t, $record.Run, $record.ProveMs, `
                $record.VerifyMs, $record.Verified
            )
        }

        Write-Host "Batch passed: 5/5 proofs verified."
        Write-Host "STDOUT log: $stdoutLog"
        Write-Host "STDERR log: $stderrLog"
        Write-Host ""
    }

    # Publish the complete CSV only after all six batches pass.
    Move-Item -LiteralPath $partialCsv -Destination $outputCsv -Force
    $completedSuccessfully = $true

    Write-Host "========================================"
    Write-Host "THREAD SCALING CAMPAIGN COMPLETE"
    Write-Host "========================================"
    Write-Host "Thread configurations: $($threadsToTest -join ', ')"
    Write-Host "Expected result rows:  30"
    Write-Host "CSV: $outputCsv"

    Write-Host ""
    Write-Host "Next: verify the CSV contains 30 data rows and all verified=true."
}
finally {
    # Restore the original environment.
    if ($null -eq $oldProfile) {
        Remove-Item Env:SAPLING_PROFILE -ErrorAction SilentlyContinue
    } else {
        $env:SAPLING_PROFILE = $oldProfile
    }

    if ($null -eq $oldThreads) {
        Remove-Item Env:RAYON_NUM_THREADS -ErrorAction SilentlyContinue
    } else {
        $env:RAYON_NUM_THREADS = $oldThreads
    }

    # Restore the formal benchmark CSV exactly as it existed before
    # this campaign. If it did not exist beforehand, remove the file
    # the smoke binary may have created.
    if ($hadFormalCsv) {
        if (Test-Path -LiteralPath $backupCsv) {
            Copy-Item -LiteralPath $backupCsv -Destination $formalCsv -Force
            Remove-Item -LiteralPath $backupCsv -Force
            Write-Host "Original formal CSV restored."
        } else {
            Write-Warning "Formal CSV backup is missing; inspect $formalCsv before proceeding."
        }
    } elseif (Test-Path -LiteralPath $formalCsv) {
        Remove-Item -LiteralPath $formalCsv -Force
        Write-Host "Temporary formal CSV removed."
    }

    if (!$completedSuccessfully -and (Test-Path -LiteralPath $partialCsv)) {
        Write-Warning "The campaign is incomplete. Partial results retained at: $partialCsv"
        Write-Warning "Do not treat that file as a complete thread-scaling dataset."
    }
}