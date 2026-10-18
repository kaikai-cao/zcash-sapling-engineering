# Sapling Spend MSM Branch-Counter vs Inner-Stage Timing Join — 20261018

## Inputs and provenance

| Item | Inner-stage batch | Branch-counter batch |
|---|---|---|
| Batch ID | `1792134295649` | `1792135474677` |
| Detail CSV | `experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792134295649.csv` | `experiments/raw/csv/sapling_spend_msm_branch_profile_1792135474677.csv` |
| Rows | 40 (8 queries x 5 runs) | 40 (8 queries x 5 runs) |
| Parameter file SHA-256 | `8e48ffd2...efc13` | `8e48ffd2...efc13` (identical) |
| Sapling dependency | `88a7946b...22d` | `88a7946b...22d` (identical) |
| RAYON_NUM_THREADS | 20 | 20 |
| Verified proofs | 5/5 | 5/5 |

## Join validation performed by the script

- Every query has exactly five runs in both batches.
- Branch counters are identical across the five runs of the branch batch (deterministic structural counts; the instrumentation only observes).
- `exponent_count`, `window`, `bucket_count`, and `chunk_count` from the inner-stage batch match the archived source-derived operation-count table (`results/tables/sapling_spend_msm_operation_counts_1792134295649.csv`) for every query, and the computed reduction iterations (`chunk_count x bucket_count`) match its exact per-call counts.

## How to read the join

- Stage timings come only from the inner-stage batch; they are never compared across batches. The branch batch's own Outer Prove median (757.13 ms) differs from the inner-stage batch's (584.918 ms) because the added counters change instrumentation overhead, not the counted work.
- `bucket_fill_sum_ms` sums per-chunk fill intervals; chunks overlap under 20 threads, so it is aggregate work, not wall time.
- `fill_us_per_nonzero_digit` divides fill time by `nonzero_window_digit_visits` (equal to `bucket_base_add_calls` in this data). The fill region also contains density checks and base-source `skip` traversal, so this is an upper bound on pure group-add cost per digit.
- `reduce_us_per_reduction_iteration` uses reduction iterations = `chunk_count x bucket_count`, matching the source-level accounting report.
- Both ratio-of-medians and median-of-per-run-ratios are reported; they are close but not identical.

## Per-query joined table

| Query | Group | Exponents | Nonzero digits | Zero/One exponent slots | Base skips | Fill median (ms) | Fill us/nonzero digit | Reduce median (ms) | Reduce us/iteration |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| H_query_G1 | G1 | 131,071 | 2,864,709 | 0 | 18,853 | 2,622.717 | 0.9155 | 170.739 | 1.8952 |
| L_query_G1 | G1 | 98,638 | 624,833 | 1,541,254 | 1,512,555 | 614.164 | 0.9829 | 179.595 | 1.9935 |
| A_input_G1 | G1 | 8 | 458 | 170 | 220 | 0.376 | 0.821 | 0.986 | 1.6571 |
| A_aux_G1 | G1 | 98,638 | 346,654 | 1,529,550 | 1,499,271 | 375.959 | 1.0845 | 189.726 | 2.106 |
| B_G1_input | G1 | 8 | 0 | 85 | 84 | 0.024 |  | 1.157 | 1.9445 |
| B_G1_aux | G1 | 98,638 | 202,141 | 1,145,166 | 1,120,820 | 227.295 | 1.1244 | 179.393 | 1.9913 |
| B_G2_input | G2 | 8 | 0 | 85 | 84 | 0.018 |  | 3.226 | 5.4218 |
| B_G2_aux | G2 | 98,638 | 202,141 | 1,145,166 | 1,120,820 | 599.776 | 2.9671 | 436.900 | 4.8496 |

## Findings

### F1. The H-query / L-query fill gap is explained by exponent distributions, not by per-digit cost

H_query_G1 fill is 4.27x longer than L_query_G1 (2,622.717 ms vs 614.164 ms), while the exponent counts differ by only 1.33x. The branch counters show why: H_query_G1 has **zero** Zero/One exponent slots (all 2,883,562 active slots are chunked exponents), whereas L_query_G1 has 822,998 Zero and 718,256 One exponent slots. Nonzero window digits differ by 4.58x, closely matching the 4.27x fill ratio.

Per-nonzero-digit fill cost is 0.9155 us for H_query_G1 and 0.9829 us for L_query_G1 — within about 8% of each other. The earlier hypothesis in `sapling_spend_msm_operation_accounting_1792134295649.md` (that input-dependent Zero/One/Chunks and digit distributions could explain the gap) is now supported by direct counts rather than left as a plausible explanation.

### F2. G2 fill costs roughly 2.6x G1 fill for an identical operation mix

B_G1_aux and B_G2_aux have identical exponent counts (98,638) and identical branch counts (202,141 nonzero digits, 1,120,820 skips, same Zero/One split), but fill medians differ: 227.295 ms (G1) vs 599.776 ms (G2). Per nonzero digit, that is 1.1244 us (G1) vs 2.9671 us (G2). This isolates the curve-level group-operation cost difference from workload differences, and is consistent with B-G2 auxiliary being the largest single MSM call in the earlier Output profile.

### F3. Sparse exponents do not merely add slots; they change the traversal pattern

L_query_G1 performs 1,512,555 base-source skip calls against 1,541,254 Zero/One exponent slots, while H_query_G1 performs only 18,853. A_aux_G1 (1,499,271 skips, 1,529,550 Zero/One slots) sits between them, matching its intermediate fill time (375.959 ms) despite having the same exponent count as L_query_G1 and the B auxiliary queries. The skip traversal is a real component of the fill region for sparse queries.

### F4. Within G1, per-digit fill cost varies by roughly 20%

G1 per-nonzero-digit fill values range from 0.9155 us (H_query_G1) to 1.1244 us (B_G1_aux). Candidate causes include base-source memory layout (131,071 vs 98,638 bases), cache behaviour, and the residual skip/branch mix inside the fill region. The current data does not separate these causes.

## Caveats

- This is a cross-batch join of deterministic structural counts with inner-stage timings. It is not a single-batch measurement and must not be quoted as one.
- Counters and stage timings are source-level observations under added instrumentation; they are not a formal performance baseline.
- The per-digit figures include density checks and skip traversal, so they upper-bound pure group-add cost.
- Fill and reduce sums aggregate overlapping per-chunk intervals under 20 threads; they cannot be summed into wall time.
- Five runs per query; treat the percentages as descriptive of this batch, not as confidence intervals.

## Outputs

- Joined table: `results/tables/sapling_spend_msm_branch_stage_join_1792134295649_vs_1792135474677.csv`
- This report: `experiments/metadata/sapling_spend_msm_branch_stage_analysis_20261018.md`
- Regenerate with: `python scripts/analyze_msm_branch_stage_join.py --stage-batch 1792134295649 --branch-batch 1792135474677 --date-tag 20261018`
