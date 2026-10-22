# 预注册（Stage 1b）：大 MSM 自适应窗口 + 尾部窗口切分（2026-10-22）

> 本文件在 Stage 1b 的正式 campaign 之前冻结。它**取代** Stage 1a 预注册（`sapling_msm_adaptive_preregistration_20261022.md`）中的策略与臂，但不修改 Stage 1a 已提交文件，也不修改 Stage 0 的任何结论或阈值。
>
> Stage 1a 的预注册在实现后先做了 6 个**探索性 smoke 批次**（不计入正式 campaign）。Smoke 暴露了两个设计问题：全局自适应会把 Output 的 `n≈8191` 窗口从 `c=10` 推到 `c=11`，Output 反而变慢约 9%；而对所有窗口切分（`split=2/4`）会成倍增加 bucket 数组和 reduce 开销，Spend 反而变慢。Stage 1b 因此冻结两个修正：**只在 `n ≥ 16384` 的大 MSM 上启用自适应**，以及**只切分尾部窗口**。这是基于 pilot 的设计修正，不是看到正式结果后改阈值；pilot 的原始文件保留，正式 campaign 不使用 pilot 数据。
>
> Stage 1b 的验收项和阈值仍在正式测量前冻结；结果文档必须记录 pilot、设计修正、失败与偏差。

---

## 1. 可检验问题

Stage 0 证明 8 个 P 核上窗口尾部是真实损失（H1 支持），但 `c=11` 的收益在 Stage 0 是跨 campaign 的点估计，不能直接当默认值。Stage 1a 的 pilot 进一步说明：

- `c=11` 对 Spend（`n=131071`、`n=98638`）仍可能是最快的；
- 对 Output（`n=8191`、`n=7821`），`c=11` 比默认 `c=10` 慢，说明“按 `W mod P` 选窗口”不能无条件推广到小 MSM；
- 对全部窗口切分会让每一段都分配一套 bucket 数组，`c=13,split=2` 的 bucket reduce 从约 105 ms 升到约 209 ms（H-query stage），收益被吃掉。

Stage 1b 回答：

1. **Q1**：在 8 P 核、`0x5555` 下，只对 `n ≥ 16384` 的 MSM 启用 Stage 1 尾部感知窗口（`c=11`），能否让 Spend prove 相对当前默认策略降低至少 5%？
2. **Q2**：只切分 `W mod P` 个尾部窗口（`c=13,s=2` 或 `c=10,s=4`，使尾部任务正好填满 8 个 worker），能否比“全窗口切分”更有效地解释尾部并降低 prove 时间？
3. **Q3**：大 MSM 门控策略在 Output 和“1 spend + 2 outputs”真实交易上是否不回归？

---

## 2. 冻结环境

| 项 | 冻结值 |
|---|---|
| 主机 | Intel Core i7-14700，LP0–15 = 8 P 核 × HT，LP16–27 = 12 E 核 |
| OS | Windows 11 Insider build 26220 |
| 工具链 | `rustc 1.98.1`，host `x86_64-pc-windows-gnu` |
| 参数目录 | `D:\Research\zcash-params` |
| Spend 参数 SHA-256 | `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13` |
| Output 参数 SHA-256 | `2f0ebbcbb9bb0bcffe95a397e7eba89c29eb4dde6191c339db88570e3f3fb0e4` |
| 线程/亲和性 | `RAYON_NUM_THREADS=8`，`0x5555` |
| 计时 | 暖态；每批丢弃 run 1；batch 中位的中位；cluster bootstrap |
| 批次间隔 | 5 s |
| 每批证明数 | Spend/Output 5 次；交易 6 次 |
| 交易形状 | V5，1 spend + 2 outputs，`tx_bytes=2377` |

所有批次串行、独立进程；每批读回 `ProcessorAffinity`，不等于 `0x5555` 作废。二进制、参数、预注册 SHA 和 git HEAD 逐批写入 manifest。

---

## 3. 冻结策略

### 3.1 大 MSM 门控的自适应窗口

在 Stage 1a 的公式上增加一个固定门控：

```text
if exponents.len() < 16384:
    使用现有 best_signed_window（即默认路径）
else if SAPLING_MSM_WINDOW_C 设置了:
    使用显式 c
else if SAPLING_MSM_ADAPTIVE_WINDOW=1:
    c = argmin_{c ∈ 3..=14, cap 满足} ceil(W(c)/P) * (n + 2*2^(c-1))
else:
    best_signed_window
```

其中 `P = rayon::current_num_threads()`，`W(c)=255//c+1`，`cap = P*2^(c-1)*sizeof(G) ≤ 16 MiB`，并列取较小 `c`。门控常量 **16384** 在代码中固定，不作为环境变量；它把 Output 的 `n=8191/7821` 留在默认 `c=10`，避免 Stage 1a pilot 中看到的 Output 回归。

### 3.2 仅尾部窗口切分

新增 `SAPLING_MSM_WINDOW_SPLIT_MODE`，取值 `all`（默认，兼容 Stage 1a）或 `tail`。`SAPLING_MSM_WINDOW_SPLIT=s` 仍为段数（1..8，默认 1）。

对 `W` 个窗口、`P` 个 worker：

```text
r = W mod P
if s <= 1 or r == 0:
    tasks = W 个完整窗口任务
else if mode == all:
    tasks = W * s 个任务（每个窗口切 s 段）
else if mode == tail:
    tasks = (W - r) 个完整窗口任务 + r*s 个尾部段任务
```

尾部段任务只覆盖窗口 `W-r .. W-1`，每段按 §3.3 的连续指数范围划分。因此：

- `c=13`：`W=20,r=4,s=2` → `16+8=24` 个任务；
- `c=10`：`W=26,r=2,s=4` → `24+8=32` 个任务。

尾部切分的群运算结果与未切分完全一致：每个窗口的 `s` 段结果先求和，再乘 `2^(c·chunk)`；完整窗口照旧。`chunk_count` 仍记窗口数 `W`，`task_count` 记实际任务数。

### 3.3 连续分段规则

```text
base = n / s
rem  = n % s
start(k) = k*base + min(k, rem)
len(k)   = base + (1 if k < rem else 0)
```

对 sparse density，段的起点按“之前 true 槽位数”跳过 base，而不是按原始下标；false 槽位不消费 base。`s=1` 必须保持 Stage 0 的等价路径。

### 3.4 覆盖优先级

```text
SAPLING_MSM_WINDOW_C              // 显式 c，优先级最高
SAPLING_MSM_ADAPTIVE_WINDOW=1     // 且 n >= 16384
否则                              // best_signed_window
SAPLING_MSM_WINDOW_SPLIT          // 1..8
SAPLING_MSM_WINDOW_SPLIT_MODE     // all|tail，默认 all
```

未设置新变量时，行为与 Stage 0 默认一致；Stage 1b 不改变默认值。

---

## 4. 实验臂与顺序

| 臂 | Spend | Output | 交易 | 环境 |
|---|---|---|---|---|
| `C0` 默认 | ✓ | ✓ | ✓ | 不设 adaptive/override/split |
| `C1` 门控自适应 | ✓ | ✓ | ✓ | `SAPLING_MSM_ADAPTIVE_WINDOW=1` |
| `C2` c13 尾切 2 | ✓ | — | — | `WINDOW_C=13`，`SPLIT=2`，`SPLIT_MODE=tail` |
| `C3` c10 尾切 4 | ✓ | — | — | `WINDOW_C=10`，`SPLIT=4`，`SPLIT_MODE=tail` |
| `C4` c11 正对照 | ✓ | ✓ | ✓ | `WINDOW_C=11`，`SPLIT=1` |

`C2`/`C3` 只用于 Spend 机制检验；Output/交易回归只比较 `C1`（以及 `C4` 正对照）对 `C0`。

顺序与 Stage 1a 相同：

```text
Spend（20 批，每臂 4 批）:
C0,C1,C2,C3,C4,C4,C3,C2,C1,C0
C0,C1,C2,C3,C4,C4,C3,C2,C1,C0

Output（12 批，每臂 4 批）:
C0,C1,C4,C4,C1,C0
C0,C1,C4,C4,C1,C0

交易（12 批，每臂 4 批）:
C0,C1,C4,C4,C1,C0
C0,C1,C4,C4,C1,C0
```

总计 **44 批**。每批独立进程，批间空闲 5 s。

---

## 5. 验收项（冻结）

| 编号 | 内容 |
|---|---|
| A1 | Spend 每批 5 行，5/5 `verified=true`；40 MSM call、40 inner-stage、5 G16 stage |
| A2 | Output 每批 5 行，5/5 `verified=true` |
| A3 | 交易每批 6 行，6/6 `verified=true`，V5，1 spend + 2 outputs，`tx_bytes=2377` |
| A4 | 每批 `ProcessorAffinity=0x5555`，`rayon_threads=8` |
| A5 | 每批单一 git HEAD；三个二进制和两个参数的 SHA-256 一致 |
| A6 | 预注册 SHA-256 与 manifest/结果文档一致；tag 唯一 |
| A7 | 策略观测：`C1` 的 Spend H 为 `c=11,W=24,split=1`；`C1` 的 Output H 为默认 `c=10,W=26,split=1`；`C2` 为 `c=13,W=20,split=2,task_count=24`；`C3` 为 `c=10,W=26,split=4,task_count=32`；`C4` 为 `c=11,W=24,split=1` |
| A8 | manifest 44 行、44 个唯一 batch ID、全部 `exit_code=0`；无覆盖 |
| A9 | 失败/中止批次保留并改名，不计入 44 批；结果文档记录 |
| A10 | 分析器可独立重跑，阈值与 §6 一致 |

A1–A10 全 PASS 才进入策略结论。

---

## 6. 估计量与阈值

与 Stage 1a 相同：batch 为 cluster，10,000 次 bootstrap，90% CI；先 warm 中位，再 batch 中位。

```text
P1: R_C1/C0 = median(C1.prove_ms) / median(C0.prove_ms)       // Spend
    支持: R ≤ 0.95 且 CI 上界 < 1.00
P2: R_C2/C0                                                    // c13 尾切
P3: R_C3/C0                                                    // c10 尾切
    各自同 P1 阈值；次要证据
P4: R_C1/C4 = median(C1.prove_ms) / median(C4.prove_ms)
    非劣效: 点估计 ≤1.02 且 CI 上界 ≤1.05
P5: R_out = median(C1.prove_ms) / median(C0.prove_ms)
    不回归: 点估计 ≤1.03 且 CI 上界 ≤1.05
P6: R_tx = median(C1.build_ms) / median(C0.build_ms)
    不回归: 点估计 ≤1.03 且 CI 上界 ≤1.05
P7: C1 Spend 中位是否 ≤657.81 ms（Stage 0 历史点）       // 仅描述，不作 PASS/FAIL
```

判定组合：

| P1 | P2/P3 | P5/P6 | 结论 |
|---|---|---|---|
| 支持 | 任意 | 不回归 | 门控自适应有证据；尾部切分按 P2/P3 单独报告 |
| 支持 | 任意 | 回归/不确定 | Spend 有证据但不能跨负载；不切默认 |
| 不支持 | 任一支持 | 不回归 | 只支持尾部切分 |
| 不支持 | 都不支持 | 任意 | 本 placement 下无策略证据；不切默认 |
| 任意 | 任意 | A1–A10 失败 | 数据不足/执行失败 |

Stage 1b **不**直接改默认值；默认切换需要独立预注册。

---

## 7. 代码边界

- `vendor/bellman/src/multiexp.rs`：实现 §3.1 门控、§3.2 tail/all 任务生成、profile 的 `split_mode/task_count`；
- `scripts/run_spend_combined_profile.ps1`：支持 split mode、门控自适应期望窗口、task_count 校验；
- 新增 `scripts/run_msm_adaptive_campaign.ps1` 与 `scripts/analyze_msm_adaptive_experiment.py`；
- 不修改 Stage 0 原始数据/阈值；不改变默认值。

---

## 8. 提交与偏差

先提交本预注册，再提交代码/脚本，再提交原始数据/manifest，最后提交结果文档与表图；通过分支 + PR。pilot 的 6 个 smoke 批次不进入正式 44 批；其原始文件保留，结果文档在“pilot 与设计修正”节列出 batch ID 与原因。
