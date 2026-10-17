//! Controlled measurement of the Groth16 assignment-conversion allocations.
//!
//! `vendor/groth16/src/prover.rs` converts the three assigned vectors from
//! `Scalar` into `bellman::multiexp::Exponent<Scalar>` before dispatching the
//! MSMs:
//!
//!   * line 292 : `h_exponents`               (length N - 1)
//!   * line 309 : `input_assignment`          (length = input count)
//!   * line 316 : `aux_assignment`            (length = aux count)
//!
//! Each conversion is `source.into_iter().map(Into::into).collect()`. The
//! source `Vec<Scalar>` buffer stays alive for the whole `collect`, so the peak
//! is the source vector plus the freshly built `Vec<Exponent>`. This binary
//! replicates those exact types and lengths and reports the measured peak.
//!
//! It needs no parameter file and finishes immediately.

use bellman::mem_probe;
use bellman::multiexp::Exponent;
use bls12_381::Scalar;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    hint::black_box,
    mem::size_of,
};

struct TrackingAllocator;

#[global_allocator]
static GLOBAL_ALLOCATOR: TrackingAllocator = TrackingAllocator;

unsafe impl GlobalAlloc for TrackingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = System.alloc(layout);
        if !ptr.is_null() {
            mem_probe::on_alloc(layout.size());
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = System.alloc_zeroed(layout);
        if !ptr.is_null() {
            mem_probe::on_alloc(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        mem_probe::on_dealloc(layout.size());
        System.dealloc(ptr, layout);
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        let new_ptr = System.realloc(ptr, layout, new_size);
        if !new_ptr.is_null() {
            if new_size >= layout.size() {
                mem_probe::on_alloc(new_size - layout.size());
            } else {
                mem_probe::on_dealloc(layout.size() - new_size);
            }
        }
        new_ptr
    }
}

/// Builds a source vector of `n` non-zero scalars (the realistic case for the
/// assignment vectors, which are mostly non-zero random field elements).
fn source_scalars(n: usize) -> Vec<Scalar> {
    (0..n)
        .map(|index| Scalar::from((index as u64) + 1))
        .collect()
}

fn measure_conversion(label: &str, n: usize) {
    let scalar_size = size_of::<Scalar>();
    let exponent_size = size_of::<Exponent<Scalar>>();

    let source = source_scalars(n);
    let source_bytes = source.len() * scalar_size;

    let live_before = mem_probe::live();
    mem_probe::reset_peak();

    // Exactly the groth16 conversion shape.
    let converted: Vec<Exponent<Scalar>> = source.into_iter().map(|s| s.into()).collect();

    let peak = mem_probe::peak();
    let live_after = mem_probe::live();

    let conversion_peak_delta = peak.saturating_sub(live_before);
    let retained_delta = live_after.saturating_sub(live_before);
    let converted_bytes = converted.len() * exponent_size;

    println!(
        "label={label} n={n} scalar_size_bytes={scalar_size} \
exponent_size_bytes={exponent_size} source_vec_bytes={source_bytes} \
converted_vec_bytes={converted_bytes} conversion_total_transient_bytes={} \
measured_peak_delta_bytes={conversion_peak_delta} measured_retained_delta_bytes={retained_delta} \
live_before_includes_source=true",
        source_bytes + converted_bytes,
    );

    black_box(&converted);
}

fn main() {
    mem_probe::enable();

    println!("circuit=Spend");
    // Spend: input count = 8, aux count = 98,638, h length = N - 1 = 131,071.
    measure_conversion("spend_input_assignment", 8);
    measure_conversion("spend_aux_assignment", 98_638);
    measure_conversion("spend_h_exponents", 131_071);

    println!("circuit=Output");
    // Output: input count = 6, aux count = 7,821, h length = N - 1 = 8,191.
    measure_conversion("output_input_assignment", 6);
    measure_conversion("output_aux_assignment", 7_821);
    measure_conversion("output_h_exponents", 8_191);

    println!("EXPONENT_CONVERSION_MEMORY=DONE");
}
