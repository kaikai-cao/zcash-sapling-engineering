# Independent reproduction procedure

This document is the reproduction path for the certified results of the Sapling
proving optimization campaign (targets a–g). It separates **parameter-free
checks** (what CI runs on every push) from the **real-proof reproduction** (needs
the Sapling parameter files, ~51 MB, which are deliberately not in-repo).

All results certified in `experiments/metadata/sapling_*_results_2026101[78].md`
were produced under this procedure's conventions:

- Windows 11, Intel i7-14700 (8 P-cores + 12 E-cores, hybrid), 32 GB RAM
- rustc / cargo **1.98.1**
- Single-thread runs **affinity-pinned to LP0** (unpinned single-thread times are
  bimodal by core placement, up to 2.6× — see README §17)
- Switch state recorded per batch; the certified configuration has **no switch
  variables set** (both defaults are `1` since 2026-10-18)

## 0. Toolchain

```powershell
rustc --version   # expect rustc 1.98.x
cargo --version
```

## 1. Clean checkout

```powershell
# The campaign branch was merged into main on 2026-10-18 (merge commit 765dc8b);
# clone main. To reproduce a specific historical batch, check out the commit
# recorded in that batch's provenance header instead.
git clone -b main https://github.com/kaikai-cao/zcash-sapling-engineering.git
cd zcash-sapling-engineering
git log --oneline -1        # record the commit under test
git status --short          # must be empty
```

## 2. Parameter-free correctness gates (also what CI runs)

```powershell
# Build the experiment binaries (needs network for the sapling-crypto git rev)
cargo build --release --locked --manifest-path experiments/prover-smoke/Cargo.toml

# Gate A — FFT path determinism across switch states.
# The flipped default (unset) must be bit-identical to the legacy four-step path.
$env:RAYON_NUM_THREADS = '1'
$bin = "experiments\prover-smoke\target\release\fft_path_gate.exe"
& $bin | Out-File -Encoding utf8 gate_default.txt
$env:SAPLING_FFT_SERIAL_SINGLE_THREAD = '0'
& $bin | Out-File -Encoding utf8 gate_legacy.txt
Remove-Item Env:SAPLING_FFT_SERIAL_SINGLE_THREAD
# compare only the blake2b digests (the switch= label line differs by design)
(Select-String -Path gate_default.txt -Pattern 'blake2b=([0-9a-f]+)').Matches.Value |
  Sort-Object | Set-Content d_default.txt
# ... same for gate_legacy.txt, then: Compare-Object (Get-Content d_default.txt) (Get-Content d_legacy.txt)
# Expected: 12 digests, zero differences.

# Gate B — MSM recoding equality (signed vs unsigned, lazy vs materialised)
$env:MSM_WINDOW_BENCH_N = '16384'; $env:MSM_WINDOW_BENCH_C = '13'; $env:MSM_WINDOW_BENCH_REPS = '1'
experiments\prover-smoke\target\release\msm_window_bench.exe
# Expected: exit code 0, "correctness=cross_recoding c=13 ok",
#           "correctness=lazy_equals_materialised c=2..20 ok", "MSM_WINDOW_BENCH=DONE".
```

## 3. Real-proof reproduction (needs parameter files)

Obtain the Sapling parameter files and verify their hashes before use:

| File | Size (B) | SHA-256 |
|---|---:|---|
| `sapling-spend.params` | 47,958,396 | `8E48FFD23ABB3A5FD9C5589204F32D9C31285A04B78096BA40A79B75677EFC13` |
| `sapling-output.params` | 3,592,860 | `2F0EBBCBB9BB0BCFFE95A397E7EBA89C29EB4DDE6191C339DB88570E3F3FB0E4` |

```powershell
Get-FileHash -Algorithm SHA256 D:\Research\zcash-params\sapling-spend.params   # must match the table

$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'
$env:RAYON_NUM_THREADS = '1'
# No SAPLING_* switch variables set: this exercises the certified default behaviour.

# Memory ledger (certified configuration): 5 runs, expect verified=true, 192 B,
# prove peak median ~86.18 MB.
$env:SAPLING_PROVER_RUNS_CSV = "$PWD\experiments\raw\csv\<your-own-label>.csv"
$p = Start-Process experiments\prover-smoke\target\release\prove_memory_ledger.exe -PassThru
$p.ProcessorAffinity = [IntPtr]1        # LP0 pin (see conventions above)
$p.WaitForExit()

# End-to-end timing: spend_prover_smoke.exe (Spend) / sapling-output-smoke.exe (Output)
```

Reference values for the certified configuration (same host, LP0-pinned):
prove peak **86,184,607 B** median (target g arm B), Spend 1 t prove
**≈3.2–3.3 s** after the flip (was ≈3.6–3.7 s before), Output ≈0.53 s.

## 4. Cross-hardware reproduction (partly covered; physical cross-host still open)

The certified numbers come from one host. Before any external claim, repeat
§2 (always) and §3 (at least the memory ledger) on a different CPU / OS, and
compare:

- gate digests (must be identical everywhere — they are platform-independent)
- prove peak median (expect the same byte counts; they are allocation-driven,
  not timing-driven)
- prove times (will differ; only compare like-for-like configurations)

Record machine, OS, toolchain and affinity in the batch provenance headers.

### 4.1 What has been verified (status 2026-10-18)

| Layer | Where | Result |
|---|---|---|
| Same-host independent reproduction (clean checkout, fresh build, no switches set) | this host, Windows | passed — [`sapling_independent_reproduction_20261018.md`](experiments/metadata/sapling_independent_reproduction_20261018.md): prove peak 86,184,600 B vs certified 86,184,607 B (−7 B); gates identical |
| Parameter-free CI, all five jobs | GitHub Actions, Ubuntu runners, merged `main` (`765dc8b`) | [run 39115163051](https://github.com/kaikai-cao/zcash-sapling-engineering/actions/runs/39115163051) — success (also green on the PR head `f28f379`) |
| Same checks re-run locally | this host, Windows | all pass; bellman 49 + groth16 4/3 library tests green |
| FFT gate digests across three instruction-set builds (`x86-64`, `x86-64-v2`, `native`) | this host, Windows | 12/12 digests bit-identical |
| MSM gate at `RAYON_NUM_THREADS=1` vs default pool | CI (1 thread) + this host (default) | both pass |

Details: [`sapling_cross_config_reproduction_20261018.md`](experiments/metadata/sapling_cross_config_reproduction_20261018.md).
The CI gates job now prints the certified digest set to its log, so any future
platform's run can be compared bit-for-bit from the log alone.

### 4.2 What remains open

A reproduction on a **different physical machine** (different CPU
microarchitecture, and ideally a non-Windows host for the real-proof ledger)
has not been performed. The automation environment cannot provide one: it runs
on the measurement host itself, and `wsl.exe` is blocked by the environment's
command security policy (no workaround attempted). The checklist above is
unchanged; the Ubuntu CI runs already cover the OS axis for the parameter-free
layer.

## 5. What "reproduced" means here

A reproduction is successful when: the gates pass, every proof verifies
(192 B), the memory ledger reproduces the peak within allocator granularity
(±8,192 B), and any timing comparison uses the same affinity, thread count and
host-load conditions as the reference batch. Timing numbers are **not**
portable across hosts; memory and correctness numbers are.
