# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792658814399
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_scaling_20261022_spend_t8_ffff
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 65535
- Processor affinity readback: 0xFFFF
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T16:46:26.3991544+08:00
- Run end: 2026-10-22T16:46:58.1122057+08:00
- Repository branch: analysis/msm-scaling-stage0
- Engineering repository HEAD at start: 547c943fec7a01143ecded6d14f49202418f7da5
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Untracked output files ignored for cleanliness: True (count: 234)
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

- vendor/bellman/src/multiexp.rs SHA-256: 4484aeb5c81b4fa020fdde7213d027e89cbc54dda905cbd4c16261ac06c72688
- vendor/bellman/src/multicore.rs SHA-256: fb951f477ae04ea7e2141a24035f2a5d9114458831d56784e5a2b94eec178dd0
- vendor/groth16/src/prover.rs SHA-256: 43d03f7ebb5c18e4112556c4301e60634edb839caa69fbff319402400e39480e
- spend_prover_smoke.rs SHA-256: 58859dec0a6872dd4aaa0400922dae737eceb2b7f99fa0e7574a117ec7e22f10
- Runner SHA-256: c8d962bbe53e105572fc4ada8b1196e89f695208f508f5c3064ac5d85ce97b2a
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 728.322
- create_proof_body_ms median (ms): 728.213
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 421.32%
- task_start_delay_ms median across MSM calls (ms): 0.112
- elapsed_ms median across MSM calls (ms): 481.995
- submit_elapsed_ms median across MSM calls (ms): 0.022
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 5898240

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_scaling_20261022_spend_t8_ffff.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 74c303db296e78cf84976e1ba9869e2e45235cb52191e4ac47b04f4a791ee8a3
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792658814399.csv
- Stage CSV SHA-256: 10a4c566d5cd6f9183ccad408b26a2ee39106f28f13d3e34e6038b5793bde365
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792658814399.csv
- MSM call CSV SHA-256: 2314f366e3d403f1b40315372c5c066e0f9ab8020c02bc57db41cc3690e224fe
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792658814399.csv
- Per-run ratio summary CSV SHA-256: 30d68639ee48bc13b6ba2290edeb2010bc291dfa072e7d72b71f87df7e6e0136
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792658814399.csv
- MSM inner-stage CSV SHA-256: 53cbc73c6377035118f7932c25ae9948f04aacabdced4b734b5b35f71b2ef415
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792658814399.csv
- MSM inner-stage per-query summary CSV SHA-256: f101b3fa628c388fc14ae2c8e525d8617e39ee5664d99ed5b523a41db35a78ba
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_164625_193.stdout.log
- Prover stdout SHA-256: fba5c03f2d2e2398d0da18fb102331bf8270ed278f788b00b2c5b7907ea73c0d
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_164625_193.stderr.log
- Prover stderr SHA-256: 3cf7905c5cd7f6b88b15ae2918405e4971951d92683a7484b9a946a645817cb2
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_164625_193.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_164625_193.stderr.log
- Build stderr SHA-256: a70da5408e7a6da7efe97b23011504833b16a7875bda14543f2504b5b8c7d97a

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