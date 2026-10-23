#!/usr/bin/env python3
"""Summarize the exploratory 2026-10-23 QAP sub-stage probe.

This is a scoping helper, not a formal campaign analyzer.  It parses the
`G16_QAP_STAGE` lines from the archived stderr logs, rebuilds the per-proof
table, and reports per-process medians.  It deliberately performs no
threshold test: the runs were not pre-registered and the concurrent /
partitioned A/B/C switches are experiments, not default-change candidates.

The `pools` mode assigns one persistent two-thread Rayon pool to each of
`a/b/c` and runs the two transform groups with a barrier between them.  The
`pipeline` mode keeps the same three pools but starts each letter's
`coset_fft` as soon as that letter's `ifft` finishes.  In both modes the
probe's `a_ifft_ms` field is the whole group; the `pipeline` mode has no
separate coset mark, and its other per-letter marks are `NaN`.
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

# label, pair, mode, round, rayon_threads
RUNS = [
    # Original five-run pilot (pre-partitioned-pool build).
    ("seq_probe", "pair0", "sequential", "pilot", 8),
    ("seq_pair1", "pair1", "sequential", "pilot", 8),
    ("abc_pair1", "pair1", "concurrent", "pilot", 8),
    ("abc_pair2", "pair2", "concurrent", "pilot", 8),
    ("seq_pair2", "pair2", "sequential", "pilot", 8),
    # Early thread-scaling / pool scouting (intermediate build; retained for
    # completeness, not used for the decision).
    ("seq_t2", "threads", "sequential", "intermediate", 2),
    ("seq_t4", "threads", "sequential", "intermediate", 4),
    ("pools_pair1", "pair1", "pools", "intermediate", 8),
    ("pools_pair2", "pair2", "pools", "intermediate", 8),
    ("pools_pair3", "pair3", "pools", "intermediate", 8),
    ("seq_pair3", "pair3", "sequential", "intermediate", 8),
    ("seq_pair4", "pair4", "sequential", "intermediate", 8),
    # Final-provenance scouting runs.
    ("final_seq_t2", "threads", "sequential", "threads", 2),
    ("final_seq_t4", "threads", "sequential", "threads", 4),
    ("final_pools", "pair1", "pools", "pools", 8),
    ("pipeline_pair1", "pair4", "pipeline", "pipeline", 8),
    # Balanced two-arm ABBA used for the decision.
    ("seq_abba1", "abba", "sequential", "abba", 8),
    ("pipe_abba1", "abba", "pipeline", "abba", 8),
    ("pipe_abba2", "abba", "pipeline", "abba", 8),
    ("seq_abba2", "abba", "sequential", "abba", 8),
    # Additional three-arm sequence: pipeline/pools occupy the middle, so this
    # is order-confounded and is not used as a decision arm.
    ("final_abba_seq_a", "confounded", "sequential", "confounded", 8),
    ("final_abba_pipe_a", "confounded", "pipeline", "confounded", 8),
    ("final_abba_pools_a", "confounded", "pools", "confounded", 8),
    ("final_abba_pools_b", "confounded", "pools", "confounded", 8),
    ("final_abba_pipe_b", "confounded", "pipeline", "confounded", 8),
    ("final_abba_seq_b", "confounded", "sequential", "confounded", 8),
]

QAP_RE = re.compile(
    r"G16_QAP_STAGE proof_id=(?P<proof_id>\d+)"
    r"(?: mode=(?P<mode>\w+))?"
    r" domains_ms=(?P<domains>[\d.]+)"
    r" a_ifft_ms=(?P<a_ifft>[\d.]+)"
    r" a_coset_ms=(?P<a_coset>[\d.\w]+)"
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
    "threads",
    "round",
]

SUMMARY_FIELDS = [
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
    "threads",
    "round",
    "qap_min_run_median_ms",
    "qap_max_run_median_ms",
    "prove_min_run_median_ms",
    "prove_max_run_median_ms",
]


def parse_float(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value == value else None


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


def median_optional(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def parse_run(
    label: str,
    pair: str,
    expected_mode: str,
    round_name: str,
    threads: int,
) -> list[dict[str, object]]:
    path = RAW_LOG_DIR / f"sapling_qap_stage_probe_20261023_{label}.log"
    if not path.exists():
        raise SystemExit(f"missing raw log: {path}")
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = QAP_RE.search(line)
        if not match:
            continue
        groups = match.groupdict()
        mode = groups["mode"] or expected_mode
        if mode != expected_mode:
            raise SystemExit(f"{path}: mode {mode} != expected {expected_mode}")
        a_ifft = float(groups["a_ifft"])
        a_coset = parse_float(groups["a_coset"])
        row: dict[str, object] = {
            "run_label": label,
            "pair": pair,
            "mode": mode,
            "proof_id": int(groups["proof_id"]),
            "domains_ms": float(groups["domains"]),
            "a_ifft_ms": a_ifft,
            "a_coset_ms": a_coset,
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
            "threads": threads,
            "round": round_name,
        }
        if mode == "sequential":
            row["group_ifft_ms"] = sum(
                row[key] for key in ("a_ifft_ms", "b_ifft_ms", "c_ifft_ms")  # type: ignore[arg-type]
            )
            row["group_coset_ms"] = sum(
                row[key] for key in ("a_coset_ms", "b_coset_ms", "c_coset_ms")  # type: ignore[arg-type]
            )
        elif mode in ("concurrent", "pools"):
            # The probe's a_* fields are the whole group; b/c are absent.
            row["group_ifft_ms"] = a_ifft
            row["group_coset_ms"] = a_coset
        elif mode == "pipeline":
            # a_ifft_ms spans ifft + coset_fft; there is no coset mark.
            row["group_ifft_ms"] = a_ifft
            row["group_coset_ms"] = None
        else:
            raise SystemExit(f"{path}: unsupported mode {mode}")
        rows.append(row)
    if len(rows) != 5:
        raise SystemExit(f"{path}: expected 5 QAP rows, found {len(rows)}")
    return rows


def prove_median(label: str, threads: int) -> float:
    path = RAW_CSV_DIR / f"sapling_qap_stage_probe_20261023_{label}.csv"
    if not path.exists():
        raise SystemExit(f"missing raw CSV: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 5:
        raise SystemExit(f"{path}: expected 5 prove rows, found {len(rows)}")
    if any(int(row["rayon_threads"]) != threads for row in rows):
        raise SystemExit(f"{path}: rayon_threads does not match manifest ({threads})")
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
    run_qap_median: dict[str, float] = {}
    run_prove_median: dict[str, float] = {}

    for label, pair, mode, round_name, threads in RUNS:
        rows = parse_run(label, pair, mode, round_name, threads)
        per_proof.extend(rows)
        run_qap_median[label] = statistics.median(
            row["total_ms"] for row in rows  # type: ignore[arg-type]
        )
        run_prove_median[label] = prove_median(label, threads)

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
                str(row["threads"]),
                str(row["round"]),
            ]
        )

    summary_rows: list[list[str]] = []
    for label, pair, mode, round_name, threads in RUNS:
        rows = [row for row in per_proof if row["run_label"] == label]
        assert rows
        summary_rows.append(
            [
                label,
                pair,
                mode,
                str(len(rows)),
                fmt(run_qap_median[label]),
                fmt(median_optional([row["group_ifft_ms"] for row in rows])),  # type: ignore[list-item]
                fmt(median_optional([row["group_coset_ms"] for row in rows])),  # type: ignore[list-item]
                fmt(statistics.median(row["icoset_ms"] for row in rows)),  # type: ignore[arg-type]
                fmt(statistics.median(row["h_exponents_ms"] for row in rows)),  # type: ignore[arg-type]
                fmt(run_prove_median[label]),
                str(threads),
                round_name,
                "",
                "",
                "",
                "",
            ]
        )

    # Preserve the original pilot summary: only the five pre-partition runs.
    for mode in ("sequential", "concurrent"):
        labels = [
            label
            for label, _pair, run_mode, round_name, _threads in RUNS
            if round_name == "pilot" and run_mode == mode
        ]
        qap = [run_qap_median[label] for label in labels]
        prove = [run_prove_median[label] for label in labels]
        summary_rows.append(
            [
                f"{mode}_summary",
                "all",
                mode,
                str(len(labels) * 5),
                fmt(statistics.median(qap)),
                "",
                "",
                "",
                "",
                fmt(statistics.median(prove)),
                "8",
                "pilot",
                fmt(min(qap)),
                fmt(max(qap)),
                fmt(min(prove)),
                fmt(max(prove)),
            ]
        )

    # ABBA arm summaries: batch medians first, then median of batch medians.
    for arm_label, mode in (
        ("abba_sequential_summary", "sequential"),
        ("abba_pipeline_summary", "pipeline"),
    ):
        labels = [
            label
            for label, _pair, run_mode, round_name, _threads in RUNS
            if round_name == "abba" and run_mode == mode
        ]
        qap = [run_qap_median[label] for label in labels]
        prove = [run_prove_median[label] for label in labels]
        summary_rows.append(
            [
                arm_label,
                "abba",
                mode,
                str(len(labels) * 5),
                fmt(statistics.median(qap)),
                "",
                "",
                "",
                "",
                fmt(statistics.median(prove)),
                "8",
                "abba",
                fmt(min(qap)),
                fmt(max(qap)),
                fmt(min(prove)),
                fmt(max(prove)),
            ]
        )

    # The three-arm sequence is reported separately because arm position is
    # confounded with order; it is not a decision arm.
    for arm_label, mode in (
        ("confounded_sequential_summary", "sequential"),
        ("confounded_pipeline_summary", "pipeline"),
        ("confounded_pools_summary", "pools"),
    ):
        labels = [
            label
            for label, _pair, run_mode, round_name, _threads in RUNS
            if round_name == "confounded" and run_mode == mode
        ]
        qap = [run_qap_median[label] for label in labels]
        prove = [run_prove_median[label] for label in labels]
        summary_rows.append(
            [
                arm_label,
                "confounded",
                mode,
                str(len(labels) * 5),
                fmt(statistics.median(qap)),
                "",
                "",
                "",
                "",
                fmt(statistics.median(prove)),
                "8",
                "confounded",
                fmt(min(qap)),
                fmt(max(qap)),
                fmt(min(prove)),
                fmt(max(prove)),
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
        SUMMARY_FIELDS,
        summary_rows,
    )

    print(
        "run_label,pair,mode,n,qap_total_median_ms,prove_median_ms,threads,round"
    )
    for row in summary_rows:
        print(",".join([row[0], row[1], row[2], row[3], row[4], row[9], row[10], row[11]]))


if __name__ == "__main__":
    main()
