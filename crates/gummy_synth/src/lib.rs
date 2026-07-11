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

mod dsp;
mod fx_core;
mod fx_modulation;
mod fx_space;
mod output;
mod plans;
mod playback;
mod sample_voice;
mod samples;
mod synth_rendering;
mod types;
mod voice_controls;
mod voice_core;

pub(crate) use dsp::*;
pub(crate) use fx_core::*;
pub(crate) use fx_modulation::*;
pub(crate) use fx_space::*;
pub(crate) use output::*;
pub(crate) use plans::*;

pub use playback::{render_plan_events, render_serialized_plan_wav_bytes};
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
pub(crate) use voice_controls::*;
pub(crate) use voice_core::*;

#[cfg(test)]
mod tests;
