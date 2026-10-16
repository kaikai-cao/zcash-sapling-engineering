# Sapling Spend MSM Branch Counter Accounting — Batch 1792135474677

- Source stderr log: `experiments/raw/logs/sapling_spend_combined_profile_20261016_152354_301.stderr.log`
- Branch counter rows validated: 40 / 40
- Per-query summaries: 8 / 8
- Each query has exactly five runs; call_id mapping follows the collector's established 8-call-per-run ordering.
- Counters are collected locally per chunk and aggregated once after the timed fill loop. They still add instrumentation overhead.

## Counters summed across the five-run diagnostic batch

These totals aggregate five proofs, not one proof. For one-proof operation counts, inspect an individual row/run in the detail CSV.

| Counter | Total across 5 proofs |
|---|---:|
| `density_true_slot_visits` | 48,150,040 |
| `density_false_slot_visits` | 9,678,690 |
| `zero_exponent_slot_visits` | 14,005,970 |
| `one_exponent_slot_visits` | 12,801,410 |
| `chunked_exponent_slot_visits` | 21,342,660 |
| `zero_window_digit_visits` | 137,980 |
| `nonzero_window_digit_visits` | 21,204,680 |
| `bucket_base_add_calls` | 21,204,680 |
| `direct_one_add_calls` | 581,825 |
| `base_skip_calls` | 26,363,535 |
| `base_skip_elements` | 26,363,535 |

## Interpretation rules

- `density_true_slot_visits` + `density_false_slot_visits` equals total loop-slot visits across all chunks.
- Active-density exponent visits partition into Zero, One and Chunks enum variants.
- Chunked exponent visits partition into zero and nonzero window digits.
- `bucket_base_add_calls` counts calls to `add_assign_from_source` for nonzero chunk digits; `direct_one_add_calls` counts the exponent-One direct accumulator path.
- `base_skip_calls` / `base_skip_elements` count `skip(1)` calls/elements, not group additions.
- These counters count source-level branches/calls, not machine instructions; the G1/G2 group-operation cost can differ.
- They are diagnostic measurements with added instrumentation, not a new formal performance baseline.

## Outputs
- Detail CSV: `experiments/raw/csv/sapling_spend_msm_branch_profile_1792135474677.csv`
- Per-query summary CSV: `experiments/raw/csv/sapling_spend_msm_branch_summary_1792135474677.csv`
