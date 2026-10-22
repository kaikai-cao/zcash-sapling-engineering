# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792675309694
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_adaptive_20261022_spend_c3
- Branch counters: enabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T21:21:22.9941433+08:00
- Run end: 2026-10-22T21:21:53.1016584+08:00
- Repository branch: stage1/msm-adaptive-window
- Engineering repository HEAD at start: a4577cbb8e002984bf1dde0b6af42d83015462dc
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Untracked output files ignored for cleanliness: True (count: 305)
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

- Outer Prove median (ms): 659.31
- create_proof_body_ms median (ms): 659.238
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 307.56%
- task_start_delay_ms median across MSM calls (ms): 0.144
- elapsed_ms median across MSM calls (ms): 300.692
- submit_elapsed_ms median across MSM calls (ms): 0.018
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 1179648

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_adaptive_20261022_spend_c3.csv (filtered by this batch ID)
- Prover run CSV SHA-256: a854df0122f80ecbe788679b891de1235dc713d7e3934c656f8a3d9879967c7e
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792675309694.csv
- Stage CSV SHA-256: a8d47da4630806657f853c8c2fa54938410d0a2322d9c14f59e45c288e06faf1
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792675309694.csv
- MSM call CSV SHA-256: 7edcbfcb5e0ec753dec9c35314b6cf867e2f6fcad0ee0e7b4af8db4fce967ce7
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792675309694.csv
- Per-run ratio summary CSV SHA-256: 274ea4da8e46c567550e777b8192d7ec1db80adfb74b69c525efb0c5f0ebda14
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792675309694.csv
- MSM inner-stage CSV SHA-256: de0ac4588e27212d7cb4354de86b1f328a76db3721f2b1a0f6a29c04f4fec1c8
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792675309694.csv
- MSM inner-stage per-query summary CSV SHA-256: b624c1dbe35f576c002dfcb1b465295c0fe0bf44ba222a21878a94be0762ac60
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_212121_818.stdout.log
- Prover stdout SHA-256: 4ceb057b8a9d99e8d689b1760b37d3ccd08943fcc7d7e308fb559e9865c2749f
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_212121_818.stderr.log
- Prover stderr SHA-256: 6c1d122a31d1cf48e50a204623122040558f99804c3110fd01a99942569fc65f
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_212121_818.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_212121_818.stderr.log
- Build stderr SHA-256: 2d5694fb348541fae3d68a033b004800c9c79f8f6edb468d5763b1d8f389597a

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