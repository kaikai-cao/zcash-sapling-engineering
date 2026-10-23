# Sapling Spend 电路合成子阶段侦察（2026-10-23）

> **状态：探索性侦察（exploratory reconnaissance），不是正式战役。** 本轮没有预注册、没有冻结阈值、没有默认值变更，也没有实现新的合成算法。目的只是回答一个筛选问题：在固定电路、固定 proving key、单证明延迟口径下，`circuit_synthesis` 内部是否还存在足以单独达到 **5% body** 的 prover 侧优化空间。若没有，就关闭合成线，不另立正式 Stage 6。

## 1. 背景

Stage 4 关闭了 QAP/FFT 调度/分区线，Stage 5 前置侦察又关闭了 FFT 算术线；两者都没有打开正式战役。Stage 4 的记录明确指出，`synthesis` 是另一条独立线，但当时没有测它的内部可并行化比例。8 线程下 `circuit_synthesis` 约 **103–120 ms**，而 body 约 **642 ms**；从比例上看，它足以影响 5% 判定，因此需要先确认时间到底花在哪里。

固定参数下的约束是硬的：不能改变电路、约束顺序或 proving key。任何“重排约束/变量”的做法都会使现有参数失效，不属于本轮可接受范围。因此本轮只检查 **prover 侧** 的合成簿记工作，尤其是 `ProvingAssignment::enforce` 中对 A/B/C 线性组合的求值 `eval`。

## 2. 方法

在 `vendor/groth16/src/prover.rs` 增加默认关闭的探针：

- 环境变量：`SAPLING_SYNTH_STAGE_PROBE=1`。
- 计数：`enforce` 调用数、aux/input `alloc` 调用数、A/B/C 线性组合项数。
- 计时：每次 `enforce` 内分别对 A、B、C 的 `eval` 调用计时，累计到原子计数器。
- 输出：每个证明一行 `G16_SYNTH_PROBE`，包含上述计数和毫秒数。
- 探针不改变任何算术；关闭时只多一次缓存的 `OnceLock` 读取。探针源码提交为 `b133e3c`。

测量使用现有 `scripts/run_spend_combined_profile.ps1`：8 线程、亲和性 `0x5555`、每批 5 个 Spend 证明、`SAPLING_PROFILE=1`。同一二进制分别跑：

- **探针开**：`SAPLING_SYNTH_STAGE_PROBE=1`，batch `1792728844494`。
- **探针关**：`SAPLING_SYNTH_STAGE_PROBE=0`，batch `1792728878993`。

两批都是 5/5 证明验证通过。批内丢弃 run 1 的规则不适用于本侦察；下表直接使用 5 个证明的批内中位数，因为这里看的是同一批内的阶段占比，而不是跨批性能判定。

## 3. 结果

| 臂 | batch | `circuit_synthesis` 中位 | body 中位 | `eval_total` 中位 | `eval_total / body` |
|---|---:|---:|---:|---:|---:|
| 探针开 | 1792728844494 | **119.437 ms** | **641.695 ms** | **29.744 ms** | **4.63%** |
| 探针关 | 1792728878993 | **103.396 ms** | **643.080 ms** | — | — |

探针开批的计数在 5 个证明中完全一致：

- `enforce_calls = 98,785`（其中 98,777 个电路约束 + 8 个 input 一致性约束）。
- `alloc_calls = 98,638`；`input_alloc_calls = 8`。
- 线性组合项数：A **312,174**、B **99,918**、C **212,492**。
- `eval` 中位：A **14.384 ms**、B **5.091 ms**、C **10.211 ms**；合计中位 **29.744 ms**。

探针开销可以从两批的合成时间差估计：**119.437 − 103.396 = +16.041 ms**，约为关闭探针时合成时间的 **15.5%**；两批 body 只差 **−1.385 ms（−0.22%）**，在跨批噪声范围内。也就是说，`eval_total` 里的 29.744 ms 本身已经包含每次 `Instant::now()` 的计时开销，**真实 eval 时间只会更低**。用两批做近似分解：

- 开探针：119.437 ms ≈ 89.693 ms 非 eval + 29.744 ms 计时区间；
- 关探针：103.396 ms ≈ 89.744 ms 非 eval + 约 13.7 ms 真实 eval。

两边的非 eval 部分几乎相同（约 **89.7 ms**），说明探针主要扰动的是 `eval` 的计时区间，而不是电路 gadget 的标量计算。

### 3.1 上界判定

5% body 的门槛约为：

- 开探针批：`0.05 × 641.695 = 32.085 ms`；
- 关探针批：`0.05 × 643.080 = 32.154 ms`。

即使把 `eval` **全部消掉**，按偏高的 29.744 ms 计算，也只相当于 **4.63% body**，低于 5%。真实 eval 约 13.7 ms，对应约 **2.1% body**。因此：

> **在固定电路和固定 proving key 下，仅优化 `eval` 不可能单独达到 5% body。**

合成时间中剩下的约 **89.7 ms** 包含电路 gadget 的标量运算、线性组合构造、`alloc` 闭包和约束生成；它不是单一成分。为了判断“是否存在另一个可动的 prover 侧大块”，又用扩展探针跑了一个归因批（batch `1792729158774`），把 `enforce` 的 LC 构造、`alloc` 总时间和 `enforce` 总时间分开计时。该批的计时器更多，绝对时间不能与上面的 clean 对直接比较，只用于同批内归因。

### 3.2 归因扩展：没有单一成分达到 5%

归因批：`circuit_synthesis` 中位 **129.980 ms**，body 中位 **643.390 ms**，5/5 证明验证通过。各计时区间中位如下（均包含该区间内的计时器开销，因此是偏高的上界）：

| 分量 | 中位 | 占 synthesis | 占 body |
|---|---:|---:|---:|
| `alloc` 总计（含 `f()` witness 计算） | **54.266 ms** | 41.7% | 8.43% |
| `enforce` 总计 | **57.897 ms** | 44.5% | 9.00% |
| — 其中 LC 构造 | **12.947 ms** | 10.0% | 2.01% |
| — 其中 A/B/C `eval` | **29.827 ms** | 22.9% | 4.64% |
| — 其中 `other`（push/计数器/计时器） | **15.724 ms** | 12.1% | 2.44% |
| 残差（synthesis − alloc − enforce） | **17.817 ms** | 13.7% | 2.77% |

解释：

- **`eval` 仍是最大的单一可动 prover 侧分量**，但只有 **4.64% body**，低于 5%。
- **LC 构造** 12.947 ms（2.01% body）、**`enforce` 的 `other`** 15.724 ms（2.44% body）都更小；`other` 还包含必须保留的 A/B/C push 和计时器开销。
- **`alloc` 54.266 ms 不是纯 prover 簿记**：它包含每个 `alloc` 闭包 `f()` 内的电路 witness 标量计算，以及 aux 向量和两个 density bitvec 的 push。要把它大幅降低，必须改 gadget 的 witness 计算或约束/变量顺序；后者会使 proving key 失效，前者只有在保持约束矩阵和变量顺序不变时才可能安全，属于电路库重写，不在本轮范围；仅优化 push 只能动其中很小一部分。
- 残差 17.817 ms 是 `alloc`/`enforce` 之外的电路代码和探针开销，同样不能作为一个独立候选。

因此：**没有单一 prover 侧成分达到 5% body。** 理论上可以把“并行 eval + 更快的 LC 构造 + push 优化”组合起来，但那是一个多部分重写，本轮没有实现或验证，且 `other`/残差中包含不可去除的工作和计时器开销；它不构成本轮可推荐的 scoping GO。若所有者要试，必须另立预注册并先证明组合收益，而不能用本轮数字外推。

## 4. 解释与限制

- **只测了 Spend、8 线程、`0x5555`。** 没有跑 1 线程、`0xFFFF` 敏感性臂、Output 电路或不同宿主；结论只针对该配置。
- **每臂只有 1 批 × 5 个证明。** 这是探索性筛选，不是正式战役；跨批漂移可达数个百分点，但本轮判定用的是“即使全部消除也不到 5%”的上界，不依赖精确点估计。
- **探针有可见开销。** clean 对中每次 `enforce` 三次计时使合成时间增加约 16 ms；归因批又加了 `alloc`/`enforce`/LC 计时，绝对时间进一步升高。因此所有计时分量都是上界，真实值更低；结论对开销方向是保守的。
- **归因批的 `alloc` 不是纯簿记。** 54.266 ms 包含 `alloc` 闭包 `f()` 内的电路 witness 计算；不能把它整体当作可优化的 prover 开销。只有 aux 向量和 density bitvec 的 push 是 prover 侧的小部分。
- **没有实现并行 eval 原型。** clean 对显示 eval 全部消除也只有 4.63% body；归因批显示最大的单一可动分量仍是 eval（4.64%），LC 构造 2.01%、`other` 2.44%。单独任何一项都不到 5%，而多部分组合没有实现或验证，因此没有继续做原型。
- **没有测组合。** 合成侧优化与 Stage 4 pipeline、Stage 5 FFT 算术的组合没有测。若所有者要试，必须另立新的预注册/例外；不能把本轮数字写成组合结果。
- **原始数据保留。** 在探针源码提交和格式化前还跑过两批 pilot（batch `1792728644973` 开、`1792728729019` 关），结论同向；它们保留在 raw 目录，但不作为本轮引用口径。clean 对（`1792728844494`/`1792728878993`）用于 eval-only 上界，归因批（`1792729158774`）用于成分归因。

## 5. 决策

**NO_GO：关闭合成线；不启动正式 Stage 6；不改变任何默认值。**

理由不是“合成不重要”，而是：clean 对证明仅消除 `eval` 最多只有 **4.63% body**；归因批进一步显示最大的单一可动 prover 侧分量仍是 `eval`（**4.64% body**），LC 构造只有 **2.01%**、`enforce` 的 `other` 只有 **2.44%**，都不到 5%。`alloc` 的 54.266 ms 主要包含电路 witness 计算，不能整体当作可优化项；残差也是电路代码和计时开销。多部分组合（并行 eval + 更快 LC + push 优化）理论上可以想象，但本轮没有实现或验证，不能据此启动正式战役；若所有者要试，必须先另立预注册并证明组合收益。

保留 `SAPLING_SYNTH_STAGE_PROBE=1` 作为默认关闭的诊断工具；它不改变生产路径。没有修改 `vendor/` 的算法、没有修改 Stage 1–4 参数、没有生成或广播交易。

## 6. 复现与证据

- clean 对探针源码：`vendor/groth16/src/prover.rs`，提交 `b133e3cca519f6e03ed50938bd806d290524b8a9`；源码 SHA-256 `7f7d3305f529616e4c8e911bf03fd2f7aa4818a5dc2d4055bbadd3f95a2cfae5`；二进制 SHA-256 `29d0f364d7dd0c93a948b4cac2afa4d1f3e57ddd7ac052143be0a5560c202b53`。
- 归因批探针源码：提交 `a93594e9ae553a7646ad99a90da05072a638e1aa`；源码 SHA-256 `1663d7d80e4a4a419d669874917e93370c787134611607be505cb114f53d4321`；二进制 SHA-256 `666cca7496a4b9e5d55e7a73a9d794b8c47ce30e54e5be8f68dc472c765622c6`。
- 参数：`D:\Research\zcash-params\sapling-spend.params`，SHA-256 `8e48ffd23abb3a5fd9c5589204f32d9c31285a04b78096ba40a79b75677efc13`。
- clean 探针开：`experiments/raw/csv/sapling_spend_stage_profile_1792728844494.csv`、`experiments/raw/logs/sapling_spend_combined_profile_20261023_121334_581.stderr.log`、`experiments/metadata/sapling_spend_combined_profile_1792728844494.md`。
- clean 探针关：`experiments/raw/csv/sapling_spend_stage_profile_1792728878993.csv`、`experiments/raw/logs/sapling_spend_combined_profile_20261023_121413_335.stderr.log`、`experiments/metadata/sapling_spend_combined_profile_1792728878993.md`。
- 归因批：`experiments/raw/csv/sapling_spend_stage_profile_1792729158774.csv`、`experiments/raw/logs/sapling_spend_combined_profile_20261023_121848_856.stderr.log`、`experiments/metadata/sapling_spend_combined_profile_1792729158774.md`。
- 复现命令（PowerShell，在仓库根目录）：

```powershell
$env:SAPLING_SYNTH_STAGE_PROBE='1'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_spend_combined_profile.ps1 `
  -Threads 8 -AffinityMask 0x5555 -RunDataLabel synth_probe_clean -AllowDirtyWorktree
```

关闭探针时把第一行改为 `$env:SAPLING_SYNTH_STAGE_PROBE='0'`，并使用不同的 `-RunDataLabel`。
