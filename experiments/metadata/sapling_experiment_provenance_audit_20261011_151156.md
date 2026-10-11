# Sapling Experiment Provenance Audit



- Generated: 2026-10-11T15:11:56+08:00

- Repository: kaikai-cao/zcash-sapling-engineering

- Branch: main

- HEAD: c85ae7ccdff6c19f6dc6b1959cdc3e18606c85d3

- origin/main at audit start: c85ae7ccdff6c19f6dc6b1959cdc3e18606c85d3

- Remote matches HEAD: True

- Worktree before audit outputs: clean_before_audit_outputs

- Audit script SHA-256: a008434e9f0525c47b014a5eaa0afb34d8f9f9c3889c3960f44e659d03349409

- Detail CSV: experiments/metadata/sapling_experiment_provenance_audit_20261011_151156.csv



## What this audit establishes



The audit inspects existing CSV rows, embedded provenance columns, and local repository log references. It does not rerun proofs or modify existing raw experiment data. It does not infer a per-batch parameter hash solely from a global parameter-validation record.



`COMPLETE_BATCH_PROVENANCE` is reserved for records where this script found the requested provenance directly linked to a batch. Dirty worktrees, missing log references, and missing fields stay visible in the detail CSV.



## Audit counts



| Evidence grade | Records |

|---|---:|

| COMPLETE_BATCH_PROVENANCE | 3 |

| PARAMETER_HASH_CHECK_PASSED | 2 |

| PARAMETER_IDENTITY_RECORDED_ENGINEERING_REVISION_MISSING | 2 |

| PARTIAL_DIAGNOSTIC_NOT_SELF_CONTAINED | 1 |

| PARTIAL_DIRTY_WORKTREE_AND_EVIDENCE_GAPS | 3 |

| PARTIAL_MISSING_OR_UNLINKED_LOGS | 100 |

| PARTIAL_NO_BATCH_OR_SOURCE_LINK | 5 |

| PARTIAL_PROFILE_METADATA | 1 |

| STATIC_FACTS_WITHOUT_EMBEDDED_SOURCE_REVISION | 2 |

| TRACEABLE_BUT_DIRTY_WORKTREE | 3 |

| TRACEABLE_PATCHED_SOURCE_BUT_DIRTY_WORKTREE | 1 |

| TRACEABLE_STATIC_PARSER_BUT_WORKTREE_DIRTY | 2 |



- Total evidence records: 125

- Cache-condition process batches: 12

- Cache-condition batches with complete direct evidence: 3

- Cache-condition batches started from a dirty worktree: 6

- Records flagged partial or dirty: 114

- Rows referencing missing RAMMap/control logs: 6



## Highest-priority gaps



| Class | Circuit | Batch | Grade | Missing evidence |

|---|---|---|---|---|

| CPU_FREQUENCY_DIAGNOSTIC | Spend | 1791688490898 | PARTIAL_DIAGNOSTIC_NOT_SELF_CONTAINED | engineering repo commit not embedded in the diagnostic CSV or linked logs; parameter-file SHA-256 not embedded in the diagnostic CSV or linked logs; instrumented source SHA-256 not embedded in the diagnostic CSV or linked logs; runner-script SHA-256 not embedded in the diagnostic CSV or linked logs |

| CACHE_CONDITION_PROCESS | Spend | 1791688828413 | PARTIAL_DIRTY_WORKTREE_AND_EVIDENCE_GAPS | referenced RAMMap/control log missing: experiments\raw\logs\rammap_Spend_cachecmp_20261011_112003_993.log |

| CACHE_CONDITION_PROCESS | Spend | 1791688962305 | PARTIAL_DIRTY_WORKTREE_AND_EVIDENCE_GAPS | referenced RAMMap/control log missing: experiments\raw\logs\rammap_Spend_cachecmp_20261011_112217_830.log |

| CACHE_CONDITION_PROCESS | Spend | 1791689006965 | PARTIAL_DIRTY_WORKTREE_AND_EVIDENCE_GAPS | referenced RAMMap/control log missing: experiments\raw\logs\rammap_Spend_cachecmp_20261011_112302_748.log |

| CACHE_CONDITION_PROCESS | Output | 1791701501974 | PARTIAL_MISSING_OR_UNLINKED_LOGS | referenced RAMMap/control log missing: experiments\raw\logs\rammap_Output_cachecmp_20261011_145139_580.log |

| CACHE_CONDITION_PROCESS | Output | 1791701524775 | PARTIAL_MISSING_OR_UNLINKED_LOGS | referenced RAMMap/control log missing: experiments\raw\logs\rammap_Output_cachecmp_20261011_145202_842.log |

| CACHE_CONDITION_PROCESS | Output | 1791701532382 | PARTIAL_MISSING_OR_UNLINKED_LOGS | referenced RAMMap/control log missing: experiments\raw\logs\rammap_Output_cachecmp_20261011_145210_458.log |

| DEBUG_PROVER_BATCH | Output | 1791526595792 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked; build profile/thread configuration incomplete |

| FIRST_REPEAT_PROCESS | Output | 1791617770814 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Output | 1791617780346 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Output | 1791617791207 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Output | 1791618423686 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Output | 1791618476491 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Output | 1791618486266 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Output | 1791618946897 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Spend | 1791617293024 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Spend | 1791617339181 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Spend | 1791617385288 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Spend | 1791619041368 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Spend | 1791619135309 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Spend | 1791619229133 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| FIRST_REPEAT_PROCESS | Spend | 1791687710196 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| OUTPUT_INTERNAL_STAGES | Output | 1791530120574491800 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| OUTPUT_INTERNAL_STAGES | Output | 1791530720153705900 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| OUTPUT_MSM_CALLS | Output | 1791530120574491800 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| OUTPUT_MSM_CALLS | Output | 1791530720153705900 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| OUTPUT_MSM_STAGE_CALLS | Output | sapling-output-stage-1threads-v1 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked; build profile/thread configuration incomplete |

| OUTPUT_MSM_STAGE_CALLS | Output | sapling-output-stage-20threads-v1 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked; build profile/thread configuration incomplete |

| PEAK_WORKING_SET_PROCESS | Output | 1791615366610 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| PEAK_WORKING_SET_PROCESS | Output | 1791689228070 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| PEAK_WORKING_SET_PROCESS | Output | 1791689232976 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| PEAK_WORKING_SET_PROCESS | Output | 1791689322538 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| PEAK_WORKING_SET_PROCESS | Spend | 1791615270097 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stdout/log file linked by path or batch ID; no raw stderr file linked by path or batch ID; engineering repository commit not linked to this batch; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| PEAK_WORKING_SET_PROCESS | Spend | 1791689208169 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |

| PEAK_WORKING_SET_PROCESS | Spend | 1791689260273 | PARTIAL_MISSING_OR_UNLINKED_LOGS | no raw stderr file linked by path or batch ID; worktree cleanliness at experiment start not recorded; parameter-file SHA-256 not linked to this batch; runner-script SHA-256 not recorded or not linked |



## Interpretation limits



- A dirty worktree cannot be uniquely identified by the commit alone. For patched instrumentation, preserve the modified-file SHA-256 and the exact patch SHA-256 in addition to the base commit.

- A parameter hash recorded in validation metadata identifies those parameter bytes but does not prove that every historical batch consumed them unless the batch or its linked log says so.

- A log in the repository is not automatically a log for a specific batch; prefer explicit per-batch stdout/stderr references and check they exist.

- CPU/system-load samples should only explain a proving batch when the join through batch ID, process ID or a documented timestamp association is explicit.

- The older `sapling_measurement_artifact_manifest_20261011.csv` remains a point-in-time campaign manifest; this audit intentionally does not rewrite it.



## Data preservation



Only the two new audit artifacts were created. Existing raw CSVs, parameter files, proof records and logs were not changed.
