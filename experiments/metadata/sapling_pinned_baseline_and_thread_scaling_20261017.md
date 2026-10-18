# 绑核冻结基线、核态参照与线程扩展（2026-10-17）

> 覆盖任务：**二-1（冻结绑核正式基线）**、**二-2（基线口径归一 + 多线程固定亲和性复测）**、**三-1（8/16/20 线程非单调性）**。
> 本轮只做测量，不改任何算法。所有原始数据新增文件，不覆盖既有文件。

---

## 0. 一句话结论

1. 在**绑核**条件下可以得到稳定可复现的 1 线程基线：**Spend 3685.6 ms（暖态）**、**Output 558.5 ms（暖态）**，暖态批内极差 **1.3%**（Spend）。
2. 不绑核是**不可用**的：同一个二进制、同一个线程数，Spend 在 **3.69–9.11 s** 之间漂移（**2.47×**），Output 更极端——不绑核时**同一个进程内部**都会发生地核迁移（批内极差 **70%**）。
3. 线程扩展在**固定亲和性**下复现了非单调性，并把它**从"未解释"变成"有界"**：曲线在 **8 线程**就已饱和（并行效率 58.8%），16→20 线程**反而变慢 2.9%**，判为**过订阅开销 + 已无多余并行度**，而不是调度缺陷。

---

## 1. 协议（Protocol）

| 项 | 设定 |
|---|---|
| runner | `scripts/run_pinned_prover_campaign.ps1`（本轮新增） |
| 进程亲和性 | `ProcessorAffinity` 在 `Start-Process` 之后、prove 之前设置 |
| 单线程基线 | `RAYON_NUM_THREADS=1`，掩码 **0x1**（逻辑处理器 0，P-core） |
| 每个配置 | **3 批**；每批 = 1 次进程调用 = 内含 5 次 prove（smoke 二进制内部 `REPEATS=5`） |
| 计时 | `prove_ms` 只包住 `create_proof`；参数读取/验证、vk 预处理、见证构造都在计时区间外 |
| 诊断开关 | `SAPLING_PROFILE=0`（关闭 stderr 诊断，`prove_ms` 不受其影响） |
| 校验 | 每批必须 5/5 `verified=true`，否则 runner 抛错、不发布汇总 |
| 机器 | i7-14700（LP0–15 = 8 P-core ×HT，LP16–27 = 12 E-core），31.7 GiB，Windows 11 |

**"暖态"口径（本文件统一使用）**：丢弃**第 1 批**（冷页缓存）与**每批的 run 1**（进程内预热），对剩余值取中位数。
同时给出未分层的 pooled 中位数，两者都列，避免口径歧义。

### 1.1 调用方式（重要坑）

PowerShell `-File` 会把 `-Threads 1,2,4` 当成**一个字符串**（实测被转成 `12481620`，导致 `RAYON_NUM_THREADS` 被设成天文数字而挂起）。
多值参数必须用 `&` 直接调用：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force   # 仅影响当前会话
$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'

& .\scripts\run_pinned_prover_campaign.ps1 `
  -RepoRoot "D:\Research\zcash-sapling-engineering" -Prover spend `
  -Threads 1,2,4,8,16,20 -AffinityMasks 0xFFFF -Batches 2 `
  -Label thread_scaling_pinned_20261017 -AllowDirtyWorktree
```

单值参数（`-Threads 1 -AffinityMasks 1`）用 `-File` 也可以。

---

## 2. 二-1 冻结的绑核正式基线（before）

原始数据：`experiments/raw/csv/sapling_{spend,output}_prover_runs_pinned_baseline_20261017.csv`（各 15 行）
汇总：`..._summary.csv`；派生：`results/tables/sapling_pinned_campaigns_20261017.csv`

| 电路 | 掩码 | 线程 | 批 × 次 | 批中位数序列 (ms) | pooled 中位 (ms) | 冷批 B1 中位 | **暖态中位 (ms)** | 暖态极差 |
|---|---|---:|---:|---|---:|---:|---:|---:|
| Spend | 0x1 | 1 | 3×5 | 3898.4 / 3711.5 / 3686.9 | 3711.504 | 3898.372 | **3685.623** | 3667.0–3715.2 (1.29%) |
| Output | 0x1 | 1 | 3×5 | 554.3 / 577.5 / 558.7 | 558.727 | 554.308 | **558.519** | 5.90% |

**读法**

- **冷启动偏差是真实存在的、可量化的**：Spend 第 1 批中位 3898.4 ms，比暖态高 **+5.8%**；第 1 批内部前两次甚至到 4416/4474 ms（+21%）。所以"预热后再测"不是洁癖，是**必须**的。
- Output 的暖态极差 5.9% 比 Spend 大，来源是第 2 批里一次 586.3 ms 的离群点；n=15 时单点即可拉高极差。**因此验收阈值不能用极差，要用中位数 + 预声明阈值**（见 `sapling_optimization_validation_protocol_20261017.md`）。
- Output 的冷批中位（554.3）反而**低于**暖态（558.5），说明 Output 的"冷"效应主要体现在**批内 run 1**（554.3 是含 run 1 的批中位；该批 run1=598.0 明显慢），与 Spend 不同。两者预热结构不一致，不能互相套用。

**冻结基线取值（供后续 before/after 使用）**

```
Spend  1t @ LP0 : 3685.6 ms  (暖态中位; pooled 3711.5)
Output 1t @ LP0 : 558.5 ms   (暖态中位; pooled 558.7)
```

---

## 3. 二-2 核态参照：为什么必须绑核，以及该绑到哪里

同一二进制、同 1 线程，只改亲和性掩码（Spend 2 批 = 10 次；Output 2 批 = 10 次）：

| 掩码 | 含义 | Spend pooled 中位 (ms) | Spend 暖态中位 | Output pooled 中位 (ms) | Output 暖态中位 |
|---|---|---:|---:|---:|---:|
| `0x1` | 单个 P-core（LP0） | 3711.504 | 3685.623 | 558.727 | 558.519 |
| `0xFFFF` | 全部 16 个 P 逻辑核（1 线程池） | 3842.248 | — | — | — |
| `0xFFF0000` | 仅 12 个 E-core | 7803.571 | 8028.304 | 1206.423 | 1253.858 |
| `0x0` | 不设亲和性（OS 自由调度） | 8808.741 | 9113.138 | 1130.878 | 1248.420 |

**结论**

1. **P-core vs E-core ≈ 2.1×（Spend）/ 2.16×（Output）**，这是纯硬件差异，与代码无关。
2. **不绑核比"只用 E-core"还慢**（8808.7 > 7803.6）。原因不是核更差，而是**进程会在核之间迁移**，冷热/频率状态被反复打断。
3. **不绑核的 Output 在同一个进程内部就会跨核迁移**：批内前两次 560.7/512.5 ms，后三次 1117.0/1366.9/1227.4 ms（批内极差 **77.5%**，暖态极差 70.2%）。这说明不绑核的数据**连"每批一个核态"都不成立**，无法事后分层修复。
4. **连"绑到全部 P-core"都不等价于"绑到单个 P-core"**：0xFFFF 的 1 线程是 3842.2 ms，比 0x1 的 3711.5 ms 高 **+3.5%**。所以单线程基线要**绑到单个逻辑核**才最紧。

**口径归一建议**：正式 1 线程基线一律记为「掩码 0x1 + `RAYON_NUM_THREADS=1` + 暖态中位」；历史未绑核数据（`*_prover_runs_release.csv`）经分层处理后只能作为**参考区间**，不作为可复现基线（见 `sapling_baseline_core_regime_restatement_20261017.md`）。

---

## 4. 三-1 绑核线程扩展与非单调性

掩码固定 `0xFFFF`（16 个 P 逻辑核），`RAYON_NUM_THREADS ∈ {1,2,4,8,16,20}`，每配置 2 批 = 10 次。
原始数据：`experiments/raw/csv/sapling_spend_prover_runs_thread_scaling_pinned_20261017.csv`（60 行）
派生：`results/tables/sapling_spend_thread_scaling_pinned_20261017.csv`

| 线程 | 中位 (ms) | min | max | 批内极差 | 相对 1 线程加速 | 并行效率 | 相对上一档 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3842.248 | 3773.446 | 3957.682 | 4.80% | 1.000× | 100.0% | — |
| 2 | 1890.879 | 1874.456 | 1980.032 | 5.58% | 2.032× | 101.6% | 2.03× |
| 4 | 1064.321 | 1045.913 | 1108.738 | 5.90% | 3.610× | 90.3% | 1.78× |
| 8 | 816.862 | 782.754 | 924.661 | **17.37%** | 4.704× | 58.8% | 1.30× |
| 16 | 785.935 | 744.284 | 918.860 | **22.21%** | 4.889× | 30.6% | 1.039× |
| 20 | 808.368 | 744.040 | 835.337 | 11.29% | 4.753× | 23.8% | **0.972×（变慢）** |

**非单调性怎么解释（此前列为"未闭合"，现在有界）**

1. **1→2→4 近似线性**（2.03×、1.78×），说明并行确实有效。
2. **4→8 只有 1.30×，8→16 只有 1.039×**：从 8 线程起，增加线程几乎不再换来时间。**16 线程用 2× 的线程只买到 3.9% 的时间**，说明瓶颈已经不是线程数（而是内存带宽/桶合并的串行尾段）。
3. **16→20 变慢 2.9%**：20 线程 > 16 个 P 逻辑核，多出的线程与已有线程争抢同一批物理核（HT 竞争），且 `bellman` 的 `WORKER_SPAWN_MAX_COUNT = 4×current_num_threads()` 也会随线程数放大任务队列，产生额外调度/内存压力，却**没有额外并行度可用**。
4. **方差随线程数先升后降**：8/16 线程的批内极差 17%/22%（最差），20 线程反而降到 11%。这与"16 线程处在饱和拐点上、调度抖动被放大"一致。

> **判定**：8/16/20 的非单调性 = **饱和 + 过订阅**，不是算法/调度缺陷。可执行的改进方向是"把线程数钉在 4–8"和"降低串行尾段"，而不是继续加线程。**注意**：这只在绑核下成立；不绑核时线程>1 的数据被核放置污染，不能用于下结论。

---

## 5. 复现凭证

| 项 | 值 |
|---|---|
| exe SHA-256（spend） | `df0de411bdf537dc8e3a853ce43eb41c0dab99134204eb9ca511294155580694` |
| exe SHA-256（output） | `5e01c707c331e14e4948635b46d383dc8b3d6805cf376dec1180f9a3958b2046` |
| spend.params SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| output.params SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| git HEAD（测量时） | `5c675f4427848925eecb26823e823b65246f9905`（+ 未提交的新脚本/新插桩，故 `dirty_worktree=true`） |
| 工具链 | rustc/cargo 1.98.1，`--locked --offline` |

命令（每个配置一行；`-Label` 决定输出文件名）：

```powershell
# 二-1 冻结基线
& .\scripts\run_pinned_prover_campaign.ps1 -Prover spend  -Threads 1 -AffinityMasks 1        -Batches 3 -Label pinned_baseline_20261017
& .\scripts\run_pinned_prover_campaign.ps1 -Prover output -Threads 1 -AffinityMasks 1        -Batches 3 -Label pinned_baseline_20261017
# 三-1 绑核线程扩展
& .\scripts\run_pinned_prover_campaign.ps1 -Prover spend  -Threads 1,2,4,8,16,20 -AffinityMasks 0xFFFF -Batches 2 -Label thread_scaling_pinned_20261017
# 核态参照
& .\scripts\run_pinned_prover_campaign.ps1 -Prover spend  -Threads 1 -AffinityMasks 0xFFF0000 -Batches 2 -Label affinity_ecore_1t_20261017
& .\scripts\run_pinned_prover_campaign.ps1 -Prover spend  -Threads 1 -AffinityMasks 0          -Batches 2 -Label unbound_1t_20261017
& .\scripts\run_pinned_prover_campaign.ps1 -Prover output -Threads 1 -AffinityMasks 0xFFF0000 -Batches 2 -Label affinity_ecore_1t_20261017
& .\scripts\run_pinned_prover_campaign.ps1 -Prover output -Threads 1 -AffinityMasks 0          -Batches 2 -Label unbound_1t_20261017
```

---

## 6. 限制

1. 每配置 n=10–15，**极差对单点敏感**；结论基于中位数与相邻档位比较，不基于极差。
2. `0xFFFF` 的 1 线程只有 2 批（该值仅用于说明"绑核范围"也会带来约 3.5% 差异），未做暖态口径。
3. 线程扩展只测到 20 线程；`RAYON_NUM_THREADS>20` 未测（该机器只有 28 个逻辑核，且 HT 竞争已明显）。
4. 本文件不含任何算法/调度改动，只是基线与其口径。
5. 机器为单台个人机，未做电源策略/温度控制；跨天的绝对值会有 ±1–2% 级别的系统漂移，**before/after 必须同日、同协议成对测量**。
