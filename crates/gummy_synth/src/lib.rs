//! PyO3-free synth, sample, FX, decoding, and WAV rendering for Gummy Snake.
//!
//! `gummy_canvas` owns the mandatory extension's PyO3 adapter and calls this
//! crate for audio rendering. Keep serialized playback compatibility, DSP, and
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
mod dsp;
mod executor;
mod fx_chain;
mod fx_core;
mod fx_modulation;
mod fx_space;
mod output;
mod plans;
mod playback;
mod program;
mod sample_voice;
mod samples;
mod synth_rendering;
mod types;
mod validation;
mod voice_controls;
mod voice_core;
// Epic 320 PBI 007 foundation; public render/export paths are not routed here yet.
#[allow(dead_code)]
mod wav_sink;

pub(crate) use dsp::*;
pub(crate) use executor::*;
pub(crate) use fx_chain::*;
pub(crate) use fx_core::*;
pub(crate) use fx_modulation::*;
pub(crate) use fx_space::*;
pub(crate) use output::*;
pub(crate) use plans::*;

pub use block_contract::{
    BlockRenderConfig, BlockRenderDiagnostics, BlockRenderStep, PcmSink, SinkWrite,
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
    render_compiled_program_wav, render_plan_events, render_serialized_plan_wav_bytes,
    render_serialized_plan_wav_file,
};
pub use program::CompiledSynthProgram;
pub(crate) use sample_voice::*;
pub use samples::sample_duration;
pub(crate) use samples::*;
pub use synth_rendering::render_event_wav;
pub(crate) use synth_rendering::*;
pub(crate) use types::*;
pub use types::{
    ControlPayload, EventPayload, FxPayload, OptMap, SynthError, SynthPlaybackPlan, SynthResult,
    SynthValue,
};
pub(crate) use validation::*;

pub const CRATE_VERSION: &str = env!("CARGO_PKG_VERSION");
pub(crate) use voice_controls::*;
pub(crate) use voice_core::*;

#[cfg(test)]
mod tests;
