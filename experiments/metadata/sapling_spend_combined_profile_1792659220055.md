# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792659220055
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_scaling_20261022_spend_t8_0x5555_c12
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T16:53:14.6122414+08:00
- Run end: 2026-10-22T16:53:43.4816698+08:00
- Repository branch: analysis/msm-scaling-stage0
- Engineering repository HEAD at start: 547c943fec7a01143ecded6d14f49202418f7da5
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

- vendor/bellman/src/multiexp.rs SHA-256: 4484aeb5c81b4fa020fdde7213d027e89cbc54dda905cbd4c16261ac06c72688
- vendor/bellman/src/multicore.rs SHA-256: fb951f477ae04ea7e2141a24035f2a5d9114458831d56784e5a2b94eec178dd0
- vendor/groth16/src/prover.rs SHA-256: 43d03f7ebb5c18e4112556c4301e60634edb839caa69fbff319402400e39480e
- spend_prover_smoke.rs SHA-256: 58859dec0a6872dd4aaa0400922dae737eceb2b7f99fa0e7574a117ec7e22f10
- Runner SHA-256: 399b902d6a47e84bc431e4efe9f08d06c2a4e25868b4a2cd1c51cb14987b76d6
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 662.031
- create_proof_body_ms median (ms): 661.928
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 289.06%
- task_start_delay_ms median across MSM calls (ms): 228.888
- elapsed_ms median across MSM calls (ms): 192.592
- submit_elapsed_ms median across MSM calls (ms): 0.024
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 4718592

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_scaling_20261022_spend_t8_0x5555_c12.csv (filtered by this batch ID)
- Prover run CSV SHA-256: fad6be4ca77aefb773e726776fd2f154cd271155b9d6553a6cb8a9f33d85f6ef
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792659220055.csv
- Stage CSV SHA-256: 1c1869d41bb87e074ccb164956dc1891359bce875f490a2b9029d786e6571644
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792659220055.csv
- MSM call CSV SHA-256: 268da6c896c22f8cef2dacd2420ea57089ae8ff6c5907e0daf7a9cf0d77dda27
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792659220055.csv
- Per-run ratio summary CSV SHA-256: 00254fcc1d4eea50157f4503856c3b0690ccbd72ac9cf0a32e77beca109e57a4
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792659220055.csv
- MSM inner-stage CSV SHA-256: 827ae7548cf31c8c31bd5aedceb47204d83533e989ae19eb8866ea46062ad7c1
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792659220055.csv
- MSM inner-stage per-query summary CSV SHA-256: a1a16c264bcead254a91410ec4a5e7f07173b2cb8ffd8aa60c076df92d0c21a9
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_165313_415.stdout.log
- Prover stdout SHA-256: 4da95512c3c9631fb3568576ac108a3ada690ca84a799e1988f37f3e820fc6fd
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_165313_415.stderr.log
- Prover stderr SHA-256: 2657aa02ec269aa707cd84ad3df8c96f3d4b7004c9e2ea08228b23f7d3264b46
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_165313_415.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_165313_415.stderr.log
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