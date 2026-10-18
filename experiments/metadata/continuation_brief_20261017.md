# 续做交接说明（2026-10-17）：任务二（优化验证前提）与任务三（欠的测量项）

> 这份文档是为了在**新会话/新窗口**里继续工作而写的，自包含。新窗口第一步：读本文件，然后按 §4 / §5 执行。
> 本文件不引入新结论，只汇总已完成状态、待办、命令与口径。

---

## 0. 一分钟状态

- 仓库：`D:\Research\zcash-sapling-engineering`
- 分支：`experiment/fallback-ablation-20261016`，本地 `HEAD = bb0f62e`，**已 push**，`origin` 与本地一致。
- 最近 3 个提交：`e74d713`(插桩) → `cadac9f`(原始数据) → `bb0f62e`(报告/元数据/README)，均基于 `b1beca2`。
- **老师的任务（跑 Sapling + 参数细化 + 瓶颈排序）已完成**，交付物 = `docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md`。
- 本文件要接着做的是：**任务二 = 把「能可信验证优化」的前提钉死；任务三 = 补完几项欠账测量。**

---

## 1. 必读口径（踩过的坑，别再踩）

1. **单线程必须绑核。** 本机是混合架构（i7-14700：LP0–15 = P-core，LP16–27 = E-core）。不绑核时同一二进制 prove 在 **3.4–8.9 s** 间波动（**2.6×**），取决于 OS 把进程放哪。
   - 绑核可复现值：**Spend ≈3.70–3.77 s**、**Output ≈0.53 s**。
   - 证据：`experiments/metadata/sapling_smoke_fresh_runs_and_cpu_affinity_20261017.md`。
2. **正式基线本身被核放置污染**：`sapling_spend_prover_runs_release.csv` 的 1 线程 27 批中 9 批（33%）落在 E-core 区间；Output 30 批中 4 批（13%）。**原始文件不要改**，如要重算请新增分层结果。
3. **绑核后 1 线程噪声 ≈±1–2%**（fallback 消融实测）。⇒ **小于 ~2% 的优化在 1 线程测不出来**；多线程余量大但方差也大。**验收阈值必须事先写死。**
4. **git 代理是坏的**：`~/.gitconfig` 里的 `http.proxy/https.proxy = 127.0.0.1:7897` 没在监听。直连可用，所以用：
   ```powershell
   git -c http.proxy= -c https.proxy= push     # 或 fetch / pull
   ```
   （或在网络稳定时 `git config --global --unset http.proxy https.proxy`）
5. **PowerShell 5.1 控制台**显示 UTF-8 中文会乱码，但文件内容没问题；读文件请用 read 工具。

---

## 2. 关键固定信息（复现凭证）

| 项 | 值 |
|---|---|
| 参数目录 | `D:\Research\zcash-params` |
| `sapling-spend.params` | 47,958,396 B，SHA-256 `8E48FFD23ABB3A5FD9C5589204F32D9C31285A04B78096BA40A79B75677EFC13` |
| `sapling-output.params` | 3,592,860 B，SHA-256 `2F0EBBCBB9BB0BCFFE95A397E7EBA89C29EB4DDE6191C339DB88570E3F3FB0E4` |
| 工具链 | rustc/cargo 1.98.1；`--locked --offline` 可用（依赖已缓存） |
| 关键数字 | Spend 98,777 约束 / N=131,072 / input 8；Output 7,827 / N=8,192 / input 6；证明 192 B |
| 基线（未绑核快态） | Spend 3,385.716 ms / Output 514.853 ms（**仅作参考，非可复现值**） |
| fallback 结论 | A vs B 端到端差 +1.1%，p≈0.11 → 计时归属现象，非瓶颈（`..._ablation_conclusion_20261017.md`） |
| 内存峰值主因 | Spend H query 的窗口化指数缓冲 25,970,216 B (24.77 MiB)（`..._prove_memory_ledger_20261017.md`） |

常用命令：

```powershell
cd D:\Research\zcash-sapling-engineering
$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'

# 构建
cargo build --release --locked --offline --manifest-path .\experiments\prover-smoke\Cargo.toml

# 绑核跑 1 线程 Spend（写独立数据标签，不混入正式基线）
powershell -ExecutionPolicy Bypass -File .\scripts\run_spend_combined_profile.ps1 `
  -RepoRoot "D:\Research\zcash-sapling-engineering" -Threads 1 `
  -BranchCounters disabled -InnerStageTiming disabled `
  -RunDataLabel <新标签> -AffinityMask 1 -AllowDirtyWorktree
```

> `-AffinityMask 1` = 逻辑处理器 0（P-core）。`-AllowDirtyWorktree` 因为工作区常有未提交改动；**跑之前先 `git status` 确认没有意外改动。**

---

## 3. 最小可复现的绑核直跑（当不需要 runner 的派生 CSV 时）

```powershell
$env:RAYON_NUM_THREADS = '1'
$exe = ".\experiments\prover-smoke\target\release\spend_prover_smoke.exe"   # Output 用 sapling-output-smoke.exe
$env:SAPLING_SPEND_PARAMS = 'D:\Research\zcash-params\sapling-spend.params'
$env:SAPLING_PROVER_RUNS_CSV = "$PWD\experiments\raw\csv\<你的新文件>.csv"
$p = Start-Process -FilePath $exe -WorkingDirectory $PWD -PassThru `
     -RedirectStandardOutput .\experiments\raw\logs\<名>.log `
     -RedirectStandardError  .\experiments\raw\logs\<名>.err
$p.ProcessorAffinity = [IntPtr]1     # ← 关键：绑核
$p.WaitForExit()
```

---

## 4. 任务二：把「优化验证前提」钉死

### 二-1 冻结一份「绑核正式基线」（before）
- **目的**：给任何优化一个稳定、可复现的 before，取代当前歧义的 3.4/3.7/8.x。
- **做法**：绑核 LP0，Spend 与 Output **各跑 3 批 × 5 次**，写入**新文件**（例：`sapling_spend_prover_runs_pinned_baseline_20261017.csv`）。记录 exe / 参数 / 源码哈希。
- **验收**：批内极差 <±2%；批次间中位差 <±2%。
- **成本**：Spend ≈45 s/批、Output ≈5 s/批 → 合计约 3 分钟。
- **产出**：一份元数据文档（参照 `sapling_smoke_fresh_runs_and_cpu_affinity_20261017.md` 的格式）。

### 二-2 基线口径归一 + 多线程在固定亲和性下复测
- 明确规定「正式基线 = 绑核值」，并在 `README.md` / `weekly_summary.md` / `results/tables/` 说明里标注。
- 多线程 2/4/8/16/20 在**固定亲和性**下重测（建议绑到 P-core 集合，如 mask `0xFFFF`，或 `start /affinity`）→ 产出 `sapling_spend_thread_scaling_pinned_<date>.csv`。
- 这同时是任务三-1 的输入。

### 二-3 选定优化目标 + 写死验收标准（**需要你拍板**）
候选（择一或排序）：
| # | 目标 | 动机 | 备注 |
|---|---|---|---|
| a | MSM 窗口化指数表示（减小 `c` / 按需生成 / 位切片） | 省内存 ~26 MB，可能也省时间 | 改动集中在 `vendor/bellman` |
| b | H query 单次 G1 MSM | 时间大头 | 见报告 §5 |
| c | B-G2 aux（Output 最贵单次调用） | Output 优化 | 见报告 §5 |
| d | `vendor/groth16/src/prover.rs:308` 转换并行化 | 有现成 TODO | 收益未知，先验证 |
**验收模板（必须先写好再改代码）**：
- 端到端 Prove 相对「二-1 绑核基线」变化 ≥ 阈值（绑定核噪声后建议 ≥3% 才算数）；
- 所有证明逐份验证通过（PASS 标记）；
- before/after **同亲和性、同参数、同源码哈希记录**；
- 原始数据 + 代码 diff 归档，不覆盖基线。

---

## 5. 任务三：欠的测量项

### 三-1 8/16/20 线程非单调性（**仍未闭合**）
- 现象：8 线程极差大；20 线程中位不优于 16 线程。
- 假设：P/E 核与 HT 争用，而非算法。
- 做法：在固定亲和性/电源策略下重测 1→20 线程，**按核态分层**报告；对同一线程数多批取样。
- 证据起点：`results/tables/sapling_spend_thread_scaling_summary_20261011.csv`、`README.md` §7。

### 三-2 in-situ 指数转换瞬态
- 现状：`groth16/prover.rs` 第 292/309/316 行的 `Vec<Scalar> → Vec<Exponent>` 只在**受控微测量**（`exponent_conversion_memory.rs`）里测过（Spend aux 7.10 MB / h 9.44 MB）。
- 做法：在真实 prove 流程内用 `SAPLING_MEM_PROBE` 采样该转换的瞬态，验证微测量是否代表 in-situ。

### 三-3 基线按核态重算（不改原始数据）
- 对既有 `experiments/raw/csv/sapling_{spend,output}_prover_runs_release.csv` 按 P/E 态**分层**重算中位数/分位，产出**新**表；修正 README / `results/tables/` 的口径说明。
- 不要再把两个物理运行态混成一个中位数。

### 三-4（可选）窗口化非零密度直接测量
- 现状：「~94% / ~24%」是从实测字节**推断**的，非直接测量。可加插桩直接统计非零 chunk 数。

---

## 6. 完成后要更新的地方

- 主报告 `docs/sapling_proving_parameter_and_bottleneck_breakdown_zh.md`（§12.4 第 5 项、§14、以及「若做了优化」新增一节）；
- `README.md`（§5/§7/§9/§16/§17）与 `weekly_summary.md`；
- 新增元数据文档 + 新增 CSV（**不要覆盖**既有文件）；
- 提交建议仍按「代码 / 数据 / 文档」拆 3 个提交，push 用 §1.4 的无代理方式。

---

*本交接说明只描述状态与计划；其中未标注「已完成」的项均为待办，未做任何结论性声明。*
