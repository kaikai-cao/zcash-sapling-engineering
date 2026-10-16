# Sapling Spend MSM source-level operation accounting — batch 1792134295649

## Scope and provenance

- Detail input: `experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792134295649.csv` (40 rows).
- Summary input: `experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792134295649.csv` (8 rows).
- Instrumented source: `vendor/bellman/src/multiexp.rs`.
- Source SHA-256 at analysis time: `7025807986f98327202147abb50a05f7440b6ea12f5a5dc4693bb376effb3e55`.
- This script does not rerun the prover and does not change raw measurement files.

## Code-level interpretation

| Measured field | Source region / exact interpretation |
|---|---|
| `exponent_chunk_prep_ms` | `exponents.iter().map(|exp| exp.chunks(c)).collect()`; transforms each exponent into `Zero`, `One`, or a vector of window chunks. The exact count of allocated inner `Vec<u64>` values is not currently recorded. |
| `bucket_init_sum_ms` | All per-chunk `vec![G::identity(); bucket_count]` initialization intervals added together. |
| `bucket_fill_sum_ms` | All per-chunk passes over `exponents.iter().zip(density_map.iter())`, including density checks, enum branches, base-source `skip`/`next` access, and point additions for selected digits. It is not only group-add time. |
| `bucket_reduce_sum_ms` | All per-chunk reverse bucket loops. Every bucket iteration executes two source-level group accumulation calls: `running_sum.add_assign(&exp)` and `acc.add_assign(&running_sum)`. |
| `chunk_parallel_wall_ms` | Wall-clock time around the parallel chunk iterator through collection; includes scheduling and overlapping work, but excludes exponent chunk preparation and the later merge. |
| `result_merge_ms` | Folding chunk results in reverse order; each part performs `window` doublings followed by one chunk-result addition. |

## Exact source-derived counts per MSM call

The following are source-level iteration/API-call counts derived from `exponent_count`, `window`, and `chunk_count`, not hardware instruction counts.

| Query | Exponent count | Window | Chunks | Fill-loop slots | Bucket elements initialized | Reduction iterations | Reduction add-assign calls | Merge doubles | Merge adds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H_query_G1 | 131,071 | 12 | 22 | 2,883,562 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| L_query_G1 | 98,638 | 12 | 22 | 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| A_input_G1 | 8 | 3 | 85 | 680 | 595 | 595 | 1,190 | 255 | 85 |
| A_aux_G1 | 98,638 | 12 | 22 | 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| B_G1_input | 8 | 3 | 85 | 680 | 595 | 595 | 1,190 | 255 | 85 |
| B_G1_aux | 98,638 | 12 | 22 | 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| B_G2_input | 8 | 3 | 85 | 680 | 595 | 595 | 1,190 | 255 | 85 |
| B_G2_aux | 98,638 | 12 | 22 | 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |

### Total across the eight MSM calls in one proof

- Exponent/density loop-slot visits: **11,565,746**.
- Bucket elements initialized across all chunks: **452,235**.
- Bucket-reduction iterations: **452,235**.
- Source-level group `add_assign` calls in bucket reduction: **904,470**.
- Source-level group doubling calls during merge: **2,085**.
- Source-level chunk-result additions during merge: **365**.

Across five successful proof runs, multiply these per-proof counts by five. This does not imply five runs executed at exactly the same hardware instruction count if the code path or input-dependent branches differ; the counted loop slots and reduction loop sizes are fixed by these dimensions.

## Timing findings and caveats

- `bucket_fill_sum_ms` accumulates per-chunk intervals; it can exceed `chunk_parallel_wall_ms` because the chunks overlap in time.
- `aggregate_fill_ms_per_loop_slot_us` is a normalized aggregate timer divided by the loop-slot count. Because it uses summed per-chunk time, it is not a single-thread latency per exponent and includes branch/source-access/group-add work as applicable.
- The H-query fill region is much longer than L-query despite a smaller exponent-count ratio. A plausible reason is different input-dependent `Zero`/`One`/`Chunks` and digit distributions, but those branch/add counts are **not captured by the current data**. Do not state that explanation as proven until branch counters or an independent count-only diagnostic is added.
- `bucket_payload_bytes_per_chunk × max_concurrent_chunk_regions` is a bucket payload estimate associated with overlapping instrumented regions. Since the region guard begins before bucket allocation and ends as the worker closure exits, it is not an exact allocator peak. It excludes other buffers, point vectors, allocator metadata, and the rest of the process.
- The counts above are method/loop counts in Rust source, not exact low-level field multiplication counts or CPU instructions. Those require deeper type implementation analysis or hardware profiling.

## Output

- Operation-count CSV: `results/tables/sapling_spend_msm_operation_counts_1792134295649.csv`.
- Source-level accounting report: `experiments/metadata/sapling_spend_msm_operation_accounting_1792134295649.md`.
