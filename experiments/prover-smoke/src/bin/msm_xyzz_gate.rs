//! Phase D correctness gate + memory ledger for the XYZZ bucket path.
//!
//! Pre-registration: `experiments/metadata/sapling_msm_phase_d_xyzz_preregistration_20261102.md`
//! §4 (C1–C8) and §6 (memory ledger).
//!
//! Every check compares **curve points byte-for-byte** after uncompressed
//! serialisation; "the program did not crash" is never accepted as evidence.
//!
//! Exit code 0 = all gates passed, 1 = at least one failure (printed as FAIL).

use bellman::multicore::Worker;
use bellman::multiexp::xyzz_g1::multiexp_g1_xyzz;
use bellman::multiexp::{multiexp, Exponent, FullDensity};
use bls12_381::{G1Affine, G1BucketXyzz, G1Projective, Scalar};
use std::sync::Arc;

struct Gate {
    pass: usize,
    fail: usize,
}

impl Gate {
    fn check(&mut self, name: &str, ok: bool) {
        if ok {
            self.pass += 1;
            println!("PASS {name}");
        } else {
            self.fail += 1;
            println!("FAIL {name}");
        }
    }
}

fn bytes(p: &G1Projective) -> [u8; 96] {
    G1Affine::from(*p).to_uncompressed()
}

fn same(a: &G1Projective, b: &G1Projective) -> bool {
    bytes(a) == bytes(b)
}

fn rand_point(seed: &mut u64) -> G1Projective {
    let mut next = || {
        *seed ^= *seed << 13;
        *seed ^= *seed >> 7;
        *seed ^= *seed << 17;
        *seed
    };
    let mut w = [0u8; 64];
    for c in w.chunks_mut(8) {
        c.copy_from_slice(&next().to_le_bytes());
    }
    G1Projective::generator() * Scalar::from_bytes_wide(&w)
}

fn rand_scalar(seed: &mut u64) -> Scalar {
    let mut next = || {
        *seed ^= *seed << 13;
        *seed ^= *seed >> 7;
        *seed ^= *seed << 17;
        *seed
    };
    let mut w = [0u8; 64];
    for c in w.chunks_mut(8) {
        c.copy_from_slice(&next().to_le_bytes());
    }
    Scalar::from_bytes_wide(&w)
}

/// Builds a dense (bases, exponents) fixture of size `n`.
fn fixture(n: usize, seed: u64) -> (Arc<Vec<G1Affine>>, Arc<Vec<Exponent<Scalar>>>) {
    let mut s = seed;
    let step = G1Affine::generator();
    let mut acc = G1Projective::identity();
    let mut bases = Vec::with_capacity(n);
    for _ in 0..n {
        acc += &step;
        bases.push(G1Affine::from(acc));
    }
    let exps: Vec<Exponent<Scalar>> = (0..n)
        .map(|_| Exponent::from(rand_scalar(&mut s)))
        .collect();
    (Arc::new(bases), Arc::new(exps))
}

fn msm_jac(worker: &Worker, bases: &Arc<Vec<G1Affine>>, exps: &Arc<Vec<Exponent<Scalar>>>) -> G1Projective {
    multiexp(worker, (Arc::clone(bases), 0), FullDensity, Arc::clone(exps))
        .wait()
        .expect("jacobian multiexp failed")
}

fn msm_xyzz(worker: &Worker, bases: &Arc<Vec<G1Affine>>, exps: &Arc<Vec<Exponent<Scalar>>>) -> G1Projective {
    multiexp_g1_xyzz(worker, Arc::clone(bases), Arc::clone(exps))
        .wait()
        .expect("xyzz multiexp failed")
}

fn main() {
    let mut g = Gate { pass: 0, fail: 0 };
    let gen = G1Projective::generator();
    let gen_aff = G1Affine::from(gen);
    let mut seed = 0x9E37_79B9_7F4A_7C15u64;

    // ---------------- C1–C6: single-operation semantics ----------------
    let mut b = G1BucketXyzz::identity();
    b.add_mixed_assign(&gen_aff, false);
    g.check("C1 identity+P", same(&b.into_projective(), &gen));

    let p = rand_point(&mut seed);
    let q = rand_point(&mut seed);
    let pa = G1Affine::from(p);
    let qa = G1Affine::from(q);

    let mut b = G1BucketXyzz::from_affine(&pa);
    b.add_mixed_assign(&qa, false);
    g.check("C2 P+Q", same(&b.into_projective(), &(p + q)));

    let mut b = G1BucketXyzz::from_affine(&pa);
    b.add_mixed_assign(&qa, true);
    g.check("C3 P-Q", same(&b.into_projective(), &(p - q)));

    let mut b = G1BucketXyzz::from_affine(&pa);
    b.add_mixed_assign(&pa, false);
    g.check("C4 P+P == double", same(&b.into_projective(), &p.double()));

    let mut b = G1BucketXyzz::from_affine(&pa);
    b.add_mixed_assign(&G1Affine::from(-p), false);
    g.check(
        "C5 P+(-P) == identity",
        same(&b.into_projective(), &G1Projective::identity()),
    );

    let mut b = G1BucketXyzz::identity();
    b.add_mixed_assign(&G1Affine::identity(), false);
    g.check(
        "C6 identity+identity",
        same(&b.into_projective(), &G1Projective::identity()),
    );
    g.check(
        "C6b identity bytes match Jacobian identity",
        G1Affine::from(G1BucketXyzz::identity().into_projective()).to_uncompressed()
            == bytes(&G1Projective::identity()),
    );

    // ---------------- C7: 1024 sequential mixed add/sub ----------------
    let mut acc_j = G1Projective::identity();
    let mut acc_x = G1BucketXyzz::identity();
    let pts: Vec<G1Affine> = (0..1024).map(|_| G1Affine::from(rand_point(&mut seed))).collect();
    for (i, a) in pts.iter().enumerate() {
        if i % 3 == 0 {
            acc_j -= a;
            acc_x.add_mixed_assign(a, true);
        } else {
            acc_j += a;
            acc_x.add_mixed_assign(a, false);
        }
    }
    g.check("C7 1024 mixed add/sub", same(&acc_x.into_projective(), &acc_j));

    // ---------------- C7b: bucket reduction with degenerates ----------------
    let buck_j: Vec<G1Projective> = vec![G1Projective::identity(); 512];
    let buck_x: Vec<G1BucketXyzz> = vec![G1BucketXyzz::identity(); 512];
    let mut bj = buck_j;
    let mut bx = buck_x;
    for i in 0..4096usize {
        let a = pts[i % pts.len()];
        let idx = (i * 37 + 11) % 512;
        bj[idx] += &a;
        bx[idx].add_mixed_assign(&a, false);
    }
    let mut run_j = G1Projective::identity();
    let mut sum_j = G1Projective::identity();
    for e in bj.iter().rev() {
        run_j += e;
        sum_j += &run_j;
    }
    let mut run_x = G1BucketXyzz::identity();
    let mut sum_x = G1BucketXyzz::identity();
    for e in bx.iter().rev() {
        run_x.add_xyzz_assign(e);
        sum_x.add_xyzz_assign(&run_x);
    }
    g.check(
        "C7b bucket reduce (xyzz+xyzz)",
        same(&sum_x.into_projective(), &sum_j),
    );

    let a = rand_point(&mut seed);
    let aa = G1Affine::from(a);
    let mut l = G1BucketXyzz::from_affine(&aa);
    l.add_xyzz_assign(&G1BucketXyzz::from_affine(&aa));
    let d1 = same(&l.into_projective(), &a.double());
    let mut l = G1BucketXyzz::from_affine(&aa);
    l.add_xyzz_assign(&G1BucketXyzz::from_affine(&G1Affine::from(-a)));
    let d2 = same(&l.into_projective(), &G1Projective::identity());
    let mut l = G1BucketXyzz::identity();
    l.add_xyzz_assign(&G1BucketXyzz::from_affine(&aa));
    let d3 = same(&l.into_projective(), &a);
    let mut l = G1BucketXyzz::from_affine(&aa);
    l.add_xyzz_assign(&G1BucketXyzz::identity());
    let d4 = same(&l.into_projective(), &a);
    g.check("C7c xyzz+xyzz degenerates", d1 && d2 && d3 && d4);

    // ---------------- C8: full MSM equivalence at three sizes ----------------
    let worker = Worker::new();
    for &n in &[8usize, 1024, 131_071] {
        let (bases, exps) = fixture(n, seed ^ n as u64);
        let j = msm_jac(&worker, &bases, &exps);
        let x = msm_xyzz(&worker, &bases, &exps);
        g.check(&format!("C8 MSM n={n} bytes equal"), same(&j, &x));
        // 重复调用一次，确认无状态泄漏
        let j2 = msm_jac(&worker, &bases, &exps);
        g.check(&format!("C8 MSM n={n} deterministic"), same(&j, &j2));
    }

    // ---------------- memory ledger ----------------
    let bucket_proj = std::mem::size_of::<G1Projective>();
    let bucket_xyzz = std::mem::size_of::<G1BucketXyzz>();
    let bucket_count = 4096usize;
    println!("\n=== memory ledger ===");
    println!("size_of G1Projective (Jacobian bucket) = {bucket_proj} B");
    println!("size_of G1BucketXyzz  (XYZZ bucket)    = {bucket_xyzz} B");
    println!(
        "bucket array @ {bucket_count} buckets: Jacobian {} B, XYZZ {} B, delta {} B",
        bucket_count * bucket_proj,
        bucket_count * bucket_xyzz,
        bucket_count * bucket_xyzz - bucket_count * bucket_proj
    );
    println!(
        "8 concurrent chunk regions: delta {} B",
        8 * (bucket_count * bucket_xyzz - bucket_count * bucket_proj)
    );

    println!("\n{} PASS, {} FAIL", g.pass, g.fail);
    if g.fail > 0 {
        std::process::exit(1);
    }
}
