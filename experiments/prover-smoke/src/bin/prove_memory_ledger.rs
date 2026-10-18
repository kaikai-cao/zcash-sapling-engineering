//! Prove-phase memory ledger for the Sapling Spend circuit.
//!
//! This diagnostic binary installs a tracking `#[global_allocator]` that feeds
//! `bellman::mem_probe` with live/peak byte counters. It then reports:
//!
//!   * the peak allocation growth while reading + validating the parameter file;
//!   * the retained live bytes after parameter load and input preparation;
//!   * per-proof peak allocation growth during `create_proof` (the real
//!     prove-phase working set, excluding nothing);
//!   * the retained (leaked-into-prove) bytes at the end of each proof.
//!
//! Run it with `SAPLING_PROFILE=1` so the MSM path also emits
//! `BELLMAN_MSM_MEM_PROBE` lines (per-call exponent-preparation and
//! bucket-array allocation deltas) on stderr.
//!
//! The numbers are process-observed allocation deltas from this specific run.
//! They are not a universal memory bound.

use bellman::mem_probe;
use group::ff::Field;
use rand::{rngs::StdRng, RngExt, SeedableRng};
use sapling_crypto::{
    circuit::SpendParameters,
    keys::ExpandedSpendingKey,
    prover::SpendProver,
    value::{NoteValue, ValueCommitTrapdoor, ValueCommitment},
    Diversifier, MerklePath, Node, Note, Rseed, SaplingVerificationContext,
};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    error::Error,
    fs::{create_dir_all, File, OpenOptions},
    io::Write,
    path::PathBuf,
    time::{Instant, SystemTime, UNIX_EPOCH},
};

struct TrackingAllocator;

#[global_allocator]
static GLOBAL_ALLOCATOR: TrackingAllocator = TrackingAllocator;

unsafe impl GlobalAlloc for TrackingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = System.alloc(layout);
        if !ptr.is_null() {
            mem_probe::on_alloc(layout.size());
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = System.alloc_zeroed(layout);
        if !ptr.is_null() {
            mem_probe::on_alloc(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        mem_probe::on_dealloc(layout.size());
        System.dealloc(ptr, layout);
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        let new_ptr = System.realloc(ptr, layout, new_size);
        if !new_ptr.is_null() {
            if new_size >= layout.size() {
                mem_probe::on_alloc(new_size - layout.size());
            } else {
                mem_probe::on_dealloc(layout.size() - new_size);
            }
        }
        new_ptr
    }
}

const TREE_DEPTH: usize = 32;
const REPEATS: usize = 5;

fn resolve_spend_params_path() -> PathBuf {
    if let Ok(path) = std::env::var("SAPLING_SPEND_PARAMS") {
        let path = path.trim();
        if !path.is_empty() {
            return PathBuf::from(path);
        }
    }

    if let Ok(directory) = std::env::var("ZCASH_PARAMS_DIR") {
        let directory = directory.trim();
        if !directory.is_empty() {
            return PathBuf::from(directory).join("sapling-spend.params");
        }
    }

    PathBuf::from(r"D:\Research\zcash-params\sapling-spend.params")
}

fn delta(peak_or_live: usize, baseline: usize) -> usize {
    peak_or_live.saturating_sub(baseline)
}

fn main() -> Result<(), Box<dyn Error>> {
    // Enable tracking before any large allocation so deltas are accurate.
    mem_probe::enable();

    let mut rng = StdRng::from_seed([7u8; 32]);

    let params_path = resolve_spend_params_path();
    let rayon_threads =
        std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".to_string());
    let build_profile = if cfg!(debug_assertions) {
        "debug"
    } else {
        "release"
    };

    println!("circuit=Spend");
    println!("params_path={}", params_path.display());
    println!("rayon_threads={rayon_threads}");
    println!("build_profile={build_profile}");

    // ----- Phase 1: read + validate parameter file -----
    let baseline_before_load = mem_probe::live();
    mem_probe::reset_peak();

    let load_start = Instant::now();
    let params = SpendParameters::read(
        File::open(&params_path).unwrap_or_else(|error| {
            panic!("无法打开 Spend 参数文件 {}: {error}", params_path.display())
        }),
        true,
    )
    .expect("无法读取或验证 Spend 参数文件");
    let load_ms = load_start.elapsed().as_secs_f64() * 1000.0;

    let load_peak = mem_probe::peak();
    let live_after_load = mem_probe::live();
    let load_peak_delta = delta(load_peak, baseline_before_load);
    let live_after_load_delta = delta(live_after_load, baseline_before_load);

    println!("params_read_validate_ms={load_ms:.3}");
    println!("live_baseline_bytes={baseline_before_load}");
    println!("load_peak_delta_bytes={load_peak_delta}");
    println!("live_after_load_delta_bytes={live_after_load_delta}");

    // ----- Phase 2: prepare verifying key (one-off) -----
    let before_vk = mem_probe::live();
    mem_probe::reset_peak();
    let vk_start = Instant::now();
    let prepared_vk = params.prepared_verifying_key();
    let prepare_vk_ms = vk_start.elapsed().as_secs_f64() * 1000.0;
    let prepare_vk_peak_delta = delta(mem_probe::peak(), before_vk);
    println!("prepare_vk_ms={prepare_vk_ms:.3}");
    println!("prepare_vk_peak_delta_bytes={prepare_vk_peak_delta}");

    // ----- Phase 3: build a valid witness / Merkle path (outside prove timing) -----
    let expsk = loop {
        let sk: [u8; 32] = rng.random();
        if let Some(key) = ExpandedSpendingKey::from_spending_key(&sk) {
            break key;
        }
    };

    let proof_generation_key = expsk.proof_generation_key();
    let viewing_key = proof_generation_key.to_viewing_key();

    let diversifier = loop {
        let bytes: [u8; 11] = rng.random();
        let d = Diversifier(bytes);
        if viewing_key.to_payment_address(d).is_some() {
            break d;
        }
    };

    let payment_address = viewing_key
        .to_payment_address(diversifier)
        .expect("已经找到有效的 diversifier");

    let value = NoteValue::from_raw(1000);
    let rseed = Rseed::AfterZip212([0x42u8; 32]);
    let note = Note::from_parts(payment_address, value, rseed);

    let rcv = ValueCommitTrapdoor::random(&mut rng);
    let cv = ValueCommitment::derive(value, rcv.clone());
    let alpha = jubjub::Fr::random(&mut rng);

    let path_elems: Vec<Node> = (0..TREE_DEPTH)
        .map(|_| Node::from_scalar(bls12_381::Scalar::random(&mut rng)))
        .collect();
    let position = 0u64;
    let merkle_path =
        MerklePath::from_parts(path_elems, position.into()).expect("Merkle 路径长度必须为 32");
    let anchor: bls12_381::Scalar = merkle_path.root(Node::from_cmu(&note.cmu())).into();

    let circuit = SpendParameters::prepare_circuit(
        proof_generation_key,
        diversifier,
        rseed,
        value,
        alpha,
        rcv.clone(),
        anchor,
        merkle_path,
    )
    .expect("无法准备 Spend 电路");

    let nullifier = note.nf(viewing_key.nk(), position);
    let rk = viewing_key.rk(alpha);
    let sighash = [0u8; 32];
    let spend_auth_sig = expsk.ask().randomize(&alpha).sign(&mut rng, &sighash);

    let live_before_prove = mem_probe::live();
    println!("live_before_prove_bytes={live_before_prove}");

    // ----- CSV for provenance -----
    let raw_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../experiments/raw/csv");
    create_dir_all(&raw_dir)?;
    // Default to the original ledger file; allow an explicit override so a
    // separate diagnostic run does not append into an already-archived batch.
    let csv_path = std::env::var_os("SAPLING_PROVER_RUNS_CSV")
        .map(PathBuf::from)
        .unwrap_or_else(|| raw_dir.join("sapling_prove_memory_ledger.csv"));
    if let Some(parent) = csv_path.parent().filter(|p| !p.as_os_str().is_empty()) {
        create_dir_all(parent)?;
    }
    let mut csv = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&csv_path)?;
    if csv.metadata()?.len() == 0 {
        writeln!(
            csv,
            "batch_id,circuit,rayon_threads,build_profile,run,\
params_read_validate_ms,load_peak_delta_bytes,live_after_load_delta_bytes,\
live_before_prove_bytes,prove_ms,prove_peak_delta_bytes,prove_peak_abs_bytes,\
prove_live_end_delta_bytes,verify_ms,proof_bytes,verified"
        )?;
    }

    let batch_id = SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis();
    println!("batch_id={batch_id}");

    // ----- Phase 4: repeated proving, each with its own peak window -----
    for run in 1..=REPEATS {
        let circuit_for_run = circuit.clone();

        let before_prove = mem_probe::live();
        mem_probe::reset_peak();

        let prove_start = Instant::now();
        let proof = params.create_proof(circuit_for_run, &mut rng);
        let prove_ms = prove_start.elapsed().as_secs_f64() * 1000.0;

        let prove_peak_abs = mem_probe::peak();
        let after_prove = mem_probe::live();
        let prove_peak_delta = delta(prove_peak_abs, before_prove);
        let prove_live_end_delta = delta(after_prove, before_prove);

        let encoded_proof = SpendParameters::encode_proof(proof.clone());
        let proof_bytes = encoded_proof.len();

        let mut context = SaplingVerificationContext::new();
        let verify_start = Instant::now();
        let verified = context.check_spend(
            &cv,
            anchor,
            &nullifier.0,
            rk,
            &sighash,
            spend_auth_sig,
            proof,
            &prepared_vk,
        );
        let verify_ms = verify_start.elapsed().as_secs_f64() * 1000.0;

        writeln!(
            csv,
            "{},Spend,{},{},{},{:.3},{},{},{},{:.3},{},{},{},{:.3},{},{}",
            batch_id,
            rayon_threads,
            build_profile,
            run,
            load_ms,
            load_peak_delta,
            live_after_load_delta,
            live_before_prove,
            prove_ms,
            prove_peak_delta,
            prove_peak_abs,
            prove_live_end_delta,
            verify_ms,
            proof_bytes,
            verified,
        )?;
        csv.flush()?;

        println!(
            "run={run} prove_ms={prove_ms:.3} prove_peak_delta_bytes={prove_peak_delta} \
prove_peak_abs_bytes={prove_peak_abs} prove_live_end_delta_bytes={prove_live_end_delta} \
verify_ms={verify_ms:.3} proof_bytes={proof_bytes} verified={verified}"
        );

        assert!(verified, "第 {run} 份 Spend 证明验证失败");
    }

    println!("CSV_PATH={}", csv_path.display());
    println!("PROVE_MEMORY_LEDGER=PASS");

    Ok(())
}
