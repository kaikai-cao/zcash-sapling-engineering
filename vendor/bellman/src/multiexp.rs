use super::multicore::{Waiter, Worker};
use bitvec::vec::BitVec;
use ff::{FieldBits, PrimeField, PrimeFieldBits};
use group::prime::{PrimeCurve, PrimeCurveAffine};
use std::io;
use std::iter;
use std::ops::AddAssign;
use std::sync::Arc;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

#[cfg(feature = "multicore")]
use rayon::prelude::*;

#[cfg(not(feature = "multicore"))]
use crate::multicore::FakeParallelIterator;

use super::SynthesisError;

// Process-wide sequence number for instrumented multiexp calls.
static MSM_PROFILE_CALL_ID: AtomicUsize = AtomicUsize::new(1);

fn msm_profile_enabled() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_PROFILE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

// Branch counters can be disabled independently of timing instrumentation.
// If the variable is absent, preserve the historical profile=1 behavior.
fn msm_branch_counts_enabled(profile: bool) -> bool {
    profile
        && std::env::var("SAPLING_MSM_BRANCH_COUNTS")
            .map(|value| value == "1")
            .unwrap_or(true)
}

// Keep outer MSM/Groth16 profiling enabled while optionally disabling the
// finer-grained timers inside each multiexp window/chunk.
fn msm_inner_stage_timing_enabled(profile: bool) -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();

    profile
        && *ENABLED.get_or_init(|| {
            std::env::var("SAPLING_MSM_STAGE_TIMING")
                .map(|value| value != "0")
                .unwrap_or(true)
        })
}

#[derive(Default)]
struct MsmStageProfile {
    bucket_init_sum_ns: std::sync::atomic::AtomicU64,
    bucket_init_max_ns: std::sync::atomic::AtomicU64,
    bucket_fill_sum_ns: std::sync::atomic::AtomicU64,
    bucket_fill_max_ns: std::sync::atomic::AtomicU64,
    bucket_reduce_sum_ns: std::sync::atomic::AtomicU64,
    bucket_reduce_max_ns: std::sync::atomic::AtomicU64,
    density_true_slot_visits: AtomicUsize,
    density_false_slot_visits: AtomicUsize,
    zero_exponent_slot_visits: AtomicUsize,
    one_exponent_slot_visits: AtomicUsize,
    chunked_exponent_slot_visits: AtomicUsize,
    zero_window_digit_visits: AtomicUsize,
    nonzero_window_digit_visits: AtomicUsize,
    bucket_base_add_calls: AtomicUsize,
    direct_one_add_calls: AtomicUsize,
    base_skip_calls: AtomicUsize,
    base_skip_elements: AtomicUsize,
    active_chunk_regions: AtomicUsize,
    max_active_chunk_regions: AtomicUsize,
}

struct ActiveBucketRegionGuard {
    profile: Arc<MsmStageProfile>,
}

impl Drop for ActiveBucketRegionGuard {
    fn drop(&mut self) {
        self.profile
            .active_chunk_regions
            .fetch_sub(1, Ordering::Relaxed);
    }
}

fn update_atomic_max(target: &AtomicUsize, value: usize) {
    let mut current = target.load(Ordering::Relaxed);

    while value > current {
        match target.compare_exchange_weak(
            current,
            value,
            Ordering::Relaxed,
            Ordering::Relaxed,
        ) {
            Ok(_) => break,
            Err(observed) => current = observed,
        }
    }
}

fn record_timing(
    sum_ns: &std::sync::atomic::AtomicU64,
    max_ns: &std::sync::atomic::AtomicU64,
    start: Option<Instant>,
) {
    if let Some(start) = start {
        let elapsed_ns = start.elapsed().as_nanos() as u64;
        sum_ns.fetch_add(elapsed_ns, Ordering::Relaxed);

        let mut current = max_ns.load(Ordering::Relaxed);
        while elapsed_ns > current {
            match max_ns.compare_exchange_weak(
                current,
                elapsed_ns,
                Ordering::Relaxed,
                Ordering::Relaxed,
            ) {
                Ok(_) => break,
                Err(observed) => current = observed,
            }
        }
    }
}

fn elapsed_ns(start: Option<Instant>) -> u64 {
    start.map(|value| value.elapsed().as_nanos() as u64).unwrap_or(0)
}

fn ns_to_ms(value: u64) -> f64 {
    value as f64 / 1_000_000.0
}

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

fn multiexp_inner<Q, D, G, S>(
    bases: S,
    density_map: D,
    exponents: Arc<Vec<Exponent<G::Scalar>>>,
    c: u32,
    profile: bool,
    branch_counts: bool,
    stage_timing: bool,
    call_id: Option<usize>,
) -> Result<G, SynthesisError>
where
    for<'a> &'a Q: QueryDensity,
    D: Send + Sync + 'static + Clone + AsRef<Q>,
    G: PrimeCurve,
    G::Scalar: PrimeFieldBits,
    S: SourceBuilder<G::Affine>,
{
    let exponent_count = exponents.len();
    let bucket_count = (1usize << c) - 1;

    // Allocate profiling counters only for diagnostic runs.
    let stage_profile = profile.then(|| Arc::new(MsmStageProfile::default()));
    let worker_stage_profile = stage_profile.clone();

    // Split the exponents into windows and measure this preprocessing step.
    let exponent_chunk_prep_start = stage_timing.then(Instant::now);
    let chunked_exponents = Arc::new(
        exponents
            .iter()
            .map(|exp| exp.chunks(c as usize))
            .collect::<Vec<_>>(),
    );
    let exponent_chunk_prep_ns = elapsed_ns(exponent_chunk_prep_start);

    // Perform one chunk of the multiexponentiation.
    let this = move |bases: S,
                     density_map: D,
                     exponents: Arc<Vec<ChunkedExponent>>,
                     chunk: usize|
          -> Result<G, SynthesisError> {
        let mut acc = G::identity();
        let mut bases = bases.build();

        // Track overlapping chunk regions for this single MSM call. The guard
        // is dropped even if a checked source operation returns an error.
        let _active_bucket_guard = if let Some(profile) = worker_stage_profile.as_ref() {
            let active = profile
                .active_chunk_regions
                .fetch_add(1, Ordering::Relaxed)
                + 1;
            update_atomic_max(&profile.max_active_chunk_regions, active);
            Some(ActiveBucketRegionGuard {
                profile: Arc::clone(profile),
            })
        } else {
            None
        };

        // Allocate the bucket array.
        let bucket_init_start = stage_timing.then(Instant::now);
        let mut buckets = vec![G::identity(); bucket_count];
        if let (Some(stage), Some(start)) =
            (worker_stage_profile.as_ref(), bucket_init_start)
        {
            record_timing(
                &stage.bucket_init_sum_ns,
                &stage.bucket_init_max_ns,
                Some(start),
            );
        }

        // Only the first round handles exponents equal to one directly.
        let handle_trivial = chunk == 0;

        // Sort the bases into buckets. Counters are only updated in diagnostic
        // mode and remain local to a chunk until the timed fill loop finishes.
        let mut density_true_slot_visits = 0usize;
        let mut density_false_slot_visits = 0usize;
        let mut zero_exponent_slot_visits = 0usize;
        let mut one_exponent_slot_visits = 0usize;
        let mut chunked_exponent_slot_visits = 0usize;
        let mut zero_window_digit_visits = 0usize;
        let mut nonzero_window_digit_visits = 0usize;
        let mut bucket_base_add_calls = 0usize;
        let mut direct_one_add_calls = 0usize;
        let mut base_skip_calls = 0usize;
        let mut base_skip_elements = 0usize;

        let bucket_fill_start = stage_timing.then(Instant::now);
        if branch_counts {
            // Diagnostic branch: count source-level operations with local
            // counters. This adds overhead to bucket-fill timing in this batch.
            for (exp, density) in exponents.iter().zip(density_map.as_ref().iter()) {
                if density {
                    density_true_slot_visits += 1;
                    match exp {
                        ChunkedExponent::Zero => {
                            zero_exponent_slot_visits += 1;
                            base_skip_calls += 1;
                            base_skip_elements += 1;
                            bases.skip(1)?;
                        }
                        ChunkedExponent::One => {
                            one_exponent_slot_visits += 1;
                            if handle_trivial {
                                direct_one_add_calls += 1;
                                acc.add_assign_from_source(&mut bases)?;
                            } else {
                                base_skip_calls += 1;
                                base_skip_elements += 1;
                                bases.skip(1)?;
                            }
                        }
                        ChunkedExponent::Chunks(chunks) => {
                            chunked_exponent_slot_visits += 1;
                            let digit = chunks[chunk];

                            if digit != 0 {
                                nonzero_window_digit_visits += 1;
                                bucket_base_add_calls += 1;
                                buckets[(digit - 1) as usize].add_assign_from_source(&mut bases)?;
                            } else {
                                zero_window_digit_visits += 1;
                                base_skip_calls += 1;
                                base_skip_elements += 1;
                                bases.skip(1)?;
                            }
                        }
                    }
                } else {
                    density_false_slot_visits += 1;
                }
            }
        } else {
            // Production path preserves the original loop without branch counters.
            for (exp, density) in exponents.iter().zip(density_map.as_ref().iter()) {
                if density {
                    match exp {
                        ChunkedExponent::Zero => bases.skip(1)?,
                        ChunkedExponent::One => {
                            if handle_trivial {
                                acc.add_assign_from_source(&mut bases)?;
                            } else {
                                bases.skip(1)?;
                            }
                        }
                        ChunkedExponent::Chunks(chunks) => {
                            let exp = chunks[chunk];

                            if exp != 0 {
                                buckets[(exp - 1) as usize].add_assign_from_source(&mut bases)?;
                            } else {
                                bases.skip(1)?;
                            }
                        }
                    }
                }
            }
        }
        if let (Some(stage), Some(start)) =
            (worker_stage_profile.as_ref(), bucket_fill_start)
        {
            record_timing(
                &stage.bucket_fill_sum_ns,
                &stage.bucket_fill_max_ns,
                Some(start),
            );
        }

        if branch_counts {
            if let Some(stage) = worker_stage_profile.as_ref() {
                stage.density_true_slot_visits.fetch_add(density_true_slot_visits, Ordering::Relaxed);
                stage.density_false_slot_visits.fetch_add(density_false_slot_visits, Ordering::Relaxed);
                stage.zero_exponent_slot_visits.fetch_add(zero_exponent_slot_visits, Ordering::Relaxed);
                stage.one_exponent_slot_visits.fetch_add(one_exponent_slot_visits, Ordering::Relaxed);
                stage.chunked_exponent_slot_visits.fetch_add(chunked_exponent_slot_visits, Ordering::Relaxed);
                stage.zero_window_digit_visits.fetch_add(zero_window_digit_visits, Ordering::Relaxed);
                stage.nonzero_window_digit_visits.fetch_add(nonzero_window_digit_visits, Ordering::Relaxed);
                stage.bucket_base_add_calls.fetch_add(bucket_base_add_calls, Ordering::Relaxed);
                stage.direct_one_add_calls.fetch_add(direct_one_add_calls, Ordering::Relaxed);
                stage.base_skip_calls.fetch_add(base_skip_calls, Ordering::Relaxed);
                stage.base_skip_elements.fetch_add(base_skip_elements, Ordering::Relaxed);
            }
        }

        // Summation by parts.
        // e.g. 3a + 2b + 1c = a +
        //                    (a) + b +
        //                    ((a) + b) + c
        let bucket_reduce_start = stage_timing.then(Instant::now);
        let mut running_sum = G::identity();
        for exp in buckets.into_iter().rev() {
            running_sum.add_assign(&exp);
            acc.add_assign(&running_sum);
        }
        if let (Some(stage), Some(start)) =
            (worker_stage_profile.as_ref(), bucket_reduce_start)
        {
            record_timing(
                &stage.bucket_reduce_sum_ns,
                &stage.bucket_reduce_max_ns,
                Some(start),
            );
        }

        Ok(acc)
    };

    // This wall-clock measurement includes parallel scheduling and all chunk work.
    let chunk_parallel_start = stage_timing.then(Instant::now);
    let parts = (0..G::Scalar::NUM_BITS)
        .into_par_iter()
        .step_by(c as usize)
        .enumerate()
        .map(|(chunk, _)| {
            this(
                bases.clone(),
                density_map.clone(),
                chunked_exponents.clone(),
                chunk,
            )
        })
        .collect::<Vec<Result<_, _>>>();
    let chunk_parallel_wall_ns = elapsed_ns(chunk_parallel_start);
    let chunk_count = parts.len();

    // Combine the independent chunk results.
    let result_merge_start = stage_timing.then(Instant::now);
    let final_result = parts
        .into_iter()
        .rev()
        .try_fold(G::identity(), |acc, part| {
            part.map(|part| (0..c).fold(acc, |acc, _| acc.double()) + part)
        });
    let result_merge_ns = elapsed_ns(result_merge_start);

    if let Some(stage) = stage_profile.as_ref() {
        let max_concurrent_chunk_regions = stage
            .max_active_chunk_regions
            .load(Ordering::Relaxed);
        let bucket_element_size_bytes = std::mem::size_of::<G>();
        let bucket_payload_at_max_concurrency_estimate_bytes =
            max_concurrent_chunk_regions * bucket_count * bucket_element_size_bytes;

        eprintln!(
            "BELLMAN_MSM_STAGE_PROFILE call_id={} exponent_count={} window={} bucket_count={} chunk_count={} bucket_element_size_bytes={} exponent_chunk_prep_ms={:.3} chunk_parallel_wall_ms={:.3} bucket_init_sum_ms={:.3} bucket_init_max_ms={:.3} bucket_fill_sum_ms={:.3} bucket_fill_max_ms={:.3} bucket_reduce_sum_ms={:.3} bucket_reduce_max_ms={:.3} max_concurrent_chunk_regions={} bucket_payload_at_max_concurrency_estimate_bytes={} result_merge_ms={:.3}",
            call_id.unwrap_or(0),
            exponent_count,
            c,
            bucket_count,
            chunk_count,
            bucket_element_size_bytes,
            ns_to_ms(exponent_chunk_prep_ns),
            ns_to_ms(chunk_parallel_wall_ns),
            ns_to_ms(stage.bucket_init_sum_ns.load(Ordering::Relaxed)),
            ns_to_ms(stage.bucket_init_max_ns.load(Ordering::Relaxed)),
            ns_to_ms(stage.bucket_fill_sum_ns.load(Ordering::Relaxed)),
            ns_to_ms(stage.bucket_fill_max_ns.load(Ordering::Relaxed)),
            ns_to_ms(stage.bucket_reduce_sum_ns.load(Ordering::Relaxed)),
            ns_to_ms(stage.bucket_reduce_max_ns.load(Ordering::Relaxed)),
            max_concurrent_chunk_regions,
            bucket_payload_at_max_concurrency_estimate_bytes,
            ns_to_ms(result_merge_ns),
        );

        if branch_counts {
            eprintln!(
                "BELLMAN_MSM_BRANCH_PROFILE call_id={} density_true_slot_visits={} density_false_slot_visits={} zero_exponent_slot_visits={} one_exponent_slot_visits={} chunked_exponent_slot_visits={} zero_window_digit_visits={} nonzero_window_digit_visits={} bucket_base_add_calls={} direct_one_add_calls={} base_skip_calls={} base_skip_elements={}",
                call_id.unwrap_or(0),
                stage.density_true_slot_visits.load(Ordering::Relaxed),
                stage.density_false_slot_visits.load(Ordering::Relaxed),
                stage.zero_exponent_slot_visits.load(Ordering::Relaxed),
                stage.one_exponent_slot_visits.load(Ordering::Relaxed),
                stage.chunked_exponent_slot_visits.load(Ordering::Relaxed),
                stage.zero_window_digit_visits.load(Ordering::Relaxed),
                stage.nonzero_window_digit_visits.load(Ordering::Relaxed),
                stage.bucket_base_add_calls.load(Ordering::Relaxed),
                stage.direct_one_add_calls.load(Ordering::Relaxed),
                stage.base_skip_calls.load(Ordering::Relaxed),
                stage.base_skip_elements.load(Ordering::Relaxed),
            );
        }
    }

    final_result
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

    if let Some(query_size) = density_map.as_ref().get_query_size() {
        // If the density map has a known query size, it should not be
        // inconsistent with the number of exponents.

        assert!(query_size == exponents.len());
    }

    let profile = msm_profile_enabled();
    let branch_counts = msm_branch_counts_enabled(profile);
    let stage_timing = msm_inner_stage_timing_enabled(profile);
    let call_id = if profile {
        Some(MSM_PROFILE_CALL_ID.fetch_add(1, Ordering::Relaxed))
    } else {
        None
    };

    let exponent_count = exponents.len();
    let density_map_size = if profile {
        density_map.as_ref().get_query_size()
    } else {
        None
    };
    let window = c;

    let submitted_at = profile.then(Instant::now);
    let submit_start = profile.then(Instant::now);

    let waiter = pool.compute(move || {
        let task_start_delay_ms = submitted_at.map(|t| t.elapsed().as_secs_f64() * 1000.0);
        let start = profile.then(Instant::now);
        let result = multiexp_inner(
            bases, density_map, exponents, c, profile, branch_counts, stage_timing, call_id,
        );

        if let (Some(call_id), Some(task_start_delay_ms), Some(start)) =
            (call_id, task_start_delay_ms, start)
        {
            let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;

            eprintln!(
                "BELLMAN_MSM_PROFILE call_id={} exponent_count={} density_map_size={:?} window={} task_start_delay_ms={:.3} elapsed_ms={:.3}",
                call_id,
                exponent_count,
                density_map_size,
                window,
                task_start_delay_ms,
                elapsed_ms,
            );
        }

        result
    });

    if let (Some(call_id), Some(submit_start)) = (call_id, submit_start) {
        let submit_elapsed_ms = submit_start.elapsed().as_secs_f64() * 1000.0;

        eprintln!(
            "BELLMAN_MSM_SUBMIT_PROFILE call_id={} submit_elapsed_ms={:.3}",
            call_id, submit_elapsed_ms,
        );
    }

    waiter
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
