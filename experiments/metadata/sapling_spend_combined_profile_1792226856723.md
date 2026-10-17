# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792226856723
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=1; SAPLING_PROFILE=1
- Run data label: fallback_ablation_pairs
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: disabled
- Force async worker: False
- Processor affinity mask: 1
- Worker fallback records: 5
- Forced-async override records: 0
- Run start: 2026-10-17T16:47:10.7433920+08:00
- Run end: 2026-10-17T16:47:54.9984533+08:00
- Repository branch: experiment/fallback-ablation-20261016
- Engineering repository HEAD at start: b1beca2278adf588add976b1e14355ab8efa1ba5
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M experiments/metadata/sapling_runtime_memory_measurements_20261016.md;  M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/lib.rs;  M vendor/bellman/src/multiexp.rs; ?? docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md; ?? experiments/metadata/sapling_prove_memory_ledger_20261017.md; ?? experiments/prover-smoke/src/bin/exponent_conversion_memory.rs; ?? experiments/prover-smoke/src/bin/prove_memory_ledger.rs; ?? experiments/raw/csv/sapling_prove_memory_ledger.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_affinity_probe.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_pairs_buggy_launcher.csv; ?? experiments/raw/logs/affinity_probe_lp0_20261017_163939.stderr.log; ?? experiments/raw/logs/affinity_probe_lp0_20261017_163939.stdout.log; ?? experiments/raw/logs/affinity_probe_lp20_20261017_164043.stderr.log; ?? experiments/raw/logs/affinity_probe_lp20_20261017_164043.stdout.log; ?? experiments/raw/logs/sapling_exponent_conversion_memory_20261017_163226.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_1t_20261017_162747.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_1t_20261017_162747.memprobe.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_8t_20261017_163006.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_8t_20261017_163006.memprobe.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164257_086.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164257_086.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164347_348.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164347_348.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164434_969.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164434_969.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164521_514.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164521_514.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164257_086.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164257_086.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164347_348.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164347_348.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164434_969.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164434_969.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164521_514.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164521_514.stdout.log; ?? vendor/bellman/src/mem_probe.rs
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

- vendor/bellman/src/multiexp.rs SHA-256: 230fdfbe07c64ce81d90a4aad60cdc5354a156c0b599be8e87cd3263376e7022
- vendor/bellman/src/multicore.rs SHA-256: 76853b028f1d7ebcf79a3b2b4ff03ae54262a4a4e57a5e2b6517e8003320d79b
- vendor/groth16/src/prover.rs SHA-256: 87a18a2b7db3d17aed628df483e05ab1e23d6f87c772baece3d70607ad08294e
- spend_prover_smoke.rs SHA-256: b70aed0f67c9af1716d89624c799c7ed087360e6559828b6be0c127e603c8ea1
- Runner SHA-256: f1f5f4fe1a40ac434fb36c6e00f2e3dd373399e7fa10257f16c16aa5b60fa1e9
- Cargo manifest SHA-256: 45910fd1a523bb2d17e6106a23237e53321aa2974174d01df3cf2679febd3e2e

## Result summary

- Outer Prove median (ms): 3650.035
- create_proof_body_ms median (ms): 3649.976
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 86.22%
- task_start_delay_ms median across MSM calls (ms): 1752.506
- elapsed_ms median across MSM calls (ms): 268.78
- submit_elapsed_ms median across MSM calls (ms): 0.02
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 1
- Maximum estimated bucket payload for observed concurrency (bytes): 1179360

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_pairs.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 5edfed53ac9d8c3d4313aa85e0bcbf8096bf6dba35f43c4f3825c5b7a257c8f1
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792226856723.csv
- Stage CSV SHA-256: e503a134b60f7f987f0a1fbd83a8394614e9143e21c828531ee1206fff173d74
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792226856723.csv
- MSM call CSV SHA-256: a53b8110d4f70566b5e63569ea024c1ccda504ee125e3772766635eac116a3c3
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792226856723.csv
- Per-run ratio summary CSV SHA-256: 1f662c46b58684936a53bd90cb659ad89513cd910a4e5972bb6cb6043e37b1ba
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792226856723.csv
- MSM inner-stage CSV SHA-256: c020c2004da206740255d259446c2b498b622aff4ce17b868edcf04c2d956180
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792226856723.csv
- MSM inner-stage per-query summary CSV SHA-256: 10d5421199351572c652033bbc819ad43debe04d9551464b03ab3f7367fe903f
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261017_164709_461.stdout.log
- Prover stdout SHA-256: 4f98af9af0c363ae57492e99f60e415c811b69a13830eb2668340c8c3d2c1438
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261017_164709_461.stderr.log
- Prover stderr SHA-256: b454f5aa7262cc5f4e121fbf7f2397107f53fb3d07a51e75afd71951db19b597
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164709_461.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164709_461.stderr.log
- Build stderr SHA-256: b65d97c967cb13bb2fd061b2f5b86011ef366acea387375a92a9808f93395384

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