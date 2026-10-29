# 历史遗留：2026-10-28 的早期采样

> **本目录不包含任何有效的性能测量结果。** 保留只为留痕，请勿用于分析或引用。

## 为什么单列一个目录

这是 10-28 晚在 docker regtest 栈（`z3-testnet-zebra-1` 容器）上跑 harness 时留下的
内存采样，早于 10-29 的 WSL2 离线 regtest 正式测量。它位于 `experiments/raw/` 而非
`experiments/e2e_testnet_tx/raw/`，是当时还没确定产物目录结构时的临时落点。

## 逐文件说明

| 文件 | 规模 | 可用性 | 说明 |
|---|---|---|---|
| `sync_memory.csv` | 564 行 / 23 KB | ❌ **不可用** | 同步期内存采样。`mem_used_bytes` 列 **564/564 全为空** |
| `run_20261028_211557/memory_timeseries.csv` | 14 行 | ⚠️ 仅片断 | 进程级（`pid:10129` 等）采样，间隔 0.25 s，覆盖仅约 3.5 s |
| `run_20261028_212048/memory_timeseries.csv` | 14 行 | ⚠️ 仅片断 | 同上，另一个 pid 组合 |
| `mem_sample.log` | 0 字节 | — | 空文件，当时未写入任何内容 |

## `sync_memory.csv` 为什么全空

`mem_used_bytes` 由 `e2e_tx_bench.py` 的 `_to_bytes()` 解析 `docker stats` 的输出
（形如 `123.4MiB / 7.6GiB`）。当时函数按后缀长度顺序匹配单位，`B` 先于 `MiB`/`GiB`
命中，导致所有读数解析失败并落成空字符串。

该缺陷已由 **`04a8423` fix(mem_sample): 修正 _to_bytes 单位后缀匹配顺序导致内存读数全空**
修复。这两个 `run_*/memory_timeseries.csv` 是修复前后的对照样本，所以有非空值。

保留这个文件的意义仅在于：它是该 bug 的现场证据，能证明修复前确实是全空，
而不是"当时忘了采"。

## 正式数据在哪里

有效测量全部在 `experiments/e2e_testnet_tx/raw/`：

- `sapling_e2e_v1/REPORT_sapling.md` —— Sapling 端到端成本模型（29 轮）
- `pczt_pool_v2/REPORT_v2.md` —— PCZT 四阶段（N=15）
- `MANIFEST.sha256` —— 66 条产物的哈希清单
- `AUDIT_trail.md` —— 留痕审计

## 与正式批次的口径差异（不要在两者间做对比）

| 项 | 本目录（10-28） | 正式批次（10-29） |
|---|---|---|
| 运行方式 | docker compose（`z3-testnet-zebra-1`） | WSL2 原生进程，离线 regtest |
| 采集对象 | 容器 cgroup 内存 | 进程 RSS（`/proc/<pid>/status`） |
| 时间粒度 | 0.25 s | 0.25 s |
| 覆盖时长 | 3.5 s 片断 | 整轮交易全流程 |
| 二进制 | 未记录 | 已记 SHA256（见 `ENV_binaries.txt`） |

环境与采集对象都不同，两套数字**不可混用**。
