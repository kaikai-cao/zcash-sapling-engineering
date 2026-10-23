# Stage 2 pilot 结果：真实 Spend 的 c=12 vs c=13（2026-10-23）

> 状态：**NO_GO**。按预注册规则关闭 c=12 窗口线；不启动正式 Stage 2，不切换默认值。
> 预注册：[`sapling_msm_c12_pilot_preregistration_20261023.md`](sapling_msm_c12_pilot_preregistration_20261023.md)
> 原始 manifest：`experiments/metadata/msm_c12_pilot_manifest_20261023.csv`
> 分析器：`scripts/analyze_msm_c12_pilot.py`
> 测量 HEAD：`4c9281c9f5e0a1aae6eb584373945ff2ef3b6ebf`
> 预注册 SHA-256：`aaacdaca264ac204b4438618f2a6e2eef22fd17e0189fb631d3796cdd24d841d`
> Spend 二进制 SHA-256：`50d973cbf103da61011286530c3ff31d24b536cb63d10494b0762c1204a8a32b`

---

## 1. 结论

4 个 Spend 批次、每臂 2 批、ABBA 顺序全部有效（A1–A5 PASS），但**冻结的 go/no-go 规则没有通过**：

- G1（点估计）**PASS**：`R = m1 / m0 = 0.944436`（c=12 臂快 5.56%）。
- G2（无批次反转）**FAIL**：C1 最慢批次 **703.710 ms** > C0 最快批次 **698.611 ms**，差 **5.099 ms（0.73%）**。
- 因此状态为 **NO_GO**：不启动正式 Stage 2，不改变默认值，不再为窗口参数追加 campaign。

这不是“c=12 无效”的正式证明。它只说明：在预注册的 4 批筛选下，点估计虽然超过 3% 门槛，但**没有达到“两个 C1 批次都优于两个 C0 批次”的稳健性要求**。按预注册，不允许用重跑或放宽 G2 来追这个信号。

## 2. 设计执行

| 项 | 预注册 | 实际 |
|---|---|---|
| 臂 | C0 默认；C1 `n ≥ 16384` 用 c=12 | 一致 |
| 批次 | 4 个 Spend，2/臂，ABBA | 一致：C0,C1,C1,C0 |
| 每批 proof | 5，丢弃 run 1 | 一致；5/5 verified |
| 线程/亲和性 | 8t，`0x5555` | 一致；`threads=8`，readback 一致 |
| 顺序间隔 | 5 s | 一致 |
| 唯一变量 | `SAPLING_MSM_WINDOW_C=12` + `SAPLING_MSM_WINDOW_MIN_N=16384` | 一致；C0 清空所有窗口变量 |
| Output/交易 | 不运行 | 未运行 |

C1 的门控只改变 `n ≥ 16384` 的 MSM；`A_input_G1`/`B_G1_input`/`B_G2_input`（n=8）保持默认 c=3。分析器从每批 40 条 MSM 记录逐条检查了窗口，A3 全部通过。

## 3. 验收

| ID | 结果 | 证据 |
|---|---|---|
| A1 | **PASS** | 4/4 批，4 个唯一 batch ID，顺序/标签与预注册一致；全部 exit 0 |
| A2 | **PASS** | 每批 5 条 raw prove 行，5/5 verified |
| A3 | **PASS** | C0 H-query c=13；C1 H-query c=12；C1 的 n=8 query 保持 c=3；40/40 行匹配 |
| A4 | **PASS** | 同一 HEAD、同一预注册 SHA、同一二进制 SHA；8t/`0x5555` |
| A5 | **PASS** | 未覆盖任何既有 raw 文件；4 批均保留 |

## 4. 结果

### 4.1 批次中位（丢弃 run 1）

| 顺序 | 臂 | batch ID | 批次中位 (ms) | H-query 中位 (ms) |
|---:|---|---|---:|---:|
| 1 | C0 | 1792718623882 | 698.611 | 457.175 |
| 2 | C1 | 1792718665475 | 703.710 | 454.500 |
| 3 | C1 | 1792718706143 | 677.724 | 438.516 |
| 4 | C0 | 1792718746987 | 764.098 | 510.787 |

### 4.2 臂汇总

| 统计量 | 值 |
|---|---:|
| C0 两批中位 | 698.611 / 764.098；臂中位 **731.354** |
| C1 两批中位 | 703.710 / 677.724；臂中位 **690.717** |
| `R = m1/m0` | **0.944436**（−5.56%） |
| G1（`R ≤ 0.97`） | **PASS** |
| `max(C1)` vs `min(C0)` | 703.710 > 698.611 |
| G2（无反转） | **FAIL**（差 0.73%） |
| 最终状态 | **NO_GO** |

C0 两批的离散度 **9.37%**，C1 为 **3.84%**；C0 第 4 批（764.098 ms）明显高于 C0 第 1 批（698.611 ms）。C1 第 2 批又略高于 C0 第 1 批。点估计的 5.56% 优势同时受“C0 末批变慢”和“C1 中批略慢”影响，不能当作稳定收益。

描述性 H-query：C0 臂中位 483.981 ms，C1 臂中位 446.508 ms（−7.72%）。该 H-query 数字不是预注册判定项，且同样受 C0 末批 510.787 ms 影响；不能据此宣称 c=12 已证明有效。

### 4.3 逐 run 的 prove_ms

| 臂/批 | run 1（丢弃） | run 2 | run 3 | run 4 | run 5 | 批次中位 |
|---|---:|---:|---:|---:|---:|---:|
| C0 b1 | 763.476 | 700.491 | 692.587 | 696.731 | 722.857 | 698.611 |
| C1 b2 | 761.021 | 800.017 | 725.267 | 673.409 | 682.152 | 703.710 |
| C1 b3 | 769.793 | 672.108 | 674.886 | 680.561 | 685.817 | 677.724 |
| C0 b4 | 930.697 | 885.964 | 782.905 | 733.356 | 745.290 | 764.098 |

## 5. 解释

- **点估计有信号，但稳健性不足**：`R=0.944` 超过 3% 筛选门槛，可是“两个 C1 批次都低于两个 C0 批次”没有满足。按预注册，这属于 NO_GO，不是“接近 GO”。
- **批次漂移大于窗口效应**：C0 两批相差 65.5 ms（9.4%），而 C1 相对 C0 的臂差 40.6 ms（5.6%）。4 批 pilot 无法把 c=12 的效应和系统漂移分开。
- **不能把 H-query 的 −7.7% 当作端到端收益**：H-query 只是 8 个 MSM 查询之一；C0 末批的 H-query 异常偏高，放大了描述性差异。
- **预注册规则的价值**：如果看到 `R=0.944` 就启动正式 campaign，等于在看到数据后放宽 G2。本次没有这样做；窗口线关闭。

## 6. 偏差与修正

1. **manifest 文件名重复前缀**：runner 首次生成 `msm_c12_pilot_manifest_msm_c12_pilot_20261023.csv`，与预注册的 `msm_c12_pilot_manifest_20261023.csv` 不一致。已将文件**重命名**为预注册路径，内容未改；runner 已修正为固定路径。该问题不影响任何批次数据。
2. **分析器状态分类**：第一版分析器把所有未通过项都归为 `INVALID`，导致 G2 失败被误报为 INVALID。已修正为：A1–A5 失败才是 INVALID；G1/G2 失败是 NO_GO。阈值、方向和原始数值未改；修正后重新生成派生 JSON/CSV。
3. **未排除批次**：4 批全部有效，无失败批次、无重跑、无剔除。
4. **未运行 Output/交易**：这是预注册的设计，不是遗漏；因此本结果不对 Output/交易作任何结论。

## 7. 决策与下一步

- **不启动正式 Stage 2 c=12 campaign**。
- **不切换默认值**；`SAPLING_MSM_WINDOW_MIN_N` 仅作为显式实验门控保留，默认 0，不改变旧行为。
- **不再为窗口参数做 pilot 重跑**。若未来重新打开窗口线，必须有新的、独立于本次结果的预注册，并先解释为什么新的设计能处理批次漂移。
- 研究重点转向**串行阶段重叠 / fill 机制**，或真实 H-query 数据驻留；不再以 1–3% 的窗口差异作为默认切换目标。

## 8. 产物

- 预注册：`experiments/metadata/sapling_msm_c12_pilot_preregistration_20261023.md`
- manifest：`experiments/metadata/msm_c12_pilot_manifest_20261023.csv`
- raw Spend（每批独立）：`experiments/raw/csv/sapling_spend_prover_runs_msm_c12_pilot_20261023_*.csv`
- stage/MSM/inner-stage：`experiments/raw/csv/*_1792718623882.csv`、`*_1792718665475.csv`、`*_1792718706143.csv`、`*_1792718746987.csv`
- campaign/outer/prebuild 日志：`experiments/raw/logs/msm_c12_pilot_20261023_*`
- 逐批子进程日志与 build 日志：`experiments/raw/logs/sapling_spend_combined_profile_*20261023_09*.log`
- 逐批 metadata：`experiments/metadata/sapling_spend_combined_profile_179271*.md`
- 派生对比：`results/tables/msm_c12_pilot_contrast_20261023.csv`
- 派生 JSON：`results/tables/msm_c12_pilot_analysis_20261023.json`
