# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792135474677
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=20; SAPLING_PROFILE=1
- Run start: 2026-10-16T15:24:00.5520142+08:00
- Run end: 2026-10-16T15:24:39.0452851+08:00
- Repository branch: main
- Engineering repository HEAD at start: ba5303aac48a43de0dbcca369749699232b41b5c
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

- vendor/bellman/src/multiexp.rs SHA-256: 77ea41ca4d42d1e381b1ef1bafd89fbf3b1c2207f2af5fa1bb02b68c2d4e3832
- vendor/groth16/src/prover.rs SHA-256: 4cc75dd822760c0f498a52351cf7e9f0d4c7455963230a76de25928d5c3b1775
- spend_prover_smoke.rs SHA-256: 0e4ebebb3bb8bc60abf4dd3220a90b4f7a9bf185d3d0c03fb7e55fbcb98b27df
- Runner SHA-256: 7c15f370fac10dfdc9ee52a0d08196fada5835faddbe8a6e529be628ac0cb6d9
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 757.13
- create_proof_body_ms median (ms): 754.213
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 267.93%
- task_start_delay_ms median across MSM calls (ms): 0.082
- elapsed_ms median across MSM calls (ms): 286.493
- submit_elapsed_ms median across MSM calls (ms): 0.004
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 20
- Maximum estimated bucket payload for observed concurrency (bytes): 22407840

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_release.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 57685fbc7115828903de0e2b70f7a074161f38bb7f9571d1c5195b356d7ce860
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792135474677.csv
- Stage CSV SHA-256: 90c9351b38322f1c3976f1843852b6a46970b7047985fbbac8fd1bee96eb522c
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792135474677.csv
- MSM call CSV SHA-256: 276a6a1b6eb28ee2de16cc3232fc3521344e65e3e9eb78592177df4a147ec968
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792135474677.csv
- Per-run ratio summary CSV SHA-256: ee455e187d7c211b99f6e630cb7bbe9c92705d135578404b27173b9d1ad0a95b
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792135474677.csv
- MSM inner-stage CSV SHA-256: 0468369815d9a887cf0a264ad4b89cb8cf4377019cfd1e37a59fac2c9b587140
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792135474677.csv
- MSM inner-stage per-query summary CSV SHA-256: a540d7756991d4cfc1aa30e9ea4aaceb7059a7c7c7b48759b485099031858323
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261016_152354_301.stdout.log
- Prover stdout SHA-256: 193e427a41b6c53c9498f2b0417ea2cf2500b5420f4c901cb23a1dafa3c6e826
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261016_152354_301.stderr.log
- Prover stderr SHA-256: 227de8650627a8396b9f63e77450cff640b2e48e96d119d2d63340f6a995c9c9
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_152354_301.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_152354_301.stderr.log
- Build stderr SHA-256: 7d9cc7321ed41c323886efcf78e7ce875f04e86395e7c91d513b160e1b7de7bd

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