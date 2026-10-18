# 预注册：QAP/FFT 阶段内存天花板的单线程 FFT scratch 消除（目标 f）— 2026-10-18

> 本文件按 `sapling_optimization_validation_protocol_20261017.md` §5 的模板，**在动任何算法代码之前**填写并冻结。
> 一旦冻结，验收阈值与判定规则**不得修改**；实现与测量中若发现标准写错，只能在结果文档里标注，不能在本文档里改。
>
> 本目标是目标 a（`SAPLING_MSM_LAZY_RECODING`）经所有者决定后的**下一目标**（决定见
> `sapling_msm_lazy_recoding_results_20261018.md` §10）。阈值按目标 a 得出的方法论教训设定：
> **先用阶段探针分解峰值，再取 `min(可移除量, 峰值 − 次高阶段峰值)`**，不设物理上不可能达到的阈值。

---

## 0. 一句话

单线程（`log_num_threads() == 0`）下 `best_fft` 仍然走四步法 `parallel_fft`，而四步法在 `log_cpus = 0` 时**退化恒等**（shuffle 是恒等、copy-back 是恒等），却仍分配**整整一个域大小的 scratch**（131,072 × 32 B = 4,194,304 B）并多做两趟全量遍历。
让单线程直接走原位 `serial_fft`，可把 `qap_fft_h_exponent_prep` 阶段峰值从 **90.13 MB 降到 85.94 MB（−4.19 MB）**，
进而把 `SAPLING_MSM_LAZY_RECODING=1` 配置的 prove 全局峰值从 **90.13 MB 降到 86.18 MB（−3.95 MB）**——新的峰值来源变成一个与本次改动无关的既存阶段（`circuit_synthesis`）。**时间不退化。**

---

## 1. 目标与选定机制

| 项 | 内容 |
|---|---|
| 目标 | **f：QAP/FFT 阶段（`qap_fft_h_exponent_prep`）的内存天花板**——目标 a 阶段探针测出的当前 prove 峰值主因 |
| 机制 | `vendor/bellman/src/domain.rs::best_fft`：当 `log_cpus == 0` 时直接调用原位 `serial_fft`，跳过四步法及其整域 scratch |
| 不选其它机制的理由 | 见 §2.3 |

### 1.1 关键结构事实（本次侦察实测，决定设计与阈值）

`best_fft`（`vendor/bellman/src/domain.rs:261`）：

```rust
let log_cpus = worker.log_num_threads();      // 1 线程 ⇒ 0
if log_n <= log_cpus { serial_fft(a, omega, log_n); } else { parallel_fft(a, worker, omega, log_n, log_cpus); }
```

`parallel_fft`（`:316`）的 scratch：

```rust
let num_cpus = 1 << log_cpus;                 // log_cpus = 0 ⇒ 1
let log_new_n = log_n - log_cpus;             // = log_n ⇒ 17（Spend 域 2^17）
let mut tmp = vec![vec![T::group_zero(); 1 << log_new_n]; num_cpus];   // 131,072 × 32 B = 4,194,304 B
```

**总量恒为一个域大小的缓冲，与线程数无关**（`num_cpus × 2^(log_n−log_cpus) = 2^log_n`）：单线程是一个 131,072 的 Vec，8 线程是 8 个 16,384 的 Vec。它**每次 `best_fft` 调用都重新分配、返回即释放**（每份证明 6 次：`a.ifft`/`a.coset_fft`/`b.ifft`/`b.coset_fft`/`c.ifft`/`c.coset_fft`）。

**`log_cpus == 0` 时四步法恒等**（可逐行核对）：
- shuffle：`omega_step = omega^(0 << log_new_n) = 1`、`omega_j = omega^0 = 1` ⇒ `elt ≡ 1`，且 `s` 只有 0 ⇒ `tmp[i] = a[i]`（纯拷贝）；
- 子 FFT：`serial_fft(tmp, omega^num_cpus = omega, log_new_n = log_n)` ⇒ 与 `serial_fft(a, omega, log_n)` **同样的蝶形序列、同样的乘法顺序**；
- copy-back：`mask = 0`、`idx & mask = 0`、`idx >> 0 = idx` ⇒ `a[idx] = tmp[0][idx]`（恒等置换）。

⇒ `parallel_fft(·, log_cpus = 0)` 与 `serial_fft` **数值逐位等价**，代价是一个整域缓冲 + 两趟全量遍历。

**侦察实测（子阶段探针，`SAPLING_G16_MEM_PHASE_PROBE=1`，1t @ `0x1`，台账 5 run，取 run 2–5；原始日志
`experiments/raw/logs/sapling_prove_memory_ledger_qap_subphase_probe_{off,on}_20261018.stderr.log`，
派生表 `results/tables/sapling_qap_fft_subphase_peak_20261018.csv`）：**

| 子阶段（`lazy=1` 臂） | live（B） | 阶段峰值（B） | 峰值 − live |
|---|---:|---:|---:|
| `circuit_synthesis` | 85,935,069 | **86,184,605** | +249,536 |
| `worker_vk_setup` | 85,935,901 | 85,935,901 | 0 |
| `qap_domains_built`（三次 `from_coeffs`） | 85,935,901 | 85,935,901 | **0** |
| **`qap_ffts_done`（六次变换）** | 85,935,901 | **90,130,325** | **+4,194,424** |
| `qap_mul_ab_done` | 81,741,597 | 85,935,941 | +4,194,344 |
| `qap_sub_c_done` | 77,547,293 | 81,741,637 | +4,194,344 |
| `qap_divide_icoset_done` | 77,547,293 | 81,741,717 | +4,194,424 |
| `qap_into_coeffs_done` | 77,547,293 | 77,547,293 | 0 |
| `qap_fft_h_exponent_prep`（h 转换） | 78,595,869 | 82,790,133 | +4,194,264 |

三条结论（决定了机制与阈值）：

1. `from_coeffs` **不产生任何净增或瞬态**：`prover.a/b/c` 在综合阶段就已经是域大小（容量 131,072），域对象直接接管原缓冲。所以"三个域向量同时驻留"（12.58 MB）是**必需的**，不是浪费。
2. 阶段内唯一的额外缓冲就是**六次变换里的那个整域 scratch**（+4,194,424 B ≈ 4,194,304 + 120 B 头部），**且不是 h 指数转换**（转换瞬态 +5,242,840 B，落在 82.79 MB，低于阶段峰值 7.3 MB）。
3. 因此阶段峰值 = **进入该阶段的 live（85.94 MB）+ 一个域大小缓冲（4.19 MB）**；移掉 scratch 后，该阶段峰值回落到自身的进入 live（85.94 MB），而**全局**峰值改由既存的 `circuit_synthesis` 峰值（86.18 MB）决定。

### 1.2 机制细节

- `vendor/bellman/src/domain.rs::best_fft`：条件从 `log_n <= log_cpus` 改为 `log_n <= log_cpus || (log_cpus == 0 && <开关>)`。
- 开关 `SAPLING_FFT_SERIAL_SINGLE_THREAD`（`0` = 现状，`1` = 单线程走原位 `serial_fft`），**默认保持 `0`**（与目标 a/b 同惯例）。
- 只影响单线程路径：`log_cpus >= 1` 时行为**逐字节不变**（多线程的四步法仍需要 scratch，且其总量已是理论最小值）。
- 不触碰 MSM、证明系统、参数或任何数值表达式；不引入浮点。

### 1.3 为什么这是可达到的最大值（阈值推导）

- 可移除量（机制上限）：**4,194,424 B**（实测 scratch）。
- 全局峰值的可转化上限：**当前全局峰值 − 次高阶段峰值** = 90,130,325 − 86,184,605 = **3,945,720 B**。
- ⇒ `min(4,194,424, 3,945,720) = 3,945,720 B` 是本目标全局峰值的物理上限。
- 冻结阈值取 **3,500,000 B**（= 物理上限的 88.7%），余量吸收分配器粒度抖动。

> 这正是目标 a 的教训：若当初按"缓冲毛值"设 15 MB，则物理上不可达。本目标的阈值按阶段分解设定，并**显式记录可转化上限**。

---

## 2. 验收表（冻结）

**测量配置：** `SAPLING_MSM_LAZY_RECODING=1` 固定（本目标改动只在单线程上生效，而该配置下 QAP/FFT 阶段才是绑定峰值）；1t @ `0x1`（LP0）；`SAPLING_PROFILE=1 SAPLING_MEM_PROBE=1 [SAPLING_G16_MEM_PHASE_PROBE=1]`；台账每臂 5 run，暖态 = run 2–5，取中位。

| # | 指标 | 阈值 | 模型预测 | 判据 |
|---|---|---:|---:|---|
| **主** | **`prove_peak_abs_bytes` 下降**（`lazy=1` 配置，全局峰值） | **≥ 3,500,000 B** | 3,945,720 B（90,130,324 → 86,184,6xx） | 必须 |
| 辅 1 | `qap_fft_h_exponent_prep` **阶段峰值**下降（机制确实生效） | ≥ 3,500,000 B | 4,194,424 B（90,130,3xx → 85,935,9xx） | 必须 |
| 辅 2a | 正确性：全部证明 `verified=true`、`proof_bytes=192` | 100% | — | 必须 |
| 辅 2b | 正确性：`serial_fft` 与 `parallel_fft(log_cpus=0)` **逐位相同**（n = 2^10、2^13、2^17） | 全过 | — | 必须 |
| 辅 3 | 时间守门（三个臂集，`lazy=1` 固定）：池化批中位 | 不退化 >1% | ≈ 略快（省两趟全量遍历） | 必须 |
| 辅 4 | `lazy=0`（shipped default）全局峰值**不上升** | ≤ 0 B | 0（预期不变，103.06 MB） | 必须 |

**PASS 判据：主 ∧ 辅 1 ∧ 辅 2a ∧ 辅 2b ∧ 辅 3 ∧ 辅 4。**

**回退条款（预声明）：**
- 主指标未达 3.5 MB 但辅 1 达标 ⇒ 记「**scratch 确实消除但未转化为全局峰值下降**」，归档，默认保持 `0`。
- 辅 1 未达标 ⇒ 记「**未消除单线程 scratch**」，归档，默认保持 `0`。
- 辅 3 退化 >1% ⇒ 记「**省内存换来时间退化**」，归档，默认保持 `0`。
- 辅 4 上升 ⇒ 记「**对默认配置有副作用**」，归档，默认保持 `0`。

**关于本目标的适用范围（预声明，避免误读）：**
本目标把 `lazy=1` 配置的 prove 峰值从 90.13 MB 降到 86.18 MB，但**不改变 shipped default（`lazy=0`）的全局峰值**，因为该配置下峰值由 H query 窗口化缓冲所在区间决定（103.06 MB）。
因此本目标的产出必须与目标 a 一起看：**组合**（`lazy=1` + 本改动）= 103.06 MB → 86.18 MB = **−16.88 MB（−16.4%）**，即超过目标 a 单独未能达到的 15 MB 门槛。
组合收益的正式验收是**下一个目标（g）**的事，本目标只负责把天花板本身降下来并给出可转化的上限。

---

## 3. 测量设计

**A/B：** 同一二进制 + 开关 `SAPLING_FFT_SERIAL_SINGLE_THREAD=0/1`；`SAPLING_MSM_LAZY_RECODING` 在时间臂集中固定为 `1`（父进程环境变量继承，驱动脚本 `-SwitchVar SAPLING_FFT_SERIAL_SINGLE_THREAD`）。

1. **内存（主 + 辅 1 + 辅 4）**：4 组台账 = {`lazy`=0,1} × {`fix`=0,1}，各 5 run，1t @ `0x1`，带阶段探针。
   - 主 + 辅 1 取自 `lazy=1, fix=0/1`；辅 4 比较 `lazy=0, fix=0/1`。
   - 阶段探针会重设水位线，因此这四组的台账 `prove_peak_abs_bytes` 列**不可用**；全局值由 `running_max_abs_bytes` 取最大（脚本 `scripts/analyze_g16_mem_phase_probe.py` 已固化该读法），并另跑不带探针的一组做对照（`lazy=1, fix=0/1`，各 5 run，台账列有效）。
2. **正确性（辅 2a/2b）**：微基准门禁新增 `serial_fft == parallel_fft(log_cpus=0)` 逐位断言（n = 2^10、2^13、2^17，与 Spend 域同尺寸的 2^17 必须在内）；台账 4 组 × 5 run 全部 `verified=true`；既有 MSM 门禁（`lazy` 的 c = 2..=20 逐位断言等）必须仍然全过。
3. **时间（辅 3）**：三个臂集，各 3 轮交错 `ABBA,ABBA,BAAB`，每批 5 次证明，丢弃每臂首批与每批 run 1：
   - `spend` 1t @ `0x1`（`lazy=1`）、`spend` 8t @ `0xFFFF`（`lazy=1`，验证多线程路径不变）、`output` 1t @ `0x1`（`lazy=1`）。
4. **分析**：复用冻结协议的统计口径（池化中位、配对 ABBA 比较、精确符号检验、MWU、主机漂移守门）。

---

## 4. 不可外推边界与风险

| 项 | 说明 |
|---|---|
| 只对单线程生效 | `log_cpus == 0` 才走新路径；多线程下四步法是必需的，且 scratch 总量已是理论最小值（一个域大小），本目标**不声称**降低多线程峰值。 |
| 域尺寸依赖 | 节省量 = 一个域大小缓冲 = `2^log_n × size_of(T)`：Spend（2^17）= 4.19 MB，Output（2^13）= 262,144 B。Output 的收益绝对值小。 |
| 位等价性 | 结论依赖"四步法在 `log_cpus=0` 时恒等"这一**逐行可核对**的事实，并以 n = 2^10/2^13/2^17 的逐位断言 + 真实证明验证兜底；若断言失败按回退条款归档。 |
| 与目标 a 的关系 | 本目标不改变 shipped default 的全局峰值；组合验收留给目标 g，默认值切换需显式记录。 |
| 时间收益 | 省两趟全量遍历（shuffle、copy-back）与一次整域分配/清零；量级 ~1% 或更小，预注册只要求不退化 >1%。 |

---

## 5. 提交与产物

| 阶段 | 说明 |
|---|---|
| 侦察（插桩 + 原始数据） | 子阶段边界探针（默认关闭）+ 两组探针 run |
| 本预注册 | 独立提交，先于任何算法改动 |
| 实现 | `vendor/bellman/src/domain.rs` + 开关 |
| 数据 | 门禁日志、4 组探针台账 + 2 组对照台账、三个臂集 CSVs |
| 文档 | 结果文档 + 报告新章 + README / `weekly_summary.md` |
