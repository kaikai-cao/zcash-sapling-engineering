# -*- coding: utf-8 -*-
"""Analyse the target-b (balanced-signed Pippenger window) A/B campaign.

Reads the raw per-proof CSVs produced by
`scripts/run_msm_signed_digit_campaign.ps1` (which drives
`scripts/run_pinned_prover_campaign.ps1`) and reports, per arm set:

  * per-arm pooled median prove_ms, over kept batches and over individual
    proofs;
  * the paired ABBA comparison inside each interleaved round, with the
    paired median relative difference and an exact sign-test p-value;
  * Mann-Whitney U (two-sided, normal approximation with tie correction)
    over the kept individual proofs;
  * host-drift guard: first-half vs second-half median per arm;
  * the "correctness all true" check.

Conventions (frozen in
`experiments/metadata/sapling_msm_signed_digit_preregistration_20261017.md`
and `sapling_optimization_validation_protocol_20261017.md`):

  * arm A = SAPLING_MSM_SIGNED_DIGITS=0 (legacy unsigned recoding),
    arm B = SAPLING_MSM_SIGNED_DIGITS=1 (balanced-signed recoding);
  * the first batch of each arm and run 1 of every batch are discarded;
  * a "pair" is the i-th kept A batch against the i-th kept B batch of the
    same interleaved round, so the two members are adjacent in time;
  * the primary acceptance threshold is -3% on the paired/pooled median.

Also parses the `BELLMAN_MSM_STAGE_PROFILE` stderr logs (auxiliary
indicator 1) and writes both derived tables under `results/tables/`.
"""

from __future__ import annotations

import csv
import math
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiments" / "raw" / "csv"
TABLES = ROOT / "results" / "tables"
STAGE_SUMMARY = TABLES / "sapling_msm_signed_digit_stage_profile_20261017.csv"
ABBA_SUMMARY = TABLES / "sapling_msm_signed_digit_abba_20261017.csv"

# name, prover, label prefix, threads, affinity, role
ARMS: list[tuple[str, str, str, str, str, str]] = [
    ("primary_spend_1t_lp0", "spend", "msm_signed_primary", "1", "0x1",
     "primary acceptance arm (frozen)"),
    ("aux_spend_8t_pcores", "spend", "msm_signed_p8t", "8", "0xFFFF",
     "auxiliary non-regression arm"),
    ("aux_output_1t_lp0", "output", "msm_signed_output", "1", "0x1",
     "auxiliary non-regression arm"),
]

STAGE_LOGS = [
    ("off", ROOT / "experiments" / "raw" / "logs" / "msm_stage_profile_signed_off_20261017.stderr.log"),
    ("on", ROOT / "experiments" / "raw" / "logs" / "msm_stage_profile_signed_on_20261017.stderr.log"),
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

    # Discard the chronologically first batch of each arm (frozen convention).
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
            a_batch = [int(row["batch_id"]) for row in a_rows][0]
            b_batch = [int(row["batch_id"]) for row in b_rows][0]
            pair_rel.append((b_ms / a_ms - 1.0) * 100.0)
            pair_detail.append(f"r{round_index}p{index} A{a_batch} {a_ms:.1f} vs B{b_batch} {b_ms:.1f}")
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
    # Positive difference => B faster.
    positives, negatives, sign_p = sign_test_p([a - b for a, b in
                                                zip([median(kept_prove_ms(r)) for r in kept_by_arm["A"]],
                                                    [median(kept_prove_ms(r)) for r in kept_by_arm["B"]])])

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
    print(f"batches kept: A={len(kept_by_arm['A'])} B={len(kept_by_arm['B'])} (dropped batch of each arm: "
          f"{', '.join(str(b) for b in sorted(dropped))})")
    print(f"proofs kept: A={len(all_proofs['A'])} B={len(all_proofs['B'])}; all verified={all_verified}")
    print(f"pooled batch-median:  A={median(all_batches['A']):.1f} ms  B={median(all_batches['B']):.1f} ms  "
          f"=> {median(all_batches['B']) / median(all_batches['A']) * 100 - 100:+.2f}%")
    print(f"pooled proof-median:  A={pooled_a:.1f} ms  B={pooled_b:.1f} ms  => {pooled_b / pooled_a * 100 - 100:+.2f}%  "
          f"(MWU two-sided p={mwu_p:.4f})")
    print(f"paired (ABBA, n={len(pair_rel)}): median {paired_median_rel:+.2f}%; "
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
        "pooled_batch_rel_pct": round(median(all_batches["B"]) / median(all_batches["A"]) * 100 - 100, 3),
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


def parse_stage_log(path: Path) -> dict[int, list[dict]]:
    fields = ("window", "signed", "bucket_count", "chunk_count", "exponent_chunk_prep_ms",
              "bucket_fill_sum_ms", "bucket_reduce_sum_ms", "chunk_parallel_wall_ms",
              "bucket_payload_at_max_concurrency_estimate_bytes")
    grouped: dict[int, list[dict]] = {}
    pattern = re.compile(r"BELLMAN_MSM_STAGE_PROFILE\s+(.*)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.search(line)
        if not match:
            continue
        parsed: dict = {}
        for token in match.group(1).split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if key in fields:
                parsed[key] = value
        count = re.search(r"exponent_count=(\d+)", match.group(1))
        if count and parsed:
            parsed["exponent_count"] = int(count.group(1))
            grouped.setdefault(int(count.group(1)), []).append(parsed)
    return grouped


def analyse_stage() -> list[dict]:
    per_arm = {arm: parse_stage_log(path) for arm, path in STAGE_LOGS}
    sizes = sorted(set(per_arm["off"]) & set(per_arm["on"]), reverse=True)
    rows: list[dict] = []
    print("\n### auxiliary indicator 1 -- H-query MSM stage profile (1 thread, LP0)")
    for size in sizes:
        record = {"exponent_count": size}
        for arm in ("off", "on"):
            entries = per_arm[arm][size]
            record[f"{arm}_window"] = int(entries[0]["window"])
            record[f"{arm}_signed"] = int(entries[0]["signed"])
            record[f"{arm}_chunk_count"] = int(entries[0]["chunk_count"])
            record[f"{arm}_bucket_count"] = int(entries[0]["bucket_count"])
            record[f"{arm}_samples"] = len(entries)
            for field in ("bucket_fill_sum_ms", "bucket_reduce_sum_ms", "exponent_chunk_prep_ms"):
                record[f"{arm}_{field}"] = round(median([float(e[field]) for e in entries]), 3)
        fill_rel = record["on_bucket_fill_sum_ms"] / record["off_bucket_fill_sum_ms"] * 100 - 100
        reduce_rel = record["on_bucket_reduce_sum_ms"] / record["off_bucket_reduce_sum_ms"] * 100 - 100
        record["fill_rel_pct"] = round(fill_rel, 2)
        record["reduce_rel_pct"] = round(reduce_rel, 2)
        if size == sizes[0]:
            print(f"n={size} (H query): window {record['off_window']}->{record['on_window']}, "
                  f"chunk {record['off_chunk_count']}->{record['on_chunk_count']}, "
                  f"fill {record['off_bucket_fill_sum_ms']:.1f}->{record['on_bucket_fill_sum_ms']:.1f} ms ({fill_rel:+.2f}%), "
                  f"reduce {record['off_bucket_reduce_sum_ms']:.1f}->{record['on_bucket_reduce_sum_ms']:.1f} ms ({reduce_rel:+.2f}%)")
        rows.append(record)
    return rows


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
    summary = [analyse(*arm) for arm in ARMS]
    write_table(ABBA_SUMMARY, summary)
    write_table(STAGE_SUMMARY, analyse_stage())

    primary = summary[0]
    print("\n### verdict")
    print(f"primary paired median {primary['paired_median_rel_pct']:+.2f}% "
          f"(acceptance threshold -3%: {'MET' if primary['paired_median_rel_pct'] <= -3.0 else 'NOT MET'}), "
          f"{primary['paired_b_faster']}/{primary['paired_count']} pairs favour B, "
          f"sign p={primary['paired_sign_test_p']}")
    for arm in summary[1:]:
        rel = arm["pooled_batch_rel_pct"]
        print(f"{arm['arm_set']}: pooled batch median {rel:+.2f}% "
              f"(non-regression budget 1%: {'OK' if rel <= 1.0 else 'REGRESSION'})")


if __name__ == "__main__":
    main()
