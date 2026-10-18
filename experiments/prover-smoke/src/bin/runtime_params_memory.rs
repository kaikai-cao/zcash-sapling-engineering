use bls12_381::{Bls12, G1Affine, G2Affine};
use groth16::Parameters;
use std::{env, error::Error, fs::File, mem::size_of, path::Path, time::Instant};

fn report_vec<T>(name: &str, values: &Vec<T>) -> (usize, usize) {
    let element_size = size_of::<T>();
    let len_bytes = values.len() * element_size;
    let capacity_bytes = values.capacity() * element_size;

    println!(
        "{:<12} len={:>7} capacity={:>7} element_size={:>3} B \
         len_payload={:>10} B capacity_payload={:>10} B",
        name,
        values.len(),
        values.capacity(),
        element_size,
        len_bytes,
        capacity_bytes,
    );

    (len_bytes, capacity_bytes)
}

fn report_params(path: &Path) -> Result<(), Box<dyn Error>> {
    println!("\n===== {} =====", path.display());

    let start = Instant::now();

    // checked=true：读取参数时验证点编码。
    let params = Parameters::<Bls12>::read(File::open(path)?, true)?;

    let read_ms = start.elapsed().as_secs_f64() * 1000.0;
    println!("groth16_body_read_validate_ms={read_ms:.3}");

    // VK 中的六个固定点：三个 G1、三个 G2。
    let vk_fixed_bytes = 3 * size_of::<G1Affine>() + 3 * size_of::<G2Affine>();

    println!("vk_fixed_points=6 vk_fixed_object_bytes={vk_fixed_bytes}");

    let mut len_total = vk_fixed_bytes;
    let mut capacity_total = vk_fixed_bytes;

    let (len, capacity) = report_vec("VK_IC", &params.vk.ic);
    len_total += len;
    capacity_total += capacity;

    let vectors = [
        ("H_G1", params.h.as_ref()),
        ("L_G1", params.l.as_ref()),
        ("A_G1", params.a.as_ref()),
        ("B_G1", params.b_g1.as_ref()),
    ];

    for (name, values) in vectors {
        let (len, capacity) = report_vec(name, values);
        len_total += len;
        capacity_total += capacity;
    }

    let (len, capacity) = report_vec("B_G2", params.b_g2.as_ref());
    len_total += len;
    capacity_total += capacity;

    println!("point_object_payload_by_len_bytes={len_total}");
    println!("point_buffer_payload_by_capacity_bytes={capacity_total}");

    println!(
        "point_object_payload_by_len_MiB={:.6}",
        len_total as f64 / (1024.0 * 1024.0)
    );

    println!(
        "point_buffer_payload_by_capacity_MiB={:.6}",
        capacity_total as f64 / (1024.0 * 1024.0)
    );

    println!(
        "vec_header_bytes={} arc_handle_bytes={}",
        size_of::<Vec<G1Affine>>(),
        size_of::<std::sync::Arc<Vec<G1Affine>>>()
    );

    println!(
        "g1_affine_bytes={} g2_affine_bytes={}",
        size_of::<G1Affine>(),
        size_of::<G2Affine>()
    );

    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let paths: Vec<String> = env::args().skip(1).collect();

    if paths.is_empty() {
        eprintln!("Usage: runtime_params_memory <spend.params> [output.params]");
        std::process::exit(2);
    }

    for path in paths {
        report_params(Path::new(&path))?;
    }

    Ok(())
}
