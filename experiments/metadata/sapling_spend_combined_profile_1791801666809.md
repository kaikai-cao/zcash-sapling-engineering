# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1791801666809
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=1; SAPLING_PROFILE=1
- Run start: 2026-10-12T18:40:42.0525341+08:00
- Run end: 2026-10-12T18:41:24.6435731+08:00
- Repository branch: main
- Engineering repository HEAD at start: 5d386da9ac719bc843d70e0c69a338b1e5110bbd
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
- Runner SHA-256: 79a88937267eee5fa0d90cae0d4d35e3b63a00a81171129c5e777051f78af116
- Cargo manifest SHA-256: 59926e0e295fd67978621bbbbb3ae17f4b08b039a96af44fbc2268cfe2535d99

## Result summary

- Outer Prove median (ms): 3535.699
- create_proof_body_ms median (ms): 3533.094
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 85.07%
- task_start_delay_ms median across MSM calls (ms): 1704.704
- elapsed_ms median across MSM calls (ms): 248.592
- submit_elapsed_ms median across MSM calls (ms): 0.002

The three MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_release.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 6b2a888ef060ad05fa09ccc569c369d389714543b578a30df2003e5f74fd196e
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1791801666809.csv
- Stage CSV SHA-256: 0bfdfdd3ff7ae49c6a51746a1b21114a4c28355cfb81de0aaa9d654f6b60708a
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1791801666809.csv
- MSM call CSV SHA-256: f669cfd1ab014dcf698b714fdc99e88938ce1538663ca785ff6317da52ebe30c
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1791801666809.csv
- Per-run ratio summary CSV SHA-256: 5b0bbaaf11afa59a7d9d956696979afdf19b6412fead16aec53e3db1990838ec
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261012_184026_955.stdout.log
- Prover stdout SHA-256: a320946e2b24dc2c3cf5f5c56d5d43fdb601d140287dd080ec9304bedf986cf0
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261012_184026_955.stderr.log
- Prover stderr SHA-256: ca24d6e11b40dc1f1899c57ebdc4203279a8711155a3df8f575224e279cfa2bd
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261012_184026_955.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261012_184026_955.stderr.log
- Build stderr SHA-256: 989aa595e57eb2f50abe13406300e8042bc59475029b9e27beba58e927380cfa

## Validation

- New raw prover batch rows: 5 / 5
- MSM call records: 40 / 40
- Submit timing records: 40 / 40
- Stage timing records: 5 / 5
- Proof verification: 5/5 passed
- Maximum absolute per-run stage-sum minus body timing (ms): 0.001

No algorithm changes were made as part of this run. Results are diagnostic profile data and are not an optimization claim.