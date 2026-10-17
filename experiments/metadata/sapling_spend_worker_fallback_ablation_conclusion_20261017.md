# Sapling Spend Worker-Fallback Ablation — 收敛结论（2026-10-17）

**目的：** 完成 `sapling_spend_worker_fallback_ablation_protocol_20261016.md` 定义的 A/B 消融，给出收敛结论。
**口径：** 固定 `RAYON_NUM_THREADS=1`，唯一改动是 Bellman worker 的同步 fallback 分支（`BELLMAN_FORCE_ASYNC_WORKER`）。诊断干预，非算法优化。

---

## 0. 结论摘要（TL;DR）

1. **fallback 对端到端 Prove 无可测影响。** A（fallback 启用）与 B（强制 async）的 10 份证明：A 均值 3669.5 ms / 中位 3666.2 ms，B 均值 3710.7 ms / 中位 3696.8 ms，差 **+41.2 / +30.6 ms（约 +1%）**，Mann–Whitney **U=29**（期望 50，z=−1.59，**p≈0.11**）——在 n=10 下**不显著**，且小于组内极差（A 3615.9–3761.2；B 3638.5–3855.7）。
2. **fallback 是“计时归属/调度现象”，不是吞吐瓶颈。** 强制 async 把约 **2.5 s** 从 `assignment_query_prep_dispatch_ms`（2,523.8 → 7.3 ms）整体挪进 `wait_and_assembly_ms`（634.1 → 3,168.1 ms），端到端不变。这正是协议预先写明的“只改变计时归属”的情形。
3. **历史批次（2026-10-16）的剧烈波动与 fallback 无关，而是混合 CPU 的核放置。** 单线程 worker 落在 P-core（LP0）时 Prove ≈3.8 s、参数加载 ≈25 s；落在 E-core（LP20）时 Prove ≈8.1 s、参数加载 ≈54 s，**2.1×**。历史 A/B 批次的“8.5 s vs 3.6 s”就是这两种核在两个批次的分布差异。

---

## 1. 方法

- **配对设计（ABBA）**：A1 → B1 → B2 → A2，抵消时间漂移。
- **核放置受控**：新增 runner 参数 `-AffinityMask`，本实验固定 `1`（逻辑处理器 LP0 = P-core）。
- **参数固定**：`-Threads 1 -BranchCounters disabled -InnerStageTiming disabled`。
- **数据标签**：`fallback_ablation_pairs`（独立文件，不写入正式基线）。
- 干预校验：A 批必须 fallback>0 且 override=0；B 批必须 fallback=0 且 override>0。
- **runner 改动**：`scripts/run_spend_combined_profile.ps1` 增加 `-AffinityMask`；并把启动方式从 `Start-Process -PassThru`（无 `-Wait` 时 Windows PowerShell 5.1 不回填 `ExitCode`）改为 `System.Diagnostics.Process`，以可靠读取退出码。该文件 SHA-256 见 §7。

> runner 的默认行为（不传 `-AffinityMask`、`Start-Process` 语义）除退出码修复外未变。

## 2. 有效性（干预已激活）

| 批次 ID | 条件 | Force async | affinity mask | fallback 记录 | override 记录 | 5/5 验证 | Prove 中位 (ms) |
|---|---|---|:--:|---:|---:|:--:|---:|
| 1792226856723 | A1 | False | 1 | 5 | 0 | ✓ | 3650.035 |
| 1792226906343 | B1 | True | 1 | 0 | 15 | ✓ | 3683.560 |
| 1792226954443 | B2 | True | 1 | 0 | 15 | ✓ | 3729.608 |
| 1792227002666 | A2 | False | 1 | 5 | 0 | ✓ | 3678.478 |

A 与 B 的干预均按协议预期激活。

## 3. 主要结果（端到端 Prove，n=10/条件）

| 统计量 | A（fallback） | B（强制 async） | 差 (B−A) |
|---|---:|---:|---:|
| 均值 | 3669.5 ms | 3710.7 ms | +41.2 ms (+1.12%) |
| 中位数 | 3666.2 ms | 3696.8 ms | +30.6 ms (+0.83%) |
| 最小 | 3615.9 ms | 3638.5 ms | — |
| 最大 | 3761.2 ms | 3855.7 ms | — |
| Mann–Whitney U | 29（期望 50，z=−1.59） | | **p≈0.11，不显著** |

**判定：** 无**可重复**的端到端差异。按协议口径，这不是“fallback 拖慢了证明”，而是调度/计时归属差异。

## 4. 次要结果（计时归属）

每一步调用 `submit_elapsed_ms` / `task_start_delay_ms` 中位数（跨 run）：

| 查询 | submit A | submit B | task_delay A | task_delay B |
|---|---:|---:|---:|---:|
| H_query_G1 | 0.031 | 0.033 | 0.9 | 1.0 |
| L_query_G1 | 0.026 | 0.024 | 1553.4 | 1549.7 |
| A_aux_G1 | 0.012 | 0.012 | 1986.5 | 1993.3 |
| **B_G1_aux** | **2517.131** | **0.023** | 2285.3 | 2298.3 |
| B_G2_aux | 0.016 | 0.024 | 4.2 | 2530.7 |

阶段计时中位数：

| 阶段 (ms) | A（fallback） | B（强制 async） |
|---|---:|---:|
| circuit_synthesis_constraints_ms | 105.740 | 106.409 |
| worker_vk_setup_ms | 0.001 | 0.001 |
| qap_fft_h_exponent_prep_ms | 396.028 | 398.697 |
| h_query_access_dispatch_ms | 0.049 | 0.051 |
| **assignment_query_prep_dispatch_ms** | **2523.815** | **7.251** |
| proof_scalar_terms_ms | 1.520 | 1.622 |
| **wait_and_assembly_ms** | **634.115** | **3168.060** |
| create_proof_body_ms | 3666.155 | 3696.694 |

**读法：** 在 A 中，`B_G1_aux` 的 submit 调用同步执行了队列里约 2.5 s 的工作（fallback），于是这段时间记在 `assignment_query_prep_dispatch_ms`；在 B 中它被改为异步提交（submit≈0.02 ms），工作改在 `B_G2_aux` 的等待里发生，于是同一时间段记在 `wait_and_assembly_ms`。两条件 `assignment+wait ≈ 3158 vs 3175 ms`（±17 ms），端到端一致。

> 与历史 §8.2 的关系：历史记录的“B-G1 aux submit 2,335 ms”在本受控实验中复现为 **2,517 ms**，证实该签名真实存在——但它**不是**额外开销，只是归属。

## 5. 混淆项（重要方法学发现）：P-core vs E-core

无 affinity 时，OS 可把单线程 worker 放到 E-core。固定 affinity 的两次探针（同一 exe、同一参数、`RAYON_NUM_THREADS=1`）：

| 探针 | 绑核 | 5 次 prove (ms) | 参数加载 (ms) | 整批墙钟 |
|---|---|---|---:|---:|---:|
| `affinity_probe_lp0_*` | LP0（P-core） | 4018.3 / 3800.6 / 3768.7 / 3771.3 / 3773.4 | 25513.6 | 45.2 s |
| `affinity_probe_lp20_*` | LP20（E-core） | 8171.4 / 8093.3 / 8129.2 / 8389.8 / 7985.9 | 54444.0 | 95.5 s |

⇒ **2.1× 的核放置差异**，且同时作用于参数加载（点验证）与 Prove。

这解释了 2026-10-16 批次：`1792146583061`（Prove 中位 3615 ms）落在 P-core，而 `1792140943874/1792141252805/1792141969850/1792142089756/1792142934977`（≈8062–8556 ms）落在 E-core。**此前把这些当作 fallback 效应是混淆的。**

## 6. 与历史批次的关系（历史数据不改动）

| 批次 ID | Force async | fallback | Prove 中位 (ms) | 核放置（推断） |
|---|---|---:|---:|---|
| 1792140943874 | False | 5 | 8555.902 | E-core |
| 1792141252805 | True | 0 | 8553.215 | E-core |
| 1792141969850 | True | 0 | 8489.571 | E-core |
| 1792142089756 | False | 5 | 8221.743 | E-core |
| 1792142934977 | False | 5 | 8062.160 | E-core |
| 1792146583061 | False | 5 | 3615.341 | P-core |

历史结论“A≈B 但波动巨大”与本次受控结论一致；历史的巨大波动的**原因**由本次 §5 定位。

**旁证（独立复现）：** 首次使用新 `-AffinityMask` 时因 runner 退出码缺陷未生成衍生 CSV 的 4 个批次（1792226607358/1792226654679/1792226701715/1792226748401，A/B/B/A），其原样数据保存在 `sapling_spend_prover_runs_fallback_ablation_pairs_buggy_launcher.csv`，Prove 中位 3734.5/3870.6/3753.8/3783.1 ms，**同样 A≲B、量级一致**，构成独立复现。

## 7. 复现凭证

| 项 | 值 |
|---|---|
| git 分支 / HEAD | `experiment/fallback-ablation-20261016` / `b1beca2`（工作区脏，含本次改动） |
| rustc / cargo | 1.98.1 / 1.98.1 |
| CPU | Intel Core i7-14700（混合 P/E 核） |
| 参数 | `D:\Research\zcash-params\sapling-spend.params`（SHA-256 `8E48FFD2…FC13`，47,958,396 B） |
| runner | `scripts/run_spend_combined_profile.ps1` SHA-256 `F1F5F4FE1A40AC434FB36C6E00F2E3DD373399E7FA10257F16C16AA5B60FA1E9` |
| 被测 exe | `spend_prover_smoke.exe` SHA-256 `DF0DE411BDF537DC8E3A853CE43EB41C0DAB99134204EB9CA511294155580694` |
| 插桩源码 | `multicore.rs` `76853B02…D79B`；`multiexp.rs` `230FDFBE…7022`；`groth16/prover.rs` `87A18A2B…294E`；`spend_prover_smoke.rs` `B70AED0F…8EA1` |
| 运行数据行 | `experiments/raw/csv/sapling_spend_prover_runs_fallback_ablation_pairs.csv` SHA-256 `F344C93FF1B4BAC49625AC41D9C8D4EDAE662A17149F7E7E954480F5CE8DA630` |

每个批次的完整证据（含 stage/MSM/inner-stage CSV 与 stdout/stderr 哈希）见
`experiments/metadata/sapling_spend_combined_profile_<batch_id>.md`。

复现命令：

```powershell
$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'
$common = @('-RepoRoot','D:\Research\zcash-sapling-engineering','-Threads','1',
  '-BranchCounters','disabled','-InnerStageTiming','disabled',
  '-RunDataLabel','fallback_ablation_pairs','-AffinityMask','1','-AllowDirtyWorktree')
# A（fallback）：
powershell -ExecutionPolicy Bypass -File .\scripts\run_spend_combined_profile.ps1 @common
# B（强制 async）：
powershell -ExecutionPolicy Bypass -File .\scripts\run_spend_combined_profile.ps1 @common -ForceAsyncWorker
```

## 8. 限制

1. 单机（i7-14700）、单线程（RAYON_NUM_THREADS=1）、每条件 10 份证明；结论限于该工作负载与调度分支。
2. 结果对 affinity 敏感：**不绑核无法复现**（见 §5）。任何后续复测必须记录并绑定 `-AffinityMask`。
3. 结论是“fallback 不改变端到端吞吐，只改变计时归属”，**不**断言 fallback 在其他线程数/负载下也无影响（20 线程时不触发 fallback）。
4. 这是一个**零效果**（null result）结论。它降低的是“把 fallback 当成独立性能瓶颈”的优先级，而非证明 fallback 代码路径无任何调度影响。

## 9. 对瓶颈排序的影响

`docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md` §9 排名 **#2（单线程 worker fallback）** 应从“大（待消融确认）”改为：
**「计时归属/调度现象，非吞吐瓶颈；对端到端无可测影响」**。

同时也给该报告补一条方法学告警：**单线程测量必须控制核放置（affinity/优先核），否则结果有 2.1× 的不确定性。**
