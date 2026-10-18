# Experiment Index — research entry points

> One table per research thread: where the conclusion lives, where the raw
> evidence lives, and what the current verdict is. Generated 2026-10-18 for the
> closed optimization campaign (targets a–g) and the measurement programme.
>
> **File classes in this repository** — do not merge these roles:
>
> | Class | Location | Rule |
> |---|---|---|
> | Raw measurements | `experiments/raw/csv/`, `experiments/raw/logs/` | Never overwritten, never edited. One batch = one ID; provenance headers record binary hashes, parameter hashes, switch state and affinity. Failed or superseded batches stay — they are part of traceability. |
> | Derived tables | `results/tables/` | Rebuilt by the analysis scripts in `scripts/`. Regenerating must reproduce the committed file byte-for-byte (the analyzers refuse to overwrite unless identical). |
> | Reports & protocol | `experiments/metadata/`, `docs/` | Interpretation. Pre-registrations are frozen **before** their measurements; results documents cite the frozen thresholds. |

## Campaign targets (pre-registered protocol)

Protocol: [`sapling_optimization_validation_protocol_20261017.md`](sapling_optimization_validation_protocol_20261017.md).

| Target | Pre-registration | Results | Raw data entry | Verdict |
|---|---|---|---|---|
| e — thread count / affinity configuration | `sapling_default_config_experiment_preregistration_20261017.md` | `sapling_default_config_experiment_results_20261017.md` | `experiments/raw/csv/sapling_{spend,output}_prover_runs_default_config_*` | partly certified: P-core pinning for setup (1.8–1.9×); thread reduction regresses Output 21.8% |
| b — balanced-signed window recoding | `sapling_msm_signed_digit_preregistration_20261017.md` | `sapling_msm_signed_digit_results_20261017.md` | `experiments/raw/csv/sapling_*_signed_digit_*`, `results/tables/sapling_msm_signed_digit_{abba,stage_profile}_20261017.csv` | **certified** (Spend 1t −6.63%, Output 1t −11.35%, peak −2.00 MB); default `SAPLING_MSM_SIGNED_DIGITS=1` |
| a — de-materialised H-query windowed exponents | `sapling_msm_lazy_recoding_preregistration_20261018.md` | `sapling_msm_lazy_recoding_results_20261018.md` | `experiments/raw/csv/sapling_prove_memory_ledger_lazy_*`, `results/tables/sapling_msm_lazy_recoding_{memory,abba}_20261018.csv` | **failed frozen ≥15 MB threshold** (12.93 MB) → archived by the frozen rule |
| f — single-thread FFT four-step scratch removal | `sapling_qap_fft_scratch_preregistration_20261018.md` | `sapling_qap_fft_scratch_results_20261018.md` | `experiments/raw/csv/sapling_prove_memory_ledger_qap_fft_fix_*`, `results/tables/sapling_qap_fft_fix_{memory,abba,phase_peak}_20261018.csv`, `experiments/raw/logs/fft_path_gate_*` | **certified** (lazy=1 peak −3,945,720 B = exactly the convertible maximum) |
| g — combination + default flip | `sapling_combo_default_preregistration_20261018.md` | `sapling_combo_default_results_20261018.md` | `experiments/raw/csv/sapling_*_combo_default_*`, `results/tables/sapling_combo_default_{memory,abba}_20261018.csv` | **certified; defaults flipped to `1`** (`SAPLING_MSM_LAZY_RECODING`, `SAPLING_FFT_SERIAL_SINGLE_THREAD`); shipped-default peak 103.06 → 86.18 MB (−16.38%) |
| closure — memory floor | (reconnaissance, no threshold) | `sapling_default_stage_decomposition_20261018.md` | `experiments/raw/csv/sapling_prove_memory_ledger_{default_phase_probe,synth_capacity}_20261018.csv` | structural floor: peak owned by `circuit_synthesis`; convertible maximum 3,314,512 B unreachable |
| closure — time floor | (reconnaissance, no threshold) | `sapling_default_time_profile_20261018.md` | `experiments/raw/logs/sapling_spend_msm_{stage,branch}_recon_20261018.log` | arithmetic floor: MSM ≈85% of prove; fill 462 ns/nonzero digit; window c=13 optimal |

## Measurement programme threads

| Thread | Primary documents | Raw data entry | Current conclusion |
|---|---|---|---|
| Formal baseline & parameter validation | `docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md` §1–§10; `sapling_measurement_campaign_closure_20261011.md` | `experiments/raw/csv/sapling_{spend,output}_prover_runs_release.csv` (v1 tag) | Spend prove median 3,385.7 ms / Output 514.9 ms (fastest recorded batches); pinned baseline Spend 3,685.6 ms / Output 558.5 ms |
| Source-level stage & MSM profiling | `sapling_spend_stage_research_summary.md`, `sapling_spend_msm_operation_accounting_1792134295649.md`, `sapling_spend_msm_branch_accounting_1792135474677.md` | `experiments/raw/csv/sapling_spend_msm_*_1792134*`, `experiments/raw/logs/sapling_spend_msm_stage_recon_20261018.log` | MSM dominates prove; fill is arithmetic-bound (~462 ns per nonzero digit, same-batch) |
| Worker fallback investigation | `sapling_spend_worker_fallback_ablation_conclusion_20261017.md` | `experiments/raw/csv/sapling_spend_prover_runs_fallback_*` | timing-attribution / scheduling effect, not a throughput bottleneck (+1.1%, p≈0.11) |
| Thread scaling & CPU affinity | `sapling_pinned_baseline_and_thread_scaling_20261017.md`, `sapling_baseline_core_regime_restatement_20261017.md` | `experiments/raw/csv/sapling_*_prover_runs_release.csv`, `results/tables/sapling_baseline_core_regime_*_20261017.csv` | single-thread bimodal by core placement (up to 2.6×); pinning required; scaling saturates at 8 threads |
| Memory ledger & phase decomposition | `sapling_prove_memory_ledger_20261017.md`, `sapling_runtime_memory_measurements_20261016.md`, `sapling_default_stage_decomposition_20261018.md` | `experiments/raw/csv/sapling_prove_memory_ledger_*` | peak 86.18 MB post-flip, owned by `circuit_synthesis`; structural floor |
| Branch counters × inner-stage join | `sapling_spend_msm_branch_stage_analysis_20261018.md` | `experiments/raw/csv/sapling_spend_msm_{branch,inner_stage}_*`, `results/tables/sapling_spend_msm_branch_stage_join_*.csv` | H/L fill gap explained by exponent distributions; G2 ≈ 2.6× G1 per-digit cost |
| Provenance & data integrity | `sapling_experiment_provenance_audit_20261011_151156.md`, `sapling_provenance_audit_closure_20261011.md` | `experiments/metadata/*.csv` (audit manifests) | source identity, dependency revision, parameter hashes recorded per batch |
| Reproduction & CI verification | `sapling_independent_reproduction_20261018.md`, `sapling_cross_config_reproduction_20261018.md`, [`docs/reproduction.md`](../../docs/reproduction.md) | `experiments/raw/{csv,logs}/repro_independent_*` | parameter-free layer green on Windows (local CI-equivalent) and Ubuntu (GitHub CI, merged `main`); FFT digests identical across three instruction-set builds; real-proof cross-host reproduction still open |

## Reproducing

- **Parameter-free checks (CI):** `.github/workflows/ci.yml` — fmt/clippy on the study crate, vendored-crate compile + library tests, release build, and the two deterministic gates (FFT path digests across switch states; MSM signed/unsigned + lazy/materialised equality). Status 2026-10-18: green on the merged `main` (Ubuntu runners) and re-verified locally on Windows; the gates job prints the certified digest set for cross-platform comparison.
- **Real-proof reproduction (needs ~51 MB Sapling parameter files, not in-repo):** [`docs/reproduction.md`](../../docs/reproduction.md).
- **Analysis scripts:** `scripts/analyze_*.py` (per-target statistics, byte-identical to the committed derived tables) and `scripts/run_*.ps1` (campaign drivers). `scripts/README.md` records which scripts are historical one-offs.

*This index is a finding aid, not a conclusion source; each row's verdict is authoritative only in its linked results document.*
