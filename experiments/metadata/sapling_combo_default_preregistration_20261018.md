# 预注册：组合目标 g——「`lazy=1` + 单线程 FFT scratch 消除」组合验收与默认值切换授权（2026-10-18 冻结）

> 本文件在**任何目标 g 相关的新测量之前**冻结。冻结之后不得修改验收表；如实验设计有误，只能作废本文件并另立新预注册，不得偷偷改阈值。
>
> 背景一句话：目标 a（`SAPLING_MSM_LAZY_RECODING`，H query 窗口化「去物化」）主指标未达标（12.93 MB < 15 MB）而归档、默认保持 `0`；其副产品是定位到 QAP/FFT 阶段 90.13 MB 天花板。目标 f（`SAPLING_FFT_SERIAL_SINGLE_THREAD`，单线程四步法恒等却分配整域 scratch）已按冻结判据**通过**（六项全过），把 `lazy=1` 配置的峰值降到 86.18 MB。两个改动各自归档/通过，但**收益被阈值切开**：目标 a 单独够不到 15 MB，目标 f 只降天花板不改默认配置峰值。本目标 g 把两者作为**一个组合**正式验收，并作为**默认值切换的唯一授权路径**。

## 1. 目标定义与范围

- **目标 g = 组合验收 + 默认切换授权**。拟议新默认：`SAPLING_MSM_LAZY_RECODING=1` **且** `SAPLING_FFT_SERIAL_SINGLE_THREAD=1`；当前 shipped default 为两者皆 `0`。
- **本目标不做任何新的算法改动**。两个开关的实现分别冻结于目标 a（`85ffb0d` 前后的 `vendor/bellman/src/multiexp.rs`）与目标 f（`1bc8bc7` 的 `vendor/bellman/src/domain.rs`）；本目标只做测量、判定，以及**判定通过后**的两处默认值翻转（`multiexp.rs` 与 `domain.rs` 各一处 `unwrap_or("0")` 语义的默认值，翻转属于辅 3 的复验范畴）。
- 组合的**代码交互面**：`multiexp.rs` 的进位位图只改指数准备的物化方式，`domain.rs` 的 serial 路由只改 FFT 执行方式，两者在不同阶段、无共享状态；但此判断不代替实测——辅 1/辅 3 的复验专门覆盖组合路径。

## 2. 冻结验收表

| # | 指标 | 冻结阈值 | 测量方式 | 备注 |
|---|---|---|---|---|
| **主** | `prove_peak_abs_bytes`：当前默认臂 (lazy=0,fix=0) → 拟新默认臂 (lazy=1,fix=1) | 中位下降 **≥ 15,000,000 B** | `prove_memory_ledger`，1t@`0x1`，无阶段探针（`SAPLING_G16_MEM_PHASE_PROBE` 不设），每臂 1 次进程调用 = 5 prove，**弃每臂 run 1**，run 2–5 取中位 | 阈值继承目标 a 的冻结阈值（15 MB）；本目标不得因「预期更高」而上调 |
| 辅 1 | 正确性：本战役全部批次 `verified=true`、`proof_bytes=192`、参数 SHA-256 不变 | 100% | 内存台账两臂 + 时间战役全部批次（runner 内置逐批校验，失败即抛错） | 既有门禁的有效性继承：目标 a 的 120/120 + cross-recoding 门禁、目标 f 的 12/12 digest 门禁，均针对单开关；组合路径由本战役的 100% 真实证明验证兜底 |
| 辅 2 | 时间非退化：三臂集，拟新默认臂 B 相对当前默认臂 A | 每臂集**池化批中位 ≤ +1%** | `run_combo_default_campaign.ps1`（新驱动，双开关）：spend 1t@`0x1`（主守门）/ spend 8t@`0xFFFF` / output 1t@`0x1`；各 ABBA×3 轮；弃每臂首批与每批 run 1 | 口径与目标 f 完全一致（池化批中位 + 配对 ABBA + 精确符号检验 + MWU + 漂移守门 + 不弃首批敏感性）；端到端时间**不是**本目标的主指标，预期为负（更快）但只以「非退化」验收 |
| 辅 3 | 切换后复验：翻转两处默认值并重编译后 | (i) `fft_path_gate` **不设** `SAPLING_FFT_SERIAL_SINGLE_THREAD`（走新默认 serial）与显式 `=0`（四步法）逐位一致；(ii) 不设任何开关环境变量的台账 run 复现 (lazy=1,fix=1) 臂峰值（容差 ±8,192 B 分配器粒度）；(iii) 不设任何开关环境变量的 spend 批次 5/5 `verified=true` | 全过 | 只有辅 3 全过，默认值切换才算落地；任何一步失败 ⇒ 回退翻转（`git revert`），维持 `0` |
| 辅 4 | 数据卫生：本战役新增原始 CSV/日志不覆盖任何既有文件；批次 ID 与既有批次不冲突 | 全新 label | label 前缀 `combo_default_*`，日期戳 20261018 | 沿用留存模板（协议 §6） |

**通过判据**：主 ∧ 辅1 ∧ 辅2（三臂全过）∧ 辅3 ∧ 辅4 = True。
**不通过的回退条款**（预先声明，避免事后解释）：

- 主指标 < 15,000,000 B ⇒ 判定「组合收益不足」，**不翻转默认值**，两开关维持 `0`，结果归档；若 ≥ 10 MB 但 < 15 MB，记为「接近门槛」并附阶段分解证据供负责人决策，但**不算通过**。
- 辅 2 任一臂集池化批中位 > +1% ⇒ **不翻转**；若退化集中在 8t 臂且敏感性分析（不弃首批）显示 ≤ +1%，可按目标 f 的先例记为「口径通过 + 漂移归因」，但须在结果文档明写，且**不得**表述为「组合让该臂更快」。
- 辅 1/辅 3 任何失败 ⇒ 立即停止，回退翻转，维持 `0`。

## 3. 样本量与协议符合性

| 协议条款（`sapling_optimization_validation_protocol_20261017.md`） | 本目标执行 |
|---|---|
| §3.1 亲和性：单线程 `0x1`，多线程 `0xFFFF` | 一致 |
| §3.2 主口径 1 线程 | 主守门臂 = spend 1t@`0x1` |
| §3.3 每配置 ≥3 批、每批 5 prove、弃首批与 run 1、有效 n≥12 | ABBA×3 轮 ⇒ 每臂 6 批，弃每臂首批 ⇒ 5 批 × 4 prove = **每臂 n=20** |
| §3.4 预热批 | 由「弃每臂首批」覆盖（目标 a/f 同一惯例） |
| §3.5 测量期间无其它 CPU 负载、同会话完成 | 三臂集在同一后台会话内顺序执行；驱动记录每批 host CPU load |
| §3.6 计时批次 `SAPLING_PROFILE=0`，内存另起台账 | 一致（runner 强制 `SAPLING_PROFILE=0`；台账独立运行） |
| §4 阈值 ≥3% 才可认证端到端收益 | 本目标端到端**不宣称收益**（主指标是内存）；辅 2 只验收非退化。目标 a/f 已实测的端到端改善（lazy=1 更快）在本目标只作为佐证引用，不重复认证 |

## 4. 已知证据与预期（仅作预期，不作判定）

以下数据均**早于本预注册**归档，用于形成预期；**判定只使用本目标自己采集的数据**（目标 f 的四臂台账虽然已含这两个臂，但产生于目标 f 的批次，先于本预注册，故本目标重测两臂，不自借证据）：

| 来源 | 数字 |
|---|---|
| 目标 f 结果文档 §3.1（`1bc8bc7` 同二进制） | (lazy=0,fix=0) 103,063,734 B；(lazy=1,fix=1) 86,184,614 B ⇒ 预期主指标 **−16,879,120 B（−16.4%）** |
| 目标 a 结果文档（时间，lazy=1 vs lazy=0，同源测量） | spend 1t −4.60% / 8t −8.52% / Output −1.90%（端到端认证未过，仅方向佐证） |
| 目标 f 结果文档 §4（时间，fix=1 vs fix=0，lazy=1 下） | spend 1t −3.31% / 8t −3.17%（8t 归因漂移）/ Output −0.20% |
| 组合预期 | 主指标 −16.9 MB（超过 15 MB 门槛约 1.9 MB）；辅 2 三臂预期均为负，其中 8t 臂可能再次出现漂移归因 |

**方法论备注**：主指标阈值取 15,000,000 B 而非预期值 16,879,120 B——阈值必须**先于**测量冻结且不随预期上调，这是目标 a 的教训（阈值 15 MB 早于 90.13 MB 天花板发现）的反向应用：本次预期已由阶段分解支撑（可转化上限 = 103,063,734 − 86,184,605 = 16,879,129 B，与目标 f 实测的 fix 后可转化上限一致），但阈值仍取下界 15 MB 以防「预期微超门槛」的运气判定。

## 5. 产物清单（全部新增，不覆盖）

```
# 预注册（本文件，先于任何测量提交）
experiments/metadata/sapling_combo_default_preregistration_20261018.md

# 代码/脚本（与预注册同批或紧随其后，不含测量结果）
scripts/run_combo_default_campaign.ps1                      # 双开关 ABBA 驱动
scripts/analyze_combo_default_experiment.py                 # 判定脚本

# 原始数据（测量产生）
experiments/raw/csv/sapling_prove_memory_ledger_combo_default_{lazy0fix0,lazy1fix1}_20261018.csv
experiments/raw/logs/sapling_prove_memory_ledger_combo_default_*_20261018.log
experiments/raw/csv/sapling_{spend,output}_prover_runs_combo_default_*_{off,on}.csv(+_summary.csv)
experiments/raw/logs/driver_combo_default_abba_*_20261018-*.log
experiments/raw/logs/fft_path_gate_combo_default_{off,on}_20261018.log     # 辅 3 (i)

# 派生表
results/tables/sapling_combo_default_memory_20261018.csv
results/tables/sapling_combo_default_abba_20261018.csv

# 结果文档
experiments/metadata/sapling_combo_default_results_20261018.md
```

判定脚本必须：拒绝覆盖既有输出（本目标只写新文件）；从上述原始文件可完整复现全部派生数字；统计口径与 `analyze_qap_fft_fix_experiment.py` 逐字节同构（池化中位、配对 ABBA、精确符号检验、MWU、漂移守门、不弃首批敏感性）。

## 6. 冻结时点状态

| 项 | 值 |
|---|---|
| 工程 HEAD | `596473f`（目标 f 文档包），工作区 clean |
| `spend_prover_smoke.exe` SHA-256 | `6b01cb764d38099f62997e1d182f34888fb3df4ffade105b8a5b78efdcdd946c` |
| `prove_memory_ledger.exe` SHA-256 | `a5efb982a1ab2cfe12e66f03ca4f48ee96e73b1992ee7e9f16de518e20a39e4f` |
| `fft_path_gate.exe` SHA-256 | `d70725464f85a5ca5c2156b4aa252ad47bda93a75c883029be4e372fcf2a0475` |
| `sapling-output-smoke.exe` SHA-256 | `214fbbf8323e3284c70ad13a25d75915dfca4d2d5b79a6cab769b163d245bf52` |
| Spend 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| Output 参数 SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 工具链 | rustc 1.98.1 (48a229cea 2026-09-01)，cargo 1.98.1 (797e8a9bc 2026-08-05) |
| 平台 | Windows 11，Intel i7-14700（8P+12E），32 GB RAM |

> 二进制与目标 f 测量时同哈希（`1bc8bc7` 构建、09:49–09:50），本预注册不引入任何源码改动，故冻结哈希 = 目标 f 哈希。辅 3 涉及重编译，届时在新结果文档中记录新二进制哈希。

## 7. 执行顺序（冻结）

1. 提交本预注册（单独提交，先于任何测量）。
2. 提交驱动脚本与判定脚本（`code/scripts`，不含数据）。
3. 运行内存台账两臂 + 时间战役三臂集（`raw data` 提交）。
4. 运行判定脚本，得出 PASS/FAIL。
5. **若 PASS**：翻转两处默认值 → 重编译 → 辅 3 三项复验 → 提交代码与复验数据。
6. 撰写结果文档，更新主报告 / README / 周报（`docs/metadata` 提交）。

---

*本预注册于 2026-10-18 冻结，先于目标 g 的任何新测量。验收表与回退条款不可修改。*
