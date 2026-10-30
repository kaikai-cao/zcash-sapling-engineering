#!/usr/bin/env python3
"""
F5（失败分类 + 未截断证据）的离线自检 —— 不发交易、不连节点、不碰实验数据。

对应用户授权的 T1 范围与冻结稿 §6 测试矩阵：
  构造   C1–C8  code/措辞映射（含「unknown privacy policy」反向用例）
  回放   R1–R4  历史 -8 原文回放 + 三条回归（同步超时 / opid 终态 / 轮询超时）
  不变量 I1–I8  params 与 timeout / 计时区间 / 成功口径 / COLUMNS / recipient_* /
                dry-run 全等 / sidecar 行数 / attempt_id 双向
  状态   S1–S11  传输异常=unknown / 被拒=not_submitted / sidecar 完整性 /
                超长原文不截断 / 写入失败 fail-closed / replaces 留痕 /
                main() 端到端（流程级，超出 §6 编号 1 条）/
                提交状态不明单列（审阅补修，超出 §6 编号 1 条）/
                F7 中止落盘 3 条（S9/S10/S11，超出 §6 编号，用户授权实施）

运行：python3 failure_class_selftest.py
退出码非 0 表示存在失败。
"""

import csv
import http.client
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import confirmatory_bench as cb            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw", "confirmatory_20261030")
GATE_RUN = os.path.join(RAW, "_feasibility_gate", "run_20261030_110042")   # 正式 gate 7/10
DRY_RUN = os.path.join(RAW, "_feasibility_gate", "run_20261030_113002")    # 补丁后 dry-run

# S7 复用 reporting_patch_selftest 的 stub（已随 6cd58de 入仓）；仍保留缺失时 SKIP 而非 ERROR 的守卫
try:
    import reporting_patch_selftest as RPS      # noqa: E402
    HAVE_RPS, RPS_ERR = True, ""
except Exception as _e:                         # pragma: no cover
    RPS = None
    HAVE_RPS, RPS_ERR = False, "%s: %s" % (type(_e).__name__, _e)

# S11 需要 fit_sapling_e2e_model（依赖 numpy）；缺 numpy 时 SKIP 而非 FAIL
try:
    import fit_sapling_e2e_model as FM          # noqa: E402
    HAVE_FM, FM_ERR = True, ""
except Exception as _e:                         # pragma: no cover
    FM = None
    HAVE_FM, FM_ERR = False, "%s: %s" % (type(_e).__name__, _e)

UA = "uregtest1" + "q" * 100
AMOUNTS = [{"address": "uregtest1abc", "amount": 1.0}]

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
    except Exception as e:
        RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
        print("ERROR %s : %s: %s" % (name, type(e).__name__, e))


def check_opt(name, fn, ok, why):
    """可选依赖用例：依赖缺失时 SKIP（不冒充通过，也不误报失败）。"""
    if not ok:
        SKIPPED.append((name, why))
        print("SKIP  %s （%s）" % (name, why))
        return
    check(name, fn)


def check_hist(name, fn, need):
    """需要历史 run 目录的用例：缺失时 SKIP（不冒充通过）。"""
    if not os.path.isdir(need):
        SKIPPED.append((name, need))
        print("SKIP  %s （缺少历史目录 %s）" % (name, os.path.relpath(need, HERE)))
        return
    check(name, fn)


# ---------------------------------------------------------------------------
# 构造工具
# ---------------------------------------------------------------------------
def rpc_err(code, message, stage="submit", **kw):
    """按 send_frozen 的真实形态构造 RPC 拒绝异常。"""
    return cb.RpcCallError("stage=%s RPC 拒绝: code=%s message=%s" % (stage, code, message),
                           stage=stage,
                           raw_error={"code": code, "message": message},
                           z_sendmany_invoked=True,
                           submit_state="not_submitted", **kw)


def tmp_run(tag):
    d = os.path.join(tempfile.mkdtemp(prefix="f5_%s_" % tag), "run_test_%s" % tag)
    os.makedirs(d)
    cb.init_sidecar(d)
    return d


def read_jsonl(path):
    out = []
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_rounds(rundir, rows):
    with open(os.path.join(rundir, "rounds.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cb.COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


class FakeClock(object):
    """只提供 monotonic/sleep，用来精确验证计时区间。"""

    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0

    def monotonic(self):
        v = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return v

    def sleep(self, _s):
        pass


def with_fake_post(handler, fn):
    """临时替换 _post / zauth，调用 fn，随后必定还原。"""
    orig_post, orig_auth = cb._post, cb.zauth
    calls = []

    def fake_post(host, port, payload, auth=None, timeout=900):
        calls.append({"payload": payload, "timeout": timeout})
        return handler(payload, timeout)

    cb._post = fake_post
    cb.zauth = lambda: ""
    try:
        return fn(), calls
    finally:
        cb._post, cb.zauth = orig_post, orig_auth


# ===========================================================================
# C 组：code / 措辞映射（§6.2）
# ===========================================================================
def c1():
    got = cb._classify(rpc_err(-4, "Insufficient funds for transaction construction; "
                                   "need an additional 5000000 zats"))
    assert got == "rpc_insufficient_funds", got


def c2():
    got = cb._classify(rpc_err(-6, "Insufficient balance (have 1.2 ZEC, need 2.0 ZEC)"))
    assert got == "rpc_insufficient_funds", got


def c3():
    got = cb._classify(rpc_err(-8, "Privacy policy: NoPrivacy not allowed here (privacyPolicy)"))
    assert got == "rpc_privacy_policy_rejected", got


def c4():
    got = cb._classify(rpc_err(-8, "Invalid parameter, unknown address format: ztestsapling1xyz"))
    assert got == "rpc_invalid_parameter", got


def c5():
    """反向用例：含 privacy policy 但属参数错误，绝不能被判成策略拒绝。"""
    got = cb._classify(rpc_err(-8, "Invalid parameter, unknown privacy policy: FooPolicy"))
    assert got == "rpc_invalid_parameter", got


def c6():
    assert cb._classify(rpc_err(-5, "Invalid address")) == "rpc_invalid_address_or_key"


def c7():
    assert cb._classify(rpc_err(-9999, "boom")) == "rpc_error_-9999"


def c8():
    assert cb._classify(rpc_err(-32602, "invalid params")) == "rpc_request_schema_invalid"


# ===========================================================================
# R 组：历史回放与回归（§6.1 + §6.4）
# ===========================================================================
def r1():
    """用历史 run 的真实 error 原文回放：必须判 rpc_duplicated_recipient 且 code=-8。"""
    with open(os.path.join(GATE_RUN, "rounds.csv"), newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("failure_class")]
    assert len(rows) == 3, "历史失败行应为 3 条，实际 %d" % len(rows)
    for r in rows:
        text = r["error"]
        # 原文形如：policy=FullPrivacy 被拒: z_sendmany -> {"code": -8, "message": "..."}
        # 但历史原文在 223 字符处被截断（地址没写完），**不是合法 JSON**，
        # 不能 json.loads；只能恢复 code 与消息前缀（§6.1 已知限制，须写入报告）。
        mc = re.search(r'"code"\s*:\s*(-?\d+)', text)
        assert mc and int(mc.group(1)) == -8, "原文里应能读出 code=-8: %s" % text[:80]
        mm = re.search(r'"message"\s*:\s*"(.*)$', text, re.S)
        assert mm, "原文里应能读出 message 前缀: %s" % text[:80]
        raw = {"code": -8, "message": mm.group(1)}   # 已截断的前缀，非完整 JSON
        assert "duplicated recipient address" in raw["message"], raw["message"][:60]
        e = cb.RpcCallError("legacy", stage="submit", raw_error=raw,
                            z_sendmany_invoked=True, submit_state="not_submitted")
        assert cb._classify(e) == "rpc_duplicated_recipient", cb._classify(e)
        # 旧包装文本不得再参与判定：把它塞进异常也不影响结果
        e2 = cb.RpcCallError("policy=FullPrivacy 被拒: " + text, stage="submit",
                             raw_error=raw, z_sendmany_invoked=True,
                             submit_state="not_submitted")
        assert cb._classify(e2) == "rpc_duplicated_recipient"


def r2():
    """前置同步超时：仍为 env_transient_sync（R1 不变）。"""
    e = cb.PreTxError("stage=sync 前置同步超时", stage="sync", z_sendmany_invoked=False)
    assert cb._classify(e) == "env_transient_sync", cb._classify(e)
    assert cb._classify("前置同步超时") == "env_transient_sync"


def r3():
    """opid 终态失败：仍为 opid_terminal_failed（§6.4 R2 不变）。"""
    e = cb.RpcCallError("stage=opid_failed", stage="opid_failed",
                        raw_error={"code": -1, "message": "boom"},
                        z_sendmany_invoked=True, submit_state="submitted", opid="opid-1")
    assert cb._classify(e) == "opid_terminal_failed", cb._classify(e)
    assert cb._classify('operation failed: {"code": -1, "message": "boom"}') == "opid_terminal_failed"


def r4():
    """轮询超时：修复点 —— 原为 rpc_policy_rejected，现由阶段决定。"""
    e = cb.PreTxError("stage=opid_timeout 轮询超时 600s（opid=x, policy=FullPrivacy）",
                      stage="opid_timeout", z_sendmany_invoked=True, submit_state="submitted")
    assert cb._classify(e) == "opid_timeout", cb._classify(e)
    # 旧文本形态（带 policy 括号）也不得再被判成策略拒绝
    assert cb._classify("operation timeout (policy=FullPrivacy)") == "opid_timeout"


# ===========================================================================
# I 组：不变量（§5）
# ===========================================================================
def i1():
    """params 逐字节不变 + timeout 仍为 120。"""
    def run():
        return cb.send_frozen(UA, AMOUNTS, "FullPrivacy")

    def handler(payload, timeout):
        if payload["method"] == "z_sendmany":
            return {"result": "opid-1", "error": None}
        return {"result": [{"status": "success", "result": {"txid": "ab" * 32}}], "error": None}

    (ts, tp, opid, res), calls = with_fake_post(handler, run)
    assert opid == "opid-1"
    p = calls[0]["payload"]
    assert list(p.keys()) == ["jsonrpc", "method", "params", "id"], list(p.keys())
    assert json.dumps(p, ensure_ascii=False) == json.dumps(
        {"jsonrpc": "2.0", "method": "z_sendmany",
         "params": [UA, AMOUNTS, 1, None, "FullPrivacy"], "id": 1}, ensure_ascii=False), p
    assert calls[0]["timeout"] == 120, calls[0]["timeout"]
    assert p["params"][2] == 1 and p["params"][3] is None   # 字面量 1 / null 未被改写


def i2():
    """计时区间：t0 在 z_sendmany 之前、t_submit 在其返回之后。"""
    clock = FakeClock([100.0, 100.25, 200.0, 200.1, 230.0])
    orig_time = cb.time
    cb.time = clock
    try:
        def handler(payload, timeout):
            if payload["method"] == "z_sendmany":
                return {"result": "opid-1", "error": None}
            return {"result": [{"status": "success", "result": {"txid": "ab" * 32}}],
                    "error": None}
        (ts, tp, opid, res), _ = with_fake_post(handler,
                                                lambda: cb.send_frozen(UA, AMOUNTS, "FullPrivacy"))
    finally:
        cb.time = orig_time
    assert abs(ts - 250.0) < 1e-9, ts        # 100.25 - 100.0
    assert abs(tp - 30000.0) < 1e-9, tp      # 230.0 - 200.0


def i3():
    """成功路径统计口径不变：历史 7 条成功仍全部 form/fee 匹配。"""
    with open(os.path.join(GATE_RUN, "rounds.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    tx_ok = [r for r in rows if r.get("txid")]
    fm = [r for r in tx_ok if r.get("form_match") in ("True", "1", "true")]
    fem = [r for r in tx_ok if r.get("fee_match") in ("True", "1", "true")]
    allm = [r for r in tx_ok if r in fm and r in fem]
    assert len(tx_ok) == 7, len(tx_ok)
    assert len(fm) == 7 and len(fem) == 7 and len(allm) == 7, (len(fm), len(fem), len(allm))
    for r in tx_ok:
        assert not r.get("failure_class"), "成功行不应带 failure_class"


def i4():
    """COLUMNS 未变：36 列，前 30 列同序（与 2eb6442 冻结值逐项比对）。"""
    frozen30 = ["round", "target_spend", "target_output", "actual_spend", "actual_output",
                "form_match", "fee_match", "policy", "txid", "opid",
                "submit", "pipeline", "mine", "sync", "total",
                "sapling_spends", "sapling_outputs", "sapling_proofs", "tx_size",
                "fee_zat", "expected_fee_zat", "planned_amount_zat", "recipients",
                "restored_height", "restored_note_count",
                "snapshot_sha256", "restore_script_sha256",
                "dry_run", "failure_class", "error"]
    assert len(cb.COLUMNS) == 36, len(cb.COLUMNS)
    assert cb.COLUMNS[:30] == frozen30, cb.COLUMNS[:30]


def i5():
    """recipient_* 分类与阶段不受 F5 影响（I5）。"""
    d = tmp_run("i5")
    try:
        e = cb.RecipientDerivationError("预算耗尽", attempts=64)
        assert e.cls == "recipient_derivation_failed"
        rec = cb._emit_failure(1, 2, 9, e.cls, e, extra={"recipients": 8},
                               stage="prep", submit_state="not_submitted",
                               z_sendmany_invoked=False)
        assert rec["stage"] == "prep", rec["stage"]
        assert rec["submit_state"] == "not_submitted"
        assert rec["z_sendmany_invoked"] is False
        assert cb.replacement_allowed(rec) is True
        assert cb.RecipientValidationError("x").cls == "recipient_validation_failed"
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


def i6():
    """dry-run 口径：列结构与历史 dry-run 逐项一致，note 按**当前**口径可复现。

    注意：`run_20261030_113002` 产出于 F1(247f855) 之前，其 gate_summary 里的 note
    是**旧措辞**（「未发交易，仅验证构造」）。按 §7「新旧口径不可混算」，本用例不拿
    旧文本否定新实现，而是分两段断言：
      ① 列结构必须与历史 dry-run 完全相同（证明零新增列）；
      ② 当前实现对同一批行产出的 note 必须是 F1 后口径，且不含归因措辞。
    """
    with open(os.path.join(DRY_RUN, "rounds.csv"), newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        header = rd.fieldnames
        rows = list(rd)
    assert header == cb.COLUMNS, "列结构变化：%s" % [c for c in header if c not in cb.COLUMNS]
    assert len(rows) == 10, len(rows)
    assert all(r["dry_run"] == "1" for r in rows)
    assert all(not r.get("txid") for r in rows)

    groups = {}
    for r in rows:
        groups.setdefault((r["target_spend"], r["target_output"]), []).append(r)
    for k, g in groups.items():
        note = cb._summary_note(g, [], [], True)
        assert "无成功构造" not in note, "%s 出现归因兜底：%r" % (k, note)
        assert "未发交易" in note and "L3 未覆盖" in note, "%s note 缺关键事实：%r" % (k, note)

    with open(os.path.join(DRY_RUN, "gate_summary.csv"), newline="", encoding="utf-8") as f:
        old_notes = {r["note"] for r in csv.DictReader(f)}
    assert any("仅验证构造" in x for x in old_notes), \
        "历史 dry-run 应为 F1 前旧措辞（若不是，说明 §7 的口径声明需更新）"


def i7():
    """sidecar 行数 == 失败轮数；超长 message 不截断。"""
    d = tmp_run("i7")
    try:
        long_msg = "X" * 1000
        e = rpc_err(-8, long_msg)
        rec = cb._emit_failure(1, 2, 2, cb._classify(e), e)
        cb._emit_failure(2, 3, 2, "state_verification_failed", None)
        recs = read_jsonl(os.path.join(d, "errors.jsonl"))
        assert len(recs) == 2, len(recs)
        assert len(recs[0]["raw_error"]["message"]) == 1000, len(recs[0]["raw_error"]["message"])
        assert rec["attempt_id"] == "run_test_i7:1", rec["attempt_id"]
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


def i8():
    """attempt_id 双向齐全：正常通过，缺一条/多一条均 SystemExit。"""
    d = tmp_run("i8")
    try:
        rows = [{"round": 1, "target_spend": 2, "target_output": 2},
                {"round": 2, "target_spend": 2, "target_output": 2, "failure_class": "other"}]
        write_rounds(d, rows)
        cb._emit_failure(2, 2, 2, "other", cb.PreTxError("boom"))
        got = cb.verify_run_artifacts(d)
        assert got == {"failure_rows": 1, "sidecar_rows": 1}, got
        # 多一条 sidecar -> 失败
        cb._emit_failure(3, 2, 2, "other", cb.PreTxError("boom"))
        try:
            cb.verify_run_artifacts(d)
        except SystemExit as e:
            assert "多 sidecar" in str(e), str(e)
        else:
            raise AssertionError("sidecar 多出一条时未终止")
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


# ===========================================================================
# S 组：状态与证据
# ===========================================================================
def s1():
    """submit 阶段传输异常 -> unknown，且不可替换。"""
    for exc in (ConnectionRefusedError(111, "refused"),
                TimeoutError("timed out"),
                http.client.RemoteDisconnected("remote closed"),
                json.JSONDecodeError("Expecting value", "<html>", 0)):
        def handler(payload, timeout, _e=exc):
            raise _e
        try:
            with_fake_post(handler, lambda: cb.send_frozen(UA, AMOUNTS, "FullPrivacy"))
        except cb.TransportError as e:
            assert e.stage == "submit", e.stage
            assert e.submit_state == "unknown", e.submit_state
            assert e.z_sendmany_invoked is True
            assert e.opid is None
            assert cb._classify(e) == "rpc_transport_error", cb._classify(e)
            rec = {"submit_state": e.submit_state, "z_sendmany_invoked": e.z_sendmany_invoked}
            assert cb.replacement_allowed(rec) is False
        else:
            raise AssertionError("%s 未抛出 TransportError" % type(exc).__name__)


def s2():
    """z_sendmany 返回 -8 -> not_submitted + invoked=True，且不可替换。"""
    def handler(payload, timeout):
        return {"result": None, "error": {"code": -8,
                "message": "Invalid parameter, duplicated recipient address: uregtest1..."}}
    try:
        with_fake_post(handler, lambda: cb.send_frozen(UA, AMOUNTS, "FullPrivacy"))
    except cb.RpcCallError as e:
        assert e.code == -8, e.code
        assert e.submit_state == "not_submitted", e.submit_state
        assert e.z_sendmany_invoked is True
        assert cb._classify(e) == "rpc_duplicated_recipient", cb._classify(e)
        rec = {"submit_state": e.submit_state, "z_sendmany_invoked": e.z_sendmany_invoked}
        assert cb.replacement_allowed(rec) is False, "被 RPC 拒绝的尝试不得替换（G3）"
    else:
        raise AssertionError("未抛出 RpcCallError")


def s3():
    """sidecar 完整性：缺一条即 SystemExit。"""
    d = tmp_run("s3")
    try:
        write_rounds(d, [{"round": 1, "target_spend": 2, "target_output": 2,
                          "failure_class": "other"}])
        try:
            cb.verify_run_artifacts(d)
        except SystemExit as e:
            assert "缺 sidecar" in str(e), str(e)
        else:
            raise AssertionError("缺 sidecar 时未终止")
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


def s4():
    """超长原文落盘长度等于原长（JSONL 不截断）。"""
    d = tmp_run("s4")
    try:
        msg = "y" * 5000
        e = rpc_err(-8, msg)
        cb.fail_row(1, 2, 2, cb._classify(e), str(e), e)   # error 列会截断到 300
        recs = read_jsonl(os.path.join(d, "errors.jsonl"))
        assert len(recs) == 1
        assert len(recs[0]["raw_error"]["message"]) == 5000, len(recs[0]["raw_error"]["message"])
        assert len(recs[0]["wrapper_text"]) > 300, len(recs[0]["wrapper_text"])
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


def s5():
    """sidecar 写入失败 -> SystemExit，且不会继续产出 rounds.csv。"""
    d = tmp_run("s5")
    orig = cb._sidecar_open_append
    cb._sidecar_open_append = lambda: (_ for _ in ()).throw(OSError(28, "No space left"))
    try:
        try:
            cb.fail_row(1, 2, 2, "other", "boom", cb.PreTxError("boom"))
        except SystemExit as e:
            assert "sidecar 写入失败" in str(e), str(e)
        else:
            raise AssertionError("sidecar 写入失败未终止实验")
        assert not os.path.isfile(os.path.join(d, "rounds.csv")), "不应先落 CSV"
    finally:
        cb._sidecar_open_append = orig
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


def s6():
    """人工替换：replaces 写入 sidecar；非法 attempt_id 直接拒绝。"""
    d = os.path.join(tempfile.mkdtemp(prefix="f5_s6_"), "run_repl_1")
    os.makedirs(d)
    try:
        cb.init_sidecar(d, "run_20261030_110042:5")
        rec = cb._emit_failure(1, 2, 2, "env_transient_sync",
                               cb.PreTxError("stage=sync 前置同步超时", stage="sync"),
                               z_sendmany_invoked=False)
        assert rec["replaces"] == "run_20261030_110042:5", rec["replaces"]
        assert cb.replacement_allowed(rec) is True
        recs = read_jsonl(os.path.join(d, "errors.jsonl"))
        assert recs[0]["replaces"] == "run_20261030_110042:5"
        # 非法 replaces 必须在 preflight 之前被拒
        argv = sys.argv
        sys.argv = ["confirmatory_bench.py", "--replaces", "not-an-attempt-id"]
        try:
            cb.main()
        except SystemExit as e:
            assert "attempt_id" in str(e), str(e)
        else:
            raise AssertionError("非法 --replaces 未被拒绝")
        finally:
            sys.argv = argv
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


# ===========================================================================
def s7():
    """main() 端到端：失败行与 sidecar 均由执行器自己写出，且关联校验通过。

    §6 的 26 条用例全部是函数级；本用例补一条**流程级**验证（超出 §6 编号 1 条）：
    用 stub 跑完整 main()，确认 sidecar 不是只有单测能写出来。
    """
    rps = RPS

    tmp = tempfile.mkdtemp(prefix="f5_s7_")
    base = os.path.join(tmp, "out")
    orig_preflight = cb.preflight
    orig_do = cb.do_one_attempt
    rps.patch_common()
    long_msg = "Invalid parameter, duplicated recipient address: " + "z" * 400

    def fake(idx, S, O, policy, mine_blocks, dry_run, restore, ah, asm, ahm):
        raise cb.RpcCallError("stage=submit RPC 拒绝: code=-8 message=%s" % long_msg,
                              stage="submit",
                              raw_error={"code": -8, "message": long_msg},
                              z_sendmany_invoked=True, submit_state="not_submitted")

    try:
        r = rps.run_main(["--mode", "gate", "--outdir-base", base], fake)
        assert r == "OK", r
        rd = rps.find_rundir(os.path.join(base, "_feasibility_gate"))
        recs = read_jsonl(os.path.join(rd, "errors.jsonl"))
        assert len(recs) == 10, len(recs)
        got = cb.verify_run_artifacts(rd)
        assert got == {"failure_rows": 10, "sidecar_rows": 10}, got
        run_id = os.path.basename(rd)
        assert {x["attempt_id"] for x in recs} == \
            {"%s:%d" % (run_id, i) for i in range(1, 11)}
        assert all(len(x["raw_error"]["message"]) == len(long_msg) for x in recs)
        assert all(x["stage"] == "submit" and x["submit_state"] == "not_submitted"
                   for x in recs)
        with open(os.path.join(rd, "gate_summary.csv"), newline="", encoding="utf-8") as f:
            summ = list(csv.DictReader(f))
        assert len(summ) == 10
        assert all("重复收款地址导致 RPC 拒绝" in x["note"] for x in summ), summ[0]["note"]
        assert all(x["tx_success"] == "0" for x in summ)
        with open(os.path.join(rd, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["sidecar_rows"] == 10 and meta["failure_rows"] == 10, meta.get("sidecar_rows")
        assert meta["sidecar"] == "errors.jsonl"
    finally:
        cb.do_one_attempt = orig_do
        cb.preflight = orig_preflight
        shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
def s8():
    """「提交状态不明」单列：opid_timeout / transport 不得写成「未产生 txid」。

    审阅中发现的第二个同族缺陷：这两类此前落在 other 桶，note 会写成
    「交易构造/发送阶段失败 N 条（opid_timeout），未产生 txid」。但 opid_timeout
    已拿到 opid（submitted）、submit 阶段传输异常为 unknown —— 交易可能已存在，
    「未产生 txid」是无法由记录支撑的断言，而且直接违反 G4 的语义。
    """
    # 1) 纯超时：必须出现「提交状态不明」，且不得出现「未产生 txid」
    rows = [{"target_spend": 2, "target_output": 2,
             "failure_class": "opid_timeout", "txid": ""}]
    n1 = cb._summary_note(rows, [], [], False)
    assert "提交状态不明 1 条" in n1, n1
    assert "opid_timeout" in n1, n1
    assert "未产生 txid" not in n1, "超时不得断言未产生 txid：%s" % n1
    assert "构造/发送阶段失败" not in n1, "超时不是构造/发送失败：%s" % n1

    # 2) 纯传输异常：同口径
    rows2 = [{"target_spend": 2, "target_output": 2,
              "failure_class": "rpc_transport_error", "txid": ""}]
    n2 = cb._summary_note(rows2, [], [], False)
    assert "提交状态不明 1 条" in n2 and "未产生 txid" not in n2, n2

    # 3) 混合：被拒 + 超时，必须分成两段，事实互不串味
    rows3 = [{"target_spend": 3, "target_output": 3,
              "failure_class": "rpc_duplicated_recipient", "txid": ""},
             {"target_spend": 3, "target_output": 3,
              "failure_class": "opid_timeout", "txid": ""}]
    n3 = cb._summary_note(rows3, [], [], False)
    assert "提交状态不明 1 条（opid_timeout）" in n3, n3
    assert "交易构造/发送阶段失败 1 条（rpc_duplicated_recipient），未产生 txid" in n3, n3

    # 4) 其余类别仍归 other，不被误并
    rows4 = [{"target_spend": 4, "target_output": 2,
              "failure_class": "rpc_insufficient_funds", "txid": ""}]
    n4 = cb._summary_note(rows4, [], [], False)
    assert "构造/发送阶段失败 1 条（rpc_insufficient_funds），未产生 txid" in n4, n4
    assert "提交状态不明" not in n4, n4


# ===========================================================================
def _f7_case(first_fail_at, csv_broken=False):
    """跑一次 stub main()：前 2 轮成功发交易，随后 z_sendmany 被拒。

    `first_fail_at` = 第几次 sidecar 写入时注入 OSError（1 起）。
    `csv_broken`   = 连 rounds.csv 补写也一并失败（测「落盘失败不掩盖原异常」）。
    返回 (run_main 结果串, meta, rows, errors.jsonl 记录)——产物在临时目录内读回，
    目录随后被清理，故不返回路径。
    """
    rps = RPS
    tmp = tempfile.mkdtemp(prefix="f7_")
    base = os.path.join(tmp, "out")
    orig = (cb.preflight, cb.do_one_attempt, cb._sidecar_open_append, cb.write_rounds_csv)
    rps.patch_common()

    n = {"c": 0}

    def fake(idx, S, O, policy, mine_blocks, dry_run, restore, ah, asm, ahm):
        n["c"] += 1
        if n["c"] <= 2:                     # 前两轮真实「发交易成功」
            return (rps.mkrow(idx, S, O, False, txid="tx%d" % idx, fm=1, fem=1),
                    {"submit": 10.0, "pipeline": 20.0, "mine": 1.0, "sync": 1.0,
                     "total": 32.0})
        raise cb.RpcCallError("stage=submit RPC 拒绝: code=-8 message=duplicate",
                              stage="submit", raw_error={"code": -8, "message": "duplicate"},
                              z_sendmany_invoked=True, submit_state="not_submitted")

    w = {"c": 0}

    def failing_open():
        w["c"] += 1
        if w["c"] >= first_fail_at:
            raise OSError(28, "No space left on device")
        return orig[2]()

    def failing_write(rundir, rows):
        raise OSError(28, "No space left on device")

    cb._sidecar_open_append = failing_open
    if csv_broken:
        cb.write_rounds_csv = failing_write
    try:
        r = rps.run_main(["--mode", "gate", "--outdir-base", base], fake)
        rd = rps.find_rundir(os.path.join(base, "_feasibility_gate"))
        rows = []
        p = os.path.join(rd, "rounds.csv")
        if os.path.isfile(p):
            with open(p, newline="", encoding="utf-8") as f:
                d = csv.DictReader(f)
                assert d.fieldnames == cb.COLUMNS, "列结构变化: %s" % d.fieldnames
                rows = list(d)
        sc = os.path.join(rd, "errors.jsonl")
        recs = read_jsonl(sc) if os.path.isfile(sc) else []
        # meta 必须在 finally 清理临时目录之前读回
        meta = RPS.read_meta(rd)
        return r, meta, rows, recs
    finally:
        cb._sidecar_open_append = orig[2]
        cb.write_rounds_csv = orig[3]
        cb.do_one_attempt, cb.preflight = orig[1], orig[0]
        shutil.rmtree(tmp, ignore_errors=True)


def s9():
    """F7 故障注入：sidecar 写入失败中止时，此前**已发送成功**的尝试不得丢记录。

    两种时序都要成立：
      (a) 首个 sidecar 写入即失败（2 条成功之后）→ CSV 必须保住 2 条 txid；
      (b) 第 3 次 sidecar 写入失败（2 成功 + 2 失败之后）→ CSV 必须保住 2 条 txid
          与 2 条失败行，且已写入的 sidecar 与已落盘的失败行仍然对得上。
    """
    # (a) 第一次写 sidecar 就失败
    r, m, rows, recs = _f7_case(first_fail_at=1)
    assert str(r).startswith("SystemExit"), "原始异常必须继续传播：%r" % (r,)
    assert "sidecar 写入失败" in str(r), "原始异常信息被改写：%r" % (r,)
    assert len(rows) == 2, "中止前的 2 条成功尝试必须留记录，实际 %d 条" % len(rows)
    assert [x["txid"] for x in rows] == ["tx1", "tx2"], [x["txid"] for x in rows]
    assert recs == [], "第 1 次写入即失败，不应有 sidecar 记录"
    assert m["meta_stage"] == "run_aborted", m.get("meta_stage")
    assert m["usable_as_sample"] is False and m["partial"] is True, m
    assert m["records_complete"] is True, m
    assert "sidecar 写入失败" in (m.get("abort_exception") or ""), m.get("abort_exception")

    # (b) 第 3 次写 sidecar 时失败
    r2, m2, rows2, recs2 = _f7_case(first_fail_at=3)
    assert str(r2).startswith("SystemExit"), r2
    assert len(rows2) == 4, "应保住 2 成功 + 2 失败共 4 行，实际 %d" % len(rows2)
    assert [x["txid"] for x in rows2 if x["txid"]] == ["tx1", "tx2"], \
        [x["txid"] for x in rows2]
    assert sum(1 for x in rows2 if x["failure_class"]) == 2, rows2
    assert len(recs2) == 2, "sidecar 应恰好有 2 条（第 3 条写入失败）：%d" % len(recs2)
    assert m2["meta_stage"] == "run_aborted" and m2["usable_as_sample"] is False, m2
    assert m2["abort_rows"] == 4 and m2["records_complete"] is True, m2
    run_id = recs2[0]["run_id"]
    assert {x["attempt_id"] for x in recs2} == {"%s:3" % run_id, "%s:4" % run_id}, recs2
    # 已落盘的失败行与已写入的 sidecar 仍一一对应（局部自洽）
    fails_csv = {"%s:%d" % (run_id, int(x["round"])) for x in rows2 if x["failure_class"]}
    assert fails_csv == {x["attempt_id"] for x in recs2}, (fails_csv, recs2)


def s10():
    """F7：连 CSV 补写都失败时，**不得覆盖原始异常**，且须在 meta 留下落盘失败痕迹。"""
    r, m, rows, _ = _f7_case(first_fail_at=1, csv_broken=True)
    assert str(r).startswith("SystemExit"), r
    assert "sidecar 写入失败" in str(r), "原始异常被落盘异常覆盖：%r" % (r,)
    assert rows == [], "CSV 补写失败时不应有 rounds.csv"
    assert m["usable_as_sample"] is False and m["partial"] is True, m
    assert m["records_complete"] is False, m
    assert "No space left" in (m.get("csv_flush_error") or ""), m.get("csv_flush_error")


def s11():
    """F7 下游：`usable_as_sample=False` 的 run 不进入拟合输入；无 meta 的旧 run 不受影响。"""
    fm = FM

    tmp = tempfile.mkdtemp(prefix="f7_s11_")
    try:
        def mk(d, meta):
            os.makedirs(d)
            if meta is not None:
                with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
                    json.dump(meta, f)
            with open(os.path.join(d, "rounds.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cb.COLUMNS, extrasaction="ignore")
                w.writeheader()
                w.writerow({"round": 1, "target_spend": 2, "target_output": 2,
                            "sapling_spends": 2, "sapling_outputs": 2,
                            "sapling_proofs": 4, "pipeline": 1234.0, "txid": "t",
                            "form_match": 1, "fee_match": 1})
        mk(os.path.join(tmp, "run_ok"), {"meta_stage": "run_end"})
        mk(os.path.join(tmp, "run_aborted"),
           {"meta_stage": "run_aborted", "partial": True, "usable_as_sample": False})
        rows = fm.load_all(tmp)
        assert len(rows) == 1, "中止的 run 必须被排除，实际读到 %d 行" % len(rows)
        mk(os.path.join(tmp, "run_old"), None)          # 兼容性：无 meta.json 的旧 run
        assert len(fm.load_all(tmp)) == 2, "无 meta 的旧 run 不应被排除"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=== C 组：code / 措辞映射 ===")
    for n, f in [("C1 -4 资金不足（经提案）", c1), ("C2 -6 资金不足", c2),
                 ("C3 -8 隐私策略拒绝", c3), ("C4 -8 地址格式参数错误", c4),
                 ("C5 -8 反向用例：unknown privacy policy", c5),
                 ("C6 -5 地址或密钥", c6), ("C7 未知码保留原码", c7),
                 ("C8 -32602 请求 schema", c8)]:
        check(n, f)

    print("\n=== R 组：历史回放与回归 ===")
    check_hist("R1 历史 -8 原文回放（3 条）", r1, GATE_RUN)
    check("R2 前置同步超时不变", r2)
    check("R3 opid 终态失败不变", r3)
    check("R4 轮询超时（原误判策略拒绝）", r4)

    print("\n=== I 组：不变量 ===")
    check("I1 params 逐字节 + timeout=120", i1)
    check("I2 计时区间", i2)
    check_hist("I3 成功口径 7/7/7/7", i3, GATE_RUN)
    check("I4 COLUMNS 36 列前 30 同序", i4)
    check("I5 recipient_* 不受影响", i5)
    check_hist("I6 dry-run 列结构与 note 全等", i6, DRY_RUN)
    check("I7 sidecar 行数 + 超长不截断", i7)
    check("I8 attempt_id 双向齐全", i8)

    print("\n=== S 组：状态与证据 ===")
    check("S1 传输异常 -> unknown/不可替换", s1)
    check("S2 被拒 -> not_submitted/不重试", s2)
    check("S3 sidecar 完整性", s3)
    check("S4 5000 字符原文不截断", s4)
    check("S5 写入失败 fail-closed", s5)
    check("S6 replaces 留痕 + 非法值拒绝", s6)
    check("S8 提交状态不明单列（超时不得写成未产生 txid）", s8)
    check_opt("S9 F7 中止时已完成尝试仍落盘（含 txid）", s9, HAVE_RPS,
              "缺少 reporting_patch_selftest.py（%s）" % RPS_ERR)
    check_opt("S10 F7 落盘失败不覆盖原始异常", s10, HAVE_RPS,
              "缺少 reporting_patch_selftest.py（%s）" % RPS_ERR)
    check_opt("S11 F7 中止 run 被排除出拟合输入", s11, HAVE_FM,
              "缺少 numpy / fit_sapling_e2e_model（%s）" % FM_ERR)
    check_opt("S7 main() 端到端：sidecar 与 CSV 自洽", s7, HAVE_RPS,
              "缺少 reporting_patch_selftest.py（%s）" % RPS_ERR)

    ok = [r for r in RESULTS if r[1]]
    bad = [r for r in RESULTS if not r[1]]
    print("\n===== 结果：%d 通过 / %d 失败 / %d 跳过 =====" % (len(ok), len(bad), len(SKIPPED)))
    for n, msg in SKIPPED:
        print("  SKIP %s（%s）" % (n, msg))
    for n, _ok, msg in bad:
        print("  FAIL %s : %s" % (n, msg))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
