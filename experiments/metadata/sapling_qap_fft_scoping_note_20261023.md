# Sapling QAP/FFT 子阶段侦察（2026-10-23）

> **状态：探索性侦察，不是正式 campaign。** 本记录没有预注册、没有冻结阈值、没有
> 判定表，也不改变任何生产默认值。它只回答一个问题：在 Stage 1b/2/3 关闭窗口、
> 重叠线之后，单次 Spend 证明内部剩余的 QAP/FFT 阶段是否还有值得预注册的
> 端到端优化候选。

## 1. 目的与边界

Stage 1b 的 8 线程阶段中位为：synthesis `118.724 ms`、QAP/FFT `110.215 ms`、
H dispatch `0.072 ms`、assignment prep `3.300 ms`、scalar terms `1.815 ms`、
wait+assembly `445.014 ms`、body `680.152 ms`。Stage 3 又表明独立 proof 共享线程池
的批次吞吐点估计不能通过稳健性门槛。因此本轮只检查 **单次证明内部** 的
QAP/FFT：

- QAP 的 `110 ms` 级总时间里，三组逆 FFT、三组 coset FFT、逆 coset FFT 和
  O(n) 逐元素 pass 各占多少；
- 三组独立 FFT 能否通过并发重叠，在不改变默认路径的情况下降低 QAP wall；
- 单组 FFT 的 8 线程并行效率不高时，是否可以把三组变换各分到 2 线程，用
  **3×2 池 + pipeline** 提高聚合吞吐；
- 若这些调度机制仍不能把 QAP 降到约 80 ms，是否还有足够的剩余空间去支撑
  一个 5% 端到端目标的正式实验。

本轮不重开 MSM 窗口、不重开独立 proof 重叠、不测试 Output/交易，也不对
synthesis 作结论。

## 2. 方法

- 在 `vendor/groth16/src/prover.rs` 增加默认关闭的
  `SAPLING_QAP_STAGE_PROBE=1`，用 `Instant` 在 QAP 子阶段边界打点。探针不改变
  运算；关闭时每个 proof 只多一次缓存 `OnceLock` 读取。
- 增加默认关闭的 `SAPLING_QAP_CONCURRENT_ABC=1`：把 `a/b/c` 的三组 `ifft` 和
  三组 `coset_fft` 分别放进嵌套 Rayon scope，让它们的 shuffle/copy 阶段可以
  重叠。三组变换写入互不重叠的向量，算术结果与顺序路径相同。
- 增加默认关闭的 `SAPLING_QAP_ABC_POOLS=1`：为 `a/b/c` 各建一个持久的 2 线程
  Rayon 池（共 6 个活跃线程），两组变换之间设屏障。增加
  `SAPLING_QAP_ABC_PIPELINE=1`（只在 pools 模式下生效）：每个字母的
  `coset_fft` 在该字母 `ifft` 结束后立即开始，不等另外两个字母。
- 运行 `spend_prover_smoke`，每个进程 5 个 proof；`RAYON_NUM_THREADS=8`，
  进程 affinity `0x5555`，参数文件为 `sapling-spend.params`。所有 proof 均验证。
- 先用一次 scouting（`pair0`，顺序）和两组反向 A/B 检查全 8 线程嵌套 scope：
  `pair1 = seq → abc`，`pair2 = abc → seq`。每组 5 个 proof；QAP 统计使用全部
  5 个 proof，`prove_ms` 仅作描述性参考并丢弃 run 1。
- 再做 2t / 4t / 8t 顺序 QAP 探针，估计单组 FFT 的线程缩放；然后做 **平衡的
  两臂 ABBA**：`seq_abba1 → pipe_abba1 → pipe_abba2 → seq_abba2`
  （C0,C1,C1,C0），每组 5 个 proof。这是判定用的比较。
- 另外做一次 **三臂顺序检查**：
  `final_abba_seq_a → final_abba_pipe_a → final_abba_pools_a →
  final_abba_pools_b → final_abba_pipe_b → final_abba_seq_b`。pipeline 和 pools
  都落在中间位置，顺序与处理混淆；它只用于说明为什么不能把中间臂的数值当作
  因果收益，**不是判定臂**。
- 运行环境：Windows 11，Intel i7-14700，32 GB；测量时 base HEAD
  `bfda9d6d5f8c642a26cf54f2a64141eca09f6c5c`。
  - 初始嵌套并发 5 组：测量源码 `prover.rs` SHA-256
    `0899acb0affde713e4dd370363278bab1493a347d2b30b935c66daaadaa39c03`，
    二进制 `spend_prover_smoke.exe` SHA-256
    `b02ffa3c44725136b9b54048a08477b07b8dbfb7712ceafe4bc49462666b6156`。
  - 3×2 池 / pipeline 最终构建：测量源码 SHA-256
    `10016877b65fdc6b058528bd4731cb5798aa9b7373fb5d72579662a47f6c7be3`，
    二进制 SHA-256
    `e8c6dbe71750920bd4c6ba8e26301afd5384ebc33b44a07c798472fe7c234c9c`。
  - 早期 `seq_t2` / `seq_t4` 使用 pre-pools 构建；`pools_pair1/2/3`、
    `seq_pair3/4` 使用 pools-only 中间构建，二进制哈希当时没有记录。它们只作
    机制侦察保留，**不进入判定**；provenance 见
    `qap_partitioned_scouting_manifest_20261023.csv` 的 `not-recorded` 标注。
  - Spend 参数 SHA-256 在所有运行中均为
    `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13`。

## 3. QAP 子阶段：FFT 占九成以上

`pair0` 的 5 个 proof 中位（探针开启，绝对时间含探针开销）：

| 子阶段 | 中位 (ms) | 说明 |
|---|---:|---|
| `domains_ms` | 0.541 | 三个 `from_coeffs` |
| `a_ifft` / `b_ifft` / `c_ifft` | 14.990 / 14.676 / 14.807 | 三组逆 FFT |
| `a_coset` / `b_coset` / `c_coset` | 15.122 / 15.132 / 14.919 | 三组 coset FFT |
| `mul_ab` | 0.922 | `a *= b` |
| `sub_c` | 0.546 | `a -= c` |
| `divide_z` | 0.537 | coset 上除以 Z |
| `icoset` | 15.725 | h 的逆 coset FFT |
| `h_exponents` | 6.077 | `Vec<Scalar> → Vec<Exponent>` |
| **QAP total** | **115.268** | 含探针开销 |

> 注：每个子阶段的中位独立计算，子阶段中位之和与 `total` 的中位可能相差约
> 1 ms；百分比按 115.268 ms 计算。

- 七个 FFT（三组 `ifft` + 三组 `coset_fft` + `icoset`）合计
  **105.598 ms**，占 QAP 的 **91.6%**。
- 剩余 9.67 ms 中，`h_exponents` 6.08 ms，三个逐元素 pass 约 2.0 ms，
  domain 构造 0.54 ms。
- Stage 1b 的无探针 QAP 中位是 110.215 ms；本记录的 115.268 ms 高约 4.6%，
  属于探针/同批系统差异，**不能与 Stage 1b 的绝对时间直接合并**。相对结构
  （FFT 占九成以上）在 `pair1` 的 112.717 ms 中重复出现：三组 `ifft` 44.486 ms、
  三组 `coset` 44.310 ms、`icoset` 15.500 ms，合计 104.296 ms（92.5%）。

线程缩放（顺序 QAP 探针，5 proof 全部进入 QAP 中位；`prove` 丢弃 run 1）：

| 线程 | QAP 中位 (ms) | 描述性 prove 中位 (ms) | 单组 ifft 约 (ms) |
|---:|---:|---:|---:|
| 2t | 233.274 | 1849.255 | 30–34 |
| 4t | 146.635 | 1079.360 | 18–21 |
| 8t | 118.803 | 716.308 | 15–17 |

单组 FFT 从 2t 到 8t 只快约 2 倍，而从 2t 到 4t 已接近 1.6 倍；这解释了为什么
把六个独立变换分到 3 个 2 线程池，可能比逐个用满 8 线程有更高的聚合吞吐。

**含义：** 若目标是端到端 5%，按 body ≈ 690–716 ms 计算需要约 34.5–35.8 ms；
QAP 必须从约 115–119 ms 降到约 80–83 ms，即 **下降约 30%**。只优化
`h_exponents`、逐元素 pass 或 domain 构造，即使全部清零也只有约 9.7 ms
（约 1.4% body），不够。唯一有量级的方向是让七个 FFT 快 30% 左右，或减少
FFT 次数。

## 4. 并发/分区候选

### 4.1 全 8 线程嵌套 scope：没有稳定收益

三组 `a/b/c` 的 `ifft` 与 `coset_fft` 在数据依赖上互相独立。把它们并发，理论上
可以让一组 FFT 的 shuffle/copy 与另一组的 sub-FFT 重叠。实测：

| 运行 | 顺序 | 模式 | QAP 中位 (ms) | 三组 ifft (ms) | 三组 coset (ms) | 描述性 prove 中位 (ms) |
|---|---|---|---|---:|---:|---:|
| `seq_probe` | pair0 | 顺序 | 115.268 | 45.401 | 44.472 | 689.497 |
| `seq_pair1` | pair1 | 顺序 | 112.717 | 44.486 | 44.310 | 687.799 |
| `abc_pair1` | pair1 | 并发 | 113.906 | 43.065 | 44.065 | 738.793 |
| `abc_pair2` | pair2 | 并发 | 108.825 | 40.623 | 42.432 | 711.853 |
| `seq_pair2` | pair2 | 顺序 | 123.739 | 48.862 | 49.548 | 832.667 |

- `pair1`：顺序 112.717 → 并发 113.906，QAP **+1.05%**，没有收益。
- `pair2`：并发 108.825，顺序 123.739，表面 QAP **−12.05%**；但 `seq_pair2`
  本身比 `seq_pair1` 慢 9.8%，同一组的 `prove` 中位也明显偏慢。这是运行顺序/
  系统漂移，不是可重复的因果收益。
- 把 15 个顺序 proof 与 10 个并发 proof 的描述性中位相比：115.268 → 111.365，
  QAP **−3.4%**，折合 body 约 **−0.6%**；而且这个数被 pair2 的慢顺序臂放大。

**机制解释：** 单组 FFT 已经使用全部 8 个 Rayon 线程；三组并发没有增加空闲
算力，只是把同样的 24 个 sub-FFT 任务重新排队。第一组 A/B 没有得到任何 wall
改善，第二组的“改善”与系统变慢同现，不能归因于重叠。

### 4.2 3×2 池 + pipeline：QAP 明显下降，但 body 只有 −3.89%

pools 模式把 `a/b/c` 各放进一个持久的 2 线程池；pipeline 模式让每个字母的
`ifft → coset_fft` 在自己的池里连续执行，不设组间屏障。平衡 ABBA 的 4 个
判定批：

| 运行 | 模式 | QAP 中位 (ms) | 三组 ifft+coset 合计 (ms) | icoset (ms) | 描述性 prove 中位 (ms) |
|---|---|---:|---:|---:|---:|
| `seq_abba1` | 顺序 | 119.047 | 93.622 | 16.213 | 702.498 |
| `pipe_abba1` | pipeline | 95.656 | 70.650 | 16.079 | 690.794 |
| `pipe_abba2` | pipeline | 97.192 | 71.571 | 16.010 | 686.086 |
| `seq_abba2` | 顺序 | 118.560 | 94.399 | 16.022 | 730.119 |

- 批次中位先算，再取臂中位：顺序 QAP **118.803 ms**、pipeline **96.424 ms**，
  QAP **−18.84%**；顺序 prove **716.308 ms**、pipeline **688.440 ms**，
  body **−3.89%**。
- 无反转：pipeline 最慢批 **690.794 ms** < 顺序最快批 **702.498 ms**，间隔
  11.704 ms（约为最快顺序批的 1.64%）。这个方向是稳定的，但幅度低于 5%。
- 机制上，pipeline 把六个独立变换的合计 wall 从约 93.6–94.4 ms 降到
  70.7–71.6 ms，节省约 22–23 ms。剩余 QAP 已接近由 `icoset`（约 16 ms）、
  `h_exponents`（约 6 ms）、逐元素 pass（约 2 ms）和 domain（约 0.5 ms）构成的
  地板；即使把 pipeline 的 6 线程调度开销全部消掉（70 ms → 理想 60 ms），
  QAP 也只能到约 86 ms，body 约 −4.6%，仍不到 5%。要达到 80 ms，必须同时让
  FFT 本身的算术变快。
- `final_pools` 单批出现 QAP **88.682 ms**、prove **627.246 ms** 的快速窗口
  数值。它没有配对的顺序控制，且与平衡 ABBA 的 pipeline 批不一致；按预先约定
  只作异常/漂移记录，不用于判定，也不据此启动正式实验。

### 4.3 三臂顺序检查：表面 −5.09%，但顺序混淆

在平衡 ABBA 之后又跑了一次三臂顺序检查：

| 运行 | 模式 | QAP 臂中位 (ms) | prove 臂中位 (ms) |
|---|---|---:|---:|
| `final_abba_seq_*` | 顺序 | 117.539 | 712.776 |
| `final_abba_pipe_*` | pipeline | 94.844 | 676.505 |
| `final_abba_pools_*` | pools | 95.225 | 682.073 |

按这组数，pipeline 的 body 是 **−5.09%**、pools 是 **−4.19%**，看似跨过 5%。
但运行顺序是 `seq, pipe, pools, pools, pipe, seq`：两个候选臂都在中间，两个
顺序臂在两端。该窗口内存在明显的 U 形系统漂移，处理和位置完全混淆；把它当作
pipeline 的因果收益会重复 Stage 2 的“顺序臂变慢放大收益”错误。因此判定只使用
4.2 的平衡 ABBA，**不采用 −5.09% 这个数**。三臂数据保留，用于解释为什么没有
据此写预注册。

## 5. 判定

**不启动正式 Stage 4，不改变默认值，关闭单证明 QAP/FFT 的调度/分区线。**

理由：

1. QAP 的 91.6% 已经是 FFT；其余部分全部清零也不到 1.5% body。
2. 全 8 线程嵌套并发没有稳定收益；3×2 池 + pipeline 的平衡 ABBA 只到
   **−3.89% body**（QAP −18.84%），无反转但低于 5% 门槛。
3. 3×2 pipeline 的 QAP 地板约 86 ms；要支撑 5% body 需要约 80 ms，必须让
   FFT 算术本身再快约 7–10%。这已经进入 radix-4 / split-radix / 不同 four-step
   分解的算术改写，属于新的机制，不是本轮“重叠/分区/调度”侦察能覆盖的。
4. 三臂顺序检查的 −5.09% 与位置混淆，不能作为预注册依据；在平衡设计下没有
   可冻结的“≥5% 端到端”候选。
5. 因此没有正式 campaign，也没有默认值变更；`SAPLING_QAP_ABC_POOLS` 和
   `SAPLING_QAP_ABC_PIPELINE` 只保留为默认关闭的实验工具，**不构成优化建议**。

如果未来继续时间线，正确的下一步不是重复本侦察，而是先单独预注册一个
**FFT 算术改写**的 scoping study（明确 radix-4/split-radix 的 op-count 上界、
正确性 gate 和 ≥5% body 的可行性），再决定是否进入 pilot。synthesis 是另一条
独立线（118.7 ms，单线程），本轮没有测量其内部可并行比例，不能与本结论混在
一起。

## 6. 偏差与限制

- **未预注册。** 本记录是机制侦察，没有 A/G 验收表；上表不构成正式 PASS/FAIL。
- **探针开销。** `SAPLING_QAP_STAGE_PROBE=1` 在每个子阶段边界取 `Instant`，
  绝对 QAP 时间可能比无探针路径高几毫秒；只应作同探针条件下的相对比较。
- **中间构建的 provenance。** `pools_pair1/2/3`、`seq_pair3/4` 是 pools-only
  中间构建，测量时的二进制哈希没有记录；`seq_t2`/`seq_t4` 是 pre-pools 构建。
  这些批次只作早期 scouting，已在 manifest 中标为 `not-recorded`，
  **不进入判定**。最终构建的 T2/T4、pools、pipeline 和平衡 ABBA 都有
  `100168…` / `e8c6…` 的源码/二进制哈希。
- **快速窗口异常。** `final_pools` 单批 prove 627.246 ms，比同批其它运行低约
  8–12%；没有配对控制，可能是热/频率/调度窗口。按预先约定保留但不使用。
- **三臂顺序混淆。** 三臂序列把两个候选放在中间、顺序控制放在两端；其
  −5.09% 与位置/漂移混淆，不构成因果证据。
- **顺序与漂移。** 平衡 ABBA 只有 2 批/臂；臂内批次差约 3–4%，无反转间隔只有
  1.64%。本记录只把它当作“低于 5%”的 scoping 证据，不声称有正式统计功效。
- **run 1 冷启动。** `seq_probe` 的 proof 1 synthesis 为 178.381 ms（冷），
  `prove_ms` 统计丢弃 run 1；QAP 子阶段仍使用全部 5 个 proof，因为 QAP 本身
  没有相应的冷启动跳变。
- **没有排除任何 proof。** 归档的 26 个进程 × 5 = 130 个 proof 行全部
  `verified=true`；判定用的平衡 ABBA 为 20/20 验证成功。中间构建批次也没有
  被删除，只是不进入判定。
- **只测了 8 线程 / `0x5555`。** 其他线程数、affinity、硬件和 Output 电路未测；
  结论限于本机、本参数、本 pipeline。
- **代码状态。** 测量时 base HEAD 为 `bfda9d6`，工作树含本轮开关；最终构建的
  源码哈希与提交后的 `vendor/groth16/src/prover.rs` 相同。二进制哈希对应测量时
  的 release 构建。

## 7. 文件

- 探针/开关：`vendor/groth16/src/prover.rs`
  （`SAPLING_QAP_STAGE_PROBE`、`SAPLING_QAP_CONCURRENT_ABC`、
  `SAPLING_QAP_ABC_POOLS`、`SAPLING_QAP_ABC_PIPELINE`，均默认关闭）。
- 分析器：`scripts/analyze_qap_stage_probe.py`（只读原始日志，重建两张派生表；
  按 `round` 区分 pilot / intermediate / threads / pools / pipeline / abba /
  confounded）。
- 原始数据：`experiments/raw/csv/sapling_qap_stage_probe_20261023_*.csv`；
  原始 stderr：`experiments/raw/logs/sapling_qap_stage_probe_20261023_*.log`。
- manifest：`experiments/metadata/qap_stage_probe_manifest_20261023.csv`（初始
  5 组）和 `experiments/metadata/qap_partitioned_scouting_manifest_20261023.csv`
  （分区/线程/三臂新增批次，含 provenance 标注）。
- 派生表：`results/tables/sapling_qap_stage_probe_20261023.csv`（逐 proof）和
  `results/tables/sapling_qap_stage_probe_summary_20261023.csv`（逐进程中位 +
  平衡 ABBA / 三臂 arm 汇总）。
- 索引：`experiments/metadata/INDEX.md`；README §7.12；主报告 §30。
