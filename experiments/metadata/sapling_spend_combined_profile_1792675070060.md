# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792675070060
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_adaptive_20261022_spend_c0
- Branch counters: enabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T21:17:23.4288510+08:00
- Run end: 2026-10-22T21:17:53.5473510+08:00
- Repository branch: stage1/msm-adaptive-window
- Engineering repository HEAD at start: a4577cbb8e002984bf1dde0b6af42d83015462dc
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Untracked output files ignored for cleanliness: True (count: 245)
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

- vendor/bellman/src/multiexp.rs SHA-256: 3bb4c6389be0c68fdcfe97206f5ee307b7b05856f229f90d1fad3d1b2c80bf5c
- vendor/bellman/src/multicore.rs SHA-256: fb951f477ae04ea7e2141a24035f2a5d9114458831d56784e5a2b94eec178dd0
- vendor/groth16/src/prover.rs SHA-256: 43d03f7ebb5c18e4112556c4301e60634edb839caa69fbff319402400e39480e
- spend_prover_smoke.rs SHA-256: 58859dec0a6872dd4aaa0400922dae737eceb2b7f99fa0e7574a117ec7e22f10
- Runner SHA-256: 151e143305e6abe79cfd397fbb75b075faee6ecbaf05737907a57e6d88171e5f
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 703.742
- create_proof_body_ms median (ms): 703.667
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 408.07%
- task_start_delay_ms median across MSM calls (ms): 0.072
- elapsed_ms median across MSM calls (ms): 423.4
- submit_elapsed_ms median across MSM calls (ms): 0.019
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 5898240

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_adaptive_20261022_spend_c0.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 6889f7e8aa498f35d1f90b3eb36746a17c23a12bb5753d2d3a3d5c8af9837f4e
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792675070060.csv
- Stage CSV SHA-256: 31d02ad8944af14ae10c2c6f1d759faa1468adb17bee4ec4ab684a66cf6e6c87
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792675070060.csv
- MSM call CSV SHA-256: a7514acfe5ef16cb302d122b7a2005c77378155fbe6f9420caad38dc622dcb5f
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792675070060.csv
- Per-run ratio summary CSV SHA-256: 97f3409e06c6d633d1ea2bd27e2061d3f360cd4e1b97dff515bb803206871ad7
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792675070060.csv
- MSM inner-stage CSV SHA-256: 0e6b463e8cd50757fb35907e0bae99a12bee4c35901d6c6f4b36d2db73991285
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792675070060.csv
- MSM inner-stage per-query summary CSV SHA-256: 83031ad0f674f7d8a83e02641110b5a8228de8f0715a4e134202eab43dc5de57
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_211722_219.stdout.log
- Prover stdout SHA-256: 2f8bab3da0847a25bc77382c9f14b2532fa69660ef19a5afc6bcb055dccc7019
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_211722_219.stderr.log
- Prover stderr SHA-256: 7cfd1e97bae63f21c6b197a02a4bf3b284f72e4bf489d5bd3b7db55f4aba2204
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_211722_219.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_211722_219.stderr.log
- Build stderr SHA-256: 2d5694fb348541fae3d68a033b004800c9c79f8f6edb468d5763b1d8f389597a

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