# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792146583061
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=1; SAPLING_PROFILE=1
- Run data label: fallback_ablation_repeat
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Worker fallback records: 5
- Forced-async override records: 0
- Run start: 2026-10-16T18:29:18.3786944+08:00
- Run end: 2026-10-16T18:30:01.7368357+08:00
- Repository branch: experiment/fallback-ablation-20261016
- Engineering repository HEAD at start: 6dff8a5dfab877c23deab51c0629a38dafa6a23c
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M experiments/prover-smoke/src/bin/spend_prover_smoke.rs;  M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/multicore.rs;  M vendor/bellman/src/multiexp.rs; ?? experiments/metadata/sapling_spend_combined_profile_1792140943874.md; ?? experiments/metadata/sapling_spend_combined_profile_1792141252805.md; ?? experiments/metadata/sapling_spend_combined_profile_1792141969850.md; ?? experiments/metadata/sapling_spend_combined_profile_1792142089756.md; ?? experiments/metadata/sapling_spend_combined_profile_1792142934977.md; ?? experiments/metadata/sapling_spend_worker_fallback_ablation_protocol_20261016.md; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_repeat.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792142934977.csv; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165444_915.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165444_915.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165957_257.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165957_257.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171154_556.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171154_556.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171355_323.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171355_323.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_172800_339.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_172800_339.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165444_915.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165444_915.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165957_257.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165957_257.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171154_556.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171154_556.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171355_323.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171355_323.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_172800_339.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_172800_339.stdout.log
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

- vendor/bellman/src/multiexp.rs SHA-256: 32d68ce5b11145d3730d26b662b3c593fc868df0ce1fea72d4b2f96bb12f79d3
- vendor/bellman/src/multicore.rs SHA-256: 76853b028f1d7ebcf79a3b2b4ff03ae54262a4a4e57a5e2b6517e8003320d79b
- vendor/groth16/src/prover.rs SHA-256: 4cc75dd822760c0f498a52351cf7e9f0d4c7455963230a76de25928d5c3b1775
- spend_prover_smoke.rs SHA-256: b70aed0f67c9af1716d89624c799c7ed087360e6559828b6be0c127e603c8ea1
- Runner SHA-256: 8d3fc072810ad8c3f9883a889c2b661edd6ba3719bab1b5bb25a515d8d4e6c44
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 3615.341
- create_proof_body_ms median (ms): 3612.556
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 86.03%
- task_start_delay_ms median across MSM calls (ms): 1716.045
- elapsed_ms median across MSM calls (ms): 270.146
- submit_elapsed_ms median across MSM calls (ms): 0.003
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 1
- Maximum estimated bucket payload for observed concurrency (bytes): 1179360

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_repeat.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 393dd528c1d17b356edde49c5e585bd9427e049a7a8d2733ca6410528bb409f1
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792146583061.csv
- Stage CSV SHA-256: 946d884a57371f5c944a4259413b3cff88058d2b03cf91d9335b3d60443bca9b
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792146583061.csv
- MSM call CSV SHA-256: bd4f8a33dcede33edfa25216512a50ddd4760465a0cc42660a141584e5cf6118
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792146583061.csv
- Per-run ratio summary CSV SHA-256: b99fef8ad3a71e5d5739423e6f41db011714a4f15f18ca8a1c3a56d634ba05c2
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792146583061.csv
- MSM inner-stage CSV SHA-256: bfba6bac25c550f797df35c110d635ff88426f94738d7391545a1b27359576b7
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792146583061.csv
- MSM inner-stage per-query summary CSV SHA-256: eb7fa3066ada03e19512c3ceaeff4101c63853e9949de9465ce104bbc5aff052
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261016_182913_374.stdout.log
- Prover stdout SHA-256: 0f3fb7c493294796abfc45679b30c3c8bb2670bd34fcd45bdbe310534e4712a2
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261016_182913_374.stderr.log
- Prover stderr SHA-256: 6516af1065356dcd8b718faeb0322c90998aa08d9c4b32308c09df91fd8b84bb
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_182913_374.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_182913_374.stderr.log
- Build stderr SHA-256: ff456b234202b717ceef839d800a32f2e730df5802218b7bf8f4e1575b3b9973

## Validation

- New raw prover batch rows: 5 / 5
- MSM call records: 40 / 40
- Submit timing records: 40 / 40
- Stage timing records: 5 / 5
- MSM inner-stage records: 40 / 40
- MSM inner-stage query summary rows: 8 / 8
- Proof verification: 5/5 passed
- Maximum absolute per-run stage-sum minus body timing (ms): 0.001

No algorithm changes were made as part of this run. Results are diagnostic profile data and are not an optimization claim.