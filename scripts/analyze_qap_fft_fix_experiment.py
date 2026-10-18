# -*- coding: utf-8 -*-
"""Analyse the target-f (single-thread FFT four-step scratch) campaign.

Derived from `scripts/analyze_msm_lazy_recoding_experiment.py` (the target-a
analyzer). The statistics are the same frozen ones -- pooled medians, the paired
ABBA comparison with an exact sign test, Mann-Whitney U and the host-drift guard
-- but the pre-registered primary indicator is the prove peak **on the
`SAPLING_MSM_LAZY_RECODING=1` configuration**, because that is the configuration
in which the QAP/FFT stage is the binding peak.

Reads:

  * four control ledgers (no phase probe, so the ledger's own peak column is
    valid) = {`SAPLING_MSM_LAZY_RECODING` 0, 1} x {`SAPLING_FFT_SERIAL_SINGLE_THREAD` 0, 1}
    from `experiments/raw/csv/sapling_prove_memory_ledger_qap_fft_fix_*.csv`
    (primary indicator, plus auxiliary 4: the shipped default must not rise),
  * the two probe-enabled stderr logs, parsed for the per-stage peaks
    (auxiliary 1: the QAP/FFT transform stage must lose the scratch),
  * the two `fft_path_gate` logs (auxiliary 2b: the four-step path and the serial
    path must produce bit-identical transforms on deterministic input),
  * the raw per-proof CSVs produced by
    `scripts/run_msm_signed_digit_campaign.ps1 -SwitchVar SAPLING_FFT_SERIAL_SINGLE_THREAD`
    with `SAPLING_MSM_LAZY_RECODING=1` (auxiliary 3: time non-regression).

Conventions (frozen in
`experiments/metadata/sapling_qap_fft_scratch_preregistration_20261018.md`):

  * arm A = `SAPLING_FFT_SERIAL_SINGLE_THREAD=0` (four-step `parallel_fft`),
    arm B = `SAPLING_FFT_SERIAL_SINGLE_THREAD=1` (in-place `serial_fft`);
  * run 1 of every ledger arm and run 1 of every batch are discarded (warm
    convention); the first batch of each arm is discarded for the timings;
  * primary threshold: peak drop >= 3.5 MB on the `lazy=1` configuration;
  * auxiliary 1 threshold: QAP/FFT transform-stage peak drop >= 3.5 MB;
  * auxiliary 3: pooled batch-median non-regression <= 1% on all three arm sets;
  * auxiliary 4: the `lazy=0` peak must not rise.
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiments" / "raw" / "csv"
LOGS = ROOT / "experiments" / "raw" / "logs"
TABLES = ROOT / "results" / "tables"

sys.path.insert(0, str(ROOT / "scripts"))
from analyze_g16_mem_phase_probe import parse_log  # noqa: E402

MEMORY_SUMMARY = TABLES / "sapling_qap_fft_fix_memory_20261018.csv"
ABBA_SUMMARY = TABLES / "sapling_qap_fft_fix_abba_20261018.csv"

# Frozen thresholds (bytes) from the pre-registration.
PEAK_DROP_MIN_BYTES = 3_500_000
STAGE_DROP_MIN_BYTES = 3_500_000

# The stage whose peak carries the four-step scratch.
TRANSFORM_STAGE = "qap_ffts_done"

LEDGER = {
    ("lazy1", "fix0"): RAW / "sapling_prove_memory_ledger_qap_fft_fix_lazy1_fix0_noprobe_20261018.csv",
    ("lazy1", "fix1"): RAW / "sapling_prove_memory_ledger_qap_fft_fix_lazy1_fix1_noprobe_20261018.csv",
    ("lazy0", "fix0"): RAW / "sapling_prove_memory_ledger_qap_fft_fix_lazy0_fix0_noprobe_20261018.csv",
    ("lazy0", "fix1"): RAW / "sapling_prove_memory_ledger_qap_fft_fix_lazy0_fix1_noprobe_20261018.csv",
}

PROBE_LOGS = {
    "fix0": LOGS / "sapling_prove_memory_ledger_qap_fft_fix_lazy1_fix0_probe_20261018.stderr.log",
    "fix1": LOGS / "sapling_prove_memory_ledger_qap_fft_fix_lazy1_fix1_probe_20261018.stderr.log",
}

GATE_LOGS = {
    "off": LOGS / "fft_path_gate_off_20261018.log",
    "on": LOGS / "fft_path_gate_on_20261018.log",
}

# name, prover, label prefix, threads, affinity, role
ARMS: list[tuple[str, str, str, str, str, str]] = [
    ("primary_spend_1t_lp0", "spend", "qap_fft_fix_spend_1t", "1", "0x1",
     "primary time guard (frozen)"),
    ("aux_spend_8t_pcores", "spend", "qap_fft_fix_spend_8t", "8", "0xFFFF",
     "auxiliary non-regression arm (multi-thread FFT path unchanged)"),
    ("aux_output_1t_lp0", "output", "qap_fft_fix_output_1t", "1", "0x1",
     "auxiliary non-regression arm"),
]

DROP_RUN_ONE = True
DROP_FIRST_BATCH_PER_ARM = True
ROUND_SIZE = 4


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_batches(prover: str, label: str) -> "list[tuple[int, list[dict]]]":
    """Per-batch groups, in chronological (batch_id) order."""
    rows = read_rows(RAW / f"sapling_{prover}_prover_runs_{label}.csv")
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["batch_id"]), []).append(row)
    return [(batch_id, grouped[batch_id]) for batch_id in sorted(grouped)]


def kept_prove_ms(rows: list[dict]) -> list[float]:
    ordered = sorted(rows, key=lambda row: int(row["run"]))
    if DROP_RUN_ONE:
        ordered = ordered[1:]
    return [float(row["prove_ms"]) for row in ordered]


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """Two-sided Mann-Whitney U with normal approximation and tie correction."""
    combined = sorted([(value, 0) for value in a] + [(value, 1) for value in b])
    n1, n2 = len(a), len(b)
    ranks = [0.0] * len(combined)
    index = 0
    tie_term = 0.0
    while index < len(combined):
        end = index
        while end + 1 < len(combined) and combined[end + 1][0] == combined[index][0]:
            end += 1
        average_rank = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[position] = average_rank
        tie_size = end - index + 1
        if tie_size > 1:
            tie_term += tie_size**3 - tie_size
        index = end + 1

    rank_sum_a = sum(rank for rank, (_, group) in zip(ranks, combined) if group == 0)
    u_a = rank_sum_a - n1 * (n1 + 1) / 2.0
    u = min(u_a, n1 * n2 - u_a)

    total = n1 + n2
    mean_u = n1 * n2 / 2.0
    tie_correction = tie_term / (total * (total - 1)) if total > 1 else 0.0
    sigma_u = math.sqrt(n1 * n2 * (total + 1 - tie_correction) / 12.0)
    if sigma_u == 0:
        return u, 1.0
    z = (u - mean_u) / sigma_u
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return u, p


def sign_test_p(differences: list[float]) -> tuple[int, int, float]:
    """Exact two-sided sign test. Positive difference means B is faster."""
    positives = sum(1 for diff in differences if diff > 0)
    negatives = sum(1 for diff in differences if diff < 0)
    n = positives + negatives
    if n == 0:
        return positives, negatives, 1.0
    k = min(positives, negatives)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2.0**n
    return positives, negatives, min(1.0, 2.0 * tail)


# ---------------------------------------------------------------------------
# Primary indicator: prove peak on the lazy=1 configuration.
# ---------------------------------------------------------------------------

def ledger_summary(group: tuple[str, str]) -> dict:
    rows = sorted(read_rows(LEDGER[group]), key=lambda row: int(row["run"]))
    kept = rows[1:] if DROP_RUN_ONE else rows
    return {
        "group": "-".join(group),
        "runs_kept": len(kept),
        "peak_abs_bytes": int(median([float(r["prove_peak_abs_bytes"]) for r in kept])),
        "peaks_sorted": " ".join(str(int(r["prove_peak_abs_bytes"])) for r in kept),
        "live_before_prove_bytes": int(median([float(r["live_before_prove_bytes"]) for r in kept])),
        "prove_ms": round(median([float(r["prove_ms"]) for r in kept]), 3),
        "all_verified": all(r["verified"] == "true" and r["proof_bytes"] == "192" for r in kept),
    }


def stage_summary(fix: str) -> dict:
    """Per-run transform-stage peak and body running max from a probe log."""
    rows = parse_log(PROBE_LOGS[fix])
    by_run: dict[int, dict] = {}
    for row in rows:
        if row["run"] == 1:
            continue
        entry = by_run.setdefault(row["run"], {"transform": [], "running_max": 0, "synthesis": []})
        if row["phase_peak_abs_bytes"] != "":
            entry["running_max"] = max(entry["running_max"], int(row["running_max_abs_bytes"]))
        if row["phase"] == TRANSFORM_STAGE:
            entry["transform"].append(int(row["phase_peak_abs_bytes"]))
        if row["phase"] == "circuit_synthesis":
            entry["synthesis"].append(int(row["phase_peak_abs_bytes"]))

    transform_peaks = [peak for entry in by_run.values() for peak in entry["transform"]]
    synthesis_peaks = [peak for entry in by_run.values() for peak in entry["synthesis"]]
    return {
        "probe_runs_kept": len(by_run),
        "transform_peak_abs_bytes": int(median([float(p) for p in transform_peaks])),
        "transform_peaks_sorted": " ".join(str(p) for p in sorted(transform_peaks)),
        "synthesis_peak_abs_bytes": int(median([float(p) for p in synthesis_peaks])),
        "running_max_abs_bytes": max(entry["running_max"] for entry in by_run.values()),
    }


def check_gate() -> dict:
    """The two-process digest gate: same input, both paths, identical output."""

    def digests(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "op=" in line and "blake2b=" in line:
                fields = dict(token.split("=", 1) for token in line.split() if "=" in token)
                result[f"log_n{fields['log_n']}_{fields['op']}"] = fields["blake2b"]
        return result

    off = digests(GATE_LOGS["off"])
    on = digests(GATE_LOGS["on"])
    shared = sorted(set(off) & set(on))
    mismatches = [key for key in shared if off[key] != on[key]]
    return {
        "gate_cases": len(shared),
        "gate_mismatches": len(mismatches),
        "gate_identical": len(shared) > 0 and not mismatches and set(off) == set(on),
    }


def analyse_memory() -> list[dict]:
    print("\n### primary indicator -- prove-phase peak (1 thread, LP0, control ledgers, 5 runs/arm)")
    groups = {group: ledger_summary(group) for group in LEDGER}
    for group in sorted(groups):
        entry = groups[group]
        print(f"  {entry['group']:14s} peak_abs={entry['peak_abs_bytes']:,} B  "
              f"live_before_prove={entry['live_before_prove_bytes']:,} B  "
              f"prove_ms={entry['prove_ms']:.1f}  verified={entry['all_verified']}")

    lazy1 = groups[("lazy1", "fix0")]["peak_abs_bytes"] - groups[("lazy1", "fix1")]["peak_abs_bytes"]
    # Auxiliary 4 is a non-regression criterion: the shipped default (lazy = 0)
    # must not *rise*. A negative "change" is a drop, which is fine.
    lazy0 = groups[("lazy0", "fix1")]["peak_abs_bytes"] - groups[("lazy0", "fix0")]["peak_abs_bytes"]
    print(f"  primary (lazy=1): {groups[('lazy1', 'fix0')]['peak_abs_bytes']:,} -> "
          f"{groups[('lazy1', 'fix1')]['peak_abs_bytes']:,} B = drop {lazy1:,} B "
          f"({'MET' if lazy1 >= PEAK_DROP_MIN_BYTES else 'NOT MET'})")
    print(f"  aux 4  (lazy=0): {groups[('lazy0', 'fix0')]['peak_abs_bytes']:,} -> "
          f"{groups[('lazy0', 'fix1')]['peak_abs_bytes']:,} B = change {lazy0:+,} B "
          f"({'OK (no rise)' if lazy0 <= 0 else 'ROSE'})")

    stages = {fix: stage_summary(fix) for fix in ("fix0", "fix1")}
    stage_drop = stages["fix0"]["transform_peak_abs_bytes"] - stages["fix1"]["transform_peak_abs_bytes"]
    for fix in ("fix0", "fix1"):
        entry = stages[fix]
        print(f"  stage {fix}: transform({TRANSFORM_STAGE}) peak="
              f"{entry['transform_peak_abs_bytes']:,} B  synthesis peak="
              f"{entry['synthesis_peak_abs_bytes']:,} B  running_max={entry['running_max_abs_bytes']:,} B")
    print(f"  aux 1  stage drop {stage_drop:,} B "
          f"({'MET' if stage_drop >= STAGE_DROP_MIN_BYTES else 'NOT MET'})")

    gate = check_gate()
    print(f"  aux 2b gate: {gate['gate_cases']} deterministic cases, "
          f"{gate['gate_mismatches']} mismatching "
          f"({'ALL IDENTICAL' if gate['gate_identical'] else 'MISMATCH'})")

    record = {
        "peak_threshold_bytes": PEAK_DROP_MIN_BYTES,
        "stage_threshold_bytes": STAGE_DROP_MIN_BYTES,
        "lazy1_peak_drop_bytes": lazy1,
        "lazy1_peak_drop_rel_pct": round(
            lazy1 / groups[("lazy1", "fix0")]["peak_abs_bytes"] * 100, 2
        ),
        "lazy1_peak_threshold_met": lazy1 >= PEAK_DROP_MIN_BYTES,
        "lazy0_peak_change_bytes": lazy0,
        "lazy0_peak_unchanged": lazy0 <= 0,
        "stage_peak_drop_bytes": stage_drop,
        "stage_peak_threshold_met": stage_drop >= STAGE_DROP_MIN_BYTES,
        "all_ledger_proofs_verified": all(entry["all_verified"] for entry in groups.values()),
    }
    for group, entry in groups.items():
        prefix = "-".join(group)
        record[f"{prefix}_peak_abs_bytes"] = entry["peak_abs_bytes"]
        record[f"{prefix}_live_before_prove_bytes"] = entry["live_before_prove_bytes"]
        record[f"{prefix}_prove_ms"] = entry["prove_ms"]
    for fix, entry in stages.items():
        record[f"{fix}_transform_peak_abs_bytes"] = entry["transform_peak_abs_bytes"]
        record[f"{fix}_synthesis_peak_abs_bytes"] = entry["synthesis_peak_abs_bytes"]
        record[f"{fix}_running_max_abs_bytes"] = entry["running_max_abs_bytes"]
    record.update(gate)
    return [record]


# ---------------------------------------------------------------------------
# Auxiliary 3: end-to-end non-regression.
# ---------------------------------------------------------------------------

def analyse(name: str, prover: str, prefix: str, threads: str, mask: str, role: str) -> dict:
    off = load_batches(prover, f"{prefix}_off")
    on = load_batches(prover, f"{prefix}_on")
    timeline = sorted(
        [("A", batch_id, rows) for batch_id, rows in off]
        + [("B", batch_id, rows) for batch_id, rows in on],
        key=lambda item: item[1],
    )

    rounds = [timeline[i:i + ROUND_SIZE] for i in range(0, len(timeline), ROUND_SIZE)]
    if any(len(round_) != ROUND_SIZE for round_ in rounds):
        raise SystemExit(f"{name}: {len(timeline)} batches do not fill whole rounds of {ROUND_SIZE}")

    dropped: set[int] = set()
    if DROP_FIRST_BATCH_PER_ARM:
        seen: set[str] = set()
        for arm, batch_id, _rows in timeline:
            if arm not in seen:
                seen.add(arm)
                dropped.add(batch_id)

    kept_by_arm: dict[str, list[list[dict]]] = {"A": [], "B": []}
    pair_rel: list[float] = []
    pair_detail: list[str] = []
    pair_rel_all: list[float] = []
    pooled_batches_all: dict[str, list[float]] = {"A": [], "B": []}
    for round_index, round_ in enumerate(rounds, start=1):
        arms_here: dict[str, list[list[dict]]] = {"A": [], "B": []}
        arms_here_all: dict[str, list[list[dict]]] = {"A": [], "B": []}
        for arm, batch_id, rows in round_:
            arms_here_all[arm].append(rows)
            pooled_batches_all[arm].append(median(kept_prove_ms(rows)))
            if batch_id in dropped:
                continue
            arms_here[arm].append(rows)
            kept_by_arm[arm].append(rows)
        for index, (a_rows, b_rows) in enumerate(zip(arms_here["A"], arms_here["B"]), start=1):
            a_ms = median(kept_prove_ms(a_rows))
            b_ms = median(kept_prove_ms(b_rows))
            pair_rel.append((b_ms / a_ms - 1.0) * 100.0)
            pair_detail.append(f"r{round_index}p{index} {a_ms:.1f} vs {b_ms:.1f} ms")
        for a_rows, b_rows in zip(arms_here_all["A"], arms_here_all["B"]):
            pair_rel_all.append(
                (median(kept_prove_ms(b_rows)) / median(kept_prove_ms(a_rows)) - 1.0) * 100.0
            )

    all_proofs = {arm: [ms for rows in kept_by_arm[arm] for ms in kept_prove_ms(rows)] for arm in ("A", "B")}
    all_batches = {arm: [median(kept_prove_ms(rows)) for rows in kept_by_arm[arm]] for arm in ("A", "B")}

    pooled_a = median(all_proofs["A"])
    pooled_b = median(all_proofs["B"])
    paired_median_rel = median(pair_rel) if pair_rel else float("nan")
    _, mwu_p = mann_whitney_u(all_proofs["A"], all_proofs["B"])
    positives, negatives, sign_p = sign_test_p(
        [a - b for a, b in zip([median(kept_prove_ms(r)) for r in kept_by_arm["A"]],
                               [median(kept_prove_ms(r)) for r in kept_by_arm["B"]])]
    )

    def drift(arm: str) -> tuple[float, float]:
        medians = all_batches[arm]
        half = len(medians) // 2
        return median(medians[:half]), median(medians[half:])

    drift_a = drift("A")
    drift_b = drift("B")
    all_verified = all(
        row["verified"] == "true" and row["proof_bytes"] == "192"
        for arm in ("A", "B")
        for rows in kept_by_arm[arm]
        for row in rows
    )

    print(f"\n### {name} -- {role}")
    print(f"prover={prover} threads={threads} affinity={mask} rounds={len(rounds)}")
    print(f"batches kept: A={len(kept_by_arm['A'])} B={len(kept_by_arm['B'])}")
    print(f"proofs kept: A={len(all_proofs['A'])} B={len(all_proofs['B'])}; all verified={all_verified}")
    pooled_rel = median(all_batches["B"]) / median(all_batches["A"]) * 100 - 100
    print(f"pooled batch-median:  A={median(all_batches['A']):.1f} ms  B={median(all_batches['B']):.1f} ms  "
          f"=> {pooled_rel:+.2f}%")
    print(f"pooled proof-median:  A={pooled_a:.1f} ms  B={pooled_b:.1f} ms  => {pooled_b / pooled_a * 100 - 100:+.2f}%  "
          f"(MWU two-sided p={mwu_p:.4f})")
    print(f"paired (n={len(pair_rel)}): median {paired_median_rel:+.2f}%; "
          f"B faster {positives}/{positives + negatives}; exact sign-test p={sign_p:.4f}")
    for detail in pair_detail:
        print(f"    {detail}")
    print(f"drift A {drift_a[0]:.1f} -> {drift_a[1]:.1f} ({(drift_a[1] / drift_a[0] - 1) * 100:+.1f}%), "
          f"B {drift_b[0]:.1f} -> {drift_b[1]:.1f} ({(drift_b[1] / drift_b[0] - 1) * 100:+.1f}%)")
    all_positives, all_negatives, all_sign_p = sign_test_p(
        [a - b for a, b in zip(pooled_batches_all["A"], pooled_batches_all["B"])]
    )
    print(f"sensitivity (no first-batch discard, run 1 still dropped): n={len(pair_rel_all)} pairs, "
          f"median {median(pair_rel_all):+.2f}%, B faster {all_positives}/{all_positives + all_negatives}, "
          f"sign p={all_sign_p:.4f}")

    return {
        "arm_set": name,
        "role": role,
        "prover": prover,
        "threads": threads,
        "affinity": mask,
        "rounds": len(rounds),
        "paired_count": len(pair_rel),
        "paired_median_rel_pct": round(paired_median_rel, 3),
        "paired_b_faster": positives,
        "paired_sign_test_p": round(sign_p, 4),
        "pooled_batch_median_a_ms": round(median(all_batches["A"]), 1),
        "pooled_batch_median_b_ms": round(median(all_batches["B"]), 1),
        "pooled_batch_rel_pct": round(pooled_rel, 3),
        "pooled_proof_median_a_ms": round(pooled_a, 1),
        "pooled_proof_median_b_ms": round(pooled_b, 1),
        "pooled_proof_rel_pct": round(pooled_b / pooled_a * 100 - 100, 3),
        "mwu_two_sided_p": round(mwu_p, 4),
        "proofs_a": len(all_proofs["A"]),
        "proofs_b": len(all_proofs["B"]),
        "all_verified": all_verified,
        "drift_a_rel_pct": round((drift_a[1] / drift_a[0] - 1) * 100, 2),
        "drift_b_rel_pct": round((drift_b[1] / drift_b[0] - 1) * 100, 2),
        "sensitivity_pairs": len(pair_rel_all),
        "sensitivity_paired_median_rel_pct": round(median(pair_rel_all), 3),
        "sensitivity_b_faster": all_positives,
        "sensitivity_sign_test_p": round(all_sign_p, 4),
    }


def write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {path.relative_to(ROOT)}")


def main() -> None:
    memory = analyse_memory()
    write_table(MEMORY_SUMMARY, memory)

    summary = [analyse(*arm) for arm in ARMS]
    write_table(ABBA_SUMMARY, summary)

    record = memory[0]
    print("\n### verdict (frozen acceptance table)")
    print(f"primary  lazy=1 peak drop {record['lazy1_peak_drop_bytes']:,} B "
          f"({record['lazy1_peak_drop_rel_pct']:+.2f}%, threshold >= {PEAK_DROP_MIN_BYTES:,} B): "
          f"{'MET' if record['lazy1_peak_threshold_met'] else 'NOT MET'}")
    print(f"aux 1    QAP/FFT transform stage drop {record['stage_peak_drop_bytes']:,} B "
          f"(threshold >= {STAGE_DROP_MIN_BYTES:,} B): "
          f"{'MET' if record['stage_peak_threshold_met'] else 'NOT MET'}")
    print(f"aux 2a   all ledger proofs verified: {record['all_ledger_proofs_verified']}")
    print(f"aux 2b   serial vs four-step digests identical: {record['gate_identical']} "
          f"({record['gate_cases']} cases, {record['gate_mismatches']} mismatches)")
    print(f"aux 4    lazy=0 peak change {record['lazy0_peak_change_bytes']:+,} B: "
          f"{'UNCHANGED/OK' if record['lazy0_peak_unchanged'] else 'ROSE'}")
    for arm in summary:
        rel = arm["pooled_batch_rel_pct"]
        print(f"aux 3    {arm['arm_set']}: pooled batch median {rel:+.2f}% "
              f"(non-regression budget 1%: {'OK' if rel <= 1.0 else 'REGRESSION'})")

    passed = (
        record["lazy1_peak_threshold_met"]
        and record["stage_peak_threshold_met"]
        and record["all_ledger_proofs_verified"]
        and record["gate_identical"]
        and record["lazy0_peak_unchanged"]
        and all(a["pooled_batch_rel_pct"] <= 1.0 for a in summary)
    )
    print(f"\nPASS={passed}")
    if not passed:
        if record["stage_peak_threshold_met"] and not record["lazy1_peak_threshold_met"]:
            print("pre-registered fallback verdict: 'scratch gone, peak not converted' -> archive")
        elif not record["stage_peak_threshold_met"]:
            print("pre-registered fallback verdict: 'single-thread scratch not removed' -> archive")
        elif not record["lazy0_peak_unchanged"]:
            print("pre-registered fallback verdict: 'side effect on the shipped default' -> archive")
        else:
            print("pre-registered fallback verdict: 'memory traded for time' -> archive")


if __name__ == "__main__":
    main()
