//! Phase C MSM kernel benchmark: A/A calibration + blst control.
//!
//! Frozen pre-registration:
//! `experiments/metadata/sapling_msm_kernel_stagec_preregistration_20261023.md`.
//! This binary only applies the frozen design; it defines no gates.
//!
//! Design summary (see the pre-registration for the full text):
//!   * Loads (same deterministic fixture for both implementations):
//!       h_query  G1 n=131,071 dense                (primary)
//!       l_query  G1 n=98,638   Zero/One density 0.777
//!       ab_aux   G1 n=98,638   Zero/One density 0.777
//!       g2_aux   G2 n=98,638   Zero/One density 0.852
//!       ic       G1 n=8        dense
//!   * Arms per process (RAYON_NUM_THREADS selects the condition):
//!       8t process (0x5555): bellman_8t_A, bellman_8t_B, blst_1t
//!       1t process (0x1):    bellman_1t_A, bellman_1t_B, blst_1t
//!     bellman runs the production path (shipped defaults, built-in window rule);
//!     blst runs with the crate's `no-threads` feature (max_count() == 1).
//!   * A/A: the two bellman arms are the same implementation under two labels;
//!     the paired difference estimates measurement-system uncertainty.
//!   * Blocks: 1 warm + 3 measured runs per arm per block; arm order per block is
//!     drawn from a frozen xorshift seed with a prefix-balance rejection rule
//!     (any prefix keeps the two bellman labels within one occurrence).
//!   * Correctness: C1 bellman vs blst (group equality via serialized bytes plus a
//!     round-trip diagnostic), C2 the two bellman arms agree (checksum), C3 the
//!     n=8 load matches naive double-and-add, C4 in-block checksum stability.
//!
//! Deviation record (constraint discovered at implementation time, also to be
//! recorded in the results document): the pre-registration text lists five arms
//! per block including bellman 1t arms inside the 8t process. That is not
//! physically possible: bellman's Worker uses the process-global rayon pool, so a
//! 1-thread bellman arm requires RAYON_NUM_THREADS=1. Each condition therefore
//! measures three arms (its own two bellman labels plus blst_1t). Both A/A pairs
//! and the matched-thread-count P1 comparison (bellman_1t_A vs blst_1t) are
//! preserved exactly as frozen.

use bellman::multicore::Worker;
use bellman::multiexp::{multiexp, Exponent, FullDensity};
use bls12_381::{G1Affine, G1Projective, G2Affine, G2Projective, Scalar};
use blst::p1_affines;
use blst::p2_affines;
use blst::{blst_p1, blst_p1_affine, blst_p2, blst_p2_affine};
use std::fs::OpenOptions;
use std::hint::black_box;
use std::io::Write as _;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;

// ---------------------------------------------------------------------------
// Frozen constants (pre-registration sections 2 and 3).
// ---------------------------------------------------------------------------

const DEFAULT_BLOCKS: usize = 8;
const DEFAULT_RUNS: usize = 3;
const DEFAULT_SEED: u64 = 0x5A17_E5B3_A5E2_D10C;
/// BLS12-381 scalar width in bits.
const NBITS: usize = 255;
/// Recorded Zero/One slot fractions from the 2026-10-18 profile census
/// (sapling_default_time_profile_20261018.md section 2).
const G1_AUX_ZERO_ONE: f64 = 0.777;
const G2_AUX_ZERO_ONE: f64 = 0.852;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Curve {
    G1,
    G2,
}

impl Curve {
    fn label(self) -> &'static str {
        match self {
            Curve::G1 => "G1",
            Curve::G2 => "G2",
        }
    }
}

struct LoadSpec {
    name: &'static str,
    curve: Curve,
    n: usize,
    /// None = dense random scalars; Some(f) = fraction of slots replaced by 0/1.
    zero_one_fraction: Option<f64>,
}

fn load_specs() -> Vec<LoadSpec> {
    vec![
        LoadSpec { name: "h_query", curve: Curve::G1, n: 131_071, zero_one_fraction: None },
        LoadSpec { name: "l_query", curve: Curve::G1, n: 98_638, zero_one_fraction: Some(G1_AUX_ZERO_ONE) },
        LoadSpec { name: "ab_aux", curve: Curve::G1, n: 98_638, zero_one_fraction: Some(G1_AUX_ZERO_ONE) },
        LoadSpec { name: "g2_aux", curve: Curve::G2, n: 98_638, zero_one_fraction: Some(G2_AUX_ZERO_ONE) },
        LoadSpec { name: "ic", curve: Curve::G1, n: 8, zero_one_fraction: None },
    ]
}

// ---------------------------------------------------------------------------
// Small helpers.
// ---------------------------------------------------------------------------

fn env_usize(name: &str, fallback: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|raw| raw.trim().parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(fallback)
}

fn env_u64(name: &str, fallback: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|raw| raw.trim().parse::<u64>().ok())
        .unwrap_or(fallback)
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

fn fnv1a(bytes: &[u8]) -> u64 {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash
}

/// Cheap cache-realistic base vector: consecutive multiples of the generator.
/// The fill loop reads the affine vector sequentially either way, so point
/// *values* do not affect the cost conclusion (same policy as msm_window_bench).
fn build_g1_bases(n: usize) -> Vec<G1Affine> {
    let step = G1Affine::generator();
    let mut acc = G1Projective::identity();
    let mut bases = Vec::with_capacity(n);
    for _ in 0..n {
        acc += &step;
        bases.push(G1Affine::from(acc));
    }
    bases
}

fn build_g2_bases(n: usize) -> Vec<G2Affine> {
    let step = G2Affine::generator();
    let mut acc = G2Projective::identity();
    let mut bases = Vec::with_capacity(n);
    for _ in 0..n {
        acc += &step;
        bases.push(G2Affine::from(acc));
    }
    bases
}

/// Deterministic scalars; for sparse loads a frozen fraction of slots is
/// replaced by zero/one in the recorded proportion.
fn build_scalars(n: usize, zero_one: Option<f64>, seed: u64) -> Vec<Scalar> {
    let mut state = seed;
    let mut scalars: Vec<Scalar> = (0..n).map(|_| random_scalar(&mut state)).collect();
    if let Some(fraction) = zero_one {
        let mut slot_state = seed ^ 0xA5A5_5A5A_0F0F_F0F0;
        for slot in scalars.iter_mut() {
            let draw = (next_u64(&mut slot_state) >> 11) as f64 / (1u64 << 53) as f64;
            if draw < fraction {
                // Half zero, half one, deterministically.
                *slot = if next_u64(&mut slot_state) & 1 == 0 {
                    Scalar::zero()
                } else {
                    Scalar::one()
                };
            }
        }
    }
    scalars
}

// ---------------------------------------------------------------------------
// Fixtures: one per load, feeding both implementations from the same input.
// ---------------------------------------------------------------------------

struct G1Fixture {
    bases: Arc<Vec<G1Affine>>,
    exponents: Arc<Vec<Exponent<Scalar>>>,
    blst_affines: p1_affines,
    scalar_bytes: Vec<u8>,
}

struct G2Fixture {
    bases: Arc<Vec<G2Affine>>,
    exponents: Arc<Vec<Exponent<Scalar>>>,
    blst_affines: p2_affines,
    scalar_bytes: Vec<u8>,
}

struct FixtureTimings {
    bases_ms: f64,
    bellman_exponents_ms: f64,
    blst_convert_ms: f64,
}

fn build_g1_fixture(spec: &LoadSpec, seed: u64) -> (G1Fixture, FixtureTimings) {
    let start = Instant::now();
    let bases_vec = build_g1_bases(spec.n);
    let bases_ms = start.elapsed().as_secs_f64() * 1000.0;
    let bases = Arc::new(bases_vec);

    let scalars = build_scalars(spec.n, spec.zero_one_fraction, seed);

    let start = Instant::now();
    let exponents: Arc<Vec<Exponent<Scalar>>> = Arc::new(scalars.iter().map(Exponent::from).collect());
    let bellman_exponents_ms = start.elapsed().as_secs_f64() * 1000.0;

    let start = Instant::now();
    let mut blst_points: Vec<blst_p1> = Vec::with_capacity(spec.n);
    let mut scalar_bytes: Vec<u8> = Vec::with_capacity(spec.n * 32);
    for (base, scalar) in bases.iter().zip(scalars.iter()) {
        let mut affine = blst_p1_affine::default();
        let bytes = base.to_uncompressed();
        let err = unsafe { blst::blst_p1_deserialize(&mut affine, bytes.as_ptr()) };
        assert_eq!(err, blst::BLST_ERROR::BLST_SUCCESS, "blst_p1_deserialize failed");
        let mut point = blst_p1::default();
        unsafe { blst::blst_p1_from_affine(&mut point, &affine) };
        blst_points.push(point);
        scalar_bytes.extend_from_slice(&scalar.to_bytes());
    }
    let blst_affines = p1_affines::from(&blst_points);
    let blst_convert_ms = start.elapsed().as_secs_f64() * 1000.0;

    (
        G1Fixture { bases, exponents, blst_affines, scalar_bytes },
        FixtureTimings { bases_ms, bellman_exponents_ms, blst_convert_ms },
    )
}

fn build_g2_fixture(spec: &LoadSpec, seed: u64) -> (G2Fixture, FixtureTimings) {
    let start = Instant::now();
    let bases_vec = build_g2_bases(spec.n);
    let bases_ms = start.elapsed().as_secs_f64() * 1000.0;
    let bases = Arc::new(bases_vec);

    let scalars = build_scalars(spec.n, spec.zero_one_fraction, seed);

    let start = Instant::now();
    let exponents: Arc<Vec<Exponent<Scalar>>> = Arc::new(scalars.iter().map(Exponent::from).collect());
    let bellman_exponents_ms = start.elapsed().as_secs_f64() * 1000.0;

    let start = Instant::now();
    let mut blst_points: Vec<blst_p2> = Vec::with_capacity(spec.n);
    let mut scalar_bytes: Vec<u8> = Vec::with_capacity(spec.n * 32);
    for (base, scalar) in bases.iter().zip(scalars.iter()) {
        let mut affine = blst_p2_affine::default();
        let bytes = base.to_uncompressed();
        let err = unsafe { blst::blst_p2_deserialize(&mut affine, bytes.as_ptr()) };
        assert_eq!(err, blst::BLST_ERROR::BLST_SUCCESS, "blst_p2_deserialize failed");
        let mut point = blst_p2::default();
        unsafe { blst::blst_p2_from_affine(&mut point, &affine) };
        blst_points.push(point);
        scalar_bytes.extend_from_slice(&scalar.to_bytes());
    }
    let blst_affines = p2_affines::from(&blst_points);
    let blst_convert_ms = start.elapsed().as_secs_f64() * 1000.0;

    (
        G2Fixture { bases, exponents, blst_affines, scalar_bytes },
        FixtureTimings { bases_ms, bellman_exponents_ms, blst_convert_ms },
    )
}

// ---------------------------------------------------------------------------
// MSM runners. The elapsed time is measured by the caller around these calls.
// ---------------------------------------------------------------------------

fn run_bellman_g1(
    worker: &Worker,
    fixture: &G1Fixture,
) -> G1Projective {
    multiexp(
        worker,
        (Arc::clone(&fixture.bases), 0),
        FullDensity,
        Arc::clone(&fixture.exponents),
    )
    .wait()
    .expect("multiexp failed")
}

fn run_blst_g1(fixture: &G1Fixture) -> blst_p1 {
    fixture.blst_affines.mult(&fixture.scalar_bytes, NBITS)
}

fn run_bellman_g2(
    worker: &Worker,
    fixture: &G2Fixture,
) -> G2Projective {
    multiexp(
        worker,
        (Arc::clone(&fixture.bases), 0),
        FullDensity,
        Arc::clone(&fixture.exponents),
    )
    .wait()
    .expect("multiexp failed")
}

fn run_blst_g2(fixture: &G2Fixture) -> blst_p2 {
    fixture.blst_affines.mult(&fixture.scalar_bytes, NBITS)
}

// ---------------------------------------------------------------------------
// Checksums (group-equality evidence, identical layout for both sides).
// ---------------------------------------------------------------------------

fn g1_checksum(point: &G1Projective) -> u64 {
    fnv1a(&G1Affine::from(*point).to_uncompressed())
}

fn blst_p1_checksum(point: &blst_p1) -> u64 {
    let mut affine = blst_p1_affine::default();
    unsafe { blst::blst_p1_to_affine(&mut affine, point) };
    let mut bytes = [0u8; 96];
    unsafe { blst::blst_p1_affine_serialize(bytes.as_mut_ptr(), &affine) };
    fnv1a(&bytes)
}

fn g2_checksum(point: &G2Projective) -> u64 {
    fnv1a(&G2Affine::from(*point).to_uncompressed())
}

fn blst_p2_checksum(point: &blst_p2) -> u64 {
    let mut affine = blst_p2_affine::default();
    unsafe { blst::blst_p2_to_affine(&mut affine, point) };
    let mut bytes = [0u8; 192];
    unsafe { blst::blst_p2_affine_serialize(bytes.as_mut_ptr(), &affine) };
    fnv1a(&bytes)
}

/// blst serialized bytes, for the byte-equality and round-trip diagnostics.
fn blst_p1_bytes(point: &blst_p1) -> [u8; 96] {
    let mut affine = blst_p1_affine::default();
    unsafe { blst::blst_p1_to_affine(&mut affine, point) };
    let mut bytes = [0u8; 96];
    unsafe { blst::blst_p1_affine_serialize(bytes.as_mut_ptr(), &affine) };
    bytes
}

fn blst_p2_bytes(point: &blst_p2) -> [u8; 192] {
    let mut affine = blst_p2_affine::default();
    unsafe { blst::blst_p2_to_affine(&mut affine, point) };
    let mut bytes = [0u8; 192];
    unsafe { blst::blst_p2_affine_serialize(bytes.as_mut_ptr(), &affine) };
    bytes
}

// ---------------------------------------------------------------------------
// Frozen ABBA-balanced arm order (pre-registration section 3.3).
// ---------------------------------------------------------------------------

/// Draw a permutation of `arms` from the frozen xorshift seed for `block`,
/// rejecting draws that break prefix balance between the two bellman labels
/// (`bellman_*_A` and `bellman_*_B`). Balance is a strict pre-registered
/// constraint; the random draw only rotates which balanced order appears.
fn arm_order(block: usize, arms: &[&'static str], seed: u64) -> Vec<&'static str> {
    let bellman_a = arms.iter().position(|a| a.ends_with("_A")).expect("arm _A");
    let bellman_b = arms.iter().position(|a| a.ends_with("_B")).expect("arm _B");
    let mut state = seed ^ (block as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    loop {
        let mut seq = arms.to_vec();
        for i in (1..seq.len()).rev() {
            let j = (next_u64(&mut state) as usize) % (i + 1);
            seq.swap(i, j);
        }
        let (mut count_a, mut count_b) = (0usize, 0usize);
        let balanced = seq.iter().all(|arm| {
            if *arm == arms[bellman_a] {
                count_a += 1;
            } else if *arm == arms[bellman_b] {
                count_b += 1;
            }
            count_a.abs_diff(count_b) <= 1
        });
        if balanced {
            return seq;
        }
    }
}

// ---------------------------------------------------------------------------
// Raw CSV recorder (append-only).
// ---------------------------------------------------------------------------

struct Recorder {
    path: PathBuf,
}

impl Recorder {
    fn open(path: PathBuf) -> Self {
        if !path.exists() {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).expect("create raw dir");
            }
            let mut handle = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&path)
                .expect("create raw csv");
            writeln!(handle, "load,curve,n,arm,block,run,phase,elapsed_ms,checksum")
                .expect("write csv header");
        }
        Self { path }
    }

    fn row(&self, load: &str, curve: Curve, n: usize, arm: &str, block: usize, run: usize, phase: &str, elapsed_ms: f64, checksum: u64) {
        let mut handle = OpenOptions::new()
            .append(true)
            .open(&self.path)
            .expect("append raw csv");
        writeln!(
            handle,
            "{load},{curve},{n},{arm},{block},{run},{phase},{elapsed_ms:.6},{checksum:016x}",
            curve = curve.label(),
            elapsed_ms = elapsed_ms,
            checksum = checksum,
        )
        .expect("write csv row");
    }
}

struct CorrectnessRecorder {
    path: PathBuf,
}

impl CorrectnessRecorder {
    fn open(path: PathBuf) -> Self {
        if !path.exists() {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).expect("create raw dir");
            }
            let mut handle = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&path)
                .expect("create correctness csv");
            writeln!(handle, "load,curve,n,check,ok").expect("write csv header");
        }
        Self { path }
    }

    fn check(&self, load: &str, curve: Curve, n: usize, name: &str, ok: bool) {
        let mut handle = OpenOptions::new()
            .append(true)
            .open(&self.path)
            .expect("append correctness csv");
        writeln!(
            handle,
            "{load},{curve},{n},{name},{}",
            if ok { 1 } else { 0 },
            curve = curve.label(),
        )
        .expect("write csv row");
        println!(
            "correctness load={load} curve={curve} n={n} check={name} ok={}",
            if ok { 1 } else { 0 },
            curve = curve.label(),
        );
    }
}

// ---------------------------------------------------------------------------
// Main.
// ---------------------------------------------------------------------------

fn main() {
    let blocks = env_usize("MSM_KB_BLOCKS", DEFAULT_BLOCKS);
    let runs = env_usize("MSM_KB_RUNS", DEFAULT_RUNS);
    let seed = env_u64("MSM_KB_SEED", DEFAULT_SEED);
    let csv_path = std::env::var("MSM_KB_CSV").ok().map(PathBuf::from);
    let rayon_threads = std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".to_string());
    let single_thread = rayon_threads.trim() == "1";

    // Arm set: the condition (process) decides which bellman labels exist.
    let arms: Vec<&'static str> = if single_thread {
        vec!["bellman_1t_A", "bellman_1t_B", "blst_1t"]
    } else {
        vec!["bellman_8t_A", "bellman_8t_B", "blst_1t"]
    };

    println!(
        "bench=msm_kernel_bench rayon_threads={rayon_threads} blocks={blocks} runs={runs} seed=0x{seed:016x} arms={arms:?}"
    );
    if csv_path.is_none() {
        println!("MSM_KB_CSV not set: running without raw CSV output (diagnostic mode)");
    }

    let recorder = csv_path.as_ref().map(|path| Recorder::open(path.clone()));
    let correctness_path = csv_path.as_ref().map(|path| {
        let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("msm_kernel_bench");
        let stem = stem.strip_suffix("_8t").or_else(|| stem.strip_suffix("_1t")).unwrap_or(stem);
        path.with_file_name(format!("{stem}_correctness.csv"))
    });
    let correctness = correctness_path
        .as_ref()
        .map(|path| CorrectnessRecorder::open(path.clone()));

    let worker = Worker::new();
    let mut all_correctness_ok = true;

    for spec in load_specs() {
        let load = spec.name;
        let curve = spec.curve;
        let n = spec.n;
        let fixture_seed = seed ^ 0x5151_9E37_79B9_7F4A;

        // --- Fixture (timed outside the MSM region) ------------------------
        match curve {
            Curve::G1 => {
                let (fixture, timings) = build_g1_fixture(&spec, fixture_seed);
                println!(
                    "fixture load={load} curve=G1 n={n} bases_ms={:.3} bellman_exponents_ms={:.3} blst_convert_ms={:.3} bases_bytes={} exponent_bytes={} blst_scratch_bytes={}",
                    timings.bases_ms,
                    timings.bellman_exponents_ms,
                    timings.blst_convert_ms,
                    n * std::mem::size_of::<G1Affine>(),
                    n * std::mem::size_of::<Exponent<Scalar>>(),
                    unsafe { blst::blst_p1s_mult_pippenger_scratch_sizeof(n) },
                );

                // --- Correctness gates ------------------------------------
                let bellman_value = run_bellman_g1(&worker, &fixture);
                let blst_value = run_blst_g1(&fixture);
                let blst_bytes = blst_p1_bytes(&blst_value);
                let bytes_equal = G1Affine::from(bellman_value).to_uncompressed() == blst_bytes;
                let roundtrip = G1Affine::from_uncompressed(&blst_bytes)
                    .map(|point| G1Projective::from(point) == bellman_value)
                    .is_some()
                    .unwrap_u8()
                    == 1;
                all_correctness_ok &= bytes_equal && roundtrip;
                if let Some(rec) = &correctness {
                    rec.check(load, curve, n, "bellman_vs_blst_bytes", bytes_equal);
                    rec.check(load, curve, n, "bellman_vs_blst_roundtrip", roundtrip);
                }

                if n == 8 {
                    // C3: naive double-and-add over the same deterministic scalars.
                    let scalars = build_scalars(n, spec.zero_one_fraction, fixture_seed);
                    let mut naive = G1Projective::identity();
                    for (base, scalar) in fixture.bases.iter().zip(scalars.iter()) {
                        naive += &(G1Projective::from(*base) * scalar);
                    }
                    let ok = naive == bellman_value;
                    all_correctness_ok &= ok;
                    if let Some(rec) = &correctness {
                        rec.check(load, curve, n, "naive_n8", ok);
                    }
                }

                run_load_g1(&spec, &fixture, &worker, &arms, blocks, runs, seed, &recorder, &correctness, &mut all_correctness_ok);
            }
            Curve::G2 => {
                let (fixture, timings) = build_g2_fixture(&spec, fixture_seed);
                println!(
                    "fixture load={load} curve=G2 n={n} bases_ms={:.3} bellman_exponents_ms={:.3} blst_convert_ms={:.3} bases_bytes={} exponent_bytes={} blst_scratch_bytes={}",
                    timings.bases_ms,
                    timings.bellman_exponents_ms,
                    timings.blst_convert_ms,
                    n * std::mem::size_of::<G2Affine>(),
                    n * std::mem::size_of::<Exponent<Scalar>>(),
                    unsafe { blst::blst_p2s_mult_pippenger_scratch_sizeof(n) },
                );

                let bellman_value = run_bellman_g2(&worker, &fixture);
                let blst_value = run_blst_g2(&fixture);
                let blst_bytes = blst_p2_bytes(&blst_value);
                let bytes_equal = G2Affine::from(bellman_value).to_uncompressed() == blst_bytes;
                let roundtrip = G2Affine::from_uncompressed(&blst_bytes)
                    .map(|point| G2Projective::from(point) == bellman_value)
                    .is_some()
                    .unwrap_u8()
                    == 1;
                all_correctness_ok &= bytes_equal && roundtrip;
                if let Some(rec) = &correctness {
                    rec.check(load, curve, n, "bellman_vs_blst_bytes", bytes_equal);
                    rec.check(load, curve, n, "bellman_vs_blst_roundtrip", roundtrip);
                }

                run_load_g2(&spec, &fixture, &worker, &arms, blocks, runs, seed, &recorder, &correctness, &mut all_correctness_ok);
            }
        }
    }

    println!(
        "correctness_summary ok={}",
        if all_correctness_ok { 1 } else { 0 }
    );
    if !all_correctness_ok {
        eprintln!("CORRECTNESS FAILURE: see rows above; the round is invalid by the frozen rules.");
        std::process::exit(2);
    }
    println!("MSM_KERNEL_BENCH=DONE");
}

fn run_load_g1(
    spec: &LoadSpec,
    fixture: &G1Fixture,
    worker: &Worker,
    arms: &[&'static str],
    blocks: usize,
    runs: usize,
    seed: u64,
    recorder: &Option<Recorder>,
    correctness: &Option<CorrectnessRecorder>,
    all_ok: &mut bool,
) {
    let (load, curve, n) = (spec.name, spec.curve, spec.n);
    let mut arm_checksums: std::collections::HashMap<&str, Vec<u64>> = std::collections::HashMap::new();

    for block in 0..blocks {
        for arm in arm_order(block, arms, seed) {
            // Warm-up run (recorded but not measured).
            let warm = match arm {
                "blst_1t" => blst_p1_checksum(&run_blst_g1(fixture)),
                _ => g1_checksum(&run_bellman_g1(worker, fixture)),
            };
            if let Some(rec) = recorder {
                rec.row(load, curve, n, arm, block, 0, "warm", 0.0, warm);
            }
            arm_checksums.entry(arm).or_default().push(warm);

            for run in 1..=runs {
                let start = Instant::now();
                let checksum = match arm {
                    "blst_1t" => blst_p1_checksum(&run_blst_g1(fixture)),
                    _ => g1_checksum(&run_bellman_g1(worker, fixture)),
                };
                let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
                black_box(checksum);
                if let Some(rec) = recorder {
                    rec.row(load, curve, n, arm, block, run, "measured", elapsed_ms, checksum);
                }
                arm_checksums.entry(arm).or_default().push(checksum);
            }
        }
    }

    // C4: in-block checksum stability per arm.
    for (arm, checksums) in &arm_checksums {
        let stable = checksums.windows(2).all(|pair| pair[0] == pair[1]);
        *all_ok &= stable;
        if let Some(rec) = correctness {
            rec.check(load, curve, n, "checksum_stable", stable);
        }
        if !stable {
            println!("correctness load={load} arm={arm} check=checksum_stable ok=0");
        }
    }
}

fn run_load_g2(
    spec: &LoadSpec,
    fixture: &G2Fixture,
    worker: &Worker,
    arms: &[&'static str],
    blocks: usize,
    runs: usize,
    seed: u64,
    recorder: &Option<Recorder>,
    correctness: &Option<CorrectnessRecorder>,
    all_ok: &mut bool,
) {
    let (load, curve, n) = (spec.name, spec.curve, spec.n);
    let mut arm_checksums: std::collections::HashMap<&str, Vec<u64>> = std::collections::HashMap::new();

    for block in 0..blocks {
        for arm in arm_order(block, arms, seed) {
            let warm = match arm {
                "blst_1t" => blst_p2_checksum(&run_blst_g2(fixture)),
                _ => g2_checksum(&run_bellman_g2(worker, fixture)),
            };
            if let Some(rec) = recorder {
                rec.row(load, curve, n, arm, block, 0, "warm", 0.0, warm);
            }
            arm_checksums.entry(arm).or_default().push(warm);

            for run in 1..=runs {
                let start = Instant::now();
                let checksum = match arm {
                    "blst_1t" => blst_p2_checksum(&run_blst_g2(fixture)),
                    _ => g2_checksum(&run_bellman_g2(worker, fixture)),
                };
                let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
                black_box(checksum);
                if let Some(rec) = recorder {
                    rec.row(load, curve, n, arm, block, run, "measured", elapsed_ms, checksum);
                }
                arm_checksums.entry(arm).or_default().push(checksum);
            }
        }
    }

    for (arm, checksums) in &arm_checksums {
        let stable = checksums.windows(2).all(|pair| pair[0] == pair[1]);
        *all_ok &= stable;
        if let Some(rec) = correctness {
            rec.check(load, curve, n, "checksum_stable", stable);
        }
        if !stable {
            println!("correctness load={load} arm={arm} check=checksum_stable ok=0");
        }
    }
}
