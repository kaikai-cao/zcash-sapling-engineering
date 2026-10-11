# Sapling Spend Proving Bottleneck Analysis

Date:
2026-10-11

## Objective

This experiment investigates the proving-side performance
of Zcash Sapling Groth16 proof generation.

The goal is not to modify the Sapling protocol,
but to reproduce the existing proving pipeline and
identify dominant computational costs.

---

## Environment

- Rust: 1.88.0
- Curve: BLS12-381
- Proof system: Groth16
- Target: Sapling Spend proof
- Build: release
- Threads: RAYON_NUM_THREADS=1


---

## Baseline Result

Profiling disabled:

```
Median prove time:
7030 ms

Median verify time:
5.3 ms

Proof size:
192 bytes

Verification:
5/5 PASS
```

The baseline represents the closest measurement of
the original execution path.


---

## Stage Profiling Result

Profiling-enabled execution was used only for
internal attribution.

Main stages:

| Stage | Approximate Cost |
|------|------:|
| create_proof_body | ~3450 ms |
| assignment/query preparation | ~2330 ms |
| QAP FFT preparation | ~380 ms |
| circuit synthesis | ~100 ms |

The proving computation dominates the total execution time.


---

## MSM Profiling Result

Eight MSM categories were observed.

Median execution time:

| MSM Task | Time(ms) |
|---|---:|
| H_query_G1 | 1446 |
| B_G2_aux | 591 |
| L_query_G1 | 399 |
| A_aux_G1 | 278 |
| B_G1_aux | 211 |
| Other MSM | <5 |


The largest contributor is H-query MSM.

Multiple auxiliary MSM operations also contribute
significant proving cost.


---

## Findings

1. Sapling Spend proof generation is dominated by
   prover-side computation.

2. MSM operations are important contributors inside
   the Groth16 proving pipeline.

3. Verification remains lightweight compared with
   proving.

4. Current work only performs profiling and bottleneck
   localization.

5. No algorithm-level optimization has been introduced.

---

## Next Research Direction

Potential optimization directions should be selected only
after understanding the identified bottlenecks.

Possible directions include:

- MSM algorithm optimization
- memory-efficient proving
- parallel scheduling optimization
- proof generation pipeline restructuring
```