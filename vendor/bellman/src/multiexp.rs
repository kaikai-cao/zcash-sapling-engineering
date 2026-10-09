use super::multicore::{Waiter, Worker};
use bitvec::vec::BitVec;
use ff::{FieldBits, PrimeField, PrimeFieldBits};
use group::prime::{PrimeCurve, PrimeCurveAffine};
use std::io;
use std::iter;
use std::ops::AddAssign;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

static MSM_PROFILE_CALL_ID: AtomicUsize = AtomicUsize::new(0);

#[cfg(feature = "multicore")]
use rayon::prelude::*;

#[cfg(not(feature = "multicore"))]
use crate::multicore::FakeParallelIterator;

use super::SynthesisError;

/// An object that builds a source of bases.
pub trait SourceBuilder<G: PrimeCurveAffine>: Send + Sync + 'static + Clone {
    type Source: Source<G>;

    fn build(self) -> Self::Source;
}

/// A source of bases, like an iterator.
pub trait Source<G: PrimeCurveAffine> {
    fn next(&mut self) -> Result<&G, SynthesisError>;

    /// Skips `amt` elements from the source, avoiding deserialization.
    fn skip(&mut self, amt: usize) -> Result<(), SynthesisError>;
}

pub trait AddAssignFromSource: PrimeCurve {
    /// Parses the element from the source. Fails if the point is at infinity.
    fn add_assign_from_source<S: Source<Self::Affine>>(
        &mut self,
        source: &mut S,
    ) -> Result<(), SynthesisError> {
        AddAssign::<&Self::Affine>::add_assign(self, source.next()?);
        Ok(())
    }
}
impl<G> AddAssignFromSource for G where G: PrimeCurve {}

impl<G: PrimeCurveAffine> SourceBuilder<G> for (Arc<Vec<G>>, usize) {
    type Source = (Arc<Vec<G>>, usize);

    fn build(self) -> (Arc<Vec<G>>, usize) {
        (self.0.clone(), self.1)
    }
}

impl<G: PrimeCurveAffine> Source<G> for (Arc<Vec<G>>, usize) {
    fn next(&mut self) -> Result<&G, SynthesisError> {
        if self.0.len() <= self.1 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "expected more bases from source",
            )
            .into());
        }

        if self.0[self.1].is_identity().into() {
            return Err(SynthesisError::UnexpectedIdentity);
        }

        let ret = &self.0[self.1];
        self.1 += 1;

        Ok(ret)
    }

    fn skip(&mut self, amt: usize) -> Result<(), SynthesisError> {
        if self.0.len() <= self.1 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "expected more bases from source",
            )
            .into());
        }

        self.1 += amt;

        Ok(())
    }
}

pub trait QueryDensity {
    /// Returns whether the base exists.
    type Iter: Iterator<Item = bool>;

    fn iter(self) -> Self::Iter;
    fn get_query_size(self) -> Option<usize>;
}

#[derive(Clone)]
pub struct FullDensity;

impl AsRef<FullDensity> for FullDensity {
    fn as_ref(&self) -> &FullDensity {
        self
    }
}

impl QueryDensity for &FullDensity {
    type Iter = iter::Repeat<bool>;

    fn iter(self) -> Self::Iter {
        iter::repeat(true)
    }

    fn get_query_size(self) -> Option<usize> {
        None
    }
}

pub struct DensityTracker {
    bv: BitVec,
}

impl<'a> QueryDensity for &'a DensityTracker {
    type Iter = Box<dyn 'a + Iterator<Item = bool>>;

    fn iter(self) -> Self::Iter {
        Box::new(self.bv.iter().by_vals())
    }

    fn get_query_size(self) -> Option<usize> {
        Some(self.bv.len())
    }
}

impl Default for DensityTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl DensityTracker {
    pub fn new() -> DensityTracker {
        DensityTracker { bv: BitVec::new() }
    }

    pub fn add_element(&mut self) {
        self.bv.push(false);
    }

    pub fn inc(&mut self, idx: usize) {
        if !self.bv.get(idx).unwrap() {
            self.bv.set(idx, true);
        }
    }

    pub fn get_total_density(&self) -> usize {
        self.bv.count_ones()
    }
}

enum ChunkedExponent {
    Zero,
    One,
    Chunks(Vec<u64>),
}

/// An exponent
pub enum Exponent<F: PrimeFieldBits> {
    Zero,
    One,
    Bits(FieldBits<F::ReprBits>),
}

impl<F: PrimeFieldBits> From<&F> for Exponent<F> {
    fn from(exp: &F) -> Self {
        if exp.is_zero_vartime() {
            Exponent::Zero
        } else if exp == &F::ONE {
            Exponent::One
        } else {
            Exponent::Bits(exp.to_le_bits())
        }
    }
}

impl<F: PrimeFieldBits> From<F> for Exponent<F> {
    fn from(exp: F) -> Self {
        (&exp).into()
    }
}

impl<F: PrimeFieldBits> Exponent<F> {
    fn chunks(&self, c: usize) -> ChunkedExponent {
        match self {
            Self::Zero => ChunkedExponent::Zero,
            Self::One => ChunkedExponent::One,
            Self::Bits(exp) => ChunkedExponent::Chunks(
                exp.chunks(c)
                    .map(|chunk| {
                        chunk
                            .iter()
                            .by_vals()
                            .enumerate()
                            .fold(0u64, |acc, (i, b)| acc + ((b as u64) << i))
                    })
                    .collect(),
            ),
        }
    }
}

struct MsmChunkProfile {
    bucket_alloc_ns: u128,
    bucket_fill_ns: u128,
    bucket_sum_ns: u128,
    point_add_calls: usize,
    base_skip_calls: usize,
}


fn multiexp_inner<Q, D, G, S>(
    bases: S,
    density_map: D,
    exponents: Arc<Vec<Exponent<G::Scalar>>>,
    c: u32,
    profile_call_id: usize,
) -> Result<G, SynthesisError>
where
    for<'a> &'a Q: QueryDensity,
    D: Send + Sync + 'static + Clone + AsRef<Q>,
    G: PrimeCurve,
    G::Scalar: PrimeFieldBits,
    S: SourceBuilder<G::Affine>,
{
    let inner_start = Instant::now();

    // 1. 将每个标量转换成窗口对应的分块。
    let exponent_chunking_start = Instant::now();

    let exponents = Arc::new(
        exponents
            .iter()
            .map(|exp| exp.chunks(c as usize))
            .collect::<Vec<_>>(),
    );

    let exponent_chunking_ns =
        exponent_chunking_start.elapsed().as_nanos();

    // 2. 每个并行任务处理一个标量窗口。
    let this = move |
        bases: S,
        density_map: D,
        exponents: Arc<Vec<ChunkedExponent>>,
        chunk: usize,
    | -> Result<(G, MsmChunkProfile), SynthesisError> {
        let mut acc = G::identity();

        let mut bases = bases.build();

        // 阶段 A：初始化桶。
        let bucket_alloc_start = Instant::now();

        let mut buckets = vec![G::identity(); (1 << c) - 1];

        let bucket_alloc_ns =
            bucket_alloc_start.elapsed().as_nanos();

        let handle_trivial = chunk == 0;

        // 阶段 B：根据当前窗口的标量片段将基点放入桶中。
        let bucket_fill_start = Instant::now();
        let mut point_add_calls = 0usize;
        let mut base_skip_calls = 0usize;

        for (exp, density) in
            exponents.iter().zip(density_map.as_ref().iter())
        {
            if density {
                match exp {
                    ChunkedExponent::Zero => {
                        base_skip_calls += 1;
                        bases.skip(1)?;
                    }
                    ChunkedExponent::One => {
                        if handle_trivial {
                            point_add_calls += 1;
                            acc.add_assign_from_source(&mut bases)?;
                        } else {
                            bases.skip(1)?;
                        }
                    }
                    ChunkedExponent::Chunks(chunks) => {
                        let exp = chunks[chunk];

                        if exp != 0 {
                            point_add_calls += 1;
                            buckets[(exp - 1) as usize]
                                .add_assign_from_source(&mut bases)?;
                        } else {
                            bases.skip(1)?;
                        }
                    }
                }
            }
        }

        let bucket_fill_ns =
            bucket_fill_start.elapsed().as_nanos();

        // 阶段 C：从高桶到低桶，执行分部求和。
        let bucket_sum_start = Instant::now();

        let mut running_sum = G::identity();

        for exp in buckets.into_iter().rev() {
            running_sum.add_assign(&exp);
            acc.add_assign(&running_sum);
        }

        let bucket_sum_ns =
            bucket_sum_start.elapsed().as_nanos();

        Ok((
            acc,
            MsmChunkProfile {
                bucket_alloc_ns,
                bucket_fill_ns,
                bucket_sum_ns,
                point_add_calls,
                base_skip_calls,
            },
        ))
    };

    let parallel_chunks_start = Instant::now();

    let parts = (0..G::Scalar::NUM_BITS)
        .into_par_iter()
        .step_by(c as usize)
        .enumerate()
        .map(|(chunk, _)| {
            this(
                bases.clone(),
                density_map.clone(),
                exponents.clone(),
                chunk,
            )
        })
        .collect::<Vec<Result<(G, MsmChunkProfile), SynthesisError>>>();

    let parallel_chunks_wall_ms =
    parallel_chunks_start.elapsed().as_secs_f64() * 1000.0;

    let part_fold_start = Instant::now();

    // 收集各并行任务的计时结果，同时合并 MSM 的数学结果。
    let mut profiles = Vec::with_capacity(parts.len());

    let result = parts
        .into_iter()
        .rev()
        .try_fold(G::identity(), |acc, part| {
            part.map(|(part, profile)| {
                profiles.push(profile);
                (0..c).fold(acc, |acc, _| acc.double()) + part
            })
        })?;

    let part_fold_ms =
        part_fold_start.elapsed().as_secs_f64() * 1000.0;

    let chunks = profiles.len();

    let alloc_sum: u128 =
        profiles.iter().map(|p| p.bucket_alloc_ns).sum();
    let fill_sum: u128 =
        profiles.iter().map(|p| p.bucket_fill_ns).sum();
    let sum_sum: u128 =
        profiles.iter().map(|p| p.bucket_sum_ns).sum();

    let point_add_calls: usize =
        profiles.iter().map(|p| p.point_add_calls).sum();

    let base_skip_calls: usize =
         profiles.iter().map(|p| p.base_skip_calls).sum();

    let alloc_max = profiles
        .iter()
        .map(|p| p.bucket_alloc_ns)
        .max()
        .unwrap_or(0);

    let fill_max = profiles
        .iter()
        .map(|p| p.bucket_fill_ns)
        .max()
        .unwrap_or(0);

    let sum_max = profiles
        .iter()
        .map(|p| p.bucket_sum_ns)
        .max()
        .unwrap_or(0);

    // 纳秒转换为毫秒。
    let to_ms = |ns: u128| ns as f64 / 1_000_000.0;

    eprintln!(
        "BELLMAN_MSM_STAGE_PROFILE \
call_id={} chunks={} \
exponent_chunking_ms={:.3} \
bucket_alloc_sum_ms={:.3} \
bucket_alloc_max_chunk_ms={:.3} \
bucket_fill_sum_ms={:.3} \
bucket_fill_max_chunk_ms={:.3} \
bucket_sum_sum_ms={:.3} \
bucket_sum_max_chunk_ms={:.3} \
parallel_chunks_wall_ms={:.3} part_fold_ms={:.3}\
inner_elapsed_ms={:.3}",
        profile_call_id,
        chunks,
        to_ms(exponent_chunking_ns),
        to_ms(alloc_sum),
        to_ms(alloc_max),
        to_ms(fill_sum),
        to_ms(fill_max),
        to_ms(sum_sum),
        to_ms(sum_max),
        parallel_chunks_wall_ms,
        part_fold_ms,
        inner_start.elapsed().as_secs_f64() * 1000.0,
    );

    // 新增：输出 MSM 内部操作计数
eprintln!(
    "BELLMAN_MSM_OP_COUNTS call_id={} point_add_calls={} base_skip_calls={}",
    profile_call_id,
    point_add_calls,
    base_skip_calls
);
    Ok(result)
}

/// Perform multi-exponentiation. The caller is responsible for ensuring the
/// query size is the same as the number of exponents.
pub fn multiexp<Q, D, G, S>(
    pool: &Worker,
    bases: S,
    density_map: D,
    exponents: Arc<Vec<Exponent<G::Scalar>>>,
) -> Waiter<Result<G, SynthesisError>>
where
    for<'a> &'a Q: QueryDensity,
    D: Send + Sync + 'static + Clone + AsRef<Q>,
    G: PrimeCurve,
    G::Scalar: PrimeFieldBits,
    S: SourceBuilder<G::Affine>,
{
    let c = if exponents.len() < 32 {
        3u32
    } else {
        (f64::from(exponents.len() as u32)).ln().ceil() as u32
    };

    let exponent_count = exponents.len();
    let density_map_size = density_map.as_ref().get_query_size();

    if let Some(query_size) = density_map_size {
    assert!(query_size == exponent_count);
}

    let profile_call_id =
    MSM_PROFILE_CALL_ID.fetch_add(1, Ordering::Relaxed) + 1;

pool.compute(move || {
    let start = Instant::now();

    let result = multiexp_inner(
    bases,
    density_map,
    exponents,
    c,
    profile_call_id,
);

    eprintln!(
    "BELLMAN_MSM_PROFILE call_id={} exponent_count={} \
density_map_size={:?} window={} elapsed_ms={:.3}",
    profile_call_id,
    exponent_count,
    density_map_size,
    c,
    start.elapsed().as_secs_f64() * 1000.0,
);

    result
})
}

#[cfg(feature = "pairing")]
#[test]
fn test_with_bls12() {
    fn naive_multiexp<G: PrimeCurve>(
        bases: Arc<Vec<G::Affine>>,
        exponents: Arc<Vec<G::Scalar>>,
    ) -> G {
        assert_eq!(bases.len(), exponents.len());

        let mut acc = G::identity();

        for (base, exp) in bases.iter().zip(exponents.iter()) {
            AddAssign::<&G>::add_assign(&mut acc, &(*base * *exp));
        }

        acc
    }

    use bls12_381::{Bls12, Scalar};
    use ff::Field;
    use group::{Curve, Group};
    use pairing::Engine;

    const SAMPLES: usize = 1 << 14;

    let mut rng = rand::rng();
    let v = Arc::new(
        (0..SAMPLES)
            .map(|_| Scalar::random(&mut rng))
            .collect::<Vec<_>>(),
    );
    let v_bits = Arc::new(v.iter().map(|e| e.into()).collect::<Vec<_>>());
    let g = Arc::new(
        (0..SAMPLES)
            .map(|_| <Bls12 as Engine>::G1::random(&mut rng).to_affine())
            .collect::<Vec<_>>(),
    );

    let naive: <Bls12 as Engine>::G1 = naive_multiexp(g.clone(), v);

    let pool = Worker::new();
    let fast = multiexp(&pool, (g, 0), FullDensity, v_bits).wait().unwrap();

    assert_eq!(naive, fast);
}
