# Sapling Parameter Serialization Size Breakdown

- Measurement timestamp: 2026-10-11T14:27:30+08:00
- Engineering repository: kaikai-cao/zcash-sapling-engineering
- Engineering commit at measurement start: c4f4befaaa73bba750663a8d005f10dd437bda4d
- Branch: main
- Worktree dirty at measurement start: true
- vendor/bellman/src/multiexp.rs SHA-256: 730af1249b78bd422dc62453a3604cb01236c94b2a2331e87e484cbdce876266
- Measurement script SHA-256: add54e81142d95f7b2d492916a36d4b7cfbf9fd28f73e7f6c396124ef1818289
- Detailed section CSV: experiments/raw/csv/sapling_parameter_size_breakdown_20261011_142729.csv
- Summary CSV: experiments/raw/csv/sapling_parameter_size_summary_20261011_142729.csv

## Results

All sizes below are serialized byte counts. MiB uses 1,048,576 bytes.

| Measurement | Spend | Output |
|---|---:|---:|
| Full parameter file (bytes) | 47958396 | 3592860 |
| Full parameter file (MiB) | 45.736691 | 3.426418 |
| Full file SHA-256 | 8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13 | 2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4 |
| Groth16 Parameters body, including VK (bytes) | 47905560 | 3540024 |
| VK serialized size (bytes) | 1636 | 1444 |
| Five query-vector fields, excluding VK (bytes) | 47903924 | 3538580 |
| MPC trailer (bytes) | 52836 | 52836 |
| MPC contribution records | 97 | 97 |
| Bytes per MPC contribution record | 544 | 544 |
| VK IC count | 8 | 6 |
| H query count | 131071 | 8191 |
| L query count | 98638 | 7821 |
| A query count | 85390 | 6298 |
| B G1 query count | 61300 | 4850 |
| B G2 query count | 61300 | 4850 |
| Exact EOF reached | True | True |

## Serialization method

The parser follows the serialized field order used by Bellman Groth16 Parameters::write for the main body: VK first, followed by H, L, A, B-G1, and B-G2 query vectors. BLS12-381 uncompressed point sizes used here are 96 bytes for G1 and 192 bytes for G2. The VK is represented as six fixed points plus a 4-byte IC length prefix and the IC G1 points.

The file trailer is interpreted according to phase2 MPC parameter serialization: a 64-byte circuit hash, a 4-byte big-endian contributor count, then one contribution record per contributor. Each contribution record comprises three uncompressed G1 points, one uncompressed G2 point, and a 64-byte transcript, giving 544 bytes per record.

The parser reached the exact end of both files. That confirms the section arithmetic and the trailer lengths agree with the actual file sizes. The CSV retains every parsed section's start/end offsets and lengths for re-checking.

## Interpretation and limits

- VerifyingKeySerializedBytes is the VK's serialized size as embedded in the parameter file; this does not mean a separate VK file exists.
- QueryVectorsSerializedBytes is the combined serialized size of H/L/A/B-G1/B-G2 query-vector fields, including their length prefixes. It is **not** a separate standalone PK file size.
- Groth16ParametersBodyBytes includes the VK and all five query-vector fields, but excludes the MPC trailer.
- The parameter files' total size includes the MPC trailer and should not be confused with process memory usage, CRS generation time, or proof size.
- The A/B query counts reflect the serialized vectors; Bellman filters points at infinity from A/B queries during parameter generation, so these counts need not equal raw circuit variable counts.
- This is a read-only structural measurement; no proving benchmark was run as part of this script.

## Inputs

- Spend parameter file: D:\Research\zcash-params\sapling-spend.params
- Output parameter file: D:\Research\zcash-params\sapling-output.params
- Point encoding assumptions: G1 = 96 bytes; G2 = 192 bytes
- MPC contribution record layout: 3 x G1 + 1 x G2 + 64-byte transcript
