# Spend MSM Profile — Batch 1791634015130

## Experiment identity

* Circuit: Sapling Spend
* Proving system: Groth16
* Curve: BLS12-381
* Batch ID: `1791634015130`
* Runs: 5
* Successful proof checks: 5/5
* Encoded proof size: 192 bytes
* Build profile: Release
* Rayon threads: 1
* Parameter files: External to this repository; validate against the recorded parameter hashes before reproduction.

## Instrumentation

The experiment uses a modified `vendor/bellman/src/multiexp.rs` that records MSM elapsed time, task-start delay, and submit-stage elapsed time.

The source difference from the frozen baseline is archived at:

`experiments/metadata/source_patches/spend_msm_profile_vs_baseline.patch`

The exact source and raw-log SHA-256 digests should be recorded alongside this metadata.

## Recorded results

* Median Prove time: 8,020.464 ms
* Median ratio of summed MSM-call elapsed time to Prove time: 87.62%
* All five proof checks passed.

## Interpretation limits

This is an exploratory, instrumented measurement. The instrumentation can affect absolute runtime. These results do not replace the designated formal Spend baseline of 3,385.716 ms, and the measured MSM share must not be generalized to other workloads.

The original raw log is archived at:

`experiments/raw/logs/sapling_spend_msm_queue_profile_20261010_200606.log`

This record must be paired with the source-difference file and the exact source and log digests. It is not an algorithmic optimization result.
