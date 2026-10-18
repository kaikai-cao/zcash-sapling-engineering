# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792149424509
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: sapling_inner_stage_scaling
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-16T19:16:39.6909734+08:00
- Run end: 2026-10-16T19:17:09.0311137+08:00
- Repository branch: experiment/fallback-ablation-20261016
- Engineering repository HEAD at start: 6dff8a5dfab877c23deab51c0629a38dafa6a23c
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M experiments/prover-smoke/src/bin/spend_prover_smoke.rs;  M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/multicore.rs;  M vendor/bellman/src/multiexp.rs; ?? experiments/metadata/sapling_spend_combined_profile_1792140943874.md; ?? experiments/metadata/sapling_spend_combined_profile_1792141252805.md; ?? experiments/metadata/sapling_spend_combined_profile_1792141969850.md; ?? experiments/metadata/sapling_spend_combined_profile_1792142089756.md; ?? experiments/metadata/sapling_spend_combined_profile_1792142934977.md; ?? experiments/metadata/sapling_spend_combined_profile_1792146583061.md; ?? experiments/metadata/sapling_spend_combined_profile_1792147098286.md; ?? experiments/metadata/sapling_spend_combined_profile_1792147150753.md; ?? experiments/metadata/sapling_spend_combined_profile_1792147441767.md; ?? experiments/metadata/sapling_spend_worker_fallback_ablation_protocol_20261016.md; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792146583061.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792147098286.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792147150753.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792147441767.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792146583061.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792147098286.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792147150753.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792147441767.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792146583061.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792147098286.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792147150753.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792147441767.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792146583061.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792147098286.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792147150753.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792147441767.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_repeat.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_sapling_inner_stage_parallel.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_timer_overhead_recheck.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792140943874.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792141252805.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792141969850.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792142089756.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792142934977.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792146583061.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792147098286.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792147150753.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792147441767.csv; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165444_915.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165444_915.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165957_257.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_165957_257.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171154_556.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171154_556.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171355_323.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_171355_323.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_172800_339.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_172800_339.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_182913_374.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_182913_374.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_183752_448.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_183752_448.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_183844_948.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_183844_948.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_184310_979.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261016_184310_979.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165444_915.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165444_915.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165957_257.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165957_257.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171154_556.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171154_556.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171355_323.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_171355_323.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_172800_339.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_172800_339.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_182913_374.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_182913_374.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_183752_448.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_183752_448.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_183844_948.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_183844_948.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_184310_979.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261016_184310_979.stdout.log
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

- Outer Prove median (ms): 690.859
- create_proof_body_ms median (ms): 688.159
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 271.84%
- task_start_delay_ms median across MSM calls (ms): 0.023
- elapsed_ms median across MSM calls (ms): 190.358
- submit_elapsed_ms median across MSM calls (ms): 0.004
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 9434880

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_sapling_inner_stage_scaling.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 594c61153230069b55b1d78f277cfb8e9babf84cf14044e0fcd35cf07e18e207
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792149424509.csv
- Stage CSV SHA-256: ef02a26a805e61d5041ac6ad4f291de17f64912c82b15ecd734020c56cfc8351
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792149424509.csv
- MSM call CSV SHA-256: 327ff6a694e2eade337821f02b6df7ccdb0cf69206164fb7a4d2094d2aa83a62
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792149424509.csv
- Per-run ratio summary CSV SHA-256: 3063721014d574b699bc6d04b754c3b4c10301ad82b28ab084a2fdea158f2cc6
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792149424509.csv
- MSM inner-stage CSV SHA-256: 8e1d1e6e7f67ce892c33c69e676819d58b2db1f698c3d3f07dba7a9595d0f674
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792149424509.csv
- MSM inner-stage per-query summary CSV SHA-256: 3a57e4c311b59c0642eca8d7a26f772f2bb3f74e120381984aac011313d7514e
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261016_191638_473.stdout.log
- Prover stdout SHA-256: 21ea3db582f02922a8464b2a3e595e12eac741b5f40baf8753c5278947577416
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261016_191638_473.stderr.log
- Prover stderr SHA-256: 17b1f577e5f11aca88d0071866770d477c9562e3412a97f8373cb9fab76afec5
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_191638_473.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_191638_473.stderr.log
- Build stderr SHA-256: 85c8dbac64ed6a362d668bf3988686e26e947620bb15cfdbe2e999a0ff8261b2

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