//! Process-wide allocation-tracking probe for diagnostic harnesses.
//!
//! This module holds counters only and performs no allocation itself. A
//! diagnostic harness binary that installs a tracking `#[global_allocator]`
//! feeds these counters by calling [`on_alloc`] / [`on_dealloc`]. Instrumented
//! code (for example the MSM bucket path) can then read real live-byte values
//! with [`live`] / [`peak`].
//!
//! When no harness enables tracking, every hook is a single relaxed atomic
//! load, so the production code path is effectively unchanged.

use std::sync::atomic::{AtomicUsize, Ordering};

static TRACKING: AtomicUsize = AtomicUsize::new(0);
static LIVE_BYTES: AtomicUsize = AtomicUsize::new(0);
static PEAK_BYTES: AtomicUsize = AtomicUsize::new(0);

/// Returns whether a harness has enabled allocation tracking in this process.
#[inline]
pub fn tracking_enabled() -> bool {
    TRACKING.load(Ordering::Relaxed) == 1
}

/// Enables tracking. Call once, as early as possible in the harness `main`.
pub fn enable() {
    TRACKING.store(1, Ordering::Relaxed);
}

/// Disables tracking. Hooks become no-ops again.
pub fn disable() {
    TRACKING.store(0, Ordering::Relaxed);
}

/// Records a successful allocation of `size` bytes.
#[inline]
pub fn on_alloc(size: usize) {
    if TRACKING.load(Ordering::Relaxed) == 0 {
        return;
    }

    let current = LIVE_BYTES.fetch_add(size, Ordering::Relaxed) + size;

    let mut peak = PEAK_BYTES.load(Ordering::Relaxed);
    while current > peak {
        match PEAK_BYTES.compare_exchange_weak(
            peak,
            current,
            Ordering::Relaxed,
            Ordering::Relaxed,
        ) {
            Ok(_) => break,
            Err(observed) => peak = observed,
        }
    }
}

/// Records a deallocation of `size` bytes.
///
/// `saturating_sub` tolerates frees of allocations that happened before
/// tracking was enabled, keeping the live counter non-negative.
#[inline]
pub fn on_dealloc(size: usize) {
    if TRACKING.load(Ordering::Relaxed) == 0 {
        return;
    }

    let _ = LIVE_BYTES.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
        Some(value.saturating_sub(size))
    });
}

/// Current live (allocated minus freed) bytes observed since tracking began.
#[inline]
pub fn live() -> usize {
    LIVE_BYTES.load(Ordering::Relaxed)
}

/// High-water mark of live bytes observed since the last [`reset_peak`].
#[inline]
pub fn peak() -> usize {
    PEAK_BYTES.load(Ordering::Relaxed)
}

/// Sets the peak watermark to the current live value.
pub fn reset_peak() {
    PEAK_BYTES.store(LIVE_BYTES.load(Ordering::Relaxed), Ordering::Relaxed);
}
