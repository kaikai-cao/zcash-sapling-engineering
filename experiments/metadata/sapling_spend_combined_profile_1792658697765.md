# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792658697765
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=8; SAPLING_PROFILE=1
- Run data label: msm_scaling_20261022_spend_t8_ffff
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 65535
- Processor affinity readback: 0xFFFF
- Worker fallback records: 0
- Forced-async override records: 0
- Run start: 2026-10-22T16:44:31.9130002+08:00
- Run end: 2026-10-22T16:45:01.4918073+08:00
- Repository branch: analysis/msm-scaling-stage0
- Engineering repository HEAD at start: 547c943fec7a01143ecded6d14f49202418f7da5
- Engineering worktree dirty at start: False
- Engineering worktree status at start: clean
- Engineering worktree status details: none
- Untracked output files ignored for cleanliness: True (count: 204)
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

- Outer Prove median (ms): 725.515
- create_proof_body_ms median (ms): 725.422
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 433.96%
- task_start_delay_ms median across MSM calls (ms): 0.104
- elapsed_ms median across MSM calls (ms): 472.307
- submit_elapsed_ms median across MSM calls (ms): 0.037
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
- Prover run CSV SHA-256: f005e59d6d961a8e3333a4e308020b86ac444dec639ee27771c81eb5c0314d1f
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792658697765.csv
- Stage CSV SHA-256: 6dac1b38d393e3d703bfd3bcdfeb9892b0894becf1303ce883d46b5b5be61a01
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792658697765.csv
- MSM call CSV SHA-256: 87740b4561488cee6e8622e71b4c316d1953ffb138cdea96d255fb19e24181b1
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792658697765.csv
- Per-run ratio summary CSV SHA-256: b4c5f26dc940b6ba3257026b454f97f3c9256c6718928924fbf2e77d16936e80
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792658697765.csv
- MSM inner-stage CSV SHA-256: 62ded9b3aff52aae8a18bc00002aa4c07c85a9ef54f74add0b992cf14e4a3c32
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792658697765.csv
- MSM inner-stage per-query summary CSV SHA-256: db03a749ad797ee4bd82292c6b7ade521027127cc50396b1fb27b2ec424d2507
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_164426_300.stdout.log
- Prover stdout SHA-256: f0162c3516fe004a0ef32fe7df547bdfe52b4ac65c85d000428de177b3e077a6
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_164426_300.stderr.log
- Prover stderr SHA-256: 1142ed7b83c641b7604eb04d4cc6b85ec8932e46a01df7a159f116c7773817c9
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_164426_300.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_164426_300.stderr.log
- Build stderr SHA-256: 84d0a460c3d6fe7d2f17c2b5e56d5cc6aaaf214bbb3bfb4c923505e8ee538bc8

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