use super::*;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};

pub const SYNTH_WORKER_POOL_CAPACITY: usize = 8;
pub const SYNTH_PARALLEL_SCRATCH_LIMIT_BYTES: usize = 64 * 1024 * 1024;
pub const SYNTH_PARALLEL_MIN_SCRATCH_BYTES: usize = 256 * 1024;

static WORKER_COUNT: AtomicUsize = AtomicUsize::new(0);

static POOL_INITIALIZATIONS: AtomicU64 = AtomicU64::new(0);
static GIL_RELEASED_CALLS: AtomicU64 = AtomicU64::new(0);
static GIL_RELEASED_RENDER_CALLS: AtomicU64 = AtomicU64::new(0);
static GIL_RELEASED_COMPILE_CALLS: AtomicU64 = AtomicU64::new(0);
static GIL_RELEASED_DECODE_CALLS: AtomicU64 = AtomicU64::new(0);
static GIL_RELEASED_WAV_WRITE_CALLS: AtomicU64 = AtomicU64::new(0);
static PARALLEL_REGIONS: AtomicU64 = AtomicU64::new(0);
static PARALLEL_TASKS: AtomicU64 = AtomicU64::new(0);
static PARALLEL_EVENTS: AtomicU64 = AtomicU64::new(0);
static SERIAL_EVENTS: AtomicU64 = AtomicU64::new(0);
static PARALLEL_SCRATCH_PEAK_BYTES: AtomicUsize = AtomicUsize::new(0);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GilReleasedOperation {
    Render,
    CompileAndRender,
    Decode,
    Compile,
    WriteWav,
    CompileRenderAndWriteWav,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SynthDiagnostics {
    pub configured_worker_count: Option<usize>,
    pub sample_cache: SampleCacheDiagnostics,
    pub worker_count: usize,
    pub worker_pool_capacity: usize,
    pub worker_pool_initializations: u64,
    pub gil_released_calls: u64,
    pub gil_released_render_calls: u64,
    pub gil_released_compile_calls: u64,
    pub gil_released_decode_calls: u64,
    pub gil_released_wav_write_calls: u64,
    pub parallel_regions: u64,
    pub parallel_tasks: u64,
    pub parallel_events: u64,
    pub serial_events: u64,
    pub parallel_scratch_peak_bytes: usize,
    pub parallel_scratch_limit_bytes: usize,
    pub parallel_min_scratch_bytes: usize,
}

pub fn set_worker_count(worker_count: Option<usize>) -> SynthResult<usize> {
    if let Some(worker_count) = worker_count {
        if !matches!(worker_count, 1 | 2 | 4 | 8) {
            return Err(SynthError::new(
                "synth worker count must be one of 1, 2, 4, 8, or 'auto'.",
            ));
        }
    }
    WORKER_COUNT.store(worker_count.unwrap_or(0), Ordering::Relaxed);
    Ok(effective_worker_count())
}

pub fn effective_worker_count() -> usize {
    let configured = WORKER_COUNT.load(Ordering::Relaxed);
    if configured > 0 {
        return configured.min(SYNTH_WORKER_POOL_CAPACITY);
    }
    std::thread::available_parallelism()
        .map(usize::from)
        .unwrap_or(1)
        .clamp(1, SYNTH_WORKER_POOL_CAPACITY)
}

pub fn diagnostics() -> SynthDiagnostics {
    let configured = WORKER_COUNT.load(Ordering::Relaxed);
    SynthDiagnostics {
        configured_worker_count: (configured > 0).then_some(configured),
        sample_cache: sample_cache_diagnostics(),
        worker_count: effective_worker_count(),
        worker_pool_capacity: SYNTH_WORKER_POOL_CAPACITY,
        worker_pool_initializations: POOL_INITIALIZATIONS.load(Ordering::Relaxed),
        gil_released_calls: GIL_RELEASED_CALLS.load(Ordering::Relaxed),
        gil_released_render_calls: GIL_RELEASED_RENDER_CALLS.load(Ordering::Relaxed),
        gil_released_compile_calls: GIL_RELEASED_COMPILE_CALLS.load(Ordering::Relaxed),
        gil_released_decode_calls: GIL_RELEASED_DECODE_CALLS.load(Ordering::Relaxed),
        gil_released_wav_write_calls: GIL_RELEASED_WAV_WRITE_CALLS.load(Ordering::Relaxed),
        parallel_regions: PARALLEL_REGIONS.load(Ordering::Relaxed),
        parallel_tasks: PARALLEL_TASKS.load(Ordering::Relaxed),
        parallel_events: PARALLEL_EVENTS.load(Ordering::Relaxed),
        serial_events: SERIAL_EVENTS.load(Ordering::Relaxed),
        parallel_scratch_peak_bytes: PARALLEL_SCRATCH_PEAK_BYTES.load(Ordering::Relaxed),
        parallel_scratch_limit_bytes: SYNTH_PARALLEL_SCRATCH_LIMIT_BYTES,
        parallel_min_scratch_bytes: SYNTH_PARALLEL_MIN_SCRATCH_BYTES,
    }
}

pub fn reset_diagnostics() {
    for counter in [
        &GIL_RELEASED_CALLS,
        &GIL_RELEASED_RENDER_CALLS,
        &GIL_RELEASED_COMPILE_CALLS,
        &GIL_RELEASED_DECODE_CALLS,
        &GIL_RELEASED_WAV_WRITE_CALLS,
        &PARALLEL_REGIONS,
        &PARALLEL_TASKS,
        &PARALLEL_EVENTS,
        &SERIAL_EVENTS,
    ] {
        counter.store(0, Ordering::Relaxed);
    }
    PARALLEL_SCRATCH_PEAK_BYTES.store(0, Ordering::Relaxed);
    reset_sample_cache_diagnostics();
}

pub fn record_gil_released_call(operation: GilReleasedOperation) {
    GIL_RELEASED_CALLS.fetch_add(1, Ordering::Relaxed);
    match operation {
        GilReleasedOperation::Render => {
            GIL_RELEASED_RENDER_CALLS.fetch_add(1, Ordering::Relaxed);
        }
        GilReleasedOperation::CompileAndRender => {
            GIL_RELEASED_COMPILE_CALLS.fetch_add(1, Ordering::Relaxed);
            GIL_RELEASED_RENDER_CALLS.fetch_add(1, Ordering::Relaxed);
        }
        GilReleasedOperation::Decode => {
            GIL_RELEASED_DECODE_CALLS.fetch_add(1, Ordering::Relaxed);
        }
        GilReleasedOperation::Compile => {
            GIL_RELEASED_COMPILE_CALLS.fetch_add(1, Ordering::Relaxed);
        }
        GilReleasedOperation::WriteWav => {
            GIL_RELEASED_WAV_WRITE_CALLS.fetch_add(1, Ordering::Relaxed);
        }
        GilReleasedOperation::CompileRenderAndWriteWav => {
            GIL_RELEASED_COMPILE_CALLS.fetch_add(1, Ordering::Relaxed);
            GIL_RELEASED_RENDER_CALLS.fetch_add(1, Ordering::Relaxed);
            GIL_RELEASED_WAV_WRITE_CALLS.fetch_add(1, Ordering::Relaxed);
        }
    }
}
