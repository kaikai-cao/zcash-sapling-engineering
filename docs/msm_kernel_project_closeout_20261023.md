# MSM 内核预研阶段结项报告

**日期：** 2026-10-23
**范围：** MSM 内层算法与曲线算术预研的阶段 A/B/C，以及按三条完成标准执行的项目结项整理。
**合入方式：** 本地 `main` 受仓库规则保护（禁止直推），全部成果经 **PR #17**（head `experiment/msm-kernel-20261023` → base `main`）合入；PR 触发 CI run `39950401559`（pull_request）与 `39950481873`（push），**6/6 job 成功**（library tests / fmt+clippy / release build / vendored compile / transaction-smoke check / deterministic gates）。
**生产安全性：** 本阶段未改任何生产默认值；`vendor/` 与 `experiments/transaction-smoke/` 相对 `4454c53` 零改动（`git diff --stat` 为空）。

## 0. 一句话结论

阶段 A（冻结研究状态）、B（文献对照）、C（A/A 校准 + 同输入 MSM 基准 vs blst）全部完成，结论 **P1 = GO**：bellman 单线程 H-query G1 全 MSM 为 blst 的 **1.9063 倍**（CI95 [1.8999, 1.9110]，两轮独立复现），差距归于 fill 点加公式；阶段 D 候选（xyzz 桶 fill 内核）已文档化但**未实施**。三条结项标准逐项验收通过（见 §1–§4），遗留事项如实记录在 §5。

## 1. 三条完成标准与验收结果

| # | 完成标准 | 结果 | 关键证据 |
|---|---|---|---|
| 1 | 本地工作区盘点：所有应提交的脚本、原始数据、结果文档进入 main | **通过** | ff 合并 33 文件（阶段 A/B/C 全套）+ 数据分支合并 9 文件；8 个被元Data引用的未提交文件哈希逐字节核验后入库；CI lint 预检发现并修复 |
| 2 | 复核最终报告、README、实验索引的数字与结论，无沿用已被否定的早期判断 | **通过（修正 6 处）** | 20+ 项关键数字对照一手记录全部一致；修正 CI 5/5→6/6、开关计数表述、「算术地板」口径等 |
| 3 | 复现说明、默认优化开关、源码版本、正确性门禁可被他人执行 | **通过（含本地实跑）** | 三个开关默认值对照源码确认；FFT/MSM 门禁本机实跑通过；Phase C 基准复现路径写入 reproduction.md §2.1；PR CI 6/6 |

## 2. 标准一明细：工作区盘点与合并

**盘点发现与处置：**

1. **主工作区**：合并前干净。新增 lint 修复提交 `26a10c9`（见第 5 条）后，`experiment/msm-kernel-20261023`（8 提交）fast-forward 并入 `main`：研究计划、文献survey、阶段 C 预注册/结果、`msm_kernel_bench` 与 `msm_arith_probe`、运行/分析脚本、两轮原始 CSV 与日志、派生表，共 33 文件。
2. **`experiment/spend-msm-profile` 链接工作区**（分支 tip `281f188`，已在 main 历史中）：发现 8 个未提交文件——7 个原始日志 + `results/tables/sapling_spend_thread_queue_comparison.csv`，以及 `sapling_spend_prover_runs_release.csv` 的 35 行追加。这些文件被**已入库**的 `experiments/metadata/spend_msm_profile_1791634015130.md` 按路径 + SHA-256 引用（8/8 哈希在本机逐字节匹配），属于"应该提交"的原始数据 → 提交 `adc2cf2` 后合并进 main（合并提交 `207a296`）。CSV 冲突按"取 HEAD"解决：main 历史已通过其他路径并入全部 80 行（前 81 行逐字节相同），theirs 无新增行。
3. **该工作区未提交的 `vendor/bellman/src/multiexp.rs`**：2026-10-10 插桩版（SHA-256 `730AF124…266`，与批次元数据记录一致）。**不提交**：main 已自带剖析插桩，且该批次的源码差异补丁（`experiments/metadata/source_patches/spend_msm_profile_vs_baseline.patch`）与源码哈希已入库，插桩源码被完整识别；生产文件必须保持干净。
4. **三个未合并旧分支**（`stage1c/msm-window-mechanism`、`stage2/msm-c12-pilot`、`stage6/synth-scoping`）：相对 main 无独有文件（内容已随此前的 squash 合入），无需处置。
5. **CI lint 预检（推送前）**：新增的两个 bench 二进制未过 `cargo fmt --check` 与 `clippy -D warnings`（文档列表缩进 7 处、3 个函数 10 参）。已在推送前修复（`26a10c9`，纯签名/结构重构，CSV 列与测量逻辑不变，1 区组冒烟 `correctness_summary ok=1`）。若无此预检，PR #17 的 lint job 会直接失败。
6. **行尾惯例**：Windows 产生的 CRLF 原始文件入 blob 为 LF，autocrlf=true 检出恢复 CRLF——元数据中的 SHA-256 在测量主机（及任何 autocrlf=true 检出）逐字节验证，LF 检出需先归一化行尾。这与仓库既有 1600+ 原始文件的惯例一致，未引入 `.gitattributes` 变更。

## 3. 标准二明细：数字与结论复核

**方法：** 对最终报告（§0–§8）、README（§7.1–§7.14、§16–§18）与 INDEX 全表，逐项对照一手记录（INDEX 各行结果文档、阶段 C 结果文档与派生表、探针日志、原始 CSV）。

**复核一致的关键数字（抽样全列）：** 基线 3,685.6 / 558.5 ms；103,063,495 → 86,184,607 B（−16.38%）；462 ns/非零数字（2,620,825 个数字、fill 1,211.7 ms）；目标 b −6.63% / −11.35% / −2.00 MB；目标 a 12.93 MB < 15 MB 冻结门槛；目标 f −3,945,720 B；Stage 0 4.22% / 0.8047 / 657.81 ms；Stage 1b 1.019 / 1.117 / 1.027 / 0.999；c=12 pilot R=0.9444（G2 失败）；overlap pilot R=0.836155（+66.27%）；QAP 3.89%；FFT 1.553× / 1.246× / 1.242×（门槛 1.25×）；synthesis 4.63%；Phase C P1=1.9063 CI95 [1.8999, 1.9110]、52/52、1t A/A 半宽 0.25–1.29%。**全部与一手记录一致。**

**修正清单（均为文档口径，不影响任何测量）：**

| # | 位置 | 修正 |
|---|---|---|
| 1 | README 顶部 | "two switch environment variables" → 三项默认开启（`SAPLING_MSM_SIGNED_DIGITS` / `SAPLING_MSM_LAZY_RECODING` / `SAPLING_FFT_SERIAL_SINGLE_THREAD`） |
| 2 | README §7.6 / 报告 §5 | "no further optimization target" 限定为已关闭战役范围（内存布局与调度参数调优），并指向新阶段；不主张证明器达理论最优 |
| 3 | 最终报告 §6 | Ubuntu CI "5/5 job" → **6/6**（第六 job 于 2026-10-22 增加） |
| 4 | README §7.5 | "Both switch defaults are now 1" → 明确为目标 g 的两个开关（连同目标 b 共三个默认开启） |
| 5 | README §7.6 + 报告 2026-10-23 更新块 | **「算术地板」口径修正**：阶段 C 证明 462 ns/数字是 vendored bellman 的**实现级**单位成本——同主机、同操作数下 blst ≈253 ns/模型操作（约一半）。该表述不再可被读作 Pippenger 算法的普适下限；所有 a–g 认证结果均在 bellman 路径测得，不受影响 |
| 6 | reproduction.md / INDEX / 报告基线注记 | "both defaults are 1" → 三开关具名；新增 Phase C 基准复现章节；INDEX 分支合并与 Phase D 状态；报告基线注记补 `207a296` |

## 4. 标准三明细：复现性核对

**默认优化开关（对照源码确认，2026-10-23）：**

| 开关 | 默认 | 语义 | 覆盖行为 |
|---|---|---|---|
| `SAPLING_MSM_SIGNED_DIGITS` | `1` | 均衡有符号窗口重编码（目标 b） | `0/false/off/no` → 关，其余 → 开 |
| `SAPLING_MSM_LAZY_RECODING` | `1` | 窗口化指数按需惰性转换（目标 g） | 仅 `1/true/on/yes` → 开，其余 → 关 |
| `SAPLING_FFT_SERIAL_SINGLE_THREAD` | `1` | 单线程 FFT 走四步法路径（目标 g） | 仅 `1` → 开，其余 → 关 |

**源码/工具链版本：** rustc/cargo **1.98.1**（全部认证测量的记录工具链）；CI 用 `dtolnay/rust-toolchain@stable`；`vendor/bellman/rust-toolchain.toml` 钉 **1.85.0**——该 pin 只在 `vendor/bellman/` 目录内调用 cargo 时生效，测量与 CI 均不经由它，**记录为已知口径差，未改动**（避免改动 vendored 镜像行为）；`vendor/bellman 0.15.0`、`vendor/groth16 0.2.0`（含本研究插桩）、`sapling-crypto 0.9.0`（`88a7946b`）、`bls12_381 0.9`、`blst 0.3.15`（`no-threads` feature，仅基准对照臂）。

**正确性门禁实跑（本机，2026-10-23，合并后的二进制）：**

| 门禁 | 命令口径 | 结果 |
|---|---|---|
| FFT 路径一致性 | `RAYON_NUM_THREADS=1`，默认 vs `SAPLING_FFT_SERIAL_SINGLE_THREAD=0` | 12/12 摘要逐字节一致，exit 0，`FFT_PATH_GATE_DONE` |
| MSM 重编码相等 | `MSM_WINDOW_BENCH_N=16384 C=13 REPS=1` | `cross_recoding c=13 ok`、`lazy_equals_materialised c=2..20 ok`，exit 0 |
| Phase C 基准冒烟 | `MSM_KB_BLOCKS=1`（lint 重构后二进制） | `correctness_summary ok=1`，`MSM_KERNEL_BENCH=DONE` |
| CI（Ubuntu，PR #17） | `.github/workflows/ci.yml` 全 6 job | **6/6 success**（run `39950401559` / `39950481873`） |

复现路径已写入 `docs/reproduction.md`：§2 参数无关门禁（CI 同款）、§2.1 Phase C 基准（构建 / 冒烟 / 完整轮 / 冻结分析，含参考值）、§3 真实证明复现（需外部参数文件，SHA-256 已记录）。

## 5. 遗留事项（如实记录，不阻塞结项）

1. **Fan et al. 全文未获取**：eprint 2024/750 被 Cloudflare 拦截，其实验曲线、硬件、加速比与存储代价 4 项细节待核对（文献survey §5 已列）。不影响阶段 C 结论（对照直接使用 blst 源码与实测）。
2. **8t A/A 噪声未解决**：8t 条件下配对差 CI 半宽在 8 区组时 10.6–24.4%，24 区组仅主负载达标（0.97%），中小负载 ~3%。按冻结规则，8t 绝对计时只作生产参考；细粒度生产条件比较需改进测量设计（更多区组或进程级配对）。
3. **端到端 Testnet 真实转账：耗时与内存剖析（下一阶段主动工作）**：研究目标已明确为端到端 Testnet 交易流程的耗时与内存剖析（钱包输入准备 → 确认，含证明生成分段），范围界定 [`../experiments/metadata/sapling_real_input_tx_proving_scoping_note_20261026.md`](../experiments/metadata/sapling_real_input_tx_proving_scoping_note_20261026.md) 与其预注册 [`../experiments/metadata/sapling_e2e_testnet_tx_preregistration_20261026.md`](../experiments/metadata/sapling_e2e_testnet_tx_preregistration_20261026.md)。本地构造（2026-10-22 合成 Merkle 状态）作为端到端全链路中的一段与对照基线保留；真实链上 note/witness + 网络/确认阶段为本阶段新增覆盖。技术路线以 Zebra + Zallet（Testnet）为优先（zcashd 已于 2026-07 结束支持且不支持 NU6.3）；先做一笔功能验证，再重复测量。**尚未实施**。参数无关层已双 OS 验证；真实 witness 与跨机器内存台账尚未复现。
4. **MSM Phase D 候选暂停**：xyzz 桶 fill 内核（默认关闭、独立配置）已在研究计划与阶段 C 结果中文档化；但当前优先级让位于端到端 Testnet 交易剖析（见 §5.3），Phase D **暂停、不立即实施**。如后续回到该路线，须另立预注册（含侧信道语义评估），不在本次结项范围。
5. **rust-toolchain.toml 钉 1.85.0** 与测量工具链 1.98.1 的口径差（见 §4），未改动。

## 6. 数据入口

- 计划：`docs/msm_kernel_research_plan_20261023.md`；文献：`docs/msm_literature_survey_20261023.md`
- 阶段 C 预注册/结果：`experiments/metadata/sapling_msm_kernel_stagec_{preregistration,results}_20261023.md`
- 原始数据：`experiments/raw/csv/msm_kernel_bench_20261023_{8t,1t,v2_8t,v2_1t,correctness,v2_correctness}.csv`、`experiments/raw/logs/msm_kernel_bench_20261023_*`、`experiments/raw/logs/msm_arith_probe_20261023.*`
- 派生表：`results/tables/msm_kernel_bench_20261023_{summary,aa}.csv`、`..._v2_*`
- 脚本：`scripts/run_msm_kernel_bench.ps1`、`scripts/run_msm_arith_probe.ps1`、`scripts/analyze_msm_kernel_bench.py`
- 总索引：`experiments/metadata/INDEX.md`（Phase C 行与结项指针）

*本报告为结项合成文档；凡与一手结果文档冲突，以一手文档为准。*
