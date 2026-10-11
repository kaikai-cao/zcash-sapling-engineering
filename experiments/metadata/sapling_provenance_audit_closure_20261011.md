# Sapling Provenance Audit Closure

- Generated: 2026-10-11T15:27:08+08:00
- Repository: kaikai-cao/zcash-sapling-engineering
- Branch: main
- HEAD before packaging: c85ae7ccdff6c19f6dc6b1959cdc3e18606c85d3
- Purpose: record the provenance audit, its triage, and a live validation of the repaired RAMMap control transcript.

## Historical provenance audit

- Audit records: 125
- Raw log files scanned: 96 (as reported by the audit run)
- Cache-condition process batches examined: 12
- Cache batches with complete direct provenance in the audit: 3
- Cache batches recorded with a dirty engineering worktree: 6
- Historical RAMMap control transcript references missing when audited: 6
- Triage records: 125

The audit found substantial historical provenance gaps. Missing evidence is not reconstructed by inference and is not described as if it had been captured at run time. A candidate log match by circuit/process index remains indirect evidence, not direct proof of batch identity.

### Triage dispositions

| Disposition | Count |
|---|---:|
| DIAGNOSTIC_ASSOCIATION_LIMIT | 1 |
| HISTORICAL_CONTROL_TRANSCRIPT_GAP | 3 |
| HISTORICAL_MICROBENCH_LINK_GAP | 5 |
| HISTORICAL_PROVENANCE_GAP | 87 |
| KEEP_AS_EXPLORATORY_WITH_SOURCE_LIMIT | 6 |
| POTENTIAL_LOG_MATCH_BY_CIRCUIT_AND_PROCESS_INDEX | 11 |
| RETAIN | 3 |
| RETAIN_WITH_EXPLICIT_CAVEAT | 3 |
| STATIC_FACTS_REVISION_GAP | 2 |
| STATIC_PARAMETER_FACT_REVISION_GAP | 2 |
| STATIC_PARAMETER_VALIDATION_ONLY | 2 |

Audit CSV: $auditCsvRel
Audit CSV SHA-256: $audHash

Triage CSV: $triageCsvRel
Triage CSV SHA-256: $triHash

## Live validation of repaired RAMMap transcript

- Test circuit: Output
- Approximate-cold batch: 1791703395429 (5/5 proofs verified)
- Approximate-warm batch: 1791703403032 (5/5 proofs verified)
- Approximate-cold Prove median: 514.14 ms
- Approximate-warm Prove median: 527.62 ms
- Warm minus cold: 13.48 ms (2.622%)
- Parameter SHA-256: 2F0EBBCBB9BB0BCFFE95A397E7EBA89C29EB4DDE6191C339DB88570E3F3FB0E4
- Engineering HEAD at control command: c85ae7ccdff6c19f6dc6b1959cdc3e18606c85d3
- Worktree dirty at command: True
- Cache runner script SHA-256: 35e2f949fab787d14166c68258193d41e19ef22119c7123c65835aab13374a05
- RAMMap executable SHA-256: e970913798481432cd590991577089e68510b861dc669dcab24feb06aae0df52
- RAMMap arguments: -accepteula -Et
- RAMMap exit code: 0
- Captured stdout/stderr lines: 0
- Control transcript: experiments/raw/logs/rammap_Output_cachecmp_20261011_152312_984.log
- Control transcript SHA-256: $controlHash

The transcript records command, timestamps, executable hash, arguments, exit status, source revision, worktree state, parameter file identity, runner script hash, and an explicit no-output marker. This validates that the invocation was recorded and returned exit code 0. It does **not** prove that every Windows cache layer was fully cleared; the condition remains an operational approximation.

Cache CSV: experiments/raw/csv/sapling_cache_condition_raw.csv
Cache CSV SHA-256: $cacheHash

Output proving raw CSV: experiments/raw/csv/sapling_output_prover_runs_release.csv
Output proving raw CSV SHA-256: $outputHash

## Interpretation and limitations

1. Historical missing RAMMap logs remain missing; the current test is a new validation record, not a reconstruction of those six records.
2. The audit's many older partial records must retain their caveats. No missing commit/hash/log was silently inferred into an original measurement.
3. The one-pair live test validates evidence capture, not a statistically useful cold/warm performance effect.
4. Cache-condition labels are approximate process-level controls, not strict OS cache isolation.
5. This package does not alter the frozen formal baseline results.

## Files in this evidence package

- $auditCsvRel
- $auditMdRel
- $triageCsvRel
- $triageMdRel
- $runnerRel
- $cacheCsvRel
- $outputCsvRel
- $controlLogRel
- New process stdout/stderr logs linked from the two validation batch IDs

The accompanying manifest excludes itself to avoid recursive self-hashing; it contains repository-relative paths, byte sizes, SHA-256, and Git status at packaging time.
