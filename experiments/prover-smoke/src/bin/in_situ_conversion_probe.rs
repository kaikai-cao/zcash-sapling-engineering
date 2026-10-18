//! In-situ measurement of the Groth16 assignment-conversion transients.
//!
//! `vendor/groth16/src/prover.rs` converts three assignment vectors from
//! `Scalar` into `bellman::multiexp::Exponent<Scalar>` before dispatching the
//! MSMs. `exponent_conversion_memory.rs` measures those conversions in a
//! *controlled* micro-benchmark with nothing else alive. This binary instead
//! measures them *in situ*, inside a real `create_proof` call, so the numbers
//! can be compared against the micro-benchmark.
//!
//! It installs a tracking `#[global_allocator]` feeding `bellman::mem_probe`
//! and enables the `SAPLING_IN_SITU_CONVERSION_PROBE=1` hook in the vendored
//! Groth16 prover. The prover then prints one `G16_IN_SITU_CONVERSION` line per
//! conversion, with:
//!
//!   * `source_bytes`      : the `Vec<Scalar>` buffer still alive at that point
//!   * `converted_bytes`   : the `Vec<Exponent>` being built
//!   * `peak_delta_bytes`  : directly measured live-byte peak above the
//!     pre-conversion live value (should be ~= the sum)
//!   * `live_after_delta_bytes` : retained bytes once the source is dropped
//!
//! Select the circuit with `SAPLING_IN_SITU_CIRCUIT=spend|output` (default
//! `spend`). One proof is generated and verified; the process exits non-zero if
//! verification fails.

use bellman::mem_probe;
use group::ff::Field;
use group::GroupEncoding;
use rand::{rngs::StdRng, RngExt, SeedableRng};
use sapling_crypto::{
    circuit::{OutputParameters, SpendParameters},
    keys::ExpandedSpendingKey,
    note::Rseed,
    note_encryption::{sapling_note_encryption, SaplingDomain},
    prover::{OutputProver, SpendProver},
    value::{NoteValue, ValueCommitTrapdoor, ValueCommitment},
    zip32::ExtendedSpendingKey,
    Diversifier, MerklePath, Node, Note, SaplingVerificationContext,
};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    error::Error,
    fs::File,
    path::PathBuf,
};
use zcash_note_encryption::Domain;

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

fn resolve_params_path(file_name: &str) -> PathBuf {
    let directory = std::env::var("ZCASH_PARAMS_DIR")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| r"D:\Research\zcash-params".to_string());

    PathBuf::from(directory).join(file_name)
}

fn circuit_name() -> String {
    std::env::var("SAPLING_IN_SITU_CIRCUIT")
        .map(|value| value.trim().to_lowercase())
        .unwrap_or_else(|_| "spend".to_string())
}

fn prove_spend() -> Result<(), Box<dyn Error>> {
    let mut rng = StdRng::from_seed([7u8; 32]);
    let params_path = resolve_params_path("sapling-spend.params");

    println!("circuit=Spend");
    println!("params_path={}", params_path.display());

    let params = SpendParameters::read(File::open(&params_path)?, true)?;
    let prepared_vk = params.prepared_verifying_key();

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

    let proof = params.create_proof(circuit, &mut rng);

    let mut context = SaplingVerificationContext::new();
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

    println!("verified={verified}");
    assert!(verified, "Spend 证明验证失败");

    Ok(())
}

fn prove_output() -> Result<(), Box<dyn Error>> {
    let mut rng = StdRng::from_seed([7u8; 32]);
    let params_path = resolve_params_path("sapling-output.params");

    println!("circuit=Output");
    println!("params_path={}", params_path.display());

    let params = OutputParameters::read(File::open(&params_path)?, true)?;
    let prepared_vk = params.prepared_verifying_key();

    let extsk = ExtendedSpendingKey::master(&[0u8; 32]).expect("无法生成测试密钥");
    let (_, payment_address) = extsk.default_address();
    let value = NoteValue::from_raw(1000);

    let rcv = ValueCommitTrapdoor::random(&mut rng);
    let cv = ValueCommitment::derive(value, rcv.clone());

    let rseed = Rseed::AfterZip212([0x42u8; 32]);
    let note = payment_address.create_note(value, rseed);

    let cmu = note.cmu();
    let rcm = note.rcm();
    let esk = note.generate_or_derive_esk(&mut rng);

    let encryptor = sapling_note_encryption(None, note, [0u8; 512], &mut rng);
    let epk_bytes = <SaplingDomain as Domain>::epk_bytes(encryptor.epk());
    let epk =
        Option::<jubjub::ExtendedPoint>::from(jubjub::ExtendedPoint::from_bytes(&epk_bytes.0))
            .expect("无法解析 epk");

    let circuit = OutputParameters::prepare_circuit(&esk, payment_address, rcm, value, rcv);

    let proof = params.create_proof(circuit, &mut rng);

    let mut context = SaplingVerificationContext::new();
    let verified = context.check_output(&cv, cmu, epk, proof, &prepared_vk);

    println!("verified={verified}");
    assert!(verified, "Output 证明验证失败");

    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    // The hook is opt-in; enable it here so the command line stays simple, but
    // respect an explicit value if the caller already set one.
    if std::env::var_os("SAPLING_IN_SITU_CONVERSION_PROBE").is_none() {
        std::env::set_var("SAPLING_IN_SITU_CONVERSION_PROBE", "1");
    }

    mem_probe::enable();

    let rayon_threads =
        std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".to_string());
    println!("rayon_threads={rayon_threads}");
    println!(
        "in_situ_conversion_probe={}",
        std::env::var("SAPLING_IN_SITU_CONVERSION_PROBE").unwrap_or_default()
    );

    match circuit_name().as_str() {
        "spend" => prove_spend()?,
        "output" => prove_output()?,
        other => return Err(format!("unknown SAPLING_IN_SITU_CIRCUIT={other}").into()),
    }

    println!("IN_SITU_CONVERSION_PROBE=PASS");
    Ok(())
}
