# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792673486925
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_adaptive_smoke_default_20261022
- Branch counters: enabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T20:50:58.3876969+08:00
- Run end: 2026-10-22T20:51:30.5832039+08:00
- Repository branch: stage1/msm-adaptive-window
- Engineering repository HEAD at start: 7787ef7727a97c747ee4c3f92666c5d8e09b7093
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/multiexp.rs
- Untracked output files ignored for cleanliness: True (count: 69)
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

- vendor/bellman/src/multiexp.rs SHA-256: f0a18a9dd411519a2f144464994aae0475382b8bf9e50f30e2f9ceaf185021ed
- vendor/bellman/src/multicore.rs SHA-256: fb951f477ae04ea7e2141a24035f2a5d9114458831d56784e5a2b94eec178dd0
- vendor/groth16/src/prover.rs SHA-256: 43d03f7ebb5c18e4112556c4301e60634edb839caa69fbff319402400e39480e
- spend_prover_smoke.rs SHA-256: 58859dec0a6872dd4aaa0400922dae737eceb2b7f99fa0e7574a117ec7e22f10
- Runner SHA-256: 089650778e1706fa83c96a083a57fa5bb529eb3f9c4628e3761f448e0df39e7c
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 717.053
- create_proof_body_ms median (ms): 716.933
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 362.37%
- task_start_delay_ms median across MSM calls (ms): 0.102
- elapsed_ms median across MSM calls (ms): 460.664
- submit_elapsed_ms median across MSM calls (ms): 0.021
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 5898240

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_adaptive_smoke_default_20261022.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 1c2312a770e45c45c83c330cf9ebbad83a1fc30ac552fd1a47e7152066293d87
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792673486925.csv
- Stage CSV SHA-256: cd6a0afc3abd70845be4f7ac2b639bbe9546ab2bea62b94033bcf55fde054f50
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792673486925.csv
- MSM call CSV SHA-256: a20d090b5146c57d0a6f9f2cf9db8716e83658e0130d94671cdf115c074a8c35
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792673486925.csv
- Per-run ratio summary CSV SHA-256: 5a1a51ef58d97587ea3ccbd3f90447c67852168efc615e403f203fe32ec1ce68
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792673486925.csv
- MSM inner-stage CSV SHA-256: 49c67d231683a91ecd9f41d13b28f737cc219e87441e15fef68da63a1d0e9413
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792673486925.csv
- MSM inner-stage per-query summary CSV SHA-256: 98e28041f3d546ff3cf0fb16020928e6cc8901b3353371b352a53134e84d3f0f
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_205057_175.stdout.log
- Prover stdout SHA-256: 20afe30bb672822e6378adf06801560c5d7dd1953c00e273a77aad917fc3edd2
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_205057_175.stderr.log
- Prover stderr SHA-256: 8a4920e0cc1cb2a1f498d563e071a964e257094cc7e064665f310eef28258580
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_205057_175.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_205057_175.stderr.log
- Build stderr SHA-256: c9ef3b68d69664e1d157e575848e4f6146e26ad39b9aa75897123cb92d2ce4bd

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