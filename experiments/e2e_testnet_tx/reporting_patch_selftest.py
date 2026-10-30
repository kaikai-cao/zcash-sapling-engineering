# -*- coding: utf-8 -*-
"""reporting-only 补丁的合成数据测试。

不触碰节点/钱包/快照：把 preflight / 恢复 / 发交易全部替换成假实现，
只验证 main() 的**报告层**行为（gate_summary 措辞、meta 自描述、自洽性硬校验）。
"""
import csv
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import confirmatory_bench as CB  # noqa: E402

MATRIX = [(1, 2), (2, 2), (4, 2), (7, 2), (10, 2), (17, 2), (1, 9), (3, 2), (3, 3), (4, 3)]
FAKE_SNAP = "aa" * 32
FAKE_SCRIPT = "bb" * 32


class DummySampler(object):
    def __init__(self, path):
        self.path = path

        class _E(object):
            def set(self):
                pass

        self.stop_evt = _E()

    def start(self):
        pass

    def join(self, timeout=None):
        pass


def patch_common():
    CB.tee_stdio = lambda p: None
    CB.find_pids = lambda: []
    CB.Sampler = DummySampler
    CB.preflight = lambda: {"snapshot_sha256": FAKE_SNAP, "snapshot_sha256_match": True,
                            "restore_script_sha256": FAKE_SCRIPT,
                            "restore_script_sha256_match": True}


def mkrow(idx, S, O, dry, txid=None, fm=None, fem=None):
    """构造一条 rounds 行，字段与真实执行器一致。"""
    return {
        "round": idx, "target_spend": S, "target_output": O,
        "actual_spend": (S if txid else None), "actual_output": (O if txid else None),
        "form_match": fm, "fee_match": fem, "policy": "FullPrivacy",
        "txid": txid or "", "opid": "", "submit": "", "pipeline": "", "mine": "", "sync": "",
        "total": "", "sapling_spends": "", "sapling_outputs": "", "sapling_proofs": "",
        "tx_size": "", "fee_zat": "", "expected_fee_zat": 5000 * max(S, O),
        "planned_amount_zat": 1, "recipients": "", "restored_height": 32297,
        "restored_note_count": 36, "snapshot_sha256": FAKE_SNAP,
        "restore_script_sha256": FAKE_SCRIPT, "dry_run": 1 if dry else 0,
        "failure_class": "", "error": "",
    }


def run_main(argv, fake_attempt):
    CB.do_one_attempt = fake_attempt
    sys.argv = ["confirmatory_bench.py"] + argv
    try:
        CB.main()
        return "OK"
    except SystemExit as e:
        return "SystemExit: %s" % e
    except Exception as e:  # noqa: BLE001
        return "%s: %s" % (type(e).__name__, e)


def read_summary(rundir, name="gate_summary.csv"):
    with open(os.path.join(rundir, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_meta(rundir):
    with open(os.path.join(rundir, "meta.json"), encoding="utf-8") as f:
        return json.load(f)


def find_rundir(base):
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "meta.json")):
            return p
    raise AssertionError("未找到 run 目录: %s" % base)


FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="reporting_test_")
    patch_common()

    # ---------- T1: dry-run 汇总措辞 + meta 自描述 ----------
    print("\n[T1] dry-run: 汇总措辞与 meta 自描述")
    base1 = os.path.join(tmp, "t1")
    counter = {"i": 0}

    def fake_dry(idx, S, O, policy, mine_blocks, dry_run, restore, ah, asm, ahm):
        counter["i"] += 1
        return mkrow(idx, S, O, dry=True), None

    r = run_main(["--mode", "gate", "--dry-run", "--outdir-base", base1], fake_dry)
    check("main 正常返回", r == "OK", r)
    rd = find_rundir(os.path.join(base1, "_feasibility_gate"))
    rows = read_summary(rd)
    check("汇总 10 行", len(rows) == 10, str(len(rows)))
    check("note 全部为 dry-run 措辞",
          all(x["note"].startswith("dry-run：地址准备与构造已完成") for x in rows),
          rows[0]["note"] if rows else "")
    check("note 不再出现'无成功构造'", all("无成功构造" not in x["note"] for x in rows))
    m = read_meta(rd)
    check("meta.dry_run is True", m.get("dry_run") is True, repr(m.get("dry_run")))
    check("meta.real_tx is False", m.get("real_tx") is False, repr(m.get("real_tx")))
    check("meta.snapshot_sha256 已写入", m.get("snapshot_sha256") == FAKE_SNAP, repr(m.get("snapshot_sha256")))
    check("meta.restore_script_sha256 已写入", m.get("restore_script_sha256") == FAKE_SCRIPT)
    check("meta.meta_stage == run_end", m.get("meta_stage") == "run_end", repr(m.get("meta_stage")))
    check("meta.rows_with_txid == 0", m.get("rows_with_txid") == 0, repr(m.get("rows_with_txid")))
    check("meta.dry_run_consistent is True", m.get("dry_run_consistent") is True)
    check("统计口径未变（tx_success 仍为 0）", all(x["tx_success"] == "0" for x in rows))

    # ---------- T2: 正式模式，全部匹配 ----------
    print("\n[T2] 正式模式(非 dry-run): 全部 form/fee 匹配")
    base2 = os.path.join(tmp, "t2")

    def fake_real(idx, S, O, policy, mine_blocks, dry_run, restore, ah, asm, ahm):
        return mkrow(idx, S, O, dry=False, txid="%064x" % idx, fm=True, fem=True), None

    r = run_main(["--mode", "gate", "--outdir-base", base2], fake_real)
    check("main 正常返回", r == "OK", r)
    rd2 = find_rundir(os.path.join(base2, "_feasibility_gate"))
    rows2 = read_summary(rd2)
    check("note 为空（全部匹配）", all(x["note"] == "" for x in rows2), rows2[0]["note"] if rows2 else "")
    check("tx_success == 1 每形态", all(x["tx_success"] == "1" for x in rows2))
    check("all_match == 1 每形态", all(x["all_match"] == "1" for x in rows2))
    m2 = read_meta(rd2)
    check("meta.dry_run is False", m2.get("dry_run") is False, repr(m2.get("dry_run")))
    check("meta.real_tx is True", m2.get("real_tx") is True)
    check("meta.rows_with_txid == 10", m2.get("rows_with_txid") == 10, repr(m2.get("rows_with_txid")))
    check("有效成功计数 10 形态各 1",
          all(v == 1 for v in m2.get("valid_successes_per_form", {}).values()),
          str(m2.get("valid_successes_per_form")))

    # ---------- T3: 正式模式，有 txid 但形态不符 ----------
    print("\n[T3] 正式模式: 成功构造但 form_match=False → 原措辞保留")
    base3 = os.path.join(tmp, "t3")

    def fake_mismatch(idx, S, O, policy, mine_blocks, dry_run, restore, ah, asm, ahm):
        return mkrow(idx, S, O, dry=False, txid="%064x" % idx, fm=False, fem=True), None

    r = run_main(["--mode", "gate", "--outdir-base", base3], fake_mismatch)
    check("main 正常返回", r == "OK", r)
    rd3 = find_rundir(os.path.join(base3, "_feasibility_gate"))
    rows3 = read_summary(rd3)
    check("note 为'成功构造但形态或手续费不符'",
          all(x["note"].startswith("成功构造但形态或手续费不符") for x in rows3),
          rows3[0]["note"] if rows3 else "")
    check("统计口径未变（tx_success 仍为 1）", all(x["tx_success"] == "1" for x in rows3))

    # ---------- T4: dry_run=True 却出现 txid → 硬停 ----------
    print("\n[T4] 自洽性硬校验: dry_run=True 但带 txid")
    base4 = os.path.join(tmp, "t4")

    def fake_bad(idx, S, O, policy, mine_blocks, dry_run, restore, ah, asm, ahm):
        return mkrow(idx, S, O, dry=True, txid="%064x" % idx, fm=True, fem=True), None

    r = run_main(["--mode", "gate", "--dry-run", "--outdir-base", base4], fake_bad)
    check("抛出 SystemExit 且信息含'拒绝写出可被误读'",
          r.startswith("SystemExit") and "拒绝写出可被误读" in r, r)

    # ---------- T5: meta 是否真的"运行开始"就写好（在第一次尝试时探测） ----------
    print("\n[T5] meta 在运行开始即写入（首次尝试时探测磁盘）")
    base5 = os.path.join(tmp, "t5")
    seen = {}

    def fake_probe(idx, S, O, policy, mine_blocks, dry_run, restore, ah, asm, ahm):
        if not seen:
            rd = find_rundir(os.path.join(base5, "_feasibility_gate"))
            seen["files"] = sorted(os.listdir(rd))
            seen["meta"] = read_meta(rd)
        return mkrow(idx, S, O, dry=True), None

    r = run_main(["--mode", "gate", "--dry-run", "--outdir-base", base5], fake_probe)
    check("main 正常返回", r == "OK", r)
    m5 = seen.get("meta", {})
    check("首次尝试时 meta.json 已存在", "meta.json" in seen.get("files", []), str(seen.get("files")))
    check("首次尝试时 meta_stage == run_start", m5.get("meta_stage") == "run_start", repr(m5.get("meta_stage")))
    check("首次尝试时 dry_run is True", m5.get("dry_run") is True, repr(m5.get("dry_run")))
    check("首次尝试时 snapshot_sha256 已可溯源", m5.get("snapshot_sha256") == FAKE_SNAP,
          repr(m5.get("snapshot_sha256")))
    check("首次尝试时尚未有结果文件（rounds.csv/gate_summary.csv）",
          "rounds.csv" not in seen.get("files", []) and "gate_summary.csv" not in seen.get("files", []),
          str(seen.get("files")))

    # ---------- T6: 预注册常量未被改动 ----------
    print("\n[T6] 预注册口径常量")
    check("MAX_ATTEMPTS_PER_FORM == 8", CB.MAX_ATTEMPTS_PER_FORM == 8, str(CB.MAX_ATTEMPTS_PER_FORM))
    check("TARGET_SUCCESS_PER_FORM == 5", CB.TARGET_SUCCESS_PER_FORM == 5, str(CB.TARGET_SUCCESS_PER_FORM))
    check("门禁与正式目录分离（gate 写 _feasibility_gate）",
          "_feasibility_gate" in os.path.join(base1, "_feasibility_gate"))

    # ---------- T7: 分析器仍排除 _feasibility_gate ----------
    print("\n[T7] 分析器排除 _feasibility_gate（合成 CSV）")
    try:
        import fit_sapling_e2e_model as FIT
    except ImportError as e:
        print("  [SKIP] 当前解释器缺依赖（%s）；请用带 numpy 的解释器单独跑 T7" % e)
        FIT = None
    if FIT is not None:
        raw = os.path.join(tmp, "raw")
        os.makedirs(os.path.join(raw, "_feasibility_gate", "run_x"))
        os.makedirs(os.path.join(raw, "run_y"))
        cols = ["round", "target_spend", "target_output", "actual_spend", "actual_output",
                "form_match", "fee_match", "policy", "txid", "opid", "submit", "pipeline",
                "mine", "sync", "total", "sapling_spends", "sapling_outputs", "sapling_proofs",
                "tx_size", "fee_zat", "expected_fee_zat", "planned_amount_zat", "recipients",
                "restored_height", "restored_note_count", "snapshot_sha256",
                "restore_script_sha256", "dry_run", "failure_class", "error"]

        def write_csv(path, pipeline):
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                for i in range(2):
                    row = {c: "" for c in cols}
                    row.update({"round": i + 1, "target_spend": 1, "target_output": 2,
                                "actual_spend": 1, "actual_output": 2, "form_match": "True",
                                "fee_match": "True", "policy": "FullPrivacy",
                                "txid": "ab" * 32, "pipeline": pipeline, "sapling_spends": 1,
                                "sapling_outputs": 2, "sapling_proofs": 1, "fee_zat": 10000,
                                "expected_fee_zat": 10000, "dry_run": 0})
                    w.writerow(row)

        write_csv(os.path.join(raw, "_feasibility_gate", "run_x", "rounds.csv"), 999999)
        write_csv(os.path.join(raw, "run_y", "rounds.csv"), 7)
        got = FIT.load_all(raw)
        check("门禁目录被排除（无 999999 记录）", all(r.get("pipeline") != "999999" for r in got),
              str(sorted({r.get("pipeline") for r in got})))
        check("正式目录被读入（存在 7）", any(r.get("pipeline") == 7 for r in got),
              str(sorted({r.get("pipeline") for r in got})))

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n===== 结果：%s =====" % ("全部通过" if not FAILS else "存在失败 %s" % FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
