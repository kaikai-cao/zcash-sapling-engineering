//! Phase D: XYZZ bucket coordinates vs the shipped Jacobian path, paired A/B.
//!
//! Pre-registration: `experiments/metadata/sapling_msm_phase_d_xyzz_preregistration_20261102.md`.
//! This binary only applies the frozen design; it defines no gates.
//!
//! Arms (single-thread process, `RAYON_NUM_THREADS=1`):
//!   jac_A, jac_B : the shipped `multiexp` path under two labels (A/A calibration)
//!   xyzz         : `multiexp_g1_xyzz` (XYZZ buckets, XYZZ reduction)
//!
//! Primary load: `h_query` G1, n = 131,071, dense scalars from the same
//! deterministic xorshift rule the Phase C bench uses. The window width is
//! **not** overridden: both arms take the shipped window rule for this n.
//!
//! Correctness: all three arms must serialise to the same 96-byte
//! uncompressed point, otherwise the block is void.

use bellman::multicore::Worker;
use bellman::multiexp::xyzz_g1::{multiexp_g1_xyzz, xyzz_enabled};
use bellman::multiexp::{multiexp, Exponent, FullDensity};
use bls12_381::{G1Affine, G1Projective, Scalar};
use std::fs::OpenOptions;
use std::hint::black_box;
use std::io::Write as _;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;

const N: usize = 131_071;
const DEFAULT_BLOCKS: usize = 8;
const DEFAULT_RUNS: usize = 3;
const DEFAULT_SEED: u64 = 0x5A17_E5B3_A5E2_D10C;

fn env_usize(name: &str, fallback: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(fallback)
}

fn env_u64(name: &str, fallback: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
        .unwrap_or(fallback)
}

fn next_u64(state: &mut u64) -> u64 {
    let mut x = *state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *state = x;
    x.wrapping_mul(0x2545_F491_4F6C_DD1D)
}

fn build_bases(n: usize) -> Vec<G1Affine> {
    let step = G1Affine::generator();
    let mut acc = G1Projective::identity();
    let mut out = Vec::with_capacity(n);
    for _ in 0..n {
        acc += &step;
        out.push(G1Affine::from(acc));
    }
    out
}

fn build_scalars(n: usize, seed: u64) -> Vec<Scalar> {
    let mut state = seed;
    (0..n)
        .map(|_| {
            let mut bytes = [0u8; 64];
            for chunk in bytes.chunks_mut(8) {
                chunk.copy_from_slice(&next_u64(&mut state).to_le_bytes());
            }
            Scalar::from_bytes_wide(&bytes)
        })
        .collect()
}

fn run_jacobian(
    worker: &Worker,
    bases: &Arc<Vec<G1Affine>>,
    exps: &Arc<Vec<Exponent<Scalar>>>,
) -> G1Projective {
    multiexp(
        worker,
        (Arc::clone(bases), 0),
        FullDensity,
        Arc::clone(exps),
    )
    .wait()
    .expect("multiexp failed")
}

fn run_xyzz(
    worker: &Worker,
    bases: &Arc<Vec<G1Affine>>,
    exps: &Arc<Vec<Exponent<Scalar>>>,
) -> G1Projective {
    multiexp_g1_xyzz(worker, Arc::clone(bases), Arc::clone(exps))
        .wait()
        .expect("multiexp_g1_xyzz failed")
}

fn median(values: &mut [f64]) -> f64 {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap());
    values[values.len() / 2]
}

fn main() {
    let blocks = env_usize("XYZZ_AB_BLOCKS", DEFAULT_BLOCKS);
    let runs = env_usize("XYZZ_AB_RUNS", DEFAULT_RUNS);
    let seed = env_u64("XYZZ_AB_SEED", DEFAULT_SEED);
    let csv_path = std::env::var("XYZZ_AB_CSV").ok().map(PathBuf::from);
    let rayon_threads = std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".into());

    let arms = ["jac_A", "jac_B", "xyzz"];
    println!(
        "bench=msm_xyzz_ab n={N} blocks={blocks} runs={runs} seed=0x{seed:016x} rayon_threads={rayon_threads} xyzz_switch={}",
        xyzz_enabled() as u8
    );
    println!(
        "note: the SAPLING_MSM_XYZZ env switch only gates the Groth16 call site; this bench calls both arms directly"
    );

    let bases = Arc::new(build_bases(N));
    let scalars = build_scalars(N, seed ^ 0x5151_9E37_79B9_7F4A);
    let exps: Arc<Vec<Exponent<Scalar>>> = Arc::new(scalars.iter().map(Exponent::from).collect());

    let worker = Worker::new();

    // Correctness gate: all three arms must agree byte-for-byte.
    let jac0 = run_jacobian(&worker, &bases, &exps);
    let xyzz0 = run_xyzz(&worker, &bases, &exps);
    let jac_bytes = G1Affine::from(jac0).to_uncompressed();
    let xyzz_bytes = G1Affine::from(xyzz0).to_uncompressed();
    let agree = jac_bytes == xyzz_bytes;
    println!("correctness h_query jac_vs_xyzz_bytes={}", agree as u8);
    let jac0_again = run_jacobian(&worker, &bases, &exps);
    let aa_agree = G1Affine::from(jac0_again).to_uncompressed() == jac_bytes;
    println!("correctness h_query jac_A_vs_B_bytes={}", aa_agree as u8);
    if !agree || !aa_agree {
        eprintln!("CORRECTNESS FAILURE: aborting before timing");
        std::process::exit(2);
    }

    let mut csv = csv_path.map(|p| {
        let mut f = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&p)
            .unwrap_or_else(|e| panic!("open {}: {e}", p.display()));
        if f.metadata().map(|m| m.len() == 0).unwrap_or(true) {
            writeln!(
                f,
                "block,order_pos,arm,run,ms,build,sha_switch,rayon_threads"
            )
            .ok();
        }
        f
    });

    let mut block_order_seed = seed ^ 0x9E37_79B9_7F4A_7C15;
    let mut per_arm: Vec<Vec<f64>> = vec![Vec::new(); arms.len()];
    let mut block_medians: Vec<[f64; 3]> = Vec::new();

    for block in 0..blocks {
        // Frozen permutation per block: Fisher-Yates driven by the block seed.
        let mut order: Vec<usize> = (0..arms.len()).collect();
        for i in (1..order.len()).rev() {
            let j = (next_u64(&mut block_order_seed) % (i as u64 + 1)) as usize;
            order.swap(i, j);
        }

        // One warm-up per arm, then `runs` measured iterations.
        for &a in order.iter() {
            match arms[a] {
                "jac_A" | "jac_B" => {
                    black_box(run_jacobian(&worker, &bases, &exps));
                }
                _ => {
                    black_box(run_xyzz(&worker, &bases, &exps));
                }
            }
        }

        let mut this_block = [0f64; 3];
        for &a in order.iter() {
            let mut times = Vec::with_capacity(runs);
            for r in 0..runs {
                let start = Instant::now();
                let value = match arms[a] {
                    "jac_A" | "jac_B" => run_jacobian(&worker, &bases, &exps),
                    _ => run_xyzz(&worker, &bases, &exps),
                };
                let ms = start.elapsed().as_secs_f64() * 1000.0;
                black_box(value);
                times.push(ms);
                if let Some(f) = csv.as_mut() {
                    writeln!(
                        f,
                        "{},{},{},{},{:.6},phase-d,{:.1},{:.1}",
                        block,
                        order.iter().position(|x| *x == a).unwrap(),
                        arms[a],
                        r,
                        ms,
                        env_usize("XYZZ_AB_BUILD", 0) as f64,
                        rayon_threads.parse::<f64>().unwrap_or(0.0)
                    )
                    .ok();
                }
            }
            let m = median(&mut times);
            this_block[a] = m;
            per_arm[a].push(m);
            println!("block={block} arm={} median_ms={m:.3}", arms[a]);
        }
        block_medians.push(this_block);
        if let Some(f) = csv.as_mut() {
            f.flush().ok();
        }
    }

    let jac_all = median(&mut per_arm[0].clone());
    let xyzz_all = median(&mut per_arm[2].clone());
    let aa = median(&mut per_arm[1].clone());
    println!("\n=== summary (per-block medians, {blocks} blocks) ===");
    println!("jac_A  median_ms = {jac_all:.3}");
    println!(
        "jac_B  median_ms = {aa:.3}   (A/A drift vs jac_A: {:+.3}%)",
        (aa - jac_all) / jac_all * 100.0
    );
    println!("xyzz   median_ms = {xyzz_all:.3}");
    println!("S_MSM = jac / xyzz = {:.4}x", jac_all / xyzz_all);

    // Paired per-block ratios: distribution, not just the ratio of medians.
    let mut ratios: Vec<f64> = block_medians.iter().map(|b| b[0] / b[2]).collect();
    let mut sorted = ratios.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    println!(
        "per-block ratio min={:.4} p25={:.4} median={:.4} p75={:.4} max={:.4}",
        sorted[0],
        sorted[sorted.len() / 4],
        median(&mut ratios),
        sorted[sorted.len() * 3 / 4],
        sorted[sorted.len() - 1]
    );
}
