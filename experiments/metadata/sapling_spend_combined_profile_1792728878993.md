# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792728878993
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: synth_probe_clean_off
- Branch counters: enabled
- Fine-grained MSM inner-stage timing: enabled
- Explicit MSM window override: default
- Explicit MSM window minimum exponent count: 0
- Force async worker: False
- Processor affinity mask: 21845
- Processor affinity readback: 0x5555
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-23T12:14:14.5152931+08:00
- Run end: 2026-10-23T12:14:42.1999475+08:00
- Repository branch: stage6/synth-scoping
- Engineering repository HEAD at start: b133e3cca519f6e03ed50938bd806d290524b8a9
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: ?? experiments/metadata/sapling_spend_combined_profile_1792728644973.md; ?? experiments/metadata/sapling_spend_combined_profile_1792728729019.md; ?? experiments/metadata/sapling_spend_combined_profile_1792728844494.md; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792728644973.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792728729019.csv; ?? experiments/raw/csv/sapling_spend_msm_call_profile_1792728844494.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792728644973.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792728729019.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792728844494.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792728644973.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792728729019.csv; ?? experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792728844494.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792728644973.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792728729019.csv; ?? experiments/raw/csv/sapling_spend_profile_run_summary_1792728844494.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_synth_probe.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_synth_probe_clean.csv; ?? experiments/raw/csv/sapling_spend_prover_runs_synth_probe_off.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792728644973.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792728729019.csv; ?? experiments/raw/csv/sapling_spend_stage_profile_1792728844494.csv; ?? experiments/raw/logs/sapling_spend_combined_profile_20261023_121019_094.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261023_121019_094.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261023_121143_148.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261023_121143_148.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261023_121334_581.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_20261023_121334_581.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121019_094.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121019_094.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121143_148.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121143_148.stdout.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121334_581.stderr.log; ?? experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121334_581.stdout.log
- Untracked output files ignored for cleanliness: False (count: 0)
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

- vendor/bellman/src/multiexp.rs SHA-256: 3a80dda3fc2aaf5b259d052d4cb303a04c83719095fa9d663c0e208ea02569c4
- vendor/bellman/src/multicore.rs SHA-256: fb951f477ae04ea7e2141a24035f2a5d9114458831d56784e5a2b94eec178dd0
- vendor/groth16/src/prover.rs SHA-256: 7f7d3305f529616e4c8e911bf03fd2f7aa4818a5dc2d4055bbadd3f95a2cfae5
- spend_prover_smoke.rs SHA-256: 58859dec0a6872dd4aaa0400922dae737eceb2b7f99fa0e7574a117ec7e22f10
- Runner SHA-256: 816bcd22f68a2b8aaa572a40e0a25d8b10a9b4548ecd5cf577ce0020e28b37ec
- Cargo manifest SHA-256: 8d6837c405f6192840cd334d1ce345e4762a7ea0ff88397b2b73a66b3bff4d77

## Result summary

- Outer Prove median (ms): 643.147
- create_proof_body_ms median (ms): 643.08
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 413.29%
- task_start_delay_ms median across MSM calls (ms): 0.067
- elapsed_ms median across MSM calls (ms): 401.22
- submit_elapsed_ms median across MSM calls (ms): 0.016
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 8
- Maximum estimated bucket payload for observed concurrency (bytes): 5898240

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_synth_probe_clean_off.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 6bf68eec8a904fa8340a06909ba32ecaaec136892022aeac2290d1bb766ece44
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792728878993.csv
- Stage CSV SHA-256: 53e5d62cbdaf9f9489abb1cdfa0effd79c7c9233bc884155a424ed2f34c349d5
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792728878993.csv
- MSM call CSV SHA-256: 9af506bc09651774abd80330baa3a85c6a67c999d9f807c8393d09ef1a0030d9
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792728878993.csv
- Per-run ratio summary CSV SHA-256: 34c0be6a0c34dd8fdaf5a3ae537867c36e49b8a34f3c61e2ff69a9af6ed0cb2e
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792728878993.csv
- MSM inner-stage CSV SHA-256: a5ec8b45f2a5fbc49857993880419e1ae1443135ea6c3fc0ac5cd3f560ac3405
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792728878993.csv
- MSM inner-stage per-query summary CSV SHA-256: c9eae87f5c23081e71c1f56acc6d9e31d6e85dc5ecad1bc9bdfc6c03a93b24f7
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261023_121413_335.stdout.log
- Prover stdout SHA-256: 2d20ff72110afd863c8c4e99e27ed991d3f47481016f3051198e071a8ecca1c2
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261023_121413_335.stderr.log
- Prover stderr SHA-256: cacfa0c13338c8a31dce1a7997f2b90891c26f28b8e007d9912ab3d848c876ac
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121413_335.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261023_121413_335.stderr.log
- Build stderr SHA-256: 85c8dbac64ed6a362d668bf3988686e26e947620bb15cfdbe2e999a0ff8261b2

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