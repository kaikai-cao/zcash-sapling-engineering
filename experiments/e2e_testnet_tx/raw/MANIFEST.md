# 实验产物哈希清单

> 生成时间：2026-10-31T01:04:29Z（UTC）  
> **可校验（git 跟踪）文件数：130**　合计：**909,297 B**（0.87 MB）  
> 本地排除（不可远端校验）文件数：**14**  
> 校验（干净克隆即可 100% 通过）：`cd experiments/e2e_testnet_tx && sha256sum -c raw/MANIFEST.sha256`

> 拆分原因：钱包库副本、`run.log`、诊断 JSON 等被 `.gitignore` 有意排除，
> 若写进正式清单，干净克隆会出现「文件不存在」而非「哈希不符」，容易被误读为数据损坏。
> 两类文件的哈希都记录，但**只有前者**可对外声明为远端可复现证据。

## 按类别（仅 git 跟踪文件）

| 类别 | 文件数 | 字节数 |
|---|---:|---:|
| doc | 3 | 46,092 |
| e2e_regtest | 9 | 3,419 |
| other | 1 | 936 |
| pczt | 19 | 56,375 |
| raw-other | 43 | 382,563 |
| sapling | 37 | 53,866 |
| script | 18 | 366,046 |

## 运行目录完整性

| run 目录 | 文件数 | 缺失 |
|---|---:|---|
| `raw/confirmatory_20261030/run_20261030_201124` | 5 | - |
| `raw/e2e_regtest_v2/run_20261029_142533` | 1 | - |
| `raw/e2e_regtest_v2/run_20261029_143529` | 4 | - |
| `raw/e2e_regtest_v2/run_20261029_143934` | 4 | - |
| `raw/pczt_cold_v1/run_20261029_150648` | 6 | 无 |
| `raw/pczt_pool_v1/run_20261029_145043` | 5 | 无 |
| `raw/pczt_pool_v2/run_20261029_150438` | 6 | 无 |
| `raw/pczt_pool_v2/run_20261029_150604` | 0 | meta.json、rounds.csv、stage_timings.csv、summary.csv、memory_timeseries.csv **（空目录/不完整）** |
| `raw/sapling_e2e_out9/run_20261029_152313` | 6 | 无 |
| `raw/sapling_e2e_scale30/run_20261029_151839` | 6 | 无 |
| `raw/sapling_e2e_scale60/run_20261029_151923` | 6 | 无 |
| `raw/sapling_e2e_v1/run_20261029_151727` | 6 | 无 |
| `raw/sapling_smoke/run_20261029_151423` | 5 | summary_by_shape.csv |
| `raw/sapling_smoke2/run_20261029_151658` | 6 | 无 |

## 明细 · git 跟踪（130 条，可干净克隆校验）

| 文件 | 字节 | mtime (UTC) | SHA256（前 16 位） |
|---|---:|---|---|
| `DEVIATIONS.md` | 24,530 | 2026-10-31T01:02:47Z | `940a8921ebf8800f` |
| `FREEZE.md` | 11,669 | 2026-10-31T01:04:25Z | `86ec79a56c662570` |
| `README_runbook.md` | 9,893 | 2026-10-30T13:24:31Z | `39643aa7faf100af` |
| `a_note_scan_diag.py` | 11,969 | 2026-10-30T02:33:53Z | `bbba7ab2ec2afcd2` |
| `a_prime_selftest.py` | 8,136 | 2026-10-30T02:40:28Z | `3833e64e4fb7b712` |
| `analyze_sapling_cost.py` | 5,969 | 2026-10-29T07:21:00Z | `acb1d5b7c0af8b8e` |
| `bootstrap_sapling_ci.py` | 4,238 | 2026-10-29T07:33:31Z | `98c922b0b1ac9e50` |
| `confirmatory_bench.py` | 97,003 | 2026-10-30T11:40:11Z | `41f3a75d10f3258b` |
| `e2e_tx_bench.py` | 20,117 | 2026-10-28T12:19:37Z | `251c421667634474` |
| `e2e_tx_bench_v2.py` | 19,270 | 2026-10-29T06:37:13Z | `6ebafa52545ab088` |
| `failure_class_selftest.py` | 38,793 | 2026-10-30T11:41:55Z | `7834ffd10766d6d7` |
| `fit_sapling_e2e_model.py` | 17,079 | 2026-10-30T13:10:15Z | `7e8d0ed19e88098d` |
| `h_ab_bootstrap.py` | 4,855 | 2026-10-30T13:10:20Z | `592643087486f997` |
| `isolated_harness.py` | 34,840 | 2026-10-30T13:12:43Z | `7bd7ecc14b852909` |
| `make_manifest.py` | 15,234 | 2026-10-30T13:10:00Z | `066183e43c3b2492` |
| `mem_sample.py` | 3,904 | 2026-10-27T10:10:05Z | `d0ad3c684c33fc8c` |
| `order_sensitivity.py` | 7,218 | 2026-10-30T13:09:07Z | `fc68c41a9f9f5e88` |
| `pczt_bench_pool.py` | 15,957 | 2026-10-29T07:03:43Z | `c2db6c650c536f9a` |
| `raw/AUDIT_trail.md` | 13,842 | 2026-10-29T08:01:32Z | `13737e8390726730` |
| `raw/ENV_binaries.txt` | 2,541 | 2026-10-29T07:44:42Z | `b8d0c672ae7bd0f7` |
| `raw/ENV_binaries_confirm_20261030.txt` | 5,336 | 2026-10-30T13:10:47Z | `933a1014358b32a0` |
| `raw/FAILURES.md` | 8,362 | 2026-10-29T08:00:44Z | `429ad5ccfac0ef91` |
| `raw/MANIFEST.prereg.sha256` | 1,088 | 2026-10-30T13:13:26Z | `5ce80442e8aa2e9c` |
| `raw/confirmatory_20261030/.gitignore` | 923 | 2026-10-30T06:55:55Z | `b171a34f6d2248f0` |
| `raw/confirmatory_20261030/FIT.md` | 5,939 | 2026-10-30T12:45:05Z | `d65a0df7bf57a2e9` |
| `raw/confirmatory_20261030/ORDER_SENSITIVITY.txt` | 1,555 | 2026-10-30T13:09:10Z | `653068cd609b0aca` |
| `raw/confirmatory_20261030/RESULTS.md` | 10,857 | 2026-10-30T13:11:08Z | `f099b05944aed39a` |
| `raw/confirmatory_20261030/_feasibility_gate/laststate_seal_20261030_1115/README.md` | 2,414 | 2026-10-30T03:15:39Z | `e4bb0bd2bf270430` |
| `raw/confirmatory_20261030/_feasibility_gate/laststate_seal_20261030_1115/addresses_before.tsv` | 5,393 | 2026-10-30T03:15:27Z | `ec19fc7c041ce676` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_092208/gate_summary.csv` | 869 | 2026-10-30T01:24:07Z | `40ca128b28e75bc2` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_092208/memory_timeseries.csv` | 10,083 | 2026-10-30T01:24:07Z | `229ced0f6bd52935` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_092208/meta.json` | 690 | 2026-10-30T01:24:07Z | `777082ceec576ce4` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_092208/rounds.csv` | 1,695 | 2026-10-30T01:24:07Z | `a1b3de30b871f8d6` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_095147/gate_summary.csv` | 869 | 2026-10-30T01:53:47Z | `40ca128b28e75bc2` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_095147/memory_timeseries.csv` | 10,105 | 2026-10-30T01:53:47Z | `ffe78d414114867f` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_095147/meta.json` | 1,116 | 2026-10-30T01:53:47Z | `18ab7bad3dd1d184` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_095147/rounds.csv` | 2,060 | 2026-10-30T01:53:47Z | `aedbf1c7de0b1fda` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_104456/gate_summary.csv` | 869 | 2026-10-30T02:46:57Z | `40ca128b28e75bc2` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_104456/memory_timeseries.csv` | 10,193 | 2026-10-30T02:46:57Z | `ee99c4129c79ab5b` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_104456/meta.json` | 1,116 | 2026-10-30T02:46:57Z | `a392866eb6d1cdeb` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_104456/rounds.csv` | 2,200 | 2026-10-30T02:46:57Z | `5ad6c7842aa71887` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_110042/gate_summary.csv` | 521 | 2026-10-30T03:05:34Z | `27e841ac37c3df7e` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_110042/memory_timeseries.csv` | 25,131 | 2026-10-30T03:05:34Z | `3f547b497010bc5c` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_110042/meta.json` | 1,615 | 2026-10-30T03:05:34Z | `09e3d8dae319ed1e` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_110042/rounds.csv` | 4,125 | 2026-10-30T03:05:34Z | `7a2dbb6308dc8064` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_113002/gate_summary.csv` | 1,199 | 2026-10-30T03:32:05Z | `eb53e72bb42df265` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_113002/memory_timeseries.csv` | 10,394 | 2026-10-30T03:32:05Z | `bd316a8de63581e0` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_113002/meta.json` | 1,528 | 2026-10-30T03:32:05Z | `e7561aa222e93d50` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_113002/rounds.csv` | 3,157 | 2026-10-30T03:32:05Z | `a3a323b050af5147` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_151545/gate_summary.csv` | 1,559 | 2026-10-30T07:17:07Z | `6b0fc46a893567e2` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_151545/memory_timeseries.csv` | 6,897 | 2026-10-30T07:17:07Z | `a7a4940f04df9f28` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_151545/meta.json` | 1,634 | 2026-10-30T07:17:07Z | `3089c3163999aa95` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_151545/rounds.csv` | 3,157 | 2026-10-30T07:17:07Z | `c16a961eefa7e2a1` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_152341/gate_summary.csv` | 371 | 2026-10-30T07:29:01Z | `5bc066ecbe9f0899` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_152341/memory_timeseries.csv` | 27,551 | 2026-10-30T07:29:00Z | `b0bfc742350720c7` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_152341/meta.json` | 1,759 | 2026-10-30T07:29:01Z | `fec1c5703d88f9db` |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_152341/rounds.csv` | 4,825 | 2026-10-30T07:29:01Z | `0a48ea443baf4266` |
| `raw/confirmatory_20261030/run_20261030_201124/memory_timeseries.csv` | 162,291 | 2026-10-30T12:41:47Z | `d0e5dc2c4aca30b5` |
| `raw/confirmatory_20261030/run_20261030_201124/meta.json` | 1,980 | 2026-10-30T12:41:47Z | `52daa9109d6ad213` |
| `raw/confirmatory_20261030/run_20261030_201124/rounds.csv` | 22,307 | 2026-10-30T12:41:47Z | `14906e941889c1bb` |
| `raw/confirmatory_20261030/run_20261030_201124/summary_by_shape.csv` | 447 | 2026-10-30T12:41:47Z | `d6b7f12ed16a1cd4` |
| `raw/e2e_regtest_v2/run_20261029_142533/memory_timeseries.csv` | 117 | 2026-10-29T06:25:33Z | `24880f834bf21c28` |
| `raw/e2e_regtest_v2/run_20261029_143529/memory_timeseries.csv` | 199 | 2026-10-29T06:35:29Z | `9eec9a09dd58c2ae` |
| `raw/e2e_regtest_v2/run_20261029_143529/run_summary.json` | 1,390 | 2026-10-29T06:35:29Z | `dc1485c50c3f947e` |
| `raw/e2e_regtest_v2/run_20261029_143529/stage_timings_long.csv` | 21 | 2026-10-29T06:35:29Z | `2f25c8c810d5a0c0` |
| `raw/e2e_regtest_v2/run_20261029_143529/summary_median.csv` | 41 | 2026-10-29T06:35:29Z | `ba4ff53157d8a548` |
| `raw/e2e_regtest_v2/run_20261029_143934/memory_timeseries.csv` | 199 | 2026-10-29T06:39:34Z | `a15364433bd63737` |
| `raw/e2e_regtest_v2/run_20261029_143934/run_summary.json` | 1,390 | 2026-10-29T06:39:34Z | `4186ad8d412217ae` |
| `raw/e2e_regtest_v2/run_20261029_143934/stage_timings_long.csv` | 21 | 2026-10-29T06:39:34Z | `2f25c8c810d5a0c0` |
| `raw/e2e_regtest_v2/run_20261029_143934/summary_median.csv` | 41 | 2026-10-29T06:39:34Z | `ba4ff53157d8a548` |
| `raw/pczt_cold_v1/run_20261029_150648/memory_timeseries.csv` | 5,322 | 2026-10-29T07:07:28Z | `4fb99454cae49517` |
| `raw/pczt_cold_v1/run_20261029_150648/meta.json` | 481 | 2026-10-29T07:07:28Z | `9ad4dc321ab2a839` |
| `raw/pczt_cold_v1/run_20261029_150648/rounds.csv` | 835 | 2026-10-29T07:07:28Z | `ecfad1545fae84a9` |
| `raw/pczt_cold_v1/run_20261029_150648/stage_timings.csv` | 2,351 | 2026-10-29T07:07:28Z | `4829491ae724f3e6` |
| `raw/pczt_cold_v1/run_20261029_150648/summary.csv` | 313 | 2026-10-29T07:07:28Z | `ad3937b50b554209` |
| `raw/pczt_cold_v1/run_20261029_150648/summary_by_shape.csv` | 584 | 2026-10-29T07:07:28Z | `2c8d97949779d8ac` |
| `raw/pczt_pool_v1/REPORT.md` | 7,905 | 2026-10-29T06:52:25Z | `4813086a48db6b07` |
| `raw/pczt_pool_v1/run_20261029_145043/memory_timeseries.csv` | 2,484 | 2026-10-29T06:51:01Z | `45112a98d6917db6` |
| `raw/pczt_pool_v1/run_20261029_145043/meta.json` | 359 | 2026-10-29T06:51:01Z | `c95046477b2e0f7c` |
| `raw/pczt_pool_v1/run_20261029_145043/rounds.csv` | 975 | 2026-10-29T06:51:01Z | `cf3562f33851ce66` |
| `raw/pczt_pool_v1/run_20261029_145043/stage_timings.csv` | 2,939 | 2026-10-29T06:51:01Z | `2101fd06ad85e29b` |
| `raw/pczt_pool_v1/run_20261029_145043/summary.csv` | 317 | 2026-10-29T06:51:01Z | `51300379fd982a8a` |
| `raw/pczt_pool_v2/REPORT_v2.md` | 11,681 | 2026-10-29T07:09:10Z | `39f6acbb01b0dadf` |
| `raw/pczt_pool_v2/run_20261029_150438/memory_timeseries.csv` | 6,995 | 2026-10-29T07:05:31Z | `35223ca932aae345` |
| `raw/pczt_pool_v2/run_20261029_150438/meta.json` | 415 | 2026-10-29T07:05:31Z | `3e736bd2331062a6` |
| `raw/pczt_pool_v2/run_20261029_150438/rounds.csv` | 2,702 | 2026-10-29T07:05:31Z | `c83f79c855635412` |
| `raw/pczt_pool_v2/run_20261029_150438/stage_timings.csv` | 8,802 | 2026-10-29T07:05:31Z | `1f9b1887196cc1b7` |
| `raw/pczt_pool_v2/run_20261029_150438/summary.csv` | 322 | 2026-10-29T07:05:31Z | `772d6e56ced1d544` |
| `raw/pczt_pool_v2/run_20261029_150438/summary_by_shape.csv` | 593 | 2026-10-29T07:05:31Z | `92bfaf993538b8b3` |
| `raw/sapling_e2e_out9/run_20261029_152313/memory_timeseries.csv` | 1,461 | 2026-10-29T07:23:23Z | `c534c5da7df50288` |
| `raw/sapling_e2e_out9/run_20261029_152313/meta.json` | 395 | 2026-10-29T07:23:24Z | `c826983a78e19b35` |
| `raw/sapling_e2e_out9/run_20261029_152313/rounds.csv` | 729 | 2026-10-29T07:23:24Z | `d075bb1100b5fd1b` |
| `raw/sapling_e2e_out9/run_20261029_152313/stage_timings.csv` | 253 | 2026-10-29T07:23:24Z | `7223265f05b1de64` |
| `raw/sapling_e2e_out9/run_20261029_152313/summary.csv` | 176 | 2026-10-29T07:23:24Z | `9a363d75929a7a91` |
| `raw/sapling_e2e_out9/run_20261029_152313/summary_by_shape.csv` | 133 | 2026-10-29T07:23:24Z | `e284dadb1b13b593` |
| `raw/sapling_e2e_scale30/run_20261029_151839/memory_timeseries.csv` | 5,784 | 2026-10-29T07:19:23Z | `a64d2bcece00eaba` |
| `raw/sapling_e2e_scale30/run_20261029_151839/meta.json` | 325 | 2026-10-29T07:19:23Z | `c5365782616e7bb8` |
| `raw/sapling_e2e_scale30/run_20261029_151839/rounds.csv` | 1,286 | 2026-10-29T07:19:23Z | `c8959b4d0db30206` |
| `raw/sapling_e2e_scale30/run_20261029_151839/stage_timings.csv` | 492 | 2026-10-29T07:19:23Z | `1d22114457c62b35` |
| `raw/sapling_e2e_scale30/run_20261029_151839/summary.csv` | 178 | 2026-10-29T07:19:23Z | `7a56b4d99dc69eb1` |
| `raw/sapling_e2e_scale30/run_20261029_151839/summary_by_shape.csv` | 316 | 2026-10-29T07:19:23Z | `095887e4c9caf697` |
| `raw/sapling_e2e_scale60/run_20261029_151923/memory_timeseries.csv` | 2,385 | 2026-10-29T07:19:41Z | `a852e6a314fee429` |
| `raw/sapling_e2e_scale60/run_20261029_151923/meta.json` | 325 | 2026-10-29T07:19:41Z | `ccdd8470b34149a8` |
| `raw/sapling_e2e_scale60/run_20261029_151923/rounds.csv` | 910 | 2026-10-29T07:19:41Z | `7cde9753968cab55` |
| `raw/sapling_e2e_scale60/run_20261029_151923/stage_timings.csv` | 332 | 2026-10-29T07:19:41Z | `5be07913a27ed900` |
| `raw/sapling_e2e_scale60/run_20261029_151923/summary.csv` | 176 | 2026-10-29T07:19:41Z | `bc39ce4b7b6dedf2` |
| `raw/sapling_e2e_scale60/run_20261029_151923/summary_by_shape.csv` | 237 | 2026-10-29T07:19:41Z | `414ef13caec5cdba` |
| `raw/sapling_e2e_v1/FIT.md` | 6,168 | 2026-10-29T07:31:28Z | `e40973dea7ced335` |
| `raw/sapling_e2e_v1/REPORT_sapling.md` | 17,640 | 2026-10-29T07:45:23Z | `5464e9e60f17ce56` |
| `raw/sapling_e2e_v1/run_20261029_151727/memory_timeseries.csv` | 6,496 | 2026-10-29T07:18:16Z | `7256c4564f0cc1a9` |
| `raw/sapling_e2e_v1/run_20261029_151727/meta.json` | 320 | 2026-10-29T07:18:16Z | `0277c69c0a51c9fc` |
| `raw/sapling_e2e_v1/run_20261029_151727/rounds.csv` | 2,940 | 2026-10-29T07:18:16Z | `10038428bd65182f` |
| `raw/sapling_e2e_v1/run_20261029_151727/stage_timings.csv` | 1,231 | 2026-10-29T07:18:16Z | `df74330a43cdb493` |
| `raw/sapling_e2e_v1/run_20261029_151727/summary.csv` | 181 | 2026-10-29T07:18:16Z | `44cd272015a87a5d` |
| `raw/sapling_e2e_v1/run_20261029_151727/summary_by_shape.csv` | 167 | 2026-10-29T07:18:16Z | `dfb279cef36027d4` |
| `raw/sapling_smoke/run_20261029_151423/memory_timeseries.csv` | 433 | 2026-10-29T07:14:25Z | `7d731f4754ca3ce9` |
| `raw/sapling_smoke/run_20261029_151423/meta.json` | 318 | 2026-10-29T07:14:26Z | `7d1c1eb27b8b9545` |
| `raw/sapling_smoke/run_20261029_151423/rounds.csv` | 295 | 2026-10-29T07:14:26Z | `c33437af7bef3c56` |
| `raw/sapling_smoke/run_20261029_151423/stage_timings.csv` | 95 | 2026-10-29T07:14:26Z | `a9a3e2b6c08cb848` |
| `raw/sapling_smoke/run_20261029_151423/summary.csv` | 176 | 2026-10-29T07:14:26Z | `074afedb55274b81` |
| `raw/sapling_smoke2/run_20261029_151658/memory_timeseries.csv` | 433 | 2026-10-29T07:17:00Z | `5a79a55e4ebdc9fd` |
| `raw/sapling_smoke2/run_20261029_151658/meta.json` | 319 | 2026-10-29T07:17:00Z | `1a20a25fb45a5dc0` |
| `raw/sapling_smoke2/run_20261029_151658/rounds.csv` | 358 | 2026-10-29T07:17:00Z | `39a69b9f103924aa` |
| `raw/sapling_smoke2/run_20261029_151658/stage_timings.csv` | 95 | 2026-10-29T07:17:00Z | `8f75ef705e1c0e68` |
| `raw/sapling_smoke2/run_20261029_151658/summary.csv` | 176 | 2026-10-29T07:17:00Z | `e3f11899206e175a` |
| `raw/sapling_smoke2/run_20261029_151658/summary_by_shape.csv` | 132 | 2026-10-29T07:17:00Z | `a1799b3c288069c5` |
| `recipient_derivation_selftest.py` | 26,269 | 2026-10-30T06:55:12Z | `13f9830138703963` |
| `reporting_patch_selftest.py` | 12,215 | 2026-10-30T06:42:25Z | `ba6e9872b990ccea` |
| `requirements-analysis.txt` | 936 | 2026-10-30T13:11:17Z | `a1bb3455689ae8c2` |
| `sapling_e2e_bench.py` | 22,980 | 2026-10-29T07:39:54Z | `e9c29018549b0dae` |

## 本地排除明细（14 条，仅本地证据）

| 文件 | 字节 | 排除理由 |
|---|---:|---|
| `raw/confirmatory_20261030/_feasibility_gate/laststate_seal_20261030_1115/filelist.tsv` | 112,447 | 封存目录的取证明细，脱离库本体无独立价值，`.gitignore` 排除 |
| `raw/confirmatory_20261030/_feasibility_gate/laststate_seal_20261030_1115/sha256.txt` | 176,512 | 封存目录的取证明细，脱离库本体无独立价值，`.gitignore` 排除 |
| `raw/confirmatory_20261030/_feasibility_gate/laststate_seal_20261030_1115/wallet.db.sealed` | 3,198,976 | regtest 钱包库字节副本，含支出密钥，`.gitignore` 排除（安全边界） |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_092208/run.log` | 7,775 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_095147/run.log` | 8,276 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_104456/run.log` | 10,204 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_110042/run.log` | 12,276 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_113002/run.log` | 13,551 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_151545/run.log` | 13,703 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |
| `raw/confirmatory_20261030/_feasibility_gate/run_20261030_152341/run.log` | 13,280 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |
| `raw/confirmatory_20261030/_note_scan_diag/a_prime_selftest_20261030_104052.json` | 5,914 | live-node 诊断产物，产出脚本未入库，不可独立复现 |
| `raw/confirmatory_20261030/_note_scan_diag/a_prime_selftest_20261030_104149.json` | 5,914 | live-node 诊断产物，产出脚本未入库，不可独立复现 |
| `raw/confirmatory_20261030/_note_scan_diag/scan_20261030_103423.json` | 41,210 | live-node 诊断产物，产出脚本未入库，不可独立复现 |
| `raw/confirmatory_20261030/run_20261030_201124/run.log` | 61,822 | 执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放） |

完整哈希见 `raw/MANIFEST.local-excluded.sha256`。这些文件**不随仓库分发**，
故读者无法验证其存在性；它们的作用仅是证明本工作区的产物与报告一致。

