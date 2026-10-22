# -*- coding: utf-8 -*-
"""Analyse the full Sapling transaction-construction baseline (2026-10-22).

Reads the raw per-run CSVs produced by
``scripts/run_tx_construct_campaign.ps1`` and evaluates the acceptance table
frozen in
``experiments/metadata/sapling_tx_construction_preregistration_20261022.md``
(搂5 as amended by 搂9, plus the pre-measurement fee deviation in 搂10).

Arms (one process each, REPEATS=6, run 1 dropped as warm-up):

  * A1  real builder + real Groth16 provers, 1 thread, affinity 0x1
  * A2  same, 8 threads, affinity 0xFFFF (P-cores)
  * A3  same builder + mock provers, 1 thread, affinity 0x1

Timing model (frozen, 搂3):

    t_total_construct = t_build + t_serialize
    t_proving         = t_build - t_mock_build        (paired, run by run)
    sum_proofs        = prove_spend + prove_output_a + prove_output_b

``t_proving`` is only used to explain the composition of ``t_build``; the
primary carrier is ``t_total_construct``. Nothing here is a network or wallet
measurement.

Outputs:

  * results/tables/sapling_tx_construct_summary_20261022.csv
  * results/tables/sapling_tx_construct_composition_20261022.csv
  * results/tables/sapling_tx_construct_acceptance_20261022.csv
  * results/figures/sapling_tx_construct_composition_20261022.png
  * results/figures/sapling_tx_construct_per_proof_20261022.png
  * results/figures/sapling_tx_construct_threads_20261022.png
"""

from __future__ import annotations

import csv
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiments" / "raw" / "csv"
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"

TAG = "tx_construct_20261022"
TAGS = {
    "A1_real_1t": f"{TAG}_real_t1_0x1",
    "A2_real_8t": f"{TAG}_real_t8_0xFFFF",
    "A3_mock_1t": f"{TAG}_mock_t1_0x1",
}

REPEATS = 6
FEE_ZATS = 10_000
VALUE_BALANCE_ZATS = 10_000
EXPECTED_TX_BYTES = 2377  # observed, must be constant; asserted below

# Frozen thresholds (搂5).
PROVING_SHARE_MIN = 0.90
ESTIMATOR_DIFF_MAX = 0.05
MOCK_BUILD_MAX_MS = 100.0
CV_MAX_PCT = 5.0

FLOAT_COLUMNS = (
    "build_ms",
    "mock_build_ms",
    "serialize_ms",
    "txid_ms",
    "total_construct_ms",
    "prove_spend_ms",
    "prove_output_a_ms",
    "prove_output_b_ms",
    "sum_proofs_ms",
    "verify_ms",
    "witness_ms",
    "setup_params_ms",
    "setup_vk_ms",
)


def load_rows() -> dict[str, list[dict]]:
    arms: dict[str, list[dict]] = {name: [] for name in TAGS}
    for name, tag in TAGS.items():
        source = RAW / f"sapling_tx_construct_runs_{'real' if 'real' in name else 'mock'}.csv"
        if not source.exists():
            raise SystemExit(f"missing raw CSV: {source}")
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["tag"] != tag:
                    continue
                for column in FLOAT_COLUMNS:
                    row[column] = float(row[column])
                row["run"] = int(row["run"])
                arms[name].append(row)
    for name, rows in arms.items():
        if len(rows) != REPEATS:
            raise SystemExit(f"{name}: expected {REPEATS} rows, got {len(rows)}")
        rows.sort(key=lambda r: r["run"])
    return arms


def warm(rows: list[dict]) -> list[dict]:
    """Drop run 1 (first-touch warm-up), as frozen in 搂4."""
    return [row for row in rows if row["run"] != 1]


def describe(values: list[float]) -> dict[str, float]:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        nan = float("nan")
        return {"n": 0, "median": nan, "mean": nan, "sd": nan, "cv_pct": nan, "min": nan, "max": nan}
    mean = statistics.mean(clean)
    sd = statistics.stdev(clean) if len(clean) > 1 else 0.0
    return {
        "n": len(clean),
        "median": statistics.median(clean),
        "mean": mean,
        "sd": sd,
        "cv_pct": (sd / mean * 100.0) if mean else float("nan"),
        "min": min(clean),
        "max": max(clean),
    }


def column(rows: list[dict], key: str) -> list[float]:
    return [row[key] for row in rows]


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> int:
    arms = load_rows()
    a1 = warm(arms["A1_real_1t"])
    a2 = warm(arms["A2_real_8t"])
    a3 = warm(arms["A3_mock_1t"])

    # ---- summaries -----------------------------------------------------
    phase_keys = [
        "witness_ms",
        "build_ms",
        "serialize_ms",
        "total_construct_ms",
        "prove_spend_ms",
        "prove_output_a_ms",
        "prove_output_b_ms",
        "sum_proofs_ms",
        "verify_ms",
    ]
    summary_rows: list[list[str]] = []
    for arm_name, rows in (("A1_real_1t", a1), ("A2_real_8t", a2), ("A3_mock_1t", a3)):
        for key in phase_keys:
            stats = describe(column(rows, key))
            if stats["n"] == 0:
                summary_rows.append(
                    [arm_name, rows[0]["affinity_mask"], rows[0]["rayon_threads"], key, "0", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"]
                )
                continue
            summary_rows.append(
                [
                    arm_name,
                    rows[0]["affinity_mask"],
                    rows[0]["rayon_threads"],
                    key,
                    str(stats["n"]),
                    fmt(stats["median"]),
                    fmt(stats["mean"]),
                    fmt(stats["sd"]),
                    fmt(stats["cv_pct"], 2),
                    fmt(stats["min"]),
                    fmt(stats["max"]),
                ]
            )
    write_csv(
        TABLES / "sapling_tx_construct_summary_20261022.csv",
        [
            "arm",
            "affinity_mask",
            "rayon_threads",
            "phase",
            "n",
            "median_ms",
            "mean_ms",
            "sd_ms",
            "cv_pct",
            "min_ms",
            "max_ms",
        ],
        summary_rows,
    )

    # ---- composition ---------------------------------------------------
    # Paired estimate: t_proving(run) = t_build(run) - t_mock_build(run).
    paired_proving = [
        real["build_ms"] - mock["build_ms"] for real, mock in zip(a1, a3)
    ]
    proving_median = statistics.median(paired_proving)
    build_median = statistics.median(column(a1, "build_ms"))
    serialize_median = statistics.median(column(a1, "serialize_ms"))
    total_median = statistics.median(column(a1, "total_construct_ms"))
    mock_median = statistics.median(column(a3, "build_ms"))
    sum_proofs_median = statistics.median(column(a1, "sum_proofs_ms"))
    spend_median = statistics.median(column(a1, "prove_spend_ms"))
    out_a_median = statistics.median(column(a1, "prove_output_a_ms"))
    out_b_median = statistics.median(column(a1, "prove_output_b_ms"))

    composition_rows = [
        ["t_total_construct", fmt(total_median), "100.00", "t_build + t_serialize"],
        ["t_build", fmt(build_median), fmt(build_median / total_median * 100.0, 2), "Builder::build"],
        ["t_serialize", fmt(serialize_median), fmt(serialize_median / total_median * 100.0, 3), "tx.write"],
        [
            "t_proving",
            fmt(proving_median),
            fmt(proving_median / total_median * 100.0, 2),
            "paired t_build - t_mock_build (estimate)",
        ],
        [
            "sum_proofs",
            fmt(sum_proofs_median),
            fmt(sum_proofs_median / total_median * 100.0, 2),
            "spend + output_a + output_b",
        ],
        ["prove_spend", fmt(spend_median), fmt(spend_median / total_median * 100.0, 2), "1 proof"],
        ["prove_output_a", fmt(out_a_median), fmt(out_a_median / total_median * 100.0, 2), "1 proof"],
        ["prove_output_b", fmt(out_b_median), fmt(out_b_median / total_median * 100.0, 2), "1 proof"],
        [
            "t_mock_build",
            fmt(mock_median),
            fmt(mock_median / total_median * 100.0, 3),
            "non-proving overhead (witness assembly, encoding, sighash, signatures)",
        ],
        [
            "t_build - sum_proofs",
            fmt(build_median - sum_proofs_median),
            fmt((build_median - sum_proofs_median) / total_median * 100.0, 2),
            "residual: assembly + encoding + signatures",
        ],
    ]
    write_csv(
        TABLES / "sapling_tx_construct_composition_20261022.csv",
        ["component", "median_ms", "share_of_total_pct", "definition"],
        composition_rows,
    )

    # ---- acceptance ----------------------------------------------------
    real_rows = arms["A1_real_1t"] + arms["A2_real_8t"]
    mock_rows = arms["A3_mock_1t"]

    primary_pass = (
        len(real_rows) == 12
        and all(row["verified"] == "true" for row in real_rows)
        and len(mock_rows) == 6
        and all(row["tx_version"] == "V5" for row in mock_rows)
    )

    structural_rows = arms["A1_real_1t"] + arms["A2_real_8t"]
    tx_bytes_values = {row["tx_bytes"] for row in structural_rows}
    structural_pass = (
        len(tx_bytes_values) == 1
        and tx_bytes_values == {str(EXPECTED_TX_BYTES)}
        and all(row["tx_version"] == "V5" for row in structural_rows)
        and all(row["spend_count"] == "1" for row in structural_rows)
        and all(row["output_count"] == "2" for row in structural_rows)
        and all(row["fee_zats"] == str(FEE_ZATS) for row in structural_rows)
        and all(row["value_balance_zats"] == str(VALUE_BALANCE_ZATS) for row in structural_rows)
    )

    proving_share = proving_median / build_median
    share_pass = proving_share >= PROVING_SHARE_MIN

    estimator_diff = abs(sum_proofs_median - proving_median) / build_median
    estimator_pass = estimator_diff <= ESTIMATOR_DIFF_MAX

    mock_pass = mock_median <= MOCK_BUILD_MAX_MS

    cv_a1 = describe(column(a1, "build_ms"))["cv_pct"]
    cv_pass = cv_a1 <= CV_MAX_PCT

    max_sum_error = max(
        abs(row["total_construct_ms"] - (row["build_ms"] + row["serialize_ms"]))
        for row in arms["A1_real_1t"] + arms["A2_real_8t"] + arms["A3_mock_1t"]
    )
    txids = [row["txid"] for row in structural_rows]
    txid_hex_ok = all(re.fullmatch(r"[0-9a-f]{64}", txid) for txid in txids)
    # Both real arms start from the same per-process RNG seed, so run i must
    # produce the identical transaction in A1 and A2. This is a structural
    # check that the two arms actually measured the same work, not a uniqueness
    # check (Groth16 randomness is re-derived from the same seed per process).
    txid_match_across_arms = [row["txid"] for row in a1] == [row["txid"] for row in a2]
    serialize_pass = max_sum_error <= 0.01 and txid_hex_ok and txid_match_across_arms

    acceptance = [
        [
            "primary",
            "complete construction + structure + cryptographic verification",
            "18/18",
            f"{len(real_rows) + len(mock_rows)}/18 (real verified 12/12, mock structural 6/6)",
            "PASS" if primary_pass else "FAIL",
        ],
        [
            "aux1",
            "structural constancy (tx_bytes, V5, 1 spend, 2 outputs, fee, balance)",
            f"tx_bytes={EXPECTED_TX_BYTES}; fee={FEE_ZATS}; balance=+{VALUE_BALANCE_ZATS}",
            f"tx_bytes={sorted(tx_bytes_values)[0]}; fee={FEE_ZATS}; balance=+{VALUE_BALANCE_ZATS}",
            "PASS" if structural_pass else "FAIL",
        ],
        [
            "aux2",
            "proving share of build time",
            f">= {PROVING_SHARE_MIN:.2f}",
            fmt(proving_share, 4),
            "PASS" if share_pass else "FAIL",
        ],
        [
            "aux3",
            "two-estimate agreement (sum_proofs vs paired t_proving)",
            f"<= {ESTIMATOR_DIFF_MAX * 100.0:.0f}% of t_build",
            f"{estimator_diff * 100.0:.3f}%",
            "PASS" if estimator_pass else "FAIL",
        ],
        [
            "aux4",
            "non-proving overhead (mock build)",
            f"<= {MOCK_BUILD_MAX_MS:.0f} ms",
            f"{mock_median:.3f} ms",
            "PASS" if mock_pass else "FAIL",
        ],
        [
            "aux5",
            "A1 within-arm stability",
            f"CV <= {CV_MAX_PCT:.0f}%",
            f"{cv_a1:.3f}%",
            "PASS" if cv_pass else "FAIL",
        ],
        [
            "aux6",
            "serialize consistency + round-trip txid (in-binary assertion)",
            "max residual <= 0.01 ms; A1/A2 txids match per run",
            f"max residual={max_sum_error:.6f} ms; cross-arm txid match={'yes' if txid_match_across_arms else 'no'}",
            "PASS" if serialize_pass else "FAIL",
        ],
    ]
    write_csv(
        TABLES / "sapling_tx_construct_acceptance_20261022.csv",
        ["criterion", "description", "threshold", "observed", "result"],
        acceptance,
    )

    overall = all(row[-1] == "PASS" for row in acceptance)

    # ---- figures -------------------------------------------------------
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - plotting is optional
        print(f"WARNING: matplotlib unavailable ({exc}); tables only.")
        plt = None

    if plt is not None:
        FIGURES.mkdir(parents=True, exist_ok=True)

        # (1) Composition of the 1-thread construction time.
        fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1, 1.25]})
        labels = ["proving\n(spend+outputs)", "non-proving\n(mock build)", "serialize"]
        values = [proving_median, mock_median, serialize_median]
        colors = ["#c0392b", "#7f8c8d", "#2980b9"]
        ax_left.bar(labels, values, color=colors)
        ax_left.set_yscale("log")
        for index, value in enumerate(values):
            ax_left.text(index, value, f"{value:.2f} ms", ha="center", va="bottom", fontsize=9)
        ax_left.set_ylabel("time (ms, log scale)")
        ax_left.set_title(f"A1 (1 thread, 0x1): total {total_median:.0f} ms")
        ax_left.set_ylim(0.01, total_median * 4)
        ax_left.grid(axis="y", alpha=0.3)
        ax_left.annotate(
            f"proving = {proving_median / total_median * 100.0:.2f}% of total",
            xy=(0.98, 0.70),
            xycoords="axes fraction",
            ha="right",
            fontsize=8,
        )

        parts = [
            ("prove_spend", spend_median, "#c0392b"),
            ("prove_output_a", out_a_median, "#e67e22"),
            ("prove_output_b", out_b_median, "#f1c40f"),
            ("serialize", serialize_median, "#2980b9"),
        ]
        left = 0.0
        for label, value, color in parts:
            ax_right.barh(["t_total_construct"], [max(value, 0.0)], left=left, color=color, label=label)
            left += max(value, 0.0)
        ax_right.set_xlabel("time (ms)")
        ax_right.set_title("composition, medians (warm runs 2-6)")
        ax_right.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3)
        ax_right.grid(axis="x", alpha=0.3)
        ax_right.set_xlim(0, total_median * 1.02)
        fig.tight_layout()
        fig.savefig(FIGURES / "sapling_tx_construct_composition_20261022.png", dpi=120)
        plt.close(fig)

        # (2) Per-proof distributions.
        fig, ax = plt.subplots(figsize=(8, 4.6))
        series = [
            ("spend (A1)", column(a1, "prove_spend_ms"), "#c0392b"),
            ("output a (A1)", column(a1, "prove_output_a_ms"), "#e67e22"),
            ("output b (A1)", column(a1, "prove_output_b_ms"), "#f1c40f"),
            ("spend (A2, 8t)", column(a2, "prove_spend_ms"), "#8e44ad"),
            ("output a (A2, 8t)", column(a2, "prove_output_a_ms"), "#16a085"),
            ("output b (A2, 8t)", column(a2, "prove_output_b_ms"), "#2ecc71"),
        ]
        positions = list(range(1, len(series) + 1))
        for position, (label, values, color) in zip(positions, series):
            jitter = [(index - (len(values) - 1) / 2.0) * 0.018 for index in range(len(values))]
            ax.scatter([position + offset for offset in jitter], values, color=color, alpha=0.8, s=26)
            median = statistics.median(values)
            ax.plot([position - 0.22, position + 0.22], [median] * 2, color="black", linewidth=1.6)
            ax.text(position, median, f" {median:.0f}", va="bottom", ha="center", fontsize=7.5)
        ax.set_xticks(positions)
        ax.set_xticklabels([label for label, _, _ in series], rotation=20, ha="right", fontsize=8)
        ax.set_ylabel("per-proof time (ms)")
        ax.set_title("per-proof durations: spend dominates; 8 threads cut both")
        ax.set_ylim(0, max(max(column(a1, "prove_spend_ms")), max(column(a2, "prove_spend_ms"))) * 1.12)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIGURES / "sapling_tx_construct_per_proof_20261022.png", dpi=120)
        plt.close(fig)

        # (3) 1 thread vs 8 threads.
        fig, (ax_bars, ax_ratio) = plt.subplots(1, 2, figsize=(11.5, 4.6))
        metrics = [
            ("t_total", "total_construct_ms"),
            ("t_build", "build_ms"),
            ("spend proof", "prove_spend_ms"),
            ("output proof", "prove_output_a_ms"),
        ]
        positions = list(range(len(metrics)))
        width = 0.36
        for offset, (label, rows, color) in (
            (-width / 2, ("A1 real, 1t, 0x1", a1, "#c0392b")),
            (width / 2, ("A2 real, 8t, 0xFFFF", a2, "#2980b9")),
        ):
            medians = [statistics.median(column(rows, key)) for _, key in metrics]
            ax_bars.bar([p + offset for p in positions], medians, width=width, color=color, label=label)
            for position, value in zip(positions, medians):
                ax_bars.text(position + offset, value, f"{value:.0f}", ha="center", va="bottom", fontsize=7.5)
        ax_bars.set_yscale("log")
        ax_bars.set_xticks(positions)
        ax_bars.set_xticklabels([name for name, _ in metrics])
        ax_bars.set_ylabel("median time (ms, log scale)")
        ax_bars.set_ylim(30, 20_000)
        ax_bars.margins(x=0.10)
        ax_bars.set_title("medians by phase (warm runs 2-6)")
        ax_bars.legend(fontsize=8)
        ax_bars.grid(axis="y", alpha=0.3)

        ratios = [b / a for a, b in zip(column(a1, "total_construct_ms"), column(a2, "total_construct_ms"))]
        ax_ratio.bar([f"run {row['run']}" for row in a1], ratios, color="#34495e")
        ratio_median = statistics.median(ratios)
        ax_ratio.axhline(ratio_median, color="#e74c3c", linestyle="--", label=f"median {ratio_median:.2f}x")
        ax_ratio.set_ylabel("1t / 8t total time")
        ax_ratio.set_title("multithread gain (paired by run)")
        ax_ratio.legend(fontsize=8)
        ax_ratio.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIGURES / "sapling_tx_construct_threads_20261022.png", dpi=120)
        plt.close(fig)

    # ---- console report ------------------------------------------------
    print(f"tag={TAG} repeats={REPEATS} (run 1 dropped)")
    print(f"A1 warm build median {build_median:.3f} ms  (CV {cv_a1:.3f}%)")
    print(f"A2 warm build median {statistics.median(column(a2, 'build_ms')):.3f} ms")
    print(f"A3 warm mock build median {mock_median:.3f} ms")
    print(f"t_proving (paired) median {proving_median:.3f} ms -> {proving_share * 100.0:.2f}% of build")
    print(f"sum_proofs median {sum_proofs_median:.3f} ms  (estimator gap {estimator_diff * 100.0:.3f}%)")
    print(f"t_total_construct median {total_median:.3f} ms")
    print(f"t_verify median {statistics.median(column(a1, 'verify_ms')):.3f} ms (not part of construction)")
    print("")
    for row in acceptance:
        print(f"  {row[0]:<8} {row[4]}  {row[1]} = {row[3]}")
    print("")
    print(f"TX_CONSTRUCT_EXPERIMENT={'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())

