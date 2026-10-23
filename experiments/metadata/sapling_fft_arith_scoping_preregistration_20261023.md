# 预注册：FFT 算术重写侦察（Stage 5 前置，2026-10-23）

> 本文件在编写任何 FFT 候选实现或运行任何候选计时**之前**填写并冻结。
> 它只用于决定“是否值得开正式 Stage 5 端到端试验”，**不是**正式优化验收，也**不改变**任何生产默认值。
> 冻结后阈值与判定规则不得修改；若实测中发现标准写错，只能在结果文档里记录偏差，不能回改本文档。
>
> 上游依据：Stage 4（`sapling_qap_fft_scoping_note_20261023.md`）已关闭 QAP/FFT 调度与分区线：
> 平衡 ABBA 的 3×2 pipeline 只把 QAP 从 **118.803 ms** 降到 **96.424 ms**、body 从 **716.308 ms** 降到
> **688.440 ms（−3.89%）**，低于 5% 目标；非 FFT 子阶段已接近地板。Stage 4 明确留下的唯一数量级候选是
> **FFT 算术重写**，但必须先做本侦察，不能直接开正式战役。

---

## 0. 一句话

当前 `vendor/bellman/src/domain.rs::serial_fft` 在每个蝶形上执行一次 **twiddle 递推乘法**
（`w.mul_assign(&w_m)`），因此每个 stage 的域乘法约为“数据乘法 + twiddle 更新”各 `n/2` 次。
本侦察要回答：**把 twiddle 预计算成表（以及可选的 radix-4 融合）能否在单次 FFT 上达到 ≥25–30% 的
稳定加速，从而值得开正式的端到端 Stage 5？** 只测独立 kernel，不测证明端到端，不改生产代码。

---

## 1. 边界与不做什么

| 项目 | 约定 |
|---|---|
| 性质 | **侦察（scoping）**，不是正式优化战役；没有端到端 PASS/FAIL 声明 |
| 代码范围 | 仅新增 `experiments/prover-smoke/src/bin/fft_arith_bench.rs`（或等价独立 bench 二进制）；**不修改** `vendor/` 和任何生产默认值 |
| 测量范围 | BLS12-381 scalar 域上的单次 FFT kernel；n = 2^10、2^13、2^14、2^17；1 线程与 8 线程 full transform |
| 不测 | 完整 Groth16 证明、参数读取、MSM、内存峰值、交易构造、跨机器 |
| 结果用途 | 只决定是否写正式 Stage 5 预注册；若 GO，正式战役另立阈值、另做正确性与端到端验收 |
| 失败处理 | 任何门禁失败都按第 3 节归档为 NO_GO / MARGINAL，不用“删掉失败候选”的方式重开 |

---

## 2. 基线与候选

### 2.1 基线（只读现有代码路径）

- **1t 基线**：`EvaluationDomain::fft`，`Worker` 为 1 线程（`log_cpus = 0`），走现有
  `serial_fft`；这正是当前生产单线程路径。
- **8t 基线**：`EvaluationDomain::fft`，`Worker` 为 8 线程（`log_cpus = 3`），走现有
  `parallel_fft` + 8 个 `serial_fft` 子变换；这是 Stage 4 使用的生产多线程路径。
- **镜像基线（harness control）**：bench 内复制现有 `serial_fft` / `parallel_fft` 的蝶形与 shuffle
  顺序，得到与基线数值逐位一致的 `fft_radix2_onfly` / `parallel_fft_onfly`。镜像基线只用于
  排除 bench harness 自身开销；生产基线仍是 `EvaluationDomain`。

### 2.2 候选 A：radix-2 + 预计算 stage twiddle 表

保持现有 bit-reversal、蝶形顺序和数值表达式不变，只把每个 stage 的 `w_m^j` 预先算进表：

- 每个 stage 先构造 `twiddles[0..m]`，`twiddles[0] = 1`，`twiddles[j] = twiddles[j-1] * w_m`；
- 每个 block 的 `j` 直接读 `twiddles[j]`，不再在每个蝶形后 `w *= w_m`；
- 数值上与现有 `serial_fft` **逐位相同**（同值、同乘法顺序），因此正确性门禁可以要求严格相等。

预期操作数（n = 2^L）：

- 基线：数据乘法 `(n/2)L` + twiddle 更新 `(n/2)L` = `nL`；加法 `nL`。
- 候选 A：数据乘法 `(n/2)L` + 表构造 `n − 1 − L`；加法 `nL`。
- 例如 n = 2^17：基线 2,228,224 次域乘；候选 A 约 1,245,166 次（**0.559×**）。
  n = 2^14：基线 229,376 次；候选 A 约 131,071 次（**0.571×**）。
- 表内存：1t 最大 `n/2` 个 scalar（2^17 时 2,097,152 B）；8t 子变换 n = 2^14 时每线程
  最大 256 KiB。候选 A 的计时包含表的分配与填充。

### 2.3 候选 B（条件触发）：radix-4 / 混合基 + 预计算 twiddle

只有在候选 A 未达第 3 节 GO 门禁、但达到 MARGINAL 区间时才实现：

- n = 2^L：用 `L mod 2` 决定一个 radix-2 stage + 若干 radix-4 stage（或先 radix-4 再收尾 radix-2）；
- twiddle 仍预计算；radix-4 蝶形按标准 3 个 twiddle 乘法实现；
- 必须与基线在全部测试 n 上严格相等；若实现无法在本次侦察时间内通过正确性门禁，记录为
  `not-tested`，不得用“看起来更快”的未验证实现替代。
- split-radix 不在本次默认实现范围内；只有在 A、B 都失败且时间允许时才追加，并单独记录。

> 选择顺序是预注册的：**A 先测**。A 若通过 GO，就不需要为了“覆盖 radix-4”而强行实现 B；
> 结果文档必须明确写“B 未测，原因是 A 已满足开正式战役的条件”，避免把未测候选说成已排除。

### 2.4 为什么不是调度/分区

Stage 4 已把 3×2 pipeline 的 QAP 降到 96.424 ms，body 只到 −3.89%；其非 FFT 部分约 9.7 ms，
即使 pipeline 零开销也到不了 5%。本侦察只动 FFT 算术，不重新打开线程池/ABBA 调度线。

---

## 3. 冻结门禁

所有门禁在同一个二进制、同一台机器、同一天会话内完成；计时前设置进程亲和性并读回。

### 3.1 正确性/机制门禁

| # | 门禁 | 阈值 | 判据 |
|---|---|---|---|
| C0 | harness control：镜像基线 vs 生产基线 | 1t 与 8t 的中位差均 ≤10% | 必须；否则先修正 harness，不得用失真的镜像值做结论 |
| C1 | 候选输出与基线严格相等 | 全部 n、全部被测实现 100% 相等 | 必须；任一不等即 NO_GO |
| C2 | 操作数模型一致（候选 A） | 实测/理论乘法比在 `[0.90, 1.10]` 内；候选 A 理论乘法比 ≤0.60 | 必须；否则记录模型或实现错误 |
| C3 | 表内存 | 1t/2^17 额外表 ≤2.5 MiB；8t/2^14 每线程 ≤256 KiB | 必须；超出即 NO_GO（本次不测全局 RSS） |

### 3.2 速度门禁（主判据）

以 **生产基线中位 / 候选中位** 定义 speedup；同一实现至少 8 个有效测量（见 §4）。

| # | 口径 | GO 阈值 | MARGINAL | NO_GO |
|---|---|---:|---|---|
| S1 | 1t，n = 2^17（Spend 全尺寸） | ≥ **1.30** | 1.15–1.30 | <1.15 |
| S2 | 1t，n = 2^14（8t 四步法的子变换尺寸） | ≥ **1.25** | 1.10–1.25 | <1.10 |
| S3 | 8t full transform，n = 2^17（含 shuffle/copy） | ≥ **1.25** | 1.10–1.25 | <1.10 |

**判定规则（冻结）：**

- **GO**：C0–C3 全过，且 S1、S2、S3 全达 GO 阈值 → 另写正式 Stage 5 预注册；
- **MARGINAL**：C0–C3 全过，但任一 S 落在 MARGINAL 区间 → 可继续测候选 B；B 也至多
  MARGINAL 则关闭算术线，不开正式战役；
- **NO_GO**：C1 失败，或 C2/C3 失败，或 S1/S2/S3 任一低于 NO_GO 阈值 → 关闭算术线，
  不再用同一次测量重挑子集。

> 这些阈值只回答“是否值得开正式 Stage 5”。1.25–1.30 的 kernel 加速**不足以单独保证**
> 5% body；正式 Stage 5 必须自己证明端到端 ≥5%，并可与 Stage 4 的 3×2 pipeline 组合。
> 本侦察不做“QAP 投影达标即通过”的替代判定。

---

## 4. 测量设计

### 4.1 输入与尺寸

- 域：`bls12_381::Scalar`，与 Sapling 证明器一致；不使用浮点。
- n：`2^10`、`2^13`、`2^14`、`2^17`；其中 2^17 是 Spend 域，2^14 是 8t 四步法子变换尺寸。
- 输入：确定性标量序列（按索引线性同余生成），每个实现从同一份原始输入拷贝；拷贝在计时区外。
- 正确性：对每个 n、每个实现，输出与生产基线逐元素严格比较；8t 只在 2^17 做一次逐位比较。
  另在 2^10/2^13 上用朴素 DFT 或基线做交叉检查（只作诊断，不作为门禁）。

### 4.2 计时协议

- 预热：每个实现先跑 3 次（不计时）；随后测 9 次，**丢弃第 1 次**，对剩余 8 次取中位。
- 顺序：基线/候选交替，采用 `B,A,A,B,B,A,A,B...` 的 ABBA 式循环，减少单侧漂移。
- 1t：进程亲和性 `0x1`，`RAYON_NUM_THREADS=1`；生产基线 `Worker` 的 `log_num_threads() == 0`。
- 8t：进程亲和性 `0xFFFF`，`RAYON_NUM_THREADS=8`；生产基线 `Worker` 的 `log_num_threads() == 3`。
- 计时区只包含 FFT 调用；输入恢复、分配和输出校验在计时区外。候选 A 的 twiddle 表分配/填充
  在 FFT 函数内部，**包含**在计时区（这是实际每次调用的成本）。
- 每次输出一个校验和（例如 8 个标量字节的 FNV）并打印，防止优化器删除整个变换。
- 异常：进程崩溃、亲和性读回不一致、基线 `log_num_threads` 不符、输出不等，整轮作废并记录；
  不得覆盖已写出的 raw CSV。

### 4.3 原始数据与派生表

- 原始：`experiments/raw/csv/sapling_fft_arith_scoping_20261023_1t.csv` 与 `_8t.csv`
  （每行一次计时；列至少含 `impl,threads,n,run,elapsed_ms,checksum`）；
- 正确性：`experiments/raw/csv/sapling_fft_arith_scoping_20261023_correctness.csv`；
- 日志：`experiments/raw/logs/sapling_fft_arith_scoping_20261023_*.log`；
- 派生：`results/tables/sapling_fft_arith_scoping_20261023.csv`（中位、min/max、speedup、
  操作数比、表内存）；分析脚本 `scripts/analyze_fft_arith_scoping.py`。
- 元数据：二进制 SHA-256、`git rev-parse HEAD`、dirty 状态、`rustc -V`、亲和性、环境变量、完整命令。

---

## 5. 预期与停止规则

- 若候选 A 的 S1 ≥1.30 且 S3 ≥1.25：说明 twiddle 预计算把“每蝶形一次额外域乘”消掉后仍有
  足够大的真实收益；进入正式 Stage 5 预注册（端到端 5%、正确性、默认值策略另定）。
- 若候选 A 只有 1t 快、8t 不快：说明四步法的 shuffle/copy 或内存带宽吃掉收益；MARGINAL，
  不因 1t 的单点漂亮而开正式战役。
- 若所有候选 <1.15：关闭 FFT 算术线；Stage 4 的结论保持不变，不再重复“换调度/换线程池”。
- 若正确性无法保持逐位相等：即使速度更快也 NO_GO；不允许用“容差”替代 FFT 等式。

---

## 6. 与既有文档的关系

- Stage 4 侦察：`experiments/metadata/sapling_qap_fft_scoping_note_20261023.md`
- 测量协议：`experiments/metadata/sapling_optimization_validation_protocol_20261017.md`
- 当前 FFT 实现：`vendor/bellman/src/domain.rs`（`serial_fft` / `parallel_fft`）
- 本侦察结果（待写）：`experiments/metadata/sapling_fft_arith_scoping_results_20261023.md`

---

## 7. 冻结签名

- 预注册日期：2026-10-23
- 代码改动前 HEAD：`ce1105f7827c3a3495323ca9ac58b1c7699962eb`
- 状态：**FROZEN**（先于任何候选 FFT 实现与候选计时）
