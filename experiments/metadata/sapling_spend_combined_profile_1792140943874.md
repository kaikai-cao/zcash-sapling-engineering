# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792140943874
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=1; SAPLING_PROFILE=1
- Run data label: fallback_ablation
- Branch counters: disabled
- Force async worker: False
- Worker fallback records: 5
- Forced-async override records: 0
- Run start: 2026-10-16T16:54:53.2242609+08:00
- Run end: 2026-10-16T16:56:24.0773168+08:00
- Repository branch: experiment/fallback-ablation-20261016
- Engineering repository HEAD at start: 6dff8a5dfab877c23deab51c0629a38dafa6a23c
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M experiments/prover-smoke/src/bin/spend_prover_smoke.rs;  M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/multicore.rs;  M vendor/bellman/src/multiexp.rs; ?? experiments/metadata/sapling_spend_worker_fallback_ablation_protocol_20261016.md
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

- vendor/bellman/src/multiexp.rs SHA-256: 6c188fb56ca5c967191f49ca9bc3963c2d59ce1d105b5aa40a55607ea8166866
- vendor/bellman/src/multicore.rs SHA-256: 76853b028f1d7ebcf79a3b2b4ff03ae54262a4a4e57a5e2b6517e8003320d79b
- vendor/groth16/src/prover.rs SHA-256: 4cc75dd822760c0f498a52351cf7e9f0d4c7455963230a76de25928d5c3b1775
- spend_prover_smoke.rs SHA-256: b70aed0f67c9af1716d89624c799c7ed087360e6559828b6be0c127e603c8ea1
- Runner SHA-256: d7453745d7de1626a4a88e01217c81c1bd6954646cc94d9259f8b337670ee210
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 8555.902
- create_proof_body_ms median (ms): 8552.94
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 86.97%
- task_start_delay_ms median across MSM calls (ms): 3363.118
- elapsed_ms median across MSM calls (ms): 520.111
- submit_elapsed_ms median across MSM calls (ms): 0.007
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 1
- Maximum estimated bucket payload for observed concurrency (bytes): 1179360

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 4f4fdbb53440f64ffafd570d37792a373196a774d859ab8f1bc09be599dabaea
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792140943874.csv
- Stage CSV SHA-256: 39c83cb8e71dddc359fedb97d002461ee9eeded7edac070ae5ccd67cc547ec97
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792140943874.csv
- MSM call CSV SHA-256: e664a2bcecf88a0da807f02a535f87121a60c4d1077490b8bde2b854d97b7bde
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792140943874.csv
- Per-run ratio summary CSV SHA-256: e3025ee779accf0e1ca0c8b4d7dc3334ddf8432ffea7ab76da61e3d4d246e28a
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792140943874.csv
- MSM inner-stage CSV SHA-256: d92e547078ed44b9188c7f70c009096c28b59ab95a6da2b987ee478f019c3439
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792140943874.csv
- MSM inner-stage per-query summary CSV SHA-256: 8c5c5b55da085b86a67bb713ad1baa17da2ed310551e0ace787a1c28f918ea95
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261016_165444_915.stdout.log
- Prover stdout SHA-256: 9acbf269779979a64597b60c9c7564cbef2c3732044d4503923122909d7be4e2
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261016_165444_915.stderr.log
- Prover stderr SHA-256: 5db1673ae48b47d5674b762263ecabb49356374706cc2515870e917f35e36ef7
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165444_915.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261016_165444_915.stderr.log
- Build stderr SHA-256: a999dea0d610386a0c131f27725ff0874832de86e0557ea6a0a66c713123816c

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