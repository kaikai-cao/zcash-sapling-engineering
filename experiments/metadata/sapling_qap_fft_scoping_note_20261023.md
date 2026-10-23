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
- 若不能，是否还有足够的剩余空间去支撑一个 5% 端到端目标的正式实验。

本轮不重开 MSM 窗口、不重开独立 proof 重叠、不测试 Output/交易，也不对
synthesis 作结论。

## 2. 方法

- 在 `vendor/groth16/src/prover.rs` 增加默认关闭的
  `SAPLING_QAP_STAGE_PROBE=1`，用 `Instant` 在 QAP 子阶段边界打点。探针不改变
  运算；关闭时每个 proof 只多一次缓存 `OnceLock` 读取。
- 增加默认关闭的 `SAPLING_QAP_CONCURRENT_ABC=1`：把 `a/b/c` 的三组 `ifft` 和
  三组 `coset_fft` 分别放进嵌套 Rayon scope，让它们的 shuffle/copy 阶段可以
  重叠。三组变换写入互不重叠的向量，算术结果与顺序路径相同。
- 运行 `spend_prover_smoke`，每个进程 5 个 proof；`RAYON_NUM_THREADS=8`，
  进程 affinity `0x5555`，参数文件为 `sapling-spend.params`。所有 proof 均验证。
- 顺序：先做一次 scouting（`pair0`，顺序）；再做两组反向顺序的 A/B：
  `pair1 = seq → abc`，`pair2 = abc → seq`。每组 5 个 proof；QAP 统计使用全部
  5 个 proof，`prove_ms` 仅作描述性参考并丢弃 run 1。
- 运行环境：Windows 11，Intel i7-14700，32 GB；测量时 base HEAD
  `bfda9d6d5f8c642a26cf54f2a64141eca09f6c5c`，工作树含本轮探针/开关。
  测量源码 `prover.rs` SHA-256 `0899acb0affde713e4dd370363278bab1493a347d2b30b935c66daaadaa39c03`，
  二进制 `spend_prover_smoke.exe` SHA-256
  `b02ffa3c44725136b9b54048a08477b07b8dbfb7712ceafe4bc49462666b6156`，
  Spend 参数 SHA-256 `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13`。

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

**含义：** 若目标是端到端 5%，按 body ≈ 690 ms 计算需要约 34.5 ms；QAP 必须从
115 ms 降到约 80 ms，即 **下降约 30%**。只优化 `h_exponents`、逐元素 pass 或
domain 构造，即使全部清零也只有约 9.7 ms（约 1.4% body），不够。唯一有量级的
方向是让七个 FFT 快 30% 左右，或减少 FFT 次数。

## 4. 并发 A/B/C 候选：没有稳定收益

三组 `a/b/c` 的 `ifft` 与 `coset_fft` 在数据依赖上互相独立。把它们并发，理论上
可以让一组 FFT 的 shuffle/copy 与另一组的 sub-FFT 重叠。实测：

| 运行 | 顺序 | 模式 | QAP 中位 (ms) | 三组 ifft (ms) | 三组 coset (ms) | 描述性 prove 中位 (ms) |
|---|---|---|---:|---:|---:|---:|
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
  无论取哪种汇总，都远低于 5% 所需的 30% QAP 降幅。

**机制解释：** 单组 FFT 已经使用全部 8 个 Rayon 线程；三组并发没有增加空闲
算力，只是把同样的 24 个 sub-FFT 任务重新排队。第一组 A/B 没有得到任何 wall
改善，第二组的“改善”与系统变慢同现，不能归因于重叠。并发开关因此保留为默认
关闭的实验工具，**不构成优化建议**。

## 5. 判定

**不启动正式 Stage 4，不改变默认值，关闭单证明 QAP/FFT 线。**

理由：

1. QAP 的 91.6% 已经是 FFT；其余部分全部清零也不到 1.5% body。
2. 并发 A/B/C 没有稳定收益；最好情况下也只有约 0.6% body。
3. 要让 5% 端到端成立，需要约 30% 的 QAP 降幅，即七个 FFT 各快约三成。
   这已经进入 radix-4 / split-radix / 不同 four-step 分解的算术改写，属于新的
   机制，不是本轮“重叠/调度”侦察能覆盖的；本轮也没有证据表明它能在不损伤
   正确性/可维护性的前提下达到 30%。
4. 因此没有可冻结的“≥5% 端到端”候选，不应为了跑一个正式 campaign 而先写
   预注册；预注册的前提是机制侦察已经给出足够大的上界。

如果未来继续时间线，正确的下一步不是重复本侦察，而是先单独预注册一个
**FFT 算术改写**的 scoping study（明确 radix-4/split-radix 的 op-count 上界、
正确性 gate 和 ≥5% body 的可行性），再决定是否进入 pilot。synthesis 是另一条
独立线（118.7 ms，单线程），本轮没有测量其内部可并行比例，不能与本结论混在
一起。

## 6. 偏差与限制

- **未预注册。** 本记录是机制侦察，没有 A/G 验收表；上表不构成正式 PASS/FAIL。
- **探针开销。** `SAPLING_QAP_STAGE_PROBE=1` 在每个子阶段边界取 `Instant`，
  绝对 QAP 时间可能比无探针路径高几毫秒；只应作同探针条件下的相对比较。
- **顺序与漂移。** `pair1` 是 `seq → abc`，`pair2` 是 `abc → seq`；`seq` 的 QAP
  中位从 112.717 漂到 123.739（+9.8%），`prove` 中位从 687.799 漂到 832.667
  （+21.1%）。因此不能把两组合并成一个因果点估计；本记录只把它当作“没有稳定
  收益”的证据。
- **run 1 冷启动。** `seq_probe` 的 proof 1 synthesis 为 178.381 ms（冷），
  `prove_ms` 统计丢弃 run 1；QAP 子阶段仍使用全部 5 个 proof，因为 QAP 本身
  没有相应的冷启动跳变。
- **没有排除任何 proof。** 25 个 QAP 行、25 个 proof 行全部保留；并发臂 10/10、
  顺序臂 15/15 均验证成功。
- **只测了 8 线程 / `0x5555`。** 其他线程数、affinity、硬件和 Output 电路未测；
  结论限于本机、本参数、本 pipeline。
- **代码状态。** 测量时 base HEAD 为 `bfda9d6`，工作树含本轮开关；测量源码哈希
  与提交后的 `vendor/groth16/src/prover.rs` 相同。二进制哈希对应测量时的 release
  构建。

## 7. 文件

- 探针/开关：`vendor/groth16/src/prover.rs`
  （`SAPLING_QAP_STAGE_PROBE`、`SAPLING_QAP_CONCURRENT_ABC`，均默认关闭）。
- 分析器：`scripts/analyze_qap_stage_probe.py`（只读原始日志，重建两张派生表）。
- 原始数据：`experiments/raw/csv/sapling_qap_stage_probe_20261023_*.csv`；
  原始 stderr：`experiments/raw/logs/sapling_qap_stage_probe_20261023_*.log`。
- manifest：`experiments/metadata/qap_stage_probe_manifest_20261023.csv`。
- 派生表：`results/tables/sapling_qap_stage_probe_20261023.csv`（逐 proof）和
  `results/tables/sapling_qap_stage_probe_summary_20261023.csv`（逐进程中位）。
- 索引：`experiments/metadata/INDEX.md`；README §7.12；主报告 §30。
