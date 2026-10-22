# Sapling Spend Combined Stage / MSM Diagnostic Profile

- Circuit: Sapling Spend
- Batch ID: 1792657138688
- Runs: 5; verified proofs: 5/5; build: Release; RAYON_NUM_THREADS=1; SAPLING_PROFILE=1
- Run data label: msm_scaling_smoke3_20261022
- Branch counters: disabled
- Fine-grained MSM inner-stage timing: enabled
- Force async worker: False
- Processor affinity mask: 1
- Processor affinity readback: 0x1
- Worker fallback records: 5
- Forced-async override records: 0
- Run start: 2026-10-22T16:18:31.5131276+08:00
- Run end: 2026-10-22T16:19:16.6524114+08:00
- Repository branch: analysis/msm-scaling-stage0
- Engineering repository HEAD at start: 489134a87fb3a8024f616f0fcb0e848fe7327025
- Engineering worktree dirty at start: True
- Engineering worktree status at start: dirty
- Engineering worktree status details: M scripts/run_pinned_prover_campaign.ps1;  M scripts/run_spend_combined_profile.ps1; ?? scripts/analyze_msm_scaling_diagnosis.py; ?? scripts/run_msm_scaling_campaign.ps1; ?? scripts/run_tx_scaling_campaign.ps1
- Untracked output files ignored for cleanliness: True (count: 10)
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

- Outer Prove median (ms): 3549.139
- create_proof_body_ms median (ms): 3549.044
- Per-run ratio sum(MSM elapsed_ms) / create_proof_body_ms median: 85.86%
- task_start_delay_ms median across MSM calls (ms): 1732.206
- elapsed_ms median across MSM calls (ms): 255.62
- submit_elapsed_ms median across MSM calls (ms): 0.025
- MSM inner-stage records: 40 / 40
- Per-query MSM inner-stage summary rows: 8 / 8
- Maximum observed concurrent chunk regions within one MSM call: 1
- Maximum estimated bucket payload for observed concurrency (bytes): 1179648

The inner-stage timing fields distinguish cumulative per-chunk work from wall-clock time. Bucket payload figures are analytical estimates based on active chunk-region instrumentation, not process peak memory.

The three existing MSM timing fields describe different measurement intervals. In particular, submit_elapsed_ms is not an additional disjoint work segment that can be summed with task_start_delay_ms and elapsed_ms. Worker fallback may execute queued work while a submit call is in progress. Treat these values as diagnostic timing fields, not as a mutually exclusive cost decomposition.

The fallback ablation uses the same instrumented source for both conditions. Set -BranchCounters disabled for paired runs so per-slot counter increments do not contaminate the timing comparison. -ForceAsyncWorker suppresses synchronous fallback only when the normal fallback threshold would otherwise be crossed; override records confirm when that intervention was exercised.

The share above is computed per run and then summarized; it is not computed by dividing separately calculated medians. This diagnostic batch is not the frozen formal performance baseline and should not be combined with historical profiling batches.

## Artifacts

- Prover run records: experiments/raw/csv/sapling_spend_prover_runs_msm_scaling_smoke3_20261022.csv (filtered by this batch ID)
- Prover run CSV SHA-256: 7a0f65cd738cf9ad9cbb27271abd19e79f231e7557f071545e5a8939662b0e83
- Stage CSV: experiments/raw/csv/sapling_spend_stage_profile_1792657138688.csv
- Stage CSV SHA-256: 20a746dae372b23693711fb2dbbb0ac1a6bac5e10e1356e82def4de882a9704e
- MSM call CSV (includes submit timing): experiments/raw/csv/sapling_spend_msm_call_profile_1792657138688.csv
- MSM call CSV SHA-256: d152aa67797fc778cf0ec072942742eef2d2d8de50e78cf5d44ae217d3ee2c8f
- Per-run ratio summary CSV: experiments/raw/csv/sapling_spend_profile_run_summary_1792657138688.csv
- Per-run ratio summary CSV SHA-256: f8b38fae864a0c6ea3b89c88c9f13531f04470162cf11983e28422db64b80f3a
- MSM inner-stage CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_profile_1792657138688.csv
- MSM inner-stage CSV SHA-256: ab35eccd87234800a6cea4a6acb59c2488c899e7c89464289efdd49cf8cdd0e1
- MSM inner-stage per-query summary CSV: experiments/raw/csv/sapling_spend_msm_inner_stage_summary_1792657138688.csv
- MSM inner-stage per-query summary CSV SHA-256: c74406c40091ab975c455801e023c8d51518b358ecc749efdcf7b0a7931c5ed5
- Prover stdout: experiments/raw/logs/sapling_spend_combined_profile_20261022_161830_273.stdout.log
- Prover stdout SHA-256: 0e58d662925d2256772b892843d6a6db82455012e320c956a1ef54aa52a2ed6f
- Prover stderr / source instrumentation records: experiments/raw/logs/sapling_spend_combined_profile_20261022_161830_273.stderr.log
- Prover stderr SHA-256: 9b65d1058e382fea77d54ed707a3ffe2ced79bd4193b5a9a377d1963f3a41e23
- Build stdout: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_161830_273.stdout.log
- Build stdout SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Build stderr: experiments/raw/logs/sapling_spend_combined_profile_build_20261022_161830_273.stderr.log
- Build stderr SHA-256: c663462ee6e8bd687c13f4f43386d516f3f0bb8fc1cb3522d98b83bf3664d8fd

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