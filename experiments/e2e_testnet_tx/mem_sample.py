#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mem_sample.py — 容器内存采样器（用于一次性成本：首次同步 / 证明期独立峰值）

独立运行，配合 z3 Testnet 栈：在 Zebra 首次同步或证明生成期间，
按固定间隔采样 zebra / zallet 容器内存，输出 CSV。

仅用 Python 标准库 + docker CLI。

用法：
  python3 mem_sample.py --containers z3-testnet-zebra-1,z3-testnet-zallet-1 \
      --interval 5 --out ../raw/e2e_testnet_tx/sync_memory.csv

  --duration 0 表示一直采样直到 Ctrl-C（适合覆盖整个首次同步窗口）。
"""

import argparse
import csv
import subprocess
import sys
import time


def parse_mem_usage(s):
    try:
        used_s, limit_s = s.split("/")
    except ValueError:
        return (None, None)
    return (_to_bytes(used_s), _to_bytes(limit_s))


def _to_bytes(tok):
    tok = tok.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3,
             "TB": 1024**4, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}
    for suf, mul in units.items():
        if tok.endswith(suf):
            try:
                return int(float(tok[:-len(suf)].strip()) * mul)
            except ValueError:
                return None
    try:
        return int(float(tok))
    except ValueError:
        return None


def sample_once(containers):
    rows = []
    for c in containers:
        try:
            out = subprocess.run(
                ["docker", "stats", "--no-stream",
                 "--format", "{{.MemUsage}}", c],
                capture_output=True, text=True, timeout=10)
            used, limit = parse_mem_usage(out.stdout.strip())
            rows.append((c, used, limit))
        except Exception as e:
            print("[warn] %s 采样失败: %s" % (c, e))
            rows.append((c, None, None))
    return rows


def main():
    p = argparse.ArgumentParser(description="docker 容器内存采样器")
    p.add_argument("--containers", required=True,
                   help="逗号分隔的容器名，如 z3-testnet-zebra-1,z3-testnet-zallet-1")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--duration", type=float, default=0.0,
                   help="采样总时长（秒）；0 = 直到 Ctrl-C")
    p.add_argument("--out", required=True, help="输出 CSV 路径")
    args = p.parse_args()

    containers = [c.strip() for c in args.containers.split(",") if c.strip()]

    print("采样容器: %s" % containers)
    print("间隔: %.1fs  时长: %s" % (args.interval,
          "直到中断" if args.duration == 0 else "%.0fs" % args.duration))
    print("输出: %s" % args.out)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts_epoch", "container", "mem_used_bytes", "mem_limit_bytes"])
        f.flush()
        deadline = time.time() + args.duration if args.duration > 0 else None
        try:
            while True:
                ts = time.time()
                for c, used, limit in sample_once(containers):
                    w.writerow([f"{ts:.3f}", c, used if used is not None else "",
                                limit if limit is not None else ""])
                f.flush()
                if deadline and time.time() >= deadline:
                    break
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n[stopped] 已写入 %s" % args.out)
            sys.exit(0)
    print("[done] 已写入 %s" % args.out)


if __name__ == "__main__":
    main()
