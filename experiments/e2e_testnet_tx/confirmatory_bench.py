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
  1. 恢复快照：停服 → 解包 → 重启 → 等追平（调用 wsl/snapshot_restore.sh --yes）
  2. 初始状态核验：恢复后查链高、可花费 Sapling Note 数、余额，记录并比对预期
  3. 构造：对目标 (S,O) 派生 O-1 个收款地址（预期 1 个找零 → 实际 O 输出）、
     按 note 清单选金额迫使 S 个 spend；
  4. 计时（冻结边界，沿用 sapling_e2e_bench 的单调时钟与 20ms 轮询）：
       submit   = z_sendmany RPC 往返（拿到 opid）
       pipeline = opid 返回 → 首次 status=success（含 Groth16 证明+签名+广播）
     策略冻结为单一 policy（默认 FullPrivacy），**不回退**到 AllowRevealedAmounts；
     若被拒即记失败，不偷偷换策略。
  5. 反查实际形态：z_viewtransaction 取实际 spends/outputs，记录 target vs actual；
  6. 留档：成功/失败/实际形态/手续费/策略/二进制版本全部落盘。

数据隔离：
  --mode gate    写到 raw/confirmatory_20261030/_feasibility_gate/run_<ts>/（绝不进入正式统计）
  --mode confirm 写到 raw/confirmatory_20261030/run_<ts>/
  正式分析必须用 fit_sapling_e2e_model.py --raw-dir raw/confirmatory_20201030
  （显式排除 _feasibility_gate 子目录）。

注意：本脚本在 WSL2 内运行（路径用 /mnt/d/...，调用 bash 子进程）。
"""

import argparse
import csv
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import time

# 复用既有基准脚本的 RPC / 计时 / 形态反查实现，保证 submit/pipeline 边界完全一致
from sapling_e2e_bench import (
    z, b, height, wait_sync, advance, sapling_ua, pools, sapling_zat,
    view_tx, tee_stdio, Sampler, find_pids, rss_kb, STAGES, build_amounts,
    COOKIE, ACCOUNT,
)

# ---------------------------------------------------------------------------
# 冻结的环境常量（与预注册 §1 / DEVIATIONS §1 一致）
# ---------------------------------------------------------------------------
SNAPSHOT_WSL = "/mnt/d/Research/z3/snapshots/z3_regtest_h32297_20261029_145710.tar.gz"
SNAPSHOT_SHA256 = "ca35201887b8041b44c483ad258a718f4a74787c02c4ff9dbbb202857b09510c"
SNAPSHOT_TARGET_HEIGHT = 32297          # 快照恢复后的预期链高（文件名编码，非 ZIP212 门槛 32257）
WSL_DIR = "/mnt/d/Research/z3/wsl"
RESTORE_SCRIPT = os.path.join(WSL_DIR, "snapshot_restore.sh")
PRE_REG_SEED = 20261030                 # 正式测量随机顺序的固定种子（预注册 §6）
FROZEN_POLICY = "FullPrivacy"           # 策略冻结：单一 policy，不回退（预注册 §5/用户审阅 §3）
OUTDIR_BASE = "raw/confirmatory_20261030"

# 候选矩阵（预注册 §4，10 种形态，每格目标 5 次成功；门禁每格 1 次）
DEFAULT_MATRIX = [
    (1, 2), (2, 2), (4, 2), (7, 2), (10, 2), (17, 2),
    (1, 9), (3, 2), (3, 3), (4, 3),
]
MAX_ATTEMPTS_PER_FORM = 8               # 每格最多尝试次数（预注册 §4）
TARGET_SUCCESS_PER_FORM = 5             # 每格目标成功次数（预注册 §4）


# ---------------------------------------------------------------------------
# 快照恢复与状态核验
# ---------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def restore_snapshot(allow_hash_mismatch=False):
    """停服 → 解包 → 重启 → 等追平（委托 snapshot_restore.sh）。

    返回快照实际 SHA256（用于与冻结值比对并记录）。
    """
    if not os.path.isfile(RESTORE_SCRIPT):
        raise RuntimeError("找不到恢复脚本: %s" % RESTORE_SCRIPT)
    if not os.path.isfile(SNAPSHOT_WSL):
        raise RuntimeError("找不到快照归档: %s" % SNAPSHOT_WSL)

    actual = sha256_file(SNAPSHOT_WSL)
    if actual != SNAPSHOT_SHA256:
        msg = ("[!] 快照 SHA256 与预注册冻结值不一致\n"
               "    冻结: %s\n    实际: %s" % (SNAPSHOT_SHA256, actual))
        if allow_hash_mismatch:
            print(msg + "\n    已按 --allow-hash-mismatch 继续（实际哈希将记录到 meta.json）")
        else:
            raise RuntimeError(msg + "\n    如需继续请用 --allow-hash-mismatch，并同步更新预注册 §1。")
    else:
        print("[snap] SHA256 匹配: %s" % actual)

    print("[snap] 恢复中（停服→解包→重启→等追平，可能 1~5 分钟）…")
    t0 = time.monotonic()
    rc = subprocess.call(["bash", RESTORE_SCRIPT, "--yes", SNAPSHOT_WSL])
    dt = time.monotonic() - t0
    if rc != 0:
        raise RuntimeError("snapshot_restore.sh 退出码 %d（环境可能处于不一致状态）" % rc)
    print("[snap] 恢复完成（%.1fs），实际 SHA256=%s" % (dt, actual))
    return actual


def note_inventory():
    """取当前钱包可花费 Sapling Note 面值列表（zat），升序。

    失败返回 None（届时金额启发退化为粗糙猜测，实际形态靠反查校正）。
    若 zallet RPC 名不同，改这里即可，不影响其余协议。
    """
    try:
        r = z("z_listunspent", [0])
        notes = r if isinstance(r, list) else (r.get("result") or [])
        vals = []
        for n in notes:
            if n.get("pool") == "sapling" or n.get("type") == "sapling":
                v = n.get("valueZat")
                if not v:
                    v = int(round(float(n.get("amount", 0)) * 1e8))
                if v:
                    vals.append(v)
        if vals:
            print("[inv] 可花费 Sapling Note %d 个，最小=%d zat" % (len(vals), min(vals)))
            return sorted(vals)
        print("[inv] z_listunspent 返回 0 个 sapling note（可能 RPC 名不同）")
    except Exception as e:
        print("[inv][warn] z_listunspent 失败: %s" % str(e)[:140])
    return None


def pick_amount_zat(S, inv):
    """选金额迫使钱包恰好花费 S 个 note（贪心最小优先假设）。

    金额 = (S-1) 个最小 note 之和 + 第 S 小 note - 1 → 必须动用前 S 个最小 note。
    S=1 时 = 最小 note - 1 → 恰好 1 个 note。
    若 note 不足 S 个，返回 None（标记「note 不足」失败）。
    """
    if not inv or len(inv) < S or S < 1:
        return None
    return sum(inv[:S - 1]) + (inv[S - 1] - 1)


def verify_state(actual_snap_hash):
    """恢复后核验：链高、可花费 Note 数、Sapling 余额。返回 dict。"""
    h = height()
    inv = note_inventory()
    bal = sapling_zat()
    note_n = len(inv) if inv else None
    print("[verify] 链高=%s (预期 %d)  notes=%s  sapling余额=%s zat"
          % (h, SNAPSHOT_TARGET_HEIGHT, note_n, bal))
    return {"restored_height": h, "restored_note_count": note_n,
            "restored_sapling_zat": bal, "snapshot_sha256": actual_snap_hash,
            "snapshot_sha256_expected": SNAPSHOT_SHA256,
            "snapshot_hash_match": actual_snap_hash == SNAPSHOT_SHA256}


# ---------------------------------------------------------------------------
# 计时（冻结边界，单一策略，无回退）
# ---------------------------------------------------------------------------
def send_frozen(from_ua, amounts, policy, timeout_op=600):
    """提交 → 轮询 → 返回 (t_submit_ms, t_pipeline_ms, opid, result)。

    只使用 policy 一种策略；被拒即抛错，绝不回退到其它策略（预注册 §5）。
    """
    params = [from_ua, amounts, 1, None, policy]
    t0 = time.monotonic()
    try:
        opid = z("z_sendmany", params, timeout=120)
    except RuntimeError as e:
        raise RuntimeError("policy=%s 被拒: %s" % (policy, str(e)[:200]))
    t_submit = (time.monotonic() - t0) * 1000.0

    t1 = time.monotonic()
    while time.monotonic() - t1 < timeout_op:
        try:
            st = z("z_getoperationstatus", [[opid]])
        except RuntimeError as e:
            raise RuntimeError("查询 opid 状态失败: %s" % str(e)[:200])
        rec = st[0] if isinstance(st, list) else st
        s = rec.get("status")
        if s == "success":
            t_pipeline = (time.monotonic() - t1) * 1000.0
            return t_submit, t_pipeline, opid, rec.get("result") or {}
        if s == "failed":
            raise RuntimeError("operation failed: %s"
                               % json.dumps(rec.get("error"), ensure_ascii=False))
        time.sleep(0.02)
    raise RuntimeError("operation timeout (policy=%s)" % policy)


# ---------------------------------------------------------------------------
# 单轮
# ---------------------------------------------------------------------------
def run_one(idx, S, O, policy, mine_blocks, dry_run=False):
    """对目标 (S,O) 执行一轮；返回 (row, T) 或 (row_with_error, None)。"""
    row = {"round": idx, "target_spend": S, "target_output": O}
    print("\n----- round %d | 目标 (S=%d,O=%d) policy=%s -----" % (idx, S, O, policy))

    wt, target, sec = wait_sync()
    if wt is None:
        raise RuntimeError("前置同步超时")
    print("  前置同步 wallet=%s 目标=%s（%.1fs）" % (wt, target, sec))

    # 收款地址 = O-1（预期 1 个找零 → 实际 O 输出），与 pilot 的 --outputs 语义一致
    n_recip = max(1, O - 1)
    recipients = [sapling_ua() for _ in range(n_recip)]

    inv = note_inventory()
    amt_zat = pick_amount_zat(S, inv)
    if amt_zat is None or amt_zat <= 0:
        raise RuntimeError("note 不足以构造 S=%d（可用 %d 个）" % (S, len(inv) if inv else 0))
    amounts = build_amounts(recipients, amt_zat / 1e8)
    print("  构造: 收款地址=%d 目标金额=%.6f ZEC（note 驱动 S）" % (n_recip, amt_zat / 1e8))

    if dry_run:
        print("  [dry-run] 不实际发交易（已恢复+核验+选定金额）")
        row.update({"dry_run": 1, "planned_amount_zat": amt_zat,
                    "recipients": n_recip, "note_count": len(inv) if inv else None})
        return row, None

    bal0 = sapling_zat()
    t_round = time.monotonic()
    try:
        ts, tp, opid, res = send_frozen(_FROM_UA, amounts, policy)
    except RuntimeError as e:
        row["error"] = str(e)[:300]
        row["failure_class"] = _classify(str(e))
        print("  [fail] %s" % row["error"])
        return row, None

    txid = res.get("txid")
    row["policy"] = policy
    row["txid"] = txid
    row["opid"] = opid
    row["submit_ms"] = "%.1f" % ts
    row["pipeline_ms"] = "%.1f" % tp
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
    row["fee_zat"] = info.get("fee_zat") or res.get("fee_zat")
    row["tx_size"] = tx_tx_size(txid) if txid else None
    # 形态匹配判定（预注册 §6：实际形态由 z_viewtransaction 决定，不以命令参数为准）
    aS = info.get("spends")
    aO = info.get("outputs")
    row["actual_spend"] = aS
    row["actual_output"] = aO
    row["form_match"] = (aS == S and aO == O)
    print("  实际形态 spends=%s outputs=%s (目标 %d,%d) match=%s"
          % (aS, aO, S, O, row["form_match"]))

    bal1 = sapling_zat()
    total_ms = (time.monotonic() - t_round) * 1000.0
    row["mine_ms"] = "%.1f" % mine_ms
    row["sync_ms"] = "%.1f" % sync_ms
    row["total_ms"] = "%.1f" % total_ms
    row["fee_measured_zat"] = (bal0 - bal1) if (bal0 and bal1) else None
    print("  本轮墙钟 %8.1f ms" % total_ms)
    return row, {"submit": ts, "pipeline": tp, "mine": mine_ms, "sync": sync_ms, "total": total_ms}


def tx_tx_size(txid):
    try:
        raw = b("getrawtransaction", [txid])
        if isinstance(raw, str):
            return len(raw) // 2
        if isinstance(raw, dict) and raw.get("hex"):
            return len(raw["hex"]) // 2
    except RuntimeError:
        pass
    return None


def _classify(err):
    e = err.lower()
    if "被拒" in e or "policy" in e:
        return "rpc_policy_rejected"
    if "timeout" in e:
        return "timeout"
    if "failed" in e:
        return "opid_terminal_failed"
    if "note" in e:
        return "insufficient_notes"
    return "other"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
_FROM_UA = None  # 在 main 中设置（花费地址，sapling-only UA）


def preflight():
    if not os.path.isfile(SNAPSHOT_WSL):
        raise RuntimeError("快照不存在: %s" % SNAPSHOT_WSL)
    if not os.path.isfile(RESTORE_SCRIPT):
        raise RuntimeError("恢复脚本不存在: %s" % RESTORE_SCRIPT)
    print("[preflight] 快照=%s\n           恢复脚本=%s" % (SNAPSHOT_WSL, RESTORE_SCRIPT))


def build_slots(matrix, mode, seed):
    """确认模式：把每格 target_success 次展开成 50 个槽位，随机排序（预注册 §6）。"""
    if mode == "gate":
        return [(S, O) for (S, O) in matrix]  # 每格 1 次，按矩阵顺序
    slots = []
    for (S, O) in matrix:
        slots += [(S, O)] * TARGET_SUCCESS_PER_FORM
    random.Random(seed).shuffle(slots)
    return slots


def main():
    global _FROM_UA
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
                   help="只做恢复+核验+选金额+打印计划，不实际发交易（验证恢复流程用）")
    p.add_argument("--allow-hash-mismatch", action="store_true")
    p.add_argument("--no-restore", action="store_true",
                   help="跳过快照恢复（仅在已确认环境干净时使用；违反预注册 §6，慎用）")
    a = p.parse_args()

    matrix = DEFAULT_MATRIX
    if a.matrix:
        matrix = []
        with open(a.matrix, newline="") as f:
            for r in csv.reader(f):
                if not r or r[0].startswith("#"):
                    continue
                matrix.append((int(r[0]), int(r[1])))

    preflight()
    ts = time.strftime("%Y%m%d_%H%M%S")
    if a.mode == "gate":
        rundir = os.path.join(a.outdir_base, "_feasibility_gate", "run_" + ts)
    else:
        rundir = os.path.join(a.outdir_base, "run_" + ts)
    os.makedirs(rundir, exist_ok=True)
    tee_stdio(os.path.join(rundir, "run.log"))
    print("[log]", os.path.join(rundir, "run.log"))
    print("[argv]", " ".join(sys.argv))
    print("[mode]", a.mode, "policy=", a.policy, "dry_run=", a.dry_run)

    # 内存采样（与既有基准一致；仅 zebrad + zallet launcher，证明进程 zallet-zaino 未覆盖）
    pids = find_pids()
    sampler = Sampler(os.path.join(rundir, "memory_timeseries.csv"))
    sampler.start()

    rows = []
    try:
        # 花费地址（sapling-only UA），整个运行固定一个
        _FROM_UA = sapling_ua()
        print("[addr] 花费地址:", _FROM_UA[:40] + "...")

        slots = build_slots(matrix, a.mode, a.seed)
        # 确认模式记账
        attempts = {}
        successes = {}
        idx = 0
        for (S, O) in slots:
            attempts[(S, O)] = attempts.get((S, O), 0) + 1
            if (a.mode == "confirm" and successes.get((S, O), 0) >= a.target_success):
                continue  # 该格已达标
            if (a.mode == "confirm" and attempts[(S, O)] > a.max_attempts):
                continue  # 该格已达尝试上限
            idx += 1

            # —— 协议核心：每轮恢复 + 核验 ——
            if not a.no_restore:
                snap_hash = restore_snapshot(a.allow_hash_mismatch)
                state = verify_state(snap_hash)
            else:
                print("[!] --no-restore：跳过恢复（违反预注册 §6）")
                state = {"snapshot_sha256": None, "restored_height": height()}

            try:
                row, T = run_one(idx, S, O, a.policy, a.mine_blocks, a.dry_run)
            except Exception as e:
                print("  [error] round %d 失败: %s" % (idx, str(e)[:300]))
                row = {"round": idx, "target_spend": S, "target_output": O,
                       "error": str(e)[:300], "failure_class": _classify(str(e))}
                attempts[(S, O)] = attempts.get((S, O), 0)  # 已计
                rows.append(row)
                try:
                    wait_sync()
                except Exception:
                    pass
                continue

            row.update({"restored_height": state.get("restored_height"),
                        "restored_note_count": state.get("restored_note_count"),
                        "snapshot_sha256": state.get("snapshot_sha256")})
            rows.append(row)
            if T is not None and row.get("txid"):
                successes[(S, O)] = successes.get((S, O), 0) + 1

        # ---- 落盘 ----
        cols = (["round", "target_spend", "target_output", "actual_spend", "actual_output",
                 "form_match", "policy", "txid", "opid", "submit_ms", "pipeline_ms",
                 "mine_ms", "sync_ms", "total_ms", "sapling_spends", "sapling_outputs",
                 "sapling_proofs", "tx_size", "fee_zat", "fee_measured_zat",
                 "restored_height", "restored_note_count", "snapshot_sha256",
                 "failure_class", "error"])
        with open(os.path.join(rundir, "rounds.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)

        # 形式聚合（门禁尤其重要：直接对应预注册 §4.2）
        groups = {}
        for r in rows:
            k = (r.get("target_spend"), r.get("target_output"))
            if k[0] is None:
                continue
            groups.setdefault(k, []).append(r)
        with open(os.path.join(rundir, "gate_summary.csv" if a.mode == "gate" else "summary_by_shape.csv"),
                  "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["target_spend", "target_output", "attempts", "success",
                        "actual_forms", "all_match", "note"])
            for k in sorted(groups):
                g = groups[k]
                succ = [x for x in g if x.get("txid")]
                actual = sorted({(x.get("actual_spend"), x.get("actual_output")) for x in succ})
                match = all(x.get("form_match") for x in succ) if succ else False
                note = ""
                if not succ:
                    note = "无成功构造"
                elif not match:
                    note = "实际形态与目标不符，需记录并决策"
                w.writerow([k[0], k[1], len(g), len(succ),
                            str(actual), "yes" if match else "no", note])

        meta = {"args": vars(a), "pids": pids, "matrix": matrix,
                "mode": a.mode, "policy_frozen": a.policy,
                "attempts_per_form": attempts, "successes_per_form": successes,
                "timestamp": ts,
                "snapshot_sha256_expected": SNAPSHOT_SHA256,
                "snapshot_target_height": SNAPSHOT_TARGET_HEIGHT}
        json.dump(meta, open(os.path.join(rundir, "meta.json"), "w"), indent=1, default=str)

        # 屏幕汇总
        print("\n=== %s 汇总（n=%d）===" % (a.mode, len(rows)))
        for k in sorted(groups):
            g = groups[k]
            succ = [x for x in g if x.get("txid")]
            actual = sorted({(x.get("actual_spend"), x.get("actual_output")) for x in succ})
            print("  (S=%d,O=%d) 尝试=%d 成功=%d 实际形态=%s"
                  % (k[0], k[1], len(g), len(succ), actual))
        if a.mode == "confirm":
            short = [k for k in matrix if successes.get(k, 0) < a.target_success]
            if short:
                print("[!] 未达目标成功数的形态: %s" % short)
    finally:
        sampler.stop_evt.set()
        sampler.join(timeout=5)

    print("\n输出:", rundir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
