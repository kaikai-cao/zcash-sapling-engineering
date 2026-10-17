# Zcash Sapling 证明流程：逐步参数细化、内存账本与瓶颈分析

**文档类型：** 工程细化报告（把每个阶段、每个参数、每个椭圆曲线点、每块内存、每种算法都拆开写清楚）
**生成日期：** 2026-10-17
**代码与数据基线：** 仓库 `experiment/fallback-ablation-20261016` 分支；测试代码 `sapling-crypto 0.9.0`（commit `88a7946b…`）；本地 `vendor/bellman 0.15.0`、`vendor/groth16 0.2.0`
**环境：** Windows 11、Intel Core i7-14700、31.7 GiB RAM、Rust 1.98.1、Release、Groth16 + BLS12-381

> 说明：本文把 `docs/`、`experiments/`、`results/` 中已有的原始测量与源码固定版本汇总成一份“参数总账”，所有数字都标注口径与来源文件。诊断批次与正式基线不混用。

---

## 0. 一页速览（关键数字）

| 维度 | Sapling Spend | Sapling Output |
|---|---:|---:|
| R1CS 约束数 | 98,777 | 7,827 |
| 辅助变量数 | 98,638 | 7,821 |
| 公开输入数（不含常数 1） | 7 | 5 |
| FFT 域大小 N = 2^k | 131,072 = 2¹⁷ | 8,192 = 2¹³ |
| 参数文件字节 | 47,958,396 B (45.74 MiB) | 3,592,860 B (3.43 MiB) |
| 参数文件里的 G1 点 | 376,701 个 × 96 B | 27,460 个 × 96 B |
| 参数文件里的 G2 点 | 61,400 个 × 192 B | 4,950 个 × 192 B |
| 参数文件解码后内存（按 len） | 51,407,240 B (49.03 MiB) | 3,796,176 B (3.62 MiB) |
| Prove 中位数（正式基线，1 线程，未绑核快态） | 3,385.716 ms | 514.853 ms |
| Prove 中位数（绑核 LP0 可复现） | 3,724.0 ms（§14） | 529.5 ms（§14） |
| Verify 中位数（正式基线） | 2.790 ms | 2.150 ms |
| 编码后证明大小 | 192 B | 192 B |
| 峰值工作集（整进程） | 101.30 MiB | 21.54 MiB |
| MSM 调用次数 / 次 | 8 | 8 |
| 最大单次 MSM（点×标量） | H query G1：131,071 | B-G2 aux：7,821（G2 最贵） |
| MSM 占总证明时间 | ~87.6%（探索性单线程插桩） | ~93.2–93.4%（单线程低开销） |

> **重要口径说明（2026-10-17）：** 单线程数字受 CPU 核放置影响可达 **2.6×**（P-core ≈3.4–4.0 s vs E-core ≈5.3–8.9 s）。上表第一行是**未绑核快态**值；绑核后可复现值为 Spend ≈3.72 s、Output ≈0.53 s。详见 §14。

---

## 1. 底层密码学参数（先把“点有多大”定义清楚）

Sapling 使用 **BLS12-381** 曲线、**Groth16** 证明系统、**R1CS → QAP** 电路表示。

### 1.1 域与标量

| 对象 | 定义 | 位宽 | 字节 |
|---|---|---:|---:|
| 基域 Fq | BLS12-381 素数域（坐标所在域） | 381 bit | 48 B |
| 标量域 Fr | BLS12-381 标量域（指数/系数所在域，等于 r 阶） | 255 bit | 32 B |
| G2 的 Fq2 元素 | 2 个 Fq 数 | 762 bit | 96 B |

`Fr` 的 255 bit 决定 MSM 的标量窗口切块数（见 §5.2）。

### 1.2 椭圆曲线点的大小（两种编码）

| 点类型 | 未压缩 (uncompressed) | 压缩 (compressed) | 说明 |
|---|---:|---:|---|
| G1 affine (x,y) | 2 × 48 = **96 B** | 1 × 48 = **48 B** | 一个坐标 + 3 个标志位 |
| G2 affine (x,y) | 4 × 48 = **192 B** | 2 × 48 = **96 B** | 两个 Fq2 坐标 |
| G1 projective (X,Y,Z) | 3 × 48 = 144 B | — | 运行时中间量 |
| G2 projective (X,Y,Z) | 6 × 48 = 288 B | — | 运行时中间量 |

> 关键结论：**参数文件用“未压缩”编码（96/192 B），而序列化证明用“压缩”编码（48/96 B）。** 这是为什么参数文件 48 MB、而证明只有 192 B 的直接原因。

### 1.3 运行时 Rust 类型布局（`size_of`，实测）

| 类型 | size_of | align_of | 与上面编码的关系 |
|---|---:|---:|---|
| `G1Affine` | 104 B | 8 | 96 B 坐标 + 8 B 对齐填充 |
| `G2Affine` | 200 B | 8 | 192 B 坐标 + 8 B 填充 |
| `G1Projective` | 144 B | 8 | 3 × Fq |
| `G2Projective` | 288 B | 8 | 3 × Fq2 |
| `Scalar` (Fr) | 32 B | 8 | |
| `Exponent<Scalar>` | 40 B | 8 | enum 标签 + 32 B 位表示 |
| `Vec<T>` 头部 | 24 B | 8 | ptr + len + cap |
| `Arc<Vec<T>>` 句柄 | 8 B | 8 | |

来源：`experiments/raw/csv/sapling_runtime_type_sizes_20261016.csv`。

### 1.4 用到的算法清单

| 阶段 | 算法 | 复杂度/规模 |
|---|---|---|
| 电路 → R1CS | Bellman `ConstraintSystem` 合成 | O(#constraints) |
| R1CS → QAP | 拉格朗日插值，用 **逆 FFT (IFFT)** 与 **陪集 FFT (coset FFT)** 计算 A、B、C、H 多项式 | O(N log N) |
| 多项式的 H 计算 | 陪集上 A·B − C，再除以 Z_H，再做 **逆陪集 FFT (icoset FFT)** | O(N log N) |
| 多标量乘 (MSM) | **Pippenger 桶方法（bucket method）+ 固定窗口 c**，窗口间用倍点合并 | O(n·c + 2^c) 每窗口 |
| 桶求和 | **Summation-by-parts**（部分和嵌套） | O(buckets) |
| 证明组装 | 标量乘/加（G1、G2） | O(1) |
| 验证 | **Groth16 pairing product**（多个 Miller loop 可批处理） | 常数对数量 |

---

## 2. 证明流程的逐步拆解（每一步做什么、多大）

调用链（源码级）：

```
钱包 → Builder::build → Sapling Bundle::create_proofs
     → SpendProver/OutputProver::create_proof
     → Groth16 create_random_proof(circuit, params, rng)
     → create_proof()  ← 见 vendor/groth16/src/prover.rs
```

`create_proof` 内部按源码顺序分为 7 个计时阶段（`vendor/groth16/src/prover.rs`，profile 标记）：

| # | 阶段 (`G16_STAGE_PROFILE` 字段) | 做什么 | Spend 1 线程中位数 | Spend 20 线程中位数 |
|---:|---|---|---:|---:|
| 1 | `circuit_synthesis_constraints_ms` | 电路合成 + 为每个输入补 `x·0=0` 约束，填 a/b/c 与密度位图 | 102.182 ms | 103.247 ms |
| 2 | `worker_vk_setup_ms` | 创建 Worker、取 VK | 0.001 ms | 0.001 ms |
| 3 | `qap_fft_h_exponent_prep_ms` | 3×IFFT、3×coset FFT、A·B−C、除 Z、icoset FFT，生成 H 指数 | 384.724 ms | 119.883 ms |
| 4 | `h_query_access_dispatch_ms` | H 查询取数 + 派发 H 的 MSM | 5.771 ms | 6.102 ms |
| 5 | `assignment_query_prep_dispatch_ms` | 赋值转换、A/B 查询准备、派发余下 MSM（**含单线程同步 fallback**） | 2,428.592 ms | 13.714 ms |
| 6 | `proof_scalar_terms_ms` | 计算 g_a、g_b、g_c 的标量项 | 1.506 ms | 1.966 ms |
| 7 | `wait_and_assembly_ms` | `wait()` 收集 8 个 MSM 结果并相加组装 | 608.975 ms | 322.071 ms |
| — | `create_proof_body_ms`（合计） | | **3,533.094 ms** | **575.654 ms** |

来源：`README.md` §8.3（批次 `1791801666809` vs `1791802391142`）。1→20 线程约 6.14×。

---

## 3. 电路规模逐步数字

来源：`experiments/raw/csv/sapling_circuit_scale_raw.csv`、`results/tables/engineering_scale.csv`。

| 指标 | Spend | Output | 计算/含义 |
|---|---:|---:|---|
| 约束数 | 98,777 | 7,827 | `enforce` 次数 |
| 辅助变量 | 98,638 | 7,821 | `alloc` 次数 |
| 公开输入（不含 1） | 7 | 5 | `alloc_input` 次数 |
| 输入变量（含常数 1） | 8 | 6 | 公开输入 + 1 |
| domain size N | 131,072 = 2¹⁷ | 8,192 = 2¹³ | `next_power_of_two(constraints)` |

### 3.1 FFT 与多项式内存

对 Spend，N = 131,072：

| 缓冲 | 元素类型 | 元素大小 | 大小 |
|---|---|---:|---:|
| A 多项式 | Scalar | 32 B | N × 32 = 4,194,304 B = 4.00 MiB |
| B 多项式 | Scalar | 32 B | 4.00 MiB |
| C 多项式 | Scalar | 32 B | 4.00 MiB |
| A/B/C 合计（prover.a/b/c） | Scalar | 32 B | 3 × 4 MiB = **12 MiB** |
| H 指数向量 `h_exponents` | Exponent | 40 B | (N−1) × 40 = 131,071 × 40 = **5,242,840 B ≈ 5.00 MiB** |

> 注意 `h_exponents` 长度正好是 **N − 1 = 131,071**：源码先 `a.truncate(a_len)`（`a_len = a.len()−1`）再转成指数。这就是 H 查询点数为 131,071 的来源。

---

## 4. 参数文件（CRS / Proving Key）逐步字节账

参数文件 = Groth16 参数体（VK + 5 组查询向量）+ MPC 尾。

### 4.1 序列化分段（未压缩点：G1=96 B，G2=192 B）

**Spend（总计 47,958,396 B）**

| 段 | 点数 | 点编码 | 载荷字节 | 长度前缀 | 编码字节 | 起止偏移 |
|---|---:|---:|---:|---:|---:|---|
| VK 固定点 | 3×G1 + 3×G2 | 96 / 192 | 864 | 0 | 864 | 0–864 |
| VK_IC | 8 × G1 | 96 | 768 | 4 | 772 | 864–1,636 |
| H_G1 | 131,071 × G1 | 96 | 12,582,816 | 4 | 12,582,820 | 1,636–12,584,456 |
| L_G1 | 98,638 × G1 | 96 | 9,469,248 | 4 | 9,469,252 | 12,584,456–22,053,708 |
| A_G1 | 85,390 × G1 | 96 | 8,197,440 | 4 | 8,197,444 | 22,053,708–30,251,152 |
| B_G1 | 61,300 × G1 | 96 | 5,884,800 | 4 | 5,884,804 | 30,251,152–36,135,956 |
| B_G2 | 61,300 × G2 | 192 | 11,769,600 | 4 | 11,769,604 | 36,135,956–47,905,560 |
| **Groth16 参数体** | | | | | **47,905,560** | |
| MPC 电路哈希 | 1 × 64 B | — | 64 | 0 | 64 | 47,905,560–47,905,624 |
| MPC 贡献者数 | 1 × u32 | — | 0 | 4 | 4 | 47,905,624–47,905,628 |
| MPC 贡献记录 | 97 条 | 3×G1+1×G2+64 B | 52,768 | 0 | 52,768 | 47,905,628–47,958,396 |
| **文件合计** | | | | | **47,958,396** | |

**Output（总计 3,592,860 B）**

| 段 | 点数 | 载荷字节 | 编码字节 |
|---|---:|---:|---:|
| VK 固定点 | 3×G1 + 3×G2 | 864 | 864 |
| VK_IC | 6 × G1 | 576 | 580 |
| H_G1 | 8,191 × G1 | 786,336 | 786,340 |
| L_G1 | 7,821 × G1 | 750,816 | 750,820 |
| A_G1 | 6,298 × G1 | 604,608 | 604,612 |
| B_G1 | 4,850 × G1 | 465,600 | 465,604 |
| B_G2 | 4,850 × G2 | 931,200 | 931,204 |
| MPC 尾 | — | 52,836 | 52,836 |
| **合计** | | | **3,592,860** |

来源：`experiments/raw/csv/sapling_parameter_size_breakdown_20261011_142729.csv`（解析器精确落在 EOF，字节账自洽）。

### 4.2 用“点 × 每点字节”复核（教学式）

**Spend 文件里一共有多少点：**

- G1 点：VK 3 + IC 8 + H 131,071 + L 98,638 + A 85,390 + B_G1 61,300 + MPC(97×3=291) = **376,701 个**
  → 376,701 × 96 B = **36,163,296 B**
- G2 点：VK 3 + B_G2 61,300 + MPC(97×1=97) = **61,400 个**
  → 61,400 × 192 B = **11,788,800 B**
- 贡献记录 transcript：97 × 64 = 6,208 B；长度前缀 28 B；电路哈希 64 B

合计 = 36,163,296 + 11,788,800 + 6,208 + 28 + 64 = **47,958,396 B** ✓（与文件大小完全一致）

**Output：** G1 27,460 × 96 = 2,636,160；G2 4,950 × 192 = 950,400；其余 6,300 → 合计 **3,592,860 B** ✓

### 4.3 解码到内存后的体积

参数读入时不做压缩，放进 `Vec<G1Affine>`（104 B/元素）和 `Vec<G2Affine>`（200 B/元素）。

**Spend（按 len / 按 capacity）**

| 组件 | 元素数 | capacity | 元素大小 | 按 len | 按 capacity |
|---|---:|---:|---:|---:|---:|
| VK 固定点 | 6 | 6 | — | 912 | 912 |
| VK_IC | 8 | 8 | 104 | 832 | 832 |
| H_G1 | 131,071 | 131,072 | 104 | 13,631,384 | 13,631,488 |
| L_G1 | 98,638 | 131,072 | 104 | 10,258,352 | 13,631,488 |
| A_G1 | 85,390 | 131,072 | 104 | 8,880,560 | 13,631,488 |
| B_G1 | 61,300 | 65,536 | 104 | 6,375,200 | 6,815,744 |
| B_G2 | 61,300 | 65,536 | 200 | 12,260,000 | 13,107,200 |
| **合计** | | | | **51,407,240 B (49.03 MiB)** | **60,819,152 B (58.00 MiB)** |

**Output**

| 组件 | 元素数 | capacity | 按 len | 按 capacity |
|---|---:|---:|---:|---:|
| VK 固定点 | 6 | 6 | 912 | 912 |
| VK_IC | 6 | 8 | 624 | 832 |
| H_G1 | 8,191 | 8,192 | 851,864 | 851,968 |
| L_G1 | 7,821 | 8,192 | 813,384 | 851,968 |
| A_G1 | 6,298 | 8,192 | 654,992 | 851,968 |
| B_G1 | 4,850 | 8,192 | 504,400 | 851,968 |
| B_G2 | 4,850 | 8,192 | 970,000 | 1,638,400 |
| **合计** | | | **3,796,176 B (3.62 MiB)** | **5,048,016 B (4.81 MiB)** |

来源：`experiments/raw/csv/sapling_runtime_params_memory_20261016.csv`。

> **观察：** 序列化 45.74 MiB → 内存 49.03 MiB（len）/ 58.00 MiB（capacity）。差值来自：未压缩点结构体从 96→104 B 的填充，以及 `Vec` 的容量按 2 的幂向上取整（满足 FFT/Vec 增长）。

### 4.4 参数加载/校验时间（证明之前的一次性成本）

| 电路 | 仅读取+点验证 | 备注 |
|---|---:|---|
| Spend | 1,807–50,246 ms（随磁盘/系统状态大幅波动） | `Parameters::read(..., true)` 会逐点验证编码 |
| Output | 1,774–3,592 ms | |

来源：`engineering_parameters.csv`、`sapling_runtime_params_memory_20261016`。**注意：这属于“证明外”的开销，不计入 Prove 中位数。**

---

## 5. MSM 逐步细化（报告的核心）

MSM（多标量乘）是 Sapling Groth16 证明里最大的一块计算。一次 Spend 证明有 **8 次** `multiexp` 调用。

### 5.1 算法（`vendor/bellman/src/multiexp.rs`）

固定窗口 Pippenger 桶方法：

1. **选窗口 c**：若标量数 n < 32，取 c = 3；否则 c = ⌈ln(n)⌉。
2. **桶数**：每个窗口 `2^c − 1` 个桶。
3. **窗口切块数**：标量 255 bit，chunk 数 = ⌈255 / c⌉。
4. **指数预处理**：每个标量转成 `Zero` / `One` / `Chunks(Vec<u64>)`（`Exponent<Scalar>`，40 B/个）。
5. **每个 chunk**（可并行）：
   - 分配桶数组 `vec![identity; 2^c − 1]`（`G1Projective` 144 B 或 `G2Projective` 288 B）；
   - 遍历指数，把对应基点 `add_assign` 进桶（bucket fill）；
   - **summation-by-parts** 反向累加桶（bucket reduce），每次迭代两次群加；
   - 得到该 chunk 的部分和。
6. **合并 chunk 结果**：从高位到低位，每段先做 c 次倍点（double），再加该 chunk 结果。
7. **单值/零指数短路**：`Exponent::One` 在 chunk 0 直接加到累加器；`Zero` 直接 `skip`。

### 5.2 每次调用的静态参数（Spend）

| MSM 调用 | 群 | n (标量数) | c | 桶数/chunk = 2^c−1 | chunk 数 = ⌈255/c⌉ | 桶元素类型 |
|---|---|---:|---:|---:|---:|---|
| H query | G1 | 131,071 | 12 | 4,095 | 22 | G1Projective |
| L query | G1 | 98,638 | 12 | 4,095 | 22 | G1Projective |
| A input | G1 | 8 | 3 | 7 | 85 | G1Projective |
| A aux | G1 | 98,638 | 12 | 4,095 | 22 | G1Projective |
| B-G1 input | G1 | 8 | 3 | 7 | 85 | G1Projective |
| B-G1 aux | G1 | 98,638 | 12 | 4,095 | 22 | G1Projective |
| B-G2 input | G2 | 8 | 3 | 7 | 85 | G2Projective |
| B-G2 aux | G2 | 98,638 | 12 | 4,095 | 22 | G2Projective |

例：n = 131,071 → ln = 11.78 → c = 12；桶数 4095；⌈255/12⌉ = 22 chunks。

### 5.3 每次调用的桶内存（点 × 每点字节）

单个桶数组（一个 chunk）数据区 = 桶数 × `size_of(projective)`：

| 调用 | 单桶数组 | 全部 chunk 累计 |
|---|---:|---:|
| H / L / A_aux / B-G1_aux (G1, c=12) | 4,095 × 144 = **589,680 B** | 22 × 589,680 = **12,972,960 B** |
| B-G2_aux (G2, c=12) | 4,095 × 288 = **1,179,360 B** | 22 × 1,179,360 = **25,945,920 B** |
| A/B input (G1, c=3) | 7 × 144 = 1,008 B | 85 × 1,008 = 85,680 B |
| B-G2 input (G2, c=3) | 7 × 288 = 2,016 B | 85 × 2,016 = 171,360 B |

**并发上界估算**（`max_concurrent_chunk_regions × 桶数 × 元素大小`）：

| 调用 | 20 线程并发上界 | 最大单调用上界 (MiB) |
|---|---:|---:|
| H / L / A_aux / B-G1_aux | 20 × 589,680 = 11,793,600 B | 11.25 |
| B-G2_aux | 20 × 1,179,360 = 23,587,200 B | 22.49 |

来源：`results/tables/sapling_spend_msm_bucket_memory_20261016.csv`。**这是静态估算，不是进程峰值。**

### 5.4 每次调用的源码级操作计数（不是硬件指令数）

由 n、c、chunk 数推导：

| 调用 | fill 循环槽位 = n × chunks | 桶初始化元素 = 桶数 × chunks | reduce 迭代 | reduce 的 `add_assign` | 合并倍点 | 合并加法 |
|---|---:|---:|---:|---:|---:|---:|
| H query G1 | 131,071 × 22 = 2,883,562 | 4,095 × 22 = 90,090 | 90,090 | 180,180 | 264 | 22 |
| L query G1 | 98,638 × 22 = 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| A aux G1 | 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| B-G1 aux | 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| B-G2 aux | 2,170,036 | 90,090 | 90,090 | 180,180 | 264 | 22 |
| A input G1 | 8 × 85 = 680 | 7 × 85 = 595 | 595 | 1,190 | 255 | 85 |
| B-G1 input | 680 | 595 | 595 | 1,190 | 255 | 85 |
| B-G2 input | 680 | 595 | 595 | 1,190 | 255 | 85 |

**一次证明的 8 次调用合计：**

- fill 循环槽位：**11,565,746**
- 桶初始化元素：**452,235**
- bucket-reduce 迭代：**452,235**
- bucket-reduce 的群 `add_assign`：**904,470**
- 合并阶段倍点：**2,085**
- 合并阶段加法：**365**

来源：`experiments/metadata/sapling_spend_msm_operation_accounting_1792134295649.md`。

### 5.5 每次调用的实测耗时

**(a) 单线程正式诊断批次（Spend，插桩）**

| 调用 | n | elapsed 中位数 |
|---|---:|---:|
| H query G1 | 131,071 | 1,446.624 ms |
| L query G1 | 98,638 | 398.915 ms |
| A input G1 | 8 | 0.950 ms |
| A aux G1 | 98,638 | 278.323 ms |
| B-G1 input | 8 | 0.770 ms |
| B-G1 aux | 98,638 | 211.220 ms |
| B-G2 input | 8 | 2.200 ms |
| B-G2 aux | 98,638 | 590.730 ms |

八次 elapsed 合计约占外层 Prove 的 **85–86%**。来源：`sapling_spend_prover_bottleneck_final_report_20261011.md`。

**(b) 20 线程（批次 `1792135474677`，逐调用）** 见 `sapling_spend_msm_call_profile_1792135474677.csv`；H query 中位数约 408–586 ms，各调用因并行重叠而普遍落在 130–590 ms 区间。

**(c) MSM 内部阶段（20 线程，`median_bucket_fill_sum_ms` 主导）**

| 调用 | chunk_parallel_wall（墙钟） | bucket_fill（累计） | bucket_reduce（累计） | bucket_init | merge |
|---|---:|---:|---:|---:|---:|
| H query G1 | 325.648 | **2,833.414** | 180.499 | 0.900 | 0.167 |
| L query G1 | 389.337 | 1,043.854 | 251.703 | 8.337 | 0.211 |
| A aux G1 | 379.851 | 454.036 | 206.089 | 0.946 | 0.209 |
| B-G1 aux | 251.319 | 242.540 | 191.495 | 1.014 | 0.197 |
| B-G2 aux | 204.425 | **687.174** | 514.161 | 8.944 | 0.424 |
| A input G1 | 0.584 | 0.477 | 1.238 | 0.085 | 0.258 |

单位 ms。**`bucket_fill` 是累计（各 chunk 相加、并行重叠），不是墙钟**；它是 MSM 内部最值得研究的成本段（Output 上单线程测得约占 MSM 内部计时的 73–74%）。

来源：`sapling_spend_msm_inner_stage_summary_1792135474677.csv`。

### 5.6 Output 的 8 次调用（对照，单线程低开销）

| 调用 | 群 | n | c | elapsed 中位数 |
|---|---|---:|---:|---:|
| H query | G1 | 8,191 | 10 | 129.125 ms |
| L query | G1 | 7,821 | 9 | 82.987 ms |
| A input | G1 | 6 | 3 | 0.938 ms |
| A aux | G1 | 7,821 | 9 | 65.012 ms |
| B-G1 input | G1 | 6 | 3 | 0.772 ms |
| B-G1 aux | G1 | 7,821 | 9 | 53.180 ms |
| B-G2 input | G2 | 6 | 3 | 2.237 ms |
| **B-G2 aux** | **G2** | **7,821** | **9** | **152.731 ms** |

> 有意思的对照：Output 的 H query 只有 8,191 个点，c=10、桶数 1,023；而 **G2 的辅助查询（B-G2 aux）虽然点数与 G1 相同，却因为 G2 群运算和 288 B 桶元素而成为单次最贵调用**（152.7 ms）。

来源：`docs/msm_profiling_notes.md`、`docs/baseline_comparison.md`。

---

## 6. 证明大小与验证

### 6.1 为什么是 192 字节

`GROTH_PROOF_SIZE = 48 + 96 + 48 = 192`（`sapling-crypto/src/constants.rs`）：

| 分量 | 群 | 压缩编码 |
|---|---|---:|
| π_A | G1 | 48 B |
| π_B | G2 | 96 B |
| π_C | G1 | 48 B |
| **合计** | | **192 B** |

> Spend 和 Output 的证明大小都是 192 B，与电路规模无关（Groth16 的常数大小证明）。

### 6.2 验证

- 公开输入：Spend **7** 个域元素（rk、value commitment、anchor、nullifier 的打包），Output **5** 个（value commitment、ephemeral pk、note commitment）。
- 验证算法：Groth16 pairing 检查 `e(A,B) = e(α,β)·e(IC,γ)·e(C,δ)`，其中 `IC` 由公开输入与 VK_IC 点组合（Spend VK_IC 有 8 个点，Output 6 个）。多个 Miller loop 可批处理。
- 实测：Spend 2.790 ms、Output 2.150 ms → **验证比证明便宜约 1200×（Spend）/ 240×（Output）**。

---

## 7. 内存账本汇总（Spend）

| 层级 | 大小 | 来源/口径 |
|---|---:|---|
| 参数文件（磁盘） | 45.74 MiB | 序列化字节 |
| 参数解码后（len） | 49.03 MiB | `Vec` 元素数据区 |
| 参数解码后（capacity） | 58.00 MiB | `Vec` 缓冲容量 |
| A/B/C 多项式 | 12 MiB | 3 × N × 32 B |
| H 指数向量 | 5.00 MiB | (N−1) × 40 B |
| aux 赋值 → Exponent | 98,638 × 40 = 3.76 MiB | 转换临时量 |
| 单次 MSM 桶数组（G2，1 chunk） | 1.125 MiB | 4,095 × 288 B |
| MSM 桶并发上界（G2，20 线程） | 22.49 MiB | 静态估算 |
| **整进程峰值工作集** | **101.30 MiB** | `PeakWorkingSet64`，含加载+证明+验证 |

> **账本缺口（已于 2026-10-17 实测闭合）：** 见 §13 与 `experiments/metadata/sapling_prove_memory_ledger_20261017.md`。已用计数型全局分配器把参数常驻、`h_exponents`、H 窗口化指数缓冲、单桶数组合并闭合到观测峰值（Spend 单线程 105,160,229 B，残差仅 3,344 B）。

---

## 8. 线程与调度瓶颈

### 8.1 线程扩展（Spend，30/30 验证通过）

| Rayon 线程 | Prove 中位数 | 观测范围 | 相对 1 线程 |
|---:|---:|---|---:|
| 1 | 3,499.607 ms | 3,480.081–3,544.655 | 1.00× |
| 2 | 1,831.514 ms | 1,825.416–1,874.669 | 1.91× |
| 4 | 1,008.486 ms | 997.631–1,051.515 | 3.47× |
| 8 | 769.625 ms | 659.059–1,178.840 | 4.55× |
| 16 | 591.082 ms | 572.541–639.469 | 5.92× |
| 20 | 596.008 ms | 565.040–627.991 | 5.87× |

**次线性**：16 线程后不再提升；8 线程波动大。来源：`results/tables/sapling_spend_thread_scaling_summary_20261011.csv`。

### 8.2 单线程 worker fallback（已消融：是计时归属现象，不是瓶颈）

单线程诊断批次中观察到的签名：

- 每次证明都记录到 **worker fallback**（5/5 证明出现）。
- B-G1 aux 调用：`submit_elapsed_ms` 中位数 **2,334.96 ms**，`task_start_delay_ms` 中位数 **2,123.68 ms**，而该调用自身 `elapsed_ms` 中位数仅 **211.22 ms**。
- 对应的 `assignment_query_prep_dispatch_ms` 阶段中位数 **2,428.592 ms**。

20 线程时：无 fallback 记录，B-G1 aux 提交中位数约 0.002 ms，该阶段降到 13.714 ms。

**结论（2026-10-17 受控消融）：** 该签名确实存在，但它是**计时归属**而非额外开销。固定线程数=1、绑核（`-AffinityMask 1`）、ABBA 配对后，A（fallback）与 B（强制 async）端到端 Prove 差 **+1%（+41 ms 均值，U=29，p≈0.11，n=10/条件，不显著）**；强制 async 只是把约 **2.5 s** 从 `assignment_query_prep_dispatch_ms`（2523.8→7.3 ms）挪进 `wait_and_assembly_ms`（634.1→3168.1 ms）。详见 `experiments/metadata/sapling_spend_worker_fallback_ablation_conclusion_20261017.md`。

### 8.3 受控消融实验（已完成）

`experiments/metadata/sapling_spend_worker_fallback_ablation_protocol_20261016.md` 定义了把线程固定为 1、只改 worker 调度分支（`-ForceAsyncWorker`）的 A/B 对照。**已于 2026-10-17 完成（ABBA 配对 + 绑核），结论：fallback 对端到端 Prove 无可测影响，只是计时归属/调度现象。** 数据在 `sapling_spend_prover_runs_fallback_ablation*.csv`，不混入正式基线。

> **方法学告警（重要）：** 本机为混合架构 CPU（i7-14700）。单线程 worker 不被绑定核时，OS 可能把它放到 E-core，导致 Prove **2.1×** 变慢（LP0≈3.8 s vs LP20≈8.1 s，参数加载 25 s vs 54 s）。这解释了 2026-10-16 历史批次“8.5 s vs 3.6 s”的波动。**单线程测量必须绑核，否则结果有 2.1× 不确定性。**

---

## 9. 瓶颈排序（按证据强度 + 潜在收益）

| 排名 | 瓶颈 | 证据 | 影响量级 | 优化候选 |
|---:|---|---|---|---|
| **1** | **MSM（尤其 H query G1 与 G2 辅助）** | MSM 占单线程 Prove 的 85–93%；H query G1 单次 1.45 s | 决定性 | 窗口调优、bucket fill 优化、Pippenger 变体（如 signed digits / wNAF）、G2 桶内存/布局 |
| **2** | ~~单线程 worker fallback / 调度归属~~ **（已消融：非瓶颈）** | 受控 ABBA+绑核：端到端差 +1%（+41 ms，U=29，p≈0.11，n=10）；仅把 ~2.5 s 在阶段间挪位 | **无（计时归属）** | 无（非吞吐瓶颈）；保留正确绑核的单线程测量 |
| **3** | **QAP / FFT（阶段 3）** | 单线程 384 ms，20 线程 120 ms | 中 | 并行 FFT、减少域向量分配、复用缓冲 |
| **4** | **并行扩展次线性 + 20 线程等待/组装** | 16 线程后饱和；wait_and_assembly 仍 322 ms | 中 | 负载均衡、减少同步、chunk 粒度调优 |
| **5** | **参数加载/点验证** | 1.8–50 s（证明外） | 大但属一次性 | 惰性解码、缓存解析结果、并行点验证 |
| — | 验证 | 2–3 ms | 可忽略 | 批量/聚合验证（多笔交易场景） |

### 9.1 用“操作计数”看为什么 bucket fill 是 MSM 内部重点

- 960 万级 fill 槽位 vs 90 万次 reduce 迭代 vs 90 万次 reduce 群加 → fill 是数量级最大的一环。
- Output 单线程实测：bucket fill 占 MSM 内部阶段计时 **73–74%**，bucket sum 占 **23–24%**（`docs/baseline_comparison.md` §4）。
- Spend 20 线程：H query 的 `bucket_fill_sum_ms` = 2,833 ms，是同一调用墙钟（326 ms）的 8.7 倍（因各 chunk 累计）。

### 9.2 编译期可见的“未优化点”（源码注释）

`vendor/groth16/src/prover.rs` 第 308 行保留早期注释：`// TODO: parallelize if it's even helpful`，指向赋值转换/查询准备这段默认串行的代码——正是 fallback 影响最明显的阶段。

---

## 10. 优化候选与验证方法（不含“未验证的收益承诺”）

| 候选 | 目标瓶颈 | 如何验证 |
|---|---|---|
| MSM 窗口 c 调优 / signed-digit 表示 | #1 | 固定电路与线程，比较局部 MSM 时间 + 端到端 Prove + 验证通过 |
| bucket fill 数据结构与访存优化 | #1 | 同上，并记录桶内存 |
| worker fallback 解耦 | #2 | 复用 §8.3 的 A/B 消融协议，重复反向顺序 |
| 并行 FFT / 缓冲复用 | #3 | 阶段计时 + 端到端 |
| 任务粒度与负载均衡 | #4 | 线程扩展曲线复测 |

> **评价标准（仓库既有原则）：** 候选优化必须同时报告 (a) 局部阶段变化、(b) 端到端 Prove 墙钟、(c) 每份证明的验证结果、(d) 资源消耗，并保留原始数据。只在小微基准上变快不算成功。

---

## 11. 测量口径与局限（必读）

1. **批次不可混用。** 正式基线（Spend `1791613854129`、Output `1791549582046`）、线程扩展批次、插桩 profile 批次、诊断批次口径不同。
2. **插桩有开销。** 重度插桩批次 Prove 可达 8 s，绝对时间不可当正式基线，只能看**相对成本结构**。
3. **并行下 MSM elapsed 会重叠。** 不能把 8 次调用 elapsed 相加当作墙钟或“最大可加速比”；诊断批次里该比例可达 246%（`sapling_spend_profile_run_summary_1792220451370.csv`），正是因为调用并行。
4. **阶段计时是源码区间计时。** 可能包含同步/fallback 工作，不是互斥 CPU 分解。
5. **参数文件大小 ≠ CRS/PK/VK 大小 ≠ 运行时内存 ≠ 证明大小。**
6. **桶内存是静态估算**，不是分配器峰值；账本尚未闭合到 101 MiB。
7. **系统因素未完全受控**（CPU 频率、微信后台、电源策略），部分批次波动未解释。

---

## 12. 附录

### 12.1 关键公式

```
窗口        c = 3                      (n < 32)
            c = ceil(ln(n))            (n ≥ 32)
桶数        buckets = 2^c - 1
chunk 数    chunks  = ceil(255 / c)      # Fr 255 bit
单桶数组    = buckets × size_of(projective)   # G1:144 B, G2:288 B
fill 槽位   = n × chunks
reduce 群加 = 2 × buckets × chunks
# 参数文件
G1 字节     = (#G1 points) × 96
G2 字节     = (#G2 points) × 192
# 证明
GROTH_PROOF_SIZE = 48(G1) + 96(G2) + 48(G1) = 192 B
```

### 12.2 数据来源文件（可追溯）

| 内容 | 文件 |
|---|---|
| 电路规模 | `experiments/raw/csv/sapling_circuit_scale_raw.csv` |
| 参数分段字节账 | `experiments/raw/csv/sapling_parameter_size_breakdown_20261011_142729.csv` |
| 运行时参数内存 | `experiments/raw/csv/sapling_runtime_params_memory_20261016.csv` |
| 运行时类型大小 | `experiments/raw/csv/sapling_runtime_type_sizes_20261016.csv` |
| MSM 调用耗时 | `experiments/raw/csv/sapling_spend_msm_call_profile_*.csv` |
| MSM 内部阶段 | `experiments/raw/csv/sapling_spend_msm_inner_stage_summary_*.csv` |
| MSM 操作计数 | `experiments/metadata/sapling_spend_msm_operation_accounting_1792134295649.md` |
| MSM 桶内存 | `results/tables/sapling_spend_msm_bucket_memory_20261016.csv` |
| 阶段计时 1 vs 20 线程 | `README.md` §8.3；`experiments/metadata/sapling_spend_thread_profile_comparison_*.md` |
| 线程扩展 | `results/tables/sapling_spend_thread_scaling_summary_20261011.csv` |
| 瓶颈定位报告 | `experiments/metadata/sapling_spend_prover_bottleneck_final_report_20261011.md` |
| MSM/Worker 笔记 | `docs/msm_profiling_notes.md` |
| 成本结构对照 | `docs/baseline_comparison.md` |
| 内存测量缺口 | `experiments/metadata/sapling_runtime_memory_measurements_20261016.md` §6 |
| fallback 消融协议 | `experiments/metadata/sapling_spend_worker_fallback_ablation_protocol_20261016.md` |
| fallback 消融收敛结论 | `experiments/metadata/sapling_spend_worker_fallback_ablation_conclusion_20261017.md` |
| 新 smoke 与核放置可复现性 | `experiments/metadata/sapling_smoke_fresh_runs_and_cpu_affinity_20261017.md` |

### 12.3 复现命令

```powershell
$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'

# 1) 校验参数文件（大小 + BLAKE2b-512）
python .\scripts\verify_params.py --param-dir $env:ZCASH_PARAMS_DIR `
  --output-csv (Join-Path $env:TEMP 'sapling-parameter-validation.csv')

# 2) 编译（不跑证明）
cargo check --locked --manifest-path .\experiments\prover-smoke\Cargo.toml

# 3) 单线程 Spend 证明 + 阶段/MSM 诊断（会写 raw CSV 与日志）
powershell -ExecutionPolicy Bypass -File .\scripts\run_spend_combined_profile.ps1 `
  -RepoRoot "D:\Research\zcash-sapling-engineering" -Threads 1 -BranchCounters disabled
```

### 12.4 尚未闭合、建议下一步补测的项目

1. ~~Prove 阶段独占的进程峰值工作集~~ → **已闭合（新）**，见 §13.2：Spend 单线程绝对高水位 100.29 MiB、8 线程 134.82 MiB。
2. ~~MSM 桶数组的**实际分配/释放生命周期**与并发峰值~~ → **已闭合（新）**，见 §13.3：4,095×144 = 589,680 B、4,095×288 = 1,179,360 B 逐一实测吻合。
3. ~~`Exponent<Scalar>` 转换的临时内存规模~~ → **已闭合（新）**，见 §13.4：Spend 每次 7–9 MB 有界瞬态。
4. ~~fallback 消融 A/B 的收敛结论（当前最关键）~~ → **已闭合（新）**，见 §8.2/§8.3：fallback 是计时归属现象，端到端差 +1%（p≈0.11，不显著）。附：单线程绑核是复现前提。
5. 8/16/20 线程非单调性的独立证据（**仍未闭合**）。新线索与量化证据见 §14：本机为混合架构 CPU，未绑定核时**单线程** prove 即在 3.4–8.9 s 间波动（最高 **2.6×**）；多线程批次同样可能受 P/E 核与线程亲和性影响，复测时应固定亲和性/电源策略并按核态分层。

---

## 13. 补充实测（2026-10-17）：内存缺口闭环与新的主因

本节用**计数型全局分配器**（`experiments/prover-smoke/src/bin/prove_memory_ledger.rs` + 新增的 `vendor/bellman/src/mem_probe.rs`）补齐了 §12.4 的第 1–3 项。完整表格、命令与原始证据见 `experiments/metadata/sapling_prove_memory_ledger_20261017.md`；原始数据在 `experiments/raw/csv/sapling_prove_memory_ledger.csv` 与对应日志。

口径：进程级 `live/peak` 字节增量，单次运行观测值，**不是通用上界**；数值均可在原报告中按字节复核。

### 13.1 实测锚点（Spend）

| 锚点 | 单线程 | 8 线程 |
|---|---:|---:|
| 参数加载后常驻 | 60,818,440 B (58.001 MiB) | 同 |
| 证明前常驻 `live_before_prove` | 68,729,865 B (65.548 MiB) | 同 |
| Prove 期**绝对** live 高水位 | 105,160,229 B (100.29 MiB) | 141,370,967 B (134.82 MiB) |
| Prove 期峰值增量 | ~34.5 MB | ~68.8 MB |

**闭合验证：** 加载后实测 60,818,440 B 与静态 `capacity_payload` 60,819,152 B 仅差 **712 B**；单线程绝对高水位 100.29 MiB 与既有整进程 `PeakWorkingSet64 = 101.30 MiB` 吻合（分配器 live 略低于 WS，合理）——即“101 MiB”就是**参数常驻 + Prove 单峰**，而非两个不同峰叠加。

### 13.2 缺口 1：峰值落点

峰值发生在 **H query 的 G1 MSM 调用内部**：

```
H 调用进入时 live               78,596,989 B   (实测)
+ H 窗口化指数表示              25,970,216 B   (实测)
= 104,567,205 B
+ 1 个 G1 桶数组 (4,095×144)       589,680 B   (实测)
= 105,156,885 B   ≈ 观测峰值 105,160,229 B  (残差 3,344 B)
```

### 13.3 缺口 2：桶数组实测（逐一吻合静态估算）

单线程 `BELLMAN_MSM_MEM_PROBE` 显示：G1 4,095 桶 = **589,680 B**、G2 4,095 桶 = **1,179,360 B**、输入 7 桶 = 1,008 / 2,016 B，全部与 `桶数×size_of(projective)` 到字节吻合。桶数组在每个 chunk 闭包内一次性分配、返回即释放。**结论：静态桶估算成立，但桶不是并行内存增量的主因。**

### 13.4 缺口 3：指数转换瞬态

groth16 第 292/309/316 行的 `Vec<Scalar> → Vec<Exponent>`：因 `into_iter` 期间源缓冲仍存活，瞬态 = 源 + 目标。Spend 实测：input 576 B、aux **7,101,936 B**、h **9,437,112 B**；转换后常驻即目标 `Exponent` 向量（aux 3.76 MiB、h 5.00 MiB）。属**有界瞬态**，优先级低。

### 13.5 新主因：MSM 的“窗口化指数表示”

`Exponent::chunks(c)` 产出 `ChunkedExponent::Chunks(Vec<u64>)`，**只有非零指数才分配** `chunk_count × 8` B（c=12 → 22×8 = 176 B/项，另有外层 `Vec` 每元素 32 B）。实测单线程窗口化增量：

| 调用 | 指数数 | c | chunk | 增量 | 平均 B/指数 | 推断非零密度 |
|---|---:|---:|---:|---:|---:|---:|
| **H query (G1)** | 131,071 | 12 | 22 | **25,970,216 B (24.77 MiB)** | 198.1 | ~94% |
| L / A_aux (G1) | 98,638 | 12 | 22 | 7,397,608 B | 75.0 | ~24% |
| B_aux (G2) | 98,638 | 12 | 22 | 7,396,664 B | 75.0 | ~24% |
| A/B input | 8 | 3 | 85 | 4,360 B | 545 | — |

**这是 Spend Prove 最大的单笔瞬态（~26 MB）**，远大于桶数组（0.59 MB）与指数转换（≤9 MB）；它同时是并行峰值抬升（100→135 MiB）的主因：多线程下不同 MSM 调用的窗口化缓冲同时驻留。

### 13.6 对瓶颈排序的更新

- **排名 #1（MSM）在内存维度上要改口径：** 主因是 **H query 的窗口化指数缓冲**，而不是桶数组。新的优化方向 = 降低窗口化表示成本（减少窗口数 `c`、按需生成窗口、位切片/就地表示），并注意它随**非零密度**增长。
- **新增权衡项：** 并行化把 Prove 瞬时内存从 ~34.5 MB 抬到 ~68.8 MB（1→8 线程），内存敏感部署需权衡。
- 指数转换（≤9 MB 瞬态）与桶数组（0.59 MB/个）**不是**当前内存瓶颈。

---

## 14. 新跑的 smoke 与核放置可复现性（2026-10-17）

本节对当前工作区实际执行 `cargo check` 并重跑 Output/Spend smoke（产出新的原始日志），同时量化本轮发现的一个**影响所有单线程数字**的问题：CPU 核放置。完整记录见 `experiments/metadata/sapling_smoke_fresh_runs_and_cpu_affinity_20261017.md`。

### 14.1 cargo check 与重跑的 smoke（绑核 LP0、无插桩）

- `cargo check --locked --offline` 通过（dev profile，7.09 s）。
- **Output smoke**：`prove_ms` 中位 **529.5 ms**（528.3–578.0），5/5 验证通过，proof 192 B。
- **Spend smoke**：`prove_ms` 中位 **3724.0 ms**（3697.1–3760.0），5/5 验证通过，proof 192 B。

新数据写入独立文件（`sapling_output_prover_runs_pinned_20261017.csv`、`sapling_spend_prover_runs_pinned_20261017.csv`），**未写入正式基线**。为保持来源分离，给 Output smoke 补了与 Spend smoke 一致的 `SAPLING_PROVER_RUNS_CSV` 覆盖（默认行为不变）。

### 14.2 单线程测量是双峰的（P-core / E-core）

同一 exe、同一参数、`RAYON_NUM_THREADS=1`，只改进程亲和性：

| 亲和性 | 落在 | 5 次 prove 中位 | 参数加载 |
|---|---|---:|---:|
| `0x1` / `0x3`（限 P-core） | P-core | **3.69–3.77 s（±2%）** | ≈25.5 s |
| `0x100000`（LP20） | E-core | **8.13 s** | ≈54.4 s |
| 无（未约束） | OS 决定 | **8.72 s**（另一次实测） | ≈57.3 s |

⇒ 未约束时单线程 prove 在 **3.4–8.9 s** 之间（最高 **2.6×**），取决于 OS 把它放到 P-core 还是 E-core；绑核后稳定在 ≈3.7 s。**即：单线程测量不绑核就不可复现。**

### 14.3 正式基线本身也被该混淆污染（原始文件未改动）

对既有 `*_runs_release.csv` 的单线程批次按核态分层：

| 数据集 | 快态（P-core） | 慢态（E-core） |
|---|---|---|
| Spend 1 线程（27 批） | 18 批，3385.7–3535.7 ms | **9 批（33%）**，5357.5–8020.5 ms |
| Output 1 线程（30 批） | 25 批，502.5–538.4 ms | **4 批（13%）**，885.5–1048.2 ms |

⇒ 历史“单线程 ≈3.4 s / ≈0.51 s”与“同配置 ≈8 s / ≈1.0 s”并存，原因是核放置而非代码或参数差异。**既有的单线程中位数是把两个物理运行态混在了一起。**

### 14.4 对结论的影响

1. §8.2/§8.3 的 fallback 消融已用绑核消除该混淆；结论不受影响。
2. 报告与基线中所有**未绑核**的单线程时间应标注为「未约束分布」，或按核态分层；**绑核可复现值（Spend ≈3.7 s、Output ≈0.53 s）才是可复现参考**。
3. 多线程批次同样可能受 P/E 核与亲和性影响（§12.4 第 5 项），复测时应固定亲和性/电源策略。

---

*本报告为工程细化与瓶颈定位，不构成算法级优化成功的声明。所有引用的时间均为对应批次的观测值，不是通用延迟保证。*
