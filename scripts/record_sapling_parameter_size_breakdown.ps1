param(
    [string]$RepoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path,
    [string]$SpendParamsPath = '',
    [string]$OutputParamsPath = ''
)

$ErrorActionPreference = 'Stop'

$RepoPath = (Resolve-Path -LiteralPath $RepoPath).Path

$parameterDirectory = if (
    -not [string]::IsNullOrWhiteSpace($env:ZCASH_PARAMS_DIR)
) {
    $env:ZCASH_PARAMS_DIR
}
else {
    'D:\Research\zcash-params'
}

if ([string]::IsNullOrWhiteSpace($SpendParamsPath)) {
    $SpendParamsPath = Join-Path $parameterDirectory 'sapling-spend.params'
}

if ([string]::IsNullOrWhiteSpace($OutputParamsPath)) {
    $OutputParamsPath = Join-Path $parameterDirectory 'sapling-output.params'
}

# Records the serialization layout of the two Sapling MPC parameter files.
# Reads parameter files only; does not modify them or run proof-generation code.
# Assumptions from the pinned BLS12-381 serialization format:
#   G1 uncompressed point = 96 bytes
#   G2 uncompressed point = 192 bytes
# MPC trailer (phase2 MPCParameters::write):
#   64-byte circuit hash + 4-byte big-endian contributor count
#   + contributor records (3*G1 + 1*G2 + 64-byte transcript).

$G1Bytes = 96L
$G2Bytes = 192L
$VkFixedBytes = 3L * $G1Bytes + 3L * $G2Bytes
$MpcTranscriptBytes = 64L
$MpcRecordBytes = 3L * $G1Bytes + $G2Bytes + $MpcTranscriptBytes
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$DateStamp = Get-Date -Format 'yyyyMMdd'

if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
    throw "Repo path not found: $RepoPath"
}
foreach ($path in @($SpendParamsPath, $OutputParamsPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Parameter file not found: $path"
    }
}

$MetadataDir = Join-Path $RepoPath 'experiments\metadata'
$RawCsvDir = Join-Path $RepoPath 'experiments\raw\csv'
New-Item -ItemType Directory -Force -Path $MetadataDir, $RawCsvDir | Out-Null

function Invoke-GitText {
    param([string[]]$GitArgs)
    $value = & git -C $RepoPath @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed: $($value -join ' ')"
    }
    return (($value | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Read-U32BE {
    param([System.IO.BinaryReader]$Reader)
    $b = $Reader.ReadBytes(4)
    if ($b.Length -ne 4) { throw "Length field was shorter than 4 bytes." }
    return ([long]$b[0] * 16777216L + [long]$b[1] * 65536L + [long]$b[2] * 256L + [long]$b[3])
}

function Skip-Bytes {
    param([System.IO.BinaryReader]$Reader, [long]$Count)
    $s = $Reader.BaseStream
    if ($Count -lt 0 -or ($s.Position + $Count) -gt $s.Length) {
        throw "Offset out of bounds: position=$($s.Position), skip=$Count, file_length=$($s.Length)"
    }
    [void]$s.Seek($Count, [System.IO.SeekOrigin]::Current)
}

function New-SectionRow {
    param(
        [string]$Circuit,
        [string]$Section,
        [long]$Count,
        [long]$StartOffset,
        [long]$EndOffset,
        [long]$LengthFieldBytes,
        [string]$PointEncodingBytes,
        [long]$PayloadBytes,
        [string]$Notes
    )
    [PSCustomObject]@{
        Circuit             = $Circuit
        Section             = $Section
        ElementCount        = $Count
        StartOffset         = $StartOffset
        EndOffset           = $EndOffset
        LengthFieldBytes    = $LengthFieldBytes
        PointEncodingBytes  = $PointEncodingBytes
        PayloadBytes        = $PayloadBytes
        EncodedBytes        = $EndOffset - $StartOffset
        Notes               = $Notes
    }
}

function Inspect-ParameterFile {
    param(
        [string]$Circuit,
        [string]$Path,
        [long]$ExpectedIcCount
    )

    $fileInfo = Get-Item -LiteralPath $Path
    $fileHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    $rows = [System.Collections.Generic.List[object]]::new()
    $stream = $null
    $reader = $null

    try {
        $stream = [System.IO.File]::OpenRead($Path)
        $reader = [System.IO.BinaryReader]::new($stream)
        $fileBytes = [long]$stream.Length

        # VK fixed points: alpha_g1, beta_g1, beta_g2, gamma_g2, delta_g1, delta_g2.
        $start = $stream.Position
        Skip-Bytes -Reader $reader -Count $VkFixedBytes
        $rows.Add((New-SectionRow -Circuit $Circuit -Section 'VK_FIXED_POINTS' -Count 6 -StartOffset $start -EndOffset $stream.Position -LengthFieldBytes 0 -PointEncodingBytes 'mixed: 3xG1(96), 3xG2(192)' -PayloadBytes $VkFixedBytes -Notes 'Six fixed verifying-key points'))

        # VK IC vector.
        $icLengthOffset = $stream.Position
        $icCount = Read-U32BE -Reader $reader
        if ($icCount -ne $ExpectedIcCount) {
            throw "Unexpected VK IC count: got $icCount, expected $ExpectedIcCount"
        }
        $icPayloadBytes = [long]$icCount * $G1Bytes
        Skip-Bytes -Reader $reader -Count $icPayloadBytes
        $rows.Add((New-SectionRow -Circuit $Circuit -Section 'VK_IC' -Count $icCount -StartOffset $icLengthOffset -EndOffset $stream.Position -LengthFieldBytes 4 -PointEncodingBytes '96' -PayloadBytes $icPayloadBytes -Notes 'Includes 4-byte big-endian length prefix'))
        $vkBytes = [long]$stream.Position

        # Five query vectors in bellman Parameters::write order.
        $vectors = @(
            [PSCustomObject]@{ Name = 'H_G1'; PointBytes = $G1Bytes },
            [PSCustomObject]@{ Name = 'L_G1'; PointBytes = $G1Bytes },
            [PSCustomObject]@{ Name = 'A_G1'; PointBytes = $G1Bytes },
            [PSCustomObject]@{ Name = 'B_G1'; PointBytes = $G1Bytes },
            [PSCustomObject]@{ Name = 'B_G2'; PointBytes = $G2Bytes }
        )
        $queryCounts = @{}
        foreach ($vector in $vectors) {
            $vectorStart = $stream.Position
            $count = Read-U32BE -Reader $reader
            $payload = [long]$count * [long]$vector.PointBytes
            Skip-Bytes -Reader $reader -Count $payload
            $queryCounts[$vector.Name] = [long]$count
            $rows.Add((New-SectionRow -Circuit $Circuit -Section $vector.Name -Count $count -StartOffset $vectorStart -EndOffset $stream.Position -LengthFieldBytes 4 -PointEncodingBytes ([string]$vector.PointBytes) -PayloadBytes $payload -Notes 'Includes 4-byte big-endian length prefix'))
        }
        $groth16BodyBytes = [long]$stream.Position
        $queryVectorsBytes = $groth16BodyBytes - $vkBytes

        # MPC trailer: circuit hash, contributor count, then fixed-size contribution records.
        $trailerStart = $stream.Position
        $hashBytes = $reader.ReadBytes([int]$MpcTranscriptBytes)
        if ($hashBytes.Length -ne $MpcTranscriptBytes) { throw 'MPC circuit-hash trailer is truncated.' }
        $rows.Add((New-SectionRow -Circuit $Circuit -Section 'MPC_CIRCUIT_HASH' -Count 1 -StartOffset $trailerStart -EndOffset $stream.Position -LengthFieldBytes 0 -PointEncodingBytes '' -PayloadBytes $MpcTranscriptBytes -Notes '64-byte circuit hash following Groth16 Parameters body'))

        $countOffset = $stream.Position
        $contributorCount = Read-U32BE -Reader $reader
        $rows.Add((New-SectionRow -Circuit $Circuit -Section 'MPC_CONTRIBUTOR_COUNT' -Count $contributorCount -StartOffset $countOffset -EndOffset $stream.Position -LengthFieldBytes 4 -PointEncodingBytes '' -PayloadBytes 0 -Notes '4-byte big-endian number of contribution records'))

        $recordsStart = $stream.Position
        $recordsPayloadBytes = [long]$contributorCount * $MpcRecordBytes
        Skip-Bytes -Reader $reader -Count $recordsPayloadBytes
        $rows.Add((New-SectionRow -Circuit $Circuit -Section 'MPC_CONTRIBUTION_RECORDS' -Count $contributorCount -StartOffset $recordsStart -EndOffset $stream.Position -LengthFieldBytes 0 -PointEncodingBytes ([string]$MpcRecordBytes) -PayloadBytes $recordsPayloadBytes -Notes 'Each record: 3xG1(96) + 1xG2(192) + 64-byte transcript'))

        if ($stream.Position -ne $stream.Length) {
            throw "Parser did not reach exact EOF: parsed=$($stream.Position), file=$($stream.Length), remaining=$($stream.Length - $stream.Position)"
        }

        $trailerBytes = $fileBytes - $groth16BodyBytes
        $summary = [PSCustomObject]@{
            Circuit                         = $Circuit
            ParameterFilePath               = $Path
            ParameterFileBytes               = $fileBytes
            ParameterFileMiB                 = [math]::Round($fileBytes / 1MB, 6)
            ParameterFileSHA256              = $fileHash
            Groth16ParametersBodyBytes       = $groth16BodyBytes
            Groth16ParametersBodyMiB         = [math]::Round($groth16BodyBytes / 1MB, 6)
            VerifyingKeySerializedBytes      = $vkBytes
            VerifyingKeySerializedMiB        = [math]::Round($vkBytes / 1MB, 6)
            QueryVectorsSerializedBytes      = $queryVectorsBytes
            MpcTrailerBytes                  = $trailerBytes
            MpcCircuitHashBytes               = $MpcTranscriptBytes
            MpcContributorCount               = $contributorCount
            MpcContributionRecordBytes        = $MpcRecordBytes
            MpcContributionRecordsTotalBytes  = $recordsPayloadBytes
            IcCount                           = $icCount
            H_G1_Count                        = $queryCounts['H_G1']
            L_G1_Count                        = $queryCounts['L_G1']
            A_G1_Count                        = $queryCounts['A_G1']
            B_G1_Count                        = $queryCounts['B_G1']
            B_G2_Count                        = $queryCounts['B_G2']
            ParserReachedExactEOF              = $true
        }

        [PSCustomObject]@{
            Summary = $summary
            Rows = @($rows.ToArray())
        }
    }
    finally {
        if ($null -ne $reader) { $reader.Dispose() }
        elseif ($null -ne $stream) { $stream.Dispose() }
    }
}

# Capture provenance before creating the output artifacts.
$engineeringCommit = Invoke-GitText -GitArgs @('rev-parse', 'HEAD')
$engineeringBranch = Invoke-GitText -GitArgs @('branch', '--show-current')
$worktreeStatus = Invoke-GitText -GitArgs @('status', '--porcelain')
$worktreeDirty = -not [string]::IsNullOrWhiteSpace($worktreeStatus)
$bellmanMultiexpPath = Join-Path $RepoPath 'vendor\bellman\src\multiexp.rs'
$bellmanMultiexpSha256 = if (Test-Path -LiteralPath $bellmanMultiexpPath -PathType Leaf) {
    (Get-FileHash -LiteralPath $bellmanMultiexpPath -Algorithm SHA256).Hash.ToLowerInvariant()
} else { 'NOT_FOUND' }
$scriptSha256 = if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath -PathType Leaf)) {
    (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
} else { 'UNAVAILABLE' }

$spendResult = Inspect-ParameterFile -Circuit 'Spend' -Path $SpendParamsPath -ExpectedIcCount 8
$outputResult = Inspect-ParameterFile -Circuit 'Output' -Path $OutputParamsPath -ExpectedIcCount 6
$allRows = @($spendResult.Rows) + @($outputResult.Rows)
$allSummaries = @($spendResult.Summary, $outputResult.Summary)

$csvPath = Join-Path $RawCsvDir "sapling_parameter_size_breakdown_$Timestamp.csv"
$summaryCsvPath = Join-Path $RawCsvDir "sapling_parameter_size_summary_$Timestamp.csv"
$markdownPath = Join-Path $MetadataDir "sapling_parameter_size_breakdown_$Timestamp.md"

$allRows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding utf8
$allSummaries | Export-Csv -LiteralPath $summaryCsvPath -NoTypeInformation -Encoding utf8

$spend = $spendResult.Summary
$output = $outputResult.Summary
$createdAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
$dirtyText = if ($worktreeDirty) { 'true' } else { 'false' }
$markdown = @"
# Sapling Parameter Serialization Size Breakdown

- Measurement timestamp: $createdAt
- Engineering repository: kaikai-cao/zcash-sapling-engineering
- Engineering commit at measurement start: $engineeringCommit
- Branch: $engineeringBranch
- Worktree dirty at measurement start: $dirtyText
- vendor/bellman/src/multiexp.rs SHA-256: $bellmanMultiexpSha256
- Measurement script SHA-256: $scriptSha256
- Detailed section CSV: experiments/raw/csv/sapling_parameter_size_breakdown_$Timestamp.csv
- Summary CSV: experiments/raw/csv/sapling_parameter_size_summary_$Timestamp.csv

## Results

All sizes below are serialized byte counts. MiB uses 1,048,576 bytes.

| Measurement | Spend | Output |
|---|---:|---:|
| Full parameter file (bytes) | $($spend.ParameterFileBytes) | $($output.ParameterFileBytes) |
| Full parameter file (MiB) | $($spend.ParameterFileMiB) | $($output.ParameterFileMiB) |
| Full file SHA-256 | $($spend.ParameterFileSHA256) | $($output.ParameterFileSHA256) |
| Groth16 Parameters body, including VK (bytes) | $($spend.Groth16ParametersBodyBytes) | $($output.Groth16ParametersBodyBytes) |
| VK serialized size (bytes) | $($spend.VerifyingKeySerializedBytes) | $($output.VerifyingKeySerializedBytes) |
| Five query-vector fields, excluding VK (bytes) | $($spend.QueryVectorsSerializedBytes) | $($output.QueryVectorsSerializedBytes) |
| MPC trailer (bytes) | $($spend.MpcTrailerBytes) | $($output.MpcTrailerBytes) |
| MPC contribution records | $($spend.MpcContributorCount) | $($output.MpcContributorCount) |
| Bytes per MPC contribution record | $($spend.MpcContributionRecordBytes) | $($output.MpcContributionRecordBytes) |
| VK IC count | $($spend.IcCount) | $($output.IcCount) |
| H query count | $($spend.H_G1_Count) | $($output.H_G1_Count) |
| L query count | $($spend.L_G1_Count) | $($output.L_G1_Count) |
| A query count | $($spend.A_G1_Count) | $($output.A_G1_Count) |
| B G1 query count | $($spend.B_G1_Count) | $($output.B_G1_Count) |
| B G2 query count | $($spend.B_G2_Count) | $($output.B_G2_Count) |
| Exact EOF reached | $($spend.ParserReachedExactEOF) | $($output.ParserReachedExactEOF) |

## Serialization method

The parser follows the serialized field order used by Bellman Groth16 `Parameters::write` for the main body: VK first, followed by H, L, A, B-G1, and B-G2 query vectors. BLS12-381 uncompressed point sizes used here are 96 bytes for G1 and 192 bytes for G2. The VK is represented as six fixed points plus a 4-byte IC length prefix and the IC G1 points.

The file trailer is interpreted according to `phase2` MPC parameter serialization: a 64-byte circuit hash, a 4-byte big-endian contributor count, then one contribution record per contributor. Each contribution record comprises three uncompressed G1 points, one uncompressed G2 point, and a 64-byte transcript, giving $MpcRecordBytes bytes per record.

The parser reached the exact end of both files. That confirms the section arithmetic and the trailer lengths agree with the actual file sizes. The CSV retains every parsed section's start/end offsets and lengths for re-checking.

## Interpretation and limits

- `VerifyingKeySerializedBytes` is the VK's serialized size as embedded in the parameter file; this does not mean a separate VK file exists.
- `QueryVectorsSerializedBytes` is the combined serialized size of H/L/A/B-G1/B-G2 query-vector fields, including their length prefixes. It is **not** a separate standalone PK file size.
- `Groth16ParametersBodyBytes` includes the VK and all five query-vector fields, but excludes the MPC trailer.
- The parameter files' total size includes the MPC trailer and should not be confused with process memory usage, CRS generation time, or proof size.
- The A/B query counts reflect the serialized vectors; Bellman filters points at infinity from A/B queries during parameter generation, so these counts need not equal raw circuit variable counts.
- This is a read-only structural measurement; no proving benchmark was run as part of this script.

## Inputs

- Spend parameter file: $SpendParamsPath
- Output parameter file: $OutputParamsPath
- Point encoding assumptions: G1 = $G1Bytes bytes; G2 = $G2Bytes bytes
- MPC contribution record layout: 3 x G1 + 1 x G2 + 64-byte transcript
"@
Set-Content -LiteralPath $markdownPath -Value $markdown -Encoding utf8

Write-Host ''
Write-Host '================ PARAMETER SIZE BREAKDOWN ================'
$allSummaries | Format-Table Circuit, ParameterFileBytes, Groth16ParametersBodyBytes, VerifyingKeySerializedBytes, QueryVectorsSerializedBytes, MpcTrailerBytes, MpcContributorCount, ParserReachedExactEOF -AutoSize
Write-Host ''
Write-Host "ENGINEERING_COMMIT=$engineeringCommit"
Write-Host "ENGINEERING_BRANCH=$engineeringBranch"
Write-Host "ENGINEERING_WORKTREE_DIRTY_AT_START=$dirtyText"
Write-Host "BELLMAN_MULTEXP_SHA256=$bellmanMultiexpSha256"
Write-Host "SCRIPT_SHA256=$scriptSha256"
Write-Host "DETAIL_CSV=$csvPath"
Write-Host "SUMMARY_CSV=$summaryCsvPath"
Write-Host "METADATA_MD=$markdownPath"
Write-Host "SPEND_PARAMS_SHA256=$($spend.ParameterFileSHA256)"
Write-Host "OUTPUT_PARAMS_SHA256=$($output.ParameterFileSHA256)"
Write-Host 'STATUS=SUCCESS'
