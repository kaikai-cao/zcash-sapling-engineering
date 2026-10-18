//! Exploratory micro-benchmark for the Spend H-query G1 MSM shape.
//!
//! Purpose (target b, see
//! `experiments/metadata/sapling_msm_signed_digit_preregistration_20261017.md`):
//! the archived `SAPLING_MSM_STAGE_TIMING` evidence attributes ~94% of the
//! H-query MSM (n = 131,071, c = 12, 4,095 buckets, 22 chunks) to
//! `bucket_fill`. Before touching the algorithm, decompose that cost:
//!
//!   probe=add_single_acc    N mixed adds into ONE accumulator (latency-bound
//!                           arithmetic cost, working set in registers/L1)
//!   probe=add_rand_bucket   N mixed adds into a random bucket of a 2^c array
//!                           (the real fill pattern)
//!   probe=msm_c<C>          the full `bellman::multiexp` at window width C
//!
//! Correctness gates (all of them must hold):
//!   * every window width and *both* recodings (unsigned and balanced-signed)
//!     must return the identical group element -- MSM is deterministic;
//!   * the balanced-signed digits, both materialised and recomputed from the
//!     carry bits inside the fill, must agree bit-for-bit at c = 2..=20;
//!   * a 64-term prefix must match a plain double-and-add;
//!   * the built-in window rule must match the explicit sweep;
//!   * the small-query path in `multiexp()` (n < 32 -> c = 3) is covered by an
//!     explicit n = 8 case.
//!
//! Knobs: `MSM_WINDOW_BENCH_C` (comma-separated, default `8,10,12,13,14,16`),
//! `MSM_WINDOW_BENCH_REPS` (default 3), `MSM_WINDOW_BENCH_N` (default 131071),
//! `MSM_WINDOW_BENCH_SIGNED` (0/1, default 1: which recoding is timed in the
//! sweep; the cross-mode equality check always runs both). Thread count comes
//! from the ambient `RAYON_NUM_THREADS`; the caller pins the process affinity.

use bellman::multicore::Worker;
use bellman::multiexp::{
    multiexp, set_msm_lazy_recoding, set_msm_signed_digits, set_msm_window_c, Exponent, FullDensity,
};
use bls12_381::{G1Affine, G1Projective, Scalar};
use std::hint::black_box;
use std::sync::Arc;
use std::time::Instant;

fn env_usize(name: &str, fallback: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|raw| raw.trim().parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(fallback)
}

fn env_bool(name: &str, fallback: bool) -> bool {
    std::env::var(name)
        .ok()
        .map(|raw| !matches!(raw.trim(), "0" | "false" | "off" | "no"))
        .unwrap_or(fallback)
}

fn env_window_list() -> Vec<u32> {
    std::env::var("MSM_WINDOW_BENCH_C")
        .ok()
        .map(|raw| {
            raw.split(',')
                .filter_map(|part| part.trim().parse::<u32>().ok())
                .filter(|c| (1..=24).contains(c))
                .collect::<Vec<u32>>()
        })
        .filter(|list| !list.is_empty())
        .unwrap_or_else(|| vec![8, 10, 12, 13, 14, 16])
}

fn next_u64(state: &mut u64) -> u64 {
    // xorshift64*; deterministic so runs are reproducible.
    let mut x = *state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *state = x;
    x.wrapping_mul(0x2545_F491_4F6C_DD1D)
}

fn random_scalar(state: &mut u64) -> Scalar {
    let mut bytes = [0u8; 64];
    for chunk in bytes.chunks_mut(8) {
        chunk.copy_from_slice(&next_u64(state).to_le_bytes());
    }
    Scalar::from_bytes_wide(&bytes)
}

/// Cheap cache-realistic base vector: consecutive multiples of the generator.
/// Bucket indices come from the (independent, random) scalar digits, so the
/// point *values* need not be random -- only the memory layout matters, and the
/// fill loop reads the affine vector sequentially either way.
fn build_bases(n: usize) -> Arc<Vec<G1Affine>> {
    let step = G1Affine::generator();
    let mut acc = G1Projective::identity();
    let mut bases = Vec::with_capacity(n);
    for _ in 0..n {
        acc += &step;
        bases.push(G1Affine::from(acc));
    }
    Arc::new(bases)
}

fn median(values: &mut [f64]) -> f64 {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let mid = values.len() / 2;
    if values.len() % 2 == 1 {
        values[mid]
    } else {
        0.5 * (values[mid - 1] + values[mid])
    }
}

fn probe_single_acc(bases: &[G1Affine], reps: usize) -> f64 {
    let mut samples = Vec::with_capacity(reps);
    for _ in 0..reps {
        let mut acc = G1Projective::identity();
        let start = Instant::now();
        for base in bases.iter() {
            acc += base;
        }
        samples.push(start.elapsed().as_secs_f64() * 1000.0);
        black_box(&acc);
    }
    median(&mut samples)
}

fn probe_random_bucket(bases: &[G1Affine], buckets: usize, seed: u64, reps: usize) -> f64 {
    let mut samples = Vec::with_capacity(reps);
    for rep in 0..reps {
        let mut bucket = vec![G1Projective::identity(); buckets];
        let mut state = seed.wrapping_add(rep as u64 * 0x9E37_79B9_7F4A_7C15);
        let start = Instant::now();
        for base in bases.iter() {
            let index = (next_u64(&mut state) as usize) % buckets;
            bucket[index] += base;
        }
        samples.push(start.elapsed().as_secs_f64() * 1000.0);
        black_box(&bucket);
    }
    median(&mut samples)
}

fn run_msm(
    worker: &Worker,
    bases: &Arc<Vec<G1Affine>>,
    exponents: &Arc<Vec<Exponent<Scalar>>>,
) -> G1Projective {
    multiexp(
        worker,
        (Arc::clone(bases), 0),
        FullDensity,
        Arc::clone(exponents),
    )
    .wait()
    .expect("multiexp failed")
}

/// Total group additions the bucket method performs for the selected recoding:
/// one bucket add per exponent per window, plus two additions per bucket per
/// window during the summation-by-parts reduce.
fn modelled_ops(n: usize, c: u32, signed: bool) -> (usize, usize, usize) {
    let chunks = if signed {
        255 / c as usize + 1
    } else {
        255_usize.div_ceil(c as usize)
    };
    let buckets = if signed {
        1usize << (c - 1)
    } else {
        (1usize << c) - 1
    };
    (chunks, buckets, chunks * (n + 2 * buckets))
}

fn main() {
    let n = env_usize("MSM_WINDOW_BENCH_N", 131_071);
    let reps = env_usize("MSM_WINDOW_BENCH_REPS", 3);
    let windows = env_window_list();
    let signed = env_bool("MSM_WINDOW_BENCH_SIGNED", true);

    let rayon_threads =
        std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".to_string());
    println!(
        "bench=msm_window n={n} reps={reps} rayon_threads={rayon_threads} windows={windows:?} sweep_signed={}",
        signed as u8
    );

    let build_start = Instant::now();
    let bases = build_bases(n);
    let mut state = 0x1234_5678_9ABC_DEF0u64;
    let scalars: Vec<Scalar> = (0..n).map(|_| random_scalar(&mut state)).collect();
    let exponents: Arc<Vec<Exponent<Scalar>>> =
        Arc::new(scalars.iter().map(Exponent::from).collect());
    println!(
        "fixture bases={} exponents={} build_ms={:.1} base_bytes={} exponent_bytes={}",
        bases.len(),
        exponents.len(),
        build_start.elapsed().as_secs_f64() * 1000.0,
        bases.len() * std::mem::size_of::<G1Affine>(),
        exponents.len() * std::mem::size_of::<Exponent<Scalar>>(),
    );

    // --- Arithmetic vs memory decomposition ---------------------------------
    let single = probe_single_acc(&bases, reps);
    println!(
        "probe=add_single_acc n={n} median_ms={single:.3} ns_per_add={:.1}",
        single * 1.0e6 / n as f64
    );

    for c in [8u32, 10, 12] {
        let buckets = (1usize << c) - 1;
        let elapsed = probe_random_bucket(&bases, buckets, 0xDEAD_BEEF_0000_0000 + c as u64, reps);
        println!(
            "probe=add_rand_bucket c={c} buckets={buckets} bucket_array_bytes={} median_ms={elapsed:.3} ns_per_add={:.1}",
            buckets * std::mem::size_of::<G1Projective>(),
            elapsed * 1.0e6 / n as f64
        );
    }

    let worker = Worker::new();

    // --- Correctness gate 1: 64-term prefix vs plain double-and-add ---------
    let prefix = 64usize;
    let prefix_bases: Arc<Vec<G1Affine>> = Arc::new(bases[..prefix].to_vec());
    let prefix_exponents: Arc<Vec<Exponent<Scalar>>> =
        Arc::new(scalars[..prefix].iter().map(Exponent::from).collect());
    let mut naive = G1Projective::identity();
    for (base, scalar) in bases.iter().zip(scalars.iter()).take(prefix) {
        naive += &(G1Projective::from(*base) * scalar);
    }
    for signed_case in [true, false] {
        for c in [1u32, 3, 5, 8] {
            for lazy in [false, true] {
                set_msm_signed_digits(signed_case);
                set_msm_window_c(Some(c));
                set_msm_lazy_recoding(lazy);
                let got = run_msm(&worker, &prefix_bases, &prefix_exponents);
                assert_eq!(
                    got, naive,
                    "prefix MSM disagrees with naive at window {c} signed={signed_case} lazy={lazy}"
                );
                println!(
                    "correctness=naive_prefix c={c} signed={} lazy={} ok",
                    signed_case as u8, lazy as u8
                );
            }
        }
    }
    set_msm_lazy_recoding(false);

    // --- Correctness gate 2: the n < 32 special case and n = 8 --------------
    let tiny_bases: Arc<Vec<G1Affine>> = Arc::new(bases[..8].to_vec());
    let tiny_exponents: Arc<Vec<Exponent<Scalar>>> =
        Arc::new(scalars[..8].iter().map(Exponent::from).collect());
    let mut tiny_naive = G1Projective::identity();
    for (base, scalar) in bases.iter().zip(scalars.iter()).take(8) {
        tiny_naive += &(G1Projective::from(*base) * scalar);
    }
    for signed_case in [true, false] {
        for lazy in [false, true] {
            set_msm_signed_digits(signed_case);
            set_msm_lazy_recoding(lazy);
            let got = run_msm(&worker, &tiny_bases, &tiny_exponents);
            assert_eq!(
                got, tiny_naive,
                "n=8 MSM disagrees with naive signed={signed_case} lazy={lazy}"
            );
            println!(
                "correctness=naive_n8 signed={} lazy={} ok",
                signed_case as u8, lazy as u8
            );
        }
    }
    set_msm_lazy_recoding(false);

    // --- Timed sweep in the selected recoding -------------------------------
    let mut reference: Option<(u32, bool, G1Projective)> = None;
    for c in windows.iter().copied() {
        set_msm_signed_digits(signed);
        set_msm_window_c(Some(c));
        let mut samples = Vec::with_capacity(reps);
        let mut value = G1Projective::identity();
        for _ in 0..reps {
            let start = Instant::now();
            value = run_msm(&worker, &bases, &exponents);
            samples.push(start.elapsed().as_secs_f64() * 1000.0);
        }
        let elapsed = median(&mut samples);
        let (chunks, buckets, ops) = modelled_ops(n, c, signed);
        println!(
            "probe=msm c={c} signed={} chunks={chunks} buckets={buckets} modelled_ops={ops} bucket_array_bytes={} median_ms={elapsed:.3} ns_per_modelled_op={:.1}",
            signed as u8,
            buckets * std::mem::size_of::<G1Projective>(),
            elapsed * 1.0e6 / ops as f64
        );

        match reference {
            None => reference = Some((c, signed, value)),
            Some((reference_c, reference_signed, expected)) => {
                assert_eq!(
                    expected, value,
                    "window {c}/signed={signed} disagrees with window {reference_c}/signed={reference_signed}"
                );
                println!(
                    "correctness=c{c}s{}_equals_c{reference_c}s{reference_signed} ok",
                    signed as u8
                );
            }
        }

        // Gate 3: the *other* recoding at the same width must agree too.
        set_msm_signed_digits(!signed);
        let other = run_msm(&worker, &bases, &exponents);
        assert_eq!(
            value, other,
            "signed and unsigned recodings disagree at window {c}"
        );
        println!("correctness=cross_recoding c={c} ok");
    }

    // --- Correctness gate 4: the built-in window rule -----------------------
    for signed_case in [true, false] {
        set_msm_signed_digits(signed_case);
        set_msm_window_c(None);
        let builtin = run_msm(&worker, &bases, &exponents);
        let (reference_c, reference_signed, expected) =
            reference.expect("at least one window measured");
        assert_eq!(
            expected, builtin,
            "built-in window disagrees with the sweep (signed={signed_case})"
        );
        println!(
            "correctness=builtin_equals_c{reference_c}s{reference_signed} signed={} ok",
            signed_case as u8
        );
    }

    // --- Correctness gate 5: carry-bit recoding vs materialised, full size ----
    // The carry-bit variant must reproduce the materialised digits bit-for-bit
    // at *every* width the dispatch can select (c = 2..=20), not only at the
    // sampled sweep widths. MSM is deterministic, so equality here is exact.
    for c in 2u32..=20 {
        set_msm_signed_digits(true);
        set_msm_window_c(Some(c));

        set_msm_lazy_recoding(false);
        let materialised = run_msm(&worker, &bases, &exponents);

        set_msm_lazy_recoding(true);
        let lazy = run_msm(&worker, &bases, &exponents);

        assert_eq!(
            materialised, lazy,
            "carry-bit recoding disagrees with the materialised digits at window {c}"
        );
        println!("correctness=lazy_equals_materialised c={c} ok");
    }

    // --- Timed comparison of the two recodings at the sweep widths -----------
    // Supplementary evidence only; the pre-registered time guard is end to end.
    for c in windows.iter().copied() {
        set_msm_signed_digits(true);
        set_msm_window_c(Some(c));
        for lazy in [false, true] {
            set_msm_lazy_recoding(lazy);
            let mut samples = Vec::with_capacity(reps);
            for _ in 0..reps {
                let start = Instant::now();
                black_box(run_msm(&worker, &bases, &exponents));
                samples.push(start.elapsed().as_secs_f64() * 1000.0);
            }
            println!(
                "probe=msm_lazy c={c} lazy={} median_ms={:.3}",
                lazy as u8,
                median(&mut samples)
            );
        }
    }
    set_msm_lazy_recoding(false);

    println!("MSM_WINDOW_BENCH=DONE");
}
