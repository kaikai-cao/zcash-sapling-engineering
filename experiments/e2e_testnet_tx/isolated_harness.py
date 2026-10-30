#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""干净克隆复跑（代码验证，非正式实验）。

目标：在干净克隆中驱动真实执行器（main / run_one / _classify / _campaign_continue /
sidecar / summary_by_shape.csv），但以**完全伪造的外部依赖**隔离实时钱包、Zebra/Zallet
RPC 与真实交易。不启动任何服务、不发送任何交易。

覆盖：
  D2 opid_timeout 的 G4 裁决入口：
    - 默认无 G4 裁决 -> 停止
    - accepted       -> 停止（禁止重发）
    - unaccepted     -> 允许继续（按预注册）
    - 缺失/非法/无法读取裁决 -> 默认停止
  underpowered：提前停止且有效成功不足目标 -> TRUE；达目标 -> FALSE
  D1 / D3 不回归：D1a 继续、@A 继续、@B 单次恢复后停止、@C 立即停止
  sidecar 关联（attempt_id）与汇总输出一致
  G4 JSON 严格校验（重复键/非法值 fail-closed）与真实文件经 --g4-verdicts 的端到端匹配

所有外部 I/O（sapling_e2e_bench、preflight、restore、verify_state、send_frozen 等）
均在本进程内伪造，原文件不动。
"""
import sys, os, json, types, io, contextlib, re, tempfile, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = HERE
CLONE_PY = os.path.join(HERE, "confirmatory_bench.py")

# 所有临时产物落在系统临时目录，不写仓库、不碰 confirmatory_bench.py 原文件。
OUTBASE = tempfile.mkdtemp(prefix="e2e_isolated_")
print("[harness] 工作目录: %s" % OUTBASE)

# ---------------------------------------------------------------------------
# 1) 伪造 sapling_e2e_bench，注入 sys.modules 以阻止真实 RPC 模块被导入/执行
# ---------------------------------------------------------------------------
fake = types.ModuleType("sapling_e2e_bench")
fake.z = lambda *a, **k: None
fake.b = lambda *a, **k: None
fake.height = lambda *a, **k: 32297
fake.wait_sync = lambda *a, **k: (0.0, 0.0, 0.0)
fake.advance = lambda *a, **k: (0, 0.0)
fake.sapling_ua = lambda *a, **k: "fakeUA"
fake.pools = {}
fake.sapling_zat = lambda *a, **k: 100000000
fake.view_tx = lambda *a, **k: {}
fake.tee_stdio = lambda *a, **k: None
class FakeSampler:
    def __init__(self, *a, **k):
        self.stop_evt = types.SimpleNamespace(set=lambda: None)
    def start(self):
        pass
    def join(self, *a, **k):
        pass
fake.Sampler = FakeSampler
fake.find_pids = lambda *a, **k: []
fake.rss_kb = lambda *a, **k: 0
fake.STAGES = []
fake.build_amounts = lambda recipients, amount_zec: [{"address": r, "amount": amount_zec} for r in recipients]
fake.COOKIE = "/x"
fake.ACCOUNT = 0
fake.tx_size = lambda *a, **k: 100
fake._post = lambda *a, **k: ("", None)
fake.zauth = lambda *a, **k: {}
fake.ZA = ("http://x", 1)
sys.modules["sapling_e2e_bench"] = fake

sys.path.insert(0, REPO)
import confirmatory_bench as CB

# ---------------------------------------------------------------------------
# 2) 用伪造实现替换所有外部依赖（仅运行时注入，不改动仓库文件）
# ---------------------------------------------------------------------------
CB.preflight = lambda: {"snapshot_sha256": "snap", "snapshot_sha256_match": True,
                        "restore_script_sha256": "script", "restore_script_sha256_match": True}
CB.tee_stdio = lambda *a, **k: None
CB.find_pids = lambda *a, **k: []
CB.restore_snapshot = lambda *a, **k: ("snapsha", "scrsha")
CB.note_inventory = lambda *a, **k: [100000] * 40
CB.pick_amount_zat = lambda S, O, inv: {"amount_zat": 1000, "fee_zat": 5000 * max(S, O),
                                        "unit_zat": 500, "n_recip": max(1, O - 1)}
CB.prepare_recipients = lambda n_recip, sender=None, budget=None: {
    "recipients": ["addr%d" % i for i in range(max(1, int(n_recip)))],
    "div_indices": [0], "receiver_types": ["sapling"],
    "derivation_attempts": 1, "validation": "L1+L1.5+L2"}
CB.wait_sync = lambda *a, **k: (0.0, 0.0, 0.0)
CB.advance = lambda *a, **k: (0, 0.0)
CB.height = lambda *a, **k: 32297
CB.sapling_zat = lambda *a, **k: 100000000
CB.tx_size = lambda *a, **k: 100
CB.build_amounts = lambda recipients, amount_zec: [{"address": r, "amount": amount_zec} for r in recipients]
CB.sapling_ua = lambda *a, **k: "fakeUA"

# 场景上下文
H = {"restore": False, "g4_default": None, "use_g4_file": None,
     "send_behavior": None, "restore_behavior": None}
ATT = {}
CTX = {}

# run_one 包装：记录每个 (S,O) 的尝试序号，并暂存 S/O/fee 供 view_tx/send_frozen 读取
_real_run_one = CB.run_one
def _wrap_run_one(idx, S, O, policy, mine_blocks, dry_run, state, from_ua):
    ATT[(S, O)] = ATT.get((S, O), 0) + 1
    CTX["S"], CTX["O"], CTX["att"], CTX["fee"] = S, O, ATT[(S, O)], state["pick"]["fee_zat"]
    return _real_run_one(idx, S, O, policy, mine_blocks, dry_run, state, from_ua)
CB.run_one = _wrap_run_one

# verify_state 包装：仅在 restore 场景用于按组抛出 StateVerificationError
_real_verify_state = CB.verify_state
def _wrap_verify_state(snap_sha, script_sha, S, O, allow_height_mismatch=False):
    ATT[(S, O)] = ATT.get((S, O), 0) + 1
    grp = H["restore_behavior"]
    if callable(grp):
        grp = grp((S, O), ATT[(S, O)])
    raise CB.StateVerificationError("verify failed grp %s" % grp, grp)
CB.verify_state = _wrap_verify_state

# send_frozen 伪造：按场景行为决定成功或抛错（关键：opid_timeout 必须 submit_state="unknown"）
def _fake_send_frozen(from_ua, amounts, policy, timeout_op=600):
    act = H["send_behavior"]
    if callable(act):
        act = act(CTX["S"], CTX["O"], CTX["att"])
    if act == "success":
        return (10.0, 20.0, "opidX",
                {"txid": "tx_%d_%d_%d" % (CTX["S"], CTX["O"], CTX["att"]),
                 "fee_zat": CTX.get("fee")})
    if act == "opid_timeout":
        raise CB.PreTxError("stage=opid_timeout 轮询窗口耗尽（opid=opidX）",
                            stage="opid_timeout", z_sendmany_invoked=True,
                            submit_state="unknown", opid="opidX")
    if act == "d1a":
        raise CB.PreTxError("stage=submit 传输层异常",
                            stage="submit", raw_transport={"type": "conn_reset"},
                            z_sendmany_invoked=False, submit_state="not_submitted")
    if act == "d1a_unknown":
        # D1a-unknown（冻结稿第 10 行）：submit 传输异常且「是否创建 opid」不可判定
        # → submit_state=unknown；raw_transport 非空 → _classify 判为 rpc_transport_error
        raise CB.PreTxError("stage=submit 传输层异常（受理状态不可判定）",
                            stage="submit", raw_transport={"type": "conn_reset"},
                            z_sendmany_invoked=True, submit_state="unknown")
    if act == "insufficient":
        raise CB.PreTxError("stage=opid_failed 资金不足",
                            stage="opid_failed",
                            raw_error={"code": -6, "message": "Insufficient funds"},
                            z_sendmany_invoked=True, submit_state="submitted")
    if act == "other":
        raise CB.PreTxError("stage=submit RPC 拒绝",
                            stage="submit",
                            raw_error={"code": -8, "message": "Invalid parameter"},
                            z_sendmany_invoked=True, submit_state="not_submitted")
    if act in ("mismatch_both", "mismatch_form"):
        # M7 场景：发送成功但回查形态/手续费不符（CTX["mismatch"] 供 view_tx 读取）
        CTX["mismatch"] = act
        return (10.0, 20.0, "opidX",
                {"txid": "tx_%d_%d_%d" % (CTX["S"], CTX["O"], CTX["att"]),
                 "fee_zat": CTX.get("fee")})
    raise RuntimeError("unknown send_behavior %r" % act)
CB.send_frozen = _fake_send_frozen

# view_tx 伪造：返回与当前形态一致的实际形态/手续费（仅成功路径用）；
# CTX["mismatch"] 为 mismatch_both / mismatch_form 时按 M7 场景返回不符值。
def _fake_view_tx(txid):
    mm = CTX.get("mismatch")
    if mm == "mismatch_both":      # 形态与手续费同时不符 → fee 优先
        return {"spends": (CTX.get("S") or 0) + 1, "outputs": CTX.get("O"),
                "fee_zat": (CTX.get("fee") or 0) + 1}
    if mm == "mismatch_form":      # 仅形态不符 → form_mismatch
        return {"spends": (CTX.get("S") or 0) + 1, "outputs": CTX.get("O"),
                "fee_zat": CTX.get("fee")}
    return {"spends": CTX.get("S"), "outputs": CTX.get("O"),
            "fee_zat": CTX.get("fee")}
CB.view_tx = _fake_view_tx

# G4 裁决加载伪造：默认行为走 G4Map（任意 key 返回固定裁决）；可强制读取真实文件以测缺失/非法
class G4Map(dict):
    def __init__(self, default="undecided"):
        self._default = default
    def get(self, key, default=None):
        if key in self:
            return self[key]
        return self._default
_real_load_g4 = CB._load_g4_verdicts
def _fake_load_g4(path):
    if H["use_g4_file"] is not None:
        return _real_load_g4(H["use_g4_file"])       # 读真实文件：缺失/非法/损坏
    if H["g4_default"] is None:
        return _real_load_g4(None)                   # 真实默认：无 --g4-verdicts -> {}
    return G4Map(H["g4_default"])
CB._load_g4_verdicts = _fake_load_g4

# ---------------------------------------------------------------------------
# 3) 场景运行器
# ---------------------------------------------------------------------------
def read_csv(path):
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def parse_rundir(out):
    m = re.search(r"\[log\]\s+(\S+)", out)
    if not m:
        raise RuntimeError("找不到 rundir：\n" + out[-500:])
    return os.path.dirname(m.group(1))

def load_outputs(rundir):
    summary = os.path.join(rundir, "summary_by_shape.csv")
    if not os.path.isfile(summary):
        summary = os.path.join(rundir, "gate_summary.csv")
    rounds = os.path.join(rundir, "rounds.csv")
    sidecar = os.path.join(rundir, "errors.jsonl")
    meta = os.path.join(rundir, "meta.json")
    return {
        "summary": read_csv(summary) if os.path.isfile(summary) else [],
        "rounds": read_csv(rounds) if os.path.isfile(rounds) else [],
        "sidecar": [json.loads(l) for l in open(sidecar, encoding="utf-8") if l.strip()]
                    if os.path.isfile(sidecar) else [],
        "meta": json.load(open(meta, encoding="utf-8")) if os.path.isfile(meta) else {},
    }

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail else ""))

def run_scenario(matrix_rows, behavior, *, restore=False, g4_default=None,
                 use_g4_file=None, max_attempts=8, target=5, restore_behavior=None,
                 mode="confirm", real_g4_file=None):
    ATT.clear(); CTX.clear()
    H["restore"] = restore
    H["send_behavior"] = behavior
    H["restore_behavior"] = restore_behavior
    H["g4_default"] = g4_default
    H["use_g4_file"] = use_g4_file
    mdir = tempfile.mkdtemp(prefix="m_", dir=OUTBASE)
    mpath = os.path.join(mdir, "matrix.csv")
    with open(mpath, "w", newline="") as f:
        for (S, O) in matrix_rows:
            f.write("%d,%d\n" % (S, O))
    runroot = tempfile.mkdtemp(prefix="run_", dir=OUTBASE)
    argv = ["cb.py", "--mode", mode, "--matrix", mpath, "--outdir-base", runroot,
            "--max-attempts", str(max_attempts), "--target-success", str(target),
            "--seed", "20261030", "--mine-blocks", "0"]
    if not restore:
        argv.append("--no-restore")
    if real_g4_file:
        argv += ["--g4-verdicts", real_g4_file]
    old = sys.argv
    sys.argv = argv
    buf = io.StringIO()
    rc = None
    try:
        with contextlib.redirect_stdout(buf):
            rc = CB.main()
    finally:
        sys.argv = old
    out = buf.getvalue()
    rundir = parse_rundir(out)
    return {"rc": rc, "out": out, "rundir": rundir, **load_outputs(rundir)}

def verify_sidecar(name, o):
    m = re.search(r"\[verify\] 失败轮=(\d+) sidecar 行=(\d+)", o["out"])
    if not m:
        check(name + "/sidecar_line", False, "未找到 verify 行")
        return
    fr, sr = int(m.group(1)), int(m.group(2))
    check(name + "/sidecar_consistent", fr == sr == len(o["sidecar"]),
          "失败轮=%d sidecar行=%d 实际=%d" % (fr, sr, len(o["sidecar"])))

# ---------------------------------------------------------------------------
# 4) 直接单元测试：_load_g4_verdicts / _campaign_continue / _classify
# ---------------------------------------------------------------------------
print("=" * 78)
print("A. 直接单元测试（_load_g4_verdicts / _campaign_continue / _classify）")
print("=" * 78)

# A1 _load_g4_verdicts 各种输入（直接调用真实实现 _real_load_g4，绕过测试用 monkeypatch）
with open(os.path.join(OUTBASE, "g4_valid.json"), "w") as f:
    json.dump({"run_x:1": "unaccepted", "run_x:2": "accepted"}, f)
with open(os.path.join(OUTBASE, "g4_bad.json"), "w") as f:
    f.write("{not valid json")
with open(os.path.join(OUTBASE, "g4_list.json"), "w") as f:
    json.dump(["a", "b"], f)
check("g4/None->empty", _real_load_g4(None) == {}, str(_real_load_g4(None)))
check("g4/missing_file->empty", _real_load_g4("/no/such/file.json") == {})
check("g4/invalid_json->empty", _real_load_g4(os.path.join(OUTBASE, "g4_bad.json")) == {})
check("g4/list_not_dict->empty", _real_load_g4(os.path.join(OUTBASE, "g4_list.json")) == {})
gv = _real_load_g4(os.path.join(OUTBASE, "g4_valid.json"))
check("g4/valid_dict_normalized", gv == {"run_x:1": "unaccepted", "run_x:2": "accepted"}, str(gv))
check("g4/illegal_value_kept",
      _real_load_g4(os.path.join(OUTBASE, "g4_valid.json")).get("run_x:1") == "unaccepted")

# A1b 严格校验：重复键 / 非法值 / 非精确大小写 均 fail-closed（整份拒绝 -> {}）
with open(os.path.join(OUTBASE, "g4_dup.json"), "w") as f:
    f.write('{"run_x:1": "accepted", "run_x:1": "unaccepted"}')   # 重复键
with open(os.path.join(OUTBASE, "g4_illegal.json"), "w") as f:
    json.dump({"run_x:1": "maybe"}, f)                            # 非法值
with open(os.path.join(OUTBASE, "g4_case.json"), "w") as f:
    json.dump({"run_x:1": "UNACCEPTED"}, f)                       # 大小写不符，精确匹配应拒绝
check("g4/dup_key->empty", _real_load_g4(os.path.join(OUTBASE, "g4_dup.json")) == {},
      "重复键应整份拒绝")
check("g4/illegal_value->empty", _real_load_g4(os.path.join(OUTBASE, "g4_illegal.json")) == {},
      "非法值应整份拒绝")
check("g4/case_mismatch->empty", _real_load_g4(os.path.join(OUTBASE, "g4_case.json")) == {},
      "非精确大小写应拒绝")
# 其它 run 的键：保留（支持多 run 文件），但当前 run 不应命中
with open(os.path.join(OUTBASE, "g4_foreign.json"), "w") as f:
    json.dump({"other_run:1": "unaccepted"}, f)
gf = _real_load_g4(os.path.join(OUTBASE, "g4_foreign.json"))
check("g4/foreign_key_kept_not_current", gf == {"other_run:1": "unaccepted"},
      "其它 run 的键应保留但当前 run 不匹配 -> 默认 undecided")

# A2 _campaign_continue 裁决矩阵
cc = CB._campaign_continue
check("cc/opid_timeout/undecided->stop", cc("opid_timeout", "opid_timeout", "unknown", "undecided") is False)
check("cc/opid_timeout/accepted->stop", cc("opid_timeout", "opid_timeout", "unknown", "accepted") is False)
check("cc/opid_timeout/unaccepted->continue", cc("opid_timeout", "opid_timeout", "unknown", "unaccepted") is True)
check("cc/opid_timeout/garbage->stop", cc("opid_timeout", "opid_timeout", "unknown", "garbage") is False)
check("cc/D1a/transport_notsubmitted->continue",
      cc("rpc_transport_error", "submit", "not_submitted", "undecided") is True)
check("cc/rpc_transport/unknown->stop",
      cc("rpc_transport_error", "status_poll", "unknown", "undecided") is False)
# D1a-unknown（冻结稿第 10 行：rpc_transport_error@submit@unknown）——G4 先行
check("cc/rpc_transport/submit_unknown/undecided->stop",
      cc("rpc_transport_error", "submit", "unknown", "undecided") is False)
check("cc/rpc_transport/submit_unknown/unaccepted->continue",
      cc("rpc_transport_error", "submit", "unknown", "unaccepted") is True)
check("cc/rpc_transport/submit_unknown/accepted->stop",
      cc("rpc_transport_error", "submit", "unknown", "accepted") is False)
# G4 授权范围：G4 只对第 10 行（submit@unknown）与第 30 行（opid_timeout）生效。
# status_poll@unknown 即使 G4=unaccepted 也必须停止（G4 分支只匹配 stage=="submit"）。
check("cc/g4_scope/status_poll_unknown_unaccepted->stop",
      cc("rpc_transport_error", "status_poll", "unknown", "unaccepted") is False)
check("cc/g4_scope/status_poll_submitted_unaccepted->stop",
      cc("rpc_transport_error", "status_poll", "submitted", "unaccepted") is False)
check("cc/stateA->continue", cc("state_verification_failed@A", None, None) is True)
check("cc/opid_terminal->stop", cc("opid_terminal_failed", "opid_failed", "submitted") is False)
check("cc/other->stop", cc("other", None, None) is False)
check("cc/insufficient->stop", cc("rpc_insufficient_funds", "opid_failed", "submitted") is False)

# A3 _classify：opid_timeout 的 PreTxError -> opid_timeout，且 submit_state 透传
err = CB.PreTxError("x", stage="opid_timeout", submit_state="unknown", opid="opidX")
check("classify/opid_timeout->opid_timeout", CB._classify(err) == "opid_timeout")
check("classify/opid_timeout_submit_state_unknown",
      getattr(err, "submit_state", None) == "unknown")
err2 = CB.PreTxError("y", stage="submit", raw_transport={"type": "x"},
                     submit_state="not_submitted")
check("classify/d1a->rpc_transport_error", CB._classify(err2) == "rpc_transport_error")
err3 = CB.PreTxError("z", stage="opid_failed", raw_error={"code": -6, "message": "insufficient funds"},
                     submit_state="submitted")
check("classify/insufficient->rpc_insufficient_funds", CB._classify(err3) == "rpc_insufficient_funds")

# ---------------------------------------------------------------------------
# 5) 集成：驱动真实 main()，穿越 run_one/_classify/_campaign_continue/sidecar/summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("B. 集成测试（驱动真实 main()）")
print("=" * 78)

MATRIX = [(2, 2), (4, 2), (7, 2)]   # 多形态以证明决策与形态无关

# B1 D2 默认无 G4 裁决：opid_timeout 停止
o = run_scenario(MATRIX, "opid_timeout", g4_default=None)
print("[B1] D2 默认无 G4 -> opid_timeout 停止")
for r in o["summary"]:
    S, O = int(r["target_spend"]), int(r["target_output"])
    check("B1/(%d,%d)/attempts==1" % (S, O), int(r["attempts"]) == 1, "attempts=%s" % r["attempts"])
    check("B1/(%d,%d)/underpowered==TRUE" % (S, O), r["underpowered"] == "TRUE", "under=%s" % r["underpowered"])
cls = {row["failure_class"] for row in o["rounds"] if row.get("failure_class")}
check("B1/all_failure_class==opid_timeout", cls == {"opid_timeout"}, str(cls))
check("B1/opid_timeout_submit_state_unknown",
      all(rec.get("submit_state") == "unknown" for rec in o["sidecar"]),
      "sidecar submit_state 集合=%s" % {rec.get("submit_state") for rec in o["sidecar"]})
verify_sidecar("B1", o)

# B2 D2 accepted -> 停止（禁止重发）
o = run_scenario(MATRIX, "opid_timeout", g4_default="accepted")
print("[B2] D2 accepted -> 停止")
for r in o["summary"]:
    check("B2/(%s,%s)/attempts==1" % (r["target_spend"], r["target_output"]), int(r["attempts"]) == 1)
    check("B2/(%s,%s)/underpowered==TRUE" % (r["target_spend"], r["target_output"]), r["underpowered"] == "TRUE")
verify_sidecar("B2", o)

# B3 D2 unaccepted -> 允许继续（跑到 max-attempts）
o = run_scenario(MATRIX, "opid_timeout", g4_default="unaccepted")
print("[B3] D2 unaccepted -> 允许继续（应达 max-attempts）")
for r in o["summary"]:
    S, O = int(r["target_spend"]), int(r["target_output"])
    check("B3/(%d,%d)/attempts==max(8)" % (S, O), int(r["attempts"]) == 8, "attempts=%s" % r["attempts"])
    check("B3/(%d,%d)/underpowered==TRUE" % (S, O), r["underpowered"] == "TRUE")
verify_sidecar("B3", o)

# B4 D2 非法裁决 -> 默认停止；缺失文件 -> 默认停止
o = run_scenario(MATRIX, "opid_timeout", g4_default="garbage")
print("[B4] D2 非法裁决值(garbage) -> 停止")
for r in o["summary"]:
    check("B4/(%s,%s)/attempts==1" % (r["target_spend"], r["target_output"]), int(r["attempts"]) == 1)
o = run_scenario(MATRIX, "opid_timeout", use_g4_file="/no/such/g4.json")
print("[B4b] D2 缺失裁决文件 -> 默认停止")
for r in o["summary"]:
    check("B4b/(%s,%s)/attempts==1" % (r["target_spend"], r["target_output"]), int(r["attempts"]) == 1)
verify_sidecar("B4b", o)

# B5 underpowered 提前停止（2 次成功 + 第 3 次不可重试错误）
def early_stop_behavior(S, O, att):
    return "success" if att <= 2 else "insufficient"
o = run_scenario([(2, 2)], early_stop_behavior, g4_default=None)
print("[B5] underpowered：提前停止且有效成功<目标 -> TRUE")
r = o["summary"][0]
check("B5/valid_success==2", int(r["valid_success"]) == 2, "valid=%s" % r["valid_success"])
check("B5/attempts==3", int(r["attempts"]) == 3, "attempts=%s" % r["attempts"])
check("B5/underpowered==TRUE", r["underpowered"] == "TRUE", "under=%s" % r["underpowered"])
verify_sidecar("B5", o)

# B6 underpowered FALSE：达目标（成功路径/M7 不触发）
o = run_scenario(MATRIX, "success", g4_default=None)
print("[B6] underpowered：达目标有效成功 -> FALSE（成功路径无回归）")
for r in o["summary"]:
    S, O = int(r["target_spend"]), int(r["target_output"])
    check("B6/(%d,%d)/valid==target(5)" % (S, O), int(r["valid_success"]) == 5, "valid=%s" % r["valid_success"])
    check("B6/(%d,%d)/underpowered==FALSE" % (S, O), r["underpowered"] == "FALSE")
    check("B6/(%d,%d)/all_match" % (S, O), r["all_match"] == str(int(r["valid_success"])))
# 成功路径不应产生失败行/sidecar
check("B6/no_failures", len(o["sidecar"]) == 0 and all(not x.get("failure_class") for x in o["rounds"]))

# B7 D1a：rpc_transport_error@submit@not_submitted -> 继续（达 max-attempts）
o = run_scenario([(2, 2)], "d1a", g4_default=None)
print("[B7] D1a 继续（区别于 D2 默认停止）")
r = o["summary"][0]
check("B7/attempts==max(8)", int(r["attempts"]) == 8, "attempts=%s" % r["attempts"])
check("B7/underpowered==TRUE", r["underpowered"] == "TRUE")
verify_sidecar("B7", o)

# B8 D3：@A 继续 / @B 单次恢复后停止 / @C 立即停止（restore 路径）
o = run_scenario([(2, 2)], None, restore=True, restore_behavior=lambda s, a: "A")
print("[B8a] D3 @A 继续")
r = o["summary"][0]
check("B8a/attempts==max(8)", int(r["attempts"]) == 8, "attempts=%s" % r["attempts"])
verify_sidecar("B8a", o)

o = run_scenario([(2, 2)], None, restore=True, restore_behavior=lambda s, a: "B")
print("[B8b] D3 @B 单次受控恢复后停止")
r = o["summary"][0]
check("B8b/attempts==2", int(r["attempts"]) == 2, "attempts=%s" % r["attempts"])
check("B8b/failure_class_stateB",
      all(x.get("failure_class") == "state_verification_failed@B" for x in o["rounds"] if x.get("failure_class")),
      str({x.get("failure_class") for x in o["rounds"]}))
verify_sidecar("B8b", o)

o = run_scenario([(2, 2)], None, restore=True, restore_behavior=lambda s, a: "C")
print("[B8c] D3 @C 立即（不可行）停止")
r = o["summary"][0]
check("B8c/attempts==1", int(r["attempts"]) == 1, "attempts=%s" % r["attempts"])
verify_sidecar("B8c", o)

# B9 rpc_insufficient_funds：不再重试至最大次数（提交阶段失败，禁止重发/替换）
o = run_scenario([(2, 2)], "insufficient", g4_default=None)
print("[B9] rpc_insufficient_funds 不再重试至最大次数（应停止于 1 次）")
r = o["summary"][0]
check("B9/attempts==1", int(r["attempts"]) == 1, "attempts=%s" % r["attempts"])
check("B9/underpowered==TRUE", r["underpowered"] == "TRUE")
cls = {row.get("failure_class") for row in o["rounds"] if row.get("failure_class")}
check("B9/failure_class==rpc_insufficient_funds", cls == {"rpc_insufficient_funds"}, str(cls))
verify_sidecar("B9", o)

# B10 GATE 模式发送异常回归：异常冒泡后进入 GATE 自己的 PreTxError 分支，
# sidecar 单次写入，原有行为保持（GATE 不重试，每形态记 1 次失败）。
o = run_scenario([(2, 2), (4, 2)], "opid_timeout", g4_default=None, mode="gate")
print("[B10] GATE 发送异常：sidecar 单次写入 + 原有行为保持")
gatesum = o["summary"]
check("B10/shape_count==2", len(gatesum) == 2, "rows=%d" % len(gatesum))
for r in gatesum:
    check("B10/(%s,%s)/attempts==1" % (r["target_spend"], r["target_output"]), int(r["attempts"]) == 1)
cls = {row.get("failure_class") for row in o["rounds"] if row.get("failure_class")}
check("B10/all_failure_class==opid_timeout", cls == {"opid_timeout"}, str(cls))
if o["sidecar"]:
    rec = o["sidecar"][0]
    check("B10/sidecar_has_recipients", rec.get("recipients") is not None, str(rec.get("recipients")))
    check("B10/sidecar_has_amounts_zat", rec.get("amounts_zat") is not None, str(rec.get("amounts_zat")))
    check("B10/sidecar_has_policy", rec.get("policy") is not None, str(rec.get("policy")))
    check("B10/sidecar_has_from_ua", rec.get("from_ua") is not None, str(rec.get("from_ua")))
    verify_sidecar("B10", o)

# B11 真实 G4 文件端到端：--g4-verdicts 真实传给 _load_g4_verdicts -> main 继续/停止
# 用固定 ts 使 run_id 可预测，从而写出与当前 run 精确匹配的裁决键。
import time as _time
_orig_strftime = _time.strftime
FIXED_TS = "20261030_000000"
_time.strftime = lambda *a, **k: FIXED_TS
try:
    _rid = "run_" + FIXED_TS
    _g4e2e = os.path.join(OUTBASE, "g4_real_e2e.json")
    with open(_g4e2e, "w") as f:
        json.dump({_rid + ":1": "unaccepted"}, f)   # 仅第 1 轮有裁决
    _saved = CB._load_g4_verdicts
    CB._load_g4_verdicts = _real_load_g4            # 本场景使用真实 loader（不经 fake）
    try:
        o = run_scenario([(2, 2)], "opid_timeout", real_g4_file=_g4e2e)
    finally:
        CB._load_g4_verdicts = _saved
finally:
    _time.strftime = _orig_strftime
print("[B11] 真实 G4 文件端到端：run_id:1=unaccepted 续，run_id:2 缺失停")
r = o["summary"][0]
check("B11/attempts==2", int(r["attempts"]) == 2, "attempts=%s" % r["attempts"])
check("B11/underpowered==TRUE", r["underpowered"] == "TRUE")
check("B11/sidecar_attempt_ids_match_file",
      {rec.get("attempt_id") for rec in o["sidecar"]} == {_rid + ":1", _rid + ":2"},
      str({rec.get("attempt_id") for rec in o["sidecar"]}))
verify_sidecar("B11", o)

# B12 其它 run 的键不得误用：当前 run 缺裁决 -> 停止
_time.strftime = lambda *a, **k: FIXED_TS
try:
    _rid = "run_" + FIXED_TS
    _g4f = os.path.join(OUTBASE, "g4_foreign_e2e.json")
    with open(_g4f, "w") as f:
        json.dump({"other_run:1": "unaccepted"}, f)   # 非当前 run
    _saved = CB._load_g4_verdicts
    CB._load_g4_verdicts = _real_load_g4
    try:
        o = run_scenario([(2, 2)], "opid_timeout", real_g4_file=_g4f)
    finally:
        CB._load_g4_verdicts = _saved
finally:
    _time.strftime = _orig_strftime
print("[B12] 其它 run 的键不得误用：当前 run 缺裁决 -> 停止")
r = o["summary"][0]
check("B12/attempts==1", int(r["attempts"]) == 1, "attempts=%s" % r["attempts"])
check("B12/underpowered==TRUE", r["underpowered"] == "TRUE")
verify_sidecar("B12", o)

# B13 D1a-unknown 的 G4 先行（真实文件端到端）：rpc_transport_error@submit@unknown
#   与 opid_timeout 同机制——第 1 轮 G4=unaccepted 续，第 2 轮缺裁决停。
_time.strftime = lambda *a, **k: FIXED_TS
try:
    _rid = "run_" + FIXED_TS
    _g4f13 = os.path.join(OUTBASE, "g4_d1a_unknown_e2e.json")
    with open(_g4f13, "w") as f:
        json.dump({_rid + ":1": "unaccepted"}, f)
    _saved = CB._load_g4_verdicts
    CB._load_g4_verdicts = _real_load_g4            # 真实 loader（不经 fake）
    try:
        o = run_scenario([(2, 2)], "d1a_unknown", real_g4_file=_g4f13)
    finally:
        CB._load_g4_verdicts = _saved
finally:
    _time.strftime = _orig_strftime
print("[B13] D1a-unknown + 真实 G4 文件：第1轮 unaccepted 续，第2轮缺裁决停")
r = o["summary"][0]
check("B13/attempts==2", int(r["attempts"]) == 2, "attempts=%s" % r["attempts"])
check("B13/underpowered==TRUE", r["underpowered"] == "TRUE")
cls = {row.get("failure_class") for row in o["rounds"] if row.get("failure_class")}
check("B13/failure_class==rpc_transport_error", cls == {"rpc_transport_error"}, str(cls))
check("B13/sidecar_attempt_ids_match_file",
      {rec.get("attempt_id") for rec in o["sidecar"]} == {_rid + ":1", _rid + ":2"},
      str({rec.get("attempt_id") for rec in o["sidecar"]}))
verify_sidecar("B13", o)

# B14 D1a-unknown 无 G4 裁决时必须默认停止（fail-closed，不得自动续）
o = run_scenario([(2, 2)], "d1a_unknown", g4_default=None)
print("[B14] D1a-unknown 无 G4 裁决 -> 默认停止")
r = o["summary"][0]
check("B14/attempts==1", int(r["attempts"]) == 1, "attempts=%s" % r["attempts"])
check("B14/underpowered==TRUE", r["underpowered"] == "TRUE")
cls = {row.get("failure_class") for row in o["rounds"] if row.get("failure_class")}
check("B14/failure_class==rpc_transport_error", cls == {"rpc_transport_error"}, str(cls))
verify_sidecar("B14", o)

# B15 M7 双重不匹配 tie-break：form 与 fee 同时不符 → 手续费优先记 fee_mismatch，
#     且 rounds.csv 仍逐列保留 form_match/fee_match 两个 false（形态偏离信息不丢失）。
o = run_scenario([(2, 2)], "mismatch_both", g4_default=None)
print("[B15] M7 双重不匹配 → fee 优先（fee_mismatch），双布尔列保留")
r = o["summary"][0]
check("B15/attempts==1", int(r["attempts"]) == 1, "attempts=%s" % r["attempts"])
check("B15/underpowered==TRUE", r["underpowered"] == "TRUE")
check("B15/summary_form_match==False", r.get("form_match") in ("False", "false", "0"),
      "form_match=%s" % r.get("form_match"))
check("B15/summary_fee_match==False", r.get("fee_match") in ("False", "false", "0"),
      "fee_match=%s" % r.get("fee_match"))
cls = {row.get("failure_class") for row in o["rounds"] if row.get("failure_class")}
check("B15/failure_class==fee_mismatch", cls == {"fee_mismatch"}, str(cls))
row0 = o["rounds"][0]
check("B15/rounds_form_match==False", str(row0.get("form_match")) in ("False", "false", "0"),
      "rounds.form_match=%s" % row0.get("form_match"))
check("B15/rounds_fee_match==False", str(row0.get("fee_match")) in ("False", "false", "0"),
      "rounds.fee_match=%s" % row0.get("fee_match"))
# 关键回归：mismatch 不是失败类别、无 sidecar，**绝不能**把整个 run 标为中止
meta = o.get("meta", {})
check("B15/run_not_aborted", meta.get("meta_stage") == "run_end",
      "meta_stage=%s（mismatch 若触发 verify fatal 会变成 run_aborted）" % meta.get("meta_stage"))
check("B15/usable_as_sample_not_false", meta.get("usable_as_sample") is not False,
      "usable_as_sample=%s" % meta.get("usable_as_sample"))
check("B15/failure_rows==0", int(meta.get("failure_rows", -1)) == 0,
      "failure_rows=%s（mismatch 不计入失败轮）" % meta.get("failure_rows"))
check("B15/mismatch_rows==1", int(meta.get("mismatch_rows", -1)) == 1,
      "mismatch_rows=%s" % meta.get("mismatch_rows"))

# B16 M7 仅形态不符 → 记 form_mismatch（证明优先级不是「一律 fee」）
o = run_scenario([(2, 2)], "mismatch_form", g4_default=None)
print("[B16] M7 仅形态不符 → form_mismatch（对照 B15 证明优先级真实生效）")
r = o["summary"][0]
check("B16/attempts==1", int(r["attempts"]) == 1, "attempts=%s" % r["attempts"])
cls = {row.get("failure_class") for row in o["rounds"] if row.get("failure_class")}
check("B16/failure_class==form_mismatch", cls == {"form_mismatch"}, str(cls))
row0 = o["rounds"][0]
check("B16/rounds_form_match==False", str(row0.get("form_match")) in ("False", "false", "0"),
      "rounds.form_match=%s" % row0.get("form_match"))
check("B16/rounds_fee_match==True", str(row0.get("fee_match")) in ("True", "true", "1"),
      "rounds.fee_match=%s" % row0.get("fee_match"))

# ---------------------------------------------------------------------------
# 6) 静态检查：opid_timeout 抛出处的 submit_state 必须为 unknown（非 submitted）
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("C. 静态检查（克隆源码中 opid_timeout 抛出语义）")
print("=" * 78)
src = open(CLONE_PY, encoding="utf-8").read()
# 在 send_frozen 内部定位 opid_timeout 抛出块（跨多行，re.S 让 . 匹配换行）
m = re.search(r'stage="opid_timeout".*?submit_state="unknown"', src, re.S)
if m:
    block = m.group(0)
    check("C/opid_timeout_uses_unknown", 'submit_state="unknown"' in block, block[:160].replace("\n", " "))
    check("C/opid_timeout_not_submitted", 'submit_state="submitted"' not in block)
else:
    check("C/opid_timeout_block_found", False, "未定位 opid_timeout 抛出块")

# status_poll 抛出块必须保持 submitted（冻结稿：钱包已受理，≠ 网络确认；opid_failed 同理）
sp_states = re.findall(r'stage="status_poll",[\s\S]*?submit_state="(\w+)"', src)
check("C/status_poll_uses_submitted",
      len(sp_states) >= 3 and all(v == "submitted" for v in sp_states),
      "status_poll 抛出 submit_state 集合=%s" % set(sp_states))
check("C/status_poll_not_unknown", "unknown" not in sp_states)

# 关键诊断：G4 裁决对 opid_timeout 是否真的生效？比较 B1(无 G4) 与 B3(unaccepted) 的尝试次数
b1 = run_scenario(MATRIX, "opid_timeout", g4_default=None)
b3 = run_scenario(MATRIX, "opid_timeout", g4_default="unaccepted")
b1_att = {int(r["target_spend"]): int(r["attempts"]) for r in b1["summary"]}
b3_att = {int(r["target_spend"]): int(r["attempts"]) for r in b3["summary"]}
check("C/G4_verdict_HAS_effect_on_opid_timeout",
      b1_att != b3_att and all(v == 1 for v in b1_att.values()) and all(v == 8 for v in b3_att.values()),
      "无G4尝试=%s  unaccepted尝试=%s（应不同：无G4停于1、unaccepted续至8）" % (b1_att, b3_att))

# ---------------------------------------------------------------------------
# 7) 汇总
# ---------------------------------------------------------------------------
n_pass = sum(1 for _, ok, _ in RESULTS if ok)
n_fail = len(RESULTS) - n_pass
print("\n" + "=" * 78)
print("验证结果：%d PASS / %d FAIL（共 %d 项）" % (n_pass, n_fail, len(RESULTS)))
print("=" * 78)
if n_fail:
    print("失败项：")
    for name, ok, detail in RESULTS:
        if not ok:
            print("  - %s  %s" % (name, detail))
    raise SystemExit(1)
print("全部通过。")
