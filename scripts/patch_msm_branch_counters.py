#!/usr/bin/env python3
"""Add low-atomic-overhead branch and base-source counters to Bellman's MSM.

Run from the repository root. The script refuses to run twice, creates a unified
patch artifact, and does not run Cargo or any proving benchmark.
"""
from __future__ import annotations

import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor" / "bellman" / "src" / "multiexp.rs"
PATCH = ROOT / "experiments" / "metadata" / "source_patches" / "spend_msm_branch_counters_20261016.patch"

MARKER = "BELLMAN_MSM_BRANCH_PROFILE"

FIELDS = """    density_true_slot_visits: AtomicUsize,
    density_false_slot_visits: AtomicUsize,
    zero_exponent_slot_visits: AtomicUsize,
    one_exponent_slot_visits: AtomicUsize,
    chunked_exponent_slot_visits: AtomicUsize,
    zero_window_digit_visits: AtomicUsize,
    nonzero_window_digit_visits: AtomicUsize,
    bucket_base_add_calls: AtomicUsize,
    direct_one_add_calls: AtomicUsize,
    base_skip_calls: AtomicUsize,
    base_skip_elements: AtomicUsize,
"""

OLD_FILL_BLOCK = '''        // Sort the bases into buckets.
        let bucket_fill_start = profile.then(Instant::now);
        for (exp, density) in exponents.iter().zip(density_map.as_ref().iter()) {
            if density {
                match exp {
                    ChunkedExponent::Zero => bases.skip(1)?,
                    ChunkedExponent::One => {
                        if handle_trivial {
                            acc.add_assign_from_source(&mut bases)?;
                        } else {
                            bases.skip(1)?;
                        }
                    }
                    ChunkedExponent::Chunks(chunks) => {
                        let exp = chunks[chunk];

                        if exp != 0 {
                            buckets[(exp - 1) as usize].add_assign_from_source(&mut bases)?;
                        } else {
                            bases.skip(1)?;
                        }
                    }
                }
            }
        }
        if let (Some(stage), Some(start)) =
            (worker_stage_profile.as_ref(), bucket_fill_start)
        {
            record_timing(
                &stage.bucket_fill_sum_ns,
                &stage.bucket_fill_max_ns,
                Some(start),
            );
        }
'''

NEW_FILL_BLOCK = '''        // Sort the bases into buckets. Counters are only updated in diagnostic
        // mode and remain local to a chunk until the timed fill loop finishes.
        let mut density_true_slot_visits = 0usize;
        let mut density_false_slot_visits = 0usize;
        let mut zero_exponent_slot_visits = 0usize;
        let mut one_exponent_slot_visits = 0usize;
        let mut chunked_exponent_slot_visits = 0usize;
        let mut zero_window_digit_visits = 0usize;
        let mut nonzero_window_digit_visits = 0usize;
        let mut bucket_base_add_calls = 0usize;
        let mut direct_one_add_calls = 0usize;
        let mut base_skip_calls = 0usize;
        let mut base_skip_elements = 0usize;

        let bucket_fill_start = profile.then(Instant::now);
        if profile {
            // Diagnostic branch: count source-level operations with local
            // counters. This adds overhead to bucket-fill timing in this batch.
            for (exp, density) in exponents.iter().zip(density_map.as_ref().iter()) {
                if density {
                    density_true_slot_visits += 1;
                    match exp {
                        ChunkedExponent::Zero => {
                            zero_exponent_slot_visits += 1;
                            base_skip_calls += 1;
                            base_skip_elements += 1;
                            bases.skip(1)?;
                        }
                        ChunkedExponent::One => {
                            one_exponent_slot_visits += 1;
                            if handle_trivial {
                                direct_one_add_calls += 1;
                                acc.add_assign_from_source(&mut bases)?;
                            } else {
                                base_skip_calls += 1;
                                base_skip_elements += 1;
                                bases.skip(1)?;
                            }
                        }
                        ChunkedExponent::Chunks(chunks) => {
                            chunked_exponent_slot_visits += 1;
                            let digit = chunks[chunk];

                            if digit != 0 {
                                nonzero_window_digit_visits += 1;
                                bucket_base_add_calls += 1;
                                buckets[(digit - 1) as usize].add_assign_from_source(&mut bases)?;
                            } else {
                                zero_window_digit_visits += 1;
                                base_skip_calls += 1;
                                base_skip_elements += 1;
                                bases.skip(1)?;
                            }
                        }
                    }
                } else {
                    density_false_slot_visits += 1;
                }
            }
        } else {
            // Production path preserves the original loop without branch counters.
            for (exp, density) in exponents.iter().zip(density_map.as_ref().iter()) {
                if density {
                    match exp {
                        ChunkedExponent::Zero => bases.skip(1)?,
                        ChunkedExponent::One => {
                            if handle_trivial {
                                acc.add_assign_from_source(&mut bases)?;
                            } else {
                                bases.skip(1)?;
                            }
                        }
                        ChunkedExponent::Chunks(chunks) => {
                            let exp = chunks[chunk];

                            if exp != 0 {
                                buckets[(exp - 1) as usize].add_assign_from_source(&mut bases)?;
                            } else {
                                bases.skip(1)?;
                            }
                        }
                    }
                }
            }
        }
        if let (Some(stage), Some(start)) =
            (worker_stage_profile.as_ref(), bucket_fill_start)
        {
            record_timing(
                &stage.bucket_fill_sum_ns,
                &stage.bucket_fill_max_ns,
                Some(start),
            );
        }

        if let Some(stage) = worker_stage_profile.as_ref() {
            stage.density_true_slot_visits.fetch_add(density_true_slot_visits, Ordering::Relaxed);
            stage.density_false_slot_visits.fetch_add(density_false_slot_visits, Ordering::Relaxed);
            stage.zero_exponent_slot_visits.fetch_add(zero_exponent_slot_visits, Ordering::Relaxed);
            stage.one_exponent_slot_visits.fetch_add(one_exponent_slot_visits, Ordering::Relaxed);
            stage.chunked_exponent_slot_visits.fetch_add(chunked_exponent_slot_visits, Ordering::Relaxed);
            stage.zero_window_digit_visits.fetch_add(zero_window_digit_visits, Ordering::Relaxed);
            stage.nonzero_window_digit_visits.fetch_add(nonzero_window_digit_visits, Ordering::Relaxed);
            stage.bucket_base_add_calls.fetch_add(bucket_base_add_calls, Ordering::Relaxed);
            stage.direct_one_add_calls.fetch_add(direct_one_add_calls, Ordering::Relaxed);
            stage.base_skip_calls.fetch_add(base_skip_calls, Ordering::Relaxed);
            stage.base_skip_elements.fetch_add(base_skip_elements, Ordering::Relaxed);
        }
'''

BRANCH_OUTPUT = '''
        eprintln!(
            "BELLMAN_MSM_BRANCH_PROFILE call_id={} density_true_slot_visits={} density_false_slot_visits={} zero_exponent_slot_visits={} one_exponent_slot_visits={} chunked_exponent_slot_visits={} zero_window_digit_visits={} nonzero_window_digit_visits={} bucket_base_add_calls={} direct_one_add_calls={} base_skip_calls={} base_skip_elements={}",
            call_id.unwrap_or(0),
            stage.density_true_slot_visits.load(Ordering::Relaxed),
            stage.density_false_slot_visits.load(Ordering::Relaxed),
            stage.zero_exponent_slot_visits.load(Ordering::Relaxed),
            stage.one_exponent_slot_visits.load(Ordering::Relaxed),
            stage.chunked_exponent_slot_visits.load(Ordering::Relaxed),
            stage.zero_window_digit_visits.load(Ordering::Relaxed),
            stage.nonzero_window_digit_visits.load(Ordering::Relaxed),
            stage.bucket_base_add_calls.load(Ordering::Relaxed),
            stage.direct_one_add_calls.load(Ordering::Relaxed),
            stage.base_skip_calls.load(Ordering::Relaxed),
            stage.base_skip_elements.load(Ordering::Relaxed),
        );
'''


def require_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"Expected exactly one match for {label}, found {n}. No source was changed.")
    return text.replace(old, new, 1)


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Run this script from repository scripts/ or adjust ROOT; source missing: {SOURCE}")

    old = SOURCE.read_text(encoding="utf-8")
    if MARKER in old:
        raise RuntimeError("Branch-counter marker already exists; refusing to patch twice.")
    if PATCH.exists():
        raise FileExistsError(f"Patch artifact already exists; refusing to overwrite: {PATCH}")

    new = old
    struct_needle = """    bucket_reduce_max_ns: std::sync::atomic::AtomicU64,
    active_chunk_regions: AtomicUsize,
"""
    struct_replacement = """    bucket_reduce_max_ns: std::sync::atomic::AtomicU64,
""" + FIELDS + """    active_chunk_regions: AtomicUsize,
"""
    new = require_once(new, struct_needle, struct_replacement, "MsmStageProfile fields")
    new = require_once(new, OLD_FILL_BLOCK, NEW_FILL_BLOCK, "bucket-fill loop")

    output_needle = """            ns_to_ms(result_merge_ns),
        );
    }

    final_result
"""
    output_replacement = """            ns_to_ms(result_merge_ns),
        );
""" + BRANCH_OUTPUT + """    }

    final_result
"""
    new = require_once(new, output_needle, output_replacement, "stage profile output block")

    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile="a/vendor/bellman/src/multiexp.rs",
        tofile="b/vendor/bellman/src/multiexp.rs",
    )
    patch_text = "".join(diff)

    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_text(patch_text, encoding="utf-8", newline="\n")
    SOURCE.write_text(new, encoding="utf-8", newline="\n")

    print("MSM branch counters added.")
    print(f"Modified source: {SOURCE}")
    print(f"Patch artifact: {PATCH}")
    print("Counters are aggregated per chunk, not atomically incremented per loop slot.")
    print("No proving benchmark was run.")
    print("Next: git diff --check, cargo check --release --locked, then inspect and commit.")


if __name__ == "__main__":
    main()
