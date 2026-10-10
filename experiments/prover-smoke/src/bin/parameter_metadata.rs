use blake2b_simd::Params as Blake2bParams;
use sapling_crypto::circuit::{OutputParameters, SpendParameters};
use sha2::{Digest, Sha256};
use std::{
    error::Error,
    fs::{self, File, OpenOptions},
    io::{BufReader, Read, Write},
    path::{Path, PathBuf},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

const PARAMS_DIR: &str = r"D:\Research\zcash-params";

const SOURCE_VERSION: &str = "0.9.0";
const SOURCE_COMMIT: &str = "88a7946b4a3066787776e11f0a502654167e022d";

/// 读取参数并验证其中的椭圆曲线点编码。
/// 返回的时间包含打开文件、读取参数和点编码验证。
fn measure_spend_load_validate(path: &Path) -> f64 {
    let start = Instant::now();

    let file = File::open(path)
        .unwrap_or_else(|e| panic!("无法打开 Spend 参数文件 {}：{e}", path.display()));

    let _params = SpendParameters::read(file, true)
        .unwrap_or_else(|e| panic!("Spend 参数读取或点编码验证失败：{e}"));

    start.elapsed().as_secs_f64() * 1000.0
}

fn measure_output_load_validate(path: &Path) -> f64 {
    let start = Instant::now();

    let file = File::open(path)
        .unwrap_or_else(|e| panic!("无法打开 Output 参数文件 {}：{e}", path.display()));

    let _params = OutputParameters::read(file, true)
        .unwrap_or_else(|e| panic!("Output 参数读取或点编码验证失败：{e}"));

    start.elapsed().as_secs_f64() * 1000.0
}

/// 使用流式读取计算 SHA-256 和 BLAKE2b-512，
/// 避免一次性将整个参数文件载入额外的内存。
fn calculate_hashes(
    path: &Path,
) -> Result<(u64, String, String), Box<dyn Error>> {
    let metadata = fs::metadata(path)?;
    let file_bytes = metadata.len();

    let file = File::open(path)?;
    let mut reader = BufReader::new(file);

    let mut sha256 = Sha256::new();
    let mut blake2b = Blake2bParams::new()
        .hash_length(64)
        .to_state();

    let mut buffer = [0u8; 1024 * 1024];

    loop {
        let bytes_read = reader.read(&mut buffer)?;

        if bytes_read == 0 {
            break;
        }

        let chunk = &buffer[..bytes_read];
        sha256.update(chunk);
        blake2b.update(chunk);
    }

    let sha256_hex = format!("{:x}", sha256.finalize());
    let blake2b512_hex = blake2b.finalize().to_hex().to_string();

    Ok((file_bytes, sha256_hex, blake2b512_hex))
}

fn build_csv_row(
    batch_id: u128,
    parameter: &str,
    circuit: &str,
    path: &Path,
    load_validate_ms: f64,
) -> Result<String, Box<dyn Error>> {
    let (file_bytes, sha256, blake2b512) = calculate_hashes(path)?;
    let file_mib = file_bytes as f64 / (1024.0 * 1024.0);

    Ok(format!(
        "{},{},{},{},{},{},{},{:.3},{},{},{:.3},true",
        batch_id,
        parameter,
        circuit,
        SOURCE_VERSION,
        SOURCE_COMMIT,
        path.display(),
        file_bytes,
        file_mib,
        sha256,
        blake2b512,
        load_validate_ms,
    ))
}

fn main() -> Result<(), Box<dyn Error>> {
    let spend_path =
        PathBuf::from(PARAMS_DIR).join("sapling-spend.params");

    let output_path =
        PathBuf::from(PARAMS_DIR).join("sapling-output.params");

    // 每次运行生成一个批次编号，两条记录共用该编号。
    let batch_id = SystemTime::now()
        .duration_since(UNIX_EPOCH)?
        .as_millis();

    // 第一步：分别读取并验证参数，独立计时。
    println!("正在读取并验证 Spend 参数……");
    let spend_load_validate_ms =
        measure_spend_load_validate(&spend_path);

    println!("Spend load_validate_ms={spend_load_validate_ms:.3}");

    println!("正在读取并验证 Output 参数……");
    let output_load_validate_ms =
        measure_output_load_validate(&output_path);

    println!("Output load_validate_ms={output_load_validate_ms:.3}");

    // 第二步：计算文件大小与哈希，并构造本批次记录。
    println!("正在计算参数文件大小和哈希……");

    let spend_row = build_csv_row(
        batch_id,
        "sapling-spend.params",
        "Spend",
        &spend_path,
        spend_load_validate_ms,
    )?;

    let output_row = build_csv_row(
        batch_id,
        "sapling-output.params",
        "Output",
        &output_path,
        output_load_validate_ms,
    )?;

    // 第三步：把原始数据追加到 experiments/raw/csv。
    let output_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../experiments/raw/csv");

    fs::create_dir_all(&output_dir)?;

    let csv_path =
        output_dir.join("sapling_parameter_metadata_raw.csv");

    let mut csv_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&csv_path)?;

    // 仅在新文件或空文件中写入表头。
    if csv_file.metadata()?.len() == 0 {
        writeln!(
            csv_file,
            "batch_id,parameter,circuit,source_version,\
source_commit,path,file_bytes,file_mib,sha256,blake2b512,\
load_validate_ms,point_encodings_verified"
        )?;
    }

    writeln!(csv_file, "{spend_row}")?;
    writeln!(csv_file, "{output_row}")?;
    csv_file.flush()?;

    println!();
    println!("本批次记录：");
    println!(
        "parameter,circuit,file_bytes,file_mib,sha256,\
blake2b512,load_validate_ms,point_encodings_verified"
    );

    println!(
        "sapling-spend.params,Spend,{},{:.3},{},{},{:.3},true",
        calculate_hashes(&spend_path)?.0,
        calculate_hashes(&spend_path)?.0 as f64 / (1024.0 * 1024.0),
        calculate_hashes(&spend_path)?.1,
        calculate_hashes(&spend_path)?.2,
        spend_load_validate_ms,
    );

    println!(
        "sapling-output.params,Output,{},{:.3},{},{},{:.3},true",
        calculate_hashes(&output_path)?.0,
        calculate_hashes(&output_path)?.0 as f64 / (1024.0 * 1024.0),
        calculate_hashes(&output_path)?.1,
        calculate_hashes(&output_path)?.2,
        output_load_validate_ms,
    );

    println!("batch_id={batch_id}");
    println!("原始 CSV 已追加到：{}", csv_path.display());

    Ok(())
}