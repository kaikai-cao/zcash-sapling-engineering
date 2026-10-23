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
}

#[derive(Clone, Copy, Debug)]
enum Kernel {
    Onfly,
    Precomputed,
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

/// Mirror of the four-step `parallel_fft`, with either the current on-the-fly
/// serial kernel or the precomputed-twiddle kernel.
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
    let shared_table = match kernel {
        Kernel::Onfly => None,
        Kernel::Precomputed => Some(build_twiddle_table(1usize << log_new_n, &new_omega)),
    };
    let shared_table = shared_table.as_ref();

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
                        fft_radix2_precomputed_with_table(tmp, shared_table.unwrap())
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

    if mirror_bad != 0 || candidate_bad != 0 {
        eprintln!(
            "correctness failure: n={n} threads={threads} mirror_bad={mirror_bad} candidate_bad={candidate_bad}"
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
    }
}

fn variant_name(variant: Variant) -> &'static str {
    match variant {
        Variant::Baseline => "baseline",
        Variant::Mirror => "mirror_onfly",
        Variant::Candidate => "cand_radix2_precomputed",
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
        }
    }
}
