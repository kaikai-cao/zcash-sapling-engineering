# 新跑 Smoke 与 CPU 核放置可复现性记录（2026-10-17）

**目的：** 记录第 3 项：对当前工作区实际执行 `cargo check`、重跑 Output/Spend smoke 产出新的原始日志；并量化本轮发现的「单线程测量受 CPU 核放置影响」这一问题。

**范围：** 不改动任何既有基线文件；新数据写入独立文件；绑核运行。

---

## 0. 摘要（TL;DR）

1. **`cargo check` 通过**（dev profile，7.09 s，依赖已缓存）。
2. **Output smoke 与 Spend smoke 各重跑 1 批（5 次证明），5/5 全部验证通过**，绑核 LP0、无插桩：
   - Output：`prove_ms` 中位 **529.5 ms**（528.3–578.0），`verify_ms` ≈2.1–2.8，proof 192 B。
   - Spend：`prove_ms` 中位 **3724.0 ms**（3697.1–3760.0），`verify_ms` ≈2.8–3.2，proof 192 B。
3. **单线程测量在未被约束时是双峰分布**，同一二进制同一参数：
   - 落在 **P-core**：prove ≈**3.4–4.0 s**，参数加载 ≈25–27 s；
   - 落在 **E-core**：prove ≈**5.3–8.9 s**，参数加载 ≈54–57 s（最高 **2.6×**）。
   - 绑核后稳定在 ≈**3.70 s（±2%）**。⇒ **绑核是单线程测量可复现的前提。**
4. **正式基线本身也被该混淆污染**（原始文件未改动，仅统计）：Spend 单线程 27 批中 **9 批（33%）** 落在 E-core 区间；Output 单线程 30 批中 **4 批（13%）** 落在 E-core 区间。

---

## 1. cargo check

```powershell
cargo check --locked --offline --manifest-path .\experiments\prover-smoke\Cargo.toml
```

```
    Checking bellman v0.15.0 (D:\Research\zcash-sapling-engineering\vendor\bellman)
    Checking groth16 v0.2.0 (D:\Research\zcash-sapling-engineering\vendor\groth16)
    Checking sapling-crypto v0.9.0 (https://github.com/zcash/sapling-crypto?rev=88a7946b...)
    Checking sapling-output-smoke v0.1.0 (D:\Research\zcash-sapling-engineering\experiments\prover-smoke)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 7.09s
```

日志：`experiments/raw/logs/cargo_check_prover_smoke_20261017.log`（1658 B，SHA-256 `900E0FB59E2FE5CC7FBD737AF52F0667C67248FA3A1EA5B3F1E7C34907838F3E`）。

## 2. 新跑的 smoke（绑核 LP0、无插桩、RAYON_NUM_THREADS=1）

环境：`ZCASH_PARAMS_DIR=D:\Research\zcash-params`；未设置 `SAPLING_PROFILE` / `SAPLING_MSM_STAGE_TIMING` / `SAPLING_MSM_BRANCH_COUNTS` / `SAPLING_MEM_PROBE`；进程亲和性 = `1`（LP0）。

### 2.1 Output smoke（`sapling-output-smoke.exe`）

| run | params_read_validate_ms | prove_ms | verify_ms | proof_bytes | verified |
|---:|---:|---:|---:|---:|:--:|
| 1 | 1861.875 | 577.954 | 2.165 | 192 | true |
| 2 | 1861.875 | 529.457 | 2.805 | 192 | true |
| 3 | 1861.875 | 528.291 | 2.144 | 192 | true |
| 4 | 1861.875 | 529.986 | 2.154 | 192 | true |
| 5 | 1861.875 | 536.468 | 2.190 | 192 | true |

- batch_id `1792227291964`；stdout `experiments/raw/logs/sapling_output_smoke_pinned_lp0_20261017_165449.log`；以 `OUTPUT_PROOF_EXPERIMENT=PASS` 结束。
- CSV：`experiments/raw/csv/sapling_output_prover_runs_pinned_20261017.csv`。

### 2.2 Spend smoke（`spend_prover_smoke.exe`）

| run | params_read_validate_ms | prove_ms | verify_ms | proof_bytes | verified |
|---:|---:|---:|---:|---:|:--:|
| 1 | 25505.545 | 3759.981 | 2.834 | 192 | true |
| 2 | 25505.545 | 3724.040 | 2.917 | 192 | true |
| 3 | 25505.545 | 3750.302 | 2.853 | 192 | true |
| 4 | 25505.545 | 3706.419 | 3.165 | 192 | true |
| 5 | 25505.545 | 3697.077 | 3.045 | 192 | true |

- batch_id `1792227320599`；stdout `experiments/raw/logs/sapling_spend_smoke_pinned_lp0_20261017_165449.log`；以 `SPEND_PROOF_EXPERIMENT=PASS` 结束。
- CSV：`experiments/raw/csv/sapling_spend_prover_runs_pinned_20261017.csv`。

> 这两个 CSV 是新文件，**未写入正式基线** `*_runs_release.csv`。为此给 Output smoke 补了与 Spend smoke 一致的 `SAPLING_PROVER_RUNS_CSV` 覆盖（见 §5），默认行为不变。

## 3. 核放置可复现性研究（Spend smoke，无插桩，RAYON_NUM_THREADS=1）

同一 exe、同一参数、每行 5 次证明：

| 亲和性 mask | 逻辑处理器 | 5 次 prove (ms) | 中位 | params_load (ms) | 墙钟 (s) |
|---|---|---|---:|---:|---:|
| `0x1` | LP0（P-core） | 4018.3 / 3800.6 / 3768.7 / 3771.3 / 3773.4 | 3771.3 | 25513.6 | 45.2 |
| `0x1`（新 smoke） | LP0（P-core） | 3760.0 / 3724.0 / 3750.3 / 3706.4 / 3697.1 | 3724.0 | 25505.5 | 44.4 |
| `0x3` | LP0+LP1（同物理核 HT 对） | 3806.9 / 3690.5 / 3692.1 / 3719.6 / 3642.5 | 3692.1 | — | 45.6 |
| `0xFFFF` | LP0–LP15（仅 P-core） | 4022.9 / 3981.2 / 3898.0 / 3979.7 / 4108.2 | 3981.2 | — | 47.0 |
| `0x100000` | LP20（E-core） | 8171.4 / 8093.3 / 8129.2 / 8389.8 / 7985.9 | 8129.2 | 54444.0 | 95.5 |
| 无（未约束） | 由 OS 调度 | 8879.8 / 8669.5 / 8649.4 / 8752.6 / 8719.9 | 8719.9 | 57299.2 | 101.3 |

**读法：**
- 只要把进程限制在 P-core（LP0 或 LP0+LP1），prove 稳定在 **3.65–3.81 s（±2%）**，参数加载也稳定在 ≈25.5 s。
- 落到 E-core 时 prove ≈**8.1–8.9 s**，参数加载 ≈**54–57 s**（点验证同样变慢）。
- 未约束时不保证落到哪一类核：本次实测直接落到 E-core（8.72 s 中位）。
- 结论：**未约束的单线程测量不是单一分布，而是 {P-core 快态, E-core 慢态} 的双峰（最高 2.6×）**；绑核是把单线程测量变成可复现的前提。

> 说明：未约束的「最快」历史值（≈3.4 s）比绑核值（≈3.7 s）还快，推测与「主线程 + 1 个 rayon worker 两个可运行线程可分散到两个物理 P-core」有关；一旦限制到单个物理核（或由 OS 同核放置），就回落到 ≈3.7 s。无论如何，**绑核值是可复现的参考值**。

相关日志：`experiments/raw/logs/affinity_probe_lp0_20261017_163939.*`、`affinity_probe_lp20_20261017_164043.*`、`affinity_probe_mask65535_20261017_165708.*`、`affinity_probe_mask3_20261017_165755.*`、`affinity_probe_unbound_20261017_165856.*`。探针 CSV：`experiments/raw/csv/sapling_spend_prover_runs_affinity_probe.csv`。

## 4. 正式基线的双峰证据（原始文件未改动，仅统计 1 线程批次）

**Spend `sapling_spend_prover_runs_release.csv`，1 线程共 27 批：**

| 簇 | 批次数 | prove 中位范围 (ms) | 相对最快 |
|---|---:|---|---|
| 快（P-core） | 18 | 3385.7 – 3535.7 | 1.00 – 1.04 |
| 慢（E-core） | 9 | 5357.5 – 8020.5 | 1.58 – 2.37 |

（慢态批次：`1791687498328 / 1791615270097 / 1791687710196 / 1791685812121 / 1791619229133 / 1791632685376 / 1791619135309 / 1791619041368 / 1791634015130`）

**Output `sapling_output_prover_runs_release.csv`，1 线程共 30 批：**

| 簇 | 批次数 | prove 中位范围 (ms) | 相对最快 |
|---|---:|---|---|
| 快（P-core） | 25 | 502.5 – 538.4 | 1.00 – 1.07 |
| 中间 | 1 | 612.4 | 1.22 |
| 慢（E-core） | 4 | 885.5 – 1048.2 | 1.76 – 2.09 |

（慢态批次：`1791685930195 / 1791617780346 / 1791617791207 / 1791618486266`）

⇒ 历史报告里「单线程 prove ≈3.4 s（Spend）/≈0.51 s（Output）」与「同一配置有时 ≈8 s / ≈1.0 s」并存，原因即核放置，而非代码或参数差异。**这也意味着既有的单线程中位数是把两个物理上不同的运行态混在了一起。**

## 5. 本轮对代码的唯一改动（为保持数据分离）

`experiments/prover-smoke/src/main.rs`（Output smoke）：把 CSV 路径从硬编码改为支持 `SAPLING_PROVER_RUNS_CSV` 覆盖，**默认值仍指向原基线文件**，行为不变；这样绑核/新来源的批次可以写独立文件，与 `spend_prover_smoke.rs` 的既有做法一致。

```rust
let raw_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../experiments/raw/csv");
create_dir_all(&raw_dir)?;
let csv_path = std::env::var_os("SAPLING_PROVER_RUNS_CSV")
    .map(PathBuf::from)
    .unwrap_or_else(|| raw_dir.join("sapling_output_prover_runs_release.csv"));
```

## 6. 复现凭证（SHA-256 / 版本）

| 项 | 字节 | SHA-256 |
|---|---:|---|
| `experiments/prover-smoke/src/main.rs`（已改） | 6,637 | `5E2C3D098837066F8DE9CCDC08E5C6AB3458641F0E2B90FAE7B434BE0ED4FF7D` |
| `experiments/prover-smoke/target/release/sapling-output-smoke.exe` | 4,151,688 | `5E01C707C331E14E4948635B46D383DC8B3D6805CF376DEC1180F9A3958B2046` |
| `experiments/prover-smoke/target/release/spend_prover_smoke.exe` | 4,261,201 | `DF0DE411BDF537DC8E3A853CE43EB41C0DAB99134204EB9CA511294155580694` |
| `experiments/raw/csv/sapling_output_prover_runs_pinned_20261017.csv` | 488 | `0E2C22A27C78469AC9F38AF78CB8BCC048614B6F639A707CE7EB2525627BACDD` |
| `experiments/raw/csv/sapling_spend_prover_runs_pinned_20261017.csv` | 498 | `8A01EBC6B8230D2C24468006C929168C8E00493491AF6A6CDCACF818E916505F` |
| `experiments/raw/csv/sapling_spend_prover_runs_affinity_probe.csv` | 1,958 | `9664188AC84658B659EDC685CC5CDB9161B3E4E346BF830E101031038E9625CF` |
| `experiments/raw/logs/cargo_check_prover_smoke_20261017.log` | 1,658 | `900E0FB59E2FE5CC7FBD737AF52F0667C67248FA3A1EA5B3F1E7C34907838F3E` |
| `experiments/raw/csv/sapling_output_prover_runs_release.csv`（未改动） | 15,767 | `37EA2186054B223D129E36BF8B6322E7382A598BEA1829AF71F5520F517DE963` |
| `experiments/raw/csv/sapling_spend_prover_runs_release.csv`（未改动） | 12,341 | `9C662F2252188122469CC892F08582864133D1D4B8F946137554131E1C133B72` |

工具链：rustc/cargo 1.98.1；git 分支 `experiment/fallback-ablation-20261016`，HEAD `b1beca2`（工作区脏）。
CPU：Intel Core i7-14700（8 P-core ×HT + 12 E-core；本机 LP0–15 = P-core，LP16–27 = E-core）。

## 7. 复现命令

```powershell
cd D:\Research\zcash-sapling-engineering
cargo check   --locked --offline --manifest-path .\experiments\prover-smoke\Cargo.toml
cargo build --release --locked --offline --manifest-path .\experiments\prover-smoke\Cargo.toml

$env:ZCASH_PARAMS_DIR = 'D:\Research\zcash-params'
$env:RAYON_NUM_THREADS = '1'

# Output（绑 LP0）
$env:SAPLING_PROVER_RUNS_CSV = "$PWD\experiments\raw\csv\sapling_output_prover_runs_pinned_20261017.csv"
$p = Start-Process -FilePath .\experiments\prover-smoke\target\release\sapling-output-smoke.exe `
     -WorkingDirectory $PWD -PassThru `
     -RedirectStandardOutput .\experiments\raw\logs\out.log -RedirectStandardError .\experiments\raw\logs\out.err
$p.ProcessorAffinity = [IntPtr]1; $p.WaitForExit()

# Spend（绑 LP0）
$env:SAPLING_SPEND_PARAMS = 'D:\Research\zcash-params\sapling-spend.params'
$env:SAPLING_PROVER_RUNS_CSV = "$PWD\experiments\raw\csv\sapling_spend_prover_runs_pinned_20261017.csv"
$p = Start-Process -FilePath .\experiments\prover-smoke\target\release\spend_prover_smoke.exe `
     -WorkingDirectory $PWD -PassThru `
     -RedirectStandardOutput .\experiments\raw\logs\spend.log -RedirectStandardError .\experiments\raw\logs\spend.err
$p.ProcessorAffinity = [IntPtr]1; $p.WaitForExit()
```

## 8. 限制与建议

1. 结论限于本机（i7-14700）与该工作负载；其他混合架构 CPU 的核编号与 P/E 划分可能不同，需先探测。
2. 建议：**今后所有单线程测量都记录并固定 `ProcessorAffinity`**，并在报告中把「绑核可复现值」与「未约束分布（双峰）」分开陈述。
3. 既有正式基线中落入 E-core 的批次**不应删除**（它们是真实的 OS 调度样本）；但在计算「单线程基线」时应**按核态分层**，或只采用绑核批次。
4. 本轮未改动任何既有原始 CSV；PowerShell 5.1 控制台对 UTF-8 中文可能显示为乱码，但不影响文件内容。
