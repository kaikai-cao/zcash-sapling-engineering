# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792657696307
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=2; SAPLING_PROFILE=1
- Run data label: msm_scaling_20261022_spend_t2_0xffff
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 65535
- Processor affinity readback: 0xFFFF
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T16:27:48.8415674+08:00
- Run end: 2026-10-22T16:28:26.2762202+08:00
- Repository branch: analysis/msm-scaling-stage0
- Engineering repository HEAD at start: 547c943fec7a01143ecded6d14f49202418f7da5
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Untracked output files ignored for cleanliness: True (count: 45)
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

- Outer Prove median (ms): 1985.313
- create_proof_body_ms median (ms): 1985.194
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 142.75%
- task_start_delay_ms median across MSM calls (ms): 1045.291
- elapsed_ms median across MSM calls (ms): 284.239
- submit_elapsed_ms median across MSM calls (ms): 0.022
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 2
- Maximum estimated bucket payload for observed concurrency (bytes): 2359296

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_scaling_20261022_spend_t2_0xffff.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 3ed2c8a7b55eb18ca3578505e2223c6ef0931801fd53d690c2b8a0627fece246
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792657696307.csv
- Stage CSV SHA-256: 8bfc6b388b9be6d5aea8f588f0f1c3460ad66eb6fcf169e937a758059f3b956e
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792657696307.csv
- MSM call CSV SHA-256: 30c14c08e659c852a60c3f2688ec852d45698aac9d66676ea36b31d611be4c25
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792657696307.csv
- Per-run ratio summary CSV SHA-256: 968b73e64704b7772b26fc7a309d5a15a707c35ee931422bae84743e67cd242c
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792657696307.csv
- MSM inner-stage CSV SHA-256: 73b53f41844135f0db28b01720923c59d2a38c11deea0d4f5b4eb085fc4bb67d
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792657696307.csv
- MSM inner-stage per-query summary CSV SHA-256: cc43203d16745a34cc4931876fee38aed2ba99ea92e2993414d7328c41c79f43
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_162747_630.stdout.log
- Prover stdout SHA-256: b24dbb6c20f85ceb0adac16eccfbcc171094cfd4725ce67530f9a5df199c8927
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_162747_630.stderr.log
- Prover stderr SHA-256: 199a2d2fe6a36a760101c03fc2c8f80e5bec5c9519881d1a41e0c83608fcdc9e
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_162747_630.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_162747_630.stderr.log
- Build stderr SHA-256: a50f4a953f17e887d3844be51c0df233623b83d4462c96d5392c2671458d7fef

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