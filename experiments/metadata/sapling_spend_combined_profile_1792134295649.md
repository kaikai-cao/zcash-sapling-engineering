# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792134295649
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=20; SAPLING_PROFILE=1
- Run start: 2026-10-16T15:04:30.9199882+08:00
- Run end: 2026-10-16T15:04:59.3096099+08:00
- Repository branch: main
- Engineering repository HEAD at start: 6b644b280de093951054db6ec24bf5e4d4a0897e
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Sapling dependency repository: https://github.com/zcash/sapling-crypto
- Sapling dependency HEAD: 88a7946b4a3066787776e11f0a502654167e022d
- Sapling dependency source: git+https://github.com/zcash/sapling-crypto?rev=88a7946b4a3066787776e11f0a502654167e022d#88a7946b4a3066787776e11f0a502654167e022d
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

- vendor/bellman/src/multiexp.rs SHA-256: 7025807986f98327202147abb50a05f7440b6ea12f5a5dc4693bb376effb3e55
- vendor/groth16/src/prover.rs SHA-256: 4cc75dd822760c0f498a52351cf7e9f0d4c7455963230a76de25928d5c3b1775
- spend_prover_smoke.rs SHA-256: 0e4ebebb3bb8bc60abf4dd3220a90b4f7a9bf185d3d0c03fb7e55fbcb98b27df
- Runner SHA-256: 7c15f370fac10dfdc9ee52a0d08196fada5835faddbe8a6e529be628ac0cb6d9
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 584.918
- create_proof_body_ms median (ms): 582.204
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 252.35%
- task_start_delay_ms median across MSM calls (ms): 0.026
- elapsed_ms median across MSM calls (ms): 137.09
- submit_elapsed_ms median across MSM calls (ms): 0.004
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 20
- Maximum estimated bucket payload for observed concurrency (bytes): 23587200

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_release.csv (filtered by this batch ID)
- Prover run CSV SHA-256: a376eeac104b0fe9abbcc09bb5a11b5330dabcb16cad0e7b58aaf1d0ec437b12
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792134295649.csv
- Stage CSV SHA-256: d59272066eb1c91688c3fa59682dd3e18b23b60934d290647fcad35a13d14e07
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792134295649.csv
- MSM call CSV SHA-256: a04df8cba569422455fa73742394e6f365cb29301d5709188433c92b92d1079e
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792134295649.csv
- Per-run ratio summary CSV SHA-256: cf6ffc49d6c1e331ed0170619c6f5d9e3ed044f994fe96a2f0076812c9b5d6ee
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792134295649.csv
- MSM inner-stage CSV SHA-256: 7fa5ddaa657c4307f16a26190664f11c36577c763d60428b7c4a9252db1ab223
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792134295649.csv
- MSM inner-stage per-query summary CSV SHA-256: 91ea8ec118f1776643b910840a6dbedea4bf5cdf19dbcf7f5930ed2f28e13dcf
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261016_150429_715.stdout.log
- Prover stdout SHA-256: f43ca89fd2c299a5464ceeadcd71591c8289fabf8057cf3a1b76ce27f84f56c4
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261016_150429_715.stderr.log
- Prover stderr SHA-256: e6b9fa2da3a9c62f961c496c913d0b421313780518244724b566a61ee795f17c
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_150429_715.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_150429_715.stderr.log
- Build stderr SHA-256: 85c8dbac64ed6a362d668bf3988686e26e947620bb15cfdbe2e999a0ff8261b2

## Validation

- New raw prover batch rows: 5 / 5
- MSM call records: 40 / 40
- Submit timing records: 40 / 40
- Stage timing records: 5 / 5
- MSM inner-stage records: 40 / 40
- MSM inner-stage query summary rows: 8 / 8
- Proof verification: 5/5 passed
- Maximum absolute per-run stage-sum minus body timing (ms): 0.002

No algorithm changes were made as part of this run. Results are diagnostic profile data and are not an optimization claim.