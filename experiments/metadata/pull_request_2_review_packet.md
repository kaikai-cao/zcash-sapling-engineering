# Pull Request #2 — suggested title and body

> Purpose of this file: PR #2 is currently titled "update test" with an empty body. This
> packet holds the suggested replacement so the edit is reviewable in-repo and versioned.
> Applying it is a manual GitHub UI step (no CLI token available in the automation
> environment): open https://github.com/kaikai-cao/zcash-sapling-engineering/pull/2 →
> "Edit" → paste the title and body below.

## Suggested title

```
Complete Sapling proving optimization campaign and certify combined defaults
```

## Suggested body

```markdown
## What this PR does

Completes the pre-registered Sapling proving optimization campaign (targets a–g,
protocol: experiments/metadata/sapling_optimization_validation_protocol_20261017.md)
and certifies the resulting combined configuration as the shipped default.

Headline result: with both switches at their new defaults
(`SAPLING_MSM_LAZY_RECODING=1`, `SAPLING_FFT_SERIAL_SINGLE_THREAD=1`), the Spend
prove peak drops **103,063,495 → 86,184,607 B (−16,878,888 B, −16.38%)** with 100%
correctness and no time regression on any measured arm set.

## Why the diff is large

This PR merges the whole research archive: raw measurements (CSV/logs), derived
tables, analysis scripts, instrumented vendored sources, and documentation. The raw
data is intentionally preserved — it is the reproducibility evidence for every claim.
Nothing was deleted to shrink the diff. Review entry points, in suggested order:

1. experiments/metadata/INDEX.md — one table mapping every campaign target to its
   results document, raw-data entry, and current verdict
2. experiments/metadata/sapling_combo_default_results_20261018.md — target g verdict
   (primary acceptance)
3. experiments/metadata/sapling_qap_fft_scratch_results_20261018.md — target f verdict
4. README.md §7 and §16–§18 — consolidated status (historical sections preserved)
5. Code changes (the actual merge-relevant diff):
   - vendor/bellman/src/multiexp.rs — signed-digit recoding default (target b),
     lazy-recoding default flipped 0→1 (target g)
   - vendor/bellman/src/domain.rs — single-thread serial-FFT switch, default 0→1
     (target g); four-step path retained for log_cpus ≥ 1
   - vendor/groth16/src/prover.rs — default-off phase/capacity probes (diagnostics)

## Campaign outcomes (all verdicts per frozen pre-registered tables)

| Target | Kind | Result | Verdict |
|---|---|---|---|
| b — balanced-signed window recoding | algorithm | Spend 1t −6.63%, Output 1t −11.35%, peak −2.00 MB | certified, default 1 |
| e — thread/affinity configuration | configuration | setup 1.8–1.9× faster pinned; thread cut regresses Output 21.8% | partly certified (pinning) |
| a — de-materialised H-query windowed exponents | memory | buffer 24.1 MB→0.33 MB, all arms faster, peak −12.93 MB < frozen 15 MB | **failed frozen rule → archived** |
| f — single-thread FFT scratch removal | memory | lazy=1 peak −3,945,720 B = exactly the convertible maximum | certified |
| g — combination + default flip | memory | shipped-default peak −16.38%, correctness 100%, no time regression | **certified, defaults flipped** |
| closure reconnaissance | — | memory at structural floor, time at arithmetic floor (this pipeline) | recorded |

Target a's failure is kept in the record deliberately: it missed its pre-declared
≥15 MB threshold (12.93 MB) and was archived by the frozen rule, and its phase probe
is what made targets f/g's thresholds computable.

## Default flip and rollback

Both switch defaults are now `1`. Each environment variable still overrides the
default in either direction:

- `SAPLING_MSM_SIGNED_DIGITS=0` — restores unsigned recoding bit-for-bit (target b)
- `SAPLING_MSM_LAZY_RECODING=0` — restores materialised windowed exponents (target a path)
- `SAPLING_FFT_SERIAL_SINGLE_THREAD=0` — forces the four-step parallel FFT path

Post-flip re-verification with **no switches set**: FFT gate 12/12 digests identical
to the explicit four-step path; memory ledger +7 B vs the flipped arm; one Spend
batch 5/5 verified.

## Reproducing

Parameter-free checks (CI, no external files needed):

```bash
cargo test --locked --manifest-path vendor/bellman/Cargo.toml
cargo test --locked --manifest-path vendor/groth16/Cargo.toml
cargo build --release --locked --manifest-path experiments/prover-smoke/Cargo.toml
RAYON_NUM_THREADS=1 experiments/prover-smoke/target/release/fft_path_gate.exe   # compare digests across switch states
```

Real-proof reproduction needs the Sapling parameter files (not in-repo, ~51 MB):
set `ZCASH_PARAMS_DIR` and run `prove_memory_ledger.exe` / `spend_prover_smoke.exe`
with no switch variables set — the default behaviour is the certified configuration.
Full procedure: docs/reproduction.md.

## Scope boundaries

- All measurements come from one host (Windows 11, i7-14700, 32 GB). Gains are
  certified under the stated measurement conditions, not guaranteed on other
  hardware/OS.
- The floor conclusions (no further target warranted) are scoped to this pipeline
  (vendored bellman + Sapling Spend/Output) under the frozen conventions.
- Instrumented batches record their own provenance; they are not the pristine
  baseline.
```

## Notes for the maintainer

- Consider whether to keep this as one archival PR or split into
  (a) code + CI + docs and (b) raw data, with (b) depending on (a). The raw data
  should not be dropped either way.
- The branch name `experiment/fallback-ablation-20261016` predates the campaign;
  consider archiving it after merge (see weekly summary §17).
