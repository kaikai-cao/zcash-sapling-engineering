#!/usr/bin/env python3
"""Summarize the exploratory 2026-10-23 QAP sub-stage probe.

This is a scoping helper, not a formal campaign analyzer.  It parses the
`G16_QAP_STAGE` lines from the archived stderr logs, rebuilds the per-proof
table, and reports per-process medians.  It deliberately performs no
threshold test: the runs were not pre-registered and the concurrent A/B/C
switch is an experiment, not a default-change candidate.
"""

from __future__ import annotations

import csv
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_LOG_DIR = ROOT / "experiments" / "raw" / "logs"
RAW_CSV_DIR = ROOT / "experiments" / "raw" / "csv"
TABLE_DIR = ROOT / "results" / "tables"

RUNS = [
    ("seq_probe", "pair0", "sequential"),
    ("seq_pair1", "pair1", "sequential"),
    ("abc_pair1", "pair1", "concurrent"),
    ("abc_pair2", "pair2", "concurrent"),
    ("seq_pair2", "pair2", "sequential"),
]

QAP_RE = re.compile(
    r"G16_QAP_STAGE proof_id=(?P<proof_id>\d+)"
    r"(?: mode=(?P<mode>\w+))?"
    r" domains_ms=(?P<domains>[\d.]+)"
    r" a_ifft_ms=(?P<a_ifft>[\d.]+)"
    r" a_coset_ms=(?P<a_coset>[\d.]+)"
    r" b_ifft_ms=(?P<b_ifft>[\d.\w]+)"
    r" b_coset_ms=(?P<b_coset>[\d.\w]+)"
    r" c_ifft_ms=(?P<c_ifft>[\d.\w]+)"
    r" c_coset_ms=(?P<c_coset>[\d.\w]+)"
    r" mul_ab_ms=(?P<mul_ab>[\d.\w]+)"
    r" sub_c_ms=(?P<sub_c>[\d.\w]+)"
    r" divide_z_ms=(?P<divide_z>[\d.\w]+)"
    r" icoset_ms=(?P<icoset>[\d.]+)"
    r" into_coeffs_ms=(?P<into_coeffs>[\d.]+)"
    r" h_exponents_ms=(?P<h_exponents>[\d.]+)"
    r" total_ms=(?P<total>[\d.]+)"
)

FIELDS = [
    "run_label",
    "pair",
    "mode",
    "proof_id",
    "domains_ms",
    "a_ifft_ms",
    "a_coset_ms",
    "b_ifft_ms",
    "b_coset_ms",
    "c_ifft_ms",
    "c_coset_ms",
    "group_ifft_ms",
    "group_coset_ms",
    "mul_ab_ms",
    "sub_c_ms",
    "divide_z_ms",
    "icoset_ms",
    "h_exponents_ms",
    "total_ms",
]


def parse_float(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value == value else None


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


def parse_run(label: str, pair: str, expected_mode: str) -> list[dict[str, object]]:
    path = RAW_LOG_DIR / f"sapling_qap_stage_probe_20261023_{label}.log"
    if not path.exists():
        raise SystemExit(f"missing raw log: {path}")
    rows: list[dict[str, object]] = []
    mode = expected_mode
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = QAP_RE.search(line)
        if not match:
            continue
        groups = match.groupdict()
        mode = groups["mode"] or expected_mode
        if mode != expected_mode:
            raise SystemExit(f"{path}: mode {mode} != expected {expected_mode}")
        row: dict[str, object] = {
            "run_label": label,
            "pair": pair,
            "mode": mode,
            "proof_id": int(groups["proof_id"]),
            "domains_ms": float(groups["domains"]),
            "a_ifft_ms": float(groups["a_ifft"]),
            "a_coset_ms": float(groups["a_coset"]),
            "b_ifft_ms": parse_float(groups["b_ifft"]),
            "b_coset_ms": parse_float(groups["b_coset"]),
            "c_ifft_ms": parse_float(groups["c_ifft"]),
            "c_coset_ms": parse_float(groups["c_coset"]),
            "mul_ab_ms": parse_float(groups["mul_ab"]),
            "sub_c_ms": parse_float(groups["sub_c"]),
            "divide_z_ms": parse_float(groups["divide_z"]),
            "icoset_ms": float(groups["icoset"]),
            "h_exponents_ms": float(groups["h_exponents"]),
            "total_ms": float(groups["total"]),
        }
        if mode == "sequential":
            row["group_ifft_ms"] = sum(
                row[key] for key in ("a_ifft_ms", "b_ifft_ms", "c_ifft_ms")  # type: ignore[arg-type]
            )
            row["group_coset_ms"] = sum(
                row[key] for key in ("a_coset_ms", "b_coset_ms", "c_coset_ms")  # type: ignore[arg-type]
            )
        else:
            # In concurrent mode the probe's a_* fields are the whole group;
            # b/c fields are intentionally absent.
            row["group_ifft_ms"] = row["a_ifft_ms"]
            row["group_coset_ms"] = row["a_coset_ms"]
        rows.append(row)
    if len(rows) != 5:
        raise SystemExit(f"{path}: expected 5 QAP rows, found {len(rows)}")
    return rows


def prove_median(label: str) -> float:
    path = RAW_CSV_DIR / f"sapling_qap_stage_probe_20261023_{label}.csv"
    if not path.exists():
        raise SystemExit(f"missing raw CSV: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    values = [float(row["prove_ms"]) for row in rows if int(row["run"]) >= 2]
    if len(values) != 4:
        raise SystemExit(f"{path}: expected 4 warm prove rows, found {len(values)}")
    return statistics.median(values)


def write_if_changed(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = [",".join(header)]
    lines.extend(",".join(row) for row in rows)
    content = "\n".join(lines) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    per_proof: list[dict[str, object]] = []
    for label, pair, mode in RUNS:
        per_proof.extend(parse_run(label, pair, mode))

    table_rows: list[list[str]] = []
    for row in per_proof:
        table_rows.append(
            [
                str(row["run_label"]),
                str(row["pair"]),
                str(row["mode"]),
                str(row["proof_id"]),
                fmt(row["domains_ms"]),  # type: ignore[arg-type]
                fmt(row["a_ifft_ms"]),  # type: ignore[arg-type]
                fmt(row["a_coset_ms"]),  # type: ignore[arg-type]
                fmt(row["b_ifft_ms"]),  # type: ignore[arg-type]
                fmt(row["b_coset_ms"]),  # type: ignore[arg-type]
                fmt(row["c_ifft_ms"]),  # type: ignore[arg-type]
                fmt(row["c_coset_ms"]),  # type: ignore[arg-type]
                fmt(row["group_ifft_ms"]),  # type: ignore[arg-type]
                fmt(row["group_coset_ms"]),  # type: ignore[arg-type]
                fmt(row["mul_ab_ms"]),  # type: ignore[arg-type]
                fmt(row["sub_c_ms"]),  # type: ignore[arg-type]
                fmt(row["divide_z_ms"]),  # type: ignore[arg-type]
                fmt(row["icoset_ms"]),  # type: ignore[arg-type]
                fmt(row["h_exponents_ms"]),  # type: ignore[arg-type]
                fmt(row["total_ms"]),  # type: ignore[arg-type]
            ]
        )

    summary_rows: list[list[str]] = []
    run_medians: dict[str, list[float]] = {"sequential": [], "concurrent": []}
    for label, pair, mode in RUNS:
        rows = [row for row in per_proof if row["run_label"] == label]
        assert rows
        total = statistics.median(row["total_ms"] for row in rows)  # type: ignore[arg-type]
        run_medians[mode].append(total)
        summary_rows.append(
            [
                label,
                pair,
                mode,
                str(len(rows)),
                fmt(total),
                fmt(statistics.median(row["group_ifft_ms"] for row in rows)),  # type: ignore[arg-type]
                fmt(statistics.median(row["group_coset_ms"] for row in rows)),  # type: ignore[arg-type]
                fmt(statistics.median(row["icoset_ms"] for row in rows)),  # type: ignore[arg-type]
                fmt(statistics.median(row["h_exponents_ms"] for row in rows)),  # type: ignore[arg-type]
                fmt(prove_median(label)),
            ]
        )

    for mode, medians in run_medians.items():
        summary_rows.append(
            [
                f"{mode}_summary",
                "all",
                mode,
                str(len([row for row in per_proof if row["mode"] == mode])),
                fmt(statistics.median(medians)),
                "",
                "",
                "",
                "",
                "",
            ]
        )

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    write_if_changed(
        TABLE_DIR / "sapling_qap_stage_probe_20261023.csv",
        FIELDS,
        table_rows,
    )
    write_if_changed(
        TABLE_DIR / "sapling_qap_stage_probe_summary_20261023.csv",
        [
            "run_label",
            "pair",
            "mode",
            "n",
            "qap_total_median_ms",
            "group_ifft_median_ms",
            "group_coset_median_ms",
            "icoset_median_ms",
            "h_exponents_median_ms",
            "prove_median_ms_runs2to5",
        ],
        summary_rows,
    )

    print("run_label,pair,mode,n,qap_total_median_ms,prove_median_ms")
    for row in summary_rows:
        print(",".join([row[0], row[1], row[2], row[3], row[4], row[9]]))


if __name__ == "__main__":
    main()
