param(
    [string]$RepoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path,
    [switch]$SkipPush
)

$ErrorActionPreference = 'Stop'

function Invoke-GitChecked {
    param(
        [string[]]$GitArgs,
        [string]$FailureMessage = 'Git command failed.'
    )
    $result = @(& git -C $RepoPath @GitArgs 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $details = ($result | ForEach-Object { [string]$_ }) -join "`n"
        throw "$FailureMessage`n$details"
    }
    return $result
}

function Get-LineEndingBytes {
    param([byte[]]$Bytes)
    for ($i = 0; $i -lt $Bytes.Length; $i++) {
        if ($Bytes[$i] -eq 10) {
            if ($i -gt 0 -and $Bytes[$i - 1] -eq 13) {
                return ,([byte[]](13, 10))
            }
            return ,([byte[]](10))
        }
    }
    return ,([byte[]](13, 10))
}

function Remove-TrailingBlankLines {
    param([string]$FullPath)
    $bytes = [System.IO.File]::ReadAllBytes($FullPath)
    if ($bytes.Length -eq 0) { return $false }

    $newline = Get-LineEndingBytes -Bytes $bytes
    $end = $bytes.Length
    while ($end -gt 0 -and ($bytes[$end - 1] -eq 10 -or $bytes[$end - 1] -eq 13)) {
        $end--
    }

    $newLength = $end + $newline.Length
    $output = New-Object byte[] $newLength
    if ($end -gt 0) { [Array]::Copy($bytes, 0, $output, 0, $end) }
    [Array]::Copy($newline, 0, $output, $end, $newline.Length)

    $changed = $output.Length -ne $bytes.Length
    if (-not $changed) {
        for ($i = 0; $i -lt $bytes.Length; $i++) {
            if ($bytes[$i] -ne $output[$i]) { $changed = $true; break }
        }
    }
    if ($changed) { [System.IO.File]::WriteAllBytes($FullPath, $output) }
    return $changed
}

function Add-ClosureNote {
    param([string]$FullPath)
    $oldBytes = [System.IO.File]::ReadAllBytes($FullPath)
    $oldText = [System.Text.Encoding]::UTF8.GetString($oldBytes)
    $marker = '## Pre-commit whitespace normalization'
    if ($oldText.Contains($marker)) { return $false }

    $newline = Get-LineEndingBytes -Bytes $oldBytes
    $end = $oldBytes.Length
    while ($end -gt 0 -and ($oldBytes[$end - 1] -eq 10 -or $oldBytes[$end - 1] -eq 13)) { $end-- }

    $note = @'
## Pre-commit whitespace normalization

Before commit, the whitespace check identified extra blank lines at end-of-file in the parameter sizing report, the RAMMap cold-pilot log, and the parameter-sizing generator script. Only trailing newline bytes were normalized; experiment contents and measured values were not changed. The artifact manifest's byte counts and SHA-256 values were refreshed for the normalized files and this closure document.
'@
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $noteBytes = $utf8.GetBytes($note.Replace("`n", [System.Text.Encoding]::UTF8.GetString($newline)))
    $prefixNewlines = New-Object byte[] ($newline.Length * 2)
    [Array]::Copy($newline, 0, $prefixNewlines, 0, $newline.Length)
    [Array]::Copy($newline, 0, $prefixNewlines, $newline.Length, $newline.Length)

    $combinedLength = $end + $prefixNewlines.Length + $noteBytes.Length + $newline.Length
    $combined = New-Object byte[] $combinedLength
    if ($end -gt 0) { [Array]::Copy($oldBytes, 0, $combined, 0, $end) }
    [Array]::Copy($prefixNewlines, 0, $combined, $end, $prefixNewlines.Length)
    [Array]::Copy($noteBytes, 0, $combined, $end + $prefixNewlines.Length, $noteBytes.Length)
    [Array]::Copy($newline, 0, $combined, $combinedLength - $newline.Length, $newline.Length)
    [System.IO.File]::WriteAllBytes($FullPath, $combined)
    return $true
}

if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
    throw "Repository directory not found: $RepoPath"
}

$branch = ((Invoke-GitChecked -GitArgs @('branch', '--show-current')) -join '').Trim()
$head = ((Invoke-GitChecked -GitArgs @('rev-parse', 'HEAD')) -join '').Trim()
$expectedHead = 'c4f4befaaa73bba750663a8d005f10dd437bda4d'
if ($branch -ne 'main') { throw "Expected branch main, found '$branch'. No commit created." }
if ($head -ne $expectedHead) { throw "HEAD changed since the campaign audit. Expected $expectedHead, found $head. No commit created." }

$summaryRelative = 'experiments/raw/csv/sapling_parameter_size_summary_20261011_142729.csv'
$reportRelative = 'experiments/metadata/sapling_parameter_size_breakdown_20261011_142729.md'
$detailRelative = 'experiments/raw/csv/sapling_parameter_size_breakdown_20261011_142729.csv'
$closureRelative = 'experiments/metadata/sapling_measurement_campaign_closure_20261011.md'
$manifestRelative = 'experiments/metadata/sapling_measurement_artifact_manifest_20261011.csv'
$generatorRelative = 'scripts/record_sapling_parameter_size_breakdown.ps1'
$pilotLogRelative = 'experiments/raw/logs/rammap_spend_cold_pilot_20261011_105153.log'
$commitHelperRelative = 'scripts/commit_sapling_measurement_campaign.ps1'
$summaryPath = Join-Path $RepoPath ($summaryRelative.Replace('/', '\'))
$reportPath = Join-Path $RepoPath ($reportRelative.Replace('/', '\'))
$detailPath = Join-Path $RepoPath ($detailRelative.Replace('/', '\'))
$closurePath = Join-Path $RepoPath ($closureRelative.Replace('/', '\'))
$manifestPath = Join-Path $RepoPath ($manifestRelative.Replace('/', '\'))
$generatorPath = Join-Path $RepoPath ($generatorRelative.Replace('/', '\'))
$pilotLogPath = Join-Path $RepoPath ($pilotLogRelative.Replace('/', '\'))
$commitHelperPath = Join-Path $RepoPath ($commitHelperRelative.Replace('/', '\'))

foreach ($required in @($summaryPath, $reportPath, $detailPath, $closurePath, $manifestPath, $generatorPath, $pilotLogPath, $commitHelperPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required audit artifact missing: $required. No commit created."
    }
}

$summaryRows = @(Import-Csv -LiteralPath $summaryPath)
if ($summaryRows.Count -ne 2) { throw "Expected two parameter summary rows, found $($summaryRows.Count)." }
$spend = $summaryRows | Where-Object { $_.Circuit -eq 'Spend' } | Select-Object -First 1
$output = $summaryRows | Where-Object { $_.Circuit -eq 'Output' } | Select-Object -First 1
if ($null -eq $spend -or $null -eq $output) { throw 'Spend/Output summary rows are missing.' }
if ([long]$spend.VerifyingKeySerializedBytes -ne 1636 -or [long]$output.VerifyingKeySerializedBytes -ne 1444) { throw 'VK size validation failed.' }
if ($spend.ParserReachedExactEOF -ne 'True' -or $output.ParserReachedExactEOF -ne 'True') { throw 'Exact EOF validation failed.' }

$report = [System.IO.File]::ReadAllText($reportPath)
foreach ($placeholder in @('$SpendParamsPath', '$OutputParamsPath', '$G1Bytes', '$G2Bytes')) {
    if ($report.Contains($placeholder)) { throw "Unexpanded placeholder found in parameter report: $placeholder" }
}

$manifestRows = @(Import-Csv -LiteralPath $manifestPath)
if ($manifestRows.Count -ne 47) { throw "Expected 47 manifest entries excluding the manifest itself; found $($manifestRows.Count). No commit created." }

# Validate hashes as generated before doing any whitespace-only normalization.
$hashFailures = [System.Collections.Generic.List[string]]::new()
foreach ($row in $manifestRows) {
    $relative = ([string]$row.RelativePath).Replace('/', '\')
    $fullPath = Join-Path $RepoPath $relative
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        $hashFailures.Add("MISSING: $($row.RelativePath)")
        continue
    }
    $actualHash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne ([string]$row.SHA256).ToLowerInvariant()) { $hashFailures.Add("HASH MISMATCH: $($row.RelativePath)") }
}
if ($hashFailures.Count -gt 0) { throw "Manifest validation failed before cleanup:`n$($hashFailures -join "`n")`nNo commit created." }

# If the previous attempt left the exact audited file set staged, safely unstage it.
# Refuse to reset the index if staged paths are not exactly the audited set.
$expectedPathsBefore = [System.Collections.Generic.List[string]]::new()
foreach ($row in $manifestRows) { $expectedPathsBefore.Add(([string]$row.RelativePath).Replace('\', '/')) }
$expectedPathsBefore.Add($manifestRelative)
$expectedPathsBefore.Add($commitHelperRelative)
$expectedBeforeSorted = @($expectedPathsBefore | Sort-Object -Unique)
$stagedNow = @(& git -C $RepoPath diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the Git index. No commit created.' }
$stagedNowSorted = @($stagedNow | ForEach-Object { ([string]$_).Replace('\', '/') } | Sort-Object -Unique)
if ($stagedNowSorted.Count -gt 0) {
    $extraStaged = @($stagedNowSorted | Where-Object { $_ -notin $expectedBeforeSorted })
    $missingStaged = @($expectedBeforeSorted | Where-Object { $_ -notin $stagedNowSorted })
    if ($extraStaged.Count -gt 0 -or $missingStaged.Count -gt 0) {
        throw "Git index contains paths other than the audited batch. Nothing reset.`nExtra: $($extraStaged -join ', ')`nMissing: $($missingStaged -join ', ')"
    }
    $unstagedPaths = @(& git -C $RepoPath diff --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect unstaged changes before safely resetting the index.' }
    $unexpectedUnstaged = @($unstagedPaths | ForEach-Object { ([string]$_).Replace('\', '/') } | Where-Object { $_ -ne $commitHelperRelative })
    if ($unexpectedUnstaged.Count -gt 0) {
        throw "Unexpected unstaged changes detected; index was not reset: $($unexpectedUnstaged -join ', ')"
    }
    $resetOutput = @(& git -C $RepoPath reset --mixed HEAD 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Could not unstage previous attempt safely:`n$(($resetOutput | ForEach-Object { [string]$_ }) -join "`n")" }
    Write-Host 'PREVIOUS_STAGE=EXPECTED_BATCH_UNSTAGED_SAFELY'
} else {
    Write-Host 'PREVIOUS_STAGE=NONE'
}

# Normalize only the three files explicitly reported by git diff --check.
$normalizedPaths = [System.Collections.Generic.List[string]]::new()
foreach ($rel in @($reportRelative, $pilotLogRelative, $generatorRelative)) {
    $full = Join-Path $RepoPath ($rel.Replace('/', '\'))
    if (Remove-TrailingBlankLines -FullPath $full) { $normalizedPaths.Add($rel) }
}

# Record the cleanup in the closure so the post-normalization manifest state is explicit.
[void](Add-ClosureNote -FullPath $closurePath)

# Refresh byte counts and hashes for every manifest row from the final working-tree content.
foreach ($row in $manifestRows) {
    $full = Join-Path $RepoPath (([string]$row.RelativePath).Replace('/', '\'))
    $info = Get-Item -LiteralPath $full
    $row.Bytes = [long]$info.Length
    $row.SHA256 = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifestRows | Sort-Object RelativePath | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8

# Verify all refreshed hashes from disk after writing the manifest.
$postHashFailures = [System.Collections.Generic.List[string]]::new()
$manifestRows = @(Import-Csv -LiteralPath $manifestPath)
foreach ($row in $manifestRows) {
    $full = Join-Path $RepoPath (([string]$row.RelativePath).Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        $postHashFailures.Add("MISSING: $($row.RelativePath)")
        continue
    }
    $info = Get-Item -LiteralPath $full
    $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne ([string]$row.SHA256).ToLowerInvariant() -or [long]$info.Length -ne [long]$row.Bytes) {
        $postHashFailures.Add("HASH/SIZE MISMATCH: $($row.RelativePath)")
    }
}
if ($postHashFailures.Count -gt 0) { throw "Refreshed manifest validation failed:`n$($postHashFailures -join "`n")`nNo commit created." }

# Ensure the tree still consists only of the manifest-listed artifacts, the manifest itself,
# and this explicitly allowlisted operational helper.
$currentStatus = @(& git -C $RepoPath status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect working-tree status.' }
$currentPaths = [System.Collections.Generic.List[string]]::new()
foreach ($statusLineObject in $currentStatus) {
    $statusLine = [string]$statusLineObject
    if ($statusLine.Length -lt 4) { continue }
    $pathPart = $statusLine.Substring(3).Trim()
    if ($pathPart.StartsWith('"') -and $pathPart.EndsWith('"')) { $pathPart = $pathPart.Trim('"') }
    $currentPaths.Add($pathPart.Replace('\', '/'))
}
$expectedPaths = [System.Collections.Generic.List[string]]::new()
foreach ($row in $manifestRows) { $expectedPaths.Add(([string]$row.RelativePath).Replace('\', '/')) }
$expectedPaths.Add($manifestRelative)
$expectedPaths.Add($commitHelperRelative)
$currentSorted = @($currentPaths | Sort-Object -Unique)
$expectedSorted = @($expectedPaths | Sort-Object -Unique)
$missingFromStatus = @($expectedSorted | Where-Object { $_ -notin $currentSorted })
$unexpectedStatus = @($currentSorted | Where-Object { $_ -notin $expectedSorted })
if ($missingFromStatus.Count -gt 0 -or $unexpectedStatus.Count -gt 0) {
    throw "Working tree differs from audited manifest after cleanup.`nMissing: $($missingFromStatus -join ', ')`nUnexpected: $($unexpectedStatus -join ', ')`nNo commit created."
}

$diffCheck = @(& git -C $RepoPath diff --check 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check still failed before staging. No commit created.`n$(($diffCheck | ForEach-Object { [string]$_ }) -join "`n")"
}

$stagePaths = @($expectedSorted)
$addOutput = @(& git -C $RepoPath add -- $stagePaths 2>&1)
if ($LASTEXITCODE -ne 0) { throw "git add failed:`n$(($addOutput | ForEach-Object { [string]$_ }) -join "`n")" }

$cachedCheck = @(& git -C $RepoPath diff --cached --check 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Staged diff check failed. Files remain staged for inspection; no commit was created.`n$(($cachedCheck | ForEach-Object { [string]$_ }) -join "`n")"
}
$stagedPaths = @(& git -C $RepoPath diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw 'Could not list staged paths.' }
if ($stagedPaths.Count -ne $expectedSorted.Count) { throw "Expected $($expectedSorted.Count) staged files, found $($stagedPaths.Count). Files remain staged; no commit created." }

Write-Host ''
Write-Host '================ PRE-COMMIT AUDIT ================'
Write-Host "BRANCH=$branch"
Write-Host "PARENT_HEAD=$head"
Write-Host "MANIFEST_ROWS=$($manifestRows.Count)"
Write-Host "STAGED_FILES=$($stagedPaths.Count)"
Write-Host "NORMALIZED_FILES=$($normalizedPaths.Count)"
foreach ($normalized in $normalizedPaths) { Write-Host "NORMALIZED=$normalized" }
Write-Host "VK_SPEND_BYTES=$($spend.VerifyingKeySerializedBytes)"
Write-Host "VK_OUTPUT_BYTES=$($output.VerifyingKeySerializedBytes)"
Write-Host 'MANIFEST_HASH_CHECK=PASS'
Write-Host 'PARAMETER_METADATA_PLACEHOLDERS=NONE'
Write-Host 'DIFF_CHECK=PASS'
Write-Host ''
Write-Host '--- Staged diff summary ---'
& git -C $RepoPath diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw 'Could not print staged diff summary.' }
Write-Host ''
Write-Host '--- Staged status ---'
& git -C $RepoPath status --short
if ($LASTEXITCODE -ne 0) { throw 'Could not print staged status.' }

$commitMessage = 'exp: archive Sapling measurement campaign results'
$commitOutput = @(& git -C $RepoPath commit -m $commitMessage 2>&1)
if ($LASTEXITCODE -ne 0) { throw "Commit failed. Files remain staged for inspection.`n$(($commitOutput | ForEach-Object { [string]$_ }) -join "`n")" }
$commitOutput | ForEach-Object { Write-Host $_ }
$newHead = ((Invoke-GitChecked -GitArgs @('rev-parse', 'HEAD')) -join '').Trim()
Write-Host "COMMIT=$newHead"
Write-Host "COMMIT_MESSAGE=$commitMessage"

if ($SkipPush) {
    Write-Host 'PUSH_STATUS=SKIPPED_BY_SWITCH'
} else {
    $pushOutput = @(& git -C $RepoPath push origin main 2>&1)
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'PUSH_STATUS=FAILED'
        $pushOutput | ForEach-Object { Write-Host $_ }
        Write-Warning "Commit $newHead exists locally. Push did not complete; inspect the message above and retry 'git push origin main' if appropriate."
    } else {
        Write-Host 'PUSH_STATUS=SUCCESS'
        $pushOutput | ForEach-Object { Write-Host $_ }
        $remoteLine = @(& git -C $RepoPath ls-remote origin refs/heads/main 2>&1)
        if ($LASTEXITCODE -eq 0 -and $remoteLine.Count -gt 0) {
            $remoteHead = ([string]$remoteLine[0]).Split("`t")[0]
            Write-Host "REMOTE_MAIN=$remoteHead"
            Write-Host "REMOTE_MATCHES_LOCAL=$($remoteHead -eq $newHead)"
        } else {
            Write-Host 'REMOTE_VERIFY_STATUS=UNAVAILABLE'
        }
    }
}

Write-Host ''
Write-Host '================ FINAL GIT STATUS ================'
& git -C $RepoPath status --short --branch
if ($LASTEXITCODE -ne 0) { throw 'Could not print final Git status.' }
