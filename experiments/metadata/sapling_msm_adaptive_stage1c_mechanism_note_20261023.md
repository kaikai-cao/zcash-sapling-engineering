# Stage 1c 机制复核：同进程 8t 窗口 A/B（2026-10-23）

> 性质：**探索性机制复核，不是正式实验，不设 PASS/FAIL 阈值，不授权默认切换。**
> 关联：Stage 1b 结果 [`sapling_msm_adaptive_stage1b_results_20261022.md`](sapling_msm_adaptive_stage1b_results_20261022.md)；Stage 0 诊断 [`sapling_msm_scaling_diagnosis_results_20261022.md`](sapling_msm_scaling_diagnosis_results_20261022.md)。
> 二进制：`experiments/prover-smoke/target/release/msm_window_bench.exe`（由当前 `main` 重建）。
> 运行：2026-10-23，8t、亲和掩码 `0x5555`。

## 1. 目的

Stage 1b 的正式结果给出两个互相印证的否定：`C1/C0 = 1.019`，且强制 c=11 的正对照 `C4/C0 = 0.999`。因此“Stage 0 的 c=11 657.81 ms”没有在同 campaign 复现。为了判断这是**窗口选择本身**还是**跨 campaign 系统状态**，在同一个进程内交替测量 c=10/11/12/13 的 H-query 形状 MSM。

这不是重复 Stage 1b：没有 Sapling proof、没有 44 批、没有预注册阈值；它只回答“在相同 fixture、相同进程、相同 8t 亲和性下，c=11 是否仍显示优势”。

## 2. 设置

| 项 | 值 |
|---|---|
| 工具 | `experiments/prover-smoke/src/bin/msm_window_bench.rs` |
| n | 131,071（Spend H-query 形状） |
| 窗口 | c = 10, 11, 12, 13 |
| recoding | balanced signed（`MSM_WINDOW_BENCH_SIGNED=1`） |
| reps | 7；每 c 取 7 次中位 |
| 线程/亲和性 | `RAYON_NUM_THREADS=8`，`0x5555` |
| 数据 | 连续生成元倍点作为 base；确定性 xorshift 随机 Scalar 作为指数 |
| 顺序 | forward `10,11,12,13`；reverse `13,12,11,10` |
| 正确性 | 工具内置 naive prefix、n=8、跨 recoding、lazy/materialised、c=2..20 等 gate；两次均 `MSM_WINDOW_BENCH=DONE` |

命令（两次运行仅 `MSM_WINDOW_BENCH_C` 顺序不同）：

```powershell
$env:RAYON_NUM_THREADS='8'
$env:MSM_WINDOW_BENCH_C='10,11,12,13'   # 或 '13,12,11,10'
$env:MSM_WINDOW_BENCH_REPS='7'
$env:MSM_WINDOW_BENCH_SIGNED='1'
# 启动后设置 ProcessorAffinity = 0x5555
```

## 3. 结果

同进程 MSM `median_ms`（每 c 7 次中位）：

| 顺序 | c=10 | c=11 | c=12 | c=13 |
|---|---:|---:|---:|---:|
| forward | 333.078 | 274.621 | **262.940** | 270.372 |
| reverse | 374.110 | 317.262 | **295.556** | 298.613 |

相对同顺序 c=13：

| 顺序 | c=10 / c=13 | c=11 / c=13 | c=12 / c=13 |
|---|---:|---:|---:|
| forward | +23.2% | +1.6% | **−2.75%** |
| reverse | +25.3% | +6.3% | **−1.02%** |

绝对漂移（reverse / forward）：

| c | 比值 | 说明 |
|---|---:|---|
| 10 | 1.123 | 跨进程状态漂移 +12.3% |
| 11 | 1.155 | +15.5% |
| 12 | 1.124 | +12.4% |
| 13 | 1.105 | +10.5% |

## 4. 观察

1. **两次顺序下 c=12 都最低**，c=13 次之；c=12 相对 c=13 仅 −2.75% / −1.02%，幅度很小。
2. **c=11 在两次顺序下都不是最优**：相对 c=13 为 **+1.6% / +6.3%**；相对 c=12 为 **+4.4% / +7.3%**。这与 Stage 1b 的 `C1/C0 = 1.019`、`C4/C0 = 0.999` 方向一致，而不支持“c=11 在 8t 有稳定内在优势”。
3. c=10 明显最慢（+23% / +25%），与 Stage 1b 的 `C3`（c10 + tail4）仍慢 2.7% 的方向一致：c=10 的 fill 增加无法由 reduce 下降补偿。
4. 两次连续运行的绝对时间差 **10–16%**，比窗口间差异大；即使同一进程内顺序相反，c=12/c=13 的绝对水平也会整体漂移。这再次说明 Stage 0 的跨 campaign 657.81 ms 不能单独作为默认切换依据。

## 5. 解释与限制

- 该 bench 使用 synthetic fixture，不是 Sapling H-query 的真实 base/exponent 数据；它保留 n、窗口、recoding、8t 和 bucket 路径，但不包含 proof 的其余阶段、真实数据驻留和参数读取。
- 两次运行各自内部一致，但顺序/系统状态影响绝对值；不能把 c=12 的 1–3% 领先当作可发布收益，也不能用它推翻 Stage 1b 的正式阈值判定。
- 结论只到“**同进程 8t MSM 没有显示 c=11 的内在优势；Stage 1b 的 null 更可信**”。若未来还要研究窗口，应先用**真实 H-query 数据 + 新预注册**测试 c=12/c=13 的静态 A/B，而不是直接改默认值。

## 6. 产物

- forward：`experiments/raw/logs/msm_window_bench_stage1c_pilot_20261023_forward.log`
- reverse：`experiments/raw/logs/msm_window_bench_stage1c_pilot_20261023_reverse.log`
- 第一次 forward 因工具中断只写出 header，原样保留为 `..._20261022_forward.aborted.log`，不计入结果。
- 工具源码：`experiments/prover-smoke/src/bin/msm_window_bench.rs`；二进制由当前 `main` 重建。
