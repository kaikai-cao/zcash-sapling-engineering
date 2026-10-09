# Sapling 工程环境与测试记录

**日期:** 2026-10-09

## 1. 上游工程

* Repository: https://github.com/zcash/sapling-crypto
* Commit: `88a7946b4a3066787776e11f0a502654167e022d`
* Git working tree: clean
* Rust: `1.88.0`
* Cargo: `1.88.0`

## 2. 环境验证

| Command       | Result                          | Status |
| ------------- | ------------------------------- | ------ |
| `cargo check` | Finished dev profile in 16.25 s | PASS   |
| `cargo test`  | 76 passed, 0 failed             | PASS   |
| Doc-tests     | 1 passed, 0 failed, 0.68 s      | PASS   |

Unit tests finished in 47.34 s.

## 3. 当前结论

* 官方 Sapling 工程可以通过编译检查。
* 当前版本的单元测试与文档测试均通过。
* 本次只验证了编译与测试，没有完成使用正式 Sapling 参数的 Groth16 proof 生成和验证。
* 本次运行没有保存完整的 stdout/stderr 原始日志；测试结果根据终端输出记录。后续正式实验将使用日志重定向保存完整输出。

## 4. 下一步

1. 获取并校验官方 Sapling Spend / Output 参数文件。
2. 构建最小 proving + verifying 程序。
3. 保存运行日志和结构化实验数据。
4. 为实际测量的 Prove、Verify、参数加载等指标生成对比图表。
