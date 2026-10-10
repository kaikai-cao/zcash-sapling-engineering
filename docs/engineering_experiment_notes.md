# Zcash Sapling / Groth16 工程实验记录

## 1. 实验目的与范围

本实验以真实 Sapling Spend 和 Output 电路为案例，记录电路规模、参数文件、证明与验证开销、峰值工作集内存，并梳理 Zcash 的证明调用链。

本阶段目标是形成可复现的工程基线，而不是优化旧版 Groth16 实现。Spend 和 Output 是不同的电路与工作负载，实验数据用于分析各自的规模与成本结构，不代表两者在相同计算任务上的直接性能竞赛。

## 2. 实验环境与源码版本

- 工程仓库：`kaikai-cao/zcash-sapling-engineering`
- 官方 `sapling-crypto` 本地源码：`D:\Research\zcash-sapling-crypto`
- 源码版本：`sapling-crypto 0.9.0`
- 固定源码 commit：`88a7946b4a3066787776e11f0a502654167e022d`
- 构建配置：Rust release profile
- 线程设置：`RAYON_NUM_THREADS=1`
- 参数文件位置：`D:\Research\zcash-params\`
- 参数文件不应提交进 Git 仓库。

正式证明性能统计只纳入预先选定的两个批次：
- Spend：`1791613854129`
- Output：`1791549582046`

其他批次可以保留在原始数据中，但不能未经说明就混入正式基线统计。

## 3. 电路规模

| 指标 | Spend | Output |
|---|---:|---:|
| 约束数量 | 98,777 | 7,827 |
| 辅助变量 | 98,638 | 7,821 |
| 不含常数 1 的公开输入数 | 7 | 5 |
| 含常数 1 的输入变量数 | 8 | 6 |
| Domain size | 131,072 | 8,192 |

约束和变量数量由 Counting ConstraintSystem 统计。Domain size 并非直接读取底层域结构得到，而是采用 `next_power_of_two(constraints)` 估算。

原始数据：`experiments/raw/csv/sapling_circuit_scale_raw.csv`
汇总数据：`results/tables/engineering_scale.csv`

## 4. 参数文件

| 指标 | Spend 参数 | Output 参数 |
|---|---:|---:|
| 文件大小 | 47,958,396 bytes | 3,592,860 bytes |
| 文件大小 | 45.737 MiB | 3.426 MiB |
| SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 参数读取与验证时间（元数据程序） | 24,326.502 ms | 1,774.506 ms |
| 点编码校验 | 通过 | 通过 |

完整的 BLAKE2b-512 哈希和文件路径保存在 `results/tables/engineering_parameters.csv`。

元数据程序中的参数读取与验证耗时各只有一次测量，不能作为稳定的冷启动或热启动性能统计。证明程序运行时另外记录了参数读取与验证时间：Spend 为 23,967.432 ms，Output 为 1,807.789 ms。由于它们来自不同运行批次，不应混为同一组重复实验。

原始数据：`experiments/raw/csv/sapling_parameter_metadata_raw.csv`

## 5. 证明和验证性能

正式基线均为 release、单线程，每种电路 5 次测量。

| 指标 | Spend | Output |
|---|---:|---:|
| Prove 中位数 | 3,385.716 ms | 514.853 ms |
| Prove 最小值 | 3,377.138 ms | 507.096 ms |
| Prove 最大值 | 3,484.750 ms | 560.162 ms |
| Verify 中位数 | 2.790 ms | 2.150 ms |
| Verify 最小值 | 2.775 ms | 2.102 ms |
| Verify 最大值 | 2.797 ms | 2.195 ms |
| Proof size | 192 bytes | 192 bytes |
| 成功验证次数 | 5/5 | 5/5 |

Prove 计时围绕单次证明生成调用，不包含参数加载、验证密钥预处理和测试见证构造。Verify 计时针对实验程序中的单次电路证明检查，不等于完整 Zcash 交易的全部验证耗时。

证明大小是本实验程序编码得到的证明字节数，不能据此推断整个交易或交易中的全部 Sapling 数据大小。

正式汇总：`results/tables/engineering_performance.csv`
原始 Spend 数据：`experiments/raw/csv/sapling_spend_prover_runs_release.csv`
原始 Output 数据：`experiments/raw/csv/sapling_output_prover_runs_release.csv`

原始 Output CSV 中还保留了后续内存测量进程产生的新证明批次。正式汇总脚本只选择上面列出的正式基线批次，避免将不同目的的实验合并统计。

## 6. 峰值工作集内存

| 指标 | Spend | Output |
|---|---:|---:|
| Peak Working Set | 101.31 MiB | 22.22 MiB |
| 线程设置 | 1 | 1 |
| 构建配置 | release | release |
| 独立进程退出码 | 0 | 0 |
| 实验结果 | PASS | PASS |

该指标来自 Windows 进程的 `PeakWorkingSet64`。测量脚本每 250 ms 查询一次该高水位指标，并记录观测值中的最大值。

这里记录的是整个实验进程的峰值工作集，包括参数加载、参数验证、证明生成和验证，并非证明算法单独占用的峰值内存。每种电路目前只测量了一次，因此只能作为初步观测值。

原始记录：`experiments/raw/csv/sapling_process_memory_raw.csv`
汇总记录：`results/tables/engineering_memory.csv`

## 7. Zcash Sapling 调用链

工程调用链和对应源码位置记录于 `docs/zcash_sapling_flow.md`。

主线为钱包侧交易构造，经过交易 Builder，再进入 Sapling Bundle 的证明生成流程，最终调用 SpendProver 或 OutputProver，并使用相应参数执行 Groth16 证明。验证路径则涉及 SaplingVerificationContext 或批量验证组件。

本实验直接测试 Spend 和 Output 的证明与电路证明检查，并未测量完整钱包交易构造、签名、网络传播或全部共识验证流程。因此，本报告的时间数据不能等同于生成一笔真实 Zcash 交易的端到端耗时。

## 8. 图表与汇总文件

核心汇总表：
- `results/tables/engineering_scale.csv`
- `results/tables/engineering_parameters.csv`
- `results/tables/engineering_performance.csv`
- `results/tables/engineering_memory.csv`

生成图表：
- `results/figures/sapling_circuit_constraints.png`
- `results/figures/sapling_circuit_auxiliary_variables.png`
- `results/figures/sapling_parameter_sizes.png`
- `results/figures/sapling_parameter_load_validate.png`
- `results/figures/sapling_prove_time.png`
- `results/figures/sapling_verify_time.png`
- `results/figures/sapling_proof_size.png`

汇总脚本：`scripts/summarize_engineering.py`

原始 CSV 保存测量数据；汇总表用于分析；图表用于展示。重新生成汇总文件时，应继续使用明确选定的正式性能批次，不要修改或覆盖原始测量记录。

## 9. 当前结论与限制

1. Spend 的约束规模约为 Output 的 12.62 倍；本次测得的证明时间中位数约为其 6.58 倍。这是两个不同电路在当前环境中的测量结果，不代表仅由约束数量决定的通用性能比例。
2. 两种电路的证明都成功通过检查，编码后的证明大小均为 192 bytes。
3. Spend 的参数文件明显更大，参数读取与验证也耗时更长。由于当前每种参数仅有单次元数据测量，不能据此建立稳定的缓存或冷启动模型。
4. 当前已有单线程 release 配置下的 5 次证明与验证数据，但尚未形成严格控制操作系统缓存状态的冷启动/热启动对照实验。
5. 峰值工作集只有每种电路一次测量，且统计整个进程生命周期。它不是 Prove 阶段独占内存的测量。
6. 当前实验不是完整的 Zcash 端到端交易基准，不能据此直接声称真实交易创建或整个系统的性能水平。
7. 当前结果是工程学习和可复现基线；它们尚不构成经过多次独立重复、误差分析和跨环境验证的性能研究结论。

本报告应与原始 CSV、源码固定版本以及参数哈希一起保存，确保今后能够追溯测量口径和数据来源。
