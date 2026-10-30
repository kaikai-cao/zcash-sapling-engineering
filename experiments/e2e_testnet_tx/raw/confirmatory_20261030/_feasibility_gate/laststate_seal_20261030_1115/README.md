# 门禁末态封存 — 2026-10-30 11:15

## 为什么封存

门禁（`--mode gate`, run `20261030_110042`）结束后按方案 B 保留末态未恢复。
下一步需要**探测地址派生能力**，而探测必须先恢复到冻结快照、会覆盖当前 `~/z3-regtest/data`。
因此在恢复之前，把末态完整取证并固化于此目录，避免"为了探测而丢掉末态"。

## 目录内容

| 文件 | 说明 |
|---|---|
| `wallet.db.sealed` | 末态 `wallet.db` 的字节级副本（3,198,976 B） |
| `wallet.db.sealed.sha256` 见下方 | SHA256 `1512cf95f3c5ff46e7e54882357cebfc3135085c772dfb87338e7e844b0f3e02` |
| `filelist.tsv` | `zebra-state/` + `zallet/` 全部 1051 个文件的 `大小<TAB>路径` |
| `sha256.txt` | 同一 1051 个文件的 SHA256（逐文件） |
| `addresses_before.tsv` | `addresses` 表 39 行的完整导出（id / account_id / key_scope / diversifier_index_be(hex) / address / receiver_flags / exposed_at_height） |

## 末态关键事实（封存时刻）

- `wallet.db` SHA256：`1512cf95f3c5ff46e7e54882357cebfc3135085c772dfb87338e7e844b0f3e02`
  - 与**快照归档内**同名文件 `4fb0a7918f950518e3354a9cebd0763ef7cbba44b1b29eb136237fec8bd68df4` **不同**：语义一致、字节不一致（zallet 启动时重写 SQLite 页）。
- 表级指标（与归档 7/7 相同）：`transactions=50`、`sapling_received_notes=50`、`sapling_received_note_spends=14`、unspent=36、unspent_zat=11999980000、`max(mined_height)=32296`、`max(blocks.height)=32297`。
- `accounts` = 1 行（hd_account_index=0）；`addresses` = 39 行，`diversifier_index_be` 唯一值 24 个，`receiver_flags` 取值集合 `{1,4,5,8,9,12,13}`。
- 末态 RPC（门禁结束后补采，非结束瞬间）：
  - `getblockcount` = 32297
  - `getrawmempool` = `[]`
  - `z_getnotescount([1])` = `{sprout:0, sapling:36, orchard:0, ironwood:1}`
  - `z_getbalanceforaccount(ACCOUNT,1).pools.sapling.valueZat` = 11999980000
  - `getwalletstatus`：`wallet_tip=32297`、`fully_synced_height=32297`、`node_tip=31296`

## 服务进程状态

封存时 `zebrad` / `zallet-zaino` **均未运行**（门禁的 WSL 后台任务结束后实例被回收）。上述 RPC 值为 11:07 补采时取得，补采前后 DB 计数未变。

## 用途限制

本目录仅作末态证据留存，**不参与统计**。地址派生探测在恢复后的冻结快照上进行，其结果另立记录。
