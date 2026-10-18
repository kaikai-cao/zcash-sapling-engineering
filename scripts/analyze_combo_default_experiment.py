# -*- coding: utf-8 -*-
"""Analyse the target-g (combination acceptance + default flip) campaign.

Pre-registration (frozen before any target-g measurement):
`experiments/metadata/sapling_combo_default_preregistration_20261018.md`.

Statistics are byte-identical to `scripts/analyze_qap_fft_fix_experiment.py`
(pooled medians, paired ABBA with an exact sign test, Mann-Whitney U, host-drift
guards, and the no-first-batch-discard sensitivity). The pre-registered primary
indicator is the prove peak **from the current shipped default arm
(`SAPLING_MSM_LAZY_RECODING=0`, `SAPLING_FFT_SERIAL_SINGLE_THREAD=0`) to the
proposed new default arm (both switches = 1)** -- the combination whose joint
gain (-16.88 MB expected) exceeds the 15 MB bar that target a alone missed.

Reads:

  * two control ledgers (no phase probe, so the ledger's own peak column is
    valid), one per arm, from
    `experiments/raw/csv/sapling_prove_memory_ledger_combo_default_{lazy0fix0,lazy1fix1}_20261018.csv`
    (primary indicator; auxiliary 1 for the ledger share of correctness),
  * the raw per-proof CSVs produced by
    `scripts/run_combo_default_campaign.ps1` (auxiliary 2: time non-regression
    on three arm sets, arm A = current default, arm B = proposed default),
  * if the default flip has already been applied and re-verified, the
    post-flip evidence for auxiliary 3:
      - `experiments/raw/logs/fft_path_gate_combo_default_{off,on}_20261018.log`
        (off = explicit four-step, on = the flipped default serial path),
      - `experiments/raw/csv/sapling_prove_memory_ledger_combo_default_postflip_default_20261018.csv`
        (no switches set; must reproduce the proposed-default arm peak),
      - `experiments/raw/csv/sapling_spend_prover_runs_combo_default_postflip_default.csv`
        (no switches set; must verify 5/5).

Conventions (frozen in the pre-registration):

  * run 1 of every ledger arm and run 1 of every batch are discarded (warm
    convention); the first batch of each arm is discarded for the timings;
  * primary threshold: peak drop >= 15,000,000 B between the two arms;
  * auxiliary 2: pooled batch-median non-regression <= 1% on all three arm sets;
  * auxiliary 3 inputs are optional: if absent they are reported as PENDING and
    the verdict is deferred to the post-flip stage (the flip itself is only
    authorised after this script reports PASS on primary + auxiliaries 1 and 2).
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

MEMORY_SUMMARY = TABLES / "sapling_combo_default_memory_20261018.csv"
ABBA_SUMMARY = TABLES / "sapling_combo_default_abba_20261018.csv"

# Frozen thresholds from the pre-registration.
PEAK_DROP_MIN_BYTES = 15_000_000
POSTFLIP_PEAK_TOLERANCE_BYTES = 8_192

LEDGER = {
    "lazy0fix0": RAW / "sapling_prove_memory_ledger_combo_default_lazy0fix0_20261018.csv",
    "lazy1fix1": RAW / "sapling_prove_memory_ledger_combo_default_lazy1fix1_20261018.csv",
}

# Optional auxiliary-3 (post-flip) evidence.
POSTFLIP_LEDGER = (
    RAW / "sapling_prove_memory_ledger_combo_default_postflip_default_20261018.csv"
)
POSTFLIP_BATCH = RAW / "sapling_spend_prover_runs_combo_default_postflip_default.csv"
POSTFLIP_GATE = {
    "off": LOGS / "fft_path_gate_combo_default_off_20261018.log",
    "on": LOGS / "fft_path_gate_combo_default_on_20261018.log",
}

# name, prover, label prefix, threads, affinity, role
ARMS: list[tuple[str, str, str, str, str, str]] = [
    ("primary_spend_1t_lp0", "spend", "combo_default_spend_1t", "1", "0x1",
     "primary time guard (non-regression under the proposed default)"),
    ("aux_spend_8t_pcores", "spend", "combo_default_spend_8t", "8", "0xFFFF",
     "auxiliary non-regression arm"),
    ("aux_output_1t_lp0", "output", "combo_default_output_1t", "1", "0x1",
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
# Primary indicator: prove peak, current default arm -> proposed default arm.
# ---------------------------------------------------------------------------

def ledger_summary(name: str, path: Path) -> dict:
    rows = sorted(read_rows(path), key=lambda row: int(row["run"]))
    kept = rows[1:] if DROP_RUN_ONE else rows
    return {
        "arm": name,
        "runs_kept": len(kept),
        "peak_abs_bytes": int(median([float(r["prove_peak_abs_bytes"]) for r in kept])),
        "peaks_sorted": " ".join(str(int(r["prove_peak_abs_bytes"])) for r in kept),
        "live_before_prove_bytes": int(median([float(r["live_before_prove_bytes"]) for r in kept])),
        "prove_ms": round(median([float(r["prove_ms"]) for r in kept]), 3),
        "all_verified": all(r["verified"] == "true" and r["proof_bytes"] == "192" for r in kept),
    }


def analyse_memory() -> list[dict]:
    print("\n### primary indicator -- prove-phase peak (1 thread, LP0, control ledgers, 5 runs/arm)")
    arms = {name: ledger_summary(name, path) for name, path in LEDGER.items()}
    for name in sorted(arms):
        entry = arms[name]
        print(f"  {entry['arm']:10s} peak_abs={entry['peak_abs_bytes']:,} B  "
              f"live_before_prove={entry['live_before_prove_bytes']:,} B  "
              f"prove_ms={entry['prove_ms']:.1f}  verified={entry['all_verified']}")

    drop = arms["lazy0fix0"]["peak_abs_bytes"] - arms["lazy1fix1"]["peak_abs_bytes"]
    rel = drop / arms["lazy0fix0"]["peak_abs_bytes"] * 100
    print(f"  primary: {arms['lazy0fix0']['peak_abs_bytes']:,} -> "
          f"{arms['lazy1fix1']['peak_abs_bytes']:,} B = drop {drop:,} B ({rel:+.2f}%) "
          f"(threshold >= {PEAK_DROP_MIN_BYTES:,} B: {'MET' if drop >= PEAK_DROP_MIN_BYTES else 'NOT MET'})")

    record = {
        "peak_threshold_bytes": PEAK_DROP_MIN_BYTES,
        "combo_peak_drop_bytes": drop,
        "combo_peak_drop_rel_pct": round(rel, 2),
        "combo_peak_threshold_met": drop >= PEAK_DROP_MIN_BYTES,
        "all_ledger_proofs_verified": all(entry["all_verified"] for entry in arms.values()),
    }
    for name, entry in arms.items():
        record[f"{name}_peak_abs_bytes"] = entry["peak_abs_bytes"]
        record[f"{name}_live_before_prove_bytes"] = entry["live_before_prove_bytes"]
        record[f"{name}_prove_ms"] = entry["prove_ms"]
        record[f"{name}_all_verified"] = entry["all_verified"]
    return [record]


# ---------------------------------------------------------------------------
# Auxiliary 2: end-to-end non-regression under the proposed default.
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


# ---------------------------------------------------------------------------
# Auxiliary 3: post-flip re-verification (optional until the flip happens).
# ---------------------------------------------------------------------------

def check_postflip(record: dict) -> dict:
    def gate_digests(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "op=" in line and "blake2b=" in line:
                fields = dict(token.split("=", 1) for token in line.split() if "=" in token)
                result[f"log_n{fields['log_n']}_{fields['op']}"] = fields["blake2b"]
        return result

    if POSTFLIP_GATE["off"].exists() and POSTFLIP_GATE["on"].exists():
        off = gate_digests(POSTFLIP_GATE["off"])
        on = gate_digests(POSTFLIP_GATE["on"])
        shared = sorted(set(off) & set(on))
        mismatches = [key for key in shared if off[key] != on[key]]
        gate_ok = len(shared) > 0 and not mismatches and set(off) == set(on)
        record["postflip_gate_cases"] = len(shared)
        record["postflip_gate_mismatches"] = len(mismatches)
        record["postflip_gate_identical"] = gate_ok
    else:
        record["postflip_gate_cases"] = ""
        record["postflip_gate_mismatches"] = ""
        record["postflip_gate_identical"] = ""

    if POSTFLIP_LEDGER.exists():
        entry = ledger_summary("postflip_default", POSTFLIP_LEDGER)
        target = record.get("lazy1fix1_peak_abs_bytes")
        if target is None:
            raise SystemExit("post-flip ledger present but the proposed-default arm is missing")
        delta = entry["peak_abs_bytes"] - int(target)
        record["postflip_default_peak_abs_bytes"] = entry["peak_abs_bytes"]
        record["postflip_default_peak_delta_bytes"] = delta
        record["postflip_default_peak_within_tolerance"] = abs(delta) <= POSTFLIP_PEAK_TOLERANCE_BYTES
        record["postflip_default_all_verified"] = entry["all_verified"]
    else:
        record["postflip_default_peak_abs_bytes"] = ""
        record["postflip_default_peak_delta_bytes"] = ""
        record["postflip_default_peak_within_tolerance"] = ""
        record["postflip_default_all_verified"] = ""

    if POSTFLIP_BATCH.exists():
        rows = read_rows(POSTFLIP_BATCH)
        record["postflip_batch_proofs"] = len(rows)
        record["postflip_batch_all_verified"] = all(
            row["verified"] == "true" and row["proof_bytes"] == "192" for row in rows
        )
    else:
        record["postflip_batch_proofs"] = ""
        record["postflip_batch_all_verified"] = ""
    return record


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
    summary = [analyse(*arm) for arm in ARMS]
    record = check_postflip(memory[0])
    write_table(MEMORY_SUMMARY, memory)
    write_table(ABBA_SUMMARY, summary)

    print("\n### verdict (frozen acceptance table)")
    print(f"primary  combo peak drop {record['combo_peak_drop_bytes']:,} B "
          f"({record['combo_peak_drop_rel_pct']:+.2f}%, threshold >= {PEAK_DROP_MIN_BYTES:,} B): "
          f"{'MET' if record['combo_peak_threshold_met'] else 'NOT MET'}")
    print(f"aux 1    all ledger proofs verified: {record['all_ledger_proofs_verified']}")
    for arm in summary:
        rel = arm["pooled_batch_rel_pct"]
        print(f"aux 2    {arm['arm_set']}: pooled batch median {rel:+.2f}% "
              f"(non-regression budget 1%: {'OK' if rel <= 1.0 else 'REGRESSION'})")

    aux3_parts = []
    for key, label in (
        ("postflip_gate_identical", "gate digests identical"),
        ("postflip_default_peak_within_tolerance", "post-flip ledger reproduces the arm peak"),
        ("postflip_batch_all_verified", "post-flip batch verified"),
    ):
        value = record.get(key, "")
        if value == "":
            aux3_parts.append(f"{label}=PENDING")
        else:
            aux3_parts.append(f"{label}={value}")
    print("aux 3    " + "; ".join(aux3_parts))

    passed = (
        record["combo_peak_threshold_met"]
        and record["all_ledger_proofs_verified"]
        and all(a["pooled_batch_rel_pct"] <= 1.0 for a in summary)
        and all(a["all_verified"] for a in summary)
    )
    aux3_done = all(record.get(key, "") != "" for key in (
        "postflip_gate_identical",
        "postflip_default_peak_within_tolerance",
        "postflip_batch_all_verified",
    ))
    aux3_ok = aux3_done and (
        record["postflip_gate_identical"]
        and record["postflip_default_peak_within_tolerance"]
        and record["postflip_default_all_verified"]
        and record["postflip_batch_all_verified"]
    )

    print(f"\nPASS (primary + aux 1 + aux 2) = {passed}")
    print(f"PASS (aux 3, post-flip) = {aux3_ok if aux3_done else 'PENDING'}")
    if not passed:
        if not record["combo_peak_threshold_met"]:
            drop = record["combo_peak_drop_bytes"]
            if drop >= 10_000_000:
                print("pre-registered fallback: combination gain 10-15 MB -> 'close to the bar', "
                      "archive with stage evidence for the owner; still NOT a pass")
            else:
                print("pre-registered fallback verdict: 'combination gain insufficient' -> archive, defaults stay 0")
        else:
            regressed = [a["arm_set"] for a in summary if a["pooled_batch_rel_pct"] > 1.0]
            print(f"pre-registered fallback verdict: 'time regression in {regressed}' -> do not flip defaults")


if __name__ == "__main__":
    main()
