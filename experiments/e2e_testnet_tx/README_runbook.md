# 端到端 Testnet 真实 Sapling 转账 —— 环境搭建与功能验证 Runbook

> ## ⚠️ 状态：本 Runbook 描述的原方案已被偏离，**不要照此执行**
>
> 本文档写于 2026-10-26，计划的是 **Testnet + docker z3 栈 + PCZT 四阶段**。
> 实际执行（2026-10-29）改成了 **WSL2 离线 regtest + `z_sendmany`**，因为 PCZT 的
> Sapling 分支在 zallet beta.3 上不可用（见 [`raw/FAILURES.md`](raw/FAILURES.md) F2）。
>
> 本文中以下表述**已不成立**，阅读时以 [`DEVIATIONS.md`](DEVIATIONS.md) 为准：
> - §0「Regtest 资金到账后缺少受支持的完整花费路径」→ regtest 实际完全可用
> - §7「Regtest 不作为完整花费环境：本实验全程用 Testnet」→ 实际全程用 regtest
> - §0 版本钉定中的 Zallet `v0.1.0-beta.1` → 实际用 `v0.1.0-beta.3`
>
> **保留本文的价值**：它记录了原计划的方法论（功能门禁、分阶段计时、一次性成本单列），
> 这些原则实际都执行了，见 `DEVIATIONS.md` §2。
>

> 配套：
> - 范围界定 [`../metadata/sapling_real_input_tx_proving_scoping_note_20261026.md`](../metadata/sapling_real_input_tx_proving_scoping_note_20261026.md)
> - ~~预注册（冻结测量方案与门槛）~~ → **该文件从未创建**；影响评估见 [](DEVIATIONS.md) §0
> - 测量脚手架：`e2e_tx_bench.py`（分阶段计时 + 内存）、`mem_sample.py`（一次性同步内存）
>
> 本 Runbook 把「在 Testnet 上跑通一笔真实 Sapling 转账并完成功能验证门禁」的步骤写清楚，
> 并说明如何接入测量脚手架。它**不报告任何测量结果**——测量由 `e2e_tx_bench.py` 在验证跑通后执行。

---

## 0. 技术路线（已冻结，来自范围文档 §2）

- 节点：**Zebra**；钱包：**Zallet**（Beta）。对应栈为 Zcash 基金会官方的 **`z3`**（Docker Compose 统一部署 Zebra + Zallet + 可选 Zaino）。
- 分阶段 RPC：**`pczt_create` / `pczt_prove` / `pczt_sign` / `pczt_extract`**（PCZT = Partially Created Zcash Transaction）。
- **功能验证优先在 Testnet**；不把 Regtest 当作完整花费环境（Zallet Beta 公开 issue：Regtest 资金到账后缺少受支持的完整花费路径）。
- 对照基线：既有本地 `Builder::build` 链路（合成 Merkle 状态，2026-10-22）保留为比较基准。

### 版本钉定（来自 z3 `main` 的 `docker-compose.yml`，复现所需）

| 组件 | 镜像 | 说明 |
|---|---|---|
| Zebra | `zfnd/zebra:6.2.3` | 支持 NU6.3 的当前 Testnet 线；Sapling 转账在此线完全可用 |
| Zallet | `zodlinc/zallet:v0.1.0-beta.1`（digest 锁定） | Beta；RPC 接口随版本变化，**每次都先 `rpc.discover` 核对** |
| Zaino | `zingodevops/zainod:0.6.0-no-tls` | 仅 `--profile indexer` 需要；Zallet 内嵌 Zaino 库，**本实验不必起独立 indexer** |

> 注：公开资料提到 NU7 已于 2026-10-04 在 Testnet 激活（需 Zebra 7.x）。本实验只做 Sapling 转账，
> 在 NU6.3 Testnet（Zebra 6.2.3，即 z3 `main` 默认钉定）上即可完成，**无需 NU7**。
> 若后续需要 NU7 特性再单独评估 Zebra 7.x 分支。

---

## 1. 前置条件

- **Docker Engine 25+**（Docker Desktop 即可；Windows 需 WSL2 后端或 Windows 容器——z3 用 Linux 容器）。
- Git。
- 稳定网络（Testnet 同步需 2–12 小时；首次同步产生一次性成本，单独报告）。
- **Testnet faucet 访问渠道**（获取 TAZ 测试币；通常经 Discord 或官网表单，可能需要人工交互）。
- 约 50–100 GB 可用磁盘（Testnet 链状态；小于主网但仍有规模）。

---

## 2. 搭建 z3 Testnet 栈

```bash
git clone https://github.com/ZcashFoundation/z3 && cd z3

# 2.1 一次性 setup：生成本地配置与 Zallet 钱包身份
./scripts/setup-network.sh testnet

# 2.2 先起 Zebra，等同步完成（health 端口 testnet = 18080）
docker compose --env-file .env.testnet up -d zebra
./scripts/check-zebra-readiness.sh 18080      # 退出即表示已同步

# 2.3 Zebra 就绪后再起 Zallet（否则会重启循环）
docker compose --env-file .env.testnet up -d
```

### 关键端口（testnet，来自 `.env.testnet`）

| 服务 | 容器内端口 | 主机端口 | 用途 |
|---|---|---|---|
| Zebra RPC | 18232 | 18232 | 节点 JSON-RPC（cookie 鉴权） |
| Zebra 健康 | 8080 | 18080 | `/ready` 同步状态 |
| Zallet RPC | 28232 | **40232** | 钱包 JSON-RPC（pczt_* 调用入口） |

- Zebra cookie 在共享卷 `/var/run/auth/.cookie`（由 `cookie-permissions` 旁路调整为可读）。
- Zallet RPC 鉴权来自 `config/testnet/zallet.toml`；脚手架通过 `--zallet-auth user:pass` 或等效方式传入。
- 容器名（用于 `docker stats` 内存采样）：`z3-testnet-zebra-1`、`z3-testnet-zallet-1`
  （`COMPOSE_PROJECT_NAME=z3-testnet`）。

---

## 3. 获取测试资金（一次性成本）

1. 用 Zallet 生成一个收款地址：`zallet rpc getnewaddress`（具体方法名以 `rpc.discover` 为准）。
2. 通过 Testnet faucet 领取 TAZ 到该地址。
3. 确认到账：`zallet rpc getwalletinfo` / `listunspent` 等价方法，看到可花费 note。

> faucet 领取与首次同步属于**一次性成本**，在报告里与每笔发送成本分开成表。

---

## 4. 功能验证门禁（先于重复测量）

> 来自预注册 §4。任一失败 → 暂停并回报环境/工具限制，不进入重复测量。

- [ ] Zebra Testnet 同步成功，Zallet 能识别并花费一笔 faucet 到账的 Note。
- [ ] `pczt_create → pczt_prove → pczt_sign → pczt_extract` 全流程跑通，提取的交易被节点接受并最终进入区块。
- [ ] 至少一笔交易达到 N 确认，收款方钱包识别收款。

### 4.1 先核对 RPC 签名（关键，Beta 易变）

```bash
# 列出全部 RPC
zallet rpc help
# 取 OpenRPC schema，核对 pczt_* 的精确参数名
zallet rpc rpc.discover | python -m json.tool | grep -A20 '"pczt_create"'
```

把核对到的参数形状写进 `e2e_tx_bench.py` 的 `--create-params` / `--prove-params`
（或直接改脚本默认值）。**不要假设参数名与 zcashd 一致**。

### 4.2 手动跑通一笔（建议先手工验证，再交给脚本）

```bash
# 以下为示意；确切参数以 rpc.discover 为准
zallet rpc pczt_create '[{"address":"<recipient>","amount":<amount>}]'
# -> 得到 pczt 字符串，传给下一步
zallet rpc pczt_prove  '["<pczt>"]'
zallet rpc pczt_sign   '["<pczt>"]'
zallet rpc pczt_extract '["<pczt>"]'
# -> 得到原始交易 hex；若 Zallet 未自动广播，则用 Zebra RPC 提交：
#    zebra RPC: sendrawtransaction '<hex>'
```

---

## 5. 接入测量脚手架

功能验证跑通后，用 `e2e_tx_bench.py` 做**分阶段计时 + 进程内存采样**：

```bash
# 5.1 干跑：校验连通性、打印计划调用、取 OpenRPC schema（不真正发交易）
python3 e2e_tx_bench.py --discover --dry-run \
    --zallet-url http://127.0.0.1:40232 \
    --zallet-auth '<user>:<pass>' \
    --recipient '<addr>' --amount <amt> \
    --zebra-url http://127.0.0.1:18232 --zebra-cookie /var/run/auth/.cookie \
    --containers z3-testnet-zebra-1,z3-testnet-zallet-1

# 5.2 正式测量（每笔生成独立 run_id 目录）
python3 e2e_tx_bench.py \
    --zallet-url http://127.0.0.1:40232 --zallet-auth '<user>:<pass>' \
    --recipient '<addr>' --amount <amt> \
    --zebra-url http://127.0.0.1:18232 --zebra-cookie /var/run/auth/.cookie \
    --containers z3-testnet-zebra-1,z3-testnet-zallet-1 \
    --confirmations 2 --sample-interval 1.0 \
    --outdir ../raw/e2e_testnet_tx
```

输出（每笔一个 `run_<时间戳>/`）：
- `stage_timings.csv`：各阶段单调时钟耗时（输入准备 / pczt_create / pczt_prove / pczt_sign / pczt_extract / 广播 / 接受 / 入块 / 确认 / 钱包识别）。
- `memory_timeseries.csv`：采样间隔内的 zebra/zallet 容器内存序列。
- `run_summary.json`：汇总（各阶段毫秒数、峰值内存、交易大小、版本与主机元数据）。

### 5.3 一次性同步内存（单独跑，不在每笔交易内）

首次同步期间另开一个终端：

```bash
python3 mem_sample.py \
    --containers z3-testnet-zebra-1,z3-testnet-zallet-1 \
    --interval 5 --out ../raw/e2e_testnet_tx/sync_memory.csv
```

---

## 6. 统计与报告（冻结，见预注册 §6–§8）

- 功能验证 1 笔；正式测量 **N ≥ 5 笔不同可花费 Note**（N 在验证后按 faucet 可得性冻结）。
- 每阶段取中位数 + 波动范围（min/median/max 或 IQR）。
- **确认相关阶段（广播→接受、等待确认）与本地证明阶段分表报告**，不合并为单一「总耗时」。
- 若 `pczt_prove` 只暴露总证明时间而无法分离 Spend/Output，主报告记总耗时，并用既有本地插桩证明器补充分段基线（明确标注来源）。
- 初次同步、faucet 准备等一次性成本单独成表，不混入每笔发送成本。

---

## 7. 已知风险与边界

- **Zallet Beta**：RPC 参数/行为随版本变化，务必每次 `rpc.discover` 核对；破坏性变更可能要求删库重建钱包。
- **Regtest 不作为完整花费环境**：本实验全程用 Testnet。
- **确认等待受网络影响**：必须与本地证明时间分开报告，否则无法判断瓶颈来源。
- **侧信道**：本实验不修改证明器；若要把分段计时用于论证「替换证明器」收益，须回到 MSM Phase D 预注册并补侧信道语义评估（blst 点加非 constant-time）。
- **NU7**：本实验在 NU6.3 Testnet（Zebra 6.2.3）即可完成，无需 NU7。
