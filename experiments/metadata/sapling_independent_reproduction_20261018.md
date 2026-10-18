# Independent reproduction of the certified default configuration (2026-10-18)

按评审建议完成的第一轮**独立复现**（同主机、干净 checkout）。目的：把“本机上有充分证据”
升级为“有明确复现路径的成果”。跨硬件复现仍未做（见 §5）。

## 1. 复现设置（与 `docs/reproduction.md` 的过程一致）

| 项 | 值 |
|---|---|
| Checkout | `git clone -b analysis/msm-branch-stage-join` 到全新目录（无 target/） |
| Commit | `7191b44`（工作区干净） |
| 构建 | `cargo build --release --locked --offline --bins`，全新 target，45.7 s |
| 工具链 | rustc/cargo 1.98.1 |
| 开关状态 | **不设任何 `SAPLING_*` 变量**（即认证后的默认行为：两个开关默认 `1`） |
| 线程/亲和性 | `RAYON_NUM_THREADS=1`，进程绑核 LP0（P-core） |
| 参数 | `D:\Research\zcash-params`（两个 .params 的 SHA-256 与复现文档表格一致） |

## 2. 无参数门禁（参数无关，平台独立）

| 门禁 | 结果 |
|---|---|
| FFT path gate | 12 个 blake2b digest 在「默认（unset）」与「显式 `=0`（旧四步法）」间**逐位一致**；与主仓库早前捕获的 digest 集合也一致 |
| MSM gate | `msm_window_bench` exit 0；`correctness=cross_recoding c=13 ok`；`lazy_equals_materialised` 19 项全过；`MSM_WINDOW_BENCH=DONE` |

## 3. 真实证明复现（Spend，1 线程，LP0）

| 指标 | 复现值 | 认证参考（目标 g B 臂） | 偏差 |
|---|---:|---:|---:|
| prove 峰值中位 | **86,184,600 B** | 86,184,607 B | **−7 B**（分配器粒度 ±8,192 B 内） |
| 验证 | 5/5 verified | — | — |
| 证明大小 | 192 B | 192 B | 一致 |
| prove 时间中位 | ≈3,233 ms | ≈3.2–3.3 s（翻转后同条件） | 一致 |

逐次峰值：86,172,520 / 86,184,600 ×4。这与目标 g 辅 3 的翻转后台账（+7 B）是同一量级的
分配器噪声——**内存与正确性指标在干净 checkout 上逐字节复现**。

## 4. 结论

1. **复现通过。** 干净 checkout + 全新构建 + 默认开关（不设任何变量）下：门禁全过、
   5/5 证明验证通过、峰值中位与认证值差 −7 B。目标 g 的默认值切换在独立 checkout 上成立。
2. **时间数字不可跨机移植**（§3 的 3,233 ms 只对应该主机与亲和性条件），内存与正确性
   数字可以——这与 `docs/reproduction.md` §5 的口径一致。

## 5. 未完成项

- **跨硬件/OS 复现**：本次仍是同一台 Windows 11 / i7-14700 主机。在不同 CPU 或 OS 上
  重复 §2（必做）与 §3（至少内存台账）是对外声明前的下一步。
- 原始数据已归档：`experiments/raw/csv/repro_independent_20261018.csv`、
  `experiments/raw/logs/repro_independent_*`（台账日志、两份 FFT 门禁捕获、MSM 门禁输出）。
