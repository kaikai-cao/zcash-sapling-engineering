# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1791802391142
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=20; SAPLING_PROFILE=1
- Run start: 2026-10-12T18:52:46.5021908+08:00
- Run end: 2026-10-12T18:53:14.1290141+08:00
- Repository branch: main
- Engineering repository HEAD at start: a486f86de1bac71f230e17749ce3aa7639dc3deb
- Engineering worktree dirty at start: False
- Engineering source commit is the recorded HEAD; profiler worktree status at start: 
- Sapling dependency repository: D:\Research\zcash-sapling-crypto
- Sapling dependency HEAD: 88a7946b4a3066787776e11f0a502654167e022d
- Sapling dependency worktree: clean
- CPU: Intel(R) Core(TM) i7-14700
- Installed physical memory (bytes): 34031325184
- OS: Microsoft Windows 11 家庭版 Insider Preview 中文版 (10.0.26220, build 26220)
- Rust: rustc 1.98.1 (48a229cea 2026-09-01)
- Cargo: cargo 1.98.1 (797e8a9bc 2026-08-05)

## Parameter identity

- Parameter path: D:\Research\zcash-params\sapling-spend.params
- Parameter bytes: 47958396
- Parameter SHA-256: 8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13

## Instrumented source identity

- vendor/bellman/src/multiexp.rs SHA-256: abfeb75bd92fe9e890d0a6f3a74d33cc20b711e13aeb31a4bbe2fbe8f405b2b1
- vendor/groth16/src/prover.rs SHA-256: 4cc75dd822760c0f498a52351cf7e9f0d4c7455963230a76de25928d5c3b1775
- spend_prover_smoke.rs SHA-256: f9ab2d1bca25a4dde8a09093dbbbb27b956d2ca1bf0650cf1e12502898297253
- Runner SHA-256: 441dfc9c4f4c04018d52984915e96b00bfb13c22251e5e3121c6f1f1743b1d2e
- Cargo manifest SHA-256: 59926e0e295fd67978621bbbbb3ae17f4b08b039a96af44fbc2268cfe2535d99

## Result summary

- Outer Prove median (ms): 578.335
- create_proof_body_ms median (ms): 575.654
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 285.87%
- task_start_delay_ms median across MSM calls (ms): 0.014
- elapsed_ms median across MSM calls (ms): 314.713
- submit_elapsed_ms median across MSM calls (ms): 0.004

The three MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_release.csv (filtered by this batch ID)
- Prover run CSV SHA-256: d5fd3058d4202e3e050d157e36b6d90eef8370d3038c731859dc55b571d7e406
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1791802391142.csv
- Stage CSV SHA-256: 078019b5e449647aa379b309242f79208869dbc5e20afc86c7d69a65667daf6b
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1791802391142.csv
- MSM call CSV SHA-256: a5f3d4d8edf36422c5c6e5d9b1cda7bf79662df6324f2489012aaa7338bbb563
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1791802391142.csv
- Per-run ratio summary CSV SHA-256: ddf34fcad405b72c89191a5f5630a6c582576c5b56e94e8821f1593c4ef470c6
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261012_185246_050.stdout.log
- Prover stdout SHA-256: f2e3a5b808b39f0f9002dda658d8c92387c65e1a4da2af4c645ba63e8d422ae7
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261012_185246_050.stderr.log
- Prover stderr SHA-256: c0bdcbb2f578b61abd9d45fcf3be2c70e980b58e11d980a55feab8503719e441
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261012_185246_050.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261012_185246_050.stderr.log
- Build stderr SHA-256: c9ef3b68d69664e1d157e575848e4f6146e26ad39b9aa75897123cb92d2ce4bd

## Validation

- New raw prover batch rows: 5 / 5
- MSM call records: 40 / 40
- Submit timing records: 40 / 40
- Stage timing records: 5 / 5
- Proof verification: 5/5 passed
- Maximum absolute per-run stage-sum minus body timing (ms): 0.002

No algorithm changes were made as part of this run. Results are diagnostic profile data and are not an optimization claim.