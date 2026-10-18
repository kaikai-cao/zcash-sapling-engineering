# Cross-configuration reproduction and CI status — 2026-10-18

Status: **done** for everything runnable in this environment; **open** for
true cross-hardware (different physical machine / OS) reproduction.

This document records what was verified on 2026-10-18 after the campaign PR
(#2) was merged into `main` (merge commit `765dc8b`). It complements
[`sapling_independent_reproduction_20261018.md`](sapling_independent_reproduction_20261018.md)
(same-host clean-checkout reproduction) and [`docs/reproduction.md`](../../docs/reproduction.md)
§4. All claims below are about the **parameter-free** layer: correctness gates,
library tests and builds. No real-proof timing number is re-stated here.

## 1. Why this document exists

The external review asked for automated reproduction and flagged cross-hardware
reproduction as open. Two things happened on 2026-10-18:

1. The parameter-free CI (`.github/workflows/ci.yml`) ran for the first time on
   the merged `main` and passed all five jobs on GitHub's Ubuntu runners.
2. On the Windows measurement host, the same checks were re-run locally, and the
   FFT gate digests were compared across three instruction-set builds.

A genuine different-machine reproduction is not possible from this environment
(the automation host *is* the measurement host); §5 records what was attempted
and what remains open.

## 2. GitHub CI on the merged main (Ubuntu runners)

Run: <https://github.com/kaikai-cao/zcash-sapling-engineering/actions/runs/39115163051>
(head `765dc8b`, event `push`, triggered by the PR #2 merge).

| Job | Result |
|---|---|
| fmt + clippy (study crate, `-D warnings`) | success |
| vendored crates compile (bellman, groth16) | success |
| library tests (bellman + groth16) | success |
| experiment binaries build (release) | success |
| deterministic correctness gates (no params needed) | success |

Gate evidence from the job log: `FFT path gate: 12 digests identical across all
switch states`, `correctness=cross_recoding c=13 ok`, `MSM_WINDOW_BENCH=DONE`.
The same workflow had already passed on the PR branch head `f28f379` before the
merge, so the gates were green on both sides of the merge.

As part of this work, the FFT gate step now **prints the digest set** to the CI
log (`.github/workflows/ci.yml`), so future runs on any platform can be compared
bit-for-bit from logs alone — no artifact download needed.

## 3. Local CI-equivalent run on the Windows measurement host

Same commands as the CI jobs, executed 2026-10-18 on the measurement host
(Windows 11, i7-14700, 32 GB, cargo/rustc 1.98.1), total wall time 3 min 52 s:

| Check | Result |
|---|---|
| `cargo fmt --check` (prover-smoke) | pass |
| `cargo clippy --locked --all-targets -- -D warnings` | pass |
| `cargo check` vendor/bellman, vendor/groth16 | pass |
| `cargo test --lib --tests` bellman | **49 passed, 0 failed** |
| `cargo test --lib --tests` groth16 | **4 + 3 passed, 0 failed** |
| `cargo build --release` prover-smoke | pass |
| FFT path gate (unset / `SAPLING_FFT_SERIAL_SINGLE_THREAD=0` / `SAPLING_MSM_LAZY_RECODING=0`) | 12 digests, all three states identical |
| MSM gate (`N=16384 C=13 REPS=1`, `RAYON_NUM_THREADS=1`) | `cross_recoding c=13 ok`, `lazy_equals_materialised c=2..20 ok`, `DONE` |

This matches the Ubuntu CI job-for-job, so the parameter-free layer is verified
on **two operating systems** (Windows and Linux) and two toolchain installations.

## 4. Cross-instruction-set digest identity (same host, three codegen baselines)

The FFT gate was built three times from the same commit with different
`RUSTFLAGS` and run under `RAYON_NUM_THREADS=1`:

| Build | `RUSTFLAGS` | Result |
|---|---|---|
| baseline | (none; rustc default `x86-64`, SSE2) | 12 digests |
| v2 | `-C target-cpu=x86-64-v2` (SSE4.2/POPCNT) | 12 digests, **identical** |
| native | `-C target-cpu=native` (i7-14700, AVX-512 available) | 12 digests, **identical** |

Digest set (identical in all three builds; also the set CI now prints):

```text
blake2b=70ee3dbf9458688b20bdcca2c7d505aae422dbba7683569f0a1c63b52d437b5c
blake2b=8caab5a0dfbde53a74465746c77523847ca4daec671ec1f730900746cdc87863
blake2b=b64507661c3b3f6409febd7d6ae745d50adf1da57b38797191c22da8e761aa3a
blake2b=9984f6756076a5e6f59c376853e44d2fbb2eefe050798c3ff9cfe16b76de13df
blake2b=ac022461e2bf2315f1ec2ff70b0ed91d7f02e6a9449425326a6f67892195dd96
blake2b=c42af96658fd6219076c9d5fea8b9db61ab6d713e40b9341cfed8b555ff06a0f
blake2b=f47aa51ffcb3aa87dbd28cb3f6b1d5d66afd05b7775cab88967e9957e94b17f2
blake2b=705022865f0621cba52c803c2d8daf391ffe97db96d7400858e267e0641425e4
blake2b=0de8391dd735ce54595151d558f5baccfb8de15e306218adbad9a3720a3c89d8
blake2b=ee98ba06f3f490c81c05fcc40aa6d2c95fea86c2c831b320209cdb949659dc00
blake2b=0a4d29a7d8fed2ee6b67be2b1c6d4761e04a1369129fa78139328264a0c03295
blake2b=915222caacf23604750f77ae78cd90d32e47bb02d2654993023d6835c087b2a1
```

Interpretation: the FFT-path equivalence that target f/g rely on is **not an
artifact of the local CPU's SIMD width or of any particular codegen baseline**.
Digest identity holds from SSE2-only through AVX-512-capable builds.

### 4.1 Cross-OS digest comparison (first log-based, 2026-10-18)

The digest-printing CI change took effect on the next push: CI run
[39116177753](https://github.com/kaikai-cao/zcash-sapling-engineering/actions/runs/39116177753)
(PR #3 head `12e6897`, Ubuntu runners, rustc stable) printed the digest set to
the job log. Those 12 digests are **bit-identical to the Windows local capture
above, in the same order** — verified by direct file comparison of the log
extraction against the local `gate_default.txt`.

The certified digest set is therefore now verified identical across:

- three instruction-set baselines on Windows (§4), and
- two operating systems and two toolchains (Windows 11 + rustc 1.98.1 vs
  Ubuntu + GitHub stable rustc).

Digest identity is a *correctness* property (pure field arithmetic hashed with
BLAKE2b), so it is expected to hold everywhere; what this adds is the empirical
cross-platform confirmation with actual hex values, which the previous
within-run-only assertion could not provide.

## 5. MSM gate thread-count insensitivity

CI runs the MSM gate with `RAYON_NUM_THREADS=1`; it was additionally run on the
measurement host with the default thread pool (all 20 logical processors):
`correctness=cross_recoding c=13 ok` and `MSM_WINDOW_BENCH=DONE` in both cases.
The cross-recoding and lazy/materialised equalities are thread-count
independent, as expected for value checks (they are not timing checks).

## 6. WSL cross-OS attempt — blocked by environment policy

A Windows-Subsystem-for-Linux run was attempted to obtain a Linux data point
from this host. The automation environment's command security policy blocks
`wsl.exe` (Program Blacklist), and the block cannot be approved or bypassed
from the agent side. No workaround was attempted. The OS difference is instead
covered by the GitHub CI Ubuntu runners (§2), which is a *stronger* data point
than WSL would have been (clean container, stable toolchain, no host noise).

## 7. What remains open

- **True cross-hardware reproduction** (different CPU microarchitecture and/or
  different physical machine): still open. The checklist in
  [`docs/reproduction.md`](../../docs/reproduction.md) §4 is unchanged — run the
  parameter-free gates everywhere, plus the memory ledger where parameter files
  are available, and compare digests (must be identical), prove peak (expect
  identical byte counts) and timings (like-for-like only).
- The digest-printing CI change is live and its first run (39116177753, PR #3
  head) confirmed the cross-OS digest identity in §4.1. Future platform runs
  can be compared from logs alone using the same extraction
  (`grep -o 'blake2b=[0-9a-f]\{64\}'` on the job log).
