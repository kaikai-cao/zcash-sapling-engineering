//! Deterministic gate for the `SAPLING_FFT_SERIAL_SINGLE_THREAD` fast path.
//!
//! The fast path asserts that the four-step `parallel_fft` degenerates to the
//! in-place `serial_fft` when the worker has a single thread (`log_cpus == 0`):
//! the shuffle collapses to a copy and the copy-back is the identity
//! permutation, so both must produce bit-identical results.
//!
//! The switch is cached in a `OnceLock` for the lifetime of the process, so the
//! two paths cannot be compared inside one process through the public API.
//! Instead this binary hashes the output of the four transforms on a
//! deterministic input and prints the digest; the gate is the two-process
//! comparison
//!
//! ```text
//! SAPLING_FFT_SERIAL_SINGLE_THREAD=0 <bin> > fft_path_gate_off.log
//! SAPLING_FFT_SERIAL_SINGLE_THREAD=1 <bin> > fft_path_gate_on.log
//! ```
//!
//! with one `blake2b=` digest per `(log_n, op)` line that must match across the
//! two logs. Domain sizes cover the real circuits: Output 2^13 and Spend 2^17
//! (2^10 is included as a smaller control).
//!
//! This binary generates no proof and touches no parameters.

use bellman::domain::{EvaluationDomain, Scalar as GroupScalar};
use bellman::multicore::Worker;
use blake2b_simd::Params as Blake2bParams;
use group::ff::PrimeField;

type Fr = bls12_381::Scalar;

/// Domain log-sizes to check: a small control plus the two real circuit sizes.
const LOG_SIZES: [u32; 3] = [10, 13, 17];

/// Deterministic coefficient vector; the same bytes in every process.
fn deterministic_coeffs(log_n: u32) -> Vec<GroupScalar<Fr>> {
    let n = 1usize << log_n;
    let mut state: u64 = 0x9E37_79B9_7F4A_7C15 ^ (log_n as u64);
    (0..n)
        .map(|_| {
            // xorshift64*: deterministic across processes and platforms.
            state ^= state >> 12;
            state ^= state << 25;
            state ^= state >> 27;
            let value = state.wrapping_mul(0x2545_F491_4F6C_DD1D);
            GroupScalar(Fr::from(value))
        })
        .collect()
}

fn digest(values: &[GroupScalar<Fr>]) -> String {
    let mut hasher = Blake2bParams::new().hash_length(32).to_state();
    for value in values {
        hasher.update(value.0.to_repr().as_ref());
    }
    hasher
        .finalize()
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn main() {
    let switch =
        std::env::var("SAPLING_FFT_SERIAL_SINGLE_THREAD").unwrap_or_else(|_| "unset".to_string());
    let worker = Worker::new();
    let log_cpus = worker.log_num_threads();

    println!(
        "FFT_PATH_GATE switch={} rayon_num_threads={} log_num_threads={}",
        switch,
        std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "unset".to_string()),
        log_cpus,
    );

    for log_n in LOG_SIZES {
        let base = deterministic_coeffs(log_n);

        // Each operation starts from the same deterministic state, so the
        // digests are comparable across processes and across operations.
        let mut domain = EvaluationDomain::<Fr, GroupScalar<Fr>>::from_coeffs(base.clone())
            .expect("domain construction");
        domain.fft(&worker);
        println!(
            "FFT_PATH_GATE log_n={log_n} op=fft switch={switch} blake2b={}",
            digest(&domain.into_coeffs())
        );

        let mut domain = EvaluationDomain::<Fr, GroupScalar<Fr>>::from_coeffs(base.clone())
            .expect("domain construction");
        domain.ifft(&worker);
        println!(
            "FFT_PATH_GATE log_n={log_n} op=ifft switch={switch} blake2b={}",
            digest(&domain.into_coeffs())
        );

        let mut domain = EvaluationDomain::<Fr, GroupScalar<Fr>>::from_coeffs(base.clone())
            .expect("domain construction");
        domain.coset_fft(&worker);
        println!(
            "FFT_PATH_GATE log_n={log_n} op=coset_fft switch={switch} blake2b={}",
            digest(&domain.into_coeffs())
        );

        let mut domain = EvaluationDomain::<Fr, GroupScalar<Fr>>::from_coeffs(base)
            .expect("domain construction");
        domain.icoset_fft(&worker);
        println!(
            "FFT_PATH_GATE log_n={log_n} op=icoset_fft switch={switch} blake2b={}",
            digest(&domain.into_coeffs())
        );
    }

    println!("FFT_PATH_GATE_DONE");
}
