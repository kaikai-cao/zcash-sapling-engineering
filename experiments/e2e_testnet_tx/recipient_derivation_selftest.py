#!/usr/bin/env python3
"""
收款地址派生补丁的离线自检（不发交易、不需节点、不改任何实验数据）

覆盖范围（对应用户批准的补丁范围 1–7）：
  T1  n_recip=1/2/8：地址互不相同、index 连续、attempts 计数正确
  T2  全部命中白名单 -4：预算耗尽 → RecipientDerivationError（不兜底）
  T3  不可恢复错误（-5 / -8 / gap-limit 文案）：立即抛错，只尝试 1 次
  T4  返回重复地址：L1 抛错
  T5  receiver 含 orchard：L2 抛错
  T6  z_listunifiedreceivers 报错（-5 无法解析）：L2 抛错
  T7  dry-run：不调用 send_frozen，且显式声明 L3 未覆盖
  T8  index 域越界：不调 RPC，直接抛错
  T9  run_one 失败行：failure_class 显式分期、txid 为空、无半构造记录
  T10 listaddresses 数据结构异常（缺 index / 类型错 / 地址重复 / 空）：一律失败，不回退 0
  A1–A3 旧分析脚本兼容性（DictReader；含新列的 CSV 与旧列 CSV 均可读）

运行：python3 recipient_derivation_selftest.py
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import confirmatory_bench as cb           # noqa: E402
import csv                                # noqa: E402
import json                               # noqa: E402

# 分析脚本依赖 numpy（系统 python3 可能没有）。缺依赖时 A 组标记 SKIP 而非 FAIL，
# 但正确做法是用带 numpy 的解释器跑全量：见文件末尾说明。
try:
    import fit_sapling_e2e_model as fm
    HAVE_FM = True
except Exception as _e:                   # pragma: no cover
    fm = None
    HAVE_FM = False
    FM_ERR = "%s: %s" % (type(_e).__name__, _e)

RESULTS = []
SKIPPED = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print("PASS  %s" % name)
    except AssertionError as e:
        RESULTS.append((name, False, str(e)[:300]))
        print("FAIL  %s : %s" % (name, e))
    except Exception as e:                 # 未预期的异常也算失败
        RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
        print("ERROR %s : %s: %s" % (name, type(e).__name__, e))


def check_fm(name, fn):
    """依赖 fit_sapling_e2e_model 的用例：缺 numpy 时 SKIP。"""
    if not HAVE_FM:
        SKIPPED.append((name, FM_ERR))
        print("SKIP  %s （需要 numpy：%s）" % (name, FM_ERR))
        return
    check(name, fn)


def check_hist(name, fn, need):
    """需要历史 raw 目录的用例：目录缺失时 SKIP，不冒充通过。

    与 failure_class_selftest.check_hist 同一约定。历史 run 目录若未纳入版本库
    （例如部分检出），直接 FAIL 会把「数据不在」误报成「实现有错」。
    """
    if not os.path.isdir(need):
        SKIPPED.append((name, "缺少历史目录 %s" % need))
        print("SKIP  %s （缺少历史目录 %s）" % (name, need))
        return
    check_fm(name, fn)


class FakeWallet:
    """替代 z_raw 的钱包假体：纯内存、可注入各类失败。"""

    def __init__(self, base_max=1001, retryable=None, fatal=None, dup=False,
                 receivers=None, list_error=None, list_payload=None,
                 list_payload_factory=None, n_start=1000):
        self.by_idx = {i: "uaddr%d" % i for i in range(n_start, base_max + 1)}
        self.retryable = retryable or {}         # idx -> message（code -4，命中白名单）
        self.retryable_all = False
        self.fatal = fatal or {}                 # idx -> (code, message)
        self.dup = dup
        self.receivers = receivers or {}         # addr -> dict（覆盖 L2 返回）
        self.receivers_error = {}                # addr -> error dict
        self.list_error = list_error
        self.list_payload = list_payload
        self.list_payload_factory = list_payload_factory
        self.calls = []

    def count(self, method):
        return sum(1 for m, _ in self.calls if m == method)

    def z_raw(self, method, params, timeout=60):
        self.calls.append((method, params))
        if method == "listaddresses":
            if self.list_error is not None:
                return None, self.list_error
            if self.list_payload_factory is not None:
                return self.list_payload_factory(), None
            if self.list_payload is not None:
                return self.list_payload, None
            entries = [{"diversifier_index": i, "address": a, "receiver_types": ["sapling"]}
                       for i, a in sorted(self.by_idx.items())]
            return [{"unified": [{"addresses": entries}]}], None
        if method == "z_getaddressforaccount":
            idx = params[2]
            if self.retryable_all:
                return None, {"code": -4,
                              "message": "cannot generate an address with the requested receivers"}
            if idx in self.retryable:
                return None, {"code": -4, "message": self.retryable[idx]}
            if idx in self.fatal:
                code, msg = self.fatal[idx]
                return None, {"code": code, "message": msg}
            addr = "uaddrDUP" if self.dup else "uaddr%d" % idx
            self.by_idx[idx] = addr
            return {"address": addr, "diversifier_index": idx,
                    "receiver_types": ["sapling"]}, None
        if method == "z_listunifiedreceivers":
            a = params[0]
            if a in self.receivers_error:
                return None, self.receivers_error[a]
            if a in self.receivers:
                return self.receivers[a], None
            return {"sapling": "zregtestsapling1" + a[-6:]}, None
        raise AssertionError("未预期的 RPC: %s" % method)


def install(wallet):
    cb.z_raw = wallet.z_raw
    return wallet


def restore_z_raw(orig):
    cb.z_raw = orig


_ORIG_Z_RAW = cb.z_raw


def fake_state(n_recip, amount_zat=100000000, fee_zat=20000):
    return {"pick": {"amount_zat": amount_zat, "fee_zat": fee_zat,
                     "n_recip": n_recip, "unit_zat": amount_zat // max(1, n_recip)},
            "restored_height": 32297, "restored_note_count": 36,
            "snapshot_sha256": "snap-sha", "restore_script_sha256": "script-sha"}


# ---------------------------------------------------------------------------
# T1：正常派生
# ---------------------------------------------------------------------------
def t1():
    for n in (1, 2, 8):
        w = install(FakeWallet(base_max=1001))
        try:
            prep = cb.prepare_recipients(n)
        finally:
            restore_z_raw(_ORIG_Z_RAW)
        assert len(prep["recipients"]) == n, "地址数 %d != %d" % (len(prep["recipients"]), n)
        assert len(set(prep["recipients"])) == n, "地址有重复"
        assert prep["div_indices"] == list(range(1002, 1002 + n)), \
            "index 不连续: %r" % (prep["div_indices"],)
        assert prep["derivation_attempts"] == n, \
            "attempts %d != %d" % (prep["derivation_attempts"], n)
        assert prep["validation"] == "L1+L1.5+L2"
        assert all(rt == "sapling" for rt in prep["receiver_types"])


# ---------------------------------------------------------------------------
# T2：预算耗尽（全部可恢复 -4）→ 必须抛错，不得兜底
# ---------------------------------------------------------------------------
def t2():
    w = install(FakeWallet())
    w.retryable_all = True
    try:
        cb.prepare_recipients(1, budget=5)
        raise AssertionError("应当抛 RecipientDerivationError")
    except cb.RecipientDerivationError as e:
        assert "预算耗尽" in str(e), "错误信息不符: %s" % e
        assert e.attempts == 5, "attempts %d != 5" % e.attempts
    finally:
        restore_z_raw(_ORIG_Z_RAW)
    assert w.count("z_getaddressforaccount") == 5, "RPC 调用次数 %d != 5" % \
        w.count("z_getaddressforaccount")


# ---------------------------------------------------------------------------
# T3：不可恢复错误必须立即抛错（fail-closed），不做顺延
# ---------------------------------------------------------------------------
def t3():
    cases = [
        ("code -5", {"code": -5, "message": "Invalid address"}),
        ("code -8", {"code": -8, "message": "Invalid parameter, duplicated recipient address"}),
        ("gap limit", {"code": -4, "message": "Cannot generate more addresses: gap limit reached"}),
        ("unknown -4", {"code": -4, "message": "something entirely different"}),
    ]
    for label, err in cases:
        w = install(FakeWallet(fatal={1002: (err["code"], err["message"])}))
        try:
            cb.prepare_recipients(1)
            raise AssertionError("%s 应当抛错" % label)
        except cb.RecipientDerivationError as e:
            assert "不可恢复" in str(e), "%s: 错误信息不符 %s" % (label, e)
            assert e.attempts == 1, "%s: attempts %d != 1" % (label, e.attempts)
        finally:
            restore_z_raw(_ORIG_Z_RAW)
        assert w.count("z_getaddressforaccount") == 1, \
            "%s: 不应顺延，实际调用了 %d 次" % (label, w.count("z_getaddressforaccount"))


# ---------------------------------------------------------------------------
# T3b：白名单两条 message 必须顺延成功
# ---------------------------------------------------------------------------
def t3b():
    for msg in cb.DERIVE_RETRYABLE_PATTERNS:
        w = install(FakeWallet(retryable={1002: msg, 1003: msg}))
        try:
            prep = cb.prepare_recipients(1)
        finally:
            restore_z_raw(_ORIG_Z_RAW)
        assert prep["div_indices"] == [1004], "应顺延到 1004，实际 %r" % (prep["div_indices"],)
        assert prep["derivation_attempts"] == 3, "attempts %d != 3" % prep["derivation_attempts"]


# ---------------------------------------------------------------------------
# T4：L1 去重（假钱包恒返回同一地址）
# ---------------------------------------------------------------------------
def t4():
    install(FakeWallet(dup=True))
    try:
        cb.prepare_recipients(2)
        raise AssertionError("应当抛 L1 错误")
    except cb.RecipientValidationError as e:
        assert e.cls == "recipient_validation_failed"
        assert "L1" in str(e), "错误信息未标注 L1: %s" % e
    finally:
        restore_z_raw(_ORIG_Z_RAW)


# ---------------------------------------------------------------------------
# T5：L2 receiver 非 sapling-only
# ---------------------------------------------------------------------------
def t5():
    w = FakeWallet()
    w.receivers["uaddr1002"] = {"sapling": "zregtestsapling1aaa", "orchard": "uregtest1orchard"}
    install(w)
    try:
        cb.prepare_recipients(1)
        raise AssertionError("应当抛 L2 错误")
    except cb.RecipientValidationError as e:
        assert "L2" in str(e) and "sapling-only" in str(e), "错误信息不符: %s" % e
    finally:
        restore_z_raw(_ORIG_Z_RAW)


# ---------------------------------------------------------------------------
# T6：z_listunifiedreceivers 报错
# ---------------------------------------------------------------------------
def t6():
    w = FakeWallet()
    w.receivers_error["uaddr1002"] = {"code": -5, "message": "Invalid address"}
    install(w)
    try:
        cb.prepare_recipients(1)
        raise AssertionError("应当抛 L2 错误")
    except cb.RecipientValidationError as e:
        assert "L2" in str(e) and "无法解析" in str(e), "错误信息不符: %s" % e
    finally:
        restore_z_raw(_ORIG_Z_RAW)


# ---------------------------------------------------------------------------
# T7：dry-run 不发送，且显式声明 L3 未覆盖
# ---------------------------------------------------------------------------
def t7():
    install(FakeWallet())
    sent = {"n": 0}

    def boom(*a, **k):
        sent["n"] += 1
        raise AssertionError("dry-run 不得调用 send_frozen")

    orig_send, orig_wait = cb.send_frozen, cb.wait_sync
    cb.send_frozen = boom
    cb.wait_sync = lambda *a, **k: (32299, 32299, 0.01)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            row, T = cb.run_one(1, 3, 3, "FullPrivacy", 2, True, fake_state(2), "uaddr1000")
    finally:
        cb.send_frozen, cb.wait_sync = orig_send, orig_wait
        restore_z_raw(_ORIG_Z_RAW)
    out = buf.getvalue()
    assert sent["n"] == 0
    assert T is None and row.get("dry_run") == 1
    assert not row.get("txid")
    assert "L3" in out and "未覆盖" in out, "dry-run 未声明 L3 未覆盖"
    assert "L1" in out and "L2" in out, "dry-run 未声明已覆盖层级"
    assert len(row["recipient_addresses_hash"].split(";")) == 2
    assert row["recipient_count"] == 2


# ---------------------------------------------------------------------------
# T8：index 域越界不调 RPC
# ---------------------------------------------------------------------------
def t8():
    w = install(FakeWallet())
    w.retryable_all = True
    try:
        cb.derive_sapling_recipient(cb.INDEX_DOMAIN_MAX, 3)
        raise AssertionError("应当抛越界错误")
    except cb.RecipientDerivationError as e:
        assert "越界" in str(e), "错误信息不符: %s" % e
    finally:
        restore_z_raw(_ORIG_Z_RAW)
    assert w.count("z_getaddressforaccount") == 1, \
        "越界前应只成功调用 1 次，实际 %d" % w.count("z_getaddressforaccount")


# ---------------------------------------------------------------------------
# T9：run_one 的失败行（不构造、不发交易、failure_class 分期明确）
# ---------------------------------------------------------------------------
def t9():
    w = install(FakeWallet())
    w.retryable_all = True
    orig_send = cb.send_frozen
    cb.send_frozen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("不得发送"))
    buf = io.StringIO()
    # F5：失败证据改由 sidecar 承载，run_one 的失败路径也会写 errors.jsonl，
    # 故此处必须先初始化 sidecar（真实运行由 main() 在首次失败前完成）。
    sd = os.path.join(tempfile.mkdtemp(prefix="recip_t9_"), "run_t9")
    os.makedirs(sd)
    cb.init_sidecar(sd)
    try:
        with contextlib.redirect_stdout(buf):
            row, T = cb.run_one(3, 4, 3, "FullPrivacy", 2, False, fake_state(2), "uaddr1000")
    finally:
        cb.send_frozen = orig_send
        restore_z_raw(_ORIG_Z_RAW)
    assert T is None
    assert row["failure_class"] == "recipient_derivation_failed", \
        "failure_class=%r" % row["failure_class"]
    assert not row.get("txid"), "失败行不得带 txid"
    assert row["derivation_attempts"] == cb.DERIVE_ATTEMPT_BUDGET
    assert row["recipient_validation"] == "failed"
    assert row["recipient_count"] == 2
    assert "收款地址准备失败" in buf.getvalue()
    # sidecar 事实层：准备阶段失败必须标明未触及提交
    with open(os.path.join(sd, "errors.jsonl"), encoding="utf-8") as f:
        recs = [json.loads(x) for x in f if x.strip()]
    assert len(recs) == 1, "sidecar 应恰好 1 条：%d" % len(recs)
    r = recs[0]
    assert r["attempt_id"] == "run_t9:3", r["attempt_id"]
    assert r["stage"] == "prep", r["stage"]
    assert r["submit_state"] == "not_submitted", r["submit_state"]
    assert r["z_sendmany_invoked"] is False
    assert r["recipients"] == 2
    shutil.rmtree(os.path.dirname(sd), ignore_errors=True)


# ---------------------------------------------------------------------------
# T10：listaddresses 数据结构异常 —— 一律失败，不静默回退到 0
# ---------------------------------------------------------------------------
def t10():
    def bad(payload):
        def run():
            install(FakeWallet(list_payload=payload))
            try:
                cb.account_unified_addresses()
                raise AssertionError("应当抛错: %r" % (payload,))
            except cb.RecipientDerivationError:
                pass
            finally:
                restore_z_raw(_ORIG_Z_RAW)
        return run

    good = {"diversifier_index": 1001, "address": "uaddr1001"}
    check("T10a 缺少 diversifier_index", bad([{"unified": [{"addresses": [
        {"address": "uaddr1001"}]}]}]))
    check("T10b index 类型错误", bad([{"unified": [{"addresses": [
        {"diversifier_index": "1001", "address": "uaddr1001"}]}]}]))
    check("T10c index 为 bool", bad([{"unified": [{"addresses": [
        {"diversifier_index": True, "address": "uaddr1001"}]}]}]))
    check("T10d 缺少 address", bad([{"unified": [{"addresses": [
        {"diversifier_index": 1001}]}]}]))
    check("T10e 空列表", bad([]))
    check("T10f 地址重复", bad([{"unified": [{"addresses": [good, dict(good)]}]}]))
    check("T10g 返回非 list", bad({"unified": []}))

    install(FakeWallet(list_error={"code": -32601, "message": "Method not found"}))
    try:
        cb.account_unified_addresses()
        raise AssertionError("RPC 报错时应当抛错")
    except cb.RecipientDerivationError as e:
        assert "listaddresses 失败" in str(e)
    finally:
        restore_z_raw(_ORIG_Z_RAW)


# ---------------------------------------------------------------------------
# A1–A3：旧分析脚本兼容性
# ---------------------------------------------------------------------------
OLD_HEADER = ["round", "target_spend", "target_output", "actual_spend", "actual_output",
              "form_match", "fee_match", "policy", "txid", "opid",
              "submit", "pipeline", "mine", "sync", "total",
              "sapling_spends", "sapling_outputs", "sapling_proofs", "tx_size",
              "fee_zat", "expected_fee_zat", "planned_amount_zat", "recipients",
              "restored_height", "restored_note_count",
              "snapshot_sha256", "restore_script_sha256",
              "dry_run", "failure_class", "error"]


def _write_rounds(root, header, rows):
    d = os.path.join(root, "run_selftest")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "rounds.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return d


def a1():
    """新列确实是旧列的严格超集（追加，不重排）。"""
    assert cb.COLUMNS[:len(OLD_HEADER)] == OLD_HEADER, \
        "COLUMNS 前 %d 列被改动（必须只在末尾追加）" % len(OLD_HEADER)
    new = cb.COLUMNS[len(OLD_HEADER):]
    assert new == ["recipient_count", "diversifier_indices", "recipient_addresses_hash",
                   "recipient_receivers", "derivation_attempts", "recipient_validation"], \
        "追加列不符: %r" % (new,)


def a2():
    """含新列的 CSV 能被 load_all 正常读取，旧字段值不变。"""
    row = {"round": 1, "target_spend": 3, "target_output": 3,
           "sapling_spends": 3, "sapling_outputs": 3, "sapling_proofs": 6,
           "pipeline": 1234.5, "form_match": "True", "fee_match": "True",
           "recipient_count": 2, "diversifier_indices": "1002;1003",
           "recipient_addresses_hash": "aaaa;bbbb", "recipient_receivers": "sapling;sapling",
           "derivation_attempts": 2, "recipient_validation": "L1+L1.5+L2"}
    tmp = tempfile.mkdtemp()
    try:
        _write_rounds(tmp, cb.COLUMNS, [row])
        rows = fm.load_all(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert len(rows) == 1, "load_all 读到 %d 行" % len(rows)
    assert rows[0]["spends"] == 3 and rows[0]["outputs"] == 3 and rows[0]["proofs"] == 6


def a3():
    """旧列 CSV（无新列）仍可读，不被新表头破坏。"""
    row = {"round": 1, "target_spend": 3, "target_output": 3,
           "sapling_spends": 3, "sapling_outputs": 3, "sapling_proofs": 6,
           "pipeline": 1234.5}
    tmp = tempfile.mkdtemp()
    try:
        _write_rounds(tmp, OLD_HEADER, [row])
        rows = fm.load_all(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert len(rows) == 1


def a4():
    """带 error 的失败行不会进入模型拟合（load_all 现有约定不变）。"""
    row = {"round": 1, "target_spend": 4, "target_output": 3,
           "sapling_spends": 4, "sapling_outputs": 3, "sapling_proofs": 7,
           "pipeline": 1234.5, "error": "recipient_derivation_failed: 预算耗尽",
           "failure_class": "recipient_derivation_failed"}
    tmp = tempfile.mkdtemp()
    try:
        _write_rounds(tmp, cb.COLUMNS, [row])
        rows = fm.load_all(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert rows == [], "失败行不应进入拟合，实际读到 %d 行" % len(rows)


def a5():
    """真实 raw 目录：load_all 仍排除 _feasibility_gate（门禁数据不得混入）。

    目录缺失由 main() 的 check_hist 判为 SKIP，故此处不再重复断言「目录存在」。
    """
    root = os.path.join(HERE, "raw", "confirmatory_20261030")
    rows = fm.load_all(root)
    assert all(r["batch"] != "_feasibility_gate" for r in rows), \
        "门禁数据混入了拟合输入"
    print("      （真实 raw 目录读到 %d 行，门禁目录已被排除）" % len(rows))


def _prep_fail_rows(n, cls="recipient_derivation_failed"):
    return [{"round": i + 1, "target_spend": 1, "target_output": 2, "failure_class": cls}
            for i in range(n)]


def s1():
    """F1: 正式模式、只发生收款地址准备失败 —— 不得读成「形态不可行」。"""
    rows = _prep_fail_rows(2)
    note = cb._summary_note(rows, [], [], False)
    assert "收款地址准备失败 2 条" in note, note
    assert "recipient_derivation_failed" in note, note
    assert "不代表该形态不可行" in note, note
    assert "无成功构造" not in note, note
    assert "环境/策略失败" not in note, note


def s2():
    """F1: 正式模式、构造/发送阶段失败 —— 按实际 failure_class 描述。"""
    rows = [{"round": 1, "failure_class": "rpc_policy_rejected"}]
    note = cb._summary_note(rows, [], [], False)
    assert "交易构造/发送阶段失败 1 条" in note, note
    assert "rpc_policy_rejected" in note, note
    assert "收款地址准备" not in note, note
    assert "形态不可行" not in note, note


def s3():
    """F1: 两类失败并存 —— 各自单列，不合并、不互相冒充。"""
    rows = _prep_fail_rows(1) + [{"round": 2, "failure_class": "timeout"}]
    note = cb._summary_note(rows, [], [], False)
    assert "收款地址准备失败 1 条" in note, note
    assert "交易构造/发送阶段失败 1 条" in note, note
    assert "timeout" in note, note


def s4():
    """F1: dry-run 且构造全部完成 —— 无 txid 属预期，并声明 L3 未覆盖。"""
    rows = [{"round": 1, "dry_run": 1}]
    note = cb._summary_note(rows, [], [], True)
    assert "无 txid 属预期" in note, note
    assert "L3 未覆盖" in note, note
    assert "收款地址准备失败" not in note, note


def s5():
    """F1 回归：dry-run 下发生地址准备失败，不能被「dry-run 无 txid 属预期」掩盖。"""
    rows = [{"round": 1, "dry_run": 1},
            {"round": 2, "failure_class": "recipient_derivation_failed"}]
    note = cb._summary_note(rows, [], [], True)
    assert "收款地址准备失败 1 条" in note, note
    assert "无 txid 属预期" in note, note


def s6():
    """F1: 有 txid 的两种情况仍沿用原文案（统计口径未变）。"""
    ok = [{"txid": "ab", "form_match": True, "fee_match": True}]
    assert cb._summary_note(ok, ok, ok, False) == "", "全匹配时应无 note"
    bad = [{"txid": "ab", "form_match": True, "fee_match": False}]
    assert cb._summary_note(bad, bad, [], False) == \
        "成功构造但形态或手续费不符，未计入有效样本"


def s7():
    """F1: 无任何阶段信息时保留兜底文案，不臆测具体原因。"""
    note = cb._summary_note([{"round": 1}], [], [], False)
    assert note == "无成功构造（形态不可行或环境/策略失败）", note


def main():
    print("=== 收款地址派生离线自检 ===")
    print("DERIVE_ATTEMPT_BUDGET=%d  INDEX_DOMAIN_MAX=2^88-1  COLUMNS=%d 列"
          % (cb.DERIVE_ATTEMPT_BUDGET, len(cb.COLUMNS)))
    print()
    check("T1  n=1/2/8 正常派生", t1)
    check("T2  预算耗尽（不兜底）", t2)
    check("T3  不可恢复错误立即抛出", t3)
    check("T3b 白名单 -4 顺延成功", t3b)
    check("T4  L1 去重", t4)
    check("T5  L2 非 sapling-only", t5)
    check("T6  L2 解析失败", t6)
    check("T7  dry-run 不发送 + L3 声明", t7)
    check("T8  index 越界", t8)
    check("T9  run_one 失败行分期", t9)
    check("T10 listaddresses 结构异常", t10)
    check("A1  COLUMNS 仅追加", a1)
    check_fm("A2  含新列 CSV 可读", a2)
    check_fm("A3  旧列 CSV 可读", a3)
    check_fm("A4  失败行不入拟合", a4)
    check_hist("A5  门禁目录仍被排除", a5,
               os.path.join(HERE, "raw", "confirmatory_20261030"))
    check("S1  汇总 note：仅地址准备失败", s1)
    check("S2  汇总 note：构造/发送失败", s2)
    check("S3  汇总 note：两类失败并存", s3)
    check("S4  汇总 note：dry-run 构造完成", s4)
    check("S5  汇总 note：dry-run 下地址失败不被掩盖", s5)
    check("S6  汇总 note：有 txid 时文案不变", s6)
    check("S7  汇总 note：无阶段信息时兜底", s7)
    print()
    ok = sum(1 for _, r, _ in RESULTS if r)
    print("结果：%d/%d 通过，%d 跳过" % (ok, len(RESULTS), len(SKIPPED)))
    if SKIPPED:
        print("跳过明细（不计为通过）：")
        for n, why in SKIPPED:
            print("  - %s：%s" % (n, why))
        if any("numpy" in str(w) for _, w in SKIPPED):
            print("  提示：含 numpy 依赖项，可用带 numpy 的解释器复跑：")
            print("    D:/WorkBuddyData/.workbuddy/binaries/python/envs/default/Scripts/python.exe "
                  "recipient_derivation_selftest.py")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
