# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792658198687
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_scaling_20261022_spend_t8_5555
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T16:36:11.8243746+08:00
- Run end: 2026-10-22T16:36:42.5043012+08:00
- Repository branch: analysis/msm-scaling-stage0
- Engineering repository HEAD at start: 547c943fec7a01143ecded6d14f49202418f7da5
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Untracked output files ignored for cleanliness: True (count: 171)
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

- Outer Prove median (ms): 762.896
- create_proof_body_ms median (ms): 762.772
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 442.15%
- task_start_delay_ms median across MSM calls (ms): 0.044
- elapsed_ms median across MSM calls (ms): 498.942
- submit_elapsed_ms median across MSM calls (ms): 0.033
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 5898240

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_scaling_20261022_spend_t8_5555.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 4216cfefd632d556b68ee711b40127b83d35d17dd035ac1667aed0d3979f4e9e
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792658198687.csv
- Stage CSV SHA-256: 590926a3116b23dacf9a587c723af2d86b8b060ff32633f080a9b1bfa787c0e4
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792658198687.csv
- MSM call CSV SHA-256: b442a40975f1550f6913de5f5438fe4a74170ca380ab00a85baef23c302828e0
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792658198687.csv
- Per-run ratio summary CSV SHA-256: 1b47754d869caca5fb83b606586a2c590c90c9da69a9e4ff753b636fbcc66aaa
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792658198687.csv
- MSM inner-stage CSV SHA-256: 51d66eefad9231730611cb5610a6842414cff69ad1163427d47575a0be663f17
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792658198687.csv
- MSM inner-stage per-query summary CSV SHA-256: 2d04399f3155400b9dd3e5355959704115998055c5d7bfc6f24634b1f8f39d96
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_163610_604.stdout.log
- Prover stdout SHA-256: bb68a24b6bf6a8ca110b57cab706637a1fea265e70fdfc8e24684be2392efc20
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_163610_604.stderr.log
- Prover stderr SHA-256: e1984439382fb96730789cb9134b3e80cffbe255b5d6880e93f7d698093384ac
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_163610_604.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_163610_604.stderr.log
- Build stderr SHA-256: 09f2b93c4bce5bfb43dca18ca8d9c1dca2831c7d2ffb73b00b96f8f73a607f86

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