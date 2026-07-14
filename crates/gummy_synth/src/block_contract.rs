//! Contract types shared by the canonical stateful synth block renderer and its sinks.
//!
//! These types intentionally do not adapt whole-signal vector rendering. A renderer
//! must own its schedule and processor state, advance only after a sink accepts
//! PCM, and report bounded workspace/state high-water marks.

use super::*;

pub const DEFAULT_RENDER_BLOCK_FRAMES: usize = 1_024;
pub const MAX_RENDER_BLOCK_FRAMES: usize = 8_192;

/// Configuration shared by every sink consuming a stateful render session.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct BlockRenderConfig {
    pub block_frames: usize,
}

impl Default for BlockRenderConfig {
    fn default() -> Self {
        Self {
            block_frames: DEFAULT_RENDER_BLOCK_FRAMES,
        }
    }
}

impl BlockRenderConfig {
    pub fn validate(self) -> SynthResult<Self> {
        if !(1..=MAX_RENDER_BLOCK_FRAMES).contains(&self.block_frames) {
            return Err(SynthError::new(format!(
                "synth render block_frames must be in 1..={MAX_RENDER_BLOCK_FRAMES}; got {}.",
                self.block_frames
            )));
        }
        Ok(self)
    }
}

/// Outcome of one pull from a stateful renderer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BlockRenderStep {
    /// The renderer appended this many stereo frames to its sink buffer.
    Produced { frames: usize },
    /// Every scheduled source and processor tail has drained.
    Finished,
}

/// Result of offering one complete PCM block to a sink.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SinkWrite {
    Accepted,
    WouldBlock,
}

/// Minimal sink boundary used by memory, file, test, and SDL queue consumers.
///
/// A `WouldBlock` result means the renderer must retain its completed PCM block
/// and must not advance source or processor state until the same block is
/// accepted. Implementations must never partially consume the supplied slice.
pub trait PcmSink {
    fn write_interleaved_i16(&mut self, samples: &[i16]) -> SynthResult<SinkWrite>;

    fn finish(&mut self) -> SynthResult<()> {
        Ok(())
    }
}

/// Explicit in-memory sink for callers that intentionally request complete PCM.
///
/// Its duration-sized output storage is caller-visible by design. Renderer
/// workspace diagnostics exclude this sink buffer, so streaming sinks can prove
/// bounded internal memory independently of a bytes-returning API.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct MemoryPcmSink {
    samples: Vec<i16>,
    finished: bool,
}

impl MemoryPcmSink {
    pub fn samples(&self) -> &[i16] {
        &self.samples
    }

    pub fn into_samples(self) -> Vec<i16> {
        self.samples
    }

    pub fn is_finished(&self) -> bool {
        self.finished
    }
}

impl PcmSink for MemoryPcmSink {
    fn write_interleaved_i16(&mut self, samples: &[i16]) -> SynthResult<SinkWrite> {
        if self.finished {
            return Err(SynthError::new(
                "cannot write PCM after the memory sink is finished.",
            ));
        }
        if !samples.len().is_multiple_of(2) {
            return Err(SynthError::new(
                "memory PCM sink requires complete stereo interleaved frames.",
            ));
        }
        self.samples.extend_from_slice(samples);
        Ok(SinkWrite::Accepted)
    }

    fn finish(&mut self) -> SynthResult<()> {
        self.finished = true;
        Ok(())
    }
}

/// Public diagnostics shape for the future one-engine renderer.
///
/// Counters are cumulative for a session. Capacity values describe owned
/// renderer state, not bytes accumulated by an explicit memory-returning sink.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct BlockRenderDiagnostics {
    pub blocks: u64,
    pub rendered_input_frames: u64,
    pub rendered_output_frames: u64,
    pub active_voices: usize,
    pub peak_active_voices: usize,
    pub active_buses: usize,
    pub peak_active_buses: usize,
    pub scratch_current_bytes: usize,
    pub scratch_peak_bytes: usize,
    pub processor_state_bytes: usize,
    pub tail_frames_rendered: u64,
    pub normaliser_latency_frames: usize,
    pub limiter_latency_frames: usize,
    pub sink_would_block_count: u64,
    pub sink_pending_peak_frames: usize,
}

impl BlockRenderDiagnostics {
    pub fn observe_active_state(&mut self, voices: usize, buses: usize) {
        self.active_voices = voices;
        self.peak_active_voices = self.peak_active_voices.max(voices);
        self.active_buses = buses;
        self.peak_active_buses = self.peak_active_buses.max(buses);
    }

    pub fn observe_scratch(&mut self, current_bytes: usize) {
        self.scratch_current_bytes = current_bytes;
        self.scratch_peak_bytes = self.scratch_peak_bytes.max(current_bytes);
    }
}
