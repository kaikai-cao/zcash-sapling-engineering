# 侦察：当前默认配置的阶段分解与合成容量实测（内存线结项）— 2026-10-18

> 本文是**预注册前的侦察记录**，不是任何优化目标的判定。目的是：在目标 g 翻转默认值
> （`SAPLING_MSM_LAZY_RECODING=1` + `SAPLING_FFT_SERIAL_SINGLE_THREAD=1`，提交 `d4ed1df`）
> 之后，按既定方法论对新的 shipped default 做阶段分解，确认下一个内存目标是否存在
> 机制干净的候选。结论：**内存线到达结构性地板，不再设立内存目标**。

---

## 0. 数据来源与口径

| 项 | 值 |
|---|---|
| 配置 | 翻转后默认，**不设任何开关环境变量**（= lazy=1 + fix=1） |
| 台账批次 | `experiments/raw/csv/sapling_prove_memory_ledger_default_phase_probe_20261018.csv`（5 次运行） |
| 阶段探针 | `SAPLING_G16_MEM_PHASE_PROBE=1` |
| 容量探针 | `SAPLING_G16_SYNTH_CAPACITY_PROBE=1`（新增，见 §4） |
| 线程/亲和 | RAYON_NUM_THREADS=1，亲和 0x1 |
| 二进制 | 翻转后重编译（提交 `d4ed1df` 记录哈希） |
| 验证 | 5/5 verified，192 B |

**探针口径警告（照录 groth16 源码注释）**：阶段探针启用时会在每个阶段边界重置水位线，
因此台账 CSV 的 `prove_peak_abs_bytes` 在探针下**无效**（本批 CSV 显示 69,126,795 B，
只是最后一段的局部水位）；权威数据是 per-phase 行的 `running_max_abs_bytes`。
它与无探针台账的中位 86,184,614 B 相差 11 B（分配器粒度），互为印证。

---

## 1. 阶段分解：全局峰值的归属

按阶段峰值中位数（5 次运行，计数类字段跨运行完全确定）：

| 阶段 | live 中位 | 阶段峰值中位 | 阶段内增量 |
|---|---:|---:|---:|
| pre_body | 69,126,075 | 69,126,075 | 0 |
| **circuit_synthesis** | 85,935,067 | **86,184,603** | 249,536 |
| worker_vk_setup | 85,935,899 | 85,935,899 | 0 |
| qap_domains_built | 85,935,899 | 85,935,899 | 0 |
| qap_ffts_done | 85,935,971 | 85,935,971 | 72 |
| qap_mul_ab_done | 81,741,595 | 85,935,939 | 4,194,344 |
| qap_sub_c_done | 77,547,291 | 81,741,635 | 4,194,344 |
| qap_divide_icoset_done | 77,547,291 | 77,547,363 | 72 |
| qap_into_coeffs_done | 77,547,291 | 77,547,291 | 0 |
| qap_fft_h_exponent_prep | 78,595,867 | 82,790,131 | 4,194,264 |
| h_query_access_dispatch | 78,596,787 | 78,596,787 | 0 |
| assignment_query_prep_dispatch | 73,094,987 | **82,870,091** | 9,775,104 |
| proof_scalar_terms | 73,094,987 | 73,094,987 | 0 |
| wait_and_assembly | 69,126,795 | 74,522,645 | 5,395,850 |

**全局峰值 86,184,603 B 归属 `circuit_synthesis` 末端**（合成结束、 enforce 输入一致性
循环结束时活存达峰）。第二高阶段峰值为 `assignment_query_prep_dispatch` 的
82,870,091 B ⇒ 物理可转化上限 = 86,184,603 − 82,870,091 = **3,314,512 B**。

峰值构成（实测分解）：

| 成分 | 字节 | 说明 |
|---|---:|---|
| 反序列化 SpendParameters | 60,818,440 | 台账 `live_after_load_delta_bytes`，整个证明期必需 |
| 见证/密钥准备 | ≈ 7,911,425 | `live_before_prove` − 加载后活存：prepared_vk、Spend 电路实例、Merkle 路径等 |
| 赋值向量容量 | 16,777,472 | a/b/c + input/aux 的 **capacity**（见 §2） |
| 合成瞬态 | 249,536 | 峰值 − 阶段结束活存 |

---

## 2. 合成容量实测：16.78 MB 里只有 1.04 MB 是真余量

新增容量探针（`SAPLING_G16_SYNTH_CAPACITY_PROBE=1`，`vendor/groth16/src/prover.rs`），
在 `circuit_synthesis` 边界打印五个向量的 len/capacity。5 次运行**逐字节确定**：

| 向量 | len | capacity | 实际字节 | 容量字节 | 余量 |
|---|---:|---:|---:|---:|---:|
| a / b / c（各） | 98,785 | 131,072 | 3,161,120 | 4,194,304 | 1,033,184 ×3 |
| input_assignment | 8 | 8 | 256 | 256 | 0 |
| aux_assignment | 98,638 | 131,072 | 3,156,416 | 4,194,560 | 1,037,888 |

- a/b/c + aux 的 capacity 全部是 **131,072 = 2^17**——push 倍增从 65,536 跳过来的落点，
  同时也是 QAP 域大小（98,785 的上界 2 的幂）。
- **a/b/c 的 3.10 MB「余量」不是余量**：`EvaluationDomain::from_coeffs` 的
  `coeffs.resize(131,072, zero)` 原地填零、整体移入域，缓冲区被 100% 利用。
  若预留下精确长度（98,785），resize 会在 QAP 阶段触发重分配，瞬态
  old+new ≈ 7.35 MB/向量，且三个向量依次重分配会把峰值抬到 ≈87.0 MB（**高于**当前峰值）。
- **唯一真余量是 aux 的 1,037,888 B**：aux 的下游消费者（`Vec<Exponent>` 转换）不要求
  131,072 长度。但在峰值点释放它只有两条路，都不可行：
  1. `shrink_to_fit`：重分配瞬态 = 峰值点活存 + 新缓冲 ≈ 85.93M + 3.16M = **89.09 MB**，
     反而把峰值抬高约 2.9 MB；
  2. 预知 aux 数量后预分配：需要合成前知道见证数——通用 bellman 无干净机制
     （干跑计数一遍 = 多一次完整合成，时间成本远超 1% 预算；硬编码常数则随
     zcash_proofs 版本漂移，且猜错时余量原样返回）。

---

## 3. 结论：内存线到达结构性地板

1. 全局峰值 86.18 MB = 60.8 MB 参数（必需）+ 7.9 MB 见证准备（必需）+
   16.78 MB 赋值容量（其中 15.74 MB 为域缓冲区/数据本身，1.04 MB 为不可释放的真余量）+
   0.25 MB 合成瞬态。
2. 物理可转化上限 3,314,512 B **不可达**：a/b/c 容量即域大小（动了更差），
   aux 真余量无干净释放机制；即使假设全部真余量可去，峰值也只落到 ≈85.14 MB。
3. 基线侧（参数 60.8 MB）在峰值时刻全部在役，无渐进释放空间；
   7.9 MB 见证准备均为证明必需。
4. 按协议纪律（阈值必须有机制支撑，不重复目标 a 的「阈值无机制」错误），
   **不再设立内存优化目标**。后续如要对 `assignment_query_prep_dispatch`
   （阶段峰值 82.87 MB，增量 9.78 MB）做优化，按 §1 数据它低于全局峰值，
   **不改变 shipped default 的 prove 峰值**，只能作为时间目标。

---

## 4. 工具链备注

- 容量探针代码：`vendor/groth16/src/prover.rs`，环境变量
  `SAPLING_G16_SYNTH_CAPACITY_PROBE=1`，默认关闭，关闭时每证明一次 `OnceLock` 读。
- 本次台账日志按 UTF-8 捕获（`[IO.File]::WriteAllText`），规避 PowerShell
  `>` 重定向写 UTF-16LE 的问题（见周报 §16.2）。
- 原始数据：`experiments/raw/csv/sapling_prove_memory_ledger_default_phase_probe_20261018.csv`、
  `experiments/raw/csv/sapling_prove_memory_ledger_synth_capacity_20261018.csv`、
  `experiments/raw/logs/sapling_prove_memory_ledger_{default_phase_probe,synth_capacity}_20261018.log`。
