# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792205083857
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: sapling_timeline_smoke
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-17T10:43:47.9533662+08:00
- Run end: 2026-10-17T10:44:50.3152158+08:00
- Repository branch: experiment/fallback-ablation-20261016
- Engineering repository HEAD at start: c520342d3d962fd61bdf24b29d9465813534d66f
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M vendor/bellman/src/multiexp.rs;  M vendor/groth16/src/prover.rs
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

- vendor/bellman/src/multiexp.rs SHA-256: 786ed875398108292737e83867676ac8373e340f39dc914449282bf7f77b945d
- vendor/bellman/src/multicore.rs SHA-256: 76853b028f1d7ebcf79a3b2b4ff03ae54262a4a4e57a5e2b6517e8003320d79b
- vendor/groth16/src/prover.rs SHA-256: 87a18a2b7db3d17aed628df483e05ab1e23d6f87c772baece3d70607ad08294e
- spend_prover_smoke.rs SHA-256: b70aed0f67c9af1716d89624c799c7ed087360e6559828b6be0c127e603c8ea1
- Runner SHA-256: 8d3fc072810ad8c3f9883a889c2b661edd6ba3719bab1b5bb25a515d8d4e6c44
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 1252.14
- create_proof_body_ms median (ms): 1245.415
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 270.29%
- task_start_delay_ms median across MSM calls (ms): 203.551
- elapsed_ms median across MSM calls (ms): 305.776
- submit_elapsed_ms median across MSM calls (ms): 1.852
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 9434880

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_sapling_timeline_smoke.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 963bc2a186f778905772beee2ebec29eac7250e0c5e1189f82769719b6ce6ce0
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792205083857.csv
- Stage CSV SHA-256: b69441c720cc67b727f7f25d3e0df6f0d67f4309b283d68331c70100a58c6f8d
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792205083857.csv
- MSM call CSV SHA-256: 792584b6e445b0d9071d5228d0bda23ba703240429d8f91b57a5232f0c7d08e1
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792205083857.csv
- Per-run ratio summary CSV SHA-256: 2ee653a1b6a41fe074529e43919f962d555d4ea5fa6619fd8af86da7a10fb8d6
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792205083857.csv
- MSM inner-stage CSV SHA-256: e287fdfa3596448b4f20cdee31566e97015812ca8cce7d3f6f58818666693603
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792205083857.csv
- MSM inner-stage per-query summary CSV SHA-256: 0946ecd6a81950221b79730a0a266e19d7477ec6cd1f2ae2d37e865f3549e628
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261017_104347_225.stdout.log
- Prover stdout SHA-256: ecd792f4f2089d99583efab026b569af2c4e91aea35cbdcfcfc34176b12f301f
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261017_104347_225.stderr.log
- Prover stderr SHA-256: e6083801db633def97ef184d49ae272accf9ee8c03c5dabea44adf133df1efb7
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261017_104347_225.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261017_104347_225.stderr.log
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