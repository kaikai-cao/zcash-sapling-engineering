#!/usr/bin/env python3
"""
Sapling 端到端成本模型 · 补充验证（confirmatory）测量执行器

> 配套预注册：experiments/metadata/sapling_e2e_regtest_confirmatory_preregistration_20261030.md
> 这是「候选协议」的**强制实现**：把预注册里冻结的实验协议（每轮快照恢复、
> (S,O) 显式目标 + 实际形态反查、策略冻结、计时边界、门禁数据隔离）写进代码，
> 使得补测不再依赖 sapling_e2e_bench.py 的「探索性循环」（那个脚本没有快照恢复、
> 会按 amount 间接控形态、且策略会自动回退）。

本执行器与预注册不一致的地方一律视为缺陷，请以预注册为准。

==================================================================
执行协议（每次探测 / 每次正式测量都严格执行）
==================================================================
  1. 恢复快照：停服 → 解包 → 重启 → 等追平（委托 wsl/snapshot_restore.sh --yes）
  2. 初始状态核验（硬阻断）：恢复后查链高必须 == 32297；可花费 Sapling Note
     清单必须成功读取且解析；余额必须可读；对目标 (S,O) 必须能可靠构造金额
     （强制 S 个 spend 的边界可满足，否则该形态标为不可行，停止发送）。
  3. 准备地址与构造：目标 (S,O) → O-1 个收款地址（预期 1 个找零 → 实际 O 输出），
     每个收款地址都是**互不相同**的 Sapling-only UA（显式 diversifier index 派生，
     不可用 index 跳过顺延，预算 64 次/轮），且必须先过 L1 去重、L1.5 账户地址集合
     一致性、L2 receiver 校验；按 note 清单选金额，显式预留手续费
     F = 5000·max(S,O) 与正找零，迫使恰好动用前 S 个最小 note。
     地址准备失败 → 记为 recipient_derivation_failed / recipient_validation_failed，
     不构造、不发送、不计有效成功。
  4. 计时（冻结边界，沿用 sapling_e2e_bench 的单调时钟与 20ms 轮询）：
       submit   = z_sendmany RPC 往返（拿到 opid）
       pipeline = opid 返回 → 首次 status=success（含 Groth16 证明+签名+广播）
     策略冻结为单一 policy（默认 FullPrivacy），**不回退**到 AllowRevealedAmounts；
     若被拒即记失败，不偷偷换策略。
  5. 反查实际形态：z_viewtransaction 取实际 spends/outputs，记录 target vs actual，
     并计算 form_match（实际==目标）与 fee_match（实际手续费==5000·max(S,O)）。
  6. 留档：成功/失败/实际形态/手续费/策略/二进制版本/恢复脚本哈希全部落盘。

有效样本定义（门禁与正式一致）：txid 存在 且 form_match 且 fee_match。
仅 tx 成功但形态或手续费不符 → 不计入目标形态的有效样本。

数据隔离：
  --mode gate    写到 raw/confirmatory_20261030/_feasibility_gate/run_<ts>/（绝不进入正式统计）
  --mode confirm 写到 raw/confirmatory_20261030/run_<ts>/
  正式分析必须显式传入：
    python3 fit_sapling_e2e_model.py --raw-dir raw/confirmatory_20261030 --require-match
  （fit 脚本已自动排除 _feasibility_gate/ 子目录；--require-match 仅保留
   form_match 与 fee_match 均为真的轮次。）

注意：本脚本在 WSL2 内运行（路径用 /mnt/d/...，调用 bash 子进程）。
注意：--dry-run 仍会调用快照恢复流程（停服→解包→重启→核验），并非完全不改环境；
      它只是不发 z_sendmany。需要完全不改环境，请勿运行任何 --mode 命令。
"""

import argparse
import csv
import hashlib
import http.client
import json
import os
import random
import sqlite3
import subprocess
import sys
import time

# 复用既有基准脚本的 RPC / 计时 / 形态反查实现，保证 submit/pipeline 边界完全一致
from sapling_e2e_bench import (
    z, b, height, wait_sync, advance, sapling_ua, pools, sapling_zat,
    view_tx, tee_stdio, Sampler, find_pids, rss_kb, STAGES, build_amounts,
    COOKIE, ACCOUNT, tx_size,
    # 地址派生需要「结构化错误」：z() 把 JSON-RPC error 压成字符串，无法按 code
    # 区分可恢复的 -4 与其它错误。这里复用同模块的底层 POST 与 cookie 认证，
    # 避免出现第二套 RPC 认证口径。
    _post, zauth, ZA,
)

# ---------------------------------------------------------------------------
# 冻结的环境常量（与预注册 §1 / DEVIATIONS §1 一致）
# ---------------------------------------------------------------------------
SNAPSHOT_WSL = "/mnt/d/Research/z3/snapshots/z3_regtest_h32297_20261029_145710.tar.gz"
SNAPSHOT_SHA256 = "ca35201887b8041b44c483ad258a718f4a74787c02c4ff9dbbb202857b09510c"
SNAPSHOT_TARGET_HEIGHT = 32297          # 快照恢复后的预期链高（文件名编码，非 ZIP212 门槛 32257）
WSL_DIR = "/mnt/d/Research/z3/wsl"
RESTORE_SCRIPT = os.path.join(WSL_DIR, "snapshot_restore.sh")
RESTORE_SCRIPT_SHA256 = "2df7cd8bd4890963d925711912aa280f944156319d2b6aa5fa2b53c35a720e11"
PRE_REG_SEED = 20261030                 # 正式测量随机顺序的固定种子（预注册 §6）
FROZEN_POLICY = "FullPrivacy"           # 策略冻结：单一 policy，不回退（预注册 §5/用户审阅 §3）
OUTDIR_BASE = "raw/confirmatory_20261030"
MIN_CHANGE_ZAT = 100000                 # 0.001 ZEC：强制正找零下限，保证 change>0

# --- A′：Note 清单改为「钱包 DB 只读 + schema 断言 + 双 RPC 硬校验」 ---------
# 不用 z_listunspent 的原因（实测，见 _note_scan_diag/）：
#   快照里 26 个 note 的 memo 是 512B 随机字节，zallet 对 memo[0] < 0xF5 的记录
#   强行按 UTF-8 解码 → 抛 `WalletDb::get_memo failed: Invalid UTF-8`，整条清单不可读；
#   maxconf=10000 只是恰好把其中大部分排除，返回的是被截断的 10/36，且被截掉的
#   并非最大的 note —— 会静默破坏「恰好动用 S 个 note」的构造，属于「能跑但错」。
WALLET_DB_PATH = os.environ.get("E2E_WALLET_DB") or os.path.expanduser(
    "~/z3-regtest/data/zallet/wallet.db")
# 冻结快照的可花费 Sapling Note 预期值（门禁核验后回填预注册 §1）。
# 这不是 warning：四个量必须两两相等，任一不等即视为清单不完整。
EXPECTED_SAPLING_NOTE_COUNT = 36
EXPECTED_SAPLING_ZAT = 11999980000
DB_REQUIRED_SCHEMA = {
    "sapling_received_notes": {"id", "transaction_id", "output_index", "value", "memo"},
    "transactions": {"id_tx", "txid", "mined_height"},
    "sapling_received_note_spends": {"sapling_received_note_id"},
}
SQL_UNSPENT_SAPLING = """
SELECT n.id, t.txid, t.mined_height, n.output_index, n.value
FROM sapling_received_notes AS n
JOIN transactions AS t ON t.id_tx = n.transaction_id
WHERE NOT EXISTS (
    SELECT 1 FROM sapling_received_note_spends AS s
    WHERE s.sapling_received_note_id = n.id
)
ORDER BY n.value ASC, n.id ASC
"""

# 候选矩阵（预注册 §4，10 种形态，每格目标 5 次有效成功；门禁每格 1 次）
DEFAULT_MATRIX = [
    (1, 2), (2, 2), (4, 2), (7, 2), (10, 2), (17, 2),
    (1, 9), (3, 2), (3, 3), (4, 3),
]
MAX_ATTEMPTS_PER_FORM = 8               # 每格最多尝试次数（预注册 §4）
TARGET_SUCCESS_PER_FORM = 5             # 每格目标有效成功次数（预注册 §4）

# --- 多收款地址派生（ZIP 316 显式 diversifier index）------------------------
# 门禁 run_20261030_110042 暴露：`recipients = [from_ua] * n_recip` 在 n_recip>=2
# 时被 zebra 以 `-8 duplicated recipient address` 拒绝。地址派生能力探测
# （experiments/metadata/sapling_e2e_address_derivation_probe_20261030.md）实测：
#   ① zallet 支持 z_getaddressforaccount(acct, ["sapling"], index) 得到不同 UA；
#   ② 低 index 可能已被历史 receiver 组合占用，或该 diversifier 导不出有效
#      Jubjub point → 报 -4，必须跳过顺延；
#   ③ 只有下面两类 -4 属于「换个 index 就行」，其余错误一律 fail-closed。
# 预算按「每轮 attempt 独立 64 次」计。实测（2026-10-30，本快照环境，样本有限）：
# 跳过率约 53%，n_recip=8 实际消耗 17–19 次，余量约 3.4 倍。64 是当前样本下的
# 工程取值，**不是**对未来其它钱包状态/环境的保证；若预算耗尽，抛错并记
# recipient_derivation_failed，**不允许**回退到旧地址或重复地址兜底。
DERIVE_ATTEMPT_BUDGET = 64
INDEX_DOMAIN_MAX = (1 << 88) - 1        # ZIP 316 diversifier index 为 11 字节
DERIVE_RETRYABLE_PATTERNS = (
    "cannot generate an address with the requested receivers",
    "was already generated with different receiver types",
)


# ---------------------------------------------------------------------------
# 自定义异常（区分「结构性不可行」与「可重试的瞬时失败」）
# ---------------------------------------------------------------------------
class StateError(Exception):
    """初始状态核验失败，但可能瞬时（可重试）。"""


class HeightMismatch(StateError):
    """恢复后链高与预期不符 —— 结构性错误，不应重试。"""


class PreTxError(Exception):
    """交易提交前就已失败（RPC 拒绝、opid 终态失败、超时、资金不足等）。

    F5：异常除文本外还承载**结构化事实**，供 `_classify()` 与 sidecar 使用，
    不再靠自然语言包装语（如「policy=... 被拒」）传达阶段：

        stage              失败阶段（§4.3 七值之一，见 metadata 设计稿）
        raw_error          原始 JSON-RPC error dict（**原对象，不截断**）
        raw_transport      传输异常 {type, repr, errno}（不截断）
        code / rpc_message 从 raw_error 解出的码与完整消息
        opid               已拿到的异步操作 id
        z_sendmany_invoked 是否调用过 z_sendmany
        submit_state       not_submitted / unknown / submitted（§4.8 三态）

    默认值为「未触及提交」（最保守以外的另一侧）：未显式覆盖时不会被误判为已提交；
    需要表达的 unknown/submitted 必须在 raise 处显式写出，避免隐式状态。
    """

    stage = None
    raw_error = None
    raw_transport = None
    code = None
    rpc_message = None
    opid = None
    z_sendmany_invoked = False
    submit_state = "not_submitted"
    method = None

    def __init__(self, msg, stage=None, raw_error=None, raw_transport=None, opid=None,
                 z_sendmany_invoked=None, submit_state=None, method=None):
        Exception.__init__(self, msg)
        if stage is not None:
            self.stage = stage
        if raw_error is not None:
            self.raw_error = raw_error
            if isinstance(raw_error, dict):
                self.code = raw_error.get("code")
                self.rpc_message = raw_error.get("message")
        if raw_transport is not None:
            self.raw_transport = raw_transport
        if opid is not None:
            self.opid = opid
        if z_sendmany_invoked is not None:
            self.z_sendmany_invoked = bool(z_sendmany_invoked)
        if submit_state is not None:
            self.submit_state = submit_state
        if method is not None:
            self.method = method


class RpcCallError(PreTxError):
    """JSON-RPC 层失败：请求已送达，服务端返回结构化 error。

    `submit_state` 默认 `not_submitted`：拿到 error 响应即未拿到 opid，交易**未被受理**。
    注意表述边界：只说「未被受理」，不说「什么都没发生」（§4.8）。
    """


class TransportError(PreTxError):
    """传输层异常：未收到可解析的 JSON-RPC 响应。

    请求是否到达**不可知**，故 `submit_state` 默认 `unknown`（从严）——
    这正是「不得重发」的技术依据，不能由「没有 txid」推定未提交（§4.8 / G4）。
    """

    submit_state = "unknown"


class SchemaMismatch(StateError):
    """钱包 DB schema / 记录结构与本执行器预期不符 —— 结构性错误，整轮中止，不重试。"""


class RecipientError(PreTxError):
    """收款地址准备失败（派生或校验）—— 发生在交易构造之前，不可能产生 txid。

    继承 PreTxError 只是为了让「万一未被就地捕获」时仍落到「提交前失败」路径；
    正常路径由 run_one() 就地捕获并写成失败行，failure_class 显式赋值，不经 _classify()。
    """
    cls = "recipient_error"

    def __init__(self, msg, attempts=0):
        PreTxError.__init__(self, msg)
        self.attempts = attempts          # 已消耗的派生尝试次数（写入 rounds.csv）


class RecipientDerivationError(RecipientError):
    """地址派生失败（index 越界 / 不可恢复的 RPC 错误 / 预算耗尽）。"""
    cls = "recipient_derivation_failed"


class RecipientValidationError(RecipientError):
    """地址校验失败（L1 去重 / L1.5 归属一致性 / L2 Sapling-only）。"""
    cls = "recipient_validation_failed"


# ---------------------------------------------------------------------------
# 失败证据：结构化异常工具 + sidecar（errors.jsonl）
#
# 设计依据：experiments/metadata/sapling_e2e_f5_error_classification_design_20261030.md
# §4.8 提交状态三态 / §4.9 sidecar 三条硬条件 / §4.10 事实层与解释层分离。
# ---------------------------------------------------------------------------
# _post 的四类失败模式（§15.2 第 2 项）：前三者请求可能未到达，
# json.JSONDecodeError 表示请求**已到达**但响应不可解析 —— 一律按 unknown 处理。
_TRANSPORT_EXC = (OSError, http.client.HTTPException, json.JSONDecodeError)

_UNSET = object()


def _transport_detail(e):
    """传输异常原样留证：类型 + repr + errno，不截断（§4.9 条件 1）。"""
    return {"type": type(e).__name__, "repr": repr(e), "errno": getattr(e, "errno", None)}


def _rpc_brief(raw_error):
    """把结构化 error 压成一行便于 CSV 阅读；完整对象另存 sidecar。"""
    if isinstance(raw_error, dict):
        return "code=%s message=%s" % (raw_error.get("code"), raw_error.get("message"))
    return repr(raw_error)


# ---------------------------------------------------------------------------
# 快照恢复与状态核验
# ---------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def restore_snapshot(allow_hash_mismatch=False, allow_script_mismatch=False):
    """停服 → 解包 → 重启 → 等追平（委托 snapshot_restore.sh）。

    返回 (快照实际 SHA256, 恢复脚本实际 SHA256)，用于与冻结值比对并记录。
    注意：本函数会停服并覆盖 ~/z3-regtest/data，已在预注册 §6 显式纳入协议；
    不要在未确认环境可恢复时随意调用。
    """
    if not os.path.isfile(RESTORE_SCRIPT):
        raise RuntimeError("找不到恢复脚本: %s" % RESTORE_SCRIPT)
    if not os.path.isfile(SNAPSHOT_WSL):
        raise RuntimeError("找不到快照归档: %s" % SNAPSHOT_WSL)

    snap_actual = sha256_file(SNAPSHOT_WSL)
    if snap_actual != SNAPSHOT_SHA256:
        msg = ("[!] 快照 SHA256 与预注册冻结值不一致\n    冻结: %s\n    实际: %s"
               % (SNAPSHOT_SHA256, snap_actual))
        if allow_hash_mismatch:
            print(msg + "\n    已按 --allow-hash-mismatch 继续（实际哈希将记录到 meta.json）")
        else:
            raise RuntimeError(msg + "\n    如需继续请用 --allow-hash-mismatch，并同步更新预注册 §1。")
    else:
        print("[snap] 快照 SHA256 匹配: %s" % snap_actual)

    script_actual = sha256_file(RESTORE_SCRIPT)
    if script_actual != RESTORE_SCRIPT_SHA256:
        smsg = ("[!] 恢复脚本 SHA256 与冻结值不一致\n    冻结: %s\n    实际: %s"
                % (RESTORE_SCRIPT_SHA256, script_actual))
        if allow_script_mismatch:
            print(smsg + "\n    已按 --allow-script-mismatch 继续（实际哈希将记录到 meta.json）")
        else:
            raise RuntimeError(smsg + "\n    恢复脚本行为可能已变，先复核再继续（--allow-script-mismatch）。")
    else:
        print("[snap] 恢复脚本 SHA256 匹配: %s" % script_actual)

    print("[snap] 恢复中（停服→解包→重启→等追平，可能 1~5 分钟）…")
    t0 = time.monotonic()
    rc = subprocess.call(["bash", RESTORE_SCRIPT, "--yes", SNAPSHOT_WSL])
    dt = time.monotonic() - t0
    if rc != 0:
        raise RuntimeError("snapshot_restore.sh 退出码 %d（环境可能处于不一致状态）" % rc)
    print("[snap] 恢复完成（%.1fs），快照 SHA256=%s 脚本 SHA256=%s" % (dt, snap_actual, script_actual))
    return snap_actual, script_actual


def _db_columns(cur, table):
    return [r[1] for r in cur.execute("PRAGMA table_info(%s)" % table)]


def assert_wallet_db_schema(cur=None):
    """断言钱包 DB schema；不匹配抛 SchemaMismatch（绝不猜字段、绝不做兼容猜测）。

    cur=None 时自行只读打开一次连接（供 preflight 使用）。
    """
    close = False
    if cur is None:
        if not os.path.isfile(WALLET_DB_PATH):
            raise SchemaMismatch("钱包 DB 不存在: %s" % WALLET_DB_PATH)
        con = sqlite3.connect("file:%s?mode=ro" % WALLET_DB_PATH, uri=True, timeout=10)
        cur = con.cursor()
        close = True
    try:
        tables = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, need in DB_REQUIRED_SCHEMA.items():
            if table not in tables:
                raise SchemaMismatch(
                    "钱包 DB 缺少表 %s（现有 %d 张表；前 10: %s）"
                    % (table, len(tables), sorted(tables)[:10]))
            missing = need - set(_db_columns(cur, table))
            if missing:
                raise SchemaMismatch("表 %s 缺少字段 %s（现有: %s）"
                                     % (table, sorted(missing), _db_columns(cur, table)))
    finally:
        if close:
            try:
                con.close()
            except Exception:
                pass


def note_inventory_detailed():
    """A′：只读读取钱包 DB 中全部可花费 Sapling Note，并做四重硬校验。

    校验链（任一不满足即失败；**绝不回退到 z_listunspent**）：
      1) 只读打开（sqlite mode=ro），不写库、不改快照、不恢复服务；
      2) schema 断言：表 / 关联字段 / mined_height / spent 判定字段齐备；
      3) 逐条记录合法性：value>0、txid 与 output_index 非空、已确认（0 < mined_height <= 链高）、
         身份 (txid, output_index) 不重复；
      4) 双 RPC 硬校验（这两个 RPC 都不解码 memo，故不受 memo bug 影响）：
             DB 条数 == z_getnotescount([1]).sapling == EXPECTED_SAPLING_NOTE_COUNT
             DB 总额 == z_getbalanceforaccount([ACCOUNT,1]).pools.sapling.valueZat
                     == EXPECTED_SAPLING_ZAT
    返回 list[dict]（按 value 升序）或 None（读取失败，由 verify_state 硬停）。
    """
    if not os.path.isfile(WALLET_DB_PATH):
        print("[inv][warn] 钱包 DB 不存在: %s" % WALLET_DB_PATH)
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % WALLET_DB_PATH, uri=True, timeout=10)
    except Exception as e:
        print("[inv][warn] 钱包 DB 只读打开失败: %s" % str(e)[:160])
        return None

    try:
        cur = con.cursor()
        assert_wallet_db_schema(cur)
        rows = cur.execute(SQL_UNSPENT_SAPLING).fetchall()
    except SchemaMismatch:
        raise
    except Exception as e:
        print("[inv][warn] 钱包 DB 查询失败: %s" % str(e)[:160])
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass

    h = height()
    if h is None:
        print("[inv][warn] 无法读取链高，Note 的确认高度无法校验")
        return None

    recs = []
    seen = set()
    for nid, txid, mined_height, out_index, value in rows:
        if txid is None or out_index is None or mined_height is None:
            raise SchemaMismatch(
                "note id=%s 关联字段缺失（txid/output_index/mined_height 有空值）" % nid)
        if value is None or int(value) <= 0:
            raise SchemaMismatch("note id=%s 面值非法: %r" % (nid, value))
        key = (bytes(txid).hex(), int(out_index))
        if key in seen:
            raise SchemaMismatch("note 身份重复: txid=%s outindex=%d" % key)
        seen.add(key)
        mh = int(mined_height)
        if mh <= 0 or mh > h:
            raise SchemaMismatch("note id=%s mined_height=%d 不在 (0, 链高 %d] 内" % (nid, mh, h))
        recs.append({"note_id": nid, "txid": key[0], "output_index": key[1],
                     "value_zat": int(value), "mined_height": mh,
                     "confirmations": h - mh + 1})

    db_count = len(recs)
    db_zat = sum(r["value_zat"] for r in recs)

    # 双 RPC 硬校验（两个都不解码 memo）
    try:
        cnt_obj = z("z_getnotescount", [1])
        rpc_count = int((cnt_obj or {}).get("sapling"))
    except Exception as e:
        print("[inv][warn] z_getnotescount 失败: %s" % str(e)[:160])
        return None
    try:
        bal_obj = z("z_getbalanceforaccount", [ACCOUNT, 1])
        rpc_zat = int(((bal_obj or {}).get("pools") or {}).get("sapling", {}).get("valueZat"))
    except Exception as e:
        print("[inv][warn] z_getbalanceforaccount 失败: %s" % str(e)[:160])
        return None

    bad = []
    if db_count != EXPECTED_SAPLING_NOTE_COUNT:
        bad.append("DB 条数 %d != 预期冻结值 %d" % (db_count, EXPECTED_SAPLING_NOTE_COUNT))
    if db_zat != EXPECTED_SAPLING_ZAT:
        bad.append("DB 总额 %d != 预期冻结值 %d" % (db_zat, EXPECTED_SAPLING_ZAT))
    if rpc_count != db_count:
        bad.append("RPC 条数 %d != DB 条数 %d" % (rpc_count, db_count))
    if rpc_zat != db_zat:
        bad.append("RPC 余额 %d != DB 总额 %d" % (rpc_zat, db_zat))
    if bad:
        raise StateError("Note 清单完整性校验失败（清单不完整，停止发交易）：\n  "
                         + "\n  ".join(bad))

    print("[inv] DB 只读清单 OK: %d notes / %d zat | RPC count=%d balance=%d 全部一致 | "
          "高度 %d..%d"
          % (db_count, db_zat, rpc_count, rpc_zat,
             min(r["mined_height"] for r in recs), max(r["mined_height"] for r in recs)))
    return recs


def note_inventory():
    """取当前钱包可花费 Sapling Note 面值列表（zat），升序；失败返回 None。

    严格规则：拿不到可靠清单就返回 None，由上层**停止发交易**，绝不粗略猜测。
    数据来源为 A′ 的钱包 DB 只读清单（见 note_inventory_detailed），不使用 z_listunspent。
    """
    recs = note_inventory_detailed()
    if recs is None:
        return None
    return [r["value_zat"] for r in recs]

def pick_amount_zat(S, O, inv):
    """选金额，显式预留手续费 F=5000·max(S,O) 与正找零，迫使恰好动用前 S 个最小 note。

    返回 dict {amount_zat, fee_zat, unit_zat, n_recip}；不可靠构造返回 None。
    边界（最佳努力，非对钱包选币的保证，最终以 z_viewtransaction 反查为准）：
        sum_{i=1}^{S-1} v_i  <  A + F  <=  sum_{i=1}^{S} v_i
    即 S-1 个最小 note 不够付（A+F），但 S 个最小 note 够付 → 钱包至少选 S 个 note。
    change = (前 S 个 note 总额) - A - F >= MIN_CHANGE_ZAT > 0。
    """
    if not inv or len(inv) < S or S < 1:
        return None
    inv = sorted(inv)
    F = 5000 * max(S, O)
    sumS = sum(inv[:S])
    sumSm1 = sum(inv[:S - 1]) if S > 1 else 0
    C = MIN_CHANGE_ZAT
    A = sumS - F - C                       # 收款地址总额（zat）
    if A <= 0:
        return None
    n_recip = max(1, O - 1)
    unit = A // n_recip
    if unit < 1:
        return None
    A_actual = unit * n_recip              # 实际收款总额（整数化后略小）
    # 用实际值复核边界
    if not (A_actual + F > sumSm1 and A_actual + F <= sumS):
        return None
    return {"amount_zat": A_actual, "fee_zat": F, "unit_zat": unit, "n_recip": n_recip}


def verify_state(snap_sha, script_sha, S, O, allow_height_mismatch=False):
    """恢复后硬核验：链高、可花费 Note 清单、余额、目标形态可构造性。返回 dict。

    - 链高必须 == SNAPSHOT_TARGET_HEIGHT，否则抛 HeightMismatch（结构性，不重试）。
    - Note 清单必须成功读取且非空，否则抛 StateError（瞬时，可重试）。
    - 余额必须可读，否则抛 StateError。
    - 对目标 (S,O) 必须能算出满足边界的金额，否则抛 StateError（形态不可行）。
    """
    h = height()
    if h is None:
        raise StateError("无法读取链高（钱包/节点可能未就绪）")
    if h != SNAPSHOT_TARGET_HEIGHT:
        if allow_height_mismatch:
            print("[verify][warn] 链高=%s 预期 %d（已按 --allow-height-mismatch 继续）" % (h, SNAPSHOT_TARGET_HEIGHT))
        else:
            raise HeightMismatch("恢复后链高=%s 预期 %d —— 快照恢复异常，停止发送" % (h, SNAPSHOT_TARGET_HEIGHT))

    inv = note_inventory()
    if inv is None:
        raise StateError("无法读取可花费 Note 清单（RPC 失败），停止以免未知状态")
    if len(inv) == 0:
        raise StateError("可花费 Note 数为 0")
    if len(inv) < S:
        raise StateError("可花费 Note 数=%d < 目标 S=%d，无法构造目标形态" % (len(inv), S))

    pick = pick_amount_zat(S, O, inv)
    if pick is None:
        raise StateError("目标 (S=%d,O=%d) 在现有 Note 下无法可靠构造（金额边界无法满足，note 数=%d）"
                         % (S, O, len(inv)))

    bal = sapling_zat()
    if bal is None:
        raise StateError("无法读取 Sapling 余额")

    print("[verify] 链高=%s(预期%d) notes=%d sapling余额=%s zat | 金额边界 A+F in (%d, %d]"
          % (h, SNAPSHOT_TARGET_HEIGHT, len(inv), bal,
             sum(sorted(inv)[:S - 1]) if S > 1 else 0, sum(sorted(inv)[:S])))
    return {"restored_height": h, "restored_note_count": len(inv),
            "restored_sapling_zat": bal, "snapshot_sha256": snap_sha,
            "snapshot_sha256_expected": SNAPSHOT_SHA256,
            "snapshot_hash_match": snap_sha == SNAPSHOT_SHA256,
            "restore_script_sha256": script_sha,
            "restore_script_sha256_expected": RESTORE_SCRIPT_SHA256,
            "restore_script_hash_match": script_sha == RESTORE_SCRIPT_SHA256,
            "pick": pick}


# ---------------------------------------------------------------------------
# 计时（冻结边界，单一策略，无回退）
# ---------------------------------------------------------------------------
def send_frozen(from_ua, amounts, policy, timeout_op=600):
    """提交 → 轮询 → 返回 (t_submit_ms, t_pipeline_ms, opid, result)。

    只使用 policy 一种策略；被拒即抛错，绝不回退到其它策略（预注册 §5）。

    F5：不再把异常包装成「policy=... 被拒」这种带归因的文本 —— 它曾让**所有**
    发送阶段失败（含 -8 参数错误、-6 资金不足、轮询超时）都被判成「策略拒绝」。
    现在异常只陈述事实（阶段 + code + RPC 原文），阶段与提交状态显式写入属性。
    """
    params = [from_ua, amounts, 1, None, policy]
    t0 = time.monotonic()
    try:
        # I1：timeout 必须显式传 120。z_raw 默认 60，退回默认即改变行为口径。
        res, err = z_raw("z_sendmany", params, timeout=120)
    except _TRANSPORT_EXC as e:
        # zauth() 在读 cookie 时失败：请求尚未发出，可判未提交（仍是环境问题）
        if isinstance(e, FileNotFoundError) and getattr(e, "filename", None) == COOKIE:
            raise TransportError("stage=submit 读取 RPC cookie 失败: %s" % type(e).__name__,
                                 stage="submit", raw_transport=_transport_detail(e),
                                 z_sendmany_invoked=False, submit_state="not_submitted",
                                 method="z_sendmany")
        # 其余传输层异常：请求是否到达不可知 → unknown（从严，§4.8）
        raise TransportError("stage=submit 传输层异常: %s" % type(e).__name__,
                             stage="submit", raw_transport=_transport_detail(e),
                             z_sendmany_invoked=True, submit_state="unknown",
                             method="z_sendmany")
    if err:
        raise RpcCallError("stage=submit RPC 拒绝: %s" % _rpc_brief(err),
                           stage="submit", raw_error=err, z_sendmany_invoked=True,
                           submit_state="not_submitted", method="z_sendmany")
    if not isinstance(res, str) or not res.strip():
        # 既无 error 也无可用的 opid：请求已到达但响应不可用 → 同 unknown 处理
        raise TransportError("stage=submit 响应无 opid（result=%r）" % (res,),
                             stage="submit", z_sendmany_invoked=True,
                             submit_state="unknown", method="z_sendmany")
    opid = res
    t_submit = (time.monotonic() - t0) * 1000.0

    t1 = time.monotonic()
    while time.monotonic() - t1 < timeout_op:
        try:
            # timeout 取 900，与 z() 的默认值一致，不改既有轮询行为
            st, perr = z_raw("z_getoperationstatus", [[opid]], timeout=900)
        except _TRANSPORT_EXC as e:
            # 已拿到 opid = 确定已受理，故 submit_state=submitted（超时不得重发）
            raise TransportError("stage=status_poll 传输层异常: %s" % type(e).__name__,
                                 stage="status_poll", raw_transport=_transport_detail(e),
                                 z_sendmany_invoked=True, submit_state="submitted",
                                 opid=opid, method="z_getoperationstatus")
        if perr:
            raise RpcCallError("stage=status_poll RPC 错误: %s" % _rpc_brief(perr),
                               stage="status_poll", raw_error=perr, z_sendmany_invoked=True,
                               submit_state="submitted", opid=opid,
                               method="z_getoperationstatus")
        rec = st[0] if isinstance(st, list) else st
        if not isinstance(rec, dict):
            raise TransportError("stage=status_poll 响应结构异常（非 dict）",
                                 stage="status_poll", z_sendmany_invoked=True,
                                 submit_state="submitted", opid=opid)
        s = rec.get("status")
        if s == "success":
            t_pipeline = (time.monotonic() - t1) * 1000.0
            return t_submit, t_pipeline, opid, rec.get("result") or {}
        if s == "failed":
            raise RpcCallError("stage=opid_failed 操作终态失败: %s"
                               % _rpc_brief(rec.get("error")),
                               stage="opid_failed", raw_error=rec.get("error"),
                               z_sendmany_invoked=True, submit_state="submitted",
                               opid=opid, method="z_getoperationstatus")
        time.sleep(0.02)
    raise PreTxError("stage=opid_timeout 轮询超时 %ds（opid=%s, policy=%s）"
                     % (timeout_op, opid, policy),
                     stage="opid_timeout", z_sendmany_invoked=True,
                     submit_state="submitted", opid=opid)


# ---------------------------------------------------------------------------
# 收款地址准备：显式 diversifier index 派生 + L1/L1.5/L2 校验
#
# 设计依据：experiments/metadata/sapling_e2e_recipient_derivation_patch_design_20261030.md
# 三条不可退让的边界：
#   1) 地址准备必须在交易构造之前完成，失败即返回失败行，绝不调用 z_sendmany；
#   2) 只有白名单内的 -4 才顺延，其余错误立即抛出（fail-closed）；
#   3) 预算耗尽后不得用旧地址/重复地址兜底，宁可让该轮失败。
# ---------------------------------------------------------------------------
def z_raw(method, params, timeout=60):
    """调用钱包 RPC 并保留结构化错误：返回 (result, error_dict)，不抛异常。"""
    d = _post(ZA[0], ZA[1], {"jsonrpc": "2.0", "method": method,
                             "params": params, "id": 1}, zauth(), timeout)
    return d.get("result"), d.get("error")


def account_unified_addresses():
    """读 listaddresses，返回 (最大 diversifier_index, 账户 unified 地址集合)。

    起点不用常量（探测已把 10^12 用掉，且快照换了常量就失效），也不用钱包 DB
    （会新增 schema 依赖）。改用 listaddresses 的实测最大值 + 1。

    **起点不保证逐轮可复现**（2026-10-30 实测，见
    sapling_e2e_recipient_patch_verification_20261030.md）：快照恢复会让
    addresses 表回到 38 行、listaddresses 的最大 index 也回到归档值
    （4610582439），但 z_getaddressforaccount 的**无参派生游标不受恢复约束** ——
    两次相同恢复后无参派生分别得到 4610657118 / 4610657129，单调上升，机制未定位。
    因此每轮起点会被 sender 的 sapling_ua() 抬着走，实际 index 逐轮不同；
    这**不影响测量**（index 不参与构造与计时），但报告不得声称「每轮钱包状态完全一致」。

    起点精度也不承担安全性：即使起点偏低，撞上「已被其它 receiver 组合占用」
    也会命中白名单被跳过。

    数据缺失 / 类型异常 / 地址重复一律抛错，**不静默回退到 index 0**（探测已证明
    index 0/1/2 都不能用）。注意：不校验 index 唯一性——同一 index 合法地可能对应
    不同 receiver 组合（正是「already generated with different receiver types」
    那一类），断言唯一性会把正常数据误判为损坏；只把「地址字符串重复」当异常。
    """
    res, err = z_raw("listaddresses", [])
    if err is not None:
        raise RecipientDerivationError(
            "listaddresses 失败: %s" % json.dumps(err, ensure_ascii=False)[:200])
    if not isinstance(res, list):
        raise RecipientDerivationError(
            "listaddresses 返回类型异常: %s" % type(res).__name__)
    idxs = []
    addrs = []
    for grp in res:
        if not isinstance(grp, dict):
            continue
        for acc in (grp.get("unified") or []):
            for e in (acc.get("addresses") or []):
                di = e.get("diversifier_index") if isinstance(e, dict) else None
                a = e.get("address") if isinstance(e, dict) else None
                if (not isinstance(di, int)) or isinstance(di, bool) \
                        or di < 0 or di > INDEX_DOMAIN_MAX:
                    raise RecipientDerivationError(
                        "addresses 条目的 diversifier_index 非法: %r" % (di,))
                if not isinstance(a, str) or not a:
                    raise RecipientDerivationError("addresses 条目缺少 address")
                idxs.append(di)
                addrs.append(a)
    if not idxs:
        raise RecipientDerivationError("listaddresses 未返回任何 unified 地址")
    uniq = set(addrs)
    if len(uniq) != len(addrs):
        raise RecipientDerivationError(
            "listaddresses 存在重复地址记录（%d 条 / %d 唯一）"
            % (len(addrs), len(uniq)))
    return max(idxs), uniq


def derive_sapling_recipient(start_index, max_attempts, account=0):
    """从 start_index 起顺延，返回 (address, used_index, receiver_types, attempts)。

    只有 DERIVE_RETRYABLE_PATTERNS 命中的 -4 才顺延；其它任何错误（含 gap-limit
    类、-5/-8、未知 code）立即抛错——把未知错误当「无效 index」会静默吞掉真实的
    环境故障，并可能让重试朝错误方向烧完预算。
    """
    idx = start_index
    attempts = 0
    last_err = None
    while attempts < max_attempts:
        if idx > INDEX_DOMAIN_MAX:
            raise RecipientDerivationError(
                "diversifier index 越界（%d > 2^88-1）" % idx, attempts)
        attempts += 1
        res, err = z_raw("z_getaddressforaccount", [account, ["sapling"], idx])
        if err is None:
            addr = res.get("address") if isinstance(res, dict) else res
            rts = res.get("receiver_types") if isinstance(res, dict) else None
            if not addr:
                raise RecipientDerivationError(
                    "派生返回缺少 address: %s" % json.dumps(res, ensure_ascii=False)[:160],
                    attempts)
            rts = list(rts) if rts else ["sapling"]
            if rts != ["sapling"]:
                raise RecipientDerivationError(
                    "派生返回的 receiver_types 非 sapling-only: %r" % (rts,), attempts)
            return addr, idx, rts, attempts
        last_err = err
        code = err.get("code") if isinstance(err, dict) else None
        msg = str(err.get("message", "")) if isinstance(err, dict) else str(err)
        if code == -4 and any(p in msg for p in DERIVE_RETRYABLE_PATTERNS):
            idx += 1
            continue
        raise RecipientDerivationError(
            "派生失败（不可恢复）index=%d code=%s msg=%s"
            % (idx, code, msg[:160]), attempts)
    raise RecipientDerivationError(
        "派生预算耗尽：%d 次尝试仍未取到可用 index（最后错误 %s）"
        % (attempts, json.dumps(last_err, ensure_ascii=False)[:160] if last_err else "-"),
        attempts)


def prepare_recipients(n_recip, sender=None, budget=DERIVE_ATTEMPT_BUDGET):
    """为 n_recip 个 Output 准备收款地址，返回 dict（含可落盘的溯源字段）。

    顺序：派生 → L1 去重 → L1.5 归属一致性 → L2 Sapling-only。任一步失败即抛
    RecipientError 的子类，调用方在构造交易前返回失败行。
    """
    start_idx, _ = account_unified_addresses()
    next_idx = start_idx + 1
    picked = []                       # [(address, index, receiver_types)]
    attempts = 0
    while len(picked) < n_recip:
        remaining = budget - attempts
        if remaining <= 0:
            raise RecipientDerivationError(
                "派生预算耗尽（%d/%d 次，已派生 %d/%d 个地址）"
                % (attempts, budget, len(picked), n_recip), attempts)
        addr, used_idx, rts, att = derive_sapling_recipient(next_idx, remaining)
        attempts += att
        picked.append((addr, used_idx, rts))
        next_idx = used_idx + 1       # 同一 index 不重复请求（幂等但无意义）

    addrs = [x[0] for x in picked]

    # L1：地址必须互不相同（纯本地判定，不依赖 RPC，是最后兜底）
    if len(set(addrs)) != n_recip:
        raise RecipientValidationError(
            "L1 失败：收款地址不唯一（%d 个地址 / %d 唯一）"
            % (len(addrs), len(set(addrs))), attempts)

    # L1.5：重新读一次 listaddresses，确认这些地址确实已被本钱包持久化且属于账户
    # unified 集合。这是「钱包账户地址集合一致性检查」，**不是**密码学意义上的
    # 地址所有权证明，报告措辞不得升级。
    _, owned = account_unified_addresses()
    missing = [a for a in addrs if a not in owned]
    if missing:
        raise RecipientValidationError(
            "L1.5 失败：%d/%d 个收款地址不在账户 unified 集合中"
            % (len(missing), len(addrs)), attempts)

    # L2：z_listunifiedreceivers 能解析且 receiver 集合严格为 {sapling}
    # （validateaddress 对合法 UA 也返回 isvalid=false，不可用）
    for a in addrs:
        res, err = z_raw("z_listunifiedreceivers", [a])
        if err is not None:
            raise RecipientValidationError(
                "L2 失败：地址无法解析 %s… (%s)"
                % (a[:24], json.dumps(err, ensure_ascii=False)[:120]), attempts)
        if not isinstance(res, dict) or set(res.keys()) != {"sapling"}:
            raise RecipientValidationError(
                "L2 失败：receiver 集合非 sapling-only: %r"
                % (sorted(res.keys()) if isinstance(res, dict) else res,), attempts)

    return {
        "recipients": addrs,
        "div_indices": [x[1] for x in picked],
        "receiver_types": ["+".join(x[2]) for x in picked],
        "derivation_attempts": attempts,
        "validation": "L1+L1.5+L2",
    }


def _addr_hash(addr):
    """地址的可追溯标识：sha256 前 16 位十六进制（CSV 不落完整地址）。"""
    return hashlib.sha256(addr.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 单轮
# ---------------------------------------------------------------------------
def run_one(idx, S, O, policy, mine_blocks, dry_run, state, from_ua):
    """对目标 (S,O) 执行一轮；返回 (row, T) 或 (row_with_error, None)。"""
    row = {"round": idx, "target_spend": S, "target_output": O}
    # 透传恢复态核验结果（硬阻断项均已在 verify_state 校验过）
    row["restored_height"] = state.get("restored_height")
    row["restored_note_count"] = state.get("restored_note_count")
    row["snapshot_sha256"] = state.get("snapshot_sha256")
    row["restore_script_sha256"] = state.get("restore_script_sha256")
    pick = state["pick"]
    n_recip = max(1, pick["n_recip"])
    amount_zec = pick["amount_zat"] / 1e8
    print("\n----- round %d | 目标 (S=%d,O=%d) policy=%s -----" % (idx, S, O, policy))

    # 收款地址必须在交易构造之前准备：n_recip 个**互不相同**的 Sapling-only UA
    # （配 1 个找零 → 实际 O 输出）。派生/校验失败即返回失败行：不构造、不发送、
    # 不产生 txid，failure_class 显式标注失败阶段。
    try:
        prep = prepare_recipients(n_recip, from_ua)
    except RecipientError as e:
        row["recipients"] = n_recip
        row["recipient_count"] = n_recip
        row["derivation_attempts"] = e.attempts
        row["failure_class"] = e.cls
        row["recipient_validation"] = "failed"
        row["error"] = str(e)[:300]
        # 证据留档：prepare 阶段失败也必须进 sidecar（否则「sidecar 行数 == 失败轮数」不成立）
        _emit_failure(idx, S, O, e.cls, e, extra={"recipients": n_recip, "policy": policy},
                      stage="prep", submit_state="not_submitted", z_sendmany_invoked=False)
        print("  [fail] 收款地址准备失败（%s，已尝试 %d 次）: %s"
              % (e.cls, e.attempts, row["error"]))
        return row, None
    recipients = prep["recipients"]
    row["recipients"] = n_recip
    row["recipient_count"] = n_recip
    row["diversifier_indices"] = ";".join(str(i) for i in prep["div_indices"])
    row["recipient_addresses_hash"] = ";".join(_addr_hash(a) for a in recipients)
    row["recipient_receivers"] = ";".join(prep["receiver_types"])
    row["derivation_attempts"] = prep["derivation_attempts"]
    row["recipient_validation"] = prep["validation"]
    print("  收款地址数=%d（含 1 找零→实际 O 输出）目标总额=%.6f ZEC 手续费预留=%d zat"
          % (n_recip, amount_zec, pick["fee_zat"]))
    print("  收款地址 index=%s 派生尝试=%d 校验=%s"
          % (row["diversifier_indices"], row["derivation_attempts"],
             row["recipient_validation"]))

    wt, target, sec = wait_sync()
    if wt is None:
        raise PreTxError("stage=sync 前置同步超时", stage="sync",
                         z_sendmany_invoked=False, submit_state="not_submitted")

    amounts = build_amounts(recipients, amount_zec)
    row["planned_amount_zat"] = pick["amount_zat"]
    row["expected_fee_zat"] = pick["fee_zat"]
    row["recipients"] = n_recip

    if dry_run:
        print("  [dry-run] 不实际发交易（已恢复+核验+选定金额）")
        print("  [dry-run] 已覆盖：L1 去重 / L1.5 账户地址集合一致性 / L2 Sapling-only"
              "（%d 个收款地址）" % n_recip)
        print("  [dry-run] 未覆盖：L3（z_sendmany 是否接受该多地址组合）——"
              "本次运行不构成形态可行性证据")
        row.update({"dry_run": 1,
                    "note_count": state.get("restored_note_count"),
                    "restored_height": state.get("restored_height")})
        return row, None

    bal0 = sapling_zat()
    t_round = time.monotonic()
    try:
        ts, tp, opid, res = send_frozen(from_ua, amounts, policy)
    except PreTxError as e:
        row["error"] = str(e)[:300]
        row["failure_class"] = _classify(e)
        # 先写 sidecar 再返回（CSV 由主循环末尾统一落盘，故此处证据必然先落盘）
        _emit_failure(idx, S, O, row["failure_class"], e,
                      extra={"recipients": recipients,
                             "amounts_zat": [int(round(x["amount"] * 1e8)) for x in amounts],
                             "policy": policy, "from_ua": from_ua})
        print("  [fail] %s" % row["error"])
        return row, None

    txid = res.get("txid")
    row["policy"] = policy
    row["txid"] = txid
    row["opid"] = opid
    row["submit"] = "%.1f" % ts
    row["pipeline"] = "%.1f" % tp
    print("  submit   %8.1f ms  pipeline %8.1f ms  txid=%s" % (ts, tp, (txid or "?")[:16]))

    h0 = height()
    nb, tm = advance(mine_blocks)
    mine_ms = tm * 1000.0
    print("  mine     %8.1f ms  +%d 块 -> %s" % (mine_ms, nb, height()))

    wt2, target2, sec2 = wait_sync()
    sync_ms = sec2 * 1000.0
    print("  后置同步 wallet=%s 目标=%s（%.1fs）" % (wt2, target2, sec2))

    try:
        info = view_tx(txid) if txid else {}
    except RuntimeError as e:
        print("  [warn] z_viewtransaction 失败: %s" % str(e)[:160])
        info = {}
    row["sapling_spends"] = info.get("spends")
    row["sapling_outputs"] = info.get("outputs")
    if info.get("spends") is not None:
        row["sapling_proofs"] = (info["spends"] or 0) + (info["outputs"] or 0)
    fee_zat = info.get("fee_zat") if info.get("fee_zat") else res.get("fee_zat")
    row["fee_zat"] = fee_zat
    row["tx_size"] = tx_size(txid) if txid else None

    # 形态与手续费匹配判定（预注册 §6：实际形态由 z_viewtransaction 决定，不以命令参数为准）
    aS = info.get("spends")
    aO = info.get("outputs")
    row["actual_spend"] = aS
    row["actual_output"] = aO
    row["form_match"] = (aS == S and aO == O)
    row["fee_match"] = (fee_zat is not None and fee_zat == pick["fee_zat"])
    print("  实际形态 spends=%s outputs=%s (目标 %d,%d) form_match=%s fee_match=%s"
          % (aS, aO, S, O, row["form_match"], row["fee_match"]))

    bal1 = sapling_zat()
    total_ms = (time.monotonic() - t_round) * 1000.0
    row["mine"] = "%.1f" % mine_ms
    row["sync"] = "%.1f" % sync_ms
    row["total"] = "%.1f" % total_ms
    row["fee_measured_zat"] = (bal0 - bal1) if (bal0 and bal1) else None
    print("  本轮墙钟 %8.1f ms" % total_ms)
    T = {"submit": ts, "pipeline": tp, "mine": mine_ms, "sync": sync_ms, "total": total_ms}
    return row, T


# failure_class 取值（冻结稿 §4.5）。T3 若决定保留旧名 `timeout`，只需改此处一处。
CLS_OPID_TIMEOUT = "opid_timeout"

# 资金不足措辞：`-4`/`-6` 都必须**同时**命中措辞才判资金不足（§2.2 双条件）。
# 仅凭 code 不足：`-6` 在码表是 WalletInsufficientFunds，但资金不足也可能经
# propose_transfer 失败映射为 `-4`；反之 `-4` 也可能是别的钱包错误。
_FUNDS_MSG_PATTERNS = ("insufficient funds", "insufficient balance", "insufficient",
                       "not enough funds", "not enough", "no spendable")

# 隐私策略拒绝的措辞：优先用事件码；否则要求「privacy policy」**且**带否定措辞。
# 关键反例：「Invalid parameter, unknown privacy policy: FooPolicy」是参数错误，
# 不能因为含 "privacy policy" 就判策略拒绝（§6.2 反向用例）。
_PRIVPOL_EVENT_PATTERNS = ("err-privpol",)
_PRIVPOL_NEGATION = ("not allowed", "not permitted", "disallowed")


def _is_funds_msg(msg):
    return any(p in msg for p in _FUNDS_MSG_PATTERNS)


def _is_privpol_msg(msg):
    if any(p in msg for p in _PRIVPOL_EVENT_PATTERNS):
        return True
    return ("privacy policy" in msg) and any(k in msg for k in _PRIVPOL_NEGATION)


def _map_code(code, msg):
    """第 2 层：error code 表驱动。msg 已 lower()，仅用于 -8 子类与 -4/-6 双条件。"""
    if code == -8:
        if "duplicated recipient address" in msg:
            # 事实层标签：仅陈述「重复收款地址导致 RPC 拒绝」。
            # 「执行器未去重」是解释层结论，须由 recipients 字段另行证明（§4.10）。
            return "rpc_duplicated_recipient"
        if _is_privpol_msg(msg):
            return "rpc_privacy_policy_rejected"
        return "rpc_invalid_parameter"
    if code in (-4, -6):
        if _is_funds_msg(msg):
            return "rpc_insufficient_funds"
        # -4 其余为钱包错误；-6 未命中措辞时**保留原码**，不猜语义
        return "rpc_wallet_error" if code == -4 else "rpc_error_%d" % code
    if code == -5:
        return "rpc_invalid_address_or_key"
    if code == -32602:
        return "rpc_request_schema_invalid"
    # 未知码保留原码，事后可无损重分类（§4.5）
    return "rpc_error_%d" % code


def _text_fallback(raw):
    """第 3 层：仅在**无 code、非传输、非超时**时使用。

    与旧实现的差别只有一处：**策略拒绝不参与文本兜底** —— 没有 code 就不得标
    policy_rejected，这正是 F5 的根因。
    """
    low = raw.lower()
    if "同步" in raw:
        return "env_transient_sync"
    if "timeout" in low or "超时" in raw:
        return CLS_OPID_TIMEOUT
    if "failed" in low:
        return "opid_terminal_failed"
    if "note" in low or "insufficient" in low or "金额" in raw:
        return "insufficient_notes"
    return "other"


def _classify(err):
    """失败 → `failure_class`（三层：阶段 → code → 文本），只输出**事实层**标签。

    参数可为异常对象（首选，携带结构化事实）或字符串（旧调用，仅文本层可用）。

    第 1 层 阶段判别不看文本：`opid_timeout` / 传输异常直接定性，
            彻底消灭「轮询超时因括号里带 policy 被判成策略拒绝」这类误判。
    第 2 层 code 表（`_map_code`），未知码保留原码。
    第 3 层 仅当无 code 时退回文本，且不产出「策略拒绝」。

    与 §4.5 的两处必要衔接（均由冻结稿其它条款要求，已在此显式实现）：
      - `opid` 终态失败仍记 `opid_terminal_failed`（§6.4 R2「不变」），
        但 code ∈ {-4,-6} 且命中资金措辞时上移为 `rpc_insufficient_funds`
        （修正 §3 表格里标记为「△ 资金语义丢失」的那一行）；
      - `stage=submit/status_poll` 却无 code 也无传输异常 = 响应不可用，
        按 `rpc_transport_error` 处理（与 send_frozen 的 unknown 判定一致）。
    """
    if not isinstance(err, BaseException):
        return _text_fallback(str(err))

    stage = getattr(err, "stage", None)
    # ---- 第 1 层：阶段 ----
    if stage == "opid_timeout":
        return CLS_OPID_TIMEOUT
    if getattr(err, "raw_transport", None) is not None:
        return "rpc_transport_error"

    code = getattr(err, "code", None)
    msg = str(getattr(err, "rpc_message", None) or "").lower()

    if stage == "opid_failed":
        if code in (-4, -6) and _is_funds_msg(msg):
            return "rpc_insufficient_funds"
        return "opid_terminal_failed"

    # ---- 第 2 层：code ----
    if code is not None:
        return _map_code(code, msg)

    if stage in ("submit", "status_poll"):
        return "rpc_transport_error"

    # ---- 第 3 层：文本兜底 ----
    return _text_fallback(str(err))


# ---------------------------------------------------------------------------
# sidecar：errors.jsonl（未截断的失败证据）
# ---------------------------------------------------------------------------
_SIDECAR = {"path": None, "run_id": None, "replaces": None, "rows": 0}


def init_sidecar(rundir, replaces=None):
    """初始化 sidecar 会话，必须在主循环之前调用。"""
    _SIDECAR.update({"path": os.path.join(rundir, "errors.jsonl"),
                     "run_id": os.path.basename(str(rundir).rstrip("/\\")),
                     "replaces": replaces, "rows": 0})
    return _SIDECAR["path"]


def _sidecar_open_append():
    """单列成函数，便于自检脚本注入写入失败（S5）。"""
    return open(_SIDECAR["path"], "a", encoding="utf-8")


def _emit_failure(idx, S, O, cls, err=None, extra=None,
                  stage=_UNSET, submit_state=_UNSET, z_sendmany_invoked=_UNSET):
    """追加一条失败证据并 flush；**写入失败即终止实验**（§4.9 条件 3）。

    `_UNSET` 与 `None` 语义不同：`None` 表示「事实未知、如实留空」，
    `_UNSET` 表示「未显式覆盖，从异常对象推导」。
    """
    if not _SIDECAR.get("path"):
        raise SystemExit("[fatal] sidecar 未初始化：拒绝在不留失败证据的情况下继续")
    run_id = _SIDECAR["run_id"]
    st = getattr(err, "stage", None) if stage is _UNSET else stage
    ss = getattr(err, "submit_state", None) if submit_state is _UNSET else submit_state
    inv = getattr(err, "z_sendmany_invoked", None) if z_sendmany_invoked is _UNSET \
        else z_sendmany_invoked
    rec = {
        "attempt_id": "%s:%d" % (run_id, idx),   # §4.2 唯一关联键，不用行号
        "run_id": run_id,
        "round": idx,
        "target_spend": S,
        "target_output": O,
        "failure_class": cls,
        "stage": st,
        "code": getattr(err, "code", None),
        "raw_error": getattr(err, "raw_error", None),          # 原对象，未截断
        "raw_transport": getattr(err, "raw_transport", None),  # 类型 + repr + errno
        "rpc_message": getattr(err, "rpc_message", None),
        "method": getattr(err, "method", None),
        "submit_state": ss,
        "z_sendmany_invoked": bool(inv) if inv is not None else None,
        "opid": getattr(err, "opid", None),
        # 仅供对照，**不得**作为分类依据（旧实现用它做过判定，这正是缺陷来源）
        "wrapper_text": None if err is None else str(err),
        "replaces": _SIDECAR.get("replaces"),
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    for k, v in (extra or {}).items():
        rec.setdefault(k, v)
    try:
        f = _sidecar_open_append()
        try:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            f.close()
    except OSError as e:
        raise SystemExit("[fatal] sidecar 写入失败，拒绝继续实验（失败证据会丢失）: %r" % (e,))
    _SIDECAR["rows"] += 1
    return rec


def replacement_allowed(rec):
    """G5：只有能证明「未触及提交阶段」的失败才允许人工替换（每形态上限 1 次）。

    - `submit_state=unknown`：可能已受理 → 不可替换（G4）；
    - `submit_state=submitted`：已受理 → 不可替换，也不得重发；
    - `z_sendmany_invoked=True`：被 RPC 拒绝 → 不得重试（G3）；
    - 仅 `not_submitted` 且 `invoked=False` → 可替换（仍须人工确认并留痕）。
    """
    if rec.get("submit_state") != "not_submitted":
        return False
    return not rec.get("z_sendmany_invoked")


def fail_row(idx, S, O, cls, msg, err=None):
    """构造失败行；**先写 sidecar 再返回**（fail-closed，§4.9 条件 3）。"""
    row = {"round": idx, "target_spend": S, "target_output": O,
           "error": str(msg)[:300], "failure_class": cls}
    _emit_failure(idx, S, O, cls, err)
    return row


def _summary_note(rows, tx_ok, allm, dry_run):
    """生成汇总表 note：**按 failure_class 的实际阶段描述，不凭「无 txid」推断原因**。

    三类必须分开，否则汇总会把工具缺陷读成实验结论：
      - `recipient_*`：收款地址准备失败 —— 发生在构造之前，没有构造、没有发送，
        **不能**读成"该形态不可行"（门禁 run_20261030_110042 就是这么被误读的）；
      - 其它 failure_class：构造/发送/状态阶段失败 —— 按实际类别列出，不笼统归因；
      - dry-run：没有 txid 是预期，但仍须报告地址准备与构造是否完成。

    本函数只影响 note 文案；tx_success / form_match / fee_match / all_match 的
    统计口径在上层，不经过这里。
    """
    if tx_ok:
        if allm:
            return ""
        return "成功构造但形态或手续费不符，未计入有效样本"

    recip = [r for r in rows if str(r.get("failure_class") or "").startswith("recipient_")]
    other = [r for r in rows if r.get("failure_class")
             and not str(r.get("failure_class")).startswith("recipient_")]
    built = [r for r in rows if not r.get("failure_class") and not r.get("txid")]

    parts = []
    if recip:
        cls_desc = "/".join(sorted({str(r.get("failure_class")) for r in recip}))
        parts.append("收款地址准备失败 %d 条（%s）：发生在构造之前，未构造、未发送，"
                     "不代表该形态不可行" % (len(recip), cls_desc))
    if other:
        cls_desc = "/".join(sorted({str(r.get("failure_class")) for r in other}))
        seg = ("交易构造/发送阶段失败 %d 条（%s），未产生 txid"
               % (len(other), cls_desc))
        # §4.7：重复收款地址只陈述事实，**不写**「执行器未去重」这类解释层结论
        if any(str(r.get("failure_class")) == "rpc_duplicated_recipient" for r in other):
            seg += "；其中重复收款地址导致 RPC 拒绝，不代表该形态不可行"
        parts.append(seg)
    if dry_run and built:
        parts.append("dry-run：地址准备与构造已完成，未发交易（无 txid 属预期；"
                     "L3 未覆盖，不构成形态可行性证据）")
    if not parts:
        return "无成功构造（形态不可行或环境/策略失败）"
    return "；".join(parts)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def preflight():
    """预检环境，并返回**运行开始时**的实际快照/脚本 SHA256（供 meta.json 自描述）。

    这些值必须在运行开始即确定并写入 meta.json，不能等运行结束后从 rounds.csv
    反向推断 —— 否则一旦中途崩溃或只写了一半，meta 就失去溯源能力。
    """
    if not os.path.isfile(SNAPSHOT_WSL):
        raise RuntimeError("快照不存在: %s" % SNAPSHOT_WSL)
    if not os.path.isfile(RESTORE_SCRIPT):
        raise RuntimeError("恢复脚本不存在: %s" % RESTORE_SCRIPT)
    snap_actual = sha256_file(SNAPSHOT_WSL)
    script_actual = sha256_file(RESTORE_SCRIPT)
    print("[preflight] 快照=%s\n           恢复脚本=%s" % (SNAPSHOT_WSL, RESTORE_SCRIPT))
    print("[preflight] 快照 SHA256=%s（与冻结值一致=%s）"
          % (snap_actual, snap_actual == SNAPSHOT_SHA256))
    print("[preflight] 脚本 SHA256=%s（与冻结值一致=%s）"
          % (script_actual, script_actual == RESTORE_SCRIPT_SHA256))
    # A′：钱包 DB schema 预检（若 DB 尚不存在则由快照恢复创建，恢复后强制断言）
    if os.path.isfile(WALLET_DB_PATH):
        assert_wallet_db_schema()
        print("[preflight] 钱包 DB schema OK: %s" % WALLET_DB_PATH)
    else:
        print("[preflight][warn] 钱包 DB 暂不存在（将由快照恢复创建），恢复后强制断言: %s"
              % WALLET_DB_PATH)
    return {"snapshot_sha256": snap_actual,
            "snapshot_sha256_match": snap_actual == SNAPSHOT_SHA256,
            "restore_script_sha256": script_actual,
            "restore_script_sha256_match": script_actual == RESTORE_SCRIPT_SHA256}


def write_meta_json(rundir, meta):
    """原子感写入 meta.json（临时文件 + 替换），避免半截文件。"""
    path = os.path.join(rundir, "meta.json")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, default=str, ensure_ascii=False)
    os.replace(tmp, path)


def verify_run_artifacts(rundir):
    """校验 sidecar 与主 CSV 的一致性（§4.9 条件 2/3），不满足即 SystemExit。

    三项：① errors.jsonl 每行可解析 ② attempt_id 双向齐全且不重复
          ③ sidecar 行数 == 失败轮数。

    注：本项目**没有** `final_check.py`（那是另一项目的脚本），校验一律在这里
    与 `failure_class_selftest.py` 完成。
    """
    rpath = os.path.join(rundir, "rounds.csv")
    spath = os.path.join(rundir, "errors.jsonl")
    run_id = os.path.basename(str(rundir).rstrip("/\\"))

    fails = []
    with open(rpath, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("failure_class"):
                fails.append("%s:%d" % (run_id, int(r["round"])))

    recs = []
    if os.path.isfile(spath):
        with open(spath, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except ValueError as e:
                    raise SystemExit("[fatal] errors.jsonl 第 %d 行不可解析: %s" % (i, e))

    ids = [r.get("attempt_id") for r in recs]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup:
        raise SystemExit("[fatal] errors.jsonl 中 attempt_id 重复: %s" % dup)
    a, b = set(fails), set(ids)
    if a != b:
        raise SystemExit("[fatal] sidecar 与失败行不一一对应："
                         "缺 sidecar=%s；多 sidecar=%s" % (sorted(a - b), sorted(b - a)))
    if len(recs) != len(fails):
        raise SystemExit("[fatal] sidecar 行数 %d != 失败轮数 %d" % (len(recs), len(fails)))
    return {"failure_rows": len(fails), "sidecar_rows": len(recs)}


COLUMNS = ["round", "target_spend", "target_output", "actual_spend", "actual_output",
           "form_match", "fee_match", "policy", "txid", "opid",
           "submit", "pipeline", "mine", "sync", "total",
           "sapling_spends", "sapling_outputs", "sapling_proofs", "tx_size",
           "fee_zat", "expected_fee_zat", "planned_amount_zat", "recipients",
           "restored_height", "restored_note_count",
           "snapshot_sha256", "restore_script_sha256",
           "dry_run", "failure_class", "error",
           # --- 多收款地址派生的溯源列（一律追加在末尾，不重排既有列）---------
           # 旧分析脚本（analyze_sapling_cost.py / fit_sapling_e2e_model.py）均用
           # csv.DictReader，追加列不影响既有字段读取。
           "recipient_count",          # 收款地址数（与 recipients 同值，保留旧列名兼容）
           "diversifier_indices",      # 实际使用的 index，分号分隔，可复现
           "recipient_addresses_hash",  # sha256(address)[:16]，分号分隔，不落完整地址
           "recipient_receivers",      # 逐地址 receiver 组成，L2 的持久证据
           "derivation_attempts",      # 该轮消耗的派生尝试次数（含被跳过的无效 index）
           "recipient_validation"]     # L1/L1.5/L2 结果；失败时为 failed


def do_one_attempt(idx, S, O, policy, mine_blocks, dry_run, restore,
                   allow_hash_mismatch, allow_script_mismatch, allow_height_mismatch):
    """执行一次尝试：恢复+核验+构造。返回 (row, T) 或抛异常（调用方分类处理）。"""
    if restore:
        snap_sha, script_sha = restore_snapshot(allow_hash_mismatch, allow_script_mismatch)
        state = verify_state(snap_sha, script_sha, S, O, allow_height_mismatch)
    else:
        # 跳过快照恢复（违反预注册 §6，仅在已确认环境干净时使用）
        print("[!] --no-restore：跳过恢复（违反预注册 §6）")
        h = height()
        inv = note_inventory()
        state = {"restored_height": h, "restored_note_count": len(inv) if inv else None,
                 "restored_sapling_zat": sapling_zat(),
                 "snapshot_sha256": None, "restore_script_sha256": None,
                 "pick": pick_amount_zat(S, O, inv) if inv else None}
        if state["pick"] is None:
            raise StateError("无恢复模式下无法为 (S=%d,O=%d) 构造金额" % (S, O))
    from_ua = sapling_ua()                  # 恢复后才派生，确保取自恢复后钱包
    return run_one(idx, S, O, policy, mine_blocks, dry_run, state, from_ua)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--matrix", default=None, help="CSV: 两列 S,O；缺省用预注册 §4 的 10 形态")
    p.add_argument("--mode", choices=["gate", "confirm"], default="gate")
    p.add_argument("--policy", default=FROZEN_POLICY)
    p.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS_PER_FORM)
    p.add_argument("--target-success", type=int, default=TARGET_SUCCESS_PER_FORM)
    p.add_argument("--mine-blocks", type=int, default=2)
    p.add_argument("--outdir-base", default=OUTDIR_BASE)
    p.add_argument("--seed", type=int, default=PRE_REG_SEED)
    p.add_argument("--dry-run", action="store_true",
                   help="只做恢复+核验+选金额+打印计划，不实际发交易（仍会调用快照恢复）")
    p.add_argument("--allow-hash-mismatch", action="store_true")
    p.add_argument("--allow-script-mismatch", action="store_true")
    p.add_argument("--allow-height-mismatch", action="store_true")
    p.add_argument("--no-restore", action="store_true",
                   help="跳过快照恢复（仅在已确认环境干净时使用；违反预注册 §6，慎用）")
    p.add_argument("--replaces", default=None, metavar="ATTEMPT_ID",
                   help="人工替换：被替换的原 attempt_id（<run_id>:<round>）。"
                        "脚本内不自动重试，替换须单独授权并独立 run 目录（§10）")
    a = p.parse_args()

    if a.replaces and ":" not in a.replaces:
        raise SystemExit("[fatal] --replaces 必须是 <run_id>:<round> 形式的 attempt_id")

    matrix = DEFAULT_MATRIX
    if a.matrix:
        matrix = []
        with open(a.matrix, newline="") as f:
            for r in csv.reader(f):
                if not r or r[0].startswith("#"):
                    continue
                matrix.append((int(r[0]), int(r[1])))

    pf = preflight()
    ts = time.strftime("%Y%m%d_%H%M%S")
    if a.mode == "gate":
        rundir = os.path.join(a.outdir_base, "_feasibility_gate", "run_" + ts)
    else:
        rundir = os.path.join(a.outdir_base, "run_" + ts)
    os.makedirs(rundir, exist_ok=True)
    tee_stdio(os.path.join(rundir, "run.log"))
    print("[log]", os.path.join(rundir, "run.log"))
    print("[argv]", " ".join(sys.argv))
    print("[mode]", a.mode, "policy=", a.policy, "dry_run=", a.dry_run, "restore=", not a.no_restore)
    # sidecar 在首次失败前就绪；写入失败即终止（§4.9 条件 3）
    print("[sidecar]", init_sidecar(rundir, a.replaces),
          "replaces=%s" % (a.replaces or "-"))

    # ---- meta.json：运行开始即写入自描述基线 ----
    # dry_run 必须是显式布尔：正式模式（dry_run=False）绝不能因为字段缺失/默认值
    # 而被误读成 dry-run，反之亦然。
    if not isinstance(a.dry_run, bool):
        raise SystemExit("[fatal] dry_run 必须是显式布尔值（拒绝把缺失/默认值当成 dry-run）")
    meta = {"args": vars(a), "matrix": matrix, "mode": a.mode,
            "dry_run": bool(a.dry_run),
            "real_tx": not bool(a.dry_run),
            "restore_enabled": not a.no_restore,
            "policy_frozen": a.policy,
            "replaces": a.replaces,
            "sidecar": "errors.jsonl",
            "timestamp": ts,
            "snapshot_sha256": pf["snapshot_sha256"],
            "snapshot_sha256_expected": SNAPSHOT_SHA256,
            "snapshot_sha256_match": pf["snapshot_sha256_match"],
            "snapshot_target_height": SNAPSHOT_TARGET_HEIGHT,
            "restore_script_sha256": pf["restore_script_sha256"],
            "restore_script_sha256_expected": RESTORE_SCRIPT_SHA256,
            "restore_script_sha256_match": pf["restore_script_sha256_match"],
            "meta_stage": "run_start"}
    write_meta_json(rundir, meta)
    print("[meta] 运行开始基线已写入 meta.json: dry_run=%s mode=%s real_tx=%s snap=%s… script=%s…"
          % (meta["dry_run"], meta["mode"], meta["real_tx"],
             meta["snapshot_sha256"][:12], meta["restore_script_sha256"][:12]))

    pids = find_pids()
    sampler = Sampler(os.path.join(rundir, "memory_timeseries.csv"))
    sampler.start()

    rows = []
    attempts = {}
    successes = {}        # 有效成功（form_match & fee_match & txid）
    idx = 0
    try:
        if a.mode == "gate":
            # 门禁：每种形态 1 次探测；失败/不可行如实记录，不重试
            for (S, O) in matrix:
                attempts[(S, O)] = 1
                idx += 1
                try:
                    row, T = do_one_attempt(idx, S, O, a.policy, a.mine_blocks, a.dry_run,
                                            not a.no_restore, a.allow_hash_mismatch,
                                            a.allow_script_mismatch, a.allow_height_mismatch)
                except HeightMismatch as e:
                    rows.append(fail_row(idx, S, O, "state_height_mismatch", str(e)))
                    continue
                except SchemaMismatch:
                    raise          # schema 结构性错误：整轮中止，不按形态重试、不发送
                except StateError as e:
                    rows.append(fail_row(idx, S, O, "state_verification_failed", str(e)))
                    continue
                except PreTxError as e:
                    rows.append(fail_row(idx, S, O, _classify(e), str(e), e))
                    continue
                except Exception as e:
                    rows.append(fail_row(idx, S, O, "other", str(e)))
                    continue
                rows.append(row)
                if T is not None and row.get("txid") and row.get("form_match") and row.get("fee_match"):
                    successes[(S, O)] = 1
        else:
            # 正式：每种形态打乱顺序后逐格 campaign，最多 max_attempts 次尝试，
            # 达到 target 有效成功即停（预注册 §4/§6）。顺序随机化以避免「先小后大」偏差。
            form_order = sorted(set(matrix))
            random.Random(a.seed).shuffle(form_order)
            for (S, O) in form_order:
                valid = 0
                att = 0
                infeasible = False
                while valid < a.target_success and att < a.max_attempts:
                    att += 1
                    attempts[(S, O)] = att
                    idx += 1
                    try:
                        row, T = do_one_attempt(idx, S, O, a.policy, a.mine_blocks, a.dry_run,
                                                not a.no_restore, a.allow_hash_mismatch,
                                                a.allow_script_mismatch, a.allow_height_mismatch)
                    except HeightMismatch as e:
                        rows.append(fail_row(idx, S, O, "state_height_mismatch", str(e)))
                        infeasible = True
                        break
                    except SchemaMismatch:
                        raise          # schema 结构性错误：整轮中止，不按形态重试、不发送
                    except StateError as e:
                        rows.append(fail_row(idx, S, O, "state_verification_failed", str(e)))
                        if att >= a.max_attempts:
                            infeasible = True
                        continue
                    except PreTxError as e:
                        rows.append(fail_row(idx, S, O, _classify(e), str(e), e))
                        continue
                    except Exception as e:
                        rows.append(fail_row(idx, S, O, "other", str(e)))
                        continue
                    rows.append(row)
                    if T is not None and row.get("txid") and row.get("form_match") and row.get("fee_match"):
                        valid += 1
                successes[(S, O)] = valid
                if infeasible:
                    print("  [!] 形态 (S=%d,O=%d) 判定为不可行/状态异常" % (S, O))

        # ---- 落盘 rounds.csv ----
        with open(os.path.join(rundir, "rounds.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)

        # ---- 形式聚合 ----
        groups = {}
        for r in rows:
            k = (r.get("target_spend"), r.get("target_output"))
            if k[0] is None:
                continue
            groups.setdefault(k, []).append(r)
        summary_name = "gate_summary.csv" if a.mode == "gate" else "summary_by_shape.csv"
        with open(os.path.join(rundir, summary_name), "w", newline="") as f:
            w = csv.writer(f)
            if a.mode == "gate":
                w.writerow(["target_spend", "target_output", "attempts", "tx_success",
                            "form_match", "fee_match", "all_match", "actual_forms", "note"])
            else:
                w.writerow(["target_spend", "target_output", "attempts", "valid_success",
                            "form_match", "fee_match", "all_match", "actual_forms", "note"])
            for k in sorted(groups):
                g = groups[k]
                tx_ok = [x for x in g if x.get("txid")]
                fm = [x for x in tx_ok if x.get("form_match")]
                fem = [x for x in tx_ok if x.get("fee_match")]
                allm = [x for x in tx_ok if x.get("form_match") and x.get("fee_match")]
                actual = sorted({(x.get("actual_spend"), x.get("actual_output")) for x in tx_ok})
                # note 一律由 failure_class 等实际阶段信息推出，不用「有没有 txid」猜原因
                note = _summary_note(g, tx_ok, allm, a.dry_run)
                w.writerow([k[0], k[1], len(g), len(tx_ok), len(fm), len(fem), len(allm),
                            str(actual), note])

        # ---- 自洽性校验：dry_run 与数据必须一致，防止汇总被误读 ----
        n_txid = len([r for r in rows if r.get("txid")])
        if a.dry_run and n_txid:
            raise SystemExit("[fatal] dry_run=True 却出现 %d 条带 txid 的记录：拒绝写出可被误读的汇总" % n_txid)
        if (not a.dry_run) and meta.get("meta_stage") != "run_start":
            raise SystemExit("[fatal] 正式模式缺少运行开始基线，meta.json 不可信")

        # ---- 证据完整性：sidecar 必须覆盖全部失败轮（§4.9 条件 2/3）----
        art = verify_run_artifacts(rundir)
        print("[verify] 失败轮=%d sidecar 行=%d（attempt_id 双向一致）"
              % (art["failure_rows"], art["sidecar_rows"]))

        meta.update({"pids": pids,
                     "failure_rows": art["failure_rows"],
                     "sidecar_rows": art["sidecar_rows"],
                     "attempts_per_form": {("%d,%d" % k): v for k, v in attempts.items()},
                     "valid_successes_per_form": {("%d,%d" % k): v for k, v in successes.items()},
                     "rows_total": len(rows),
                     "rows_with_txid": n_txid,
                     "dry_run_consistent": (n_txid == 0) if a.dry_run else True,
                     "meta_stage": "run_end"})
        write_meta_json(rundir, meta)

        # 屏幕汇总
        print("\n=== %s 汇总（n=%d）===" % (a.mode, len(rows)))
        for k in sorted(groups):
            g = groups[k]
            tx_ok = [x for x in g if x.get("txid")]
            actual = sorted({(x.get("actual_spend"), x.get("actual_output")) for x in tx_ok})
            vs = successes.get(k, 0)
            print("  (S=%d,O=%d) 尝试=%d 有效成功=%d 实际形态=%s"
                  % (k[0], k[1], len(g), vs, actual))
        if a.dry_run:
            print("  [dry-run] 本轮未发交易，有效成功必然为 0；判定请看 rounds.csv 的 "
                  "planned_amount_zat / expected_fee_zat / restored_note_count。")
        if a.mode == "confirm":
            short = [k for k in form_order if successes.get(k, 0) < a.target_success]
            if short:
                print("[!] 未达目标有效成功数的形态: %s（可能需在预注册 §4.2 记录为样本不足）" % short)
    finally:
        sampler.stop_evt.set()
        sampler.join(timeout=5)

    print("\n输出:", rundir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
