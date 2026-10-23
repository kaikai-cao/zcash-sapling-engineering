# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792718746987
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_c12_pilot_20261023_c0_b4
- Branch counters: enabled
- Fine-grained MSM inner-stage timing: enabled
- Explicit MSM window override: default
- Explicit MSM window minimum exponent count: 0
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-23T09:25:18.1853657+08:00
- Run end: 2026-10-23T09:25:51.1050791+08:00
- Repository branch: stage2/msm-c12-pilot
- Engineering repository HEAD at start: 4c9281c9f5e0a1aae6eb584373945ff2ef3b6ebf
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Untracked output files ignored for cleanliness: True (count: 38)
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

- vendor/bellman/src/multiexp.rs SHA-256: 98f48fe41040f44f4e88a2819601446caaeb00bd7c61aa43ca4a231b689c9423
- vendor/bellman/src/multicore.rs SHA-256: fb951f477ae04ea7e2141a24035f2a5d9114458831d56784e5a2b94eec178dd0
- vendor/groth16/src/prover.rs SHA-256: 43d03f7ebb5c18e4112556c4301e60634edb839caa69fbff319402400e39480e
- spend_prover_smoke.rs SHA-256: 58859dec0a6872dd4aaa0400922dae737eceb2b7f99fa0e7574a117ec7e22f10
- Runner SHA-256: 816bcd22f68a2b8aaa572a40e0a25d8b10a9b4548ecd5cf577ce0020e28b37ec
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 782.905
- create_proof_body_ms median (ms): 782.795
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 388.57%
- task_start_delay_ms median across MSM calls (ms): 0.069
- elapsed_ms median across MSM calls (ms): 503.046
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

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_c12_pilot_20261023_c0_b4.csv (filtered by this batch ID)
- Prover run CSV SHA-256: d4b044290b3d8dbf639febc0d6ef2f254f09db8c9098245a34833f32cc43be82
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792718746987.csv
- Stage CSV SHA-256: da95fbcf1858fc1392d8d26f3f6db27747309583bd55f362dd0ddfc54388cdbe
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792718746987.csv
- MSM call CSV SHA-256: ca61872519505d9077a2b989cdad98d60f8df67a18e371231c4e3bd6b54ddfbe
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792718746987.csv
- Per-run ratio summary CSV SHA-256: 3856747b4396c6aedb2da17c8c5493a6622b81629ac7c0786486427f4f5f656c
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792718746987.csv
- MSM inner-stage CSV SHA-256: a3f3974c342e559c8c3e729df313c8542a13b41f4645c6e722bb3b7229b5a04b
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792718746987.csv
- MSM inner-stage per-query summary CSV SHA-256: c11a1b5035bb835e5fce109bc6b798d3410d9418e89f12313a66ba2043c2908d
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261023_092516_959.stdout.log
- Prover stdout SHA-256: 237fc6e1733e343887798e8bb6c262999382873f6e3acfda06b83f1f6a808a19
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261023_092516_959.stderr.log
- Prover stderr SHA-256: e7d964c24bae7cbb5774954b23c24c15ada5c1ee1c2fd9e0e53e49544ba4b8d2
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261023_092516_959.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261023_092516_959.stderr.log
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