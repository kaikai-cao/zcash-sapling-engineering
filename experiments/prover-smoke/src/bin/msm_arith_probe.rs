//! Exploratory unit-cost decomposition probe for the Phase C finding
//! (bellman_1t / blst_1t = 1.90x on H-query G1, with matched modelled op
//! counts). This probe does not gate anything; it only splits the gap by
//! layer, using only types both crates expose publicly:
//!
//!   fill layer      g1_mixed_add (bls12_381 crate)      vs blst_p1_add_or_double_affine
//!   reduce layer    g1_double (bls12_381 crate)         vs blst_p1_add_or_double
//!                   single to_affine (bls12_381 crate)  vs blst_p1s_to_affine (batched)
//!   field layer     scalar mul (bls12_381 crate)        vs blst_fp_mul
//!
//! Notes on what is and is not comparable:
//!  * The blst fill loop internally uses xyzz coordinates, which the Rust
//!    crate does not expose; blst_p1_add_or_double_affine is the exposed
//!    projective+affine add and therefore a *conservative* proxy for the
//!    blst fill unit cost (xyzz would be no slower).
//!  * The field-layer pair is a proxy: both are 381-bit 6-limb Montgomery
//!    multiplications (Fr in bls12_381 vs Fp in blst); the layers are not
//!    the same field, but the multiplication cost structure is the same.
//!  * bellman's single to_affine performs one field inversion per point;
//!    blst_p1s_to_affine performs a single batched inversion (Montgomery's
//!    trick) for the whole vector. This is the batch-affine reduce gap.
//!
//! Conditions: single process, affinity 0x1 (one P-core), no rayon work.
//! 3 warm + 7 measured passes; report the median ns/op.

use bls12_381::{G1Affine, G1Projective, Scalar};
use blst::{blst_fp, blst_p1, blst_p1_affine};
use std::hint::black_box;
use std::time::Instant;

const REPS: usize = 7;
const WARM: usize = 3;

fn next_u64(state: &mut u64) -> u64 {
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

fn median(values: &mut [f64]) -> f64 {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let mid = values.len() / 2;
    if values.len() % 2 == 1 {
        values[mid]
    } else {
        0.5 * (values[mid - 1] + values[mid])
    }
}

fn bench<F: FnMut()>(name: &str, ops_per_pass: usize, mut body: F) {
    let mut samples = Vec::with_capacity(REPS);
    for _ in 0..WARM {
        body();
    }
    for _ in 0..REPS {
        let start = Instant::now();
        body();
        let elapsed_ns = start.elapsed().as_secs_f64() * 1e9;
        samples.push(elapsed_ns / ops_per_pass as f64);
    }
    println!(
        "probe={name} ops_per_pass={ops_per_pass} ns_per_op={:.2}",
        median(&mut samples)
    );
}

/// Deterministic base vector: consecutive multiples of the generator.
fn build_bases(n: usize) -> Vec<G1Affine> {
    let step = G1Affine::generator();
    let mut acc = G1Projective::identity();
    let mut bases = Vec::with_capacity(n);
    for _ in 0..n {
        acc += &step;
        bases.push(G1Affine::from(acc));
    }
    bases
}

/// The same points as blst types (projective for the add probes).
fn to_blst_projectives(bases: &[G1Affine]) -> Vec<blst_p1> {
    let mut out = Vec::with_capacity(bases.len());
    for base in bases {
        let mut affine = blst_p1_affine::default();
        let bytes = base.to_uncompressed();
        let err = unsafe { blst::blst_p1_deserialize(&mut affine, bytes.as_ptr()) };
        assert_eq!(err, blst::BLST_ERROR::BLST_SUCCESS, "deserialize failed");
        let mut point = blst_p1::default();
        unsafe { blst::blst_p1_from_affine(&mut point, &affine) };
        out.push(point);
    }
    out
}

fn main() {
    let mut state = 0x00C0_FFEE_1234_5678u64;
    let n = 20_000usize;

    let bases = build_bases(n);
    let blst_points = to_blst_projectives(&bases);

    // ---------------- fill layer: accumulator + affine base ----------------
    bench("g1_mixed_add_bls12_381", n, || {
        let mut acc = G1Projective::identity();
        for base in bases.iter() {
            acc += base;
        }
        black_box(acc);
    });
    bench("g1_add_or_double_affine_blst", n, || {
        let mut acc = blst_p1::default();
        let mut out = blst_p1::default();
        for base in bases.iter() {
            let mut affine = blst_p1_affine::default();
            let bytes = base.to_uncompressed();
            unsafe { blst::blst_p1_deserialize(&mut affine, bytes.as_ptr()) };
            unsafe { blst::blst_p1_add_or_double_affine(&mut out, black_box(&acc), &affine) };
            acc = out;
        }
        black_box(&acc);
    });

    // ---------------- reduce layer: bucket doubling / full add -------------
    bench("g1_double_bls12_381", n, || {
        let mut acc = G1Projective::from(bases[0]);
        for _ in 0..n {
            acc = acc.double();
        }
        black_box(acc);
    });
    bench("g1_add_or_double_blst", n, || {
        let mut acc = blst_points[0];
        let mut out = blst_p1::default();
        for point in blst_points.iter() {
            unsafe { blst::blst_p1_add_or_double(&mut out, black_box(&acc), point) };
            acc = out;
        }
        black_box(&acc);
    });

    // ---------------- reduce layer: affine conversion ----------------------
    // bls12_381 path: one field inversion per point.
    let projectives: Vec<G1Projective> = bases.iter().map(|b| G1Projective::from(*b)).collect();
    bench("g1_to_affine_pure_bls12_381", n, || {
        let mut sink = G1Affine::identity();
        for point in projectives.iter() {
            sink = G1Affine::from(*point);
        }
        black_box(sink);
    });
    let batch_n = 4_096usize;
    let batch_points: Vec<blst_p1> = blst_points[..batch_n].to_vec();
    let ptrs: Vec<*const blst_p1> = batch_points.iter().map(|p| p as *const blst_p1).collect();
    let mut batch_affine: Vec<blst_p1_affine> = vec![blst_p1_affine::default(); batch_n];
    bench("g1s_to_affine_batch_blst", batch_n, || {
        unsafe {
            blst::blst_p1s_to_affine(batch_affine.as_mut_ptr(), ptrs.as_ptr(), batch_n);
        }
        black_box(&batch_affine[0]);
    });

    // ---------------- field layer (proxy) ----------------------------------
    let sa = random_scalar(&mut state);
    let sb = random_scalar(&mut state);
    bench("scalar_mul_bls12_381", 200_000, || {
        for _ in 0..200_000 {
            black_box(black_box(sa) * black_box(sb));
        }
    });
    let mut fa = blst_fp::default();
    let mut fb = blst_fp::default();
    let bytes_a: Vec<u8> = (0..48u8)
        .map(|i| i.wrapping_mul(7).wrapping_add(1))
        .collect();
    let bytes_b: Vec<u8> = (0..48u8)
        .map(|i| i.wrapping_mul(13).wrapping_add(5))
        .collect();
    unsafe {
        blst::blst_fp_from_bendian(&mut fa, bytes_a.as_ptr());
        blst::blst_fp_from_bendian(&mut fb, bytes_b.as_ptr());
    }
    bench("fp_mul_blst", 200_000, || {
        let mut ret = blst_fp::default();
        for _ in 0..200_000 {
            unsafe { blst::blst_fp_mul(&mut ret, black_box(&fa), black_box(&fb)) };
            black_box(&ret);
        }
    });

    println!("ARITH_PROBE=DONE");
}
