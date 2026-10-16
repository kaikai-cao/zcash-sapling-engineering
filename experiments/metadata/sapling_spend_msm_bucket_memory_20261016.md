# Sapling Spend MSM 桶数组内存核算

**日期：** 2026-10-16

## 1. 数据来源

- MSM 调用数量：
  `experiments/raw/csv/sapling_spend_msm_call_profile_1791802391142.csv`
- 群元素对象大小：
  `experiments/raw/csv/sapling_runtime_type_sizes_20261016.csv`
- 实现：`vendor/bellman/src/multiexp.rs`

本报告是根据已记录的调用参数和 Rust 类型大小得到的
静态核算结果，不是新增的性能测量。

## 2. 计算方法

窗口规则：指数数量小于 32 时，`c = 3`；否则，
`c = ceil(ln(exponent_count))`。

每个 chunk 的桶数为 `2^c - 1`。

单个桶数组数据区大小为：
`bucket_count × size_of(projective group element)`。

BLS12-381 标量位数按 255 计算，
chunk 数为 `ceil(255 / c)`。

## 3. 逐调用核算

| 调用 | 群 | 指数数 | 窗口 | 桶数/chunk | chunk 数 | 单个桶数组 | 累计桶数组数据区 |
|---|---|---:|---:|---:|---:|---:|---:|
| H_query_G1 | G1 | 131,071 | 12 | 4,095 | 22 | 589,680 B | 12,972,960 B |
| L_query_G1 | G1 | 98,638 | 12 | 4,095 | 22 | 589,680 B | 12,972,960 B |
| A_input_G1 | G1 | 8 | 3 | 7 | 85 | 1,008 B | 85,680 B |
| A_aux_G1 | G1 | 98,638 | 12 | 4,095 | 22 | 589,680 B | 12,972,960 B |
| B_G1_input | G1 | 8 | 3 | 7 | 85 | 1,008 B | 85,680 B |
| B_G1_aux | G1 | 98,638 | 12 | 4,095 | 22 | 589,680 B | 12,972,960 B |
| B_G2_input | G2 | 8 | 3 | 7 | 85 | 2,016 B | 171,360 B |
| B_G2_aux | G2 | 98,638 | 12 | 4,095 | 22 | 1,179,360 B | 25,945,920 B |

## 4. 如何解释这些数字

- **单个桶数组数据区**：一个 chunk 中桶元素的数据区大小，
  不包含 Vec 头部、分配器元数据或其他临时对象。
- **累计桶数组数据区**：所有 chunk 的桶数组大小之和，
  不是同一时刻的峰值内存。
- **20 线程并发上界**：假设最多 20 个 chunk 桶数组同时活动时，
  对单个 MSM 调用计算的理论上界；不是实测峰值。
- 多个 MSM 调用可能相互重叠；单个调用的上界不能直接相加，
  并当作整个证明过程的峰值内存。
- 要获得实际峰值，后续仍需在执行时采集分配数量、桶数组
  生命周期和并发情况，或使用系统级内存测量。

## 5. 输出文件

- CSV：`results/tables/sapling_spend_msm_bucket_memory_20261016.csv`
- Markdown：`experiments/metadata/sapling_spend_msm_bucket_memory_20261016.md`
