# Sapling Provenance Gap Triage



- Generated: 2026-10-11T15:19:19+08:00

- Main audit input: experiments/metadata/sapling_experiment_provenance_audit_20261011_151156.csv

- Repository HEAD at triage time: c85ae7ccdff6c19f6dc6b1959cdc3e18606c85d3

- Detailed triage CSV: experiments/metadata/sapling_provenance_gap_triage_20261011_151919.csv

- This triage does not rerun proofs and does not alter prior audit/raw files.



## Decision summary



- Audit records triaged: 125

- Cache process batches checked directly from the 60-row cache CSV: 12

- Cache batches with missing referenced RAMMap logs: 6

- Cache batches that started from dirty worktrees: 6



## Cache-batch disposition



| Circuit | Batch | Condition | Proofs passed | Worktree dirty | stdout/stderr exist | RAMMap log | Median Prove (ms) | Median load/validate (ms) | Disposition |

|---|---|---:|---|---|---|---|---:|---:|---|

| Output | 1791701501974 | standby_list_cleared_approximate | True | False | True/True | MISSING | 515.786 | 1821.808 | reviewed in CSV |

| Output | 1791701509616 | parameter_file_preread_approximate | True | False | True/True | not applicable | 513.898 | 1804.318 | reviewed in CSV |

| Output | 1791701517163 | parameter_file_preread_approximate | True | False | True/True | not applicable | 513.821 | 1795.919 | reviewed in CSV |

| Output | 1791701524775 | standby_list_cleared_approximate | True | False | True/True | MISSING | 516.459 | 1810.558 | reviewed in CSV |

| Output | 1791701532382 | standby_list_cleared_approximate | True | False | True/True | MISSING | 517.515 | 1815.114 | reviewed in CSV |

| Output | 1791701539994 | parameter_file_preread_approximate | True | False | True/True | not applicable | 518.464 | 1810.352 | reviewed in CSV |

| Spend | 1791688828413 | standby_list_cleared_approximate | True | True | True/True | MISSING | 3440.691 | 24042.953 | reviewed in CSV |

| Spend | 1791688872855 | parameter_file_preread_approximate | True | True | True/True | not applicable | 3472.575 | 23960.443 | reviewed in CSV |

| Spend | 1791688917416 | parameter_file_preread_approximate | True | True | True/True | not applicable | 3460.207 | 24043.246 | reviewed in CSV |

| Spend | 1791688962305 | standby_list_cleared_approximate | True | True | True/True | MISSING | 3444.299 | 24018.808 | reviewed in CSV |

| Spend | 1791689006965 | standby_list_cleared_approximate | True | True | True/True | MISSING | 3429.333 | 24086.965 | reviewed in CSV |

| Spend | 1791689051396 | parameter_file_preread_approximate | True | True | True/True | not applicable | 3455.482 | 24068.97 | reviewed in CSV |



## How to interpret the historical RAMMap gap



The cache CSV contains per-proof results, approximate cold-condition labels, prover-process exit codes, proof-verification flags, source/parameter/runner hashes, and direct stdout/stderr references. Its `process_exit_code` field belongs to the prover process, not RAMMap. For six cold-condition processes, the CSV references a RAMMap log path but the file is not present. The terminal output supplied during this session showed `RAMMAP_EXIT_CODE=0` for the cache runs, but that output is not preserved as a repository artifact and cannot reconstruct the missing RAMMap transcript. Do not manufacture a retrospective RAMMap log or mark its transcript as present.



For future runs, change the runner so it creates the control-log file before invoking RAMMap, writes the command/start time to it, appends any stdout/stderr if present, and always writes `RAMMAP_EXIT_CODE=<value>` plus end time after the process exits. This guarantees a durable control transcript even if RAMMap produces no pipeline output; the current `Tee-Object` capture path does not guarantee a useful, self-describing control record.



## Non-cache records



The detailed CSV keeps the original audit grade and adds a disposition/action. Potential log matches are explicitly described as indirect candidates, not direct evidence. No missing script hash, code revision, parameter hash, or log is synthesized from general/global facts.



## Recommended order



1. Fix future RAMMap logging in the cache runner; do not rerun any old batch solely to replace a historical control transcript.

2. Use cache-condition results as exploratory data: all twelve process batches can be checked from their per-proof rows, but the six Spend batches started with a dirty engineering worktree and all six cold batches lack the referenced RAMMap transcript.

3. For older release/profiling batches, upgrade a record only when a deterministic direct link exists (explicit path or batch ID in the log). Circuit/timestamp/process-index guesses should remain labeled indirect.

4. Do not rerun the entire 100-row partial category indiscriminately. First focus on claims planned for a report or paper, then repeat only the minimum experiments whose missing provenance materially blocks those claims.



## Disposition counts



| Disposition | Records |

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
