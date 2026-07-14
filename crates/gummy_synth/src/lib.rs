//! PyO3-free synth, sample, FX, decoding, and WAV rendering for Gummy Snake.
//!
//! `gummy_canvas` owns the mandatory extension's PyO3 adapter and calls this
//! crate for audio rendering. Keep serialized playback, DSP, and
//! sample processing here; Python-facing parsing and registration do not belong
//! in this crate. See the contributor ownership map for the cross-crate boundary.

#![allow(clippy::useless_conversion)]

use flate2::read::ZlibDecoder;
use serde_json::Value as JsonValue;
use std::collections::{HashMap, VecDeque};
use std::f64::consts::{FRAC_1_SQRT_2, PI, TAU};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

pub mod codec;

mod block_contract;
mod causal_normaliser;
// These modules still contain whole-event reference helpers used by parity tests.
// The canonical runtime does not call those helpers; Epic 320 tracks their deletion.
#[cfg_attr(not(test), allow(dead_code))]
mod dsp;
mod executor;
#[cfg_attr(not(test), allow(dead_code))]
mod fx_chain;
#[cfg_attr(not(test), allow(dead_code))]
mod fx_core;
#[cfg_attr(not(test), allow(dead_code))]
mod fx_modulation;
#[cfg_attr(not(test), allow(dead_code))]
mod fx_space;
#[cfg_attr(not(test), allow(dead_code))]
mod output;
mod plans;
mod playback;
mod program;
#[cfg_attr(not(test), allow(dead_code))]
mod sample_voice;
mod samples;
mod stateful_block_renderer;
#[cfg_attr(not(test), allow(dead_code))]
mod synth_rendering;
mod types;
#[cfg_attr(not(test), allow(dead_code))]
mod validation;
#[cfg_attr(not(test), allow(dead_code))]
mod voice_controls;
#[cfg_attr(not(test), allow(dead_code))]
mod voice_core;
mod wav_sink;

pub(crate) use dsp::*;

pub(crate) use fx_chain::*;
pub(crate) use fx_core::*;
pub(crate) use fx_modulation::*;
pub(crate) use fx_space::*;
#[cfg(test)]
pub(crate) use output::*;
pub(crate) use plans::*;

pub use block_contract::{
    BlockRenderConfig, BlockRenderDiagnostics, BlockRenderStep, MemoryPcmSink, PcmSink, SinkWrite,
    DEFAULT_RENDER_BLOCK_FRAMES, MAX_RENDER_BLOCK_FRAMES,
};
pub use causal_normaliser::{
    CausalNormaliser, CausalNormaliserConfig, CAUSAL_NORMALISER_CONTRACT_VERSION,
    DEFAULT_CAUSAL_NORMALISER_ATTACK_SECONDS, DEFAULT_CAUSAL_NORMALISER_LOOKAHEAD_SECONDS,
    DEFAULT_CAUSAL_NORMALISER_RELEASE_SECONDS, DEFAULT_CAUSAL_NORMALISER_TARGET,
};
pub use executor::{
    diagnostics, effective_worker_count, record_gil_released_call, reset_diagnostics,
    set_worker_count, GilReleasedOperation, SynthDiagnostics, SYNTH_PARALLEL_MIN_SCRATCH_BYTES,
    SYNTH_PARALLEL_SCRATCH_LIMIT_BYTES, SYNTH_WORKER_POOL_CAPACITY,
};
pub use playback::{
    render_compiled_program_wav, render_compiled_program_wav_file, render_plan_events,
    render_serialized_plan_wav_bytes, render_serialized_plan_wav_file,
};
pub use program::{
    CompiledEventId, CompiledEventKind, CompiledSynthProgram, InternedIdentifier, SynthFrame,
};
pub(crate) use sample_voice::*;
pub(crate) use samples::*;
pub use samples::{
    band_limited_sample, band_limited_sample_strided, sample_cache_diagnostics, sample_duration,
    SampleCacheDiagnostics, SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES, SAMPLE_SOURCE_CACHE_BUDGET_BYTES,
};
pub use stateful_block_renderer::StatefulBlockRenderer;
pub use synth_rendering::render_event_wav;
pub(crate) use synth_rendering::*;
pub(crate) use types::*;
pub use types::{
    ControlPayload, EventPayload, FxPayload, OptMap, SynthError, SynthResult, SynthValue,
};
pub(crate) use validation::*;

pub const CRATE_VERSION: &str = env!("CARGO_PKG_VERSION");
pub(crate) use voice_controls::*;
pub(crate) use voice_core::*;

#[cfg(test)]
mod tests;
