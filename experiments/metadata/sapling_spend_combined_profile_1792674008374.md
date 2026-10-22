# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792674008374
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_adaptive_tail10_smoke_20261022
- Branch counters: enabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T20:59:39.4036093+08:00
- Run end: 2026-10-22T21:00:12.0963719+08:00
- Repository branch: stage1/msm-adaptive-window
- Engineering repository HEAD at start: 75e96375f87f16ac5654da4ed12f128f471a1c34
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/multiexp.rs
- Untracked output files ignored for cleanliness: True (count: 106)
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

- Outer Prove median (ms): 712.731
- create_proof_body_ms median (ms): 712.662
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 341.08%
- task_start_delay_ms median across MSM calls (ms): 0.156
- elapsed_ms median across MSM calls (ms): 466.251
- submit_elapsed_ms median across MSM calls (ms): 0.02
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 1179648

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_adaptive_tail10_smoke_20261022.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 85c341b06119671d483cb6a045c671a9761f9fdb79fc14123373f51f71d86c78
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792674008374.csv
- Stage CSV SHA-256: 45f915a9e1ce8d08560bad2b0b2d220965be0f950e63255ac72253886861cff5
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792674008374.csv
- MSM call CSV SHA-256: 21a50a2cbe289d4a32515c2143804f4e8146aa1d0a92b14b79471ca2243b37ca
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792674008374.csv
- Per-run ratio summary CSV SHA-256: 76d461ecb57df9652b649bce22bb5dbb112f3048211865d7061866bb37461133
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792674008374.csv
- MSM inner-stage CSV SHA-256: 920c5b1927fc892799116f9c1174d6fa085a60663f70e0f9251e73f06369ee0d
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792674008374.csv
- MSM inner-stage per-query summary CSV SHA-256: 772a74281b4ee79ec8f2d291e5579093ea9fabe649cc2ce34f878448c8b68feb
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_205938_188.stdout.log
- Prover stdout SHA-256: a055b6100f6f7307a094a614550b5f27e3ee6783ed249907ad5a1647570516f9
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_205938_188.stderr.log
- Prover stderr SHA-256: 7df4167eba53dc6e2e91411bc9636f2179d96f049a50adbd924455247df45bab
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_205938_188.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_205938_188.stderr.log
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