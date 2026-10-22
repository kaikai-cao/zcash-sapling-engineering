//! 完整 Sapling 交易构造基准（真实交易构造器）。
//!
//! 与既有 Spend/Output proving 实验的区别：那些实验直接调用
//! `SpendParameters::create_proof` / `OutputParameters::create_proof`；本程序调用的是
//! 真实交易构造器 `zcash_primitives::transaction::builder::Builder::build(...)`，
//! 即 `docs/zcash_sapling_flow.md` §2 描述的那条链路：
//!
//!   Builder::build -> Sapling builder -> create_proofs(Spend/Output)
//!                  -> 计算 sighash -> 应用授权签名 -> 交易对象
//!
//! 测量口径与冻结验收表见
//! `experiments/metadata/sapling_tx_construction_preregistration_20261022.md`。
//! **本程序不测网络广播、不测钱包输入选择**：所有时间都是本地构造时间。
//!
//! 三个臂由环境变量 `TX_SMOKE_ARM` 选择：
//!   * `real`  —— 真实构造 + 真实 proving 参数（主臂）
//!   * `mock`  —— 同一构造器 + mock prover（分解对照：除 Groth16 外的全部开销）
//!
//! 其余环境变量：
//!   * `ZCASH_PARAMS_DIR`（默认 `D:\Research\zcash-params`）
//!   * `RAYON_NUM_THREADS`
//!   * `TX_CONSTRUCT_CSV`（默认写到 `experiments/raw/csv/`）
//!   * `TX_SMOKE_TAG`（批次标签，写进 CSV 的 `tag` 列）

use std::{
    error::Error,
    fs::{create_dir_all, File, OpenOptions},
    io::{Read, Write},
    path::PathBuf,
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use group::ff::Field;
use rand::{rngs::StdRng, SeedableRng};
use sha2::{Digest, Sha256};

use sapling::{
    circuit::{OutputParameters, SpendParameters},
    keys::FullViewingKey,
    prover::{
        mock::{MockOutputProver, MockSpendProver},
        OutputProver, SpendProver,
    },
    value::NoteValue,
    zip32::ExtendedSpendingKey,
    Anchor, BatchValidator, MerklePath, Node, Note, PaymentAddress, Rseed,
};
use transparent::builder::TransparentSigningSet;
use zcash_primitives::transaction::{
    builder::{BuildConfig, Builder, BundlePadding},
    fees::zip317,
    sighash::{PrecomputedSighashData, SignableInput},
    Authorization, Transaction, TransactionData,
};
use zcash_protocol::{
    consensus::{BlockHeight, MAIN_NETWORK},
    memo::MemoBytes,
    value::Zatoshis,
};

// ---------------------------------------------------------------------------
// 冻结场景（见预注册 §2）。任何改动都会使本批次与预注册不一致。
// ---------------------------------------------------------------------------

/// Sapling 承诺树深度。
const TREE_DEPTH: usize = 32;

/// 每臂 run 数；run 1 丢弃（暖态取 run 2..）。
const REPEATS: usize = 6;

/// 目标高度：NU5 激活之后、NU6 之前 ⇒ 交易版本 v5，Sapling bundle 为 v4 格式。
const TARGET_HEIGHT: u32 = 1_700_000;

/// 花费的 note 面额（zats）。
const SPEND_ZATS: u64 = 100_000_000;
/// 收款输出面额（zats）。
const OUT_PAYMENT_ZATS: u64 = 60_000_000;
/// 找零输出面额（zats）：100,000,000 − 60,000,000 − 10,000。
const OUT_CHANGE_ZATS: u64 = 39_990_000;
/// ZIP-317 手续费：marginal_fee(5,000) × max(grace(2), logical_actions) = 10,000。
/// `logical_actions = max(透明输入, 透明输出) + max(sapling spend, sapling output) + orchard + ironwood`
/// = 0 + max(1, 2) + 0 + 0 = 2 ⇒ `5,000 × max(2, 2) = 10,000`。
/// 预注册初版按 "1 spend + 2 outputs = 3 actions" 估成 15,000，测量前发现口径错误并修正，
/// 偏差记录见预注册 §10。
const FEE_ZATS: u64 = 10_000;

/// 三个 zip32 主密钥的固定种子（spend / 收款 / 找零）。
const SEED_SPEND: [u8; 32] = [0x11; 32];
const SEED_PAYEE: [u8; 32] = [0x12; 32];
const SEED_CHANGE: [u8; 32] = [0x13; 32];

/// note 的 rcm 种子（ZIP-212 之后的 note）。
const RSEED_BYTES: [u8; 32] = [0x42; 32];

/// 每进程的 RNG 种子。
const RNG_SEED: [u8; 32] = [0x42; 32];

// ---------------------------------------------------------------------------

#[derive(Clone, Copy, PartialEq, Eq)]
enum Arm {
    Real,
    Mock,
}

impl Arm {
    fn from_env() -> Result<Self, Box<dyn Error>> {
        match std::env::var("TX_SMOKE_ARM").as_deref() {
            Ok("real") => Ok(Arm::Real),
            Ok("mock") => Ok(Arm::Mock),
            Ok(other) => Err(format!("TX_SMOKE_ARM 只接受 real|mock，收到 `{other}`").into()),
            Err(_) => Err("必须设置 TX_SMOKE_ARM=real|mock".into()),
        }
    }

    fn label(self) -> &'static str {
        match self {
            Arm::Real => "real",
            Arm::Mock => "mock",
        }
    }
}

/// 冻结场景的全部输入。每次 run 都用同一份密钥/地址/路径结构，
/// 但 randomness 由同一个 RNG 继续推进（因此 run 之间是独立构造）。
struct Scenario {
    extsk: ExtendedSpendingKey,
    fvk: FullViewingKey,
    note: Note,
    merkle_path: MerklePath,
    anchor: Anchor,
    to: PaymentAddress,
    change: PaymentAddress,
}

fn master_key(seed: &[u8; 32]) -> Result<ExtendedSpendingKey, Box<dyn Error>> {
    ExtendedSpendingKey::master(seed).ok_or_else(|| "无法从固定种子导出 zip32 主密钥".into())
}

fn default_address(extsk: &ExtendedSpendingKey) -> PaymentAddress {
    extsk
        .to_diversifiable_full_viewing_key()
        .default_address()
        .1
}

fn make_scenario(rng: &mut StdRng) -> Result<Scenario, Box<dyn Error>> {
    let extsk = master_key(&SEED_SPEND)?;
    let dfvk = extsk.to_diversifiable_full_viewing_key();
    let fvk = dfvk.fvk().clone();
    let payment_address = dfvk.default_address().1;

    let note = Note::from_parts(
        payment_address,
        NoteValue::from_raw(SPEND_ZATS),
        Rseed::AfterZip212(RSEED_BYTES),
    );

    // 合成 Merkle 路径：32 层随机节点、position 0。
    // 明确声明：这些节点不对应任何真实链上状态，只用于构造一条自洽的 witness。
    let path_elems: Vec<Node> = (0..TREE_DEPTH)
        .map(|_| Node::from_scalar(bls12_381::Scalar::random(&mut *rng)))
        .collect();
    let merkle_path =
        MerklePath::from_parts(path_elems, 0u64.into()).map_err(|_| "Merkle 路径长度错误")?;

    let anchor = Anchor::from(merkle_path.root(Node::from_cmu(&note.cmu())));

    Ok(Scenario {
        extsk,
        fvk,
        note,
        merkle_path,
        anchor,
        to: default_address(&master_key(&SEED_PAYEE)?),
        change: default_address(&master_key(&SEED_CHANGE)?),
    })
}

/// 仅用于计算 sighash 的授权标记。
///
/// `PrecomputedSighashData::new` 要求 `A::TransparentAuth: TransparentAuthorizingContext`，
/// 而真正上链形态的 `transparent::bundle::Authorized` 不实现该 trait（它没有 prevout 授权数据）。
/// 本场景没有任何透明输入，因此把透明 bundle 映射为 `None`、Sapling/Orchard bundle 原样保留，
/// 得到的 sighash 与构造器内部计算的那一个完全相同。
struct SighashAuth;

impl Authorization for SighashAuth {
    type TransparentAuth = transparent::pczt::Unbound;
    type SaplingAuth = sapling::bundle::Authorized;
    type OrchardAuth = orchard::bundle::Authorized;
}

fn shielded_sighash(tx: &Transaction) -> [u8; 32] {
    let data: TransactionData<SighashAuth> = tx
        .clone()
        .into_data()
        .map_bundles(|_| None, |bundle| bundle, |bundle| bundle);
    let sighash = PrecomputedSighashData::new(data).signature_hash(&SignableInput::Shielded);
    *sighash.as_ref()
}

/// 一次构造的产物。
struct BuiltTx {
    tx: Transaction,
    build_ms: f64,
    serialize_ms: f64,
    txid_ms: f64,
    verify_ms: f64,
    verified: bool,
    tx_bytes: usize,
    explore_durations_ms: Vec<f64>,
}

/// 用真实或 mock prover 构造一次交易，并按预注册 §3 的口径计时。
fn build_once<SP: SpendProver, OP: OutputProver>(
    scenario: &Scenario,
    spend_prover: &SP,
    output_prover: &OP,
    spend_vk: &sapling::circuit::SpendVerifyingKey,
    output_vk: &sapling::circuit::OutputVerifyingKey,
    rng: &mut StdRng,
    verify: bool,
) -> Result<BuiltTx, Box<dyn Error>> {
    // 进度消息的接收线程：构造器在每份证明完成后发送一条 `Progress`，
    // 由阻塞在 recv 上的线程打时间戳（比构造结束后再读缓冲更精确）。
    let (progress_tx, progress_rx) = mpsc::channel();
    let marks: Arc<Mutex<Vec<Instant>>> = Arc::new(Mutex::new(Vec::new()));
    let marks_rx = Arc::clone(&marks);
    let receiver = thread::spawn(move || {
        while progress_rx.recv().is_ok() {
            marks_rx.lock().expect("mutex").push(Instant::now());
        }
    });

    let config = BuildConfig::Standard {
        sapling_anchor: Some(scenario.anchor),
        orchard_anchor: None,
        ironwood_anchor: None,
        orchard_padding: BundlePadding::DEFAULT,
        ironwood_padding: BundlePadding::DEFAULT,
    };

    let mut builder = Builder::new(MAIN_NETWORK, BlockHeight::from_u32(TARGET_HEIGHT), config)
        .with_progress_notifier(progress_tx);

    builder.add_sapling_spend::<zip317::FeeError>(
        scenario.fvk.clone(),
        scenario.note.clone(),
        scenario.merkle_path.clone(),
    )?;
    builder.add_sapling_output::<zip317::FeeError>(
        None,
        scenario.to,
        Zatoshis::from_u64(OUT_PAYMENT_ZATS)?,
        MemoBytes::empty(),
    )?;
    builder.add_sapling_output::<zip317::FeeError>(
        None,
        scenario.change,
        Zatoshis::from_u64(OUT_CHANGE_ZATS)?,
        MemoBytes::empty(),
    )?;

    let start = Instant::now();
    let result = builder.build::<_, SP, OP, zip317::FeeRule>(
        &TransparentSigningSet::new(),
        std::slice::from_ref(&scenario.extsk),
        &[],
        &mut *rng,
        spend_prover,
        output_prover,
        &zip317::FeeRule::standard(),
    )?;
    let build_ms = start.elapsed().as_secs_f64() * 1000.0;

    // 构造器被消费后 sender 已释放 ⇒ recv 返回 Err ⇒ 接收线程退出。
    receiver.join().expect("进度接收线程 panic");

    let marks = marks.lock().expect("mutex").clone();
    let mut durations = Vec::with_capacity(marks.len());
    let mut previous = start;
    for mark in marks {
        durations.push(mark.duration_since(previous).as_secs_f64() * 1000.0);
        previous = mark;
    }

    let tx = result.transaction().clone();

    let start = Instant::now();
    let mut bytes = Vec::with_capacity(4096);
    tx.write(&mut bytes)?;
    let serialize_ms = start.elapsed().as_secs_f64() * 1000.0;
    let tx_bytes = bytes.len();

    let start = Instant::now();
    let _txid = tx.txid();
    let txid_ms = start.elapsed().as_secs_f64() * 1000.0;

    let (verify_ms, verified) = if verify {
        let start = Instant::now();

        let bundle = tx
            .sapling_bundle()
            .ok_or("构造出的交易没有 Sapling bundle")?
            .clone();
        let sighash_bytes = shielded_sighash(&tx);

        let mut validator = BatchValidator::new();
        let consensus_ok = validator.check_bundle(bundle, sighash_bytes);
        let proofs_ok = validator.validate(spend_vk, output_vk, &mut *rng);

        (start.elapsed().as_secs_f64() * 1000.0, consensus_ok && proofs_ok)
    } else {
        (f64::NAN, false)
    };

    Ok(BuiltTx {
        tx,
        build_ms,
        serialize_ms,
        txid_ms,
        verify_ms,
        verified,
        tx_bytes,
        explore_durations_ms: durations,
    })
}

// ---------------------------------------------------------------------------

fn resolve_params_path(name: &str) -> PathBuf {
    if let Ok(directory) = std::env::var("ZCASH_PARAMS_DIR") {
        let directory = directory.trim();
        if !directory.is_empty() {
            return PathBuf::from(directory).join(name);
        }
    }
    PathBuf::from(r"D:\Research\zcash-params").join(name)
}

fn sha256_file(path: &PathBuf) -> String {
    let mut file = match File::open(path) {
        Ok(file) => file,
        Err(_) => return "unreadable".to_string(),
    };
    let mut hasher = Sha256::new();
    let mut buffer = vec![0u8; 1 << 20];
    loop {
        match file.read(&mut buffer) {
            Ok(0) => break,
            Ok(n) => hasher.update(&buffer[..n]),
            Err(_) => return "unreadable".to_string(),
        }
    }
    format!("{:x}", hasher.finalize())
}

fn main() -> Result<(), Box<dyn Error>> {
    let arm = Arm::from_env()?;
    let mut rng = StdRng::from_seed(RNG_SEED);

    let spend_params_path = resolve_params_path("sapling-spend.params");
    let output_params_path = resolve_params_path("sapling-output.params");

    // ---- 进程级 setup（不计入构造时间） ----
    let start = Instant::now();
    let spend_params = SpendParameters::read(
        File::open(&spend_params_path)?,
        true,
    )?;
    let output_params = OutputParameters::read(File::open(&output_params_path)?, true)?;
    let setup_params_ms = start.elapsed().as_secs_f64() * 1000.0;

    let start = Instant::now();
    let spend_vk = spend_params.verifying_key();
    let output_vk = output_params.verifying_key();
    let _prepared_spend_vk = spend_params.prepared_verifying_key();
    let _prepared_output_vk = output_params.prepared_verifying_key();
    let setup_vk_ms = start.elapsed().as_secs_f64() * 1000.0;

    println!("arm={}", arm.label());
    println!("spend_params={}", spend_params_path.display());
    println!("output_params={}", output_params_path.display());
    println!("setup_params_ms={setup_params_ms:.3}");
    println!("setup_vk_ms={setup_vk_ms:.3}");

    // ---- 原始 CSV ----
    let raw_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../experiments/raw/csv");
    create_dir_all(&raw_dir)?;
    let csv_path = std::env::var_os("TX_CONSTRUCT_CSV")
        .map(PathBuf::from)
        .unwrap_or_else(|| raw_dir.join(format!("sapling_tx_construct_runs_{}.csv", arm.label())));
    if let Some(parent) = csv_path.parent().filter(|p| !p.as_os_str().is_empty()) {
        create_dir_all(parent)?;
    }
    let mut csv = OpenOptions::new().create(true).append(true).open(&csv_path)?;
    if csv.metadata()?.len() == 0 {
        writeln!(
            csv,
            "batch_id,tag,arm,run,repeats,affinity_mask,rayon_threads,\
setup_params_ms,setup_vk_ms,witness_ms,build_ms,mock_build_ms,\
serialize_ms,txid_ms,total_construct_ms,\
prove_spend_ms,prove_output_a_ms,prove_output_b_ms,sum_proofs_ms,\
verify_ms,verified,tx_version,tx_header,consensus_branch_id,tx_bytes,\
spend_count,output_count,fee_zats,value_balance_zats,txid,\
spend_params_sha256,output_params_sha256,exe_sha256,exe_path,rustc_version,build_profile,git_head"
        )?;
    }

    let batch_id = SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis();
    let tag = std::env::var("TX_SMOKE_TAG").unwrap_or_default();
    let affinity_mask = std::env::var("TX_SMOKE_AFFINITY").unwrap_or_else(|_| "unset".into());
    let rayon_threads = std::env::var("RAYON_NUM_THREADS").unwrap_or_else(|_| "default".into());
    let exe_path = std::env::current_exe()?;
    let exe_sha256 = sha256_file(&exe_path);
    let spend_params_sha256 = sha256_file(&spend_params_path);
    let output_params_sha256 = sha256_file(&output_params_path);
    let rustc_version = option_env!("RUSTC_VERSION_UNKNOWN")
        .unwrap_or("see batch log")
        .to_string();
    let build_profile = if cfg!(debug_assertions) { "debug" } else { "release" };
    let git_head = std::env::var("TX_SMOKE_GIT_HEAD").unwrap_or_default();

    println!("batch_id={batch_id}");
    println!("exe_sha256={exe_sha256}");
    println!("spend_params_sha256={spend_params_sha256}");
    println!("output_params_sha256={output_params_sha256}");

    let start = Instant::now();
    let scenario = make_scenario(&mut rng)?;
    let witness_ms = start.elapsed().as_secs_f64() * 1000.0;
    println!("witness_ms={witness_ms:.3}");

    // 结构断言的参照值（第一次成功构造后确定，其后所有 run 必须一致）。
    let mut reference: Option<(usize, String, String, String)> = None;

    for run in 1..=REPEATS {
        let built = match arm {
            Arm::Real => build_once(
                &scenario,
                &spend_params,
                &output_params,
                &spend_vk,
                &output_vk,
                &mut rng,
                true,
            )?,
            Arm::Mock => build_once(
                &scenario,
                &MockSpendProver,
                &MockOutputProver,
                &spend_vk,
                &output_vk,
                &mut rng,
                false,
            )?,
        };

        let tx = &built.tx;
        let version_label = format!("{:?}", tx.version());
        let tx_header = tx.version().header();
        let branch_label = format!("{:?}", tx.consensus_branch_id());
        let fee_zats = FEE_ZATS;
        let (spend_count, output_count, value_balance_zats) = match tx.sapling_bundle() {
            Some(bundle) => (
                bundle.shielded_spends().len(),
                bundle.shielded_outputs().len(),
                i64::from(*bundle.value_balance()),
            ),
            None => (0, 0, 0),
        };
        let txid = format!("{}", tx.txid());

        // 结构断言：形状、版本、平账、字节数恒定。
        assert_eq!(spend_count, 1, "run {run}: spend 数应为 1");
        assert_eq!(output_count, 2, "run {run}: output 数应为 2");
        // Sapling value balance 是有符号量（`ZatBalance`），定义 = 输入 − 输出；
        // 本场景把手续费留在 Sapling 池一侧，故为 +fee。
        assert_eq!(
            value_balance_zats, FEE_ZATS as i64,
            "run {run}: Sapling value balance 应为 +fee"
        );
        assert_eq!(version_label, "V5", "run {run}: 交易版本应为 V5");
        match &reference {
            None => reference = Some((built.tx_bytes, txid.clone(), version_label.clone(), branch_label.clone())),
            Some((bytes, ref_txid, ref_version, ref_branch)) => {
                assert_eq!(*bytes, built.tx_bytes, "run {run}: 序列化长度与其他 run 不一致");
                assert_eq!(ref_version, &version_label, "run {run}: 版本与其他 run 不一致");
                assert_eq!(ref_branch, &branch_label, "run {run}: branch id 与其他 run 不一致");
                let _ = ref_txid;
            }
        }
        if arm == Arm::Real {
            assert!(built.verified, "run {run}: 交易密码学校验失败");
        }

        // 反序列化一致性：同一字节串读回后 txid 必须相同。
        let round_trip = Transaction::read(&mut &{
            let mut bytes = Vec::new();
            tx.write(&mut bytes)?;
            bytes
        }[..], tx.consensus_branch_id())?;
        assert_eq!(format!("{}", round_trip.txid()), txid, "run {run}: 反序列化后 txid 不一致");

        let durations = &built.explore_durations_ms;
        let (spend_proof, out_a, out_b) = match durations.len() {
            3 => (durations[0], durations[1], durations[2]),
            other => return Err(format!("run {run}: 期望 3 条进度消息，收到 {other}").into()),
        };
        // 进度消息按 spend → output → output 顺序到达；用机制先验做一次方向性检查。
        assert!(
            spend_proof > out_a.max(out_b),
            "run {run}: spend 证明应显著慢于 output 证明（实际 {spend_proof:.1} vs {out_a:.1}/{out_b:.1}）"
        );
        let sum_proofs_ms = spend_proof + out_a + out_b;

        let build_ms = built.build_ms;
        let mock_build_ms = if arm == Arm::Mock { build_ms } else { f64::NAN };
        let total_construct_ms = build_ms + built.serialize_ms;

        let fields: Vec<String> = vec![
            batch_id.to_string(),
            tag.clone(),
            arm.label().to_string(),
            run.to_string(),
            REPEATS.to_string(),
            affinity_mask.clone(),
            rayon_threads.clone(),
            format!("{setup_params_ms:.3}"),
            format!("{setup_vk_ms:.3}"),
            format!("{witness_ms:.3}"),
            format!("{build_ms:.3}"),
            format!("{mock_build_ms:.3}"),
            format!("{:.3}", built.serialize_ms),
            format!("{:.3}", built.txid_ms),
            format!("{total_construct_ms:.3}"),
            format!("{spend_proof:.3}"),
            format!("{out_a:.3}"),
            format!("{out_b:.3}"),
            format!("{sum_proofs_ms:.3}"),
            format!("{:.3}", built.verify_ms),
            if arm == Arm::Real {
                built.verified.to_string()
            } else {
                "n/a".to_string()
            },
            version_label.clone(),
            tx_header.to_string(),
            branch_label.clone(),
            built.tx_bytes.to_string(),
            spend_count.to_string(),
            output_count.to_string(),
            fee_zats.to_string(),
            value_balance_zats.to_string(),
            txid.clone(),
            spend_params_sha256.clone(),
            output_params_sha256.clone(),
            exe_sha256.clone(),
            exe_path.display().to_string(),
            rustc_version.clone(),
            build_profile.to_string(),
            git_head.clone(),
        ];
        writeln!(csv, "{}", fields.join(","))?;
        csv.flush()?;

        println!(
            "run={run} build_ms={build_ms:.3} serialize_ms={:.3} total_ms={total_construct_ms:.3} \
spend_proof_ms={spend_proof:.3} output_ms=[{out_a:.3},{out_b:.3}] verify_ms={:.3} verified={} tx_bytes={} txid={}",
            built.serialize_ms, built.verify_ms, built.verified, built.tx_bytes, txid
        );
    }

    println!("CSV_PATH={}", csv_path.display());
    println!("TX_CONSTRUCT_EXPERIMENT=PASS");
    Ok(())
}
