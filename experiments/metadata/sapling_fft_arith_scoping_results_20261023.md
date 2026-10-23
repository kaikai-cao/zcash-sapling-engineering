# FFT 算术重写侦察结果（Stage 5 前置，2026-10-23）

> 预注册：`experiments/metadata/sapling_fft_arith_scoping_preregistration_20261023.md`（SHA-256
> `0148d93569505e9ea50d9163f517692cbc3cf7cdcd1b300f20a57cca66235d47`）。
> 本文件只记录侦察结果；**不是正式 Stage 5，不改变任何生产默认值**。
> 判定严格按预注册冻结的 C0–C3、S1–S3 门禁执行，未在看见数据后改阈值。

---

## 0. 一句话

把 `serial_fft` 的 twiddle 递推改成预计算表后，**单线程 kernel 有稳定的大幅收益**：
n = 2^17 的 1t FFT 从约 **45.8 ms 降到 29.5 ms（1.553×）**，n = 2^14 子变换从
**4.42 ms 降到 2.99 ms（1.479×）**。但生产使用的 **8 线程 full transform** 只从
**14.98 ms 降到 12.02 ms（1.246×）**，低于冻结的 **1.25× GO 门禁**；条件候选
radix-4 为 **1.242×**，没有补上差距。按预注册规则，本轮为 **MARGINAL**，
**关闭 FFT 算术线，不启动正式 Stage 5，不改变默认值**。

---

## 1. 预注册与执行

| 项目 | 内容 |
|---|---|
| 预注册 | `sapling_fft_arith_scoping_preregistration_20261023.md`，在候选实现前冻结 |
| 判定集 | `sapling_fft_arith_scoping_radix4_20261023`（同时含候选 A 与条件候选 B） |
| 复现集 | `sapling_fft_arith_scoping_20261023`（只含候选 A，较早一轮） |
| 批次 | 每个 tag 9 个 1t 批 + 9 个 8t 批；每批 3 次预热、9 次计时、丢弃 run 1，ABBA 交替 |
| 1t 亲和性 | `0x1`，`RAYON_NUM_THREADS=1`，`SAPLING_FFT_SERIAL_SINGLE_THREAD=1` |
| 8t 亲和性 | `0x5555`，`RAYON_NUM_THREADS=8`（与 Stage 4 的 8t 口径一致；见 §6 偏差） |
| 判定集测量 HEAD | `e41f1f858139eae747bc167c01895a49cfbd5086` |
| 判定集二进制 | `a997593b62f0f001efc6b74a5475e4346b34f98b1eed0dc8ffb3e99e1404c152` |
| 复现集二进制 | `05337c088443093c3f11fe29f1e391f5649ac86a96eef01bccf3853740241d5c` |
| 编译器 | `rustc 1.98.1 (48a229cea 2026-09-01)` |

判定集测量完成后，源码只追加了 crate 级 clippy allow（`assign_op_pattern`、
`explicit_counter_loop`、`manual_is_multiple_of`、`unusual_byte_groupings`），
目的是保持 baseline/mirror 的逐行表达式；kernel 表达式没有改写。因此当前分支
HEAD 会晚于测量 HEAD，但正式 raw 对应的二进制仍是 `a997…`，本轮不重跑、不覆盖
raw，也不把新构建的二进制冒充测量二进制。

测量代码是独立 bench 二进制
`experiments/prover-smoke/src/bin/fft_arith_bench.rs`；它不链接进证明器，不修改
`vendor/`，也不写参数文件。生产基线始终是现有 `EvaluationDomain::fft`：
1t 走 `serial_fft`，8t 走 `parallel_fft` + 8 个 `serial_fft` 子变换。镜像基线
`mirror_onfly` 是现有蝶形/shuffle 顺序的逐行复制，只用于 harness control。

---

## 2. 正确性

判定集 18 个进程、**234 行 correctness**（1t 每批 12 行，8t 每批 14 行），
全部 `exact_match=1`；每个 `(threads, n)` 的 checksum 集合只有唯一值。
复现集 18 个正式进程、216 行 correctness，也全部相等。被排除的首次 1t 批
（runner `ExitCode` 读取失败）另有 12 行，保留但不计入。

候选 A 与现有 `serial_fft` 使用相同 bit-reversal、蝶形顺序和同一组 twiddle 值，
因此要求逐位相等，而不是容差；候选 B 的 radix-4 只在四步法子变换
`log2(n_sub)` 为偶数的尺寸上启用（2^13、2^17 full domain 的子变换为 2^10、2^14），
同样逐位相等。没有发现任何 correctness 失败。

---

## 3. 操作数与表内存

候选 A 的静态乘法数（n = 2^L）：

- 基线：数据乘法 `(n/2)L` + twiddle 更新 `(n/2)L` = `nL`；
- 候选 A：数据乘法 `(n/2)L` + 表构造 `n − 1 − L`；
- 加法数两者相同，均为 `nL`。

| n | 基线乘法 | 候选 A 乘法 | 比值 |
|---:|---:|---:|---:|
| 2^14 | 229,376 | 131,057 | **0.571** |
| 2^17 | 2,228,224 | 1,245,166 | **0.559** |

两者都满足预注册的候选比值 ≤0.60。**偏差：** bench 没有运行时乘法计数器
（加计数器会改变被计时的二进制），所以预注册中“实测/理论在 10% 内”这一半
没有按运行时计数执行；本结果只报告从精确循环结构导出的静态计数。该偏差不影响
正确性或计时，但必须在这里明示。

表内存：1t/2^17 使用最大 stage 表 **2,097,152 B**（≤2.5 MiB）；8t 子变换
n = 2^14 使用一张 **524,256 B** 的共享全表（所有子变换只读共享，线程私有表为 0 B），
低于 2.5 MiB 上限。共享表是对预注册“每线程 ≤256 KiB”描述的实现细化：总表更小，
且不是每线程私有一份。

---

## 4. 速度结果

判定集（`radix4_20261023`）的批次中位、再取批中位：

| 口径 | 基线中位 | 候选 A 中位 | 候选 A speedup | 候选 B 中位 | 候选 B speedup | 门禁 |
|---|---:|---:|---:|---:|---:|---|
| 1t，n=2^17 | 45.809 ms | 29.490 ms | **1.553×** | — | — | S1 GO（≥1.30） |
| 1t，n=2^14 | 4.424 ms | 2.991 ms | **1.479×** | — | — | S2 GO（≥1.25） |
| 8t，n=2^17 | 14.980 ms | 12.021 ms | **1.246×** | 12.063 ms | **1.242×** | S3 MARGINAL（<1.25） |

较早的复现集（`20261023`，只含 A）得到同方向结果：1t n=2^17 **1.571×**、
1t n=2^14 **1.552×**、8t n=2^17 **1.202×**。两轮的 1t 结果一致；8t 点估计在
**1.202–1.246×** 之间，跨轮绝对时间有漂移（复现集 8t 基线 12.68 ms，判定集
14.98 ms），因此判定只用同一轮内的配对批次中位，不跨轮拼接绝对值。

Harness control 全部通过：判定集 `baseline/mirror` 为 1t/2^14 **0.975**、
1t/2^17 **0.985**、8t/2^17 **1.028**，均在 ±10% 内；复现集为 0.991、0.974、1.016。
镜像基线与生产基线逐位相等，排除了 bench harness 自身的主要偏差。

**机制解释。** 1t 的收益来自每个蝶形少一次 twiddle 更新域乘：2^17 时域乘从
2,228,224 降到 1,245,166（约 −44%），实测 1.55× 与操作数模型同向。8t 的收益被
四步法的固定部分吃掉：`parallel_fft` 仍有 n 次 shuffle 域乘、n 次加法、临时缓冲
分配/清零和 copy-back；这些不随子 FFT 的算术改写而减少。radix-4 虽然把子变换的
twiddle 乘法再降到约 0.75×，但每个蝶形要读 3 个 twiddle、并增加索引/加法开销，
在 8t full transform 上没有超过候选 A（1.242× vs 1.246×），所以条件候选 B 失败。

---

## 5. 判定

预注册门禁：

- C0 harness control：**PASS**；
- C1 逐位正确性：**PASS**（判定集 234/234，复现集 216/216）；
- C2 静态操作数比：**PASS**（0.559/0.571 ≤0.60；运行时计数器偏差见 §3）；
- C3 表内存：**PASS**；
- S1 1t/2^17：**GO**（1.553×）；
- S2 1t/2^14：**GO**（1.479×）；
- S3 8t/2^17：**MARGINAL**（最好 1.246×，低于 1.25×）。

按预注册规则：候选 A 为 MARGINAL，允许测条件候选 B；B 仍为 MARGINAL，因此
**关闭 FFT 算术线，不启动正式 Stage 5，不改变任何默认值**。

**为什么不把 1.246× 当作 GO：** 冻结阈值是 1.25×，点估计差 0.3 个百分点；
本轮不做事后改阈值、不挑一轮更高的数、不把“再跑一次可能过线”当作证据。
1t 的 1.55× 是真实的机制收益，但生产 8t 路径没有达到预注册的“值得开正式战役”
门槛。若所有者希望把该 kernel 与 Stage 4 的 3×2 pipeline 组合，必须另立
**所有者批准的例外/新预注册**；本轮没有测这个组合，不能把它写成结果。

作为量级说明（**不是判定依据**）：Stage 4 的 QAP 为 115.268 ms，其中 FFT 105.598 ms、
非 FFT 约 9.67 ms；若 8t full transform 的 1.246× 能原样迁移到该 QAP，投影约为
FFT 84.7 ms、QAP 94.4 ms（约 −18% QAP、body 约 −2.9%）。这只说明单靠算术改写
离 5% body 仍有距离，不能替代端到端测量。

---

## 6. 偏差、失败与排除

1. **8t 亲和性偏差：** 预注册写的是 `0xFFFF`，正式运行使用 `0x5555`。原因是
   Stage 4 的 8t 基线就是 `0x5555`，而 `0xFFFF` 在本机是 16 个逻辑处理器；
   为了让 8t 口径与 Stage 4 可比，主口径改用 `0x5555`。阈值未改；没有另跑
   `0xFFFF` 敏感性臂，这是本轮的方法学偏差。
2. **C2 运行时计数器未实现：** 见 §3；只报告静态操作数，未伪造“实测”值。
3. **条件候选 B 的范围：** 只在四步法子变换 `log2(n_sub)` 为偶数时实现/计时；
   odd 尺寸没有 radix-4 路径。split-radix 未实现，因为 B 已失败，继续追加不会
   改变“B 也至多 MARGINAL”的冻结判定。
4. **首次 1t 批 runner 失败：** PowerShell 包装器读不到子进程 `ExitCode`，但该批
   CSV 本身完整（156 行，12 正确性 + 144 计时，全部相等）。该批以
   `..._1t_b1_runnerexitcode_failed.csv` 保留并排除；正式集从修复后的
   `System.Diagnostics.Process` 包装器重新跑 9 批。没有覆盖任何 raw 文件。
5. **跨轮 8t 漂移：** 复现集与判定集的 8t 基线绝对时间相差约 18%，但每轮
   harness control 通过、候选/基线同轮配对；判定使用轮内比值，不把两轮绝对值
   合并。8t 的 S3 点估计仍应视为对系统负载敏感的区间，而不是精确常数。
6. **未改生产代码/默认值：** `vendor/bellman/src/domain.rs` 未修改；
   `SAPLING_QAP_*`、MSM 窗口等实验开关保持原默认；没有生成证明或交易。
7. **测量后 clippy-only 变更：** 正式 raw 完成后，bench 源码只加了 crate 级
   `allow` 以保留 baseline/mirror 的逐行表达式，并让 CI 的 `-D warnings` 通过；
   kernel 代码没有改写。当前分支 HEAD 晚于测量 HEAD，测量二进制仍是
   `a997…`；没有重跑正式集、没有覆盖 raw。重跑本地 correctness 检查仍为
   8t 14/14、1t 12/12 exact。

---

## 7. 产物

- 预注册：`experiments/metadata/sapling_fft_arith_scoping_preregistration_20261023.md`
- 结果（本文件）：`experiments/metadata/sapling_fft_arith_scoping_results_20261023.md`
- 判定集 manifest：
  `experiments/metadata/fft_arith_scoping_manifest_sapling_fft_arith_scoping_radix4_20261023.csv`
- 复现集 manifest：
  `experiments/metadata/fft_arith_scoping_manifest_sapling_fft_arith_scoping_20261023.csv`
- 判定集 raw：
  `experiments/raw/csv/sapling_fft_arith_scoping_radix4_20261023_{1t,8t}_b*.csv`；
  `experiments/raw/logs/sapling_fft_arith_scoping_radix4_20261023_*`
- 复现集 raw：
  `experiments/raw/csv/sapling_fft_arith_scoping_20261023_{1t,8t}_b*.csv`；
  `experiments/raw/logs/sapling_fft_arith_scoping_20261023_*`
- 失败批归档：
  `experiments/raw/csv/sapling_fft_arith_scoping_20261023_1t_b1_runnerexitcode_failed.csv`
- 派生表：
  `results/tables/sapling_fft_arith_scoping_20261023_summary.csv`；
  `results/tables/sapling_fft_arith_scoping_radix4_20261023_summary.csv`
- 代码/脚本：
  `experiments/prover-smoke/src/bin/fft_arith_bench.rs`；
  `scripts/run_fft_arith_scoping.ps1`；
  `scripts/analyze_fft_arith_scoping.py`

---

## 8. 结论边界

本轮只证明：

1. 预计算 twiddle 表能把 **单线程** radix-2 FFT 稳定加速约 **1.5×**，且逐位正确；
2. 该收益在现有 **8 线程四步法** full transform 上只剩约 **1.20–1.25×**，没有
   达到预注册的 1.25× GO 门槛；
3. radix-4 条件候选没有超过 radix-2 候选；
4. 因此不启动正式 Stage 5，不改变默认值，FFT 算术线关闭。

本轮不证明：端到端证明时间一定不下降（没有做正式端到端战役）；pipeline 与算术
改写组合无效（没有测）；其它 FFT 算法（split-radix、六步法、GPU 等）无效（没有测）。
这些都不能从本轮结果外推。
