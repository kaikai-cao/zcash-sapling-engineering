# Stage 3 pilot 结果：独立 Spend 证明的批次吞吐重叠（2026-10-23）

> 性质：**pilot / go-no-go 筛选**，不是正式 campaign。它只测**多证明批次吞吐**，不测单次证明延迟，不改变任何默认值，也不并入 Stage 1b / Stage 2 的数据。
> 预注册：[`sapling_spend_overlap_pilot_preregistration_20261023.md`](sapling_spend_overlap_pilot_preregistration_20261023.md)
> 预注册 SHA-256：`15758a3a6b1412c317188d62b33815f1008805fb6d6465a389086568488deaf9`
> 正式测量 HEAD：`27d3bc577399955f6c71717403790d3969a41453`
> 正式 manifest：[`spend_overlap_pilot_manifest_spend_overlap_pilot_20261023c.csv`](spend_overlap_pilot_manifest_spend_overlap_pilot_20261023c.csv)
> 正式原始数据：[`../raw/csv/sapling_spend_overlap_pilot_spend_overlap_pilot_20261023c.csv`](../raw/csv/sapling_spend_overlap_pilot_spend_overlap_pilot_20261023c.csv)

---

## 1. 结论

**分类：NO_GO。独立证明重叠线关闭；不启动正式 Stage 3，不切换默认值。**

预注册的两个 go/no-go 条件中：

- **G1 通过**：`R = 0.836155`，即 `S1` 的每证明批处理墙钟中位比 `S0` 低 **16.38%**（`S0 = 670.908 ms/proof`，`S1 = 560.983 ms/proof`）；
- **G2 失败**：`S1` 的第 6 批为 **938.951 ms/proof**，高于 `S0` 最快批 **647.044 ms/proof**；不满足 `max(S1) < min(S0)`。

按预注册规则，只要存在批次反转就是 **NO_GO**，不因 `R ≤ 0.95` 而重跑或改判。第 6 批的 8 个 proof 全部通过验证，stderr 为空；该批从第 1 个 proof 起就整体变慢（中位 `prove_ms = 1911.096 ms`，其他 `S1` 批为 1063.620–1101.571 ms）。本结果记录不把第 6 批排除，也不把它归因于某个已证实的外部原因；它按原始观测进入判定。

**解释边界：** 本 pilot 的 16.38% 是**批次吞吐**点估计，不是单次证明延迟收益。并发臂的单 proof 中位延迟反而升高 **66.27%**（`S1/S0 = 1.662690`），这与“共享 8 线程池、两个 proof 同时推进”的设计一致。该结果不能支持“单个 Spend 证明变快”，也不能支持默认切换。

## 2. 设计回顾（测量前冻结）

| 项目 | 冻结值 |
|---|---|
| 臂 | `S0` 顺序；`S1` 两个 proof worker 动态取任务，共享同一 8 线程 Rayon 池 |
| 批次 | 8 批，每臂 4 批，两轮 ABBA：`S0,S1,S1,S0,S0,S1,S1,S0` |
| 每批 | 1 个 warmup（不记录）+ 8 个 measured proofs |
| 线程/亲和 | `RAYON_NUM_THREADS=8`，`0x5555` |
| 策略开关 | 所有 `SAPLING_MSM_*` / `SAPLING_FFT_*` 均未显式设置；`SAPLING_PROFILE=0` |
| 估计量 | 每批 `batch_wall_ms / 8`；每臂 4 批取中位；`R = m1 / m0` |
| G1 | `R ≤ 0.95` |
| G2 | `max(S1 batch ms/proof) < min(S0 batch ms/proof)` |

批次墙钟只覆盖 warmup 之后的 8 个 measured proofs，包含每个 proof 的生成和验证；不包含参数读取、VK 准备和进程启动。`S1` 的 proof 生成不持任务队列锁；锁只保护取下一条 circuit 的短暂临界区。

## 3. 验收

| ID | 结果 | 证据 |
|---|---|---|
| A1 | PASS | 8/8 批，8 个唯一 batch ID，`exit_code=0` |
| A2 | PASS | 每批 8 条 measured raw 行，proof index 0–7 各一次；64/64 `verified=true` |
| A3 | PASS | arm 顺序与预注册一致；8 批均为 `threads=8`、`affinity=0x5555`；HEAD/预注册/二进制/参数哈希逐批一致 |
| A4 | PASS | manifest 与 raw 的 batch ID 集合一致；8 个 stdout 日志均存在；未覆盖既有 artifact |
| A5 | PASS | raw 共 64 行 = 8 批 × 8 proof；warmup 未写入 raw |
| A6 | PASS（人工核对） | 生产默认值、`spend_prover_smoke` 和正式 runner 未修改；只新增实验二进制、runner、分析器和预注册 |

- 预注册 SHA-256：`15758a3a6b1412c317188d62b33815f1008805fb6d6465a389086568488deaf9`
- 实验二进制 SHA-256：`a8b06e1181d7c060a3bec0b971f3c205770e2bf74f3608f86c050a5e53584df1`
- Spend 参数 SHA-256：`8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13`

## 4. 结果

### 4.1 每批吞吐

| 顺序 | 臂 | batch ID | batch wall (ms) | ms/proof | 批内 proof 中位 (ms) | verify 中位 (ms) |
|---:|---|---:|---:|---:|---:|---:|
| 1 | S0 | 1792720804759 | 5,255.392 | 656.924 | 656.329 | 2.944 |
| 2 | S1 | 1792720842337 | 4,558.065 | 569.758 | 1,101.571 | 3.204 |
| 3 | S1 | 1792720878936 | 4,417.656 | 552.207 | 1,079.506 | 3.571 |
| 4 | S0 | 1792720917001 | 5,479.131 | 684.891 | 665.663 | 3.006 |
| 5 | S0 | 1792720954485 | 5,784.984 | 723.123 | 684.139 | 3.115 |
| 6 | S1 | 1792720994289 | 7,511.608 | **938.951** | 1,911.096 | 4.059 |
| 7 | S1 | 1792721030836 | 4,368.441 | 546.055 | 1,063.620 | 3.364 |
| 8 | S0 | 1792721067851 | 5,176.350 | 647.044 | 646.477 | 2.954 |

- `S0` 四批 ms/proof：647.044、656.924、684.891、723.123；中位 **670.908 ms/proof**。
- `S1` 四批 ms/proof：546.055、552.207、569.758、938.951；中位 **560.983 ms/proof**。
- `R = 560.983 / 670.908 = 0.836155`（G1 PASS）。
- `max(S1) = 938.951 > min(S0) = 647.044`（G2 FAIL）。

### 4.2 单 proof 延迟（仅描述）

| 臂 | 单 proof `prove_ms` 中位 |
|---|---:|
| S0 | 658.079 ms |
| S1 | 1,094.181 ms |
| 比值 S1/S0 | **1.662690** |

`S1` 的单 proof 延迟显著变长，说明收益来自两个 proof 的串行/并行阶段交错，而不是单个 proof 变快。该比值不是预注册判定项。

## 5. 第 6 批异常

第 6 批（`S1`，batch ID `1792720994289`）的逐 proof 数据：

| proof | worker | start (ms) | end (ms) | prove (ms) | verified |
|---:|---:|---:|---:|---:|---|
| 0 | 0 | 0.171 | 1,911.245 | 1,911.074 | true |
| 1 | 1 | 0.203 | 1,911.321 | 1,911.118 | true |
| 2 | 0 | 1,915.629 | 3,858.287 | 1,942.658 | true |
| 3 | 1 | 1,915.688 | 3,859.250 | 1,943.562 | true |
| 4 | 0 | 3,862.046 | 5,067.454 | 1,205.408 | true |
| 5 | 1 | 3,862.878 | 5,872.358 | 2,009.480 | true |
| 6 | 0 | 5,071.354 | 6,754.633 | 1,683.279 | true |
| 7 | 1 | 5,875.841 | 7,507.350 | 1,631.508 | true |

该批从第一个 proof 起即整体变慢，8 个 proof 全部验证通过，stderr 为空；没有发现 runner、亲和性、线程数或环境变量异常。由于没有独立的外部负载/频率记录，本报告不声称已证明具体原因（热降频、后台进程或其它系统扰动均可能），也**不排除该批**。预注册规则不允许在看到结果后剔除批次；因此它是 G2 失败的直接原因，判定保持 **NO_GO**。

## 6. 执行偏差与排除批次

1. **首次启动失败（tag `spend_overlap_pilot_20261023`，无批次）**
   - 第一次正式启动在写出任何 batch 前失败：脚本把 `"${item.Label}"` 当作变量名，而不是属性表达式。
   - 留下了 campaign/prebuild 日志，`rows=0`；没有 manifest，没有 raw proof 行。
   - 日志保留在 `experiments/raw/logs/spend_overlap_pilot_20261023_*`，不计入 pilot。
   - 修复后改用独立 tag，未覆盖这些日志。

2. **exit code 捕获缺陷（tag `spend_overlap_pilot_20261023b`，1 批被排除）**
   - 第二次启动完成了第 1 个 `S0` 批（8 个 proof，全部验证通过），但 runner 用 `Start-Process -PassThru` 后读取 `ExitCode`，在 Windows PowerShell 5.1 上得到空值，脚本把该批判为失败并停止。
   - 该批的 raw CSV、manifest、日志原样保留；manifest 的 `exit_code` 为空，**不作为 pilot 数据**。
   - runner 改为 `System.Diagnostics.Process` 后，用新 tag 重新开始；没有修改预注册阈值、臂、批次或 proof 数。

3. **第 6 批整体变慢（tag `spend_overlap_pilot_20261023c`）**
   - 见 §5。保留在正式数据中，未剔除；按 G2 判 NO_GO。

4. **预注册前的二进制 smoke**
   - 在冻结预注册之前，曾用 4 个 proof 的临时 smoke 验证过 `seq` / `conc2` / `conc3` 路径（数据只在临时目录，不在仓库，不计入 pilot）。
   - smoke 只用于确认二进制能运行和证明能验证；pilot 的 5% 阈值、8 批 ABBA、8 个 measured proofs 和 G1/G2 均按预注册执行，没有根据 smoke 调参。
   - 该 smoke 不构成正式测量，也不进入本结果。

5. **未做重跑**
   - 正式 tag `spend_overlap_pilot_20261023c` 已产生 8/8 批；按预注册“G2 失败仍判 NO_GO，不因差一点而重跑”，没有重跑。
   - 如需进一步研究，必须另写预注册；不得复用本 pilot 的阈值或把第 6 批剔除后重新判定。

## 7. 解释与决策

**决策：关闭“独立证明重叠”线，不启动正式 Stage 3，不切换默认值，不对 Output/交易作任何结论。**

理由：

1. 预注册的 G2 是无批次反转；第 6 批反转幅度很大（938.951 vs 647.044 ms/proof，+45.1%），不是 0.7% 的边缘差；
2. 即使 G1 点估计为 −16.38%，它依赖 4 个 `S1` 批中的 3 个；第 6 批说明该收益在当前机器状态下不稳健；
3. 本 pilot 的并发收益是**吞吐**收益，单 proof 延迟反而 +66.27%；把吞吐点估计写成“Spend 证明变快”会混淆指标；
4. 单次证明内部的串行阶段仍不能被 H-MSM 隐藏：H-MSM 依赖完整 QAP/FFT，L/A/B 已经在同一 proof 内重叠，`proof_scalar_terms` 只有约 2 ms。独立证明重叠是唯一剩下的“串行阶段重叠”形式，而它没有通过稳健性门槛。

**没有改变的默认值：** `SAPLING_MSM_WINDOW_C`、`SAPLING_MSM_WINDOW_MIN_N`、`SAPLING_MSM_ADAPTIVE_WINDOW`、`SAPLING_MSM_WINDOW_SPLIT*`、FFT 路径及其它生产默认值均未修改。实验只通过新二进制 `spend_overlap_pilot` 和 `SAPLING_OVERLAP_*` 环境变量启用。

## 8. 产物

- 预注册：`experiments/metadata/sapling_spend_overlap_pilot_preregistration_20261023.md`
- 结果（本文件）：`experiments/metadata/sapling_spend_overlap_pilot_results_20261023.md`
- 正式 manifest：`experiments/metadata/spend_overlap_pilot_manifest_spend_overlap_pilot_20261023c.csv`
- 正式 raw CSV：`experiments/raw/csv/sapling_spend_overlap_pilot_spend_overlap_pilot_20261023c.csv`
- 正式日志：`experiments/raw/logs/spend_overlap_pilot_20261023c_*`
- 排除的 tag-b 数据：`experiments/raw/csv/sapling_spend_overlap_pilot_spend_overlap_pilot_20261023b.csv`、`experiments/raw/logs/spend_overlap_pilot_20261023b_*`
- 首次失败日志：`experiments/raw/logs/spend_overlap_pilot_20261023_*`
- 派生对比表：`results/tables/spend_overlap_pilot_contrast_20261023c.csv`
- 实验二进制：`experiments/prover-smoke/src/bin/spend_overlap_pilot.rs`
- runner：`scripts/run_spend_overlap_pilot.ps1`
- 分析器：`scripts/analyze_spend_overlap_pilot.py`

## 9. 复现命令

```powershell
# 需要干净工作树、8 个 P 核和参数文件
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run_spend_overlap_pilot.ps1 `
  -Tag spend_overlap_pilot_20261023c

python scripts/analyze_spend_overlap_pilot.py `
  --manifest experiments/metadata/spend_overlap_pilot_manifest_spend_overlap_pilot_20261023c.csv `
  --raw experiments/raw/csv/sapling_spend_overlap_pilot_spend_overlap_pilot_20261023c.csv `
  --out-csv results/tables/spend_overlap_pilot_contrast_20261023c.csv
```

本文件只记录该 tag 的一次执行；不要用同一 tag 重跑覆盖。
