use rand_core::Rng;
use std::ops::{AddAssign, MulAssign};
use std::sync::Arc;

use ff::{Field, PrimeField, PrimeFieldBits};
use group::{Curve, CurveAffine};
use pairing::Engine;

use super::{ParameterSource, Proof};

use bellman::{Circuit, ConstraintSystem, Index, LinearCombination, SynthesisError, Variable};

use bellman::domain::{EvaluationDomain, Scalar};

use bellman::multiexp::{DensityTracker, FullDensity, multiexp, profile_timestamp_ns};

use bellman::multicore::Worker;

static G16_PROFILE_PROOF_ID: std::sync::atomic::AtomicUsize =
    std::sync::atomic::AtomicUsize::new(1);

fn g16_profile_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_PROFILE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

/// Whether the in-situ assignment-conversion memory probe is enabled.
///
/// Gated by `SAPLING_IN_SITU_CONVERSION_PROBE=1`. This exists to measure the
/// `Vec<Scalar> -> Vec<Exponent>` transients *inside a real `create_proof`
/// call* instead of in a standalone micro-benchmark. It is off by default and
/// costs one cached `OnceLock` read per conversion when disabled.
fn g16_in_situ_conversion_probe_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_IN_SITU_CONVERSION_PROBE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

/// Whether the per-phase prove-peak attribution probe is enabled.
///
/// Gated by `SAPLING_G16_MEM_PHASE_PROBE=1`. The overall prove peak is a single
/// watermark, so it says *that* the phase peak is high but not *where* it is.
/// This probe reports the live bytes and the peak watermark observed inside
/// each stage of `create_proof` and then re-arms the watermark, which pinpoints
/// the stage that owns the peak.
///
/// It is off by default and costs one cached `OnceLock` read per stage when
/// disabled. While enabled it re-arms the watermark at every boundary, so the
/// enclosing harness's own "peak since reset" figure is only valid outside the
/// probe; the authoritative composition is the per-phase rows.
fn g16_mem_phase_probe_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_G16_MEM_PHASE_PROBE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

/// Whether the synthesis capacity probe is enabled.
///
/// Gated by `SAPLING_G16_SYNTH_CAPACITY_PROBE=1`. The `a`/`b`/`c` and witness
/// vectors grow by `push`, so their final capacity can overshoot the length.
/// This probe reports `len`/`capacity` at the end of synthesis, separating the
/// mathematically necessary bytes from `Vec` growth slack. Off by default and
/// costs one cached `OnceLock` read per proof when disabled.
fn g16_synth_capacity_probe_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_G16_SYNTH_CAPACITY_PROBE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

/// Whether the synthesis sub-stage timing probe is enabled.
///
/// Gated by `SAPLING_SYNTH_STAGE_PROBE=1`. The existing `G16_STAGE_PROFILE`
/// reports the whole `circuit_synthesis` region as one phase. This probe
/// separates the `eval` work for the A/B/C linear combinations inside
/// `enforce`, which is the only substantial prover-side work performed while
/// the circuit is being synthesized. It is exploratory instrumentation only:
/// it does not change any arithmetic and is off by default.
fn g16_synth_stage_probe_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_SYNTH_STAGE_PROBE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

static G16_SYNTH_ENFORCE_CALLS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_ALLOC_CALLS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_INPUT_ALLOC_CALLS: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_LC_A_TERMS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_LC_B_TERMS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_LC_C_TERMS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_EVAL_A_NS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_EVAL_B_NS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static G16_SYNTH_EVAL_C_NS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

fn g16_synth_probe_reset() {
    for counter in [
        &G16_SYNTH_ENFORCE_CALLS,
        &G16_SYNTH_ALLOC_CALLS,
        &G16_SYNTH_INPUT_ALLOC_CALLS,
        &G16_SYNTH_LC_A_TERMS,
        &G16_SYNTH_LC_B_TERMS,
        &G16_SYNTH_LC_C_TERMS,
        &G16_SYNTH_EVAL_A_NS,
        &G16_SYNTH_EVAL_B_NS,
        &G16_SYNTH_EVAL_C_NS,
    ] {
        counter.store(0, std::sync::atomic::Ordering::Relaxed);
    }
}

fn g16_synth_probe_add(counter: &std::sync::atomic::AtomicU64, value: u64) {
    counter.fetch_add(value, std::sync::atomic::Ordering::Relaxed);
}

fn g16_synth_probe_report(proof_id: usize) {
    let load =
        |counter: &std::sync::atomic::AtomicU64| counter.load(std::sync::atomic::Ordering::Relaxed);
    let eval_a_ns = load(&G16_SYNTH_EVAL_A_NS);
    let eval_b_ns = load(&G16_SYNTH_EVAL_B_NS);
    let eval_c_ns = load(&G16_SYNTH_EVAL_C_NS);

    eprintln!(
        "G16_SYNTH_PROBE proof_id={} enforce_calls={} alloc_calls={} input_alloc_calls={} \
lc_a_terms={} lc_b_terms={} lc_c_terms={} eval_a_ms={:.3} eval_b_ms={:.3} eval_c_ms={:.3} \
eval_total_ms={:.3}",
        proof_id,
        load(&G16_SYNTH_ENFORCE_CALLS),
        load(&G16_SYNTH_ALLOC_CALLS),
        load(&G16_SYNTH_INPUT_ALLOC_CALLS),
        load(&G16_SYNTH_LC_A_TERMS),
        load(&G16_SYNTH_LC_B_TERMS),
        load(&G16_SYNTH_LC_C_TERMS),
        eval_a_ns as f64 / 1_000_000.0,
        eval_b_ns as f64 / 1_000_000.0,
        eval_c_ns as f64 / 1_000_000.0,
        (eval_a_ns + eval_b_ns + eval_c_ns) as f64 / 1_000_000.0,
    );
}

/// Whether the QAP sub-stage timing probe is enabled.
///
/// Gated by `SAPLING_QAP_STAGE_PROBE=1`. The existing `G16_STAGE_PROFILE`
/// treats the whole QAP/FFT region as one phase, which hides whether the
/// remaining cost is in the three inverse FFTs, the three coset FFTs, or the
/// O(n) element-wise passes. This probe is exploratory instrumentation only:
/// it does not change any arithmetic and is off by default.
fn g16_qap_stage_probe_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_QAP_STAGE_PROBE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

/// Whether the exploratory concurrent A/B/C QAP transform is enabled.
///
/// Gated by `SAPLING_QAP_CONCURRENT_ABC=1`. The three inverse FFTs (and the
/// three coset FFTs) are independent, but the baseline executes them one after
/// another on the same Rayon pool. This switch overlaps each group to test
/// whether the per-FFT parallel efficiency is poor enough that three smaller
/// concurrent transforms beat three full-pool transforms. It is off by default
/// and is an experiment, not a production default.
fn g16_qap_concurrent_abc_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_QAP_CONCURRENT_ABC")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

/// Whether the exploratory three-pool A/B/C QAP transform is enabled.
///
/// Gated by `SAPLING_QAP_ABC_POOLS=1`. Unlike the all-thread nested-scope
/// variant, this assigns one persistent two-thread Rayon pool to each of the
/// independent `a/b/c` transforms. The single-transform parallel efficiency at
/// eight threads is low, so three two-thread transforms can have higher
/// aggregate throughput even though two of the eight logical CPUs stay idle.
/// It is off by default and is an experiment, not a production default.
fn g16_qap_abc_pools_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_QAP_ABC_POOLS")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

/// Whether the three A/B/C pools should pipeline `ifft -> coset_fft` per
/// letter instead of synchronizing between the two transform groups.
///
/// Gated by `SAPLING_QAP_ABC_PIPELINE=1` and only meaningful together with
/// `SAPLING_QAP_ABC_POOLS=1`. It is off by default.
fn g16_qap_abc_pipeline_enabled() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *ENABLED.get_or_init(|| {
        std::env::var("SAPLING_QAP_ABC_PIPELINE")
            .map(|value| value == "1")
            .unwrap_or(false)
    })
}

#[cfg(feature = "multicore")]
fn g16_qap_abc_pools() -> &'static [rayon::ThreadPool; 3] {
    static POOLS: std::sync::OnceLock<[rayon::ThreadPool; 3]> = std::sync::OnceLock::new();

    POOLS.get_or_init(|| {
        let pools: [rayon::ThreadPool; 3] = std::array::from_fn(|index| {
            rayon::ThreadPoolBuilder::new()
                .num_threads(2)
                .thread_name(move |thread| format!("qap-abc-{index}-{thread}"))
                .build()
                .expect("build QAP A/B/C pool")
        });
        // Spawn the workers before the first measured proof so pool startup is
        // not charged to a transform.
        for pool in &pools {
            pool.install(|| {});
        }
        pools
    })
}

/// Reports the live bytes and the peak watermark since the previous boundary,
/// then re-arms the watermark at the current live value.
///
/// `phase_peak_abs_bytes` is therefore the highest live value reached during
/// the stage that just finished, on the same absolute scale as
/// `BELLMAN_MSM_MEM_PROBE` and the ledger. Because re-arming destroys the
/// caller's own watermark, `running_max_abs_bytes` carries the maximum over
/// the phases seen since `pre_body`, i.e. the body-wide peak computed from the
/// per-phase peaks.
#[inline]
fn g16_mem_phase_boundary(phase: &str) {
    static RUNNING_MAX_ABS_BYTES: std::sync::atomic::AtomicUsize =
        std::sync::atomic::AtomicUsize::new(0);

    if !g16_mem_phase_probe_enabled() {
        return;
    }

    let live = bellman::mem_probe::live();
    let peak = bellman::mem_probe::peak();
    if phase == "pre_body" {
        RUNNING_MAX_ABS_BYTES.store(peak, std::sync::atomic::Ordering::Relaxed);
    }
    let running_max = RUNNING_MAX_ABS_BYTES.fetch_max(peak, std::sync::atomic::Ordering::Relaxed);
    let running_max = running_max.max(peak);

    eprintln!(
        "G16_MEM_PHASE phase={} live_bytes={} phase_peak_abs_bytes={} phase_peak_delta_bytes={} running_max_abs_bytes={}",
        phase,
        live,
        peak,
        peak.saturating_sub(live),
        running_max,
    );
    bellman::mem_probe::reset_peak();
}

/// Collects a converted assignment vector, optionally reporting the directly
/// measured allocation transient of the `Scalar -> Exponent` conversion.
///
/// The conversion shape is `source.into_iter().map(..).collect()`. The source
/// `Vec` buffer is only released once `collect` completes, so the transient
/// window holds `source_bytes + converted_bytes`. Because the source is
/// consumed here, its length and element size are passed in by the caller.
///
/// The probe needs a process that feeds [`bellman::mem_probe`] from a tracking
/// `#[global_allocator]`; when no harness enables tracking the counters read 0.
#[inline]
fn collect_conversion<T>(
    site: &str,
    source_len: usize,
    source_elem_size: usize,
    iter: impl Iterator<Item = T>,
) -> Vec<T> {
    if g16_in_situ_conversion_probe_enabled() {
        let live_before = bellman::mem_probe::live();
        bellman::mem_probe::reset_peak();

        let converted: Vec<T> = iter.collect();

        let peak = bellman::mem_probe::peak();
        let live_after = bellman::mem_probe::live();
        let converted_bytes = converted.len() * std::mem::size_of::<T>();

        eprintln!(
            "G16_IN_SITU_CONVERSION site={} n={} source_elem_size_bytes={} \
source_bytes={} converted_bytes={} live_before_bytes={} peak_delta_bytes={} \
live_after_delta_bytes={}",
            site,
            converted.len(),
            source_elem_size,
            source_len * source_elem_size,
            converted_bytes,
            live_before,
            peak.saturating_sub(live_before),
            live_after.saturating_sub(live_before),
        );

        converted
    } else {
        iter.collect()
    }
}

fn eval<S: PrimeField>(
    lc: &LinearCombination<S>,
    mut input_density: Option<&mut DensityTracker>,
    mut aux_density: Option<&mut DensityTracker>,
    input_assignment: &[S],
    aux_assignment: &[S],
) -> S {
    let mut acc = S::ZERO;

    for &(index, coeff) in lc.as_ref() {
        let mut tmp;

        if !coeff.is_zero_vartime() {
            match index.get_unchecked() {
                Index::Input(i) => {
                    tmp = input_assignment[i];
                    if let Some(ref mut v) = input_density {
                        v.inc(i);
                    }
                }
                Index::Aux(i) => {
                    tmp = aux_assignment[i];
                    if let Some(ref mut v) = aux_density {
                        v.inc(i);
                    }
                }
            }

            if coeff != S::ONE {
                tmp *= coeff;
            }
            acc += tmp;
        }
    }

    acc
}

struct ProvingAssignment<S: PrimeField> {
    // Density of queries
    a_aux_density: DensityTracker,
    b_input_density: DensityTracker,
    b_aux_density: DensityTracker,

    // Evaluations of A, B, C polynomials
    a: Vec<Scalar<S>>,
    b: Vec<Scalar<S>>,
    c: Vec<Scalar<S>>,

    // Assignments of variables
    input_assignment: Vec<S>,
    aux_assignment: Vec<S>,
}

impl<S: PrimeField> ConstraintSystem<S> for ProvingAssignment<S> {
    type Root = Self;

    fn alloc<F, A, AR>(&mut self, _: A, f: F) -> Result<Variable, SynthesisError>
    where
        F: FnOnce() -> Result<S, SynthesisError>,
        A: FnOnce() -> AR,
        AR: Into<String>,
    {
        if g16_synth_stage_probe_enabled() {
            g16_synth_probe_add(&G16_SYNTH_ALLOC_CALLS, 1);
        }

        self.aux_assignment.push(f()?);
        self.a_aux_density.add_element();
        self.b_aux_density.add_element();

        Ok(Variable::new_unchecked(Index::Aux(
            self.aux_assignment.len() - 1,
        )))
    }

    fn alloc_input<F, A, AR>(&mut self, _: A, f: F) -> Result<Variable, SynthesisError>
    where
        F: FnOnce() -> Result<S, SynthesisError>,
        A: FnOnce() -> AR,
        AR: Into<String>,
    {
        if g16_synth_stage_probe_enabled() {
            g16_synth_probe_add(&G16_SYNTH_INPUT_ALLOC_CALLS, 1);
        }

        self.input_assignment.push(f()?);
        self.b_input_density.add_element();

        Ok(Variable::new_unchecked(Index::Input(
            self.input_assignment.len() - 1,
        )))
    }

    fn enforce<A, AR, LA, LB, LC>(&mut self, _: A, a: LA, b: LB, c: LC)
    where
        A: FnOnce() -> AR,
        AR: Into<String>,
        LA: FnOnce(LinearCombination<S>) -> LinearCombination<S>,
        LB: FnOnce(LinearCombination<S>) -> LinearCombination<S>,
        LC: FnOnce(LinearCombination<S>) -> LinearCombination<S>,
    {
        let a = a(LinearCombination::zero());
        let b = b(LinearCombination::zero());
        let c = c(LinearCombination::zero());
        let synth_probe = g16_synth_stage_probe_enabled();

        if synth_probe {
            g16_synth_probe_add(&G16_SYNTH_ENFORCE_CALLS, 1);
            g16_synth_probe_add(&G16_SYNTH_LC_A_TERMS, a.as_ref().len() as u64);
            g16_synth_probe_add(&G16_SYNTH_LC_B_TERMS, b.as_ref().len() as u64);
            g16_synth_probe_add(&G16_SYNTH_LC_C_TERMS, c.as_ref().len() as u64);
        }

        let a_value = if synth_probe {
            let start = std::time::Instant::now();
            let value = eval(
                &a,
                // Inputs have full density in the A query
                // because there are constraints of the
                // form x * 0 = 0 for each input.
                None,
                Some(&mut self.a_aux_density),
                &self.input_assignment,
                &self.aux_assignment,
            );
            g16_synth_probe_add(&G16_SYNTH_EVAL_A_NS, start.elapsed().as_nanos() as u64);
            value
        } else {
            eval(
                &a,
                None,
                Some(&mut self.a_aux_density),
                &self.input_assignment,
                &self.aux_assignment,
            )
        };
        self.a.push(Scalar(a_value));

        let b_value = if synth_probe {
            let start = std::time::Instant::now();
            let value = eval(
                &b,
                Some(&mut self.b_input_density),
                Some(&mut self.b_aux_density),
                &self.input_assignment,
                &self.aux_assignment,
            );
            g16_synth_probe_add(&G16_SYNTH_EVAL_B_NS, start.elapsed().as_nanos() as u64);
            value
        } else {
            eval(
                &b,
                Some(&mut self.b_input_density),
                Some(&mut self.b_aux_density),
                &self.input_assignment,
                &self.aux_assignment,
            )
        };
        self.b.push(Scalar(b_value));

        let c_value = if synth_probe {
            let start = std::time::Instant::now();
            let value = eval(
                &c,
                // There is no C polynomial query,
                // though there is an (beta)A + (alpha)B + C
                // query for all aux variables.
                // However, that query has full density.
                None,
                None,
                &self.input_assignment,
                &self.aux_assignment,
            );
            g16_synth_probe_add(&G16_SYNTH_EVAL_C_NS, start.elapsed().as_nanos() as u64);
            value
        } else {
            eval(&c, None, None, &self.input_assignment, &self.aux_assignment)
        };
        self.c.push(Scalar(c_value));
    }

    fn push_namespace<NR, N>(&mut self, _: N)
    where
        NR: Into<String>,
        N: FnOnce() -> NR,
    {
        // Do nothing; we don't care about namespaces in this context.
    }

    fn pop_namespace(&mut self) {
        // Do nothing; we don't care about namespaces in this context.
    }

    fn get_root(&mut self) -> &mut Self::Root {
        self
    }
}

pub fn create_random_proof<E, C, R, P: ParameterSource<E>>(
    circuit: C,
    params: P,
    mut rng: &mut R,
) -> Result<Proof<E>, SynthesisError>
where
    E: Engine,
    E::Fr: PrimeFieldBits,
    C: Circuit<E::Fr>,
    R: Rng,
{
    let profile = g16_profile_enabled();
    let random_start = profile.then(std::time::Instant::now);

    let r = E::Fr::random(&mut rng);
    let s = E::Fr::random(&mut rng);

    let random_scalars_ms = random_start.map(|start| start.elapsed().as_secs_f64() * 1000.0);

    let proof = create_proof::<E, C, P>(circuit, params, r, s);

    if let Some(elapsed_ms) = random_scalars_ms {
        eprintln!("G16_RANDOMNESS_PROFILE random_scalars_ms={elapsed_ms:.3}");
    }

    proof
}

#[allow(clippy::many_single_char_names)]
pub fn create_proof<E, C, P: ParameterSource<E>>(
    circuit: C,
    mut params: P,
    r: E::Fr,
    s: E::Fr,
) -> Result<Proof<E>, SynthesisError>
where
    E: Engine,
    E::Fr: PrimeFieldBits,
    C: Circuit<E::Fr>,
{
    let profile = g16_profile_enabled();
    let synth_probe = g16_synth_stage_probe_enabled();
    let proof_id = if profile || synth_probe {
        G16_PROFILE_PROOF_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    } else {
        0
    };
    if synth_probe {
        g16_synth_probe_reset();
    }
    // Marks delimit sequential wall-clock phases. Each boundary is captured once
    // and reused by adjacent phases, avoiding double-counting between phases.
    let mut profile_marks: [Option<std::time::Instant>; 8] = [None; 8];
    g16_mem_phase_boundary("pre_body");
    if profile {
        profile_marks[0] = Some(std::time::Instant::now());
        eprintln!(
            "G16_TIMELINE event=proof_body_start proof_id={} t_ns={}",
            proof_id,
            profile_timestamp_ns(),
        );
    }

    let mut prover = ProvingAssignment {
        a_aux_density: DensityTracker::new(),
        b_input_density: DensityTracker::new(),
        b_aux_density: DensityTracker::new(),
        a: vec![],
        b: vec![],
        c: vec![],
        input_assignment: vec![],
        aux_assignment: vec![],
    };

    prover.alloc_input(|| "", || Ok(E::Fr::ONE))?;

    circuit.synthesize(&mut prover)?;

    for i in 0..prover.input_assignment.len() {
        prover.enforce(
            || "",
            |lc| lc + Variable::new_unchecked(Index::Input(i)),
            |lc| lc,
            |lc| lc,
        );
    }

    if synth_probe {
        g16_synth_probe_report(proof_id);
    }

    if profile {
        profile_marks[1] = Some(std::time::Instant::now());
    }
    g16_mem_phase_boundary("circuit_synthesis");

    if g16_synth_capacity_probe_enabled() {
        let scalar_bytes = std::mem::size_of::<Scalar<E::Fr>>();
        let field_bytes = std::mem::size_of::<E::Fr>();
        let abc_capacity_bytes =
            (prover.a.capacity() + prover.b.capacity() + prover.c.capacity()) * scalar_bytes;
        let witness_capacity_bytes =
            (prover.input_assignment.capacity() + prover.aux_assignment.capacity()) * field_bytes;
        eprintln!(
            "G16_SYNTH_CAPACITY a_len={} a_cap={} b_len={} b_cap={} c_len={} c_cap={} input_len={} input_cap={} aux_len={} aux_cap={} scalar_bytes={} abc_capacity_bytes={} witness_capacity_bytes={} live_bytes={}",
            prover.a.len(),
            prover.a.capacity(),
            prover.b.len(),
            prover.b.capacity(),
            prover.c.len(),
            prover.c.capacity(),
            prover.input_assignment.len(),
            prover.input_assignment.capacity(),
            prover.aux_assignment.len(),
            prover.aux_assignment.capacity(),
            scalar_bytes,
            abc_capacity_bytes,
            witness_capacity_bytes,
            bellman::mem_probe::live(),
        );
    }

    let worker = Worker::new();

    let vk = params.get_vk(prover.input_assignment.len())?;

    if profile {
        profile_marks[2] = Some(std::time::Instant::now());
    }
    g16_mem_phase_boundary("worker_vk_setup");

    // QAP polynomial transforms and H-query exponent preparation.
    let h_exponents = {
        let qap_probe = g16_qap_stage_probe_enabled();
        #[cfg(feature = "multicore")]
        let qap_abc_pools = g16_qap_abc_pools_enabled();
        #[cfg(not(feature = "multicore"))]
        let qap_abc_pools = false;
        let qap_abc_pipeline = g16_qap_abc_pipeline_enabled();
        #[cfg(feature = "multicore")]
        let abc_pools = qap_abc_pools.then(g16_qap_abc_pools);
        let mut qap_marks: [Option<std::time::Instant>; 14] = [None; 14];
        if qap_probe {
            qap_marks[0] = Some(std::time::Instant::now());
        }

        let mut a = EvaluationDomain::from_coeffs(prover.a)?;
        let mut b = EvaluationDomain::from_coeffs(prover.b)?;
        let mut c = EvaluationDomain::from_coeffs(prover.c)?;
        if qap_probe {
            qap_marks[1] = Some(std::time::Instant::now());
        }
        g16_mem_phase_boundary("qap_domains_built");
        let qap_concurrent = g16_qap_concurrent_abc_enabled();
        if qap_abc_pools {
            #[cfg(feature = "multicore")]
            {
                let pools = abc_pools.expect("QAP ABC pools initialized");
                if qap_abc_pipeline {
                    // Pipeline per letter: a's coset can start as soon as a's
                    // ifft finishes, without waiting for b/c's ifft.
                    let worker_ref = &worker;
                    std::thread::scope(|scope| {
                        let a = &mut a;
                        let b = &mut b;
                        let c = &mut c;
                        scope.spawn(move || {
                            pools[0].install(|| {
                                a.ifft(worker_ref);
                                a.coset_fft(worker_ref);
                            })
                        });
                        scope.spawn(move || {
                            pools[1].install(|| {
                                b.ifft(worker_ref);
                                b.coset_fft(worker_ref);
                            })
                        });
                        scope.spawn(move || {
                            pools[2].install(|| {
                                c.ifft(worker_ref);
                                c.coset_fft(worker_ref);
                            })
                        });
                    });
                    if qap_probe {
                        qap_marks[2] = Some(std::time::Instant::now());
                    }
                } else {
                    let worker_ref = &worker;
                    std::thread::scope(|scope| {
                        let a = &mut a;
                        let b = &mut b;
                        let c = &mut c;
                        scope.spawn(move || pools[0].install(|| a.ifft(worker_ref)));
                        scope.spawn(move || pools[1].install(|| b.ifft(worker_ref)));
                        scope.spawn(move || pools[2].install(|| c.ifft(worker_ref)));
                    });
                    if qap_probe {
                        qap_marks[2] = Some(std::time::Instant::now());
                    }
                    let worker_ref = &worker;
                    std::thread::scope(|scope| {
                        let a = &mut a;
                        let b = &mut b;
                        let c = &mut c;
                        scope.spawn(move || pools[0].install(|| a.coset_fft(worker_ref)));
                        scope.spawn(move || pools[1].install(|| b.coset_fft(worker_ref)));
                        scope.spawn(move || pools[2].install(|| c.coset_fft(worker_ref)));
                    });
                    if qap_probe {
                        qap_marks[3] = Some(std::time::Instant::now());
                    }
                }
            }
        } else if qap_concurrent {
            // The three transforms are independent. Use nested Rayon scopes
            // so their shuffle/copy phases can overlap on the shared pool.
            let worker_ref = &worker;
            worker.scope(0, |scope, _| {
                let a = &mut a;
                let b = &mut b;
                let c = &mut c;
                scope.spawn(move |_| a.ifft(worker_ref));
                scope.spawn(move |_| b.ifft(worker_ref));
                scope.spawn(move |_| c.ifft(worker_ref));
            });
            if qap_probe {
                qap_marks[2] = Some(std::time::Instant::now());
            }
            let worker_ref = &worker;
            worker.scope(0, |scope, _| {
                let a = &mut a;
                let b = &mut b;
                let c = &mut c;
                scope.spawn(move |_| a.coset_fft(worker_ref));
                scope.spawn(move |_| b.coset_fft(worker_ref));
                scope.spawn(move |_| c.coset_fft(worker_ref));
            });
            if qap_probe {
                qap_marks[3] = Some(std::time::Instant::now());
            }
        } else {
            a.ifft(&worker);
            if qap_probe {
                qap_marks[2] = Some(std::time::Instant::now());
            }
            a.coset_fft(&worker);
            if qap_probe {
                qap_marks[3] = Some(std::time::Instant::now());
            }
            b.ifft(&worker);
            if qap_probe {
                qap_marks[4] = Some(std::time::Instant::now());
            }
            b.coset_fft(&worker);
            if qap_probe {
                qap_marks[5] = Some(std::time::Instant::now());
            }
            c.ifft(&worker);
            if qap_probe {
                qap_marks[6] = Some(std::time::Instant::now());
            }
            c.coset_fft(&worker);
            if qap_probe {
                qap_marks[7] = Some(std::time::Instant::now());
            }
        }
        g16_mem_phase_boundary("qap_ffts_done");

        a.mul_assign(&worker, &b);
        drop(b);
        if qap_probe {
            qap_marks[8] = Some(std::time::Instant::now());
        }
        g16_mem_phase_boundary("qap_mul_ab_done");
        a.sub_assign(&worker, &c);
        drop(c);
        if qap_probe {
            qap_marks[9] = Some(std::time::Instant::now());
        }
        g16_mem_phase_boundary("qap_sub_c_done");
        a.divide_by_z_on_coset(&worker);
        if qap_probe {
            qap_marks[10] = Some(std::time::Instant::now());
        }
        a.icoset_fft(&worker);
        if qap_probe {
            qap_marks[11] = Some(std::time::Instant::now());
        }
        g16_mem_phase_boundary("qap_divide_icoset_done");
        let mut a = a.into_coeffs();
        let a_len = a.len() - 1;
        a.truncate(a_len);
        if qap_probe {
            qap_marks[12] = Some(std::time::Instant::now());
        }
        g16_mem_phase_boundary("qap_into_coeffs_done");
        let h_source_len = a.len();
        let h_source_elem_size = a
            .first()
            .map(|element| std::mem::size_of_val(element))
            .unwrap_or(0);
        let result = Arc::new(collect_conversion(
            "h_exponents",
            h_source_len,
            h_source_elem_size,
            a.into_iter().map(|s| s.0.into()),
        ));
        if qap_probe {
            qap_marks[13] = Some(std::time::Instant::now());
            let duration = |start: usize, end: usize| {
                qap_marks[start]
                    .zip(qap_marks[end])
                    .map(|(start, end)| end.duration_since(start).as_secs_f64() * 1000.0)
                    .unwrap_or(f64::NAN)
            };
            eprintln!(
                "G16_QAP_STAGE proof_id={} mode={} domains_ms={:.3} a_ifft_ms={:.3} a_coset_ms={:.3} b_ifft_ms={:.3} b_coset_ms={:.3} c_ifft_ms={:.3} c_coset_ms={:.3} mul_ab_ms={:.3} sub_c_ms={:.3} divide_z_ms={:.3} icoset_ms={:.3} into_coeffs_ms={:.3} h_exponents_ms={:.3} total_ms={:.3}",
                proof_id,
                if qap_abc_pools {
                    if qap_abc_pipeline {
                        "pipeline"
                    } else {
                        "pools"
                    }
                } else if qap_concurrent {
                    "concurrent"
                } else {
                    "sequential"
                },
                duration(0, 1),
                duration(1, 2),
                duration(2, 3),
                duration(3, 4),
                duration(4, 5),
                duration(5, 6),
                duration(6, 7),
                duration(7, 8),
                duration(8, 9),
                duration(9, 10),
                duration(10, 11),
                duration(11, 12),
                duration(12, 13),
                duration(0, 13),
            );
        }
        result
    };

    if profile {
        profile_marks[3] = Some(std::time::Instant::now());
    }
    g16_mem_phase_boundary("qap_fft_h_exponent_prep");

    // This call can include synchronous fallback work inside Worker::compute.
    let h = multiexp(
        &worker,
        params.get_h(h_exponents.len())?,
        FullDensity,
        h_exponents,
    );

    if profile {
        profile_marks[4] = Some(std::time::Instant::now());
    }
    g16_mem_phase_boundary("h_query_access_dispatch");

    // Assignment conversion, query preparation, and the remaining MSM dispatches.
    // In single-thread mode, a multiexp call may block while doing fallback work.
    // TODO: parallelize if it's even helpful
    let input_source_len = prover.input_assignment.len();
    let input_source_elem_size = prover
        .input_assignment
        .first()
        .map(|element| std::mem::size_of_val(element))
        .unwrap_or(0);
    let input_assignment = Arc::new(collect_conversion(
        "input_assignment",
        input_source_len,
        input_source_elem_size,
        prover.input_assignment.into_iter().map(|s| s.into()),
    ));
    let aux_source_len = prover.aux_assignment.len();
    let aux_source_elem_size = prover
        .aux_assignment
        .first()
        .map(|element| std::mem::size_of_val(element))
        .unwrap_or(0);
    let aux_assignment = Arc::new(collect_conversion(
        "aux_assignment",
        aux_source_len,
        aux_source_elem_size,
        prover.aux_assignment.into_iter().map(|s| s.into()),
    ));

    let l = multiexp(
        &worker,
        params.get_l(aux_assignment.len())?,
        FullDensity,
        aux_assignment.clone(),
    );

    let a_aux_density_total = prover.a_aux_density.get_total_density();

    let (a_inputs_source, a_aux_source) =
        params.get_a(input_assignment.len(), a_aux_density_total)?;

    let a_inputs = multiexp(
        &worker,
        a_inputs_source,
        FullDensity,
        input_assignment.clone(),
    );
    let a_aux = multiexp(
        &worker,
        a_aux_source,
        Arc::new(prover.a_aux_density),
        aux_assignment.clone(),
    );

    let b_input_density = Arc::new(prover.b_input_density);
    let b_input_density_total = b_input_density.get_total_density();
    let b_aux_density = Arc::new(prover.b_aux_density);
    let b_aux_density_total = b_aux_density.get_total_density();

    let (b_g1_inputs_source, b_g1_aux_source) =
        params.get_b_g1(b_input_density_total, b_aux_density_total)?;

    let b_g1_inputs = multiexp(
        &worker,
        b_g1_inputs_source,
        b_input_density.clone(),
        input_assignment.clone(),
    );
    let b_g1_aux = multiexp(
        &worker,
        b_g1_aux_source,
        b_aux_density.clone(),
        aux_assignment.clone(),
    );

    let (b_g2_inputs_source, b_g2_aux_source) =
        params.get_b_g2(b_input_density_total, b_aux_density_total)?;

    let b_g2_inputs = multiexp(
        &worker,
        b_g2_inputs_source,
        b_input_density,
        input_assignment,
    );
    let b_g2_aux = multiexp(&worker, b_g2_aux_source, b_aux_density, aux_assignment);

    if profile {
        profile_marks[5] = Some(std::time::Instant::now());
    }
    g16_mem_phase_boundary("assignment_query_prep_dispatch");

    if bool::from(vk.delta_g1.is_identity() | vk.delta_g2.is_identity()) {
        // If this element is zero, someone is trying to perform a
        // subversion-CRS attack.
        return Err(SynthesisError::UnexpectedIdentity);
    }

    let mut g_a = vk.delta_g1 * r;
    AddAssign::<&E::G1Affine>::add_assign(&mut g_a, &vk.alpha_g1);
    let mut g_b = vk.delta_g2 * s;
    AddAssign::<&E::G2Affine>::add_assign(&mut g_b, &vk.beta_g2);
    let mut g_c;
    {
        let mut rs = r;
        rs.mul_assign(&s);

        g_c = vk.delta_g1 * rs;
        AddAssign::<&E::G1>::add_assign(&mut g_c, &(vk.alpha_g1 * s));
        AddAssign::<&E::G1>::add_assign(&mut g_c, &(vk.beta_g1 * r));
    }

    if profile {
        profile_marks[6] = Some(std::time::Instant::now());
        eprintln!(
            "G16_TIMELINE event=wait_and_assembly_start proof_id={} t_ns={}",
            proof_id,
            profile_timestamp_ns(),
        );
    }
    g16_mem_phase_boundary("proof_scalar_terms");

    let mut a_answer = a_inputs.wait()?;
    AddAssign::<&E::G1>::add_assign(&mut a_answer, &a_aux.wait()?);
    AddAssign::<&E::G1>::add_assign(&mut g_a, &a_answer);
    MulAssign::<E::Fr>::mul_assign(&mut a_answer, s);
    AddAssign::<&E::G1>::add_assign(&mut g_c, &a_answer);

    let mut b1_answer: E::G1 = b_g1_inputs.wait()?;
    AddAssign::<&E::G1>::add_assign(&mut b1_answer, &b_g1_aux.wait()?);
    let mut b2_answer = b_g2_inputs.wait()?;
    AddAssign::<&E::G2>::add_assign(&mut b2_answer, &b_g2_aux.wait()?);

    AddAssign::<&E::G2>::add_assign(&mut g_b, &b2_answer);
    MulAssign::<E::Fr>::mul_assign(&mut b1_answer, r);
    AddAssign::<&E::G1>::add_assign(&mut g_c, &b1_answer);
    AddAssign::<&E::G1>::add_assign(&mut g_c, &h.wait()?);
    AddAssign::<&E::G1>::add_assign(&mut g_c, &l.wait()?);

    let proof = Proof {
        a: g_a.to_affine(),
        b: g_b.to_affine(),
        c: g_c.to_affine(),
    };
    g16_mem_phase_boundary("wait_and_assembly");

    if profile {
        profile_marks[7] = Some(std::time::Instant::now());
        let end_t_ns = profile_timestamp_ns();
        eprintln!(
            "G16_TIMELINE event=wait_and_assembly_end proof_id={} t_ns={}",
            proof_id, end_t_ns,
        );
        eprintln!(
            "G16_TIMELINE event=proof_body_end proof_id={} t_ns={}",
            proof_id, end_t_ns,
        );

        let marks = profile_marks.map(|mark| mark.expect("all G16 profile marks must be set"));
        let duration_ms = |start: std::time::Instant, end: std::time::Instant| {
            end.duration_since(start).as_secs_f64() * 1000.0
        };

        let circuit_synthesis_ms = duration_ms(marks[0], marks[1]);
        let worker_vk_setup_ms = duration_ms(marks[1], marks[2]);
        let qap_fft_h_exponent_prep_ms = duration_ms(marks[2], marks[3]);
        let h_query_access_dispatch_ms = duration_ms(marks[3], marks[4]);
        let assignment_query_prep_dispatch_ms = duration_ms(marks[4], marks[5]);
        let proof_scalar_terms_ms = duration_ms(marks[5], marks[6]);
        let wait_and_assembly_ms = duration_ms(marks[6], marks[7]);
        let create_proof_body_ms = duration_ms(marks[0], marks[7]);

        eprintln!(
            "G16_STAGE_PROFILE circuit_synthesis_constraints_ms={:.3} worker_vk_setup_ms={:.3} qap_fft_h_exponent_prep_ms={:.3} h_query_access_dispatch_ms={:.3} assignment_query_prep_dispatch_ms={:.3} proof_scalar_terms_ms={:.3} wait_and_assembly_ms={:.3} create_proof_body_ms={:.3}",
            circuit_synthesis_ms,
            worker_vk_setup_ms,
            qap_fft_h_exponent_prep_ms,
            h_query_access_dispatch_ms,
            assignment_query_prep_dispatch_ms,
            proof_scalar_terms_ms,
            wait_and_assembly_ms,
            create_proof_body_ms,
        );
    }

    Ok(proof)
}
