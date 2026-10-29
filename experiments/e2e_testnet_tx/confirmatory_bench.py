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
  3. 构造：目标 (S,O) → O-1 个收款地址（预期 1 个找零 → 实际 O 输出）全部指向
     恢复后钱包的同一 sapling UA；按 note 清单选金额，显式预留手续费
     F = 5000·max(S,O) 与正找零，迫使恰好动用前 S 个最小 note。
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
import json
import os
import random
import subprocess
import sys
import time

# 复用既有基准脚本的 RPC / 计时 / 形态反查实现，保证 submit/pipeline 边界完全一致
from sapling_e2e_bench import (
    z, b, height, wait_sync, advance, sapling_ua, pools, sapling_zat,
    view_tx, tee_stdio, Sampler, find_pids, rss_kb, STAGES, build_amounts,
    COOKIE, ACCOUNT, tx_size,
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

# 候选矩阵（预注册 §4，10 种形态，每格目标 5 次有效成功；门禁每格 1 次）
DEFAULT_MATRIX = [
    (1, 2), (2, 2), (4, 2), (7, 2), (10, 2), (17, 2),
    (1, 9), (3, 2), (3, 3), (4, 3),
]
MAX_ATTEMPTS_PER_FORM = 8               # 每格最多尝试次数（预注册 §4）
TARGET_SUCCESS_PER_FORM = 5             # 每格目标有效成功次数（预注册 §4）


# ---------------------------------------------------------------------------
# 自定义异常（区分「结构性不可行」与「可重试的瞬时失败」）
# ---------------------------------------------------------------------------
class StateError(Exception):
    """初始状态核验失败，但可能瞬时（可重试）。"""


class HeightMismatch(StateError):
    """恢复后链高与预期不符 —— 结构性错误，不应重试。"""


class PreTxError(Exception):
    """交易提交前就已失败（RPC 拒绝、opid 终态失败、超时、资金不足等）。"""


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


def note_inventory():
    """取当前钱包可花费 Sapling Note 面值列表（zat），升序；失败返回 None。

    严格规则：拿不到可靠清单就返回 None，由上层**停止发交易**，绝不粗略猜测。
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
            return sorted(vals)
        print("[inv] z_listunspent 返回 0 个 sapling note（RPC 名可能不同或钱包为空）")
        return None
    except Exception as e:
        print("[inv][warn] z_listunspent 失败: %s" % str(e)[:140])
        return None


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
    """
    params = [from_ua, amounts, 1, None, policy]
    t0 = time.monotonic()
    try:
        opid = z("z_sendmany", params, timeout=120)
    except RuntimeError as e:
        raise PreTxError("policy=%s 被拒: %s" % (policy, str(e)[:200]))
    t_submit = (time.monotonic() - t0) * 1000.0

    t1 = time.monotonic()
    while time.monotonic() - t1 < timeout_op:
        try:
            st = z("z_getoperationstatus", [[opid]])
        except RuntimeError as e:
            raise PreTxError("查询 opid 状态失败: %s" % str(e)[:200])
        rec = st[0] if isinstance(st, list) else st
        s = rec.get("status")
        if s == "success":
            t_pipeline = (time.monotonic() - t1) * 1000.0
            return t_submit, t_pipeline, opid, rec.get("result") or {}
        if s == "failed":
            raise PreTxError("operation failed: %s"
                             % json.dumps(rec.get("error"), ensure_ascii=False))
        time.sleep(0.02)
    raise PreTxError("operation timeout (policy=%s)" % policy)


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
    recipients = [from_ua] * n_recip          # 收款地址全部指向恢复后钱包同一 UA（自转/自收）
    print("\n----- round %d | 目标 (S=%d,O=%d) policy=%s -----" % (idx, S, O, policy))
    print("  收款地址数=%d（含 1 找零→实际 O 输出）目标总额=%.6f ZEC 手续费预留=%d zat"
          % (n_recip, amount_zec, pick["fee_zat"]))

    wt, target, sec = wait_sync()
    if wt is None:
        raise PreTxError("前置同步超时")

    amounts = build_amounts(recipients, amount_zec)
    row["planned_amount_zat"] = pick["amount_zat"]
    row["expected_fee_zat"] = pick["fee_zat"]
    row["recipients"] = n_recip

    if dry_run:
        print("  [dry-run] 不实际发交易（已恢复+核验+选定金额）")
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
        row["failure_class"] = _classify(str(e))
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


def _classify(err):
    e = err.lower()
    if "被拒" in e or "policy" in e:
        return "rpc_policy_rejected"
    if "timeout" in e:
        return "timeout"
    if "failed" in e:
        return "opid_terminal_failed"
    if "note" in e or "insufficient" in e or "金额" in e:
        return "insufficient_notes"
    if "同步" in e:
        return "env_transient_sync"
    return "other"


def fail_row(idx, S, O, cls, msg):
    return {"round": idx, "target_spend": S, "target_output": O,
            "error": msg[:300], "failure_class": cls}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def preflight():
    if not os.path.isfile(SNAPSHOT_WSL):
        raise RuntimeError("快照不存在: %s" % SNAPSHOT_WSL)
    if not os.path.isfile(RESTORE_SCRIPT):
        raise RuntimeError("恢复脚本不存在: %s" % RESTORE_SCRIPT)
    print("[preflight] 快照=%s\n           恢复脚本=%s" % (SNAPSHOT_WSL, RESTORE_SCRIPT))


COLUMNS = ["round", "target_spend", "target_output", "actual_spend", "actual_output",
           "form_match", "fee_match", "policy", "txid", "opid",
           "submit", "pipeline", "mine", "sync", "total",
           "sapling_spends", "sapling_outputs", "sapling_proofs", "tx_size",
           "fee_zat", "expected_fee_zat", "planned_amount_zat", "recipients",
           "restored_height", "restored_note_count",
           "snapshot_sha256", "restore_script_sha256",
           "dry_run", "failure_class", "error"]


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
    print("[mode]", a.mode, "policy=", a.policy, "dry_run=", a.dry_run, "restore=", not a.no_restore)

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
                except StateError as e:
                    rows.append(fail_row(idx, S, O, "state_verification_failed", str(e)))
                    continue
                except PreTxError as e:
                    rows.append(fail_row(idx, S, O, _classify(str(e)), str(e)))
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
                    except StateError as e:
                        rows.append(fail_row(idx, S, O, "state_verification_failed", str(e)))
                        if att >= a.max_attempts:
                            infeasible = True
                        continue
                    except PreTxError as e:
                        rows.append(fail_row(idx, S, O, _classify(str(e)), str(e)))
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
                note = ""
                if not tx_ok:
                    note = "无成功构造（形态不可行或环境/策略失败）"
                elif not allm:
                    note = "成功构造但形态或手续费不符，未计入有效样本"
                w.writerow([k[0], k[1], len(g), len(tx_ok), len(fm), len(fem), len(allm),
                            str(actual), note])

        meta = {"args": vars(a), "pids": pids, "matrix": matrix, "mode": a.mode,
                "policy_frozen": a.policy, "attempts_per_form": attempts,
                "valid_successes_per_form": successes, "timestamp": ts,
                "snapshot_sha256_expected": SNAPSHOT_SHA256,
                "snapshot_target_height": SNAPSHOT_TARGET_HEIGHT,
                "restore_script_sha256_expected": RESTORE_SCRIPT_SHA256}
        json.dump(meta, open(os.path.join(rundir, "meta.json"), "w"), indent=1, default=str)

        # 屏幕汇总
        print("\n=== %s 汇总（n=%d）===" % (a.mode, len(rows)))
        for k in sorted(groups):
            g = groups[k]
            tx_ok = [x for x in g if x.get("txid")]
            actual = sorted({(x.get("actual_spend"), x.get("actual_output")) for x in tx_ok})
            vs = successes.get(k, 0)
            print("  (S=%d,O=%d) 尝试=%d 有效成功=%d 实际形态=%s"
                  % (k[0], k[1], len(g), vs, actual))
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
