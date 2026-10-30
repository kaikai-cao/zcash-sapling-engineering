#!/usr/bin/env python3
"""
make_manifest.py
----------------
为实验产物生成可校验的哈希清单（SHA256 + 字节数 + mtime），用于事后核对
「报告里的数字来自哪些文件、这些文件有没有被改过」。

**本版起按 git 跟踪状态拆分两份清单（2026-10-30 冻结审计修复）**

  1. `raw/MANIFEST.sha256` —— **只含 git 跟踪的文件**，格式兼容 `sha256sum -c`，
     在**任何干净克隆**中都能 100% 校验通过。这是对外声明的复现证据。
  2. `raw/MANIFEST.local-excluded.sha256` —— 记录本地存在但**有意不入库**的文件
     及其哈希（钱包库副本、`run.log`、诊断 JSON 等），标注为"本地证据"，
     **不要求**干净克隆验证。

  这样做的原因：旧版直接遍历文件系统，把 `.gitignore` 排除的 14 个文件也写进正式
  清单 —— 原工作区 `sha256sum -c` 138/138 通过，但别人克隆后 14 条"无此文件"，
  不能称作可复现校验。**绝不为让校验通过而上传播助记词的钱包库。**

覆盖范围：
  - raw/ 下全部 run 目录（数据、meta、报告文本）
  - **本目录下的全部脚本与文档**（fit_*.py、bootstrap_*.py、*.md 等：数字怎么算出来的，
    必须与数据同等固定）
  - 可通过 --extra 追加外部路径（例如 WSL 侧快照 tar.gz；仅进 MANIFEST.md）

输出：
  raw/MANIFEST.sha256                   git 跟踪文件（可干净克隆校验）
  raw/MANIFEST.local-excluded.sha256    本地排除文件（本地证据，含排除理由）
  raw/MANIFEST.md                       人读版（分类汇总 + 完整性 + 两份明细）

用法：
  python3 make_manifest.py
  python3 make_manifest.py --extra /path/to/z3_regtest_h32297_*.tar.gz
  python3 make_manifest.py --check-only    # 只校验现有清单与 git 树是否自洽
"""

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")

OUT_TRACKED = os.path.join(RAW, "MANIFEST.sha256")
OUT_EXCLUDED = os.path.join(RAW, "MANIFEST.local-excluded.sha256")
OUT_MD = os.path.join(RAW, "MANIFEST.md")

# 清单自身不进清单（否则生成→哈希变→再生成，自指）
SELF_NAMES = {"MANIFEST.sha256", "MANIFEST.md", "MANIFEST.local-excluded.sha256"}

# 一次运行至少应有这些文件才算完整（不同批次略有差异，仅作标记用）
EXPECT = {
    "sapling": ["meta.json", "rounds.csv", "stage_timings.csv", "summary.csv",
                "summary_by_shape.csv", "memory_timeseries.csv"],
    "pczt": ["meta.json", "rounds.csv", "stage_timings.csv", "summary.csv",
             "memory_timeseries.csv"],
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def git_tracked(repo_root):
    """返回 git 索引中、位于 BASE 之下的文件绝对路径集合。"""
    out = subprocess.run(
        ["git", "-C", repo_root, "ls-files", "-z", "--", BASE],
        capture_output=True, check=True)
    names = out.stdout.decode("utf-8", "surrogateescape").split("\0")
    return {_norm(os.path.join(repo_root, n)) for n in names if n}


def git_ignored(repo_root, paths):
    """返回被 .gitignore 排除的路径集合（未跟踪且未忽略的属"待提交"）。"""
    if not paths:
        return set()
    feed = "\n".join(os.path.relpath(p, repo_root).replace("\\", "/") for p in paths)
    out = subprocess.run(
        ["git", "-C", repo_root, "check-ignore", "--stdin"],
        input=feed.encode("utf-8", "surrogateescape"),
        capture_output=True)
    ignored = set()
    for line in out.stdout.decode("utf-8", "surrogateescape").splitlines():
        line = line.strip()
        if line:
            ignored.add(_norm(os.path.join(repo_root, line)))
    return ignored


def find_repo_root():
    r = subprocess.run(["git", "-C", BASE, "rev-parse", "--show-toplevel"],
                       capture_output=True)
    if r.returncode != 0:
        sys.exit("当前目录不在 git 仓库内：无法判定哪些文件可被干净克隆校验。\n"
                 "（本脚本自 2026-10-30 起要求 git 环境，以避免把被忽略文件写入正式清单）")
    return r.stdout.decode("utf-8", "surrogateescape").strip()


def walk(root, extra):
    files = []
    for base in [root] + extra:
        if os.path.isfile(base):
            files.append(base)
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for fn in sorted(filenames):
                if fn in SELF_NAMES:
                    continue
                files.append(os.path.join(dirpath, fn))
    return sorted(set(files))


def top_level():
    """本目录下的脚本与文档（不递归）。这些是"数字怎么算出来的"，必须与数据同等固定。"""
    out = []
    for fn in sorted(os.listdir(BASE)):
        p = os.path.join(BASE, fn)
        if os.path.isfile(p) and fn not in SELF_NAMES:
            out.append(p)
    return out


def classify(path):
    rel = os.path.relpath(path, BASE).replace("\\", "/")
    if rel.startswith(".."):
        return "external"
    if rel.startswith("raw/"):
        for k in ("sapling", "pczt", "e2e_regtest"):
            if f"/{k}" in rel or rel.split("/")[1].startswith(k):
                return k
        return "raw-other"
    if rel.endswith(".py"):
        return "script"
    if rel.endswith(".md"):
        return "doc"
    return "other"


def exclusion_reason(rel):
    """给本地排除项一句可核对的理由（按 .gitignore 的实际规则归类）。"""
    if "laststate_seal_" in rel and rel.endswith("wallet.db.sealed"):
        return "regtest 钱包库字节副本，含支出密钥，`.gitignore` 排除（安全边界）"
    if "laststate_seal_" in rel:
        return "封存目录的取证明细，脱离库本体无独立价值，`.gitignore` 排除"
    if rel.endswith("run.log"):
        return "执行日志，`.gitignore` 的 `**/run_*/run.log` 排除（可由 run 产物与脚本重放）"
    if "_note_scan_diag/" in rel:
        return "live-node 诊断产物，产出脚本未入库，不可独立复现"
    return "未被 git 跟踪（详见 `.gitignore`）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", nargs="*", default=[], help="额外纳入的文件（如快照 tar.gz，仅进 MANIFEST.md）")
    ap.add_argument("--md", default=OUT_MD)
    ap.add_argument("--check-only", action="store_true",
                    help="只校验现有 MANIFEST.sha256 是否全部为 git 跟踪文件，不重写")
    args = ap.parse_args()

    if not os.path.isdir(RAW):
        sys.exit(f"找不到 {RAW}")

    repo_root = find_repo_root()
    tracked = git_tracked(repo_root)

    files = sorted(set(walk(RAW, args.extra) + top_level()))
    if not files:
        sys.exit("没有可清单化的文件")

    entries = []
    for p in files:
        st = os.stat(p)
        entries.append(dict(
            path=p,
            rel=os.path.relpath(p, BASE).replace("\\", "/"),
            size=st.st_size,
            mtime=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            sha=sha256(p),
            kind=classify(p),
            tracked=_norm(p) in tracked,
        ))

    cand = [e for e in entries if e["kind"] != "external"]
    ignored = git_ignored(repo_root, [e["path"] for e in cand if not e["tracked"]])

    for e in cand:
        if e["tracked"]:
            e["bucket"] = "tracked"
        elif _norm(e["path"]) in ignored:
            e["bucket"] = "ignored"
            e["reason"] = exclusion_reason(e["rel"])
        else:
            e["bucket"] = "pending"      # 未跟踪、也未忽略：应当提交

    tracked_e = [e for e in cand if e["bucket"] == "tracked"]
    ignored_e = [e for e in cand if e["bucket"] == "ignored"]
    pending_e = [e for e in cand if e["bucket"] == "pending"]
    ext_e = [e for e in entries if e["kind"] == "external"]

    if pending_e:
        print("[!] 以下 %d 个文件既未被 git 跟踪、也未在 .gitignore 中："
              "先 `git add` 再生成清单，否则它们不会出现在可校验清单里：" % len(pending_e))
        for e in pending_e:
            print("      " + e["rel"])

    if args.check_only:
        bad = []
        if os.path.isfile(OUT_TRACKED):
            for line in open(OUT_TRACKED, encoding="utf-8"):
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                _, rel = line.split("  ", 1)
                if _norm(os.path.join(BASE, rel)) not in tracked:
                    bad.append(rel)
        print("[check] MANIFEST.sha256 条目: %d，其中非 git 跟踪: %d"
              % (len(open(OUT_TRACKED, encoding="utf-8").readlines()) if os.path.isfile(OUT_TRACKED) else 0,
                 len(bad)))
        for b in bad:
            print("  非跟踪: " + b)
        sys.exit(1 if bad else 0)

    # ---- MANIFEST.sha256：只含 git 跟踪文件 ----
    with open(OUT_TRACKED, "w", encoding="utf-8", newline="\n") as f:
        for e in sorted(tracked_e, key=lambda x: x["rel"]):
            f.write(f"{e['sha']}  {e['rel']}\n")

    # ---- MANIFEST.local-excluded.sha256：本地证据，不要求干净克隆验证 ----
    with open(OUT_EXCLUDED, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 本地证据清单（不要求干净克隆验证）\n")
        f.write("# 这些文件存在于工作区但被 .gitignore 有意排除；列出哈希是为了证明\n")
        f.write("# 「本地产物与报告一致」，而**不是**「远端可复现」。校验方式：\n")
        f.write("#   sha256sum -c raw/MANIFEST.local-excluded.sha256\n")
        for e in sorted(ignored_e, key=lambda x: x["rel"]):
            f.write(f"# 原因: {e['reason']}\n")
            f.write(f"{e['sha']}  {e['rel']}\n")

    # 连续性硬约束：正式清单不得出现任何未跟踪路径
    for e in tracked_e:
        assert _norm(e["path"]) in tracked, e["rel"]

    # 完整性标记：直接扫磁盘上的 run 目录（含空目录）
    runs = {}
    for batch in sorted(os.listdir(RAW)):
        bdir = os.path.join(RAW, batch)
        if not os.path.isdir(bdir):
            continue
        for run in sorted(os.listdir(bdir)):
            if run.startswith("run_"):
                rdir = os.path.join(bdir, run)
                runs[f"raw/{batch}/{run}"] = sorted(
                    x for x in os.listdir(rdir) if os.path.isfile(os.path.join(rdir, x)))

    total_bytes = sum(e["size"] for e in tracked_e)
    lines = []
    p = lines.append
    p("# 实验产物哈希清单")
    p("")
    p(f"> 生成时间：{datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}（UTC）  ")
    p(f"> **可校验（git 跟踪）文件数：{len(tracked_e)}**　合计：**{total_bytes:,} B**（{total_bytes/1024/1024:.2f} MB）  ")
    p(f"> 本地排除（不可远端校验）文件数：**{len(ignored_e)}**  ")
    p(f"> 校验（干净克隆即可 100% 通过）：`cd experiments/e2e_testnet_tx && sha256sum -c raw/MANIFEST.sha256`")
    p("")
    p("> 拆分原因：钱包库副本、`run.log`、诊断 JSON 等被 `.gitignore` 有意排除，")
    p("> 若写进正式清单，干净克隆会出现「文件不存在」而非「哈希不符」，容易被误读为数据损坏。")
    p("> 两类文件的哈希都记录，但**只有前者**可对外声明为远端可复现证据。")
    p("")

    p("## 按类别（仅 git 跟踪文件）")
    p("")
    p("| 类别 | 文件数 | 字节数 |")
    p("|---|---:|---:|")
    kinds = {}
    for e in tracked_e:
        k = kinds.setdefault(e["kind"], [0, 0])
        k[0] += 1
        k[1] += e["size"]
    for k, (n, b) in sorted(kinds.items()):
        p(f"| {k} | {n} | {b:,} |")
    p("")

    p("## 运行目录完整性")
    p("")
    p("| run 目录 | 文件数 | 缺失 |")
    p("|---|---:|---|")
    for run in sorted(runs):
        have = runs[run]
        kind = "pczt" if "pczt" in run else ("sapling" if "sapling" in run else None)
        miss = "-"
        if kind:
            miss_files = [f for f in EXPECT[kind] if f not in have]
            miss = "、".join(miss_files) if miss_files else "无"
        flag = " **（空目录/不完整）**" if len(have) == 0 else ""
        p(f"| `{run}` | {len(have)} | {miss}{flag} |")
    p("")

    p(f"## 明细 · git 跟踪（{len(tracked_e)} 条，可干净克隆校验）")
    p("")
    p("| 文件 | 字节 | mtime (UTC) | SHA256（前 16 位） |")
    p("|---|---:|---|---|")
    for e in sorted(tracked_e, key=lambda x: x["rel"]):
        p(f"| `{e['rel']}` | {e['size']:,} | {e['mtime']} | `{e['sha'][:16]}` |")
    p("")

    if ignored_e:
        p(f"## 本地排除明细（{len(ignored_e)} 条，仅本地证据）")
        p("")
        p("| 文件 | 字节 | 排除理由 |")
        p("|---|---:|---|")
        for e in sorted(ignored_e, key=lambda x: x["rel"]):
            p(f"| `{e['rel']}` | {e['size']:,} | {e['reason']} |")
        p("")
        p("完整哈希见 `raw/MANIFEST.local-excluded.sha256`。这些文件**不随仓库分发**，")
        p("故读者无法验证其存在性；它们的作用仅是证明本工作区的产物与报告一致。")
        p("")

    if ext_e:
        p("## 外部资产（不进任何 sha256 清单，需单独校验）")
        p("")
        p("| 绝对路径 | 字节 | SHA256 |")
        p("|---|---:|---|")
        for e in ext_e:
            p(f"| `{e['path']}` | {e['size']:,} | `{e['sha']}` |")
        p("")
        p("这些文件位于另一个仓库（`D:/Research/z3`）或 WSL 内，是复现实验的前置资产：")
        p("链快照含 32297 高度之前的全部区块状态与钱包库，`snapshot_restore.sh --yes` 12 秒可回到该状态，")
        p("省掉约 4 小时的重新挖块。**它丢了不会影响已测数据的解读，但会显著拖慢任何复现尝试。**")
        p("")

    with open(args.md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[ok] {OUT_TRACKED}（{len(tracked_e)} 文件，git 跟踪）")
    print(f"[ok] {OUT_EXCLUDED}（{len(ignored_e)} 文件，本地排除）")
    print(f"[ok] {args.md}")
    empty = [r for r in runs if len(runs[r]) == 0]
    if empty:
        print(f"[!] 空运行目录 {len(empty)} 个：" + ", ".join(empty))
    incomplete = []
    for run in sorted(runs):
        kind = "pczt" if "pczt" in run else ("sapling" if "sapling" in run else None)
        if kind:
            m = [f for f in EXPECT[kind] if f not in runs[run]]
            if m:
                incomplete.append(f"{run} 缺 {','.join(m)}")
    if incomplete:
        print("[!] 不完整运行：" + "; ".join(incomplete))


if __name__ == "__main__":
    main()
