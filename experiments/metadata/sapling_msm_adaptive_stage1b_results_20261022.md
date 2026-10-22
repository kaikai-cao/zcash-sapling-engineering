# Stage 1b 结果：大 MSM 门控自适应窗口与尾部切分（2026-10-22）

> 预注册：[`sapling_msm_adaptive_stage1b_preregistration_20261022.md`](sapling_msm_adaptive_stage1b_preregistration_20261022.md)
> 预注册 SHA-256：`fcd2bd7cbfd80443a0a9f9765f5077222c5b6ed4c5f5535c1536a8d6ec16b0a1`
> 预注册提交：`75e9637`（Stage 1a 预注册为 `7787ef7`，SHA-256 `a7cc4a7d6085442534ddd068eccb4bc81de1195c64f9e78d0a024d9d83e60d60`）
> 正式测量 HEAD：`a4577cbb8e002984bf1dde0b6af42d83015462dc`
> 分析脚本：[`../../scripts/analyze_msm_adaptive_experiment.py`](../../scripts/analyze_msm_adaptive_experiment.py)
> 原始数据/manifest 提交：`3acd998`
> 执行：OpenCode（2026-10-22；用户确认后执行）

本文只记录 Stage 1b 的结果。Stage 1b 不切换任何默认值；所有策略只通过显式环境变量启用。本文不因结果方向修改预注册阈值或验收表。

---

## 0. 结论摘要

1. **正式 campaign 完成 44/44 批**：Spend 20 批、Output 12 批、交易 12 批；44 个唯一 batch ID；manifest 全部 `exit_code=0`。分析器 **A1–A10 共 10/10 PASS**。
2. **P1（主检验）不支持**：8t `0x5555` 的 Spend `C1`（门控自适应，n≥16384）对 `C0`（默认）的 prove 中位比为 **1.019**（90% CI `0.958–1.077`）。点估计方向为 **C1 慢 1.9%**，不是预注册要求的 `≤0.95`，CI 上界也未低于 1.00。
3. **正对照 C4（强制 c=11）同样没有收益**：`C4/C0=0.999`（90% CI `0.940–1.055`）。因此 c=11 在本次 campaign 中没有复现 Stage 0 的 prove 优势；P1 的否定不能归因于门控实现。
4. **P2/P3（尾部切分）不支持**：`C2`（c=13，尾切 2 段）为 **1.117**（CI `1.052–1.179`，慢 11.7%）；`C3`（c=10，尾切 4 段）为 **1.027**（CI `0.956–1.094`，慢 2.7%）。尾部切分没有降低 H-query wall，反而增加任务/bucket 开销。
5. **P4 未通过非劣效**：`C1/C4=1.020`（CI `0.966–1.076`，上界 >1.05）。两者对大 MSM 都用 c=11；差异主要来自 C1 将 `A_input`（n=8）留在默认 c=3、C4 强制 c=11，以及批次噪声，说明小 MSM 的任务数也有可测影响，但不足以形成可采用的收益。
6. **P5 未通过“不回归”认证**：Output `C1/C0=0.997`（点估计快 0.3%），但 90% CI 上界 **1.0546 > 1.05**；只能报告“点估计未见回归，但置信区间过宽，未达到预注册认证”。`C4/C0=1.289`（c=11 使 Output 慢 28.9%），说明 n<16384 门控是必要的，但门控本身不产生 Output 收益。
7. **P6 通过“不回归”**：交易 `C1/C0=0.943`（90% CI `0.877–1.015`，快 5.7%），但 `C4/C0=0.987` 且 C1/C4 的差异与 C4 的 Output c=11 回归混叠；不能把交易层点估计单独解释为自适应窗口的收益。
8. **结论：Stage 1b 没有支持任何默认切换。** `W mod P` 感知的 c=11 选择、以及尾部窗口切分，在本 8t `0x5555` campaign 中都没有稳定降低 Spend prove；Stage 0 的 c=11 657.81 ms 未复现（本次 C4 679.60 ms、C0 680.24 ms）。下一阶段不应继续堆窗口参数，而应转向同批次可重复的 fill/串行阶段机制检验，或先解决跨 campaign 的状态漂移。

**一句话：** 这次实验否定了“窗口尾部是当前 8t 可稳定提取的 5% 级杠杆”；c=11 与尾部切分都只在 Stage 0 的跨 campaign 点估计中出现，在 Stage 1b 的正式同 campaign 对照中消失或变慢。默认值保持不变。

---

## 1. 设计与执行

### 1.1 从 Stage 1a pilot 到 Stage 1b

Stage 1a 的预注册（`sapling_msm_adaptive_preregistration_20261022.md`）冻结的是**全局自适应**和**所有窗口切分**。在正式 campaign 前做了 6 个探索性 smoke（不计入正式数据）：

| smoke | batch ID | 观测 |
|---|---:|---:|
| Spend 全局 adaptive（c=11） | `1792673323919` | 696.497 ms |
| Spend 默认（c=13） | `1792673486925` | 717.053 ms |
| Spend c13 + 全窗口 split2 | `1792673373370` | 914.327 ms |
| Spend c10 + 全窗口 split4 | `1792673424608` | 775.708 ms |
| Output 全局 adaptive（c=11） | `1792673448697` | 99.259 ms |
| Output 默认（c=10） | `1792673509802` | 91.287 ms |

pilot 暴露两个问题：全局 c=11 对 Output 约慢 8.7%；所有窗口切分把 bucket reduce 从约 105 ms 推到 209 ms（H-query），收益被吃掉。因此在**正式测量前**冻结 Stage 1b：

- 自适应只在 `n ≥ 16384` 启用，Output 的 `n=8191/7821` 留在默认 c=10；
- 只切分 `W mod P` 个尾部窗口（`tail` 模式），不做全窗口切分；
- Stage 1a 不进入正式 44 批；pilot 原始文件保留，结果文档在 §2.2 记录。

这是基于 pilot 的设计修正，不是看到正式结果后改阈值。Stage 1b 的验收项和阈值仍是先冻结、再测量。

### 1.2 正式 campaign

| 项 | 值 |
|---|---|
| 测量 HEAD | `a4577cbb8e002984bf1dde0b6af42d83015462dc` |
| 预注册 SHA-256 | `fcd2bd7cbfd80443a0a9f9765f5077222c5b6ed4c5f5535c1536a8d6ec16b0a1` |
| Spend 二进制 SHA-256 | `4abe27710790b8ee096184feee90772641c2ecd79464f0c2a4c35c21e8fdf6bd` |
| Output 二进制 SHA-256 | `2505c21061571e947d8da293afca8766a647913797966b8f1168748e236be37c` |
| 交易二进制 SHA-256 | `6e97c39fcc35517223e7d1df06c57eaf3a0b0c5423d3ed61a2d600dff7a39c5f` |
| Spend 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| Output 参数 SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 线程/亲和性 | `RAYON_NUM_THREADS=8`，`0x5555` |
| 批次时间（UTC） | `2026-10-22T13:10:53Z` 至 `2026-10-22T13:33:42Z` |
| 每批 | Spend/Output 5 proofs；交易 6 次 |
| 估计量 | 先每 batch 取 warm 中位（丢弃 run 1），再对 4 个 batch 中位取中位；10,000 次 cluster bootstrap，90% CI |

实验臂与顺序严格按预注册 §4：

- Spend 20 批：`C0,C1,C2,C3,C4` 的镜像/ABBA 顺序，每臂 4 批；
- Output 12 批：`C0,C1,C4`，每臂 4 批；
- 交易 12 批：`C0,C1,C4`，每臂 4 批。

所有批次串行、每批独立进程，批间空闲 5 s；每批 runner 读回亲和性并检查 `rayon_threads=8`。

---

## 2. 验收与执行偏差

### 2.1 验收：A1–A10 全 PASS

派生表：`results/tables/msm_adaptive_acceptance_msm_adaptive_20261022.csv`。

| 项 | 结果 | 证据 |
|---|---|---|
| A1 | PASS | 20 个 Spend batch 各 5 行、5/5 `verified=true`；每批 40 条 MSM call、40 条 inner-stage、5 条 G16 stage |
| A2 | PASS | 12 个 Output batch 各 5 行、5/5 verified，`rayon_threads=8` |
| A3 | PASS | 12 个交易 batch 各 6 行、72/72 verified；V5、1 spend + 2 outputs、`tx_bytes=2377`、`affinity_mask=0x5555` |
| A4 | PASS | 所有 manifest 配置为 `8t_0x5555_*`；交易行读回 `0x5555`；proof 行 `rayon_threads=8` |
| A5 | PASS | 单一 HEAD、单一 Spend/Output/交易二进制哈希、单一参数哈希；交易 raw 的 `exe_sha256` 与 manifest 一致 |
| A6 | PASS | 44 行 tag 均为 `msm_adaptive_20261022`，预注册 SHA 与冻结值一致 |
| A7 | PASS | Spend H-query 策略逐批观测正确；C1 Output 由独立 profile 批次确认 c=10/W=26（§3） |
| A8 | PASS | manifest 44 行、44 个唯一 batch ID、全部 exit 0；Spend/Output/tx = 20/12/12 |
| A9 | PASS | 正式 campaign 无失败 batch、无 `.failed` raw 文件、notes 为空；启动失败单独记录在 §2.2 |
| A10 | PASS | 分析器可独立重跑并重建 summary/contrast/policy/stage 表与图 |

### 2.2 必须保留的偏差、pilot 和被排除项

1. **Stage 1a 的 6 个 pilot 批次不进入正式 44 批。** 原因见 §1.1；原始 CSV/日志保留在原路径，batch ID 为 `1792673323919`、`1792673486925`、`1792673373370`、`1792673424608`、`1792673448697`、`1792673509802`。
2. **Stage 1b 的尾部切分/门控 smoke 不进入正式 44 批。** 包括 c13 尾切 `1792673953152`（797.255 ms）、c10 尾切 `1792674008374`（712.731 ms）、Output 门控 smoke `1792674321126`（83.320 ms）。它们只用于机制和 runner 校验。
3. **第一次正式启动在 batch 1 之前失败。** 编排器标签重复了 `msm_adaptive_` 前缀，生成的 `RunDataLabel` 超过 40 字符，Spend runner 在参数验证阶段退出；**没有启动任何证明进程，也没有产生 raw prove 行**。失败 manifest 行和日志原样保留为：
   - `experiments/metadata/msm_adaptive_manifest_msm_adaptive_20261022.failed_launch.csv`
   - `experiments/raw/logs/msm_adaptive_campaign_msm_adaptive_20261022.failed_launch.log`
   - `experiments/raw/logs/msm_adaptive_campaign_console_20261022.failed_launch.log`
   修复提交 `a4577cb` 后，正式 campaign 在 `a4577cb` 上从头运行 44 批；失败尝试不计入 44 批。
4. **编排器 smoke 批次 `1792674621763` 不计入正式数据。** 修复后用 `-MaxBatches 1` 跑了一个 Spend C0 batch，tag 为 `msm_adaptive_campaign_smoke`；用于确认标签/路径正确，随后正式 campaign 使用新的 tag。
5. **C1 Output 策略用独立的 profile 批次确认。** 批次 `1792674347692` 设置 `SAPLING_PROFILE=1`、`SAPLING_MSM_ADAPTIVE_WINDOW=1`，H-query 观测为 `c=10,W=26,split=1`；该批次只用于 A7，不进入 12 个正式 Output 计时 batch。
6. **Output/交易子进程的逐批 stdout/stderr 日志只保留每臂最后一批。** campaign 对同一臂重复使用同一个 `-Label`/`-Tag`，runner 的文件名固定为 `_b1`，因此后一批覆盖前一批的子进程日志。**原始 CSV 和 campaign 日志完整保留全部 12 次调用的测量行**（campaign 日志包含每次子进程的 stdout）；没有覆盖任何 raw CSV。后续 campaign 应把 batch 序号纳入 label，或一次性用 `-Batches 4`。
7. **P5 的判定词是“未认证”，不是“回归”。** 初版分析器把 `REGRESSION_OR_UNCERTAIN` 用于 CI 超界；定稿前改为 `NOT_CERTIFIED`，因为点估计 `0.997` 没有回归方向。阈值、样本和比较均未改。
8. **Stage 0 历史 c=11 657.81 ms 不作为 PASS/FAIL。** 本次 C4 679.60 ms、C0 680.24 ms；历史值与本次不是同一 campaign，不能混合。预注册 P7 只作描述。

---

## 3. 策略观测

### 3.1 Spend H-query

每个 Spend batch 取 H-query_G1 的 5 个 run 中位：

| 臂 | window | W | split | task_count | mode | bucket_count | 观测 |
|---|---:|---:|---:|---:|---|---:|---|
| C0 默认 | 13 | 20 | 1 | 20 | none | 4096 | 预期 |
| C1 门控自适应 | 11 | 24 | 1 | 24 | none | 1024 | 预期 |
| C2 c13 尾切 2 | 13 | 20 | 2 | 24 | tail | 4096 | 预期 |
| C3 c10 尾切 4 | 10 | 26 | 4 | 32 | tail | 512 | 预期 |
| C4 c11 正对照 | 11 | 24 | 1 | 24 | none | 1024 | 预期 |

A7 **PASS**：5 个臂 × 4 个 batch 的 H-query window/split/task/mode 全部匹配预注册。

### 3.2 Output 门控

独立 profile 批次 `1792674347692`：

```
exponent_count=8191 window=10 chunk_count=26 split=1 task_count=26 split_mode=none
```

即 C1 的 `n=8191 < 16384` 走默认 c=10，不进入 c=11。A7 的 Output 观测 **PASS**。

---

## 4. Spend 主结果

### 4.1 prove 中位

| 臂 | 配置 | prove 中位 (ms) | batch 范围 (ms) |
|---|---|---:|---:|
| C0 | 默认 c=13 | **680.24** | 649.63–721.40 |
| C1 | 门控自适应 c=11 | 693.12 | 657.12–724.92 |
| C2 | c=13 + 尾切 2 | 760.13 | 732.11–780.14 |
| C3 | c=10 + 尾切 4 | 698.35 | 658.08–732.20 |
| C4 | 强制 c=11 | 679.60 | 646.18–706.13 |

### 4.2 预注册对比

`relative_pct = (1 - R) × 100`；正值表示 treatment 更快，负值表示更慢。

| 编号 | 比较 | R | 90% CI | 相对变化 | 判定 |
|---|---|---:|---:|---:|---|
| P1 | Spend C1/C0 | **1.0189** | 0.9577–1.0771 | −1.9% | **NOT_SUPPORTED** |
| P2 | Spend C2/C0 | **1.1174** | 1.0522–1.1787 | −11.7% | **NOT_SUPPORTED** |
| P3 | Spend C3/C0 | **1.0266** | 0.9560–1.0945 | −2.7% | **NOT_SUPPORTED** |
| P4 | Spend C1/C4 | **1.0199** | 0.9663–1.0759 | −2.0% | **FAIL**（上界 >1.05） |
| P5 | Output C1/C0 | 0.9970 | 0.9617–1.0546 | +0.3% | **NOT_CERTIFIED**（上界 >1.05） |
| P6 | Tx C1/C0 | 0.9430 | 0.8768–1.0154 | +5.7% | **NO_REGRESSION** |
| S1 | Spend C4/C0 | 0.9991 | 0.9398–1.0549 | +0.1% | 描述性 |
| S2 | Output C4/C0 | 1.2891 | 1.2451–1.3767 | −28.9% | 描述性 |
| S3 | Tx C4/C0 | 0.9867 | 0.9036–1.0637 | +1.3% | 描述性 |

**P1 的读法：** C1 不仅没有达到 `≤0.95`，点估计还比 C0 慢 1.9%；CI 上界 1.077。C4 是 c=11 的正对照，点估计 0.999、CI 上界 1.055，说明 c=11 本身在本次 campaign 没有 prove 收益。Stage 0 的 c=11 优势不是可重复的默认切换依据。

### 4.3 机制：H-query 的 fill/reduce 交换

每臂 4 个 batch 的 H-query stage 中位：

| 臂 | H wall (ms) | fill_sum (ms) | reduce_sum (ms) | 相对 C0 wall | 相对 C0 fill | 相对 C0 reduce |
|---|---:|---:|---:|---:|---:|---:|
| C0 c=13 | 418.37 | 1,445.14 | 99.13 | — | — | — |
| C1 c=11 | 425.97 | 1,797.49 | 30.69 | +1.8% | +24.4% | −69.0% |
| C4 c=11 | 414.20 | 1,743.79 | 30.38 | −1.0% | +20.7% | −69.4% |
| C2 c=13 尾切 2 | 503.29 | 1,496.48 | 124.17 | +20.3% | +3.6% | +25.3% |
| C3 c=10 尾切 4 | 431.27 | 1,912.01 | 20.48 | +3.1% | +32.3% | −79.3% |

解释：

- **c=11 把 reduce 降了约 69%，但 fill 增加约 21–24%**，两者在 wall 上抵消；C1/C4 的 H wall 与 C0 基本同量级。Stage 0 的 `ns_per_add` 优势没有转化成端到端 prove 优势。
- **C2 尾切** 的 fill 只增加 3.6%，但 reduce 增加 25.3%，wall 增加 20.3%；尾部 4 个窗口切成 8 个任务后，bucket 数组/归约开销和任务调度抵消了尾部填充，且没有减少最后一个完整 wave 的填充。
- **C3 尾切** 把 reduce 降到 20.5 ms，但 c=10 的 fill 增加 32.3%，wall 仍慢 3.1%；说明此负载下 fill 是主项，减少 reduce 不能补偿 fill。
- 因而 **“尾切只增加少量 reduce”** 的模型不成立：它同时改变了任务形状、bucket 生命周期和 fill 的并行效率。

### 4.4 小 MSM 的任务数效应

C1 与 C4 对大 MSM 都使用 c=11，唯一策略差异是 `A_input`（n=8）：C1 在门控下保留默认 c=3（86 个 window 任务），C4 强制 c=11（24 个任务）。C1 的 `A_input` stage wall 约 416 ms，C4 约 376 ms；C1 的 Spend prove 比 C4 慢 2.0%。这不是 c=11 的收益，而是**小 n 时“任务数/调度”可以影响 wall**的旁证。该差异不足以让 C1 超过 C0，也不改变主结论；若未来研究窗口策略，应把 `task_count` 作为一阶变量，而不是只用 `n` 或 `ns_per_add`。

---

## 5. Output

| 臂 | Output prove 中位 (ms) | batch 范围 (ms) | 对 C0 |
|---|---:|---:|---:|
| C0 默认 c=10 | 91.23 | 87.86–95.11 | — |
| C1 门控自适应 | 90.95 | 89.33–96.79 | 0.997（CI 0.962–1.055） |
| C4 强制 c=11 | 117.60 | 116.03–126.93 | **1.289**（CI 1.245–1.377） |

- 门控确实避免了 c=11 对 Output 的强回归；C1 的点估计与 C0 基本相同。
- 但 C1 的 4 个 batch 中有一个 96.79 ms 的离群值，导致 4 个 batch 的 cluster bootstrap CI 上界 1.0546，**超过预注册的 1.05**；因此 P5 只能记为 `NOT_CERTIFIED`，不能写成“已认证不回归”。
- C4 的 28.9% 回归是 c=11 对 n=8191 的直接反例；这支持“大 MSM 门控”的必要性，但不能把门控当成优化成功。

---

## 6. 真实交易

固定 V5、1 spend + 2 outputs、`tx_bytes=2377`；每批 6 次，丢弃 run 1：

| 臂 | `build_ms` 中位 (ms) | batch 范围 (ms) | 对 C0 |
|---|---:|---:|---:|
| C0 默认 | 925.49 | 906.05–972.21 | — |
| C1 门控自适应 | 872.78 | 823.10–938.58 | **0.943**（CI 0.877–1.015） |
| C4 强制 c=11 | 913.22 | 862.63–971.06 | 0.987（CI 0.904–1.064） |

- P6 的冻结判定是“不回归”，C1 **通过**（点估计快 5.7%，CI 上界 1.015 <1.05）。
- 但这次交易只有 4 个 batch，CI 很宽；C4 也略快 1.3%，而 C1/C4 的差异又和 C4 的 Output c=11 回归混叠。因此 **P6 只能作为不回归证据，不能作为“自适应窗口改善交易”的因果证据**。
- 72/72 笔交易通过 `BatchValidator` 和结构检查；所有交易行 `affinity_mask=0x5555`、`rayon_threads=8`。

---

## 7. 与 Stage 0 和历史值的关系

| 指标 | Stage 0（历史） | Stage 1b 正式 | 说明 |
|---|---:|---:|---|
| Spend c=11 正对照/候选 | 657.81 ms | C4 **679.60 ms** | 未复现；C4 是本次的 c=11 正对照 |
| Spend c=13 默认 | 751.51 ms | C0 **680.24 ms** | 本次系统状态更快约 9.5% |
| c=11 相对 c=13 | 0.875（c=11 快 12.5%） | C4/C0 **0.999** | 方向反转/消失 |
| H-query c=11 reduce | 约 105 ms（pilot） | 30.69 ms | 机制项受批次/窗口形状影响 |
| H-query c=11 fill | 约 1,569 ms（pilot c13） | 1,797 ms | c=11 fill 更高 |

**解释：** Stage 0 的 657.81 ms 是**跨 campaign 的历史点**，其 c=11/c=13 对比没有同一 campaign 的正对照；Stage 1b 把 C4（强制 c=11）和 C0 放在同一 manifest 内，结果 C4/C0=0.999。因此不能把 Stage 0 的 12.5% 当作稳定效应。预注册 P7 只作描述：C1 693.12 ms **没有达到** 657.81 ms（慢 5.37%）。

---

## 8. 结论与下一步

### 8.1 冻结判定

- **P1 不支持**；**P2/P3 不支持**；**P4 FAIL**；**P5 NOT_CERTIFIED**；**P6 NO_REGRESSION**。
- 因 P1 不支持且 P5 未认证，**不切换任何默认值**；Stage 1b 的代码只保留为显式环境变量实验路径，不进入 shipped default。
- 不能把 P6 的交易点估计写成优化成功；它不是 P1 的替代证据。

### 8.2 研究结论

1. **窗口尾部不是当前 8t 的可稳定 5% 杠杆。** c=11 的 reduce 下降被 fill 上升抵消；尾切又把 bucket/调度开销加回来。Stage 0 的 H1 `ns_per_add` 支持是真实的微观信号，但没有在端到端 prove 上复现为收益。
2. **Stage 0 的 c=11 657.81 ms 是跨 campaign 点估计，不能作为默认切换依据。** 同 campaign 正对照 C4/C0=0.999 是更强的证据。这是本次实验最重要的方法学结论：**跨 campaign 的最优点必须用同 campaign 正对照复核**。
3. **Output 的 c=11 回归是真实的**（C4/C0=1.289）；大 MSM 门控避免了它，但门控本身没有带来 Spend 收益。
4. **下一阶段不应继续调窗口参数。** 如果继续，应先做一个**同批次、同二进制的 fill 机制实验**：固定 c=13 与 c=11，在同一进程内交替测量 H-query 的 fill/reduce，并记录 `task_count`、bucket footprint 和 worker 饱和；或者转向 Stage 0 H3 指出的串行阶段重叠。任何新策略仍需独立预注册，不能复用本次的 P1 阈值。

### 8.3 建议的下一步问题（需要新预注册）

**Q-next：** 在 8t `0x5555` 下，把 H-query 的 bucket fill 固定为相同总 group-add 数、只改变窗口切分/任务形状，是否能解释 c=11 与 c=13 的 wall 差异？如果不能，说明差异来自系统状态/频率/缓存，而不是窗口算法；如果可以，下一步才值得设计新的窗口策略。

该问题不改变本次结论，也不授权默认切换。

---

## 9. 产物与复现

### 9.1 文件

- 预注册（Stage 1b）：`experiments/metadata/sapling_msm_adaptive_stage1b_preregistration_20261022.md`
- 预注册（Stage 1a，已被 1b 取代）：`experiments/metadata/sapling_msm_adaptive_preregistration_20261022.md`
- manifest：`experiments/metadata/msm_adaptive_manifest_msm_adaptive_20261022.csv`
- 原始 Spend/Output/交易 CSV：`experiments/raw/csv/*msm_adaptive_20261022*`
- 每批 Spend stage/call/inner CSV：`experiments/raw/csv/sapling_spend_{stage,msm_call,msm_inner_stage}_profile_<batch_id>.csv`
- campaign 日志：`experiments/raw/logs/msm_adaptive_campaign_msm_adaptive_20261022.log`
- 失败启动记录：`experiments/raw/logs/*failed_launch*` 与 `experiments/metadata/msm_adaptive_manifest_msm_adaptive_20261022.failed_launch.csv`
- 派生表：`results/tables/msm_adaptive_{summary,contrasts,policy,stage,acceptance}_msm_adaptive_20261022.csv`
- 图：`results/figures/msm_adaptive_*_msm_adaptive_20261022.png`

### 9.2 复现命令

```powershell
# 1. 重新运行冻结分析（只读 raw，重建派生表/图）
python scripts\analyze_msm_adaptive_experiment.py

# 2. 如需重跑正式 campaign（会拒绝覆盖已有 manifest；使用新 tag）
powershell -ExecutionPolicy Bypass -File scripts\run_msm_adaptive_campaign.ps1 -Tag <new_tag>
```

分析器的 `TAG`、`PREREG_SHA` 是冻结常量；换 tag 需要新预注册/新分析器副本，不能直接改常量后复用本次结论。

---

## 10. 验收表与冻结阈值未改动声明

本次没有修改 Stage 1b 预注册的 P1–P6 阈值、样本量、比较方向或 A1–A10。分析器只修正了 P5 的展示词（`REGRESSION_OR_UNCERTAIN` → `NOT_CERTIFIED`），因为点估计没有回归方向；这不改变任何数值或判定边界。所有原始 CSV 未被覆盖；pilot、smoke、失败启动和正式 44 批分离存放。
