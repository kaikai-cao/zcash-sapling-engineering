# Sapling Spend Worker Fallback Ablation Protocol (2026-10-16)

## Objective

Estimate the effect of Bellman's synchronous worker-fallback path on Sapling Spend proving latency while holding the Rayon thread count fixed at one. This is a diagnostic intervention, not an algorithm optimization.

## Conditions

Use the same checkout, release build, Spend parameter file, CPU/power state, and `RAYON_NUM_THREADS=1` for both conditions. Run with `-BranchCounters disabled` in both conditions so branch-count increments are not an asymmetrical source of timing overhead. The runner preserves separate data in `sapling_spend_prover_runs_fallback_ablation.csv`; it does not append these runs to the formal `sapling_spend_prover_runs_release.csv` baseline.

A — normal fallback enabled:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\run_spend_combined_profile.ps1 `
  -RepoRoot "D:\Research\zcash-sapling-engineering" `
  -Threads 1 -BranchCounters disabled -RunDataLabel fallback_ablation
```

B — force async when the normal threshold would trigger fallback:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\run_spend_combined_profile.ps1 `
  -RepoRoot "D:\Research\zcash-sapling-engineering" `
  -Threads 1 -BranchCounters disabled -ForceAsyncWorker `
  -RunDataLabel fallback_ablation
```

Each invocation performs five proofs and verifies each proof. A valid A batch must contain one or more `BELLMAN_WORKER_FALLBACK` events; a valid B batch must contain no fallback events and at least one `BELLMAN_WORKER_ASYNC_OVERRIDE` event. These checks are enforced by the runner.

## Primary and secondary outcomes

Primary outcome: per-proof `prove_ms` and its median by batch. The stage fields are secondary: `assignment_query_prep_dispatch_ms`, `wait_and_assembly_ms`, and `create_proof_body_ms`. Also compare the distribution of `submit_elapsed_ms`, `task_start_delay_ms`, and each MSM's `elapsed_ms`.

Do not add MSM task elapsed times and interpret the sum as wall-clock time; MSM tasks overlap. A fall in assignment/query/dispatch accompanied by a rise in wait/assembly but little change in end-to-end Prove indicates mostly a change in timing attribution/work scheduling. A repeatable change in end-to-end Prove indicates an effect on overall scheduling/execution efficiency under this workload.

## Limitations

This is an exploratory five-run-per-condition comparison on one machine. It changes the Worker scheduling branch, not the cryptographic algorithm. Forced asynchronous submission may increase queued work and alter task ordering or transient memory use. A null result does not prove fallback is irrelevant in other workloads. If results differ substantially, repeat in reversed order or in matched pairs before making a causal claim.
