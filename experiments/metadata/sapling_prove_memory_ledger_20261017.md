# Sapling Prove 阶段内存账本实测记录（Prove memory ledger）

**归档日期：** 2026-10-17
**用途：** 用真实分配器计数补齐 `docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md` §12.4 的第 1、2、3 项测量缺口。
**口径：** 进程级 `#[global_allocator]` 统计的 live/peak 字节增量；单次运行的观测值，不是通用上界。

## 0. 本次新增的插桩与工具

| 文件 | 作用 |
|---|---|
| `vendor/bellman/src/mem_probe.rs`（新增） | 进程级分配计数（live/peak），默认关闭，零开销 |
| `vendor/bellman/src/lib.rs` | 注册 `pub mod mem_probe;` |
| `vendor/bellman/src/multiexp.rs` | `SAPLING_MEM_PROBE=1` 时输出 `BELLMAN_MSM_MEM_PROBE` |
| `experiments/prover-smoke/src/bin/prove_memory_ledger.rs`（新增） | 安装计数型全局分配器，跑参数加载 + 5 次 Spend 证明 |
| `experiments/prover-smoke/src/bin/exponent_conversion_memory.rs`（新增） | 复刻 groth16 的 `Scalar → Exponent` 转换并测其瞬态 |

> 插桩全部可由环境变量关闭：未设置 `SAPLING_MEM_PROBE=1` 时，`mem_probe` 的钩子只做一次 relaxed 原子读，原路径行为不变。

## 1. 运行命令

```powershell
$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'
cargo build --release --offline --manifest-path .\experiments\prover-smoke\Cargo.toml `
  --bin prove_memory_ledger --bin exponent_conversion_memory

# 单线程（Per-call 归属干净）
$env:SAPLING_MEM_PROBE='1'; $env:SAPLING_PROFILE='1'
$env:SAPLING_MSM_STAGE_TIMING='0'; $env:SAPLING_MSM_BRANCH_COUNTS='0'
$env:RAYON_NUM_THREADS='1'
.\experiments\prover-smoke\target\release\prove_memory_ledger.exe

# 8 线程（看并行峰值抬升）
$env:RAYON_NUM_THREADS='8'
.\experiments\prover-smoke\target\release\prove_memory_ledger.exe

# 指数转换微测量（无需参数文件，瞬时完成）
.\experiments\prover-smoke\target\release\exponent_conversion_memory.exe
```

## 2. 原始证据文件

| 内容 | 文件 |
|---|---|
| 主账本 CSV（1 线程 + 8 线程，batch 级） | `experiments/raw/csv/sapling_prove_memory_ledger.csv` |
| 1 线程 stdout | `experiments/raw/logs/sapling_prove_memory_ledger_spend_1t_*.log` |
| 1 线程 MSM 内存探针 stderr | `experiments/raw/logs/sapling_prove_memory_ledger_spend_1t_*.memprobe.log` |
| 8 线程 stdout | `experiments/raw/logs/sapling_prove_memory_ledger_spend_8t_*.log` |
| 8 线程 MSM 内存探针 stderr | `experiments/raw/logs/sapling_prove_memory_ledger_spend_8t_*.memprobe.log` |
| 指数转换微测量 | `experiments/raw/logs/sapling_exponent_conversion_memory_*.log` |

批次（batch_id = 起始毫秒时间戳）：
- 1 线程批：`1792225715131`
- 8 线程批：`1792225858191`
- 环境：i7-14700，31.7 GiB，Windows 11，Rust release。

## 3. 缺口 1：Prove 阶段独占峰值工作集（Spend）

`live_baseline_bytes = 1,073`（跟踪启用后、加载前的基线）。

| 锚点 | 1 线程 | 8 线程 |
|---|---:|---:|
| 参数读取+验证耗时 | 47,890.664 ms | 51,603.612 ms |
| 加载期峰值增量 | 60,818,440 B (58.001 MiB) | 同 |
| 加载后常驻 live | 60,818,440 B (58.001 MiB) | 同 |
| `prepared_vk` 峰值增量 | 40,000 B | 40,000 B |
| 证明前常驻 `live_before_prove` | 68,729,865 B (65.548 MiB) | 同 |
| Prove 期峰值增量 | 36,034,144–36,428,784 B (34.37–34.74 MiB) | 71,605,766–72,603,548 B (68.29–69.24 MiB) |
| Prove 期**绝对** live 高水位 | 105,160,229–105,161,797 B (100.29–100.31 MiB) | 140,781,251–141,370,967 B (134.26–134.82 MiB) |
| 证明后仍新增常驻（run1 / run2-5） | 393,408 B / 0 B | 442,760 B / 0 B |

**关键结论：**

1. 加载参数的实际常驻 = **60,818,440 B (58.001 MiB)**，与静态估算的 capacity_payload `60,819,152 B` 仅差 **712 B**，静态账本得到实测确认。
2. 单线程 Prove 期绝对高水位 **100.29 MiB**，与既有整进程 `PeakWorkingSet64 = 101.30 MiB` 吻合（分配器 live 略低于 WS，合理）；即“整进程 101 MiB 主要就是参数常驻 + Prove 瞬时峰值”，不是两个叠加的不同峰。
3. **并行会抬升瞬时内存**：1→8 线程，Prove 峰值增量从 ~34.5 MB 升到 ~68.8 MB，绝对高水位从 100 MiB 升到 135 MiB（见 §6 主因）。
4. 峰值落点在 **H query 的 MSM 调用内部**：H 调用进入时 live=78,596,989 B，窗口化表示后 live=104,567,205 B，再加 1 个 G1 桶数组 589,680 B = 105,156,885 B ≈ 观测峰值 105,160,229 B（差 3,344 B，分配抖动）。

## 4. 缺口 2：MSM 桶数组实际分配/生命周期（单线程实测）

每行来自 `BELLMAN_MSM_MEM_PROBE ...`（1 线程批，逐次调用）：

| 调用 | 指数数 | window c | bucket_count | chunk_count | 元素字节 | 单桶数组实测 | 静态值 | 一致 |
|---|---:|---:|---:|---:|---:|---:|---:|:--:|
| H query (G1) | 131,071 | 12 | 4,095 | 22 | 144 | 589,680 | 4,095×144=589,680 | ✓ |
| L / A_aux (G1) | 98,638 | 12 | 4,095 | 22 | 144 | 589,680 | 589,680 | ✓ |
| A_input (G1) | 8 | 3 | 7 | 85 | 144 | 1,008 | 7×144=1,008 | ✓ |
| B_aux (G2) | 98,638 | 12 | 4,095 | 22 | 288 | 1,179,360 | 4,095×288=1,179,360 | ✓ |
| B_input (G2) | 8 | 3 | 7 | 85 | 288 | 2,016 | 7×288=2,016 | ✓ |

**生命周期：** 桶数组在 chunk 闭包内 `vec![G::identity(); bucket_count]` 一次性分配，闭包返回即释放（H 调用 `live_end_delta ≈ live_after_exponent_prep_delta`，说明调用结束时保留的是窗口化指数缓冲，而不是桶）。单线程时同一时刻只有一个 chunk 的桶存活，故“桶并发峰值”退化为单桶；8 线程时 `bucket_alloc_max` 会被其它并发调用的分配污染（观测到 2,662,144 / 1,769,040 等），此时只能用进程级峰值衡量，见 §6。

> 即：**静态桶内存估算被逐一证实到字节**；但桶数组**不是**并行内存增量的主因（G2 全并发上限也仅 ~9 MB）。

## 5. 缺口 3：`Exponent<Scalar>` 转换瞬态（微测量）

复刻 `vendor/groth16/src/prover.rs` 第 292 / 309 / 316 行的 `source.into_iter().map(Into::into).collect::<Vec<Exponent>>()`：

| 向量 | n | source `Vec<Scalar>` | converted `Vec<Exponent>` | 转换瞬态合计 | 转换后常驻 |
|---|---:|---:|---:|---:|---:|
| Spend input (line 309) | 8 | 256 | 320 | 576 | 320 |
| Spend aux (line 316) | 98,638 | 3,156,416 | 3,945,520 | 7,101,936 (6.77 MiB) | 3,945,520 |
| Spend h (line 292) | 131,071 | 4,194,272 | 5,242,840 | 9,437,112 (9.00 MiB) | 5,242,840 |
| Output input | 6 | 192 | 240 | 432 | 240 |
| Output aux | 7,821 | 250,272 | 312,840 | 563,112 | 312,840 |
| Output h | 8,191 | 262,112 | 327,640 | 589,752 | 327,640 |

说明：`Vec::into_iter()` 期间源缓冲仍存活，因此转换的**瞬态 = 源 + 目标**；`collect` 结束后源释放，只剩目标 `Exponent` 向量（`Scalar`=32 B，`Exponent<Scalar>`=40 B）。Spend 的每次转换是 **7–9 MB 量级的有界瞬态**，远小于 §6 的窗口化表示。

## 6. 新发现主因：MSM 的“窗口化指数表示”

`vendor/bellman/src/multiexp.rs`：`Exponent::chunks(c)` 生成
`ChunkedExponent::Zero | One | Chunks(Vec<u64>)`——**零/一指数零堆分配**，非零指数才分配 `chunk_count` 个 `u64`。因此该缓冲量与**非零指数密度**成正比，而非只与指数个数成正比。

`exponent_prep_live_delta_bytes`（单线程实测）：

| 调用 | n | c | chunk_count | 窗口化增量 | 平均 B/指数 | 推断非零密度 |
|---|---:|---:|---:|---:|---:|---:|
| H query (G1) | 131,071 | 12 | 22 | **25,970,216 (24.77 MiB)** | 198.1 | ~94% |
| L (G1) | 98,638 | 12 | 22 | 7,397,608 (7.06 MiB) | 75.0 | ~24% |
| A_aux (G1) | 98,638 | 12 | 22 | 7,397,608 | 75.0 | ~24% |
| B_aux (G2) | 98,638 | 12 | 22 | 7,396,664 | 75.0 | ~24% |
| A_input / B_input | 8 | 3 | 85 | 4,360 | 545 | — |

非零指数每项堆开销 = `chunk_count × 8` B（c=12 → 22×8=176 B），外加外层 `Vec<ChunkedExponent>` 每元素 32 B。按此：H 若 100% 密集应约 131,071×208 ≈ 26.0 MiB，实测 24.77 MiB → 密度约 94%；L/A/B 实测 7.06 MiB → 密度约 24%（与 assignment 大量零元一致）。

**结论：** Spend Prove 的最大单笔瞬态是 **H query 的窗口化指数缓冲（~26 MB）**，它同时解释了单线程峰值（78.6→104.6 MB）与并行峰值抬升的主因（多个 MSM 调用的窗口化缓冲在不同线程上同时驻留）。桶数组（0.59 MB）与指数转换（≤9 MB）都远小于它。

## 7. 更新后的 Spend 单线程峰值账本（可闭合）

| 锚点 | 字节 | 口径 |
|---|---:|---|
| 参数加载后常驻 | 60,818,440 | 实测 |
| 证明前常驻 | 68,729,865 | 实测（含见证/电路/vk） |
| H MSM 调用进入时 | 78,596,989 | 实测（含 QAP/FFT + `h_exponents` 5,242,840） |
| H 窗口化表示后 | 104,567,205 | 实测（+25,970,216） |
| 再加 1 个 G1 桶数组 | 105,156,885 | 实测 +589,680 |
| **观测峰值（绝对）** | **105,160,229** | 实测，差 3,344 B |

## 8. 限制

1. 分配器统计的是本次运行的 live/peak 字节，不含代码段/栈/分配器元数据；不是通用内存上界。
2. 8 线程时各 MSM 调用并发，**逐调用** `live_start/live_after_prep` 会互相污染，只有**进程级**峰值可信；逐调用归属仅在单线程干净。
3. 单线程批的 Prove 时间（4.1–8.2 s）受 `SAPLING_PROFILE=1` 影响，不能当正式计时基线，只用于内存归属。
4. 指数转换的微测量复刻了 groth16 的转换代码形态与真实长度，属于受控测量，不是 in-situ 时间线采样。
5. 8/16/20 线程非单调性（原缺口 5）与 fallback 消融（原缺口 4）仍未由本次测量闭合。

## 9. 复现凭证（Reproduction credentials）

**归档时间：** 2026-10-17
**机器：** i7-14700，31.7 GiB RAM，Windows 11

### 9.1 工具链与源码版本

| 项 | 值 |
|---|---|
| git 分支 | `experiment/fallback-ablation-20261016` |
| git HEAD | `b1beca2278adf588add976b1e14355ab8efa1ba5`（工作区有未提交改动，见下） |
| rustc | `rustc 1.98.1 (48a229cea 2026-09-01)` |
| cargo | `cargo 1.98.1 (797e8a9bc 2026-08-05)` |

### 9.2 参数文件（SHA-256）

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `D:\Research\zcash-params\sapling-spend.params` | 47,958,396 | `8E48FFD23ABB3A5FD9C5589204F32D9C31285A04B78096BA40A79B75677EFC13` |
| `D:\Research\zcash-params\sapling-output.params` | 3,592,860 | `2F0EBBCBB9BB0BCFFE95A397E7EBA89C29EB4DDE6191C339DB88570E3F3FB0E4` |

### 9.3 本次运行的诊断二进制（SHA-256）

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `experiments/prover-smoke/target/release/prove_memory_ledger.exe` | 4,298,439 | `2BF2AAD172827CE1BE24A6B370864455BFDF4693BC0C36BF323C1039D76BEBA8` |
| `experiments/prover-smoke/target/release/exponent_conversion_memory.exe` | 1,705,981 | `45D43F82DF927F6F47FF7C59994837C7F46792D2D85C9A199089AE8A395ACCA3` |

### 9.4 插桩源码（SHA-256）

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `vendor/bellman/src/mem_probe.rs`（新增） | 2,661 | `4E7C7F4FBDF86C6D8E3CB00E20F5F6B66921753E76A4A5AC8BC77A707E3D595E` |
| `vendor/bellman/src/multiexp.rs`（已改） | 29,650 | `230FDFBE07C64CE81D90A4AAD60CDC5354A156C0B599BE8E87CD3263376E7022` |
| `vendor/bellman/src/lib.rs`（已改） | 19,789 | `E4A466AF261F4F7931448887768DC1C89B9BA41E250592BE88177843CC84BD75` |
| `experiments/prover-smoke/src/bin/prove_memory_ledger.rs`（新增） | 10,382 | `D09F212C2CCBA3BC6C364BAA5224101A5CEB1DB437AC76E7405020E8EE5E7F1D` |
| `experiments/prover-smoke/src/bin/exponent_conversion_memory.rs`（新增） | 4,216 | `B783DE8F0B38F4E06C6454DD343AB955CF328AC519E5FCC6273DE2F2401DF3FC` |
| `experiments/prover-smoke/Cargo.lock` | 23,419 | `DFC0A8E0065098D3EDA16030B33EA701CB3815802ABC17B4D9E046D77056A5B4` |

### 9.5 运行环境变量（可在 PowerShell 中 `$env:VAR` 复现）

```
SAPLING_MEM_PROBE=1
SAPLING_PROFILE=1
SAPLING_MSM_STAGE_TIMING=0
SAPLING_MSM_BRANCH_COUNTS=0
ZCASH_PARAMS_DIR=D:\Research\zcash-params
RAYON_NUM_THREADS=1     # 1 线程批；8 线程批改为 8
```

### 9.6 实验留存规范（后续每次实验都应遵守）

1. **参数路径与哈希**：记录所用参数文件路径 + SHA-256。
2. **可执行文件哈希**：记录被测二进制的 SHA-256（而非仅源码）。
3. **源码哈希 + git 版本**：记录相关插桩源码 SHA-256 与 git HEAD（工作区改动必须说明）。
4. **环境**：记录 `RAYON_NUM_THREADS`、全部诊断用环境变量、build profile。
5. **原始文件三件套**：stdout 日志、stderr（诊断探针）日志、结构化 CSV，并保留 batch_id。
6. **不覆盖原则**：不同批次、不同线程数、不同插桩开关的数据分文件保存，不合并、不覆盖、不平均。
7. **口径声明**：区分「直接实测」与「由实测推导」的值，区分「受控微测量」与「in-situ 采样」。
