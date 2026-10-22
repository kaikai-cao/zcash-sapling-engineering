# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792673953152
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_adaptive_tail13_smoke_20261022
- Branch counters: enabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T20:58:44.1619443+08:00
- Run end: 2026-10-22T20:59:17.2516115+08:00
- Repository branch: stage1/msm-adaptive-window
- Engineering repository HEAD at start: 75e96375f87f16ac5654da4ed12f128f471a1c34
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/multiexp.rs
- Untracked output files ignored for cleanliness: True (count: 95)
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

- Outer Prove median (ms): 797.255
- create_proof_body_ms median (ms): 797.166
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 341.32%
- task_start_delay_ms median across MSM calls (ms): 0.084
- elapsed_ms median across MSM calls (ms): 289.584
- submit_elapsed_ms median across MSM calls (ms): 0.024
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 9437184

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_adaptive_tail13_smoke_20261022.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 412fd9c45b1f8cf9e769f0d8ddc9700ff12559b626334487faa0560278f41a8a
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792673953152.csv
- Stage CSV SHA-256: b7a1f33337ff447997775395af67fa375b95f6a7f270baa1934891c841a99bcd
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792673953152.csv
- MSM call CSV SHA-256: f9d51247a49013b76896833930df6d775835877ad70d0c1cde4a57554290818c
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792673953152.csv
- Per-run ratio summary CSV SHA-256: 2ab61663f96074c09f10e3343c4394e1a1f02a4544a112a0097ce3534c088bf8
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792673953152.csv
- MSM inner-stage CSV SHA-256: b58e31784e2ee0b58d42b2e0f95fe3d2b40956a1068664c548f83d53459aefcc
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792673953152.csv
- MSM inner-stage per-query summary CSV SHA-256: cee72f81cd99a72e65c1a04e743ce29f0ed7a3970a1456e34929dcb4ca0f3e94
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_205842_957.stdout.log
- Prover stdout SHA-256: 90956c95f2be672355c437c207b4d1c22c2b9bb582abb7dc59d5dd6baac7a7ae
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_205842_957.stderr.log
- Prover stderr SHA-256: a5bc17431989b867a1402c5085f9c644558f49b43472c03afeae13f54bfdd1c6
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_205842_957.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_205842_957.stderr.log
- Build stderr SHA-256: 1ff8bbcb4151dc887e69b78a29bc241d5062cba4757aa5f4639926ae712a8181

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