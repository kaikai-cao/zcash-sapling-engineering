# In-situ 指数转换瞬态与窗口化表示的非零普查（2026-10-17）

> 覆盖任务：**三-2（in-situ 指数转换瞬态）**、**三-4（窗口化非零密度直接测量）**。
> 本轮新增了**可关闭**的插桩（默认零开销）；原始数据全部新增文件，不覆盖既有文件。

---

## 0. 一句话结论

1. **转换瞬态的"峰值增量"等于新建的 `Vec<Exponent>`，而不是"源 + 目标"。** 源 `Vec<Scalar>` 在转换前已经计入 live，`into_iter()` 期间它才被释放。之前的"瞬态 = 源 + 目标"描述的是**该窗口的绝对footprint**，不是**峰值的增量**——两者差一个源向量（Spend h：4.19 MB）。这是对既有表述的精化。
2. **in-situ ≠ 受控微测量**：Spend 的 `aux_assignment` 转换在真实流程里峰值增量 **9,361,800 B**，明显大于它自己的"源+目标"（7,101,936 B）——因为此时 **h 的 MSM 还在后台跑**（`h.wait()` 要到第 427 行才发生），它的桶/工作分配落进了同一个窗口。**峰值记账必须用 in-situ 数，不能用微测量数。**
3. **窗口化表示的非零密度是"高通"的，之前的"~94% / ~24%"是**模型产物**，不是事实。** 直接普查显示：
   - H query（n=131,071）：**100% 是 `Chunks`，且 22 个 chunk 槽里 99.35% 非零** → 实际上是**满密度**，之前算出的 ~94% 来自错误的字节模型；
   - L / A_aux / B_aux（n=98,638）：只有 **29.0% 是 `Chunks`**，另外 **37.9% 恰好是 0、33.1% 恰好是 1**（两者**不分配任何堆内存**）；在被 chunk 化的那部分里，槽占有率为 **99.37%** → 之前的"~24% 密度"其实是"**大部分指数是 0 或 1**"，不是"chunk 大量为零"。

---

## 1. 三-2 方法

`vendor/groth16/src/prover.rs` 的三处转换（原第 292/309/316 行）改为调用一个 `#[inline]` 包装函数 `collect_conversion(site, source_len, source_elem_size, iter)`：

- 由环境变量 **`SAPLING_IN_SITU_CONVERSION_PROBE=1`** 门控，默认关闭（关闭时只多一次 `OnceLock` 读取）；
- 开启时对每次转换做 `mem_probe::reset_peak()`，`collect()` 后读取 `peak()` 与 `live()`，打印一行
  `G16_IN_SITU_CONVERSION site=... n=... source_bytes=... converted_bytes=... live_before_bytes=... peak_delta_bytes=... live_after_delta_bytes=...`。

测量载体是新二进制 `experiments/prover-smoke/src/bin/in_situ_conversion_probe.rs`（装入 tracking `#[global_allocator]` + `mem_probe::enable()`），跑**真实的**一次 `create_proof` 并验证通过。
`SAPLING_IN_SITU_CIRCUIT=spend|output` 选择电路。

```powershell
$env:ZCASH_PARAMS_DIR='D:\Research\zcash-params'; $env:RAYON_NUM_THREADS='1'
$env:SAPLING_IN_SITU_CIRCUIT='spend'
.\experiments\prover-smoke\target\release\in_situ_conversion_probe.exe   # 进程亲和性 = 0x1
```

日志：`experiments/raw/logs/sapling_in_situ_conversion_{spend,output}_20261017.{stdout,stderr}.log`

---

## 2. 三-2 结果（1 线程 @ LP0）

类型尺寸：`Scalar` = **32 B**，`Exponent<Scalar>` = **40 B**。

### Spend

| site | n | 源 `Vec<Scalar>` (B) | 目标 `Vec<Exponent>` (B) | **峰值增量 (B)** | 结束后净增 (B) |
|---|---:|---:|---:|---:|---:|
| `h_exponents` | 131,071 | 4,194,272 | 5,242,840 | **5,242,840** | 1,048,536 |
| `input_assignment` | 8 | 256 | 320 | **320** | 64 |
| `aux_assignment` | 98,638 | 3,156,416 | 3,945,520 | **9,361,800** | 5,167,496 |

### Output

| site | n | 源 (B) | 目标 (B) | **峰值增量 (B)** | 结束后净增 (B) |
|---|---:|---:|---:|---:|---:|
| `h_exponents` | 8,191 | 262,112 | 327,640 | **327,640** | 65,496 |
| `input_assignment` | 6 | 192 | 240 | **240** | 0 |
| `aux_assignment` | 7,821 | 250,272 | 312,840 | **312,840** | 50,696 |

**解读**

1. **`h_exponents` 与 Output 三处：峰值增量 = 目标向量大小**，分毫不差。因为转换前 live 里**已经包含源向量**；`collect` 期间新增的只有目标向量，`into_iter` 结束后源才释放（净增 = 目标 − 源：Spend h 5,242,840−4,194,272 = 1,048,568，实测 1,048,536，差 32 B 属分配器粒度）。
2. **Spend `aux_assignment` 是唯一的例外（9,361,800 > 3,945,520）**：这一步执行时 **h 的 MSM 正在后台运行**（`multiexp` 在第 300 行派发，`h.wait()` 在第 427 行），其桶数组/工作缓冲与该转换**共享同一个时间窗**。所以 in-situ 峰值增量 = 转换自己 3.95 MB **加上** 并发 MSM 的约 5.42 MB。
3. **与受控微测量的对照**（`exponent_conversion_memory.rs`）：

   | 项 | 受控微测量（源+目标） | in-situ 峰值增量 |
   |---|---:|---:|
   | Spend h | 9,437,112 | 5,242,840 |
   | Spend aux | 7,101,936 | **9,361,800** |

   → 两者**不可互换**：微测量给的是"孤立转换的绝对 footprint"，in-situ 给的是"真实流程里的峰值增量"。**峰值账本用后者**；前者只在解释"源+目标=多少"时有意义。

---

## 3. 三-4 方法

在 `vendor/bellman/src/multiexp.rs` 的**既有** `SAPLING_MEM_PROBE=1` 门控内，对窗口化预处理（`Exponent::chunks(c)`）增加一次**普查**：统计 `Zero` / `One` / `Chunks` 各多少个，以及 `Chunks` 里**零槽 / 非零槽**各多少。普查关闭时零开销。
普查字段加入既有的 `BELLMAN_MSM_MEM_PROBE` 行，并额外打印 `exponent_size_bytes` 与 `chunked_exponent_size_bytes`，使字节模型可以**闭合验证**。

命令（1 线程 @ LP0，`SAPLING_PROFILE=1` + `SAPLING_MEM_PROBE=1`）：

```powershell
$env:SAPLING_MEM_PROBE='1'; $env:SAPLING_PROFILE='1'; $env:RAYON_NUM_THREADS='1'
$env:SAPLING_PROVER_RUNS_CSV="$PWD\experiments\raw\csv\sapling_prove_memory_ledger_exponent_density_20261017.csv"
.\experiments\prover-smoke\target\release\prove_memory_ledger.exe
```

日志：`experiments/raw/logs/sapling_exponent_density_census_20261017.{stdout,stderr}.log`

---

## 4. 三-4 结果（直接普查）

| 调用 | n | c | chunks/指数 | `Zero` | `One` | `Chunks` | 非零槽 | 零槽 | **槽非零率** | prep live 增量 (B) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **H query (G1)** | 131,071 | 12 | 22 | 0 | 0 | **131,071 (100%)** | 2,864,709 | 18,853 | **99.35%** | **26,218,896** |
| L / A_aux / B_aux (G1/G2) | 98,638 | 12 | 22 | **37,409 (37.9%)** | **32,648 (33.1%)** | 28,581 (29.0%) | 624,833 | 3,949 | **99.37%**（仅在 `Chunks` 内） | 7,397,608 |
| A_input / B_input | 8 | 3 | 85 | 0 | 2 (25%) | 6 (75%) | 458 | 58 | 89.8% | 4,360 |

（H 与 L/A/B 的值在 5 次 prove × 8 次调用里完全稳定，逐次一致。）

**字节模型闭合验证**（`ChunkedExponent` = **24 B**，`Exponent<Scalar>` = 40 B）

| 调用 | 模型：外层 `n×24` + 堆 `槽数×8` | 实测 prep 增量 | 残差 |
|---|---:|---:|---:|
| H | 131,071×24 + 2,883,562×8 = 3,145,704 + 23,068,496 = **26,214,200** | 26,218,896 | **+4,696** |
| L | 98,638×24 + 628,782×8 = 2,367,312 + 5,030,256 = **7,397,568** | 7,397,608 | **+40** |

模型闭合到分配器粒度，说明普查计数是可信的。

**纠正之前的推断**

| 项 | 之前的推断（从字节数反推） | 直接普查 | 结论 |
|---|---|---|---|
| H query 非零密度 | ~94% | **99.35%**（且 100% 为 `Chunks`） | 94% 是"假设外层 32 B/元素、且始终存满 22 槽"的模型产物 |
| L/A_aux/B_aux 非零密度 | ~24% | `Chunks` 内 **99.37%**；但只有 **29.0%** 的指数是 `Chunks` | "低密度"来自 **0/1 指数**（71%），不是零 chunk |

**对优化方向的影响（重要）**

- **H 的 ~26 MB 窗口化缓冲无法靠"跳过零 chunk"缩小**：只有 **0.65%** 的槽是零。要缩小它只能：
  (a) **不要物化**整个窗口化表示（按需生成 chunk / 分块惰性展开）；
  (b) 换成 bit-slice / signed-digit 表示；
  (c) **减小 c**（槽数 ∝ ⌈255/c⌉，但桶数 ∝ 2^c，需权衡时间）。
- **L / A_aux / B_aux 的 0/1 短路本来就有效**：71% 的指数零堆分配。任何针对这些调用的"省内存"改动收益上限有限。
- 因此**内存优化目标应集中在 H query**，这与 `sapling_prove_memory_ledger_20261017.md` 的峰值归属一致。

> **口径修正与后续（2026-10-18 追记，见报告 §21.6）：** 上表 c=12 的 `26,218,896 B` 是**毛值**（闭合到模型 `3,145,704 + 23,068,496 = 26,214,200`，残差 +4,696）。此前同一缓冲还出现过 25,970,216 B（报告 §13.2/§13.5 的受控/台账值）与 22.0 MB / 19.9 MB（台账 off/on 臂）——差异来源是 `exponent_prep_live_delta_bytes` 为**净值**，测点时源 `Vec<Scalar>`（4,194,304 B = 精确 4 MiB）若已释放就整体少一个源向量。**引用一律用「外层 + 堆」毛值**：c=12 = 26,214,200 B；有符号 c=13（当前默认）= **24,117,064 B**。
>
> 方向 (a) 已实现并通过预注册验收但**未达标**：只预存进位位后该缓冲 24,117,064 → **327,680 B**（现场瞬态 −23,789,344 B），端到端时间反而 −4.60%（1t）/ −8.52%（8t）/ −1.90%（Output）；但 prove 峰值只降 **12.93 MB**（阈值 15 MB），因为存在一个与本缓冲无关的 **90.13 MB 独立天花板**（`qap_fft_h_exponent_prep` 阶段，两臂逐字节相同）。方向 (c)「减小 c」经核算为净亏（桶数 ∝ 2^c 增长快于槽数缩减）。

---

## 5. 复现凭证

| 项 | 值 |
|---|---|
| in-situ 二进制 | `experiments/prover-smoke/target/release/in_situ_conversion_probe.exe` |
| 新增插桩 | `vendor/groth16/src/prover.rs`（`SAPLING_IN_SITU_CONVERSION_PROBE`）、`vendor/bellman/src/multiexp.rs`（普查字段）、`experiments/prover-smoke/src/bin/prove_memory_ledger.rs`（`SAPLING_PROVER_RUNS_CSV` 覆盖） |
| 参数 SHA-256 | spend `8e48ffd2…fc13`；output `2f0ebbcb…f0e4` |
| 新增原始 CSV | `experiments/raw/csv/sapling_prove_memory_ledger_exponent_density_20261017.csv` |
| 交叉验证 | 该 run 的 `prove_peak_abs_bytes` = 105,160,208，与既有账本 105,160,229 一致（差 21 B），说明插桩未破坏原测量 |

---

## 6. 限制

1. in-situ 转换探针会调用 `reset_peak()`，因此在**开启**该探针的进程里，外层"整段 prove 峰值"不可用（本文件的 in-situ 运行不使用外层峰值；峰值账本由不带该探针的 `prove_memory_ledger` 提供）。
2. 普查是**单线程**（`RAYON_NUM_THREADS=1`）下的逐调用统计；多线程时各调用并发，逐调用计数仍准确（每个调用独立计数），但**峰值**归属不可用（沿用既有账本的说明）。
3. `live_start` 在极少数 run 间会有约 4 MB 级别的差异（分配器复用时机），导致 `prep live 增量` 随之偏移；**普查计数（批内 100% 稳定）不受影响**，故结论以计数为准、以增量为辅。
4. 字节模型里的 24 B / 40 B 是本机本工具链（rustc 1.98.1）下的实测尺寸，换工具链需重测。
