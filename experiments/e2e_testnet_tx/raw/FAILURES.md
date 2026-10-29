# 失败与异常记录（事后重建）

> ⚠️ **本文件是事后重建，不是运行时日志。**
> `AUDIT_trail.md` §3 缺口 #2 指出：所有 bench 输出只到终端，`rounds.csv` 只记成功轮，
> 失败轮次没有任何结构化记录。本文件按会话记录与报告文字回填，逐条标注**证据强度**。
>
> 证据强度分级：
> - **A = 原始产物**：有落盘文件可直接复核（`rounds.csv`、错误码、空目录）
> - **B = 报告文字**：已写进报告，但无独立证据文件
> - **C = 仅会话记录**：只在当时的终端输出里出现过，项目内无任何痕迹
>
> 从本文件之后，bench 脚本已内置 `tee_stdio()` 自动落盘 `run.log`（commit `71cc965`），
> 同类失败将直接获得 A 级证据。

---

## 一、工具链缺陷（阻塞性）

### F1 · PCZT 拒绝创建：ZIP 212 未生效

| 项 | 内容 |
|---|---|
| 现象 | `pczt_create` 报 `PCZTs require that ZIP 212 is enforced for outputs` |
| 触发 | regtest 链高 < 32257 时，任何 `pczt_create` 调用 |
| 根因 | **不是缺陷**。ZIP 212 的 grace period = `Canopy激活高(1) + 32256 = 32257`，此前不允许输出 |
| 误判过程 | 起初当成 beta.3 的 bug，查了 nuparams、账户生日、RPC 签名都没找到问题 |
| 处置 | `zip212_mine.sh` 空块挖到 32270（留 13 块余量），之后一次通过 |
| 证据 | **A** — 挖块后链高与 `pczt_create` 成功记录可对账 |
| 教训 | 报错文本说"未生效"时，先算激活高度 + grace period，别先怀疑工具 |

### F2 · PCZT Sapling 路径不可用（**决定性**，直接导致 D2 偏离）

| 项 | 内容 |
|---|---|
| 现象 1 | `pczt_sign` 返回成功但 `sapling_signed=0`（耗时 12.0 ms，明显没做签名） |
| 现象 2 | `pczt_prove` 报 `Prover(MissingProofGenerationKey)` |
| 复现次数 | **5 轮连续失败**，调整 sign/prove 顺序后仍失败 |
| 根因 | Sapling 是双密钥（`ask` 与 `nsk` 独立），PGK = `(ak, nsk)` 必须由持有 `expsk` 的 **Updater** 写入；而 `pczt_sign` 只传 `ask`，`pczt_create` 走 `create_pczt_from_proposal::<…, Infallible, …>` 完全不碰私钥，`pczt::sapling::Spend` 的公开接口只有 `cv()/nullifier()/rk()/witness()/proprietary()`，**无 PGK 访问器** |
| 排除项 | 控制实验 `sapling_spend_ctl.py` 用 `z_sendmany` 3.01 s 成功（txid `fb27193b…`），证明密钥本身完好 → 是 PCZT 工具链缺口，不是密钥问题 |
| 处置 | 放弃 PCZT-Sapling，改走 `z_sendmany`（见 `DEVIATIONS.md` D2）；PCZT 四阶段改在 Orchard/Ironwood 上测 |
| 证据 | **B** — 报告 §1.2 有完整论述；`pczt_probe.py` / `pczt_rca.sh` 能重跑，但当时的输出未落盘 |
| 残留风险 | 若上游后续修复，需重新判定本结论的时效性。已记录版本：`zallet-zaino` SHA256 `e602e4a3…` |

### F3 · 透明地址 gap limit

| 项 | 内容 |
|---|---|
| 现象 | PCZT benchmark 第 1 轮失败：`reached the transparent gap limit at index 16` |
| 根因 | 每轮循环内重新派生收款地址，20 个未使用的透明地址超过 gap limit |
| 处置 | 地址在循环外派生一次，且只请求 sapling receiver（`["sapling"]`） |
| 证据 | **C** — 仅终端输出 |

### F4 · `generate` 假失败（**最容易误判的一个**）

| 项 | 内容 |
|---|---|
| 现象 | `generate` 返回错误 `failed to send mined block to gossip task: no available capacity` |
| 实情 | **区块确实产生了**，链高正常推进 |
| 复现次数 | 8 次（Orchard 路线注资阶段） |
| 根因 | regtest 下 gossip 任务队列满，矿出区块送不进 gossip，但本地链状态已提交 |
| 处置 | **判据改为链高增量**，完全不看 `generate` 返回值 |
| 证据 | **A** — 链高增量可复算（每次报错后 +1 块） |
| 教训 | 凡"返回错误但副作用已发生"的接口，判据必须建立在状态上而不是返回值上 |

### F5 · 跨池注资被拒

| 项 | 内容 |
|---|---|
| 现象 1 | ironwood 地址转账报 `Invalid from address` |
| 现象 2 | 跨池 dry-run 被 `FullPrivacy` 策略拒绝 |
| 根因 | `["orchard"]` 派生地址的余额落在 ironwood 池；跨池交易会揭示金额，`FullPrivacy` 不允许 |
| 处置 | 改 `AllowRevealedAmounts` 策略；`z_sendmany` 必须传五参形态且 fee 显式为 `null` |
| 证据 | **C** — 仅终端输出 |

### F6 · `z_listtransactions` 的 memo 解码 bug

| 项 | 内容 |
|---|---|
| 现象 | 报 `Data DB is corrupted: Invalid memo data: InvalidUtf8(...)` |
| 根因 | 任意 memo（首字节 `0xf6` 表示任意数据）被当作 UTF-8 严格解码 |
| 影响 | **不影响** `z_sendmany` / `z_viewtransaction`，只是列交易接口不可用 |
| 处置 | 改用 `z_viewtransaction` 取 spend/output 明细 |
| 证据 | **C** — 这是 `AUDIT_trail.md` §4 唯一标为"结论存在但证据不在项目内"的条目 |

---

## 二、分析过程中的错误（已纠正）

### F7 · 冷启动归因错误

| 项 | 内容 |
|---|---|
| 早期结论 | 某轮 prove 2857.7 ms 被判为"冷启动代价"，据此推断冷启动开销巨大 |
| 复查发现 | 该轮 `extract` 放大 21.8×、`mine` 放大 3.9×，属**资源竞争离群点**，不是冷启动 |
| 正确结论 | 真正的进程冷启动仅 **+142 ms**（1537.1 vs 1395.2，1.10×），见 `raw/pczt_cold_v1` |
| 证据 | **A** — 两批 `rounds.csv` 可对比 |
| 教训 | 单点异常必须先看**同轮内其它阶段**是否同时变慢；只变慢一个阶段才是该阶段的问题 |

### F8 · M1 模型设定错误（负截距）

| 项 | 内容 |
|---|---|
| 早期结论 | `pipeline = 609.7×proofs − 689.8`，R²=0.9969，看似很好 |
| 问题 | **截距为负**，物理上不可能；当时 O 只取 2~3，output 的贡献被截距吸收成假象 |
| 触发修正 | `--outputs 8` 判别实验（`1s+9o`）实测 1826.5 ms，M1 预测 4898 ms，偏差 −3072 ms |
| 最终 | M1 R² 崩到 0.8724、截距 −863.9 → 否证"按证明个数计费"；改双变量 M3 |
| 证据 | **A** — `FIT.md` 有三模型逐点残差 |
| 教训 | 高 R² 不等于模型正确；检查截距符号与外推行为 |

### F9 · `wait_sync` 用了陈旧 tip

| 项 | 内容 |
|---|---|
| 现象 | 同步判据立刻返回"已同步"，但实际落后 |
| 根因 | zallet 重启后 `node_tip` 可能陈旧 1001 块 |
| 处置 | 目标改为 `max(node_tip, zebra.blocks)` |
| 证据 | **A** — `rounds.csv` 的前置/后置同步秒数 |

---

## 三、基础设施故障（已修复，留作警示）

### F10 · 快照预检误报"归档里没有 data/zebra-state/"

| 项 | 内容 |
|---|---|
| 现象 | `--check` 反复报缺目录，但归档实际完好 |
| 根因 | `set -o pipefail` + `echo "$BIG" \| grep -q`：输出 >64 KB 时 `grep` 提前退出触发 SIGPIPE(141)，整条管道被判失败 |
| 处置 | 预检列表先落盘再 `grep`，不用管道直接判 |
| 证据 | **A** — 后续 `--check` 校验 1058 条目通过 |
| 教训 | `pipefail` 下任何 `\| head` / `\| grep -q` 都可能把成功判成失败 |

### F11 · regtest nuparams 全 0 导致 panic

| 项 | 内容 |
|---|---|
| 现象 | `InvalidHeightZero` panic，节点起不来 |
| 根因 | 试图把 nuparams 全设 0 来"关掉"升级 |
| 处置 | 回滚官方值（Canopy=1、NU5=2、NU6.x=2）；`wsl/regtest/` 是合法版，`wsl/conf/` 是全 0 实验版 |
| 证据 | **A** — 两份配置都在仓库里，可直接对比 |

### F12 · 中断产生的空运行目录

| 项 | 内容 |
|---|---|
| 现象 | `raw/pczt_pool_v2/run_20261029_150604/` 为空 |
| 原因 | 启动后立即中断，目录已建但未写文件 |
| 处置 | 保留不删，在 `MANIFEST.md` 中标记为不完整运行 |
| 证据 | **A** — 目录本身即是证据 |

---

## 四、当前未闭合的失败证据缺口

| 缺口 | 影响 | 能否补 |
|---|---|---|
| F2 的原始 RPC 响应（5 次失败的完整报文） | 只能靠报告文字，无法让别人独立复核"beta.3 有缺口" | 可：链在跑时用 `pczt_probe.py` 重跑（会重现同样的失败） |
| F3/F5/F6 的终端输出 | 仅会话记录 | 部分可：F6 可对任一含任意 memo 的交易重跑 |
| 所有轮次的 `run.log` | 24 轮已完成的实验无法补 | ❌ 不可补，只能由 `tee_stdio()` 保证以后不再发生 |
