# 预注册：H query 窗口化表示「去物化」（目标 a）— 2026-10-18

> 本文件按 `sapling_optimization_validation_protocol_20261017.md` §5 的模板，**在动任何算法代码之前**填写并冻结。
> 一旦冻结，验收阈值与判定规则**不得修改**；实现与测量中若发现标准写错，只能在结果文档里标注，不能在本文档里改。

---

## 0. 一句话

目标 a 的机制选定为 **只预存进位位（carry bits），把窗口数字的折叠挪到 fill 循环里即时做**：H query（n=131,071，c=13）的窗口化缓冲从 **24.1 MB 降到 0.33 MB**，预计 Spend 单线程 prove 峰值从 **103.06 MB 降到 ~79.3 MB（−23.8 MB / −23%）**，时间要求不退化。

---

## 1. 目标与选定机制

| 项 | 内容 |
|---|---|
| 目标 | **a：H query 的内存主因**（报告 §10.1 / §11.4 已确认峰值落在 H query G1 MSM 的窗口化指数缓冲上） |
| 机制 | 有符号重编码**只预计算进位**（1 bit / 窗口 / 指数），窗口数字在 fill 时由「源位段 + 该窗口的进位位」即时折叠 |
| 不选其它机制的理由 | 见 §2.3 |

### 1.1 关键结构事实（本次侦察实测，决定设计）

`multiexp_inner` 的并行轴是**窗口**，不是"region"：

```rust
let parts = (0..window_count as u32).into_par_iter()   // 20 个窗口并行
    .map(|chunk| this(bases.clone(), density_map.clone(), chunked_exponents.clone(), chunk as usize))
```

⇒ **窗口乱序并发**，因此"按窗口顺序滚动推进进位数组"**不可行**：进位必须在填桶开始前一次算完，之后只读。
（这是本次侦察推翻的第一版设计；把它记在这里，避免后续再走一遍。）

### 1.2 机制细节

现有 `chunks_signed`（`vendor/bellman/src/multiexp.rs:528`）是：

```
carry = 0
for j in 0..windows:
    window = raw_chunk_j + carry          // raw ∈ [0, 2^c-1]，window ∈ [0, 2^c]
    if window > 2^(c-1): d = window - 2^c; carry = 1
    else:                d = window;       carry = 0
    slot = d + 2^(c-1)                    // 偏置存储
```

进位链是纯 1 bit 递推（`carry_{j+1} = 1 ⟺ raw_j + carry_j > 2^(c-1)`）。因此：

- **预计算**：一趟顺序扫描，只写**进位位图** `carry: Vec<u64>`（位打包，n×windows bit ≈ 0.33 MB），不写数字；
- **fill 时**：对窗口 j、指数 e，`raw = bits_e[c·j .. c·j+c]`（O(1) 位段取，**不是** `.chunks(c).nth(j)`，后者是 O(j)），再折叠出 `d`，装桶；
- 0 / 1 短路**不变**：直接 match 已有的 `Exponent::Zero / One / Bits`，不需要额外标签数组。

与现有偏置槽表示**逐位等价**：`d == 0 ⟺ slot == 2^(c-1)`、`d > 0 ⟺ slot > 2^(c-1)`、`d < 0 ⟺ slot < 2^(c-1)`。

---

## 2. 证据基础（本次动手前已实测）

### 2.1 峰值归属：窗口化缓冲是 prove 期的最大单笔

`prove_memory_ledger`（1t@`0x1`，`SAPLING_PROFILE=1 SAPLING_MEM_PROBE=1`）：`live_before_prove` 68.73 MB → `prove_peak_abs` **105.16 MB**（无符号臂）/ **103.06 MB**（有符号臂当前默认）。

### 2.2 该缓冲的**正确口径**（本次重新闭合，取代此前的三个不一致数字）

结构：`enum ChunkedExponent { Zero, One, Chunks(Vec<u64>) }`（`multiexp.rs:464`）

- **外层** = 24 B/指数（`Vec<u64>` 头 + 判别式，无 niche 压缩）；
- **堆** = `chunk_count × 8 B`/指数（`Chunks` 为稠密 `u64` 向量，**槽数恒为 n × chunk_count**）。

| 配置 | 外层 (24 B×n) | 堆 (8 B×n×chunks) | 合计 |
|---|---:|---:|---:|
| 无符号 c=12（历史规则） | 3,145,704 | 23,068,496 | **26,214,200 B** |
| **有符号 c=13（当前默认）** | 3,145,704 | 20,971,360 | **24,117,064 B** |

**此前 26.2 / 22.0 / 19.9 MB 三个数字的来源已查明**：`exponent_prep_live_delta_bytes` 是**净值**，测点时源 `Vec<Scalar>`（4,194,304 B = 精确 4 MiB 容量）若已释放，整体就少 4 MiB。因此：

- 26.2 MB（普查 run，c=12）= 毛值；
- 22.0 MB（台账 off 臂，c=12）= 毛值 − 源；
- 19.9 MB（台账 on 臂，c=13）= 毛值 − 源。

三者在各自口径下都自洽（残差为分配器粒度 +4,696 B），但**引用时必须写"外层 + 堆"的毛值**。本预注册以 **24,117,064 B（c=13）** 为目标 a 的基线。

### 2.3 为什么不去做别的

| 候选机制 | 实测/推理 | 结论 |
|---|---|---|
| 跳过零 chunk | H query 槽非零率 **99.35%**（有符号下零槽仅 595 个） | **无效**，缓冲是满密度的 |
| 减小 c（减 chunk 数） | c=16 → chunks 16（省 4.2 MB），但桶数 2^15=32768 → 桶数组 **+4.1 MB**，且填桶次数 3.15M vs 2.79M（**−13% 时间**） | **净亏** |
| 打包成 13-bit/槽 | 堆 21.0 → ~4.3 MB，但保留外层 3.1 MB 与 prep 扫描，且每槽多一次解包 | 次优，作为本方案的**回退变体** |
| 逐窗口重算进位链 | 窗口并行 ⇒ 每个窗口要 O(j) 重算，总计 O(w²/2)=200 步/指数（现 20 步）⇒ **+10× 提取工作** | **放弃**（并入 §1.1） |
| **仅预存进位位（本方案）** | 工作量与现方案**同量级**（提取从 prep 挪到 fill，总遍数不变），但**省掉 131,071 次小分配与 21 MB 堆读写** | **采用** |

### 2.4 时间预期（不承诺收益）

- 去掉：131,071 次 `Vec<u64>` 分配/释放、21.0 MB 的写入与 20 遍跨步读（当前每窗口按 160 B 步长读 8 B）；
- 增加：每槽一次位段提取 + 一次折叠（比较/选择），估计 2.6M 槽 × 数 ns ≈ **个位数 ms**；
- ⇒ **净时间预期：中性或略好，但幅度很可能 <3%（不可认证）**。因此本目标按**内存口径**验收，时间只作**不退化守门**。

---

## 3. 改动清单（预计）

| 文件 | 改动 |
|---|---|
| `vendor/bellman/src/multiexp.rs` | 新增 `carry_bits(c)`（一趟扫描只产出位打包进位数组）；`multiexp_inner` 在开启时改为把 `Arc<Vec<Exponent>>` + `carry: Arc<[u64]>` 传给 `this`；fill 循环按窗口即时折叠（含 0/1 短路）；新增进程级开关 |
| `experiments/prover-smoke/src/bin/msm_window_bench.rs` | 增加第二条开关的 A/B 与"两种实现结果必须逐位相同"的断言（c = 2..=20、n = 131,071） |
| 开关 | **`SAPLING_MSM_LAZY_RECODING`**（进程级；`0` = 现状物料化，`1` = 仅进位位）。**A/B 用同一二进制 + 该开关**，避免重建混杂。实现落地时默认 `0`；结果通过后再改默认 `1` |

**不改**：`chunks`（无符号）路径、reduce 的 summation-by-parts、桶数组大小与桶下标语义、`zero_digit_slot` 相关口径、任何 `vendor/groth16` 代码、参数与电路。

---

## 4. 预声明验收标准（冻结）

| 字段 | 内容 |
|---|---|
| 目标 | a（H query 窗口化表示的内存占用） |
| 改动文件 | `vendor/bellman/src/multiexp.rs`、`experiments/prover-smoke/src/bin/msm_window_bench.rs` |
| 假设 | 窗口数字由 64 bit/槽 降为 1 bit/槽（转成进位位）后，H query 的窗口化缓冲从 24.1 MB 降到 0.33 MB，且因为工作量同量级，端到端时间不退化 |
| **主验收指标（内存）** | `prove_peak_abs_bytes`（`prove_memory_ledger`，1t@`0x1`，n≥5，同二进制开关 off=A / on=B）中位下降 **≥ 15 MB**（预期 ~23.8 MB） |
| 辅助指标 1 | H query 的 `exponent_prep_live_delta_bytes` 下降 **≥ 20 MB**；`BELLMAN_MSM_MEM_PROBE` 的 H query 新字段（进位位图字节数）≤ 0.4 MB |
| 辅助指标 2（守门） | Spend 端到端 1t@`0x1` 暖态中位**不退化 >1%**（ABBA 配对 ≥5 对） |
| 辅助指标 3（守门） | 8t@`0xFFFF` 与 Output 1t@`0x1` 中位**不退化 >1%** |
| 正确性 | ① 每批 5/5 `verified=true` 且 `proof_bytes=192`；② 微基准里**两种实现（物料化 / 进位位）的 MSM 结果在 c = 2..=20 每个宽度、n = 131,071 整规模下逐位相同**；③ 64 项前缀与朴素 double-and-add 相同；④ 参数哈希与电路规模不变 |
| 回退条件 | 任一正确性项失败 → 立即回退该改动；主指标 <15 MB → 记为"局部改动未转化为峰值下降"并归档（默认值保持 `0`） |
| 预期样本量 | A/B 各 ≥3 批 × 5 次证明，ABBA 交错 3 轮（`ABBA,ABBA,BAAB`）≥5 对；内存台账 out/on 各 n=5 |
| 预声明日期 | 2026-10-18 |
| 冻结时二进制 | **实现前**：`prove_memory_ledger.exe` `0055ff01fc5511555226d2641985a376aabac199781dba5e87760fbf9f394904`；`spend_prover_smoke.exe` `e498c6059a082275517a4bcc35c4fdaf9153031ff78aa31099f2c21faed63b62`；`sapling-output-smoke.exe` `cd7f576c0b2ec511ee191fba0ea0fc57fe6fc0f1805092798d071097998d064c`；`msm_window_bench.exe` `cd257acdf87e45a6b4e29c0eb7afe36ed76f8e84039dea093243054e42aedb54` |
| 基线（A 臂）口径 | 有符号 c=13 现状：H query 窗口化缓冲 **24,117,064 B**；`prove_peak_abs_bytes` 中位 **103,062,954 B**（2026-10-17 台账 on 臂） |
| 本预注册的提交 | 本文件单独一个提交（先于任何代码改动）；提交哈希记录在结果文档里 |

**通过判据**：主指标达标 **且** 辅助指标 2/3 无 >1% 退化 **且** 正确性全过。
**不通过但有效**：主指标未达标但辅助指标 1 显著改善 → 记为"缓冲确实缩小但峰值未转化"，归档。

---

## 5. 风险与回退

| 风险 | 处置 |
|---|---|
| 位段随机访问不可用（`FieldBits` 只暴露 `chunks()` 迭代器，取第 j 段是 O(j)） | 先验证 `&bits[c·j .. c·j+c]` 可用；若不可用则退回**打包变体**（§2.3 第 3 行），并在此预注册中标注"机制降级"（阈值不变） |
| fill 热路径变慢（折叠开销 > 分配与内存流量节省） | 由辅助指标 2 守门；若 >1% 退化则记"内存达标但时间退化"，默认值保持 `0` |
| 与目标 b 的交互 | 两者都在同一函数内，但互不改变对方语义；正确性 ② 在**每条路径的组合**上断言 |
| 峰值不降反升（进位位图与源向量同时存活） | 源 `Vec<Exponent>` 本就存活（5.24 MB，已计入基线），位图 0.33 MB；预期净降 23.8 MB。若实测不降，按"不通过但有效"归档 |

---

## 6. 复现与数据留存

- 数据留存按协议 §5：新增 raw CSV / 日志 / metadata，**不覆盖**既有文件；提交按「代码 / 数据 / 文档」拆分。
- 预期新增文件：
  - `experiments/raw/csv/sapling_prove_memory_ledger_msm_lazy_recoding_{off,on}_20261018.csv`
  - `experiments/raw/csv/sapling_spend_prover_runs_msm_lazy_recoding_primary_{off,on}.csv`
  - `experiments/raw/logs/msm_window_bench_final_lazy_{off,on}_20261018.log`
  - `experiments/metadata/sapling_msm_lazy_recoding_results_20261018.md`
  - `results/tables/sapling_msm_lazy_recoding_*.csv`
- 环境：Windows 11 / i7-14700 / `rustc 1.98.1`；1t 掩码 `0x1`、8t 掩码 `0xFFFF`；参数哈希 spend `8e48ffd2…`、output `2f0ebbcb…`。
- 二进制必须**全量** `cargo build --release --bins` 重建并记录哈希（上一目标曾因单 `--bin` 重建导致台账作废，见 `sapling_msm_signed_digit_results_20261017.md` §9）。
