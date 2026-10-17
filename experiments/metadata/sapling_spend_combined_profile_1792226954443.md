# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792226954443
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=1; SAPLING_PROFILE=1
- Run data label: fallback_ablation_pairs
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: disabled
- Force async worker: True
- Processor affinity mask: 1
- Worker fallback records: 0
- Forced-async override records: 15
- Run start: 2026-10-17T16:48:49.0074230+08:00
- Run end: 2026-10-17T16:49:33.0993363+08:00
- Repository branch: experiment/fallback-ablation-20261016
- Engineering repository HEAD at start: b1beca2278adf588add976b1e14355ab8efa1ba5
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M experiments/metadata/sapling_runtime_memory_measurements_20261016.md;  M scripts/run_spend_combined_profile.ps1;  M vendor/bellman/src/lib.rs;  M vendor/bellman/src/multiexp.rs; ?? docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md; ?? experiments/metadata/sapling_prove_memory_ledger_20261017.md; ?? experiments/metadata/sapling_spend_combined_profile_1792226856723.md; ?? experiments/metadata/sapling_spend_combined_profile_1792226906343.md; ?? experiments/prover-smoke/src/bin/exponent_conversion_memory.rs; ?? experiments/prover-smoke/src/bin/prove_memory_ledger.rs; ?? experiments/raw/csv/sapling_prove_memory_ledger.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792226856723.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792226906343.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792226856723.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792226906343.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792226856723.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792226906343.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792226856723.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792226906343.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_affinity_probe.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_pairs.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_pairs_buggy_launcher.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792226856723.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792226906343.csv; ?? experiments/raw/logs/affinity_probe_lp0_20261017_163939.stderr.log; ?? experiments/raw/logs/affinity_probe_lp0_20261017_163939.stdout.log; ?? experiments/raw/logs/affinity_probe_lp20_20261017_164043.stderr.log; ?? experiments/raw/logs/affinity_probe_lp20_20261017_164043.stdout.log; ?? experiments/raw/logs/sapling_exponent_conversion_memory_20261017_163226.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_1t_20261017_162747.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_1t_20261017_162747.memprobe.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_8t_20261017_163006.log; ?? experiments/raw/logs/sapling_prove_memory_ledger_spend_8t_20261017_163006.memprobe.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164257_086.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164257_086.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164347_348.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164347_348.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164434_969.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164434_969.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164521_514.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164521_514.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164709_461.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164709_461.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164759_701.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261017_164759_701.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164257_086.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164257_086.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164347_348.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164347_348.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164434_969.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164434_969.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164521_514.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164521_514.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164709_461.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164709_461.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164759_701.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164759_701.stdout.log; ?? vendor/bellman/src/mem_probe.rs
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

- Outer Prove median (ms): 3729.608
- create_proof_body_ms median (ms): 3729.551
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 86.02%
- task_start_delay_ms median across MSM calls (ms): 2206.167
- elapsed_ms median across MSM calls (ms): 268.308
- submit_elapsed_ms median across MSM calls (ms): 0.023
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
- Prover run CSV SHA-256: 350e646693d92f049c048caf1708e850e4dd9d31ce392ad77e49df32df6b7de7
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792226954443.csv
- Stage CSV SHA-256: eb6489ff01741c0f84585766232c4100b2cc575917be96d6c432c79e8a30ccca
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792226954443.csv
- MSM call CSV SHA-256: aab9a4947522a88395f2844eca354f41a4d4229c82deab331355514976e11bfc
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792226954443.csv
- Per-run ratio summary CSV SHA-256: c36af85a60947318ef22f48815e3d4c18148f94c8e7ea8277144e298e3bb14c6
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792226954443.csv
- MSM inner-stage CSV SHA-256: 12b705a90e8aa40e582462e3d6d6a76557abbb5fdb5b2e4851d46f0766598fc7
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792226954443.csv
- MSM inner-stage per-query summary CSV SHA-256: 8e4e0efb6e5714b25b94b46668c8da974adafcb8467f672fc6f62abd8319f29e
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261017_164847_803.stdout.log
- Prover stdout SHA-256: 4f945a5b301d152f28ddaf7197941df3056721f94ceb1ea048dbe66a575f73fe
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261017_164847_803.stderr.log
- Prover stderr SHA-256: 1b292a3f258ec42812bad8ed7d7a809570c6dce87eb288818a01d891e0ad133c
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164847_803.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261017_164847_803.stderr.log
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