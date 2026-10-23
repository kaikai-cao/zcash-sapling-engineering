//! Standalone FFT arithmetic scoping benchmark.
//!
//! This binary is measurement-only: it does not touch any production default
//! and is not linked into the prover.  It compares the current Bellman
//! `serial_fft` path with:
//!
//! * `mirror_onfly`: a line-for-line copy of the current radix-2 on-the-fly
//!   twiddle recurrence (harness control);
//! * `cand_radix2_precomputed`: the same butterfly order, but each stage's
//!   twiddles are precomputed once and reused by every block.
//!
//! Run in separate processes for 1 and 8 threads:
//!
//!     fft_arith_bench.exe 1 all
//!     fft_arith_bench.exe 8 all
//!
//! The caller pins the process (`0x1` for 1t, `0xFFFF` for 8t), sets
//! `RAYON_NUM_THREADS`, and for 1t keeps
//! `SAPLING_FFT_SERIAL_SINGLE_THREAD=1` so the production baseline is the
//! in-place serial FFT.

// This harness deliberately keeps the production kernel's expression forms so
// that the baseline and mirror paths stay line-for-line comparable.  Rewriting
// them only to satisfy style lints would weaken that comparison.
#![allow(
    clippy::assign_op_pattern,
    clippy::explicit_counter_loop,
    clippy::manual_is_multiple_of,
    clippy::unusual_byte_groupings
)]

use bellman::domain::{EvaluationDomain, Scalar as DomainScalar};
use bellman::multicore::Worker;
use bls12_381::Scalar;
use ff::PrimeField;
use std::hint::black_box;
use std::time::Instant;

const ROOT_ORDER_LOG: u32 = 32;

#[derive(Clone, Copy, Debug)]
enum Variant {
    Baseline,
    Mirror,
    Candidate,
    CandidateRadix4,
}

#[derive(Clone, Copy, Debug)]
enum Kernel {
    Onfly,
    Precomputed,
    Radix4,
}

fn bitreverse(mut n: u32, l: u32) -> u32 {
    let mut r = 0;
    for _ in 0..l {
        r = (r << 1) | (n & 1);
        n >>= 1;
    }
    r
}

/// Line-for-line copy of `vendor/bellman/src/domain.rs::serial_fft`.
fn fft_radix2_onfly(a: &mut [Scalar], omega: &Scalar) {
    let n = a.len() as u32;
    let log_n = n.trailing_zeros();
    assert_eq!(n, 1 << log_n);

    for k in 0..n {
        let rk = bitreverse(k, log_n);
        if k < rk {
            a.swap(rk as usize, k as usize);
        }
    }

    let mut m = 1u32;
    for _ in 0..log_n {
        let w_m = omega.pow_vartime(&[u64::from(n / (2 * m)), 0, 0, 0]);

        let mut k = 0u32;
        while k < n {
            let mut w = Scalar::one();
            for j in 0..m {
                let mut t = a[(k + j + m) as usize];
                t = t * w;
                let mut tmp = a[(k + j) as usize];
                tmp = tmp - t;
                a[(k + j + m) as usize] = tmp;
                a[(k + j) as usize] = a[(k + j) as usize] + t;
                w = w * w_m;
            }
            k += 2 * m;
        }

        m *= 2;
    }
}

/// Same butterfly order as the current serial FFT, but stage twiddles are
/// built once per stage and reused by every block.
fn fft_radix2_precomputed(a: &mut [Scalar], omega: &Scalar) {
    let n = a.len() as u32;
    let log_n = n.trailing_zeros();
    assert_eq!(n, 1 << log_n);

    for k in 0..n {
        let rk = bitreverse(k, log_n);
        if k < rk {
            a.swap(rk as usize, k as usize);
        }
    }

    let mut twiddles = vec![Scalar::one(); (n / 2) as usize];
    let mut m = 1u32;
    for _ in 0..log_n {
        let w_m = omega.pow_vartime(&[u64::from(n / (2 * m)), 0, 0, 0]);
        for j in 1..m as usize {
            twiddles[j] = twiddles[j - 1] * w_m;
        }

        let mut k = 0u32;
        while k < n {
            for j in 0..m {
                let w = twiddles[j as usize];
                let mut t = a[(k + j + m) as usize];
                t = t * w;
                let mut tmp = a[(k + j) as usize];
                tmp = tmp - t;
                a[(k + j + m) as usize] = tmp;
                a[(k + j) as usize] = a[(k + j) as usize] + t;
            }
            k += 2 * m;
        }

        m *= 2;
    }
}

/// Full per-stage twiddle table: one contiguous allocation.
///
/// The 8-thread four-step path shares one table across all sub-FFTs.  A full
/// table is 2^14-1 scalars (512 KiB) for the four-step sub-transform, rather
/// than eight private 256 KiB stage tables.
struct TwiddleTable {
    log_n: u32,
    offsets: Vec<usize>,
    values: Vec<Scalar>,
}

fn build_twiddle_table(n: usize, omega: &Scalar) -> TwiddleTable {
    let log_n = n.trailing_zeros();
    assert_eq!(n, 1usize << log_n);

    let mut offsets = Vec::with_capacity(log_n as usize);
    let mut values = Vec::with_capacity(n - 1);
    let mut m = 1u32;
    for _ in 0..log_n {
        offsets.push(values.len());
        let w_m = omega.pow_vartime(&[u64::from(n as u32 / (2 * m)), 0, 0, 0]);
        values.push(Scalar::one());
        for _ in 1..m {
            let previous = values[values.len() - 1];
            values.push(previous * w_m);
        }
        m *= 2;
    }

    TwiddleTable {
        log_n,
        offsets,
        values,
    }
}

fn fft_radix2_precomputed_with_table(a: &mut [Scalar], table: &TwiddleTable) {
    let n = a.len() as u32;
    let log_n = table.log_n;
    assert_eq!(n, 1u32 << log_n);

    for k in 0..n {
        let rk = bitreverse(k, log_n);
        if k < rk {
            a.swap(rk as usize, k as usize);
        }
    }

    for stage in 0..log_n {
        let m = 1u32 << stage;
        let offset = table.offsets[stage as usize];

        let mut k = 0u32;
        while k < n {
            for j in 0..m {
                let w = table.values[offset + j as usize];
                let mut t = a[(k + j + m) as usize];
                t = t * w;
                let mut tmp = a[(k + j) as usize];
                tmp = tmp - t;
                a[(k + j + m) as usize] = tmp;
                a[(k + j) as usize] = a[(k + j) as usize] + t;
            }
            k += 2 * m;
        }
    }
}

struct Radix4Stage {
    m: u32,
    offset: usize,
}

/// Precomputed twiddles for a radix-4 decimation-in-time transform.
///
/// `values` stores, for every stage and every j, the three twiddles
/// `w^j, w^{2j}, w^{3j}`.  The table has exactly `n - 1` scalars.
struct Radix4Table {
    log_n: u32,
    stages: Vec<Radix4Stage>,
    values: Vec<Scalar>,
    i: Scalar,
}

fn digit_reverse_base4(mut n: u32, digits: u32) -> u32 {
    let mut r = 0u32;
    for _ in 0..digits {
        r = (r << 2) | (n & 3);
        n >>= 2;
    }
    r
}

fn build_radix4_table(n: usize, omega: &Scalar) -> Radix4Table {
    let log_n = n.trailing_zeros();
    assert_eq!(n, 1usize << log_n);
    assert_eq!(log_n % 2, 0, "radix-4 table requires an even log2(n)");

    let mut stages = Vec::with_capacity((log_n / 2) as usize);
    let mut values = Vec::with_capacity(n - 1);
    let mut m = 1u32;
    while m < n as u32 {
        stages.push(Radix4Stage {
            m,
            offset: values.len(),
        });

        let w_m = omega.pow_vartime(&[u64::from(n as u32 / (4 * m)), 0, 0, 0]);
        let mut w = Scalar::one();
        for _ in 0..m {
            let w2 = w * w;
            let w3 = w2 * w;
            values.push(w);
            values.push(w2);
            values.push(w3);
            w = w * w_m;
        }

        m *= 4;
    }

    let i = omega.pow_vartime(&[(n / 4) as u64, 0, 0, 0]);

    Radix4Table {
        log_n,
        stages,
        values,
        i,
    }
}

/// Radix-4 DIT with base-4 digit-reversed input and natural output.
fn fft_radix4_precomputed_with_table(a: &mut [Scalar], table: &Radix4Table) {
    let n = a.len() as u32;
    let log_n = table.log_n;
    assert_eq!(n, 1u32 << log_n);
    assert_eq!(log_n % 2, 0);

    let digits = log_n / 2;
    for k in 0..n {
        let rk = digit_reverse_base4(k, digits);
        if k < rk {
            a.swap(rk as usize, k as usize);
        }
    }

    for stage in &table.stages {
        let m = stage.m;
        let offset = stage.offset;

        let mut k = 0u32;
        while k < n {
            for j in 0..m {
                let base = offset + 3 * j as usize;
                let w1 = table.values[base];
                let w2 = table.values[base + 1];
                let w3 = table.values[base + 2];

                let a0 = a[(k + j) as usize];
                let a1 = a[(k + j + m) as usize] * w1;
                let a2 = a[(k + j + 2 * m) as usize] * w2;
                let a3 = a[(k + j + 3 * m) as usize] * w3;

                let t0 = a0 + a2;
                let t1 = a0 - a2;
                let t2 = a1 + a3;
                let t3 = a1 - a3;
                let it3 = table.i * t3;

                a[(k + j) as usize] = t0 + t2;
                a[(k + j + m) as usize] = t1 + it3;
                a[(k + j + 2 * m) as usize] = t0 - t2;
                a[(k + j + 3 * m) as usize] = t1 - it3;
            }
            k += 4 * m;
        }
    }
}

/// Mirror of the four-step `parallel_fft`, with the current on-the-fly serial
/// kernel, the radix-2 precomputed-twiddle kernel, or the conditional radix-4
/// precomputed-twiddle kernel.
fn parallel_fft_with_kernel(
    a: &mut [Scalar],
    worker: &Worker,
    omega: &Scalar,
    log_n: u32,
    log_cpus: u32,
    kernel: Kernel,
) {
    assert!(log_n >= log_cpus);

    let num_cpus = 1usize << log_cpus;
    let log_new_n = log_n - log_cpus;
    let mut tmp = vec![vec![Scalar::zero(); 1usize << log_new_n]; num_cpus];
    let new_omega = omega.pow_vartime(&[num_cpus as u64, 0, 0, 0]);

    // Build the table once, then share it read-only across all sub-FFTs.
    let shared_radix2 = match kernel {
        Kernel::Precomputed => Some(build_twiddle_table(1usize << log_new_n, &new_omega)),
        Kernel::Onfly | Kernel::Radix4 => None,
    };
    let shared_radix4 = match kernel {
        Kernel::Radix4 => {
            assert_eq!(log_new_n % 2, 0, "radix-4 sub-FFT requires even log2(n)");
            Some(build_radix4_table(1usize << log_new_n, &new_omega))
        }
        Kernel::Onfly | Kernel::Precomputed => None,
    };
    let shared_radix2 = shared_radix2.as_ref();
    let shared_radix4 = shared_radix4.as_ref();

    worker.scope(0, |scope, _| {
        let a = &*a;

        for (j, tmp) in tmp.iter_mut().enumerate() {
            scope.spawn(move |_scope| {
                let omega_j = omega.pow_vartime(&[j as u64, 0, 0, 0]);
                let omega_step = omega.pow_vartime(&[(j as u64) << log_new_n, 0, 0, 0]);

                let mut elt = Scalar::one();
                for (i, tmp) in tmp.iter_mut().enumerate() {
                    for s in 0..num_cpus {
                        let idx = (i + (s << log_new_n)) % (1usize << log_n);
                        let mut t = a[idx];
                        t = t * elt;
                        *tmp = *tmp + t;
                        elt = elt * omega_step;
                    }
                    elt = elt * omega_j;
                }

                match kernel {
                    Kernel::Onfly => fft_radix2_onfly(tmp, &new_omega),
                    Kernel::Precomputed => {
                        fft_radix2_precomputed_with_table(tmp, shared_radix2.unwrap())
                    }
                    Kernel::Radix4 => {
                        fft_radix4_precomputed_with_table(tmp, shared_radix4.unwrap())
                    }
                }
            });
        }
    });

    worker.scope(a.len(), |scope, chunk| {
        let tmp = &tmp;

        for (idx, a) in a.chunks_mut(chunk).enumerate() {
            scope.spawn(move |_scope| {
                let mut idx = idx * chunk;
                let mask = (1usize << log_cpus) - 1;
                for a in a {
                    *a = tmp[idx & mask][idx >> log_cpus];
                    idx += 1;
                }
            });
        }
    });
}

fn omega_for(n: usize) -> Scalar {
    let log_n = n.trailing_zeros();
    assert!(log_n <= ROOT_ORDER_LOG);
    assert_eq!(Scalar::S, ROOT_ORDER_LOG);
    let exponent = 1u64 << (ROOT_ORDER_LOG - log_n);
    Scalar::ROOT_OF_UNITY.pow_vartime(&[exponent, 0, 0, 0])
}

fn make_input(n: usize) -> Vec<Scalar> {
    (0..n)
        .map(|i| {
            let x = (i as u64)
                .wrapping_mul(0x9E37_79B9_7F4A_7C15)
                .wrapping_add(0x1234_5678_9ABC_DEF);
            Scalar::from(x)
        })
        .collect()
}

fn build_domain(original: &[Scalar]) -> EvaluationDomain<Scalar, DomainScalar<Scalar>> {
    EvaluationDomain::from_coeffs(
        original
            .iter()
            .cloned()
            .map(DomainScalar)
            .collect::<Vec<_>>(),
    )
    .expect("domain construction failed")
}

fn baseline_once(original: &[Scalar], worker: &Worker) -> Vec<Scalar> {
    let mut domain = build_domain(original);
    domain.fft(worker);
    domain
        .into_coeffs()
        .into_iter()
        .map(|value| value.0)
        .collect()
}

fn mirror_once(
    original: &[Scalar],
    omega: &Scalar,
    worker: &Worker,
    threads: usize,
) -> Vec<Scalar> {
    let mut a = original.to_vec();
    if threads == 1 {
        fft_radix2_onfly(&mut a, omega);
    } else {
        let log_n = a.len().trailing_zeros();
        let log_cpus = worker.log_num_threads();
        parallel_fft_with_kernel(&mut a, worker, omega, log_n, log_cpus, Kernel::Onfly);
    }
    a
}

fn candidate_once(
    original: &[Scalar],
    omega: &Scalar,
    worker: &Worker,
    threads: usize,
) -> Vec<Scalar> {
    let mut a = original.to_vec();
    if threads == 1 {
        fft_radix2_precomputed(&mut a, omega);
    } else {
        let log_n = a.len().trailing_zeros();
        let log_cpus = worker.log_num_threads();
        parallel_fft_with_kernel(&mut a, worker, omega, log_n, log_cpus, Kernel::Precomputed);
    }
    a
}

fn candidate_radix4_once(
    original: &[Scalar],
    omega: &Scalar,
    worker: &Worker,
    threads: usize,
) -> Option<Vec<Scalar>> {
    let mut a = original.to_vec();
    if threads == 1 {
        let log_n = a.len().trailing_zeros();
        if log_n % 2 != 0 {
            return None;
        }
        let table = build_radix4_table(a.len(), omega);
        fft_radix4_precomputed_with_table(&mut a, &table);
    } else {
        let log_n = a.len().trailing_zeros();
        let log_cpus = worker.log_num_threads();
        if (log_n - log_cpus) % 2 != 0 {
            return None;
        }
        parallel_fft_with_kernel(&mut a, worker, omega, log_n, log_cpus, Kernel::Radix4);
    }
    Some(a)
}

fn checksum(a: &[Scalar]) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325u64;
    for value in a {
        for byte in value.to_bytes() {
            hash ^= u64::from(byte);
            hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
        }
    }
    hash
}

fn mismatch_count(a: &[Scalar], b: &[Scalar]) -> usize {
    assert_eq!(a.len(), b.len());
    a.iter().zip(b.iter()).filter(|(x, y)| x != y).count()
}

fn check_correctness(n: usize, threads: usize, worker: &Worker) {
    let original = make_input(n);
    let omega = omega_for(n);

    let baseline = baseline_once(&original, worker);
    let mirror = mirror_once(&original, &omega, worker, threads);
    let candidate = candidate_once(&original, &omega, worker, threads);

    let mirror_bad = mismatch_count(&baseline, &mirror);
    let candidate_bad = mismatch_count(&baseline, &candidate);

    println!(
        "correctness,baseline,{threads},{n},0,0.000,{},{},reference",
        checksum(&baseline),
        1
    );
    println!(
        "correctness,mirror_onfly,{threads},{n},0,0.000,{},{},harness",
        checksum(&mirror),
        u8::from(mirror_bad == 0)
    );
    println!(
        "correctness,cand_radix2_precomputed,{threads},{n},0,0.000,{},{},candidate",
        checksum(&candidate),
        u8::from(candidate_bad == 0)
    );

    let mut radix4_bad = None;
    if threads == 8 {
        if let Some(radix4) = candidate_radix4_once(&original, &omega, worker, threads) {
            let bad = mismatch_count(&baseline, &radix4);
            println!(
                "correctness,cand_radix4_precomputed,{threads},{n},0,0.000,{},{},conditional",
                checksum(&radix4),
                u8::from(bad == 0)
            );
            radix4_bad = Some(bad);
        }
    }

    if mirror_bad != 0 || candidate_bad != 0 || radix4_bad.unwrap_or(0) != 0 {
        eprintln!(
            "correctness failure: n={n} threads={threads} mirror_bad={mirror_bad} candidate_bad={candidate_bad} radix4_bad={radix4_bad:?}"
        );
        std::process::exit(3);
    }
}

fn time_variant(
    variant: Variant,
    original: &[Scalar],
    omega: &Scalar,
    worker: &Worker,
    threads: usize,
) -> (f64, u64) {
    match variant {
        Variant::Baseline => {
            // Domain construction is deliberately outside the timed region.
            let mut domain = build_domain(original);
            let start = Instant::now();
            domain.fft(worker);
            let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
            let output: Vec<Scalar> = domain
                .into_coeffs()
                .into_iter()
                .map(|value| value.0)
                .collect();
            (elapsed_ms, checksum(&output))
        }
        Variant::Mirror => {
            let mut a = original.to_vec();
            let start = Instant::now();
            if threads == 1 {
                fft_radix2_onfly(&mut a, omega);
            } else {
                let log_n = a.len().trailing_zeros();
                let log_cpus = worker.log_num_threads();
                parallel_fft_with_kernel(&mut a, worker, omega, log_n, log_cpus, Kernel::Onfly);
            }
            let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
            (elapsed_ms, checksum(&a))
        }
        Variant::Candidate => {
            let mut a = original.to_vec();
            let start = Instant::now();
            if threads == 1 {
                fft_radix2_precomputed(&mut a, omega);
            } else {
                let log_n = a.len().trailing_zeros();
                let log_cpus = worker.log_num_threads();
                parallel_fft_with_kernel(
                    &mut a,
                    worker,
                    omega,
                    log_n,
                    log_cpus,
                    Kernel::Precomputed,
                );
            }
            let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
            (elapsed_ms, checksum(&a))
        }
        Variant::CandidateRadix4 => {
            let mut a = original.to_vec();
            let start = Instant::now();
            if threads == 1 {
                let log_n = a.len().trailing_zeros();
                assert_eq!(log_n % 2, 0, "1t radix-4 benchmark requires even log2(n)");
                let table = build_radix4_table(a.len(), omega);
                fft_radix4_precomputed_with_table(&mut a, &table);
            } else {
                let log_n = a.len().trailing_zeros();
                let log_cpus = worker.log_num_threads();
                parallel_fft_with_kernel(&mut a, worker, omega, log_n, log_cpus, Kernel::Radix4);
            }
            let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
            (elapsed_ms, checksum(&a))
        }
    }
}

fn variant_name(variant: Variant) -> &'static str {
    match variant {
        Variant::Baseline => "baseline",
        Variant::Mirror => "mirror_onfly",
        Variant::Candidate => "cand_radix2_precomputed",
        Variant::CandidateRadix4 => "cand_radix4_precomputed",
    }
}

fn bench_pair(a: Variant, b: Variant, n: usize, threads: usize, pair_name: &str, worker: &Worker) {
    let original = make_input(n);
    let omega = omega_for(n);

    // Three untimed warmups per implementation.
    for _ in 0..3 {
        black_box(time_variant(a, &original, &omega, worker, threads));
        black_box(time_variant(b, &original, &omega, worker, threads));
    }

    for run in 1..=9usize {
        // ABBA-ish ordering: A B | B A | B A | A B | A B ...
        let order = match (run - 1) % 4 {
            0 | 3 => [a, b],
            _ => [b, a],
        };
        for variant in order {
            let (elapsed_ms, cs) = time_variant(variant, &original, &omega, worker, threads);
            println!(
                "time,{},{threads},{n},{run},{elapsed_ms:.6},{cs},1,{}",
                variant_name(variant),
                pair_name
            );
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let threads_arg = args.get(1).map(String::as_str).unwrap_or("1");
    let threads: usize = threads_arg.parse().expect("threads must be 1 or 8");
    let mode = args.get(2).map(String::as_str).unwrap_or("all");
    assert!(threads == 1 || threads == 8, "threads must be 1 or 8");

    if threads == 1 {
        let serial = std::env::var("SAPLING_FFT_SERIAL_SINGLE_THREAD").ok();
        if serial.as_deref() == Some("0") {
            eprintln!(
                "SAPLING_FFT_SERIAL_SINGLE_THREAD=0 would make the 1t baseline use the four-step path; aborting"
            );
            std::process::exit(2);
        }
    }

    let worker = Worker::new();
    let expected_log = if threads == 1 { 0 } else { 3 };
    if worker.log_num_threads() != expected_log {
        eprintln!(
            "thread-count mismatch: requested {threads}, worker.log_num_threads()={} (set RAYON_NUM_THREADS)",
            worker.log_num_threads()
        );
        std::process::exit(2);
    }

    eprintln!(
        "fft_arith_bench threads={threads} log_num_threads={} mode={mode}",
        worker.log_num_threads()
    );

    println!("kind,impl,threads,n,run,elapsed_ms,checksum,exact_match,note");

    let correctness_sizes = [1usize << 10, 1 << 13, 1 << 14, 1 << 17];

    if mode == "correctness" || mode == "all" {
        for &n in &correctness_sizes {
            check_correctness(n, threads, &worker);
        }
    }

    if mode == "bench" || mode == "all" {
        let bench_sizes: &[usize] = if threads == 1 {
            &correctness_sizes
        } else {
            &correctness_sizes[3..]
        };

        for &n in bench_sizes {
            bench_pair(
                Variant::Baseline,
                Variant::Mirror,
                n,
                threads,
                "harness_control",
                &worker,
            );
            bench_pair(
                Variant::Baseline,
                Variant::Candidate,
                n,
                threads,
                "candidate",
                &worker,
            );
            if threads == 8 {
                bench_pair(
                    Variant::Baseline,
                    Variant::CandidateRadix4,
                    n,
                    threads,
                    "candidate_radix4",
                    &worker,
                );
            }
        }
    }
}
