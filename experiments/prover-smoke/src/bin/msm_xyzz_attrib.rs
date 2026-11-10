//! Phase D attribution: separates the cost of the XYZZ formula from the cost of
//! its degenerate-case checks, so the NO_GO verdict can be attributed rather
//! than asserted.
//!
//! Three arms over the same fill pattern (4,096 buckets, random bucket index,
//! n = 131,071 mixed additions — the H-query shape):
//!
//!   jac      : `G1Projective += &G1Affine` (shipped `add_mixed`)
//!   xyzz     : `G1BucketXyzz::add_mixed_assign` (with identity/equal checks)
//!   xyzz_un  : `G1BucketXyzz::add_mixed_assign_unchecked` (formula only)
//!
//! `xyzz_un` is **not** a candidate implementation: it is wrong on degenerate
//! inputs. It exists only to price the checks.
//!
//! Run: `RAYON_NUM_THREADS=1 msm_xyzz_attrib.exe`

use bls12_381::{G1Affine, G1BucketXyzz, G1Projective, Scalar};
use std::hint::black_box;
use std::time::Instant;

const BUCKETS: usize = 4096;
const N: usize = 131_071;
const ROUNDS: usize = 9;

fn next_u64(state: &mut u64) -> u64 {
    let mut x = *state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *state = x;
    x.wrapping_mul(0x2545_F491_4F6C_DD1D)
}

fn rand_point(seed: &mut u64) -> G1Projective {
    let mut w = [0u8; 64];
    for c in w.chunks_mut(8) {
        c.copy_from_slice(&next_u64(seed).to_le_bytes());
    }
    G1Projective::generator() * Scalar::from_bytes_wide(&w)
}

fn median(values: &mut [f64]) -> f64 {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap());
    values[values.len() / 2]
}

fn time_jac(pts: &[G1Affine], idx: &[usize]) -> f64 {
    let mut b: Vec<G1Projective> = vec![G1Projective::identity(); BUCKETS];
    let t = Instant::now();
    for (p, &i) in pts.iter().zip(idx.iter()) {
        b[i] += p;
    }
    let ns = t.elapsed().as_nanos() as f64;
    black_box(&b);
    ns
}

fn time_xyzz_checked(pts: &[G1Affine], idx: &[usize]) -> f64 {
    let mut b: Vec<G1BucketXyzz> = vec![G1BucketXyzz::identity(); BUCKETS];
    let t = Instant::now();
    for (p, &i) in pts.iter().zip(idx.iter()) {
        b[i].add_mixed_assign(p, false);
    }
    let ns = t.elapsed().as_nanos() as f64;
    black_box(&b);
    ns
}

fn time_xyzz_unchecked(pts: &[G1Affine], idx: &[usize]) -> f64 {
    let mut b: Vec<G1BucketXyzz> = vec![G1BucketXyzz::identity(); BUCKETS];
    // Seed every touched bucket with one real point so the unchecked path never
    // starts from the identity (which it does not handle).
    for &i in idx.iter().take(BUCKETS) {
        b[i].add_mixed_assign(&pts[0], false);
    }
    let t = Instant::now();
    for (p, &i) in pts.iter().zip(idx.iter()) {
        b[i].add_mixed_assign_unchecked(p, false);
    }
    let ns = t.elapsed().as_nanos() as f64;
    black_box(&b);
    ns
}

fn main() {
    let mut seed = 0x1234_5678_9ABC_DEF1u64;
    let pts: Vec<G1Affine> = (0..N)
        .map(|_| G1Affine::from(rand_point(&mut seed)))
        .collect();
    let mut idx = Vec::with_capacity(N);
    let mut s = 0xA5A5_1234_5678_9ABCu64;
    for _ in 0..N {
        idx.push((next_u64(&mut s) as usize) % BUCKETS);
    }

    let mut jac = Vec::new();
    let mut chk = Vec::new();
    let mut unc = Vec::new();
    for r in 0..ROUNDS {
        // Rotate the order so a monotone drift cannot favour one arm.
        match r % 3 {
            0 => {
                jac.push(time_jac(&pts, &idx));
                chk.push(time_xyzz_checked(&pts, &idx));
                unc.push(time_xyzz_unchecked(&pts, &idx));
            }
            1 => {
                chk.push(time_xyzz_checked(&pts, &idx));
                unc.push(time_xyzz_unchecked(&pts, &idx));
                jac.push(time_jac(&pts, &idx));
            }
            _ => {
                unc.push(time_xyzz_unchecked(&pts, &idx));
                jac.push(time_jac(&pts, &idx));
                chk.push(time_xyzz_checked(&pts, &idx));
            }
        }
    }

    let j = median(&mut jac);
    let c = median(&mut chk);
    let u = median(&mut unc);
    let per = |ns: f64| ns / N as f64;

    println!("n={N} buckets={BUCKETS} rounds={ROUNDS}");
    println!(
        "fill jacobian         {:9.3} ms  {:7.1} ns/add",
        j / 1e6,
        per(j)
    );
    println!(
        "fill xyzz checked     {:9.3} ms  {:7.1} ns/add  {:+.2}% vs jac",
        c / 1e6,
        per(c),
        (c / j - 1.0) * 100.0
    );
    println!(
        "fill xyzz unchecked   {:9.3} ms  {:7.1} ns/add  {:+.2}% vs jac",
        u / 1e6,
        per(u),
        (u / j - 1.0) * 100.0
    );
    println!(
        "degenerate checks cost {:8.1} ns/add  ({:+.2}% of jacobian)",
        per(c - u),
        (c - u) / j * 100.0
    );
}
