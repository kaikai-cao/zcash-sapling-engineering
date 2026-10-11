# Sapling Spend / Output 同源码 MSM 剖析对照

- 日期：2026-10-11
- 目的：补齐原七天计划第六阶段的 Spend / Output 同口径 MSM 剖析对照。
- Git revision：1e599813e1cf15d50454e2d7517363c8f7ba6266
- 构建：Release
- Rayon 线程：1
- 每组证明轮数：5
- 算法代码修改：无

## 实验批次

| 项目 | Spend | Output |
|---|---|---|
| Batch ID | 1791685812121 | 1791685930195 |
| 原始 CSV | experiments/raw/csv/sapling_spend_prover_runs_release.csv | experiments/raw/csv/sapling_output_prover_runs_release.csv |
| 日志 | experiments/raw/logs/sapling_spend_msm_profile_same_source_20261011_102916.log | experiments/raw/logs/sapling_output_msm_profile_same_source_20261011_103205.log |

## 逐轮数据

MSM 累计耗时为该轮 8 条 BELLMAN_MSM_PROFILE 记录的 elapsed_ms 之和；比例为该累计耗时除以该轮 prove_ms。

### Spend

| Run | Prove (ms) | MSM 累计耗时 (ms) | MSM / Prove |
|---:|---:|---:|---:|
| 1 | 6886.682 | 5932.749 | 86.15% |
| 2 | 6865.663 | 6002.708 | 87.43% |
| 3 | 6755.116 | 5880.978 | 87.06% |
| 4 | 6858.210 | 5984.795 | 87.26% |
| 5 | 6782.222 | 5888.293 | 86.82% |

### Output

| Run | Prove (ms) | MSM 累计耗时 (ms) | MSM / Prove |
|---:|---:|---:|---:|
| 1 | 553.271 | 477.688 | 86.34% |
| 2 | 507.648 | 473.712 | 93.32% |
| 3 | 885.491 | 850.428 | 96.04% |
| 4 | 995.708 | 935.886 | 93.99% |
| 5 | 1051.759 | 980.647 | 93.24% |

## 汇总

| 指标 | Spend | Output |
|---|---:|---:|
| Prove 中位数 (ms) | 6858.210 | 885.491 |
| MSM 累计耗时中位数 (ms) | 5932.749 | 850.428 |
| 单轮 MSM / Prove 比例中位数 | 87.06% | 93.32% |
| Verify 成功 | 5/5 | 5/5 |
| Proof Size (bytes) | 192 | 192 |

## 初步观察与限制

1. 两组实验中，MSM 调用耗时之和均占 Prove 时间的大部分，支持将 MSM 视为重要的性能分析对象；这不是端到端加速幅度的预测。
2. Output 的 Prove 时间在五轮之间有明显波动，现有数据不足以确定原因，应保留所有逐轮记录。
3. 两组均为单线程 Release 剖析实验，不能与未启用同等剖析的正式基准时间直接混为一组。
4. 本记录描述当前实验批次，不替代正式性能汇总；不据此推断算法优化收益。

## 源码与原始数据校验

- MSM 源码：vendor/bellman/src/multiexp.rs
- MSM 源码 SHA-256：730AF1249B78BD422DC62453A3604CB01236C94B2A2331E87E484CBDCE876266
- Spend CSV SHA-256（UTF-8，行尾统一为 LF 后计算）：4C446462D9CFECA9DCC68180F56618B01BE89C0B08CE95A1BB1F9A8E1CD01C47
- Output CSV SHA-256（UTF-8，行尾统一为 LF 后计算）：B0D356EBE0DC1E47C7392E2747E7CB72C1E378478E61B1B975F69228530B1B37
- Spend 日志 SHA-256：6221674922C3BA6E487FB17EB0A61CC7CB872A862DBF5B89CB654ACB32E5D1C7
- Output 日志 SHA-256：5323EB228668E18D944D8347EA8707A13649E42B8A0E92BB58C215A730BA5E0B
