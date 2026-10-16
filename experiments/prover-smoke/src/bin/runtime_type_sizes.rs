use bellman::multiexp::Exponent;
use bls12_381::{
    G1Affine,
    G1Projective,
    G2Affine,
    G2Projective,
    Scalar,
};
use std::mem::{align_of, size_of};
use std::sync::Arc;

fn report<T>(name: &str) {
    println!(
        "{:<32} size={:>4} bytes, align={:>2} bytes",
        name,
        size_of::<T>(),
        align_of::<T>(),
    );
}

fn main() {
    println!("===== Elliptic Curve Runtime Types =====");

    // 椭圆曲线点：仿射坐标表示。
    report::<G1Affine>("G1Affine");
    report::<G2Affine>("G2Affine");

    // MSM 桶累加使用的群元素：投影坐标表示。
    report::<G1Projective>("G1Projective");
    report::<G2Projective>("G2Projective");

    // 标量及 Bellman 的指数表示。
    report::<Scalar>("Scalar");
    report::<Exponent<Scalar>>("Exponent<Scalar>");

    println!("\n===== Container Headers =====");

    // 这里只测容器本身，不包含容器指向的数据。
    report::<Vec<G1Affine>>("Vec<G1Affine> header");
    report::<Vec<G2Affine>>("Vec<G2Affine> header");
    report::<Vec<G1Projective>>("Vec<G1Projective> header");
    report::<Vec<G2Projective>>("Vec<G2Projective> header");
    report::<Vec<Scalar>>("Vec<Scalar> header");
    report::<Vec<Exponent<Scalar>>>("Vec<Exponent<Scalar>> header");

    report::<Arc<Vec<G1Affine>>>("Arc<Vec<G1Affine>> handle");
    report::<Arc<Vec<G2Affine>>>("Arc<Vec<G2Affine>> handle");
}