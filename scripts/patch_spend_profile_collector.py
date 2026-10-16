from pathlib import Path

ROOT = Path.cwd()
RUNNER = ROOT / "scripts" / "run_spend_combined_profile.ps1"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one insertion point for {label}; found {count}. "
            "No file was written. Check whether the runner has already been modified."
        )
    return source.replace(old, new, 1)


def main() -> None:
    if not RUNNER.is_file():
        raise FileNotFoundError(f"Runner not found: {RUNNER}")

    source = RUNNER.read_text(encoding="utf-8-sig")
    if "BELLMAN_MSM_STAGE_PROFILE" in source:
        raise RuntimeError(
            "The combined profile collector already contains MSM inner-stage support. "
            "Refusing to patch twice."
        )

    updated = source

    old = r"$stageRegex = [regex]'G16_STAGE_PROFILE circuit_synthesis_constraints_ms=([\d.]+) worker_vk_setup_ms=([\d.]+) qap_fft_h_exponent_prep_ms=([\d.]+) h_query_access_dispatch_ms=([\d.]+) assignment_query_prep_dispatch_ms=([\d.]+) proof_scalar_terms_ms=([\d.]+) wait_and_assembly_ms=([\d.]+) create_proof_body_ms=([\d.]+)'"
    new = old + "\n" + r"$innerStageRegex = [regex]'BELLMAN_MSM_STAGE_PROFILE call_id=(\d+) exponent_count=(\d+) window=(\d+) bucket_count=(\d+) chunk_count=(\d+) bucket_element_size_bytes=(\d+) exponent_chunk_prep_ms=([\d.]+) chunk_parallel_wall_ms=([\d.]+) bucket_init_sum_ms=([\d.]+) bucket_init_max_ms=([\d.]+) bucket_fill_sum_ms=([\d.]+) bucket_fill_max_ms=([\d.]+) bucket_reduce_sum_ms=([\d.]+) bucket_reduce_max_ms=([\d.]+) max_concurrent_chunk_regions=(\d+) bucket_payload_at_max_concurrency_estimate_bytes=(\d+) result_merge_ms=([\d.]+)'"
    updated = replace_once(updated, old, new, "inner-stage regex")

    old = "$stageMatches = $stageRegex.Matches($stderr)"
    new = old + "\n$innerStageMatches = $innerStageRegex.Matches($stderr)"
    updated = replace_once(updated, old, new, "inner-stage regex matching")

    old = '''if ($stageMatches.Count -ne 5) {
    throw "Expected 5 G16_STAGE_PROFILE records; found $($stageMatches.Count). Preserve logs and do not publish partial profile data."
}
'''
    new = old + '''
if ($innerStageMatches.Count -ne 40) {
    throw "Expected 40 BELLMAN_MSM_STAGE_PROFILE records; found $($innerStageMatches.Count). Preserve logs and do not publish partial profile data."
}
'''
    updated = replace_once(updated, old, new, "inner-stage record count validation")

    parse_block = r'''$innerStageObjects = @()
$seenInnerStageCalls = @{}

foreach ($m in $innerStageMatches) {
    $callId = [int]$m.Groups[1].Value

    if ($callId -lt 1 -or $callId -gt 40) {
        throw "Inner-stage call ID $callId is outside expected range 1..40."
    }
    if ($seenInnerStageCalls.ContainsKey($callId)) {
        throw "Duplicate inner-stage call ID: $callId"
    }
    $seenInnerStageCalls[$callId] = $true

    $run = [int][Math]::Floor(($callId - 1) / 8) + 1
    $query = $queries[($callId - 1) % 8]

    $exponentCount = [int]$m.Groups[2].Value
    $window = [int]$m.Groups[3].Value
    $bucketCount = [int]$m.Groups[4].Value
    $chunkCount = [int]$m.Groups[5].Value
    $elementSize = [int]$m.Groups[6].Value
    $expectedWindow = if ($query.Count -lt 32) { 3 } else { 12 }
    $expectedBucketCount = [int]([Math]::Pow(2, $expectedWindow) - 1)
    $expectedChunkCount = [int][Math]::Ceiling(255.0 / $expectedWindow)
    $expectedElementSize = if ($query.Group -eq 'G1') { 144 } else { 288 }
    $maxConcurrent = [int]$m.Groups[15].Value
    $bucketPayloadEstimate = [long]$m.Groups[16].Value
    $expectedBucketPayloadEstimate = [long]$maxConcurrent * $bucketCount * $elementSize

    if ($exponentCount -ne [int]$query.Count) {
        throw "Inner-stage call $callId ($($query.Name)) exponent_count mismatch: $exponentCount."
    }
    if ($window -ne $expectedWindow -or $bucketCount -ne $expectedBucketCount) {
        throw "Inner-stage call $callId ($($query.Name)) has unexpected window/bucket count."
    }
    if ($chunkCount -ne $expectedChunkCount) {
        throw "Inner-stage call $callId ($($query.Name)) chunk_count mismatch: $chunkCount; expected $expectedChunkCount."
    }
    if ($elementSize -ne $expectedElementSize) {
        throw "Inner-stage call $callId ($($query.Name)) element size mismatch: $elementSize; expected $expectedElementSize."
    }
    if ($maxConcurrent -lt 1 -or $maxConcurrent -gt $chunkCount) {
        throw "Inner-stage call $callId ($($query.Name)) reports invalid concurrent chunk count: $maxConcurrent."
    }
    if ($bucketPayloadEstimate -ne $expectedBucketPayloadEstimate) {
        throw "Inner-stage call $callId ($($query.Name)) bucket payload estimate mismatch."
    }

    $innerStageObjects += [PSCustomObject]@{
        batch_id = $batchId
        run = $run
        call_id = $callId
        query = $query.Name
        group = $query.Group
        exponent_count = $exponentCount
        window = $window
        bucket_count = $bucketCount
        chunk_count = $chunkCount
        bucket_element_size_bytes = $elementSize
        exponent_chunk_prep_ms = [double]$m.Groups[7].Value
        chunk_parallel_wall_ms = [double]$m.Groups[8].Value
        bucket_init_sum_ms = [double]$m.Groups[9].Value
        bucket_init_max_ms = [double]$m.Groups[10].Value
        bucket_fill_sum_ms = [double]$m.Groups[11].Value
        bucket_fill_max_ms = [double]$m.Groups[12].Value
        bucket_reduce_sum_ms = [double]$m.Groups[13].Value
        bucket_reduce_max_ms = [double]$m.Groups[14].Value
        max_concurrent_chunk_regions = $maxConcurrent
        bucket_payload_at_max_concurrency_estimate_bytes = $bucketPayloadEstimate
        result_merge_ms = [double]$m.Groups[17].Value
        threads = $Threads
        build_profile = 'release'
    }
}

if ($seenInnerStageCalls.Count -ne 40) {
    throw "Expected 40 unique inner-stage call IDs; found $($seenInnerStageCalls.Count)."
}

$innerStageSummaryObjects = @()
foreach ($query in $queries) {
    $queryRows = @(
        $innerStageObjects |
        Where-Object { $_.query -eq $query.Name } |
        Sort-Object run
    )
    if ($queryRows.Count -ne 5) {
        throw "Expected five inner-stage records for $($query.Name); found $($queryRows.Count)."
    }

    $prep = @($queryRows | ForEach-Object { [double]$_.exponent_chunk_prep_ms })
    $wall = @($queryRows | ForEach-Object { [double]$_.chunk_parallel_wall_ms })
    $init = @($queryRows | ForEach-Object { [double]$_.bucket_init_sum_ms })
    $fill = @($queryRows | ForEach-Object { [double]$_.bucket_fill_sum_ms })
    $reduce = @($queryRows | ForEach-Object { [double]$_.bucket_reduce_sum_ms })
    $merge = @($queryRows | ForEach-Object { [double]$_.result_merge_ms })
    $concurrent = @($queryRows | ForEach-Object { [double]$_.max_concurrent_chunk_regions })
    $bucketEstimate = @($queryRows | ForEach-Object { [double]$_.bucket_payload_at_max_concurrency_estimate_bytes })

    $innerStageSummaryObjects += [PSCustomObject]@{
        batch_id = $batchId
        query = $query.Name
        group = $query.Group
        exponent_count = $query.Count
        window = [int]$queryRows[0].window
        bucket_count = [int]$queryRows[0].bucket_count
        chunk_count = [int]$queryRows[0].chunk_count
        bucket_element_size_bytes = [int]$queryRows[0].bucket_element_size_bytes
        runs = $queryRows.Count
        median_exponent_chunk_prep_ms = Get-Median -Values $prep
        median_chunk_parallel_wall_ms = Get-Median -Values $wall
        median_bucket_init_sum_ms = Get-Median -Values $init
        median_bucket_fill_sum_ms = Get-Median -Values $fill
        median_bucket_reduce_sum_ms = Get-Median -Values $reduce
        median_result_merge_ms = Get-Median -Values $merge
        median_max_concurrent_chunk_regions = Get-Median -Values $concurrent
        max_concurrent_chunk_regions_observed = [int](($queryRows | Measure-Object -Property max_concurrent_chunk_regions -Maximum).Maximum)
        median_bucket_payload_estimate_bytes = Get-Median -Values $bucketEstimate
        max_bucket_payload_estimate_bytes = [long](($queryRows | Measure-Object -Property bucket_payload_at_max_concurrency_estimate_bytes -Maximum).Maximum)
        note = 'Stage sums aggregate chunk timings; chunk_parallel_wall_ms is wall time. Payload estimate is not measured process peak memory.'
    }
}

'''
    updated = replace_once(updated, "$stageFieldNames = @(\n", parse_block + "$stageFieldNames = @(\n", "inner-stage parse and validation block")

    old = '''$stageCsv = Join-Path $rawDir "sapling_spend_stage_profile_$batchId.csv"
$msmCsv = Join-Path $rawDir "sapling_spend_msm_call_profile_$batchId.csv"
$summaryCsv = Join-Path $rawDir "sapling_spend_profile_run_summary_$batchId.csv"
$metadataPath = Join-Path $metadataDir "sapling_spend_combined_profile_$batchId.md"
'''
    new = old + '''$innerStageCsv = Join-Path $rawDir "sapling_spend_msm_inner_stage_profile_$batchId.csv"
$innerStageSummaryCsv = Join-Path $rawDir "sapling_spend_msm_inner_stage_summary_$batchId.csv"
'''
    updated = replace_once(updated, old, new, "inner-stage output paths")

    old = '''if (
    (Test-Path $stageCsv) -or
    (Test-Path $msmCsv) -or
    (Test-Path $summaryCsv) -or
    (Test-Path $metadataPath)
) {
'''
    new = '''if (
    (Test-Path $stageCsv) -or
    (Test-Path $msmCsv) -or
    (Test-Path $summaryCsv) -or
    (Test-Path $innerStageCsv) -or
    (Test-Path $innerStageSummaryCsv) -or
    (Test-Path $metadataPath)
) {
'''
    updated = replace_once(updated, old, new, "inner-stage output collision guard")

    old = "$perRun | Export-Csv -LiteralPath $summaryCsv -NoTypeInformation -Encoding UTF8\n"
    new = old + '''$innerStageObjects | Export-Csv -LiteralPath $innerStageCsv -NoTypeInformation -Encoding UTF8
$innerStageSummaryObjects | Export-Csv -LiteralPath $innerStageSummaryCsv -NoTypeInformation -Encoding UTF8
'''
    updated = replace_once(updated, old, new, "inner-stage CSV export")

    old = '''$msmElapsedMedian = Get-Median -Values @(
    $msmObjects | ForEach-Object { [double]$_.elapsed_ms }
)
'''
    new = old + '''
$maxConcurrentChunkRegions = [int](
    ($innerStageObjects | Measure-Object -Property max_concurrent_chunk_regions -Maximum).Maximum
)
$maxBucketPayloadEstimateBytes = [long](
    ($innerStageObjects | Measure-Object -Property bucket_payload_at_max_concurrency_estimate_bytes -Maximum).Maximum
)
'''
    updated = replace_once(updated, old, new, "inner-stage report summary metrics")

    old = '''- submit_elapsed_ms median across MSM calls (ms): $([Math]::Round($submitMedian, 3))

The three MSM timing fields describe different measurement intervals.'''
    new = '''- submit_elapsed_ms median across MSM calls (ms): $([Math]::Round($submitMedian, 3))
- MSM inner-stage records: $($innerStageObjects.Count) / 40
- Per-query MSM inner-stage summary rows: $($innerStageSummaryObjects.Count) / 8
- Maximum observed concurrent chunk regions within one MSM call: $maxConcurrentChunkRegions
- Maximum estimated bucket payload for observed concurrency (bytes): $maxBucketPayloadEstimateBytes

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals.'''
    updated = replace_once(updated, old, new, "inner-stage summary in Markdown report")

    old = '''- Per-run ratio summary CSV SHA-256: $(Get-Sha256 $summaryCsv)
- Prover stdout: experiments/raw/logs/$(Split-Path $stdoutPath -Leaf)'''
    new = '''- Per-run ratio summary CSV SHA-256: $(Get-Sha256 $summaryCsv)
- MSM inner-stage CSV: experiments/raw/csv/$(Split-Path $innerStageCsv -Leaf)
- MSM inner-stage CSV SHA-256: $(Get-Sha256 $innerStageCsv)
- MSM inner-stage per-query summary CSV: experiments/raw/csv/$(Split-Path $innerStageSummaryCsv -Leaf)
- MSM inner-stage per-query summary CSV SHA-256: $(Get-Sha256 $innerStageSummaryCsv)
- Prover stdout: experiments/raw/logs/$(Split-Path $stdoutPath -Leaf)'''
    updated = replace_once(updated, old, new, "inner-stage CSV artifacts in report")

    old = '''- Stage timing records: $($stageObjects.Count) / 5
- Proof verification: 5/5 passed'''
    new = '''- Stage timing records: $($stageObjects.Count) / 5
- MSM inner-stage records: $($innerStageObjects.Count) / 40
- MSM inner-stage query summary rows: $($innerStageSummaryObjects.Count) / 8
- Proof verification: 5/5 passed'''
    updated = replace_once(updated, old, new, "inner-stage validation report")

    old = '''Write-Host "Per-run summary: $summaryCsv"
Write-Host "Metadata report: $metadataPath"'''
    new = '''Write-Host "Per-run summary: $summaryCsv"
Write-Host "MSM inner-stage CSV: $innerStageCsv"
Write-Host "MSM inner-stage query summary: $innerStageSummaryCsv"
Write-Host "Metadata report: $metadataPath"'''
    updated = replace_once(updated, old, new, "inner-stage output paths in console")

    RUNNER.write_text(updated, encoding="utf-8", newline="\n")
    print("Combined profile collector updated successfully.")
    print(f"Modified: {RUNNER}")
    print("Added: 40-record validation, 40-row inner-stage CSV, 8-row per-query summary CSV.")
    print("No build or proof benchmark was run by this script.")
    print("Next: review git diff, run PowerShell syntax checks if available, then run cargo check.")


if __name__ == "__main__":
    main()
