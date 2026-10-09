use group::GroupEncoding;
use rand::{rngs::StdRng, SeedableRng};
use sapling_crypto::{
    circuit::OutputParameters,
    note::Rseed,
    note_encryption::{sapling_note_encryption, SaplingDomain},
    prover::OutputProver,
    value::{NoteValue, ValueCommitTrapdoor, ValueCommitment},
    zip32::ExtendedSpendingKey,
    SaplingVerificationContext,
};
use std::{
    fs::{create_dir_all, File, OpenOptions},
    io::Write,
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use zcash_note_encryption::Domain;

fn main() {
    const REPEATS: usize = 5;

    let mut rng = StdRng::from_seed([7u8; 32]);

    // 1. 读取参数并校验点编码。
    let start = Instant::now();

    let params = OutputParameters::read(
        File::open(r"D:\Research\zcash-params\sapling-output.params")
            .expect("无法打开 Output 参数文件"),
        true,
    )
    .expect("无法读取 Output 参数文件");

    let params_read_validate_ms = start.elapsed().as_secs_f64() * 1000.0;

    println!("params_read_validate_ms={params_read_validate_ms:.3}");

    // 2. 准备验证密钥，只执行一次。
    let start = Instant::now();
    let prepared_vk = params.prepared_verifying_key();
    let prepare_vk_ms = start.elapsed().as_secs_f64() * 1000.0;

    println!("prepare_vk_ms={prepare_vk_ms:.3}");

    // 3. 准备同一份有效的测试输入。
    let start = Instant::now();

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

    let input_prep_ms = start.elapsed().as_secs_f64() * 1000.0;

    println!("input_prep_ms={input_prep_ms:.3}");

    // 4. 准备 CSV 文件。
    let csv_dir = "experiments/raw/csv";
    create_dir_all(csv_dir).expect("无法创建 CSV 目录");

    let csv_path = "experiments/raw/csv/sapling_output_prover_runs_release.csv";

    let mut csv = OpenOptions::new()
        .create(true)
        .append(true)
        .open(csv_path)
        .expect("无法打开 CSV 文件");

    if csv.metadata().expect("无法读取 CSV 文件信息").len() == 0 {
        writeln!(
            csv,
            "batch_id,run,params_read_validate_ms,\
prepare_vk_ms,input_prep_ms,prove_ms,verify_ms,\
proof_bytes,verified,rayon_threads,build_profile"
        )
        .expect("无法写入 CSV 表头");
    }

    let batch_id = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("系统时间异常")
        .as_millis();

    let rayon_threads =
        std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".to_string());

    let build_profile = if cfg!(debug_assertions) {
        "debug"
    } else {
        "release"
    };
    // 5. 重复生成证明，并逐份验证。
    for run in 1..=REPEATS {
        // 电路复制放在计时区间之外。
        let circuit_for_run = circuit.clone();

        let start = Instant::now();
        let proof = params.create_proof(circuit_for_run, &mut rng);
        let prove_ms = start.elapsed().as_secs_f64() * 1000.0;

        // 序列化用于统计证明大小，不计入 prove_ms。
        let encoded_proof = OutputParameters::encode_proof(proof.clone());
        let proof_bytes = encoded_proof.len();

        // 每份证明使用独立的验证上下文。
        let mut context = SaplingVerificationContext::new();

        let start = Instant::now();
        let verified = context.check_output(&cv, cmu.clone(), epk.clone(), proof, &prepared_vk);
        let verify_ms = start.elapsed().as_secs_f64() * 1000.0;

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
        )
        .expect("无法写入实验数据");

        csv.flush().expect("无法刷新 CSV 文件");

        println!(
            "run={run}, prove_ms={prove_ms:.3}, \
verify_ms={verify_ms:.3}, proof_bytes={proof_bytes}, \
verified={verified}"
        );

        assert!(verified, "第 {run} 份 Output 证明验证失败");
    }

    println!("CSV_PATH={csv_path}");
    println!("OUTPUT_PROOF_EXPERIMENT=PASS");
}
