# -*- coding: utf-8 -*-
"""Analyse the "default thread/affinity config vs tuned config" experiment.

Target `e` of the optimization protocol: compare the as-shipped default
(Rayon default thread count = one worker per logical processor, no processor
affinity) against a tuned configuration (pinned to the P-core set, 8 threads).

Reads the raw per-proof CSVs produced by `scripts/run_pinned_prover_campaign.ps1`
and reports, per condition:

  * batch count / proof count / all-verified
  * per-batch median prove_ms and the pooled median
  * parameter read+validate median (the serial setup phase)
  * batch total (params read + prepare vk + input prep + sum of prove + sum of verify)

and the statistics the pre-registration asked for:

  * pooled medians of A vs B and the relative change
  * paired comparison on the fine-grained interleaved ABAB part
    (A,B,A,B,... one batch each), with the paired median difference and an
    exact sign-test p-value
  * Mann-Whitney U (two-sided, normal approximation with tie correction)
    over all individual proofs of A vs B
  * drift check: first vs last batch of each interleaved condition

Nothing is modified: this script only reads raw CSVs and writes one derived
table under `results/tables/`.
"""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "experiments" / "raw" / "csv"
TABLES = REPO / "results" / "tables"

# alias -> (prover, label, affinity description, thread description)
CONDITIONS = {
    "A_unbound_default28": ("spend", "default_threads_unbound_20261017", "none (0)", "default (28)"),
    "B_pinned_pcore_8t": ("spend", "pinned8_pcore_20261017", "0xFFFF (P cores)", "8"),
    "A_abab_unbound_default28": ("spend", "abab_unbound_default_20261017", "none (0)", "default (28)"),
    "B_abab_pinned_pcore_8t": ("spend", "abab_pinned8_pcore_20261017", "0xFFFF (P cores)", "8"),
    "A_abab2_unbound_default28": ("spend", "abab2_unbound_default_20261017", "none (0)", "default (28)"),
    "B_abab2_pinned_pcore_8t": ("spend", "abab2_pinned8_pcore_20261017", "0xFFFF (P cores)", "8"),
    "C_abab2_pinned_pcore_16t": ("spend", "abab2_pinned16_pcore_20261017", "0xFFFF (P cores)", "16"),
    "A_quiet_unbound_default28": ("spend", "quiet_abab_unbound_default_20261017", "none (0)", "default (28)"),
    "B_quiet_pinned_pcore_8t": ("spend", "quiet_abab_pinned8_pcore_20261017", "0xFFFF (P cores)", "8"),
    "C_quiet_pinned_pcore_16t": ("spend", "quiet_abab_pinned16_pcore_20261017", "0xFFFF (P cores)", "16"),
    "C_pinned_pcore_16t": ("spend", "pinned16_pcore_20261017", "0xFFFF (P cores)", "16"),
    "D_pinned_all28_defaultt": ("spend", "default_threads_all28_20261017", "0xFFFFFFF (all 28 LP)", "default (28)"),
    "E_pinned_all28_8t": ("spend", "pinned8_all28_20261017", "0xFFFFFFF (all 28 LP)", "8"),
    "Output_A_unbound_default28": ("output", "default_threads_unbound_20261017", "none (0)", "default (28)"),
    "Output_B_pinned_pcore_8t": ("output", "pinned8_pcore_20261017", "0xFFFF (P cores)", "8"),
    "Output_C_pinned_pcore_16t": ("output", "pinned16_pcore_20261017", "0xFFFF (P cores)", "16"),
    "Output_D_pinned_all28_defaultt": ("output", "default_threads_all28_20261017", "0xFFFFFFF (all 28 LP)", "default (28)"),
    "Output_E_pinned_all28_8t": ("output", "pinned8_all28_20261017", "0xFFFFFFF (all 28 LP)", "8"),
    "Rebuild_control_1t_lp0": ("spend", "rebuild_control_1t_lp0_20261017", "0x1 (LP0)", "1"),
}


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def batches_of(prover: str, label: str) -> "list[list[dict]]":
    rows = read_rows(RAW / f"sapling_{prover}_prover_runs_{label}.csv")
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["batch_id"], []).append(row)
    return [grouped[bid] for bid in sorted(grouped)]


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


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
    positives = sum(1 for diff in differences if diff > 0)
    negatives = sum(1 for diff in differences if diff < 0)
    n = positives + negatives
    if n == 0:
        return positives, negatives, 1.0
    k = min(positives, negatives)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2.0**n
    return positives, negatives, min(1.0, 2.0 * tail)


def summarise(alias: str) -> dict:
    prover, label, affinity, threads = CONDITIONS[alias]
    grouped = batches_of(prover, label)

    per_batch_median = [statistics.median([float(r["prove_ms"]) for r in b]) for b in grouped]
    per_batch_total = [
        float(b[0]["params_read_validate_ms"])
        + float(b[0]["prepare_vk_ms"])
        + float(b[0]["input_prep_ms"])
        + sum(float(r["prove_ms"]) for r in b)
        + sum(float(r["verify_ms"]) for r in b)
        for b in grouped
    ]
    all_prove = [float(r["prove_ms"]) for b in grouped for r in b]

    return {
        "alias": alias,
        "prover": prover,
        "label": label,
        "affinity": affinity,
        "threads": threads,
        "batches": len(grouped),
        "proofs": len(all_prove),
        "all_verified": all(r["verified"] == "true" for b in grouped for r in b),
        "params_read_median_ms": round(statistics.median([float(b[0]["params_read_validate_ms"]) for b in grouped]), 1),
        "prove_median_ms": round(statistics.median(all_prove), 3),
        "prove_min_ms": round(min(all_prove), 3),
        "prove_max_ms": round(max(all_prove), 3),
        "per_batch_median_ms": " ".join(f"{v:.1f}" for v in per_batch_median),
        "batch_total_median_ms": round(statistics.median(per_batch_total), 1),
        "_prove": all_prove,
        "_batch_median": per_batch_median,
    }


def main() -> None:
    results = {alias: summarise(alias) for alias in CONDITIONS}

    header = (
        f"{'alias':<27}{'affinity':<22}{'threads':<12}{'bat':<5}{'proofs':<8}"
        f"{'params_read':<13}{'prove_med':<12}{'batch_total':<13}per_batch_medians"
    )
    print(header)
    for row in results.values():
        print(
            f"{row['alias']:<27}{row['affinity']:<22}{row['threads']:<12}{row['batches']:<5}"
            f"{row['proofs']:<8}{row['params_read_median_ms']:<13}{row['prove_median_ms']:<12}"
            f"{row['batch_total_median_ms']:<13}{row['per_batch_median_ms']}"
        )

    a = results["A_unbound_default28"]
    b = results["B_pinned_pcore_8t"]
    print("\n== Spend primary comparison (all available proofs) ==")
    change = 100.0 * (b["prove_median_ms"] - a["prove_median_ms"]) / a["prove_median_ms"]
    print(f"A (unbound, default 28 threads): median {a['prove_median_ms']} ms  (n={a['proofs']}, {a['batches']} batches)")
    print(f"B (P-core pinned, 8 threads)  : median {b['prove_median_ms']} ms  (n={b['proofs']}, {b['batches']} batches)")
    print(f"relative change B vs A = {change:+.2f}%  (negative = B faster)")
    print(f"params read+validate: A {a['params_read_median_ms']} ms vs B {b['params_read_median_ms']} ms"
          f"  ({a['params_read_median_ms'] / b['params_read_median_ms']:.2f}x)")
    print(f"batch total         : A {a['batch_total_median_ms']} ms vs B {b['batch_total_median_ms']} ms"
          f"  ({a['batch_total_median_ms'] / b['batch_total_median_ms']:.2f}x)")

    u, p = mann_whitney_u(a["_prove"], b["_prove"])
    print(f"Mann-Whitney U = {u:.1f}, p = {p:.4f} (two-sided, tie-corrected normal approximation)")

    print("\n== Interleaved rounds (drift-controlled; A/B/C measured back-to-back within each round) ==")
    rounds = [
        ("round1 (A,B)", "A_abab_unbound_default28", "B_abab_pinned_pcore_8t", None),
        ("round2 (A,B,C)", "A_abab2_unbound_default28", "B_abab2_pinned_pcore_8t", "C_abab2_pinned_pcore_16t"),
        ("quiet (A,B,C then C,B,A)", "A_quiet_unbound_default28", "B_quiet_pinned_pcore_8t", "C_quiet_pinned_pcore_16t"),
    ]
    ab_diffs: list[float] = []
    ab_a: list[float] = []
    ac_diffs: list[float] = []
    ac_a: list[float] = []
    for name, a_key, b_key, c_key in rounds:
        a_batches = results[a_key]["_batch_median"]
        b_batches = results[b_key]["_batch_median"]
        c_batches = results[c_key]["_batch_median"] if c_key else None
        print(f"  {name}:")
        for i in range(min(len(a_batches), len(b_batches))):
            difference = b_batches[i] - a_batches[i]
            ab_diffs.append(difference)
            ab_a.append(a_batches[i])
            c_text = (f"   C {c_batches[i]:8.1f}  C-A {c_batches[i] - a_batches[i]:+8.1f}"
                      if c_batches else "")
            print(f"    pair {i + 1}: A {a_batches[i]:8.1f}   B {b_batches[i]:8.1f}   B-A {difference:+8.1f}{c_text}")
        if c_batches:
            for i in range(min(len(a_batches), len(c_batches))):
                ac_diffs.append(c_batches[i] - a_batches[i])
                ac_a.append(a_batches[i])

    def report_pair(alias: str, differences: list[float], baseline: list[float]) -> None:
        if not differences:
            return
        positives, negatives, p_value = sign_test_p(differences)
        median_difference = statistics.median(differences)
        print(f"  {alias}: n_pairs={len(differences)}  paired median diff = {median_difference:+.1f} ms"
              f" ({100.0 * median_difference / statistics.median(baseline):+.1f}%)"
              f"  candidate faster in {negatives}/{len(differences)} pairs  exact sign-test p = {p_value:.3f}")

    report_pair("B - A (both rounds)", ab_diffs, ab_a)
    report_pair("C - A (round 2)", ac_diffs, ac_a)

    a_all = (results["A_abab_unbound_default28"]["_prove"]
             + results["A_abab2_unbound_default28"]["_prove"])
    b_all = (results["B_abab_pinned_pcore_8t"]["_prove"]
             + results["B_abab2_pinned_pcore_8t"]["_prove"])
    pooled_a = statistics.median(a_all)
    pooled_b = statistics.median(b_all)
    print(f"\n  pooled interleaved medians (10 A batches vs 10 B batches):"
          f" A {pooled_a:.1f} ms (n={len(a_all)}) vs B {pooled_b:.1f} ms (n={len(b_all)})"
          f"  ({100.0 * (pooled_b - pooled_a) / pooled_a:+.2f}%)")
    u2, p2 = mann_whitney_u(a_all, b_all)
    print(f"  pooled interleaved Mann-Whitney U = {u2:.1f}, p = {p2:.4f}")

    for alias in ("A_abab_unbound_default28", "B_abab_pinned_pcore_8t", "A_abab2_unbound_default28", "B_abab2_pinned_pcore_8t"):
        row = results[alias]
        first, last = row["_batch_median"][0], row["_batch_median"][-1]
        print(f"  drift {alias}: first {first:.1f} -> last {last:.1f}"
              f" ({100.0 * (last - first) / first:+.1f}%)")

    print("\n== Quiet-host replication only (6 rounds; order A,B,C then C,B,A) ==")
    quiet_a = results["A_quiet_unbound_default28"]
    quiet_b = results["B_quiet_pinned_pcore_8t"]
    quiet_c = results["C_quiet_pinned_pcore_16t"]
    for label, row in (("A", quiet_a), ("B", quiet_b), ("C", quiet_c)):
        print(f"  {label}: prove median {row['prove_median_ms']:>8} ms (n={row['proofs']})   "
              f"params read {row['params_read_median_ms']:>8} ms   per-batch {row['per_batch_median_ms']}")
    for label, row in (("B", quiet_b), ("C", quiet_c)):
        change_quiet = 100.0 * (row["prove_median_ms"] - quiet_a["prove_median_ms"]) / quiet_a["prove_median_ms"]
        u3, p3 = mann_whitney_u(quiet_a["_prove"], row["_prove"])
        print(f"  {label} vs A in the quiet replication: {change_quiet:+.2f}%"
              f"   Mann-Whitney U = {u3:.1f}, p = {p3:.4f}")
    for label, row in (("A", quiet_a), ("B", quiet_b), ("C", quiet_c)):
        first, last = row["_batch_median"][0], row["_batch_median"][-1]
        print(f"  quiet drift {label}: first {first:.1f} -> last {last:.1f}"
              f" ({100.0 * (last - first) / first:+.1f}%)")

    print("\n== Attribution references ==")
    for alias in ("C_pinned_pcore_16t", "D_pinned_all28_defaultt", "E_pinned_all28_8t"):
        row = results[alias]
        print(f"{alias:<27} prove median {row['prove_median_ms']:>9} ms   params read {row['params_read_median_ms']:>8} ms"
              f"   batch total {row['batch_total_median_ms']:>9} ms")
    print(f"{'A (unbound)':<27} prove median {a['prove_median_ms']:>9} ms   params read {a['params_read_median_ms']:>8} ms"
          f"   batch total {a['batch_total_median_ms']:>9} ms")
    print(f"{'B (P-core 8t)':<27} prove median {b['prove_median_ms']:>9} ms   params read {b['params_read_median_ms']:>8} ms"
          f"   batch total {b['batch_total_median_ms']:>9} ms")

    print("\n== Output secondary comparison (full attribution) ==")
    for alias in ("Output_A_unbound_default28", "Output_B_pinned_pcore_8t",
                  "Output_C_pinned_pcore_16t", "Output_D_pinned_all28_defaultt",
                  "Output_E_pinned_all28_8t"):
        row = results[alias]
        print(f"  {alias:<32} affinity {row['affinity']:<22} threads {row['threads']:<13}"
              f" prove median {row['prove_median_ms']:>8} ms  (n={row['proofs']})")
    oa = results["Output_A_unbound_default28"]
    ob = results["Output_B_pinned_pcore_8t"]
    print(f"  pre-declared pair B vs A = "
          f"{100.0 * (ob['prove_median_ms'] - oa['prove_median_ms']) / oa['prove_median_ms']:+.2f}%"
          f"  (positive = candidate slower)")
    uo, po = mann_whitney_u(oa["_prove"], ob["_prove"])
    print(f"  Mann-Whitney U = {uo:.1f}, p = {po:.4f}")

    print("\n== Rebuild-neutrality control (today's binary, 1 thread @ LP0) ==")
    control = results["Rebuild_control_1t_lp0"]
    frozen_warm = 3685.623
    frozen_pooled = 3711.504
    print(f"  today median {control['prove_median_ms']} ms  vs frozen warm baseline {frozen_warm} ms"
          f"  ({100.0 * (control['prove_median_ms'] - frozen_warm) / frozen_warm:+.2f}%)")
    print(f"  today median {control['prove_median_ms']} ms  vs frozen pooled baseline {frozen_pooled} ms"
          f"  ({100.0 * (control['prove_median_ms'] - frozen_pooled) / frozen_pooled:+.2f}%)")

    TABLES.mkdir(parents=True, exist_ok=True)
    target = TABLES / "sapling_default_vs_pinned_config_20261017.csv"
    fieldnames = [k for k in next(iter(results.values())) if not k.startswith("_")]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results.values():
            writer.writerow({key: row[key] for key in fieldnames})
    print(f"\nwrote {target.relative_to(REPO)}")


if __name__ == "__main__":
    main()
