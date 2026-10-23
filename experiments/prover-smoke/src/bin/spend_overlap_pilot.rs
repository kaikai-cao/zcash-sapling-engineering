//! Exploratory overlap pilot for independent Sapling Spend proofs.
//!
//! This binary is deliberately **not** a formal experiment and changes no
//! library default. It answers a narrow reconnaissance question:
//!
//! > With one shared 8-thread Rayon pool, does running independent Spend
//! > proofs concurrently recover enough of the serial stages to beat the
//! > sequential proof loop on *batch wall time*?
//!
//! `SAPLING_OVERLAP_ARM` selects:
//!   * `seq`   — one proof at a time (the current runner shape);
//!   * `conc2` — two worker threads pull proofs from a shared queue;
//!   * `conc3` — three worker threads.
//!
//! The output is per-proof start/end offsets plus the batch wall time. A
//! concurrent per-proof latency is expected to rise; only the batch wall can
//! improve through overlap. This pilot therefore says nothing about a
//! single proof's latency and cannot justify a default change.
//!
//! The process affinity and `RAYON_NUM_THREADS` are set by the caller. The
//! binary records them so the raw rows stay attributable.

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
    error::Error,
    fs::{create_dir_all, File, OpenOptions},
    io::Write,
    path::PathBuf,
    sync::{
        atomic::{AtomicUsize, Ordering},
        mpsc, Arc, Mutex,
    },
    time::{Instant, SystemTime, UNIX_EPOCH},
};

fn resolve_params_path() -> PathBuf {
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

const TREE_DEPTH: usize = 32;

#[derive(Clone, Copy)]
enum Arm {
    Sequential,
    Concurrent(usize),
}

impl Arm {
    fn from_env() -> Result<Self, Box<dyn Error>> {
        match std::env::var("SAPLING_OVERLAP_ARM").as_deref() {
            Ok("seq") | Err(_) => Ok(Arm::Sequential),
            Ok("conc2") => Ok(Arm::Concurrent(2)),
            Ok("conc3") => Ok(Arm::Concurrent(3)),
            Ok(other) => {
                Err(format!("unknown SAPLING_OVERLAP_ARM={other}; use seq|conc2|conc3").into())
            }
        }
    }

    fn label(self) -> String {
        match self {
            Arm::Sequential => "seq".to_string(),
            Arm::Concurrent(depth) => format!("conc{depth}"),
        }
    }
}

struct Record {
    proof_index: usize,
    worker: usize,
    start_offset_ms: f64,
    end_offset_ms: f64,
    prove_ms: f64,
    verify_ms: f64,
    verified: bool,
}

fn main() -> Result<(), Box<dyn Error>> {
    let arm = Arm::from_env()?;
    let proofs: usize = std::env::var("SAPLING_OVERLAP_PROOFS")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(5);
    let warmups: usize = std::env::var("SAPLING_OVERLAP_WARMUPS")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(1);

    let mut rng = StdRng::from_seed([7u8; 32]);

    let params_path = resolve_params_path();
    let params = match SpendParameters::read(
        File::open(&params_path).unwrap_or_else(|error| {
            panic!(
                "cannot open Spend parameters {}: {error}",
                params_path.display()
            )
        }),
        true,
    ) {
        Ok(params) => params,
        Err(error) => panic!("cannot read or validate Spend parameters: {error}"),
    };

    let prepared_vk = params.prepared_verifying_key();

    // Scenario construction is intentionally the same as spend_prover_smoke:
    // a valid Spend witness with a random 32-level Merkle path and position 0.
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
        .expect("valid diversifier");
    let value = NoteValue::from_raw(1000);
    let rseed = Rseed::AfterZip212([0x42u8; 32]);
    let note = Note::from_parts(payment_address, value, rseed);

    let rcv = ValueCommitTrapdoor::random(&mut rng);
    let cv = ValueCommitment::derive(value, rcv.clone());
    let cv_ref = &cv;
    let alpha = jubjub::Fr::random(&mut rng);

    let path_elems: Vec<Node> = (0..TREE_DEPTH)
        .map(|_| Node::from_scalar(bls12_381::Scalar::random(&mut rng)))
        .collect();
    let position = 0u64;
    let merkle_path =
        MerklePath::from_parts(path_elems, position.into()).expect("Merkle path length");
    let anchor: bls12_381::Scalar = merkle_path.root(Node::from_cmu(&note.cmu())).into();

    let circuit = SpendParameters::prepare_circuit(
        proof_generation_key,
        diversifier,
        rseed,
        value,
        alpha,
        rcv,
        anchor,
        merkle_path,
    )
    .expect("cannot prepare Spend circuit");

    let nullifier = note.nf(viewing_key.nk(), position);
    let rk = viewing_key.rk(alpha);
    let sighash = [0u8; 32];
    let spend_auth_sig = expsk.ask().randomize(&alpha).sign(&mut rng, &sighash);

    // Warm the proof path once. It is not recorded, matching the protocol's
    // "discard run 1" convention.
    for _ in 0..warmups {
        let proof = params.create_proof(circuit.clone(), &mut rng);
        let mut context = SaplingVerificationContext::new();
        assert!(
            context.check_spend(
                cv_ref,
                anchor,
                &nullifier.0,
                rk,
                &sighash,
                spend_auth_sig,
                proof,
                &prepared_vk,
            ),
            "warmup proof failed verification"
        );
    }

    let circuit_slots: Vec<Option<sapling_crypto::circuit::Spend>> =
        (0..proofs).map(|_| Some(circuit.clone())).collect();
    let slots = Arc::new(Mutex::new(circuit_slots));
    let next = Arc::new(AtomicUsize::new(0));
    let (sender, receiver) = mpsc::channel::<Record>();
    let batch_start = Instant::now();

    match arm {
        Arm::Sequential => {
            for proof_index in 0..proofs {
                let circuit = slots
                    .lock()
                    .expect("circuit slots")
                    .get_mut(proof_index)
                    .and_then(Option::take)
                    .expect("circuit slot");
                let start = Instant::now();
                let proof = params.create_proof(circuit, &mut rng);
                let prove_ms = start.elapsed().as_secs_f64() * 1000.0;
                let start_offset_ms = start.duration_since(batch_start).as_secs_f64() * 1000.0;
                let end_offset_ms =
                    Instant::now().duration_since(batch_start).as_secs_f64() * 1000.0;

                let verify_start = Instant::now();
                let mut context = SaplingVerificationContext::new();
                let verified = context.check_spend(
                    cv_ref,
                    anchor,
                    &nullifier.0,
                    rk,
                    &sighash,
                    spend_auth_sig,
                    proof,
                    &prepared_vk,
                );
                let verify_ms = verify_start.elapsed().as_secs_f64() * 1000.0;
                sender.send(Record {
                    proof_index,
                    worker: 0,
                    start_offset_ms,
                    end_offset_ms,
                    prove_ms,
                    verify_ms,
                    verified,
                })?;
            }
        }
        Arm::Concurrent(depth) => {
            std::thread::scope(|scope| {
                for worker in 0..depth {
                    let slots = Arc::clone(&slots);
                    let next = Arc::clone(&next);
                    let sender = sender.clone();
                    let params = &params;
                    let prepared_vk = &prepared_vk;
                    scope.spawn(move || {
                        let mut rng = StdRng::from_seed([7u8.wrapping_add(worker as u8); 32]);
                        loop {
                            let proof_index = next.fetch_add(1, Ordering::Relaxed);
                            if proof_index >= proofs {
                                break;
                            }
                            let circuit = slots
                                .lock()
                                .expect("circuit slots")
                                .get_mut(proof_index)
                                .and_then(Option::take)
                                .expect("circuit slot");
                            let start = Instant::now();
                            let proof = params.create_proof(circuit, &mut rng);
                            let prove_ms = start.elapsed().as_secs_f64() * 1000.0;
                            let start_offset_ms =
                                start.duration_since(batch_start).as_secs_f64() * 1000.0;
                            let end_offset_ms =
                                Instant::now().duration_since(batch_start).as_secs_f64() * 1000.0;

                            let verify_start = Instant::now();
                            let mut context = SaplingVerificationContext::new();
                            let verified = context.check_spend(
                                cv_ref,
                                anchor,
                                &nullifier.0,
                                rk,
                                &sighash,
                                spend_auth_sig,
                                proof,
                                prepared_vk,
                            );
                            let verify_ms = verify_start.elapsed().as_secs_f64() * 1000.0;
                            sender
                                .send(Record {
                                    proof_index,
                                    worker,
                                    start_offset_ms,
                                    end_offset_ms,
                                    prove_ms,
                                    verify_ms,
                                    verified,
                                })
                                .expect("record receiver");
                        }
                    });
                }
            });
        }
    }

    drop(sender);
    let batch_wall_ms = batch_start.elapsed().as_secs_f64() * 1000.0;
    let mut records: Vec<Record> = receiver.into_iter().collect();
    records.sort_by_key(|record| record.proof_index);

    let verified_count = records.iter().filter(|record| record.verified).count();
    if verified_count != proofs {
        return Err(format!("only {verified_count}/{proofs} proofs verified").into());
    }

    let raw_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../experiments/raw/csv");
    create_dir_all(&raw_dir)?;
    let csv_path = std::env::var_os("SAPLING_OVERLAP_CSV")
        .map(PathBuf::from)
        .unwrap_or_else(|| raw_dir.join("sapling_spend_overlap_pilot.csv"));
    if let Some(parent) = csv_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
    {
        create_dir_all(parent)?;
    }
    let mut csv = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&csv_path)?;
    if csv.metadata()?.len() == 0 {
        writeln!(
            csv,
            "batch_id,arm,proof_index,worker,start_offset_ms,end_offset_ms,prove_ms,verify_ms,verified,batch_wall_ms,rayon_threads,affinity_mask,git_head"
        )?;
    }

    let batch_id = SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis();
    let rayon_threads =
        std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".to_string());
    let affinity_mask =
        std::env::var("SAPLING_OVERLAP_AFFINITY").unwrap_or_else(|_| "unset".into());
    let git_head = std::env::var("SAPLING_OVERLAP_GIT_HEAD").unwrap_or_default();
    let arm_label = arm.label();

    for record in &records {
        writeln!(
            csv,
            "{},{},{},{},{:.3},{:.3},{:.3},{:.3},{},{:.3},{},{},{}",
            batch_id,
            arm_label,
            record.proof_index,
            record.worker,
            record.start_offset_ms,
            record.end_offset_ms,
            record.prove_ms,
            record.verify_ms,
            record.verified,
            batch_wall_ms,
            rayon_threads,
            affinity_mask,
            git_head,
        )?;
    }
    csv.flush()?;

    println!("batch_id={batch_id}");
    println!("arm={arm_label}");
    println!("proofs={proofs}");
    println!("batch_wall_ms={batch_wall_ms:.3}");
    for record in &records {
        println!(
            "proof={} worker={} start_ms={:.3} end_ms={:.3} prove_ms={:.3} verify_ms={:.3} verified={}",
            record.proof_index,
            record.worker,
            record.start_offset_ms,
            record.end_offset_ms,
            record.prove_ms,
            record.verify_ms,
            record.verified,
        );
    }
    println!("CSV_PATH={}", csv_path.display());
    println!("SPEND_OVERLAP_PILOT=PASS");

    Ok(())
}
