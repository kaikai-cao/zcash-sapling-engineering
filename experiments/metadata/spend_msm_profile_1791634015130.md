# Spend MSM Profile — Batch 1791634015130

## 1. Experiment identity

- Circuit: Sapling Spend
- Proving system: Groth16
- Curve: BLS12-381
- Batch ID: `1791634015130`
- Runs: 5
- Successful proof checks: 5/5
- Encoded proof size: 192 bytes
- Build profile: Release
- Rayon threads: 1
- Operating system: Windows 11
- CPU: Intel Core i7-14700
- Installed memory: 32 GB
- Rust: `1.98.1` (`48a229cea`, 2026-09-01)
- Cargo: `1.98.1` (`797e8a9bc`, 2026-08-05)
- Sapling source: `sapling-crypto 0.9.0`
- Sapling source commit: `88a7946b4a3066787776e11f0a502654167e022d`

## 2. Source revision and artifact hashes

The profiling worktree HEAD was the frozen baseline commit `281f1882bd1b8347f44f485f0f5dca296edafe08`. The experiment was run with a modified, uncommitted working tree. The commit therefore identifies the base revision; the source SHA-256 and source-difference patch identify the instrumented Bellman file used for this batch.

| Artifact | Path | SHA-256 |
|---|---|---|
| Instrumented Bellman source | `vendor/bellman/src/multiexp.rs` in the profiling worktree | `730AF1249B78BD422DC62453A3604CB01236C94B2A2331E87E484CBDCE876266` |
| Primary raw log | `experiments/raw/logs/sapling_spend_msm_queue_profile_20261010_200606.log` | `6433E1D9F22BA98B96FB23C29FED1CF667D452FB2F880732286418C8E82D1530` |
| Source difference from baseline | `experiments/metadata/source_patches/spend_msm_profile_vs_baseline.patch` | `33EC2F896DBC46BBC2C68A71F72E9020E1C965938846ED4ADA0C12ABEB25F8C1` |
| Thread comparison table | `results/tables/sapling_spend_thread_queue_comparison.csv` | `02E0D31047701CEAE591F1AAB8F15AEB663EC63447757C9B6DCCF60D89A276FC` |

The following logs are also preserved. The two earlier single-thread records are auxiliary exploratory runs; the 2/4/8/20-thread logs correspond to the individual thread-configuration batches described in `docs/msm_profiling_notes.md`.

| Raw log | SHA-256 |
|---|---|
| `experiments/raw/logs/sapling_spend_msm_profile_reproduction_20261010_194334.log` | `878E708CE3614FED18E2D4FA77210DB52F837F1CC6C62FCE4F8632B77D828454` |
| `experiments/raw/logs/sapling_spend_msm_queue_profile_20261010_195403.log` | `82084DED96A8A6B07FC84985FDB9C26BB7073A4BA08987478B23C282ED0BB38B` |
| `experiments/raw/logs/sapling_spend_msm_queue_profile_20261010_200606.log` | `6433E1D9F22BA98B96FB23C29FED1CF667D452FB2F880732286418C8E82D1530` |
| `experiments/raw/logs/sapling_spend_msm_queue_2threads_20261010_201521.log` | `0D5C17A03C698107273069A7CC76438391E64EAE13D9CE8C0EBAE90C79B0B517` |
| `experiments/raw/logs/sapling_spend_msm_queue_4threads_20261010_201624.log` | `E6C603EBECCF7571E014D0158C080FB7909FE2DADFC3152DD3B7C1EE6B7A17C8` |
| `experiments/raw/logs/sapling_spend_msm_queue_8threads_20261010_201717.log` | `5607D116D2146C16A6980A68E4A5D03ADA1E2326731D6EFB52AB46D3CA19696E` |
| `experiments/raw/logs/sapling_spend_msm_queue_20threads_20261010_201805.log` | `85587CAE8572B8DFD09AEFD9A19EB9EB9D4A0C34C01F2E8CF4D75BDA5A4B7465` |

## 3. Parameter files

The parameter files are external to the repository.

| Parameter | Bytes | SHA-256 |
|---|---:|---|
| Spend | 47,958,396 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| Output | 3,592,860 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |

Validate external parameter files with `python scripts/verify_params.py` before attempting reproduction.

## 4. Instrumentation and measurement method

The modified `vendor/bellman/src/multiexp.rs` records MSM-call elapsed time, task-start delay, and submit-stage elapsed time. The measurements were collected in Release mode with `RAYON_NUM_THREADS=1`. The Prove timer excludes parameter loading, verifying-key preparation, and witness/input construction.

## 5. Recorded results

- Median Prove time: 8,020.464 ms
- Prove times: 8,020.464, 7,996.506, 8,176.483, 8,320.273, 7,896.238 ms
- Median of per-run ratios of summed MSM-call elapsed time to Prove time: 87.62%
- Successful proof checks: 5/5
- Encoded proof size: 192 bytes

The eight MSM calls are mapped to Groth16 prover query roles using source call order and scalar counts. This profile does not instrument MSM-internal bucket stages.

## 6. Interpretation limits

This is exploratory, heavily instrumented data. The added timers and logging can affect absolute proving time. This batch does not replace the designated formal Spend baseline (batch `1791613854129`, median Prove time 3,385.716 ms). The 87.62% figure describes only this instrumented, single-thread batch and must not be generalized to other workloads.

Each 2/4/8/20-thread configuration currently has one process batch of five proofs. Those results provide scheduling clues, not a reliable curve for identifying the generally optimal thread count. The two earlier single-thread logs are retained for traceability but are not used to calculate the published 87.62% ratio.

No algorithmic optimization has been implemented or validated. The source hash, raw-log hashes, source-difference hash, parameter hashes, batch IDs, toolchain, and thread configuration above are the provenance record for these exploratory measurements.