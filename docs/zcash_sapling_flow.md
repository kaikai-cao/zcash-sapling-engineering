
# Zcash Sapling 交易证明调用链

## 1. 研究范围

本记录追踪 Sapling Spend / Output 从交易构造、Groth16 证明生成到证明验证的主要调用路径。

Sapling 电路代码固定为 `sapling-crypto 0.9.0`，commit：

`88a7946b4a3066787776e11f0a502654167e022d`

交易调用路径参考 `zcash/librustzcash` commit：

`3c76c2d822446a68b67cd25692aaf92b4f6cb98c`

交易层和电路层是不同的代码层，不能把单独的电路证明测试等同于完整交易构造与共识验证。

## 2. 证明生成的调用链

```text
钱包后端
  |
  v
create_proposed_transaction(...)
  |
  v
zcash_primitives::transaction::builder::Builder::build(...)
  |
  +-- add_sapling_spend(...)
  +-- add_sapling_output(...)
  |
  v
Sapling builder 构造 bundle
  |
  v
Bundle::create_proofs(...)
  |
  +-- Spend
  |    |
  |    v
  |    SpendProver::create_proof(...)
  |    |
  |    v
  |    SpendParameters::create_proof(...)
  |    |
  |    v
  |    Groth16 create_random_proof(...)
  |
  +-- Output
       |
       v
       OutputProver::create_proof(...)
       |
       v
       OutputParameters::create_proof(...)
       |
       v
       Groth16 create_random_proof(...)

证明生成完成后
  |
  v
计算交易摘要与 sighash
  |
  v
Sapling bundle 应用授权签名
  |
  v
完成交易构造
```

以上是主要调用关系的简化表示，不是完整的函数调用栈。

## 3. 各层分别做什么

### 3.1 钱包后端

`zcash_client_backend/src/data_api/wallet.rs` 中的
`create_proposed_transaction(...)` 调用交易构造器的 `build(...)`，并传入 Spend / Output prover。

参考：

[钱包后端的交易构造调用](https://github.com/zcash/librustzcash/blob/3c76c2d822446a68b67cd25692aaf92b4f6cb98c/zcash_client_backend/src/data_api/wallet.rs)

### 3.2 交易构造器

`zcash_primitives/src/transaction/builder.rs` 中：

- `add_sapling_spend(...)` 把待花费的 Sapling note 及其 Merkle 路径交给 Sapling builder。
- `add_sapling_output(...)` 添加接收地址、金额和 memo 等输出信息。
- `Builder::build(...)` 在内部构造 Sapling bundle，并调用 `bundle.create_proofs(...)`。
- 证明生成后再应用授权签名。

源码还明确说明，证明必须在签名之前生成，因为它仍然支持交易摘要会提交 Sapling 证明内容的 V4 交易。

参考：

[Transaction Builder 源码](https://github.com/zcash/librustzcash/blob/3c76c2d822446a68b67cd25692aaf92b4f6cb98c/zcash_primitives/src/transaction/builder.rs)

### 3.3 Sapling bundle

`sapling-crypto/src/builder.rs` 中的 `Bundle::create_proofs(...)` 遍历 bundle 中的 Spend 和 Output：

- Spend 调用 `spend_prover.create_proof(...)`，然后编码证明。
- Output 调用 `output_prover.create_proof(...)`，然后编码证明。

这一层负责将交易构造流程与具体证明实现连接起来。

参考：

[Sapling bundle 证明生成逻辑](https://github.com/zcash/sapling-crypto/blob/88a7946b4a3066787776e11f0a502654167e022d/src/builder.rs)

### 3.4 Prover 与 Groth16

`sapling-crypto/src/prover.rs` 定义 `SpendProver` 和 `OutputProver` 接口。

`SpendParameters` 和 `OutputParameters` 的具体实现调用 Groth16 的 `create_random_proof(...)`，完成相应电路的证明生成。

`zcash_proofs::LocalTxProver` 则实现这两个接口，并持有 Spend / Output 参数。

生产参数加载路径还包含文件大小与哈希校验；本工程中的独立测量程序采用显式参数文件路径，并单独记录读取时间、点编码验证和文件哈希。

参考：

[Sapling prover 实现](https://github.com/zcash/sapling-crypto/blob/88a7946b4a3066787776e11f0a502654167e022d/src/prover.rs)

[LocalTxProver 实现](https://github.com/zcash/librustzcash/blob/3c76c2d822446a68b67cd25692aaf92b4f6cb98c/zcash_proofs/src/prover.rs)

## 4. 验证调用链

```text
已构造的 Sapling bundle
  |
  v
SaplingVerificationContext 或 BatchValidator
  |
  +-- Spend
  |    |
  |    +-- 检查 Spend 授权签名
  |    +-- 构造 7 个公开输入
  |    +-- Groth16 proof verification
  |
  +-- Output
       |
       +-- 检查相关曲线点与公开数据
       +-- 构造 5 个公开输入
       +-- Groth16 proof verification
  |
  v
对整个 bundle 执行最终检查
  |
  v
检查 binding signature
```

`SaplingVerificationContext::check_spend(...)` 除了验证 Groth16 证明，还会验证 Spend 授权签名，并构造公开输入。

其公开输入由随机化验证密钥 `rk`、value commitment、anchor 和 nullifier 的打包结果组成，共 7 个域元素。

`check_output(...)` 的公开输入由 value commitment、ephemeral public key 和 note commitment 组成，共 5 个域元素。

`final_check(...)` 则负责整个 bundle 的最终 value-balance / binding-signature 检查。完整交易验证还包括此处未展开的其他交易与共识规则。

参考：

[单笔 Sapling 验证逻辑](https://github.com/zcash/sapling-crypto/blob/88a7946b4a3066787776e11f0a502654167e022d/src/verifier/single.rs)

[批量 Sapling 验证逻辑](https://github.com/zcash/sapling-crypto/blob/88a7946b4a3066787776e11f0a502654167e022d/src/verifier/batch.rs)

## 5. 与本工程实验的对应关系

本工程目前完成的内容：

| 实验 | 覆盖范围 |
|---|---|
| 电路规模测量 | 统计 Spend / Output 约束和变量数 |
| 参数测量 | 记录参数文件大小、哈希和读取验证时间 |
| Spend proving | 5 次证明生成，5 次成功验证 |
| Output proving | 5 次证明生成，5 次成功验证 |
| Python 汇总 | 3 张 CSV 汇总表、7 张 PNG 图 |

当前 proving 实验直接调用对应的参数与 prover 接口；验证实验直接调用 Sapling 的 Spend / Output 验证接口。

它们没有执行完整的 `Builder::build(...)` 钱包交易构造流程，也没有覆盖完整交易中的所有 bundle 最终检查、交易序列化和网络提交。因此，当前结果衡量的是 Sapling 证明流程中的核心环节，而不是生成一笔完整 Zcash 交易的总耗时。

## 6. 阶段性结论

Sapling 的 Groth16 证明不是由钱包直接计算出来的，而是由交易构造器组织 Spend / Output 电路，通过 prover 接口调用 Groth16 实现生成。

Spend 与 Output 使用不同的电路和参数文件，但都生成固定大小的 Groth16 证明。后续分析应区分电路规模、参数加载、证明生成、证明验证和整个交易构造的开销，避免用单一时间指标代表整个系统性能。

本阶段暂不开展算法优化，优先完成交易调用链和实验数据的可复现记录。