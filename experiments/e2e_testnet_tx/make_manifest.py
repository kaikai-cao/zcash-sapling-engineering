#!/usr/bin/env python3
"""
make_manifest.py
----------------
为实验产物生成可校验的哈希清单（SHA256 + 字节数 + mtime），用于事后核对
「报告里的数字来自哪些文件、这些文件有没有被改过」。

覆盖范围：
  - raw/ 下全部 run 目录（数据、meta、报告文本）
  - 本目录下的分析脚本
  - 可通过 --extra 追加外部路径（例如 WSL 侧快照 tar.gz）

输出：raw/MANIFEST.sha256（sha256sum 兼容格式，可直接 `sha256sum -c` 校验）
      同时输出 raw/MANIFEST.md（人读版，含分类汇总与异常标记）

用法：
  python3 make_manifest.py
  python3 make_manifest.py --extra /path/to/z3_regtest_h32297_*.tar.gz
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")

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


def walk(root, extra):
    files = []
    for base in [root] + extra:
        if os.path.isfile(base):
            files.append(base)
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for fn in sorted(filenames):
                # 排除叙述性文档与清单自身：它们会随清单生成而变，纳入会造成自指循环
                if fn in ("MANIFEST.sha256", "MANIFEST.md", "AUDIT_trail.md"):
                    continue
                files.append(os.path.join(dirpath, fn))
    return sorted(set(files))


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", nargs="*", default=[], help="额外纳入的文件（如快照 tar.gz）")
    ap.add_argument("--out", default=os.path.join(RAW, "MANIFEST.sha256"))
    ap.add_argument("--md", default=os.path.join(RAW, "MANIFEST.md"))
    args = ap.parse_args()

    if not os.path.isdir(RAW):
        sys.exit(f"找不到 {RAW}")

    files = walk(RAW, args.extra)
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
        ))

    # sha256sum 兼容格式（相对 BASE，便于在仓库内校验）
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for e in entries:
            if e["kind"] != "external":
                f.write(f"{e['sha']}  {e['rel']}\n")

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

    total_bytes = sum(e["size"] for e in entries)
    lines = []
    p = lines.append
    p("# 实验产物哈希清单")
    p("")
    p(f"> 生成时间：{datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}（UTC）  ")
    p(f"> 文件数：**{len(entries)}**　合计：**{total_bytes:,} B**（{total_bytes/1024/1024:.2f} MB）  ")
    p(f"> 校验：`cd experiments/e2e_testnet_tx && sha256sum -c raw/MANIFEST.sha256`")
    p("")

    p("## 按类别")
    p("")
    p("| 类别 | 文件数 | 字节数 |")
    p("|---|---:|---:|")
    kinds = {}
    for e in entries:
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

    p("## 明细")
    p("")
    p("| 文件 | 字节 | mtime (UTC) | SHA256（前 16 位） |")
    p("|---|---:|---|---|")
    for e in entries:
        if e["kind"] == "external":
            continue
        p(f"| `{e['rel']}` | {e['size']:,} | {e['mtime']} | `{e['sha'][:16]}` |")
    p("")

    ext = [e for e in entries if e["kind"] == "external"]
    if ext:
        p("## 外部资产（不进 MANIFEST.sha256，需单独校验）")
        p("")
        p("| 绝对路径 | 字节 | SHA256 |")
        p("|---|---:|---|")
        for e in ext:
            p(f"| `{e['path']}` | {e['size']:,} | `{e['sha']}` |")
        p("")
        p("这些文件位于另一个仓库（`D:/Research/z3`）或 WSL 内，是复现实验的前置资产：")
        p("链快照含 32297 高度之前的全部区块状态与钱包库，`snapshot_restore.sh --yes` 12 秒可回到该状态，")
        p("省掉约 4 小时的重新挖块。**它丢了不会影响已测数据的解读，但会显著拖慢任何复现尝试。**")
        p("")

    with open(args.md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[ok] {args.out}（{len(entries)} 文件）")
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
