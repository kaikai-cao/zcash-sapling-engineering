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
    time::{Instant, SystemTime, UNIX_EPOCH},
};

const PARAMS_PATH: &str =
    r"D:\Research\zcash-params\sapling-spend.params";

const TREE_DEPTH: usize = 32;
const REPEATS: usize = 5;

fn main() -> Result<(), Box<dyn Error>> {
    let mut rng = StdRng::from_seed([7u8; 32]);

    // 1. 读取并验证 Spend 参数文件。
    let start = Instant::now();

    let params = SpendParameters::read(
        File::open(PARAMS_PATH).expect("无法打开 Spend 参数文件"),
        true,
    )
    .expect("无法读取或验证 Spend 参数文件");

    let params_read_validate_ms =
        start.elapsed().as_secs_f64() * 1000.0;

    println!(
        "params_read_validate_ms={params_read_validate_ms:.3}"
    );

    // 2. 预处理验证密钥，只执行一次。
    let start = Instant::now();
    let prepared_vk = params.prepared_verifying_key();

    let prepare_vk_ms =
        start.elapsed().as_secs_f64() * 1000.0;

    println!("prepare_vk_ms={prepare_vk_ms:.3}");

    // 3. 构造有效的测试见证及对应的 Merkle 路径。
    let start = Instant::now();

    let expsk = loop {
        let sk: [u8; 32] = rng.random();

        if let Some(key) = ExpandedSpendingKey::from_spending_key(&sk) {
            break key;
        }
    };

    let proof_generation_key = expsk.proof_generation_key();
    let viewing_key = proof_generation_key.to_viewing_key();

    // 随机寻找一个有效的 Sapling diversifier。
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

    // 生成 32 层路径。路径中的节点可以是随机值，
    // 但 anchor 必须由这条路径和当前笔记承诺计算得到。
    let path_elems: Vec<Node> = (0..TREE_DEPTH)
        .map(|_| {
            Node::from_scalar(bls12_381::Scalar::random(&mut rng))
        })
        .collect();

    // 使用位置 0，因此路径的每一层都将当前节点放在左侧。
    let position = 0u64;

    let merkle_path = MerklePath::from_parts(
        path_elems,
        position.into(),
    )
    .expect("Merkle 路径长度必须为 32");

    let anchor: bls12_381::Scalar = merkle_path
        .root(Node::from_cmu(&note.cmu()))
        .into();

    // 使用 Sapling 的正式接口准备 Spend 电路。
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

    // 准备验证所需的公开数据。
    let nullifier = note.nf(viewing_key.nk(), position);
    let rk = viewing_key.rk(alpha);

    // 测试用 sighash。签名和验证使用同一消息。
    let sighash = [0u8; 32];

    // 使用与 rk 相匹配的随机化授权密钥签名。
    let spend_auth_sig = expsk
        .ask()
        .randomize(&alpha)
        .sign(&mut rng, &sighash);

    let input_prep_ms =
        start.elapsed().as_secs_f64() * 1000.0;

    println!("input_prep_ms={input_prep_ms:.3}");

    // 4. 打开原始 CSV 文件，使用独立批次编号。
    let raw_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../experiments/raw/csv");

    create_dir_all(&raw_dir)?;

    let csv_path = raw_dir.join("sapling_spend_prover_runs_release.csv");

    let mut csv = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&csv_path)?;

    if csv.metadata()?.len() == 0 {
        writeln!(
            csv,
            "batch_id,run,params_read_validate_ms,\
prepare_vk_ms,input_prep_ms,prove_ms,verify_ms,\
proof_bytes,verified,rayon_threads,build_profile"
        )?;
    }

    let batch_id = SystemTime::now()
        .duration_since(UNIX_EPOCH)?
        .as_millis();

    let rayon_threads =
        std::env::var("RAYON_NUM_THREADS")
            .unwrap_or_else(|_| "default".to_string());

    let build_profile = if cfg!(debug_assertions) {
        "debug"
    } else {
        "release"
    };

    // 5. 重复生成并验证证明。
    for run in 1..=REPEATS {
        let circuit_for_run = circuit.clone();

        let start = Instant::now();
        let proof = params.create_proof(circuit_for_run, &mut rng);

        let prove_ms =
            start.elapsed().as_secs_f64() * 1000.0;

        let encoded_proof =
            SpendParameters::encode_proof(proof.clone());

        let proof_bytes = encoded_proof.len();

        let mut context = SaplingVerificationContext::new();

        let start = Instant::now();

        let verified = context.check_spend(
            &cv,
            anchor,
            &nullifier.0,
            rk,
            &sighash,
            spend_auth_sig.clone(),
            proof,
            &prepared_vk,
        );

        let verify_ms =
            start.elapsed().as_secs_f64() * 1000.0;

        writeln!(
            csv,
            "{},{},{:.3},{:.3},{:.3},{:.3},{:.3},{},{},{},{}",
            batch_id,
            run,
            params_read_validate_ms,
            prepare_vk_ms,
            input_prep_ms,
            prove_ms,
            verify_ms,
            proof_bytes,
            verified,
            rayon_threads,
            build_profile,
        )?;

        csv.flush()?;

        println!(
            "run={run}, prove_ms={prove_ms:.3}, \
verify_ms={verify_ms:.3}, proof_bytes={proof_bytes}, \
verified={verified}"
        );

        assert!(verified, "第 {run} 份 Spend 证明验证失败");
    }

    println!("batch_id={batch_id}");
    println!("CSV_PATH={}", csv_path.display());
    println!("SPEND_PROOF_EXPERIMENT=PASS");

    Ok(())
}