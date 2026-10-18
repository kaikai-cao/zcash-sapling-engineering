#!/usr/bin/env python3
"""Analyse `SAPLING_G16_MEM_PHASE_PROBE=1` stderr logs.

The per-phase probe in `vendor/groth16/src/prover.rs` emits one line per stage
boundary of `create_proof`:

    G16_MEM_PHASE phase=<name> live_bytes=<n> phase_peak_abs_bytes=<n> \
        phase_peak_delta_bytes=<n> running_max_abs_bytes=<n>

`phase_peak_abs_bytes` is the highest live value reached during the stage that
just ended, on the same absolute scale as the `BELLMAN_MSM_MEM_PROBE` lines and
the prove memory ledger. The probe re-arms the allocator watermark at every
boundary, so `running_max_abs_bytes` recomposes the stage peaks into a
body-wide peak: in a probe-enabled run the ledger's own `prove_peak_abs_bytes`
column is *not* usable, and this file is the authoritative source.

This script only reads logs and writes a CSV; it never reruns a prover and
never overwrites an existing measurement. Each row keeps its source, so
multiple arms / rounds can be aggregated by the caller without losing
provenance.

Output columns:
    source, run, sequence, phase, live_bytes, phase_peak_abs_bytes,
    phase_peak_delta_bytes, running_max_abs_bytes
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

LINE_RE = re.compile(r"G16_MEM_PHASE\s+(?P<body>(?:[a-z_]+=\S+\s*)+)")
FIELD_RE = re.compile(r"(?P<key>[a-z_]+)=(?P<value>\S+)")

FIELDS = (
    "live_bytes",
    "phase_peak_abs_bytes",
    "phase_peak_delta_bytes",
    "running_max_abs_bytes",
)


def parse_log(path: Path) -> list[dict]:
    rows: list[dict] = []
    run = 0
    sequence = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            match = LINE_RE.search(raw)
            if not match:
                continue
            fields = {m.group("key"): m.group("value") for m in FIELD_RE.finditer(match.group("body"))}
            phase = fields.get("phase")
            if phase is None:
                continue
            if phase == "pre_body":
                run += 1
                sequence = 0
            if run == 0:
                # A truncated log that starts mid-run: label it run 1 anyway.
                run = 1
            sequence += 1
            row = {
                "source": path.stem,
                "run": run,
                "sequence": sequence,
                "phase": phase,
            }
            for field in FIELDS:
                value = fields.get(field)
                row[field] = int(value) if value is not None else ""
            rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("logs", nargs="+", type=Path, help="G16_MEM_PHASE stderr logs")
    parser.add_argument("--label", action="append", default=None, help="arm label per log, in order")
    parser.add_argument("--output", type=Path, required=True, help="CSV to write")
    args = parser.parse_args(argv)

    if args.label and len(args.label) != len(args.logs):
        parser.error("--label must be given once per log")

    all_rows: list[dict] = []
    for index, log in enumerate(args.logs):
        if not log.exists():
            parser.error(f"missing log: {log}")
        rows = parse_log(log)
        if args.label:
            for row in rows:
                row["source"] = args.label[index]
        all_rows.extend(rows)

    if not all_rows:
        parser.error("no G16_MEM_PHASE lines found")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["source", "run", "sequence", "phase", *FIELDS]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"wrote {args.output} ({len(all_rows)} rows, {len(args.logs)} log(s))")

    # Console summary: the maximum phase peak per source, excluding run 1.
    for index, log in enumerate(args.logs):
        label = args.label[index] if args.label else log.stem
        warm = [r for r in all_rows if r["source"] == label and r["run"] > 1 and r["phase_peak_abs_bytes"] != ""]
        if not warm:
            continue
        peaks: dict[str, int] = {}
        for row in warm:
            key = row["phase"]
            value = int(row["phase_peak_abs_bytes"])
            peaks[key] = max(peaks.get(key, 0), value)
        top = sorted(peaks.items(), key=lambda item: item[1], reverse=True)[:5]
        print(f"  {label}: top phase peaks (runs 2+): " + ", ".join(f"{k}={v:,}" for k, v in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
