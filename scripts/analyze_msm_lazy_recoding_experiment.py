# -*- coding: utf-8 -*-
"""Analyse the target-a (de-materialised H-query windowed exponents) campaign.

Derived from `scripts/analyze_msm_signed_digit_experiment.py` (the target-b
analyzer). The statistics are the same frozen ones -- pooled medians, the
paired ABBA comparison with an exact sign test, Mann-Whitney U and the
host-drift guard -- but this experiment's *primary* acceptance indicator is a
memory metric, so the prove-phase ledger is analysed here as well.

Reads:

  * `experiments/raw/csv/sapling_prove_memory_ledger_msm_lazy_recoding_{off,on}_20261018.csv`
    (primary indicator: prove_peak_abs_bytes),
  * the matching `.stderr.log` files for the `BELLMAN_MSM_MEM_PROBE` rows
    (auxiliary indicator 1: the H-query windowed-representation transient),
  * the raw per-proof CSVs produced by
    `scripts/run_msm_signed_digit_campaign.ps1 -SwitchVar SAPLING_MSM_LAZY_RECODING`
    for the three non-regression arm sets.

Conventions (frozen in
`experiments/metadata/sapling_msm_lazy_recoding_preregistration_20261018.md`):

  * arm A = `SAPLING_MSM_LAZY_RECODING=0` (materialised digits),
    arm B = `SAPLING_MSM_LAZY_RECODING=1` (carry bits, digits folded in fill);
  * run 1 of every ledger arm and run 1 of every batch are discarded (warm
    convention); the first batch of each arm is discarded for the timings;
  * a "pair" is the i-th kept A batch against the i-th kept B batch of the
    same interleaved round;
  * primary threshold: prove_peak_abs_bytes median drop >= 15 MB;
  * auxiliary 1 threshold: H-query prep transient drop >= 20 MB and the carry
    bitmap <= 0.4 MB;
  * auxiliary 2/3: end-to-end median non-regression <= 1%.
"""

from __future__ import annotations

import csv
import math
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiments" / "raw" / "csv"
LOGS = ROOT / "experiments" / "raw" / "logs"
TABLES = ROOT / "results" / "tables"

ABBA_SUMMARY = TABLES / "sapling_msm_lazy_recoding_abba_20261018.csv"
MEMORY_SUMMARY = TABLES / "sapling_msm_lazy_recoding_memory_20261018.csv"

LEDGER = {
    "off": RAW / "sapling_prove_memory_ledger_msm_lazy_recoding_off_20261018.csv",
    "on": RAW / "sapling_prove_memory_ledger_msm_lazy_recoding_on_20261018.csv",
}
LEDGER_STDERR = {
    "off": LOGS / "sapling_prove_memory_ledger_msm_lazy_recoding_off_20261018.stderr.log",
    "on": LOGS / "sapling_prove_memory_ledger_msm_lazy_recoding_on_20261018.stderr.log",
}

# Frozen primary thresholds (bytes).
PEAK_DROP_MIN_BYTES = 15 * 1000 * 1000
PREP_DROP_MIN_BYTES = 20 * 1000 * 1000
CARRY_MAX_BYTES = 400 * 1000

# name, prover, label prefix, threads, affinity, role
ARMS: list[tuple[str, str, str, str, str, str]] = [
    ("primary_spend_1t_lp0", "spend", "msm_lazy_recoding_primary", "1", "0x1",
     "primary time guard (frozen)"),
    ("aux_spend_8t_pcores", "spend", "msm_lazy_recoding_pcores", "8", "0xFFFF",
     "auxiliary non-regression arm"),
    ("aux_output_1t_lp0", "output", "msm_lazy_recoding_output", "1", "0x1",
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
# Primary indicator: prove-phase peak, and where it sits.
# ---------------------------------------------------------------------------

def ledger_rows(arm: str) -> list[dict]:
    rows = read_rows(LEDGER[arm])
    return sorted(rows, key=lambda row: int(row["run"]))


def probe_rows(arm: str) -> dict[int, list[dict]]:
    """`BELLMAN_MSM_MEM_PROBE` rows grouped by exponent_count, in file order."""
    pattern = re.compile(r"BELLMAN_MSM_MEM_PROBE\s+(.*)")
    grouped: dict[int, list[dict]] = {}
    text = LEDGER_STDERR[arm].read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        parsed: dict = {}
        for token in match.group(1).split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            parsed[key] = value
        if "exponent_count" in parsed:
            grouped.setdefault(int(parsed["exponent_count"]), []).append(parsed)
    return grouped


def analyse_memory() -> list[dict]:
    print("\n### primary indicator -- prove-phase peak (1 thread, LP0, 5 runs/arm)")
    record: dict = {}
    for arm in ("off", "on"):
        rows = ledger_rows(arm)
        kept = rows[1:] if DROP_RUN_ONE else rows
        record[f"{arm}_runs_kept"] = len(kept)
        record[f"{arm}_peak_abs_bytes"] = int(median([float(r["prove_peak_abs_bytes"]) for r in kept]))
        record[f"{arm}_peak_delta_bytes"] = int(median([float(r["prove_peak_delta_bytes"]) for r in kept]))
        record[f"{arm}_live_before_prove_bytes"] = int(
            median([float(r["live_before_prove_bytes"]) for r in kept])
        )
        record[f"{arm}_prove_ms"] = round(median([float(r["prove_ms"]) for r in kept]), 3)
        record[f"{arm}_all_verified"] = all(
            r["verified"] == "true" and r["proof_bytes"] == "192" for r in kept
        )

        probes = probe_rows(arm)
        h_query = probes[131_071]
        record[f"{arm}_h_query_prep_bytes"] = int(
            median([float(p["exponent_prep_live_delta_bytes"]) for p in h_query])
        )
        record[f"{arm}_h_query_carry_bitset_bytes"] = int(
            median([float(p.get("carry_bitset_bytes", 0)) for p in h_query])
        )
        record[f"{arm}_h_query_lazy_flag"] = int(median([float(p.get("lazy_recoding", 0)) for p in h_query]))
        record[f"{arm}_h_query_window"] = int(h_query[0]["window"])
        record[f"{arm}_h_query_chunk_count"] = int(h_query[0]["chunk_count"])
        record[f"{arm}_h_query_samples"] = len(h_query)
        # Largest per-call transient among the *aux* MSMs, for the write-up: it
        # shows the peak moving off the H query is not an artefact of the switch.
        record[f"{arm}_max_aux_prep_bytes"] = int(
            max(
                float(p["exponent_prep_live_delta_bytes"])
                for size, entries in probes.items()
                if size < 131_071
                for p in entries
            )
        )

    record["peak_drop_bytes"] = record["off_peak_abs_bytes"] - record["on_peak_abs_bytes"]
    record["peak_drop_rel_pct"] = round(
        record["peak_drop_bytes"] / record["off_peak_abs_bytes"] * 100, 2
    )
    record["prep_drop_bytes"] = record["off_h_query_prep_bytes"] - record["on_h_query_prep_bytes"]
    record["peak_threshold_bytes"] = PEAK_DROP_MIN_BYTES
    record["peak_threshold_met"] = record["peak_drop_bytes"] >= PEAK_DROP_MIN_BYTES
    record["prep_threshold_bytes"] = PREP_DROP_MIN_BYTES
    record["prep_threshold_met"] = record["prep_drop_bytes"] >= PREP_DROP_MIN_BYTES
    record["carry_threshold_bytes"] = CARRY_MAX_BYTES
    record["carry_threshold_met"] = record["on_h_query_carry_bitset_bytes"] <= CARRY_MAX_BYTES

    print(f"off peak_abs {record['off_peak_abs_bytes']:,} B   on peak_abs {record['on_peak_abs_bytes']:,} B")
    print(f"  peak drop {record['peak_drop_bytes']:,} B ({record['peak_drop_rel_pct']:+.2f}%) "
          f"-- threshold >= {PEAK_DROP_MIN_BYTES:,} B: "
          f"{'MET' if record['peak_threshold_met'] else 'NOT MET'}")
    print(f"H-query transient (aux 1): prep {record['off_h_query_prep_bytes']:,} -> "
          f"{record['on_h_query_prep_bytes']:,} B (drop {record['prep_drop_bytes']:,} B, "
          f"{'MET' if record['prep_threshold_met'] else 'NOT MET'}); "
          f"carry bitmap {record['on_h_query_carry_bitset_bytes']:,} B "
          f"({'MET' if record['carry_threshold_met'] else 'NOT MET'})")
    print(f"largest non-H-query MSM transient: off {record['off_max_aux_prep_bytes']:,} B, "
          f"on {record['on_max_aux_prep_bytes']:,} B")
    print(f"in-arm prove_ms (ledger, profiling on): off {record['off_prove_ms']:.1f} ms, "
          f"on {record['on_prove_ms']:.1f} ms")
    print(f"all proofs verified: off={record['off_all_verified']} on={record['on_all_verified']}")
    return [record]


# ---------------------------------------------------------------------------
# Auxiliary 2/3: end-to-end non-regression.
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
    print(f"primary  peak drop {record['peak_drop_bytes']:,} B "
          f"(threshold >= {PEAK_DROP_MIN_BYTES:,} B): "
          f"{'MET' if record['peak_threshold_met'] else 'NOT MET'}")
    print(f"aux 1    H-query transient drop {record['prep_drop_bytes']:,} B "
          f"(threshold >= {PREP_DROP_MIN_BYTES:,} B): "
          f"{'MET' if record['prep_threshold_met'] else 'NOT MET'}; "
          f"carry bitmap {record['on_h_query_carry_bitset_bytes']:,} B "
          f"(<= {CARRY_MAX_BYTES:,} B): {'MET' if record['carry_threshold_met'] else 'NOT MET'}")
    for arm in summary:
        rel = arm["pooled_batch_rel_pct"]
        print(f"aux 2/3  {arm['arm_set']}: pooled batch median {rel:+.2f}% "
              f"(non-regression budget 1%: {'OK' if rel <= 1.0 else 'REGRESSION'})")
    passed = (
        record["peak_threshold_met"]
        and record["prep_threshold_met"]
        and record["carry_threshold_met"]
        and all(a["pooled_batch_rel_pct"] <= 1.0 for a in summary)
    )
    print(f"\nPASS={passed}")
    if not passed and record["prep_threshold_met"]:
        print("pre-registered fallback verdict: 'buffer smaller, peak not converted' -> archive")


if __name__ == "__main__":
    main()
