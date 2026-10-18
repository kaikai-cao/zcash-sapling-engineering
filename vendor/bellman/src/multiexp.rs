use super::multicore::{Waiter, Worker};
use bitvec::field::BitField;
use bitvec::vec::BitVec;
use ff::{BitViewSized, FieldBits, PrimeField, PrimeFieldBits};
use group::prime::{PrimeCurve, PrimeCurveAffine};
use std::io;
use std::iter;
use std::ops::{AddAssign, SubAssign};
use std::sync::Arc;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicI32, AtomicUsize, Ordering};
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

// Allocation tracking is independent of timing profiling. A diagnostic harness
// installs a tracking global allocator and enables `SAPLING_MEM_PROBE=1`; the
// MSM path then reports real live-byte deltas for exponent preparation and
// bucket-array allocation.
fn msm_mem_probe_enabled() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_MEM_PROBE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

// Experimental/optimization knob: override the Pippenger window width `c` that
// `multiexp` normally derives from the exponent count as `ceil(ln n)`.
//
// Why this exists: the archived stage profile for the Spend H-query MSM
// (n = 131,071 -> c = 12, 4,095 buckets, 22 chunks) attributes ~94% of the call
// to `bucket_fill`, i.e. the loop that repeatedly adds one base into a
// pseudo-random bucket. That loop's cost is set by both the number of chunk
// passes (`n * ceil(255/c)`) and the bucket array's cache footprint
// (`(2^c - 1) * 144 B`). The textbook `c = ln n` optimum assumes uniform memory
// cost, so it is worth measuring rather than assuming on this host.
//
// `SAPLING_MSM_WINDOW_C` is read once (values outside 1..=24 are ignored), and
// `set_msm_window_c` exposes the same knob to benchmark binaries. With no
// override the code below is bit-for-bit the previous behavior.
const MSM_WINDOW_C_UNSET: i32 = i32::MIN;
static MSM_WINDOW_C_OVERRIDE: AtomicI32 = AtomicI32::new(MSM_WINDOW_C_UNSET);

fn msm_window_c_override() -> Option<u32> {
    let mut value = MSM_WINDOW_C_OVERRIDE.load(Ordering::Relaxed);
    if value == MSM_WINDOW_C_UNSET {
        let parsed = std::env::var("SAPLING_MSM_WINDOW_C")
            .ok()
            .and_then(|raw| raw.trim().parse::<u32>().ok())
            .filter(|c| (1..=24).contains(c))
            .map(|c| c as i32)
            .unwrap_or(-1);
        let _ = MSM_WINDOW_C_OVERRIDE.compare_exchange(
            MSM_WINDOW_C_UNSET,
            parsed,
            Ordering::Relaxed,
            Ordering::Relaxed,
        );
        value = MSM_WINDOW_C_OVERRIDE.load(Ordering::Relaxed);
    }

    if value < 0 {
        None
    } else {
        Some(value as u32)
    }
}

/// Programmatic counterpart of `SAPLING_MSM_WINDOW_C` for benchmark binaries.
/// `None` restores the built-in `ceil(ln n)` rule. Out-of-range values are
/// treated as "no override".
pub fn set_msm_window_c(c: Option<u32>) {
    let value = match c {
        Some(value) if (1..=24).contains(&value) => value as i32,
        _ => -1,
    };
    MSM_WINDOW_C_OVERRIDE.store(value, Ordering::Relaxed);
}

// Signed ("balanced") window recoding for the Pippenger bucket fill.
//
// Why: the archived stage profile pinpoints `bucket_fill` at ~94% of the Spend
// H-query MSM, and a micro-benchmark shows the cost is ~470 ns per mixed
// addition regardless of the bucket array size -- i.e. it is arithmetic-bound
// (bls12_381's mixed add is 11 `Fp` multiplications), not memory-bound. The
// only lever left is the *number* of group operations:
//
//     total group ops = windows(c) * (n + 2 * buckets(c))
//
// where `windows(c)` are the chunk passes and `buckets(c)` the bucket array
// length. Unsigned `c`-bit digits need `2^c - 1` buckets, and `ceil(ln n)` is
// already close to optimal, so a pure `c` retune buys at most ~3.7%. Balanced
// signed digits in
// `[-2^(c-1), 2^(c-1)]` halve the bucket count needed at the same width, so one
// extra bit per window becomes affordable at the *same* bucket array size --
// which matters, because the measured per-add cost rises once the array leaves
// the ~590 KB regime.
//
// Enabled by default; `SAPLING_MSM_SIGNED_DIGITS=0` restores the previous
// unsigned recoding bit-for-bit (that is the A/B switch, and it is also how the
// frozen baseline stays reproducible). `set_msm_signed_digits` exposes the same
// knob to benchmark binaries.
const MSM_SIGNED_DIGITS_DEFAULT: i32 = 1;
static MSM_SIGNED_DIGITS_OVERRIDE: AtomicI32 = AtomicI32::new(i32::MIN);

fn msm_signed_digits_enabled() -> bool {
    let mut value = MSM_SIGNED_DIGITS_OVERRIDE.load(Ordering::Relaxed);
    if value < 0 {
        let parsed = match std::env::var("SAPLING_MSM_SIGNED_DIGITS") {
            Ok(raw) => match raw.trim() {
                "0" | "false" | "off" | "no" => 0,
                _ => 1,
            },
            Err(_) => MSM_SIGNED_DIGITS_DEFAULT,
        };
        let _ = MSM_SIGNED_DIGITS_OVERRIDE.compare_exchange(
            i32::MIN,
            parsed,
            Ordering::Relaxed,
            Ordering::Relaxed,
        );
        value = MSM_SIGNED_DIGITS_OVERRIDE.load(Ordering::Relaxed);
    }

    value != 0
}

/// Programmatic counterpart of `SAPLING_MSM_SIGNED_DIGITS` for benchmarks.
pub fn set_msm_signed_digits(enabled: bool) {
    MSM_SIGNED_DIGITS_OVERRIDE.store(if enabled { 1 } else { 0 }, Ordering::Relaxed);
}

// Whether the balanced-signed recoding is *materialised* as a
// `Vec<ChunkedExponent>` (the historical shape) or only its **carry bits** are
// precomputed and each window's digit is folded inside the fill loop.
//
// The materialised representation costs `n * size_of::<ChunkedExponent>()` for
// the outer vector plus `n * windows * 8 B` for the digit vectors. For the
// Spend H query (`n = 131,071`, `c = 13`, 20 windows) that is 3,145,704 B +
// 20,971,360 B = 24.1 MB, and it is the single largest allocation of the
// prove phase. The carry chain is a pure function of the scalar's bits, so the
// digits can be recomputed on demand; only the carry (one bit per window per
// exponent, ~0.33 MB) has to be shared, because the fill runs one task per
// window and those tasks execute concurrently, out of order.
//
// `SAPLING_MSM_LAZY_RECODING=1` selects the carry-bit variant. The default
// stays `0` (materialised) until the pre-registered measurement decides.
const MSM_LAZY_RECODING_DEFAULT: i32 = 0;
static MSM_LAZY_RECODING_OVERRIDE: AtomicI32 = AtomicI32::new(i32::MIN);

fn msm_lazy_recoding_enabled() -> bool {
    let mut value = MSM_LAZY_RECODING_OVERRIDE.load(Ordering::Relaxed);
    if value < 0 {
        let parsed = match std::env::var("SAPLING_MSM_LAZY_RECODING") {
            Ok(raw) => match raw.trim() {
                "1" | "true" | "on" | "yes" => 1,
                _ => 0,
            },
            Err(_) => MSM_LAZY_RECODING_DEFAULT,
        };
        let _ = MSM_LAZY_RECODING_OVERRIDE.compare_exchange(
            i32::MIN,
            parsed,
            Ordering::Relaxed,
            Ordering::Relaxed,
        );
        value = MSM_LAZY_RECODING_OVERRIDE.load(Ordering::Relaxed);
    }

    value != 0
}

/// Programmatic counterpart of `SAPLING_MSM_LAZY_RECODING` for benchmarks.
pub fn set_msm_lazy_recoding(enabled: bool) {
    MSM_LAZY_RECODING_OVERRIDE.store(if enabled { 1 } else { 0 }, Ordering::Relaxed);
}

/// Reads the `c`-bit window `window` of a little-endian bit representation.
///
/// `BitArray` is word aligned and `BitField::load_le` only walks the live head /
/// body / tail words of the requested range, so this is O(1) rather than O(c).
/// The final window may run past the end of the representation (`c` divides
/// `bits` and the dispatch adds one carry window); the range is clamped, and
/// the missing high bits are zero, which is exactly what the materialised
/// recoding produces for that window.
#[inline(always)]
fn window_bits<B: BitViewSized>(bits: &FieldBits<B>, c: usize, window: usize) -> u64 {
    let lo = c * window;
    let hi = (lo + c).min(bits.len());
    bits[lo..hi].load_le::<u64>()
}

/// Folds a raw `c`-bit window plus its incoming carry into the biased slot.
///
/// Identical arithmetic to `Exponent::chunks_signed`; kept as a free function so
/// the fill loop and the recoding cannot drift apart.
#[inline(always)]
fn signed_slot(window: u64, carry: u64, half: u64, modulus: u64) -> u64 {
    let value = window + carry;
    if value > half {
        value.wrapping_sub(modulus).wrapping_add(half)
    } else {
        value + half
    }
}

/// The balanced recoding input of one MSM call: either the materialised digits,
/// or the shared carry bits that let the fill fold them itself.
#[derive(Clone)]
enum Recoding {
    Materialized(Arc<Vec<ChunkedExponent>>),
    /// Bit `window * n + exponent` is the carry into that window. `Zero` and
    /// `One` exponents never carry (their raw windows are 0 and 1), so their
    /// bits stay clear.
    CarryBits(Arc<Vec<u64>>),
}

/// Walks the balanced-recoding carry chain once per exponent and records only
/// *where* a carry occurs, packed window-major as bit `window * n + exponent`.
///
/// Window-major packing is what makes the lazy fill cheap: the tasks that read
/// one window walk a contiguous bit range. `Zero` / `One` exponents have an
/// all-zero carry chain and are skipped, which is why the fill's 0/1 shortcut
/// needs no extra bookkeeping.
fn build_carry_bits<F: PrimeFieldBits>(
    exponents: &[Exponent<F>],
    c: usize,
    windows: usize,
) -> Vec<u64> {
    let n = exponents.len();
    let mut out = vec![0u64; (n * windows).div_ceil(64)];
    let half = 1u64 << (c - 1);

    for (index, exp) in exponents.iter().enumerate() {
        if let Exponent::Bits(bits) = exp {
            let mut carry = 0u64;
            for window in 0..windows {
                if carry == 1 {
                    let at = window * n + index;
                    out[at >> 6] |= 1u64 << (at & 63);
                }
                carry = u64::from(window_bits(bits, c, window) + carry > half);
            }
        }
    }

    out
}

/// Resolves one exponent's contribution under the active recoding.
///
/// Returns `(is_zero, is_one, slot)`. `slot` is only meaningful when neither
/// flag is set, and equals exactly the biased value the materialised recoding
/// would have stored — `signed_slot` is the same arithmetic `chunks_signed`
/// uses, so the two representations cannot drift apart.
#[inline(always)]
#[allow(clippy::too_many_arguments)]
fn resolve_slot<F: PrimeFieldBits>(
    recoding: &Recoding,
    source: &[Exponent<F>],
    index: usize,
    chunk: usize,
    c: usize,
    exponent_count: usize,
    half: u64,
    modulus: u64,
) -> (bool, bool, u64) {
    match recoding {
        Recoding::Materialized(chunked) => match &chunked[index] {
            ChunkedExponent::Zero => (true, false, 0),
            ChunkedExponent::One => (false, true, 0),
            ChunkedExponent::Chunks(chunks) => (false, false, chunks[chunk]),
        },
        // Reached only when the recoding is signed (the switch requires it).
        Recoding::CarryBits(carry) => match &source[index] {
            Exponent::Zero => (true, false, 0),
            Exponent::One => (false, true, 0),
            Exponent::Bits(bits) => {
                let raw = window_bits(bits, c, chunk);
                let at = chunk * exponent_count + index;
                let carry_bit = (carry[at >> 6] >> (at & 63)) & 1;
                (false, false, signed_slot(raw, carry_bit, half, modulus))
            }
        },
    }
}

/// Number of balanced-signed digits per scalar (`c` bits per window).
///
/// This is one larger than the unsigned `ceil(bits / c)` count of the
/// historical dispatch. The balanced recoding carries into the window above the
/// most significant digit, and that carry can be non-zero whenever `c` divides
/// `bits` (the final window then holds `c` significant bits and can exceed
/// `2^(c-1)`). Allocating `bits / c + 1` windows absorbs it unconditionally; the
/// extra window is a zero digit whenever the carry does not materialise.
fn signed_window_count(bits: usize, c: u32) -> usize {
    bits / c as usize + 1
}

/// Picks the window width that minimises the total number of group operations
/// for the balanced-signed recoding, i.e.
/// `(bits/c + 1) * (n + 2 * 2^(c-1))` (one bucket add per exponent per window
/// plus two additions per bucket per window during the reduce).
fn best_signed_window(bits: usize, exponent_count: usize) -> u32 {
    let mut best_c = 3u32;
    let mut best_ops = usize::MAX;
    for c in 2..=20u32 {
        let ops = signed_window_count(bits, c) * (exponent_count + 2 * (1usize << (c - 1)));
        if ops < best_ops {
            best_ops = ops;
            best_c = c;
        }
    }
    best_c
}

struct MsmMemProbe {
    bucket_alloc_max_bytes: AtomicUsize,
    // Directly measured exponent-shape census (replaces the earlier density
    // figure that was inferred from the allocated byte count).
    zero_exponents: AtomicUsize,
    one_exponents: AtomicUsize,
    chunked_exponents: AtomicUsize,
    nonzero_chunk_slots: AtomicUsize,
    zero_chunk_slots: AtomicUsize,
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

/// Timestamp shared by Bellman MSM and Groth16 timeline events.
/// The origin is initialized once per process and uses a monotonic clock.
pub fn profile_timestamp_ns() -> u128 {
    static PROFILE_TIMELINE_ORIGIN: OnceLock<Instant> = OnceLock::new();

    PROFILE_TIMELINE_ORIGIN
        .get_or_init(Instant::now)
        .elapsed()
        .as_nanos()
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

    /// Subtracts the element parsed from the source, i.e. `self -= source.next()`.
    /// Used by the signed-digit bucket fill, where roughly half of the window
    /// digits are negative. `Sub`/`SubAssign` against an affine point is a
    /// mixed addition of the negated point, so it costs the same as
    /// `add_assign_from_source`.
    fn sub_assign_from_source<S: Source<Self::Affine>>(
        &mut self,
        source: &mut S,
    ) -> Result<(), SynthesisError> {
        SubAssign::<&Self::Affine>::sub_assign(self, source.next()?);
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

    /// Balanced (signed) window recoding.
    ///
    /// Produces digits `d_i in [-2^(c-1), 2^(c-1)]` such that
    /// `value == sum_i d_i * 2^(c*i)` exactly, where each digit is stored
    /// *biased* by `+2^(c-1)` so the slot type stays `u64`:
    ///
    /// * `slot == 2^(c-1)`      -> zero digit (skip the base),
    /// * `slot >  2^(c-1)`      -> `d = slot - 2^(c-1) > 0`, add the base,
    /// * `slot <  2^(c-1)`      -> `d = slot - 2^(c-1) < 0`, subtract the base.
    ///
    /// The bucket used is always `|d| - 1`, so `2^(c-1)` buckets suffice
    /// instead of the unsigned `2^c - 1`. The representation is exact within
    /// `bits / c + 1` windows: the final carry is absorbed by the extra window
    /// even when `c` divides `bits` (see `signed_window_count`).
    fn chunks_signed(&self, c: usize) -> ChunkedExponent {
        match self {
            Self::Zero => ChunkedExponent::Zero,
            Self::One => ChunkedExponent::One,
            Self::Bits(exp) => {
                let half = 1u64 << (c - 1);
                let modulus = 1u64 << c;
                let windows = signed_window_count(F::NUM_BITS as usize, c as u32);
                let mut digits = Vec::with_capacity(windows);
                let mut carry = 0u64;

                for chunk in exp.chunks(c) {
                    let mut window = carry;
                    for (i, bit) in chunk.iter().by_vals().enumerate() {
                        if bit {
                            window += 1u64 << i;
                        }
                    }
                    // window in [0, 2^c]; a value above half is represented as
                    // the negative digit and carries one into the next window.
                    if window > half {
                        // Two's-complement slot: `window - modulus` is the
                        // negative digit, `+ half` biases it into `[1, 2^c]`.
                        digits.push(window.wrapping_sub(modulus).wrapping_add(half));
                        carry = 1;
                    } else {
                        digits.push(window + half);
                        carry = 0;
                    }
                }

                // The dispatch indexes exactly `windows` slots, so normalise the
                // length: trailing digits hold no significant bits (the carry is
                // provably zero here), and a short vector is padded with zero
                // digits.
                debug_assert!(
                    digits[windows.min(digits.len())..]
                        .iter()
                        .all(|slot| *slot == half),
                    "signed recoding dropped a non-zero window"
                );
                debug_assert_eq!(carry, 0, "signed recoding carry escaped the scalar");
                digits.truncate(windows);
                digits.resize(windows, half);

                ChunkedExponent::Chunks(digits)
            }
        }
    }
}

fn multiexp_inner<Q, D, G, S>(
    bases: S,
    density_map: D,
    exponents: Arc<Vec<Exponent<G::Scalar>>>,
    c: u32,
    signed: bool,
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
    // Balanced-signed digits in `[-2^(c-1), 2^(c-1)]` are stored biased by
    // `+2^(c-1)` and indexed by `|d| - 1`, so only `2^(c-1)` buckets are needed;
    // the unsigned `c`-bit path keeps `2^c - 1` buckets.
    let bucket_count = if signed {
        1usize << (c - 1)
    } else {
        (1usize << c) - 1
    };
    // A signed zero digit is stored as the bias itself. In the unsigned path a
    // zero digit is literally zero, so one marker covers both.
    let zero_digit_slot = if signed { 1u64 << (c - 1) } else { 0 };

    // Allocate profiling counters only for diagnostic runs.
    let stage_profile = profile.then(|| Arc::new(MsmStageProfile::default()));
    let worker_stage_profile = stage_profile.clone();

    // Optional allocation-tracking counters for the memory ledger.
    let mem_probe = msm_mem_probe_enabled().then(|| {
        Arc::new(MsmMemProbe {
            bucket_alloc_max_bytes: AtomicUsize::new(0),
            zero_exponents: AtomicUsize::new(0),
            one_exponents: AtomicUsize::new(0),
            chunked_exponents: AtomicUsize::new(0),
            nonzero_chunk_slots: AtomicUsize::new(0),
            zero_chunk_slots: AtomicUsize::new(0),
        })
    });
    let worker_mem_probe = mem_probe.clone();
    let mem_live_start = mem_probe.as_ref().map(|_| crate::mem_probe::live());

    // Split the exponents into windows and measure this preprocessing step.
    //
    // When the memory probe is active we also take a census of the exponent
    // shapes (Zero / One / Chunks) and of the non-zero chunk slots inside the
    // chunked exponents. That turns the previously *inferred* density figure
    // into a directly measured one. The census is off in normal runs.
    // Number of windows drives both the dispatch and the carry-bit layout.
    let window_count = if signed {
        signed_window_count(G::Scalar::NUM_BITS as usize, c)
    } else {
        // Same count as the historical `(0..NUM_BITS).step_by(c)` dispatch.
        (G::Scalar::NUM_BITS as usize + c as usize - 1) / c as usize
    };

    let exponent_chunk_prep_start = stage_timing.then(Instant::now);
    // The carry-bit variant only applies to the signed path, and the slot
    // arithmetic needs the raw window to fit a u64.
    let lazy_recoding = msm_lazy_recoding_enabled() && signed && c <= 63;
    let carry_bits = if lazy_recoding {
        Some(Arc::new(build_carry_bits(&exponents, c as usize, window_count)))
    } else {
        None
    };
    let chunked_exponents = if lazy_recoding {
        // The digit vectors are deliberately not built here. The exponent-shape
        // census stays meaningful (it counts the source exponents, not the
        // recoding), so keep recording it when the probe is on; the chunk-slot
        // counters do not apply and are left at zero.
        if let Some(probe) = mem_probe.as_ref() {
            let mut zero_exponents = 0usize;
            let mut one_exponents = 0usize;
            let mut chunked_exponents = 0usize;
            for exp in exponents.iter() {
                match exp {
                    Exponent::Zero => zero_exponents += 1,
                    Exponent::One => one_exponents += 1,
                    Exponent::Bits(_) => chunked_exponents += 1,
                }
            }
            probe.zero_exponents.store(zero_exponents, Ordering::Relaxed);
            probe.one_exponents.store(one_exponents, Ordering::Relaxed);
            probe.chunked_exponents.store(chunked_exponents, Ordering::Relaxed);
        }
        Arc::new(Vec::new())
    } else if let Some(probe) = mem_probe.as_ref() {
        let mut zero_exponents = 0usize;
        let mut one_exponents = 0usize;
        let mut chunked_exponents = 0usize;
        let mut nonzero_chunk_slots = 0usize;
        let mut zero_chunk_slots = 0usize;

        let built = exponents
            .iter()
            .map(|exp| {
                let chunked = if signed {
                    exp.chunks_signed(c as usize)
                } else {
                    exp.chunks(c as usize)
                };

                match &chunked {
                    ChunkedExponent::Zero => zero_exponents += 1,
                    ChunkedExponent::One => one_exponents += 1,
                    ChunkedExponent::Chunks(chunks) => {
                        chunked_exponents += 1;

                        for chunk in chunks {
                            if *chunk == zero_digit_slot {
                                zero_chunk_slots += 1;
                            } else {
                                nonzero_chunk_slots += 1;
                            }
                        }
                    }
                }

                chunked
            })
            .collect::<Vec<_>>();

        probe.zero_exponents.store(zero_exponents, Ordering::Relaxed);
        probe.one_exponents.store(one_exponents, Ordering::Relaxed);
        probe
            .chunked_exponents
            .store(chunked_exponents, Ordering::Relaxed);
        probe
            .nonzero_chunk_slots
            .store(nonzero_chunk_slots, Ordering::Relaxed);
        probe
            .zero_chunk_slots
            .store(zero_chunk_slots, Ordering::Relaxed);

        Arc::new(built)
    } else {
        Arc::new(
            exponents
                .iter()
                .map(|exp| {
                    if signed {
                        exp.chunks_signed(c as usize)
                    } else {
                        exp.chunks(c as usize)
                    }
                })
                .collect::<Vec<_>>(),
        )
    };
    let exponent_chunk_prep_ns = elapsed_ns(exponent_chunk_prep_start);

    let mem_live_after_exponent_prep = mem_probe.as_ref().map(|_| crate::mem_probe::live());

    // Perform one chunk of the multiexponentiation.
    let this = move |bases: S,
                     density_map: D,
                     source: Arc<Vec<Exponent<G::Scalar>>>,
                     recoding: Recoding,
                     chunk: usize|
          -> Result<G, SynthesisError> {
        let mut acc = G::identity();
        let mut bases = bases.build();
        // Fold parameters for the carry-bit recoding (unused when the digits are
        // materialised, where the slot is read straight from the vector).
        let half: u64 = 1u64 << (c - 1);
        let modulus: u64 = 1u64 << c;

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
        let mem_before_bucket = worker_mem_probe
            .as_ref()
            .map(|_| crate::mem_probe::live());
        let mut buckets = vec![G::identity(); bucket_count];
        if let Some(probe) = worker_mem_probe.as_ref() {
            if let Some(before) = mem_before_bucket {
                let delta = crate::mem_probe::live().saturating_sub(before);
                update_atomic_max(&probe.bucket_alloc_max_bytes, delta);
            }
        }
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
            //
            // The density map is *not* truncated by its own length: `FullDensity`
            // yields `iter::repeat(true)`, so the original `exponents.iter().zip(..)`
            // was what bounded the loop. Take the exponent count explicitly.
            for (index, density) in density_map
                .as_ref()
                .iter()
                .enumerate()
                .take(exponent_count)
            {
                if density {
                    density_true_slot_visits += 1;
                    let (is_zero, is_one, digit) = resolve_slot(
                        &recoding,
                        &source,
                        index,
                        chunk,
                        c as usize,
                        exponent_count,
                        half,
                        modulus,
                    );
                    if is_zero {
                        zero_exponent_slot_visits += 1;
                        base_skip_calls += 1;
                        base_skip_elements += 1;
                        bases.skip(1)?;
                    } else if is_one {
                        one_exponent_slot_visits += 1;
                        if handle_trivial {
                            direct_one_add_calls += 1;
                            acc.add_assign_from_source(&mut bases)?;
                        } else {
                            base_skip_calls += 1;
                            base_skip_elements += 1;
                            bases.skip(1)?;
                        }
                    } else {
                        chunked_exponent_slot_visits += 1;
                        if digit == zero_digit_slot {
                            zero_window_digit_visits += 1;
                            base_skip_calls += 1;
                            base_skip_elements += 1;
                            bases.skip(1)?;
                        } else {
                            nonzero_window_digit_visits += 1;
                            bucket_base_add_calls += 1;
                            if signed {
                                if digit > zero_digit_slot {
                                    buckets[(digit - zero_digit_slot - 1) as usize]
                                        .add_assign_from_source(&mut bases)?;
                                } else {
                                    buckets[(zero_digit_slot - digit - 1) as usize]
                                        .sub_assign_from_source(&mut bases)?;
                                }
                            } else {
                                buckets[(digit - 1) as usize]
                                    .add_assign_from_source(&mut bases)?;
                            }
                        }
                    }
                } else {
                    density_false_slot_visits += 1;
                }
            }
        } else {
            // Production path preserves the original loop without branch counters.
            // Bounded by the exponent count, not by the density map: see above.
            for (index, density) in density_map
                .as_ref()
                .iter()
                .enumerate()
                .take(exponent_count)
            {
                if density {
                    let (is_zero, is_one, digit) = resolve_slot(
                        &recoding,
                        &source,
                        index,
                        chunk,
                        c as usize,
                        exponent_count,
                        half,
                        modulus,
                    );
                    if is_zero {
                        bases.skip(1)?;
                    } else if is_one {
                        if handle_trivial {
                            acc.add_assign_from_source(&mut bases)?;
                        } else {
                            bases.skip(1)?;
                        }
                    } else if digit == zero_digit_slot {
                        bases.skip(1)?;
                    } else if !signed {
                        buckets[(digit - 1) as usize].add_assign_from_source(&mut bases)?;
                    } else if digit > zero_digit_slot {
                        buckets[(digit - zero_digit_slot - 1) as usize]
                            .add_assign_from_source(&mut bases)?;
                    } else {
                        buckets[(zero_digit_slot - digit - 1) as usize]
                            .sub_assign_from_source(&mut bases)?;
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
    // The fill resolves each window's digit through `Recoding`. The carry-bit
    // variant shares the source exponents and a ~0.33 MB carry array instead of
    // the 24.1 MB materialised digits.
    let recoding = match carry_bits.as_ref() {
        Some(bits) => Recoding::CarryBits(Arc::clone(bits)),
        None => Recoding::Materialized(Arc::clone(&chunked_exponents)),
    };
    let parts = (0..window_count as u32)
        .into_par_iter()
        .map(|chunk| {
            this(
                bases.clone(),
                density_map.clone(),
                exponents.clone(),
                recoding.clone(),
                chunk as usize,
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
            "BELLMAN_MSM_STAGE_PROFILE call_id={} exponent_count={} window={} signed={} bucket_count={} chunk_count={} bucket_element_size_bytes={} exponent_chunk_prep_ms={:.3} chunk_parallel_wall_ms={:.3} bucket_init_sum_ms={:.3} bucket_init_max_ms={:.3} bucket_fill_sum_ms={:.3} bucket_fill_max_ms={:.3} bucket_reduce_sum_ms={:.3} bucket_reduce_max_ms={:.3} max_concurrent_chunk_regions={} bucket_payload_at_max_concurrency_estimate_bytes={} result_merge_ms={:.3}",
            call_id.unwrap_or(0),
            exponent_count,
            c,
            signed as u8,
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

    if let Some(probe) = mem_probe.as_ref() {
        let live_end = crate::mem_probe::live();
        let live_start = mem_live_start.unwrap_or(0);
        let live_after_prep = mem_live_after_exponent_prep.unwrap_or(0);

        eprintln!(
            "BELLMAN_MSM_MEM_PROBE call_id={} exponent_count={} window={} signed={} bucket_count={} chunk_count={} bucket_element_size_bytes={} exponent_size_bytes={} chunked_exponent_size_bytes={} live_start_bytes={} live_after_exponent_prep_bytes={} exponent_prep_live_delta_bytes={} bucket_alloc_max_bytes={} live_end_bytes={} live_end_delta_bytes={} zero_exponents={} one_exponents={} chunked_exponents={} nonzero_chunk_slots={} zero_chunk_slots={} lazy_recoding={} carry_bitset_bytes={}",
            call_id.unwrap_or(0),
            exponent_count,
            c,
            signed as u8,
            bucket_count,
            chunk_count,
            std::mem::size_of::<G>(),
            std::mem::size_of::<Exponent<G::Scalar>>(),
            std::mem::size_of::<ChunkedExponent>(),
            live_start,
            live_after_prep,
            live_after_prep.saturating_sub(live_start),
            probe.bucket_alloc_max_bytes.load(Ordering::Relaxed),
            live_end,
            live_end.saturating_sub(live_start),
            probe.zero_exponents.load(Ordering::Relaxed),
            probe.one_exponents.load(Ordering::Relaxed),
            probe.chunked_exponents.load(Ordering::Relaxed),
            probe.nonzero_chunk_slots.load(Ordering::Relaxed),
            probe.zero_chunk_slots.load(Ordering::Relaxed),
            lazy_recoding as u8,
            carry_bits
                .as_ref()
                .map_or(0, |bits| bits.len() * std::mem::size_of::<u64>()),
        );
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
    let signed = msm_signed_digits_enabled();
    let c = msm_window_c_override().unwrap_or_else(|| {
        if signed {
            // Balanced-signed digits halve the bucket count at the same width,
            // so the optimal window is one bit wider than the unsigned rule and
            // is worth recomputing from the operation-count model.
            best_signed_window(G::Scalar::NUM_BITS as usize, exponents.len())
        } else if exponents.len() < 32 {
            3u32
        } else {
            (f64::from(exponents.len() as u32)).ln().ceil() as u32
        }
    });

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
    // Capture the submit timestamp before Worker::compute; emit it later because
    // the synchronous fallback branch can make compute block before returning.
    let submit_begin_timeline_ns = profile.then(profile_timestamp_ns);

    let waiter = pool.compute(move || {
        let task_start_delay_ms = submitted_at.map(|t| t.elapsed().as_secs_f64() * 1000.0);
        let start = profile.then(Instant::now);
        let task_start_timeline_ns = profile.then(profile_timestamp_ns);
        let result = multiexp_inner(
            bases, density_map, exponents, c, signed, profile, branch_counts, stage_timing, call_id,
        );
        // Read elapsed immediately after the inner call to minimize distortion.
        let elapsed_ms = start.map(|value| value.elapsed().as_secs_f64() * 1000.0);
        let inner_end_timeline_ns = profile.then(profile_timestamp_ns);

        if let Some(call_id) = call_id {
            if let Some(t_ns) = task_start_timeline_ns {
                eprintln!(
                    "BELLMAN_MSM_TIMELINE event=task_start call_id={} t_ns={}",
                    call_id, t_ns,
                );
            }
            if let Some(t_ns) = inner_end_timeline_ns {
                eprintln!(
                    "BELLMAN_MSM_TIMELINE event=inner_end call_id={} t_ns={}",
                    call_id, t_ns,
                );
            }
        }

        if let (Some(call_id), Some(task_start_delay_ms), Some(elapsed_ms)) =
            (call_id, task_start_delay_ms, elapsed_ms)
        {
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

    // This timestamp is taken immediately after compute returns. Under
    // synchronous fallback, it may follow inner_end by the work duration.
    let submit_return_timeline_ns = profile.then(profile_timestamp_ns);
    if let Some(call_id) = call_id {
        if let Some(t_ns) = submit_begin_timeline_ns {
            eprintln!(
                "BELLMAN_MSM_TIMELINE event=submit_begin call_id={} t_ns={}",
                call_id, t_ns,
            );
        }
        if let Some(t_ns) = submit_return_timeline_ns {
            eprintln!(
                "BELLMAN_MSM_TIMELINE event=submit_return call_id={} t_ns={}",
                call_id, t_ns,
            );
        }
    }

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
