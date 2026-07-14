use super::*;

/// Version for the stateful normaliser signal contract.
///
/// This is the canonical normalisation contract for stateful synth sinks. It
/// never scans or retains a complete future signal.
pub const CAUSAL_NORMALISER_CONTRACT_VERSION: u32 = 1;
pub const DEFAULT_CAUSAL_NORMALISER_LOOKAHEAD_SECONDS: f64 = 0.005;
pub const DEFAULT_CAUSAL_NORMALISER_ATTACK_SECONDS: f64 = 0.001;
pub const DEFAULT_CAUSAL_NORMALISER_RELEASE_SECONDS: f64 = 0.050;
pub const DEFAULT_CAUSAL_NORMALISER_TARGET: f64 = 1.0;

/// Immutable configuration for the versioned causal normaliser.
///
/// `lookahead_seconds` is bounded future analysis, not whole-program peak
/// knowledge. The left and right channels always share one gain envelope.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CausalNormaliserConfig {
    pub target: f64,
    pub lookahead_seconds: f64,
    pub attack_seconds: f64,
    pub release_seconds: f64,
}

impl Default for CausalNormaliserConfig {
    fn default() -> Self {
        Self {
            target: DEFAULT_CAUSAL_NORMALISER_TARGET,
            lookahead_seconds: DEFAULT_CAUSAL_NORMALISER_LOOKAHEAD_SECONDS,
            attack_seconds: DEFAULT_CAUSAL_NORMALISER_ATTACK_SECONDS,
            release_seconds: DEFAULT_CAUSAL_NORMALISER_RELEASE_SECONDS,
        }
    }
}

/// Stateful, channel-linked normaliser for a planar stereo block stream.
///
/// Every input frame is delayed by `latency_frames()` so its gain can use the
/// fixed lookahead window. `flush()` must be called by finite sinks to emit the
/// delayed final frames. Open sinks do not flush until they close.
#[derive(Clone, Debug)]
pub struct CausalNormaliser {
    sample_rate: u32,
    config: CausalNormaliserConfig,
    lookahead_frames: usize,
    gain: f64,
    delayed_frames: VecDeque<(f64, f64)>,
}

impl CausalNormaliser {
    pub fn new(sample_rate: u32, config: CausalNormaliserConfig) -> SynthResult<Self> {
        validate_sample_rate(sample_rate)?;
        validate_config(config)?;
        let lookahead_frames = checked_frame_count(
            config.lookahead_seconds,
            sample_rate,
            "causal normaliser lookahead",
            0,
        )?;
        Ok(Self {
            sample_rate,
            config,
            lookahead_frames,
            gain: 1.0,
            delayed_frames: VecDeque::with_capacity(lookahead_frames.saturating_add(1)),
        })
    }

    pub fn contract_version(&self) -> u32 {
        CAUSAL_NORMALISER_CONTRACT_VERSION
    }

    pub fn latency_frames(&self) -> usize {
        self.lookahead_frames
    }

    pub fn is_idle(&self) -> bool {
        self.delayed_frames.is_empty()
    }

    pub fn reset(&mut self) {
        self.gain = 1.0;
        self.delayed_frames.clear();
    }

    /// Process a planar stereo block and return the frames whose fixed
    /// lookahead is now complete. Both channels must contain the same count.
    pub fn process(&mut self, left: &[f64], right: &[f64]) -> SynthResult<(Vec<f64>, Vec<f64>)> {
        let mut out_left = Vec::with_capacity(left.len());
        let mut out_right = Vec::with_capacity(right.len());
        self.process_into(left, right, &mut out_left, &mut out_right)?;
        Ok((out_left, out_right))
    }

    /// Process a block into reusable caller-owned planar buffers.
    ///
    /// The buffers are cleared before output is appended. A block renderer can
    /// retain them at its fixed configured capacity across every render step.
    pub fn process_into(
        &mut self,
        left: &[f64],
        right: &[f64],
        out_left: &mut Vec<f64>,
        out_right: &mut Vec<f64>,
    ) -> SynthResult<()> {
        if left.len() != right.len() {
            return Err(SynthError::new(
                "causal normaliser requires equal-length left and right blocks.",
            ));
        }
        out_left.clear();
        out_right.clear();
        out_left.reserve(left.len());
        out_right.reserve(right.len());
        for (&left_sample, &right_sample) in left.iter().zip(right) {
            if let Some((normalised_left, normalised_right)) =
                self.process_frame(left_sample, right_sample)
            {
                out_left.push(normalised_left);
                out_right.push(normalised_right);
            }
        }
        Ok(())
    }

    /// Finish a finite stream, emitting exactly the outstanding delayed frames.
    pub fn flush(&mut self) -> (Vec<f64>, Vec<f64>) {
        let mut out_left = Vec::with_capacity(self.delayed_frames.len());
        let mut out_right = Vec::with_capacity(self.delayed_frames.len());
        self.flush_into(&mut out_left, &mut out_right);
        (out_left, out_right)
    }

    /// Drain a finite stream into reusable caller-owned planar buffers.
    pub fn flush_into(&mut self, out_left: &mut Vec<f64>, out_right: &mut Vec<f64>) {
        self.flush_up_to_into(usize::MAX, out_left, out_right);
    }

    /// Drain at most `max_frames` from a finite stream.
    ///
    /// Block sinks use this to keep the final latency flush bounded by their
    /// configured block size instead of emitting the entire lookahead queue in
    /// one oversized terminal write.
    pub fn flush_up_to_into(
        &mut self,
        max_frames: usize,
        out_left: &mut Vec<f64>,
        out_right: &mut Vec<f64>,
    ) {
        out_left.clear();
        out_right.clear();
        let frame_count = self.delayed_frames.len().min(max_frames);
        out_left.reserve(frame_count);
        out_right.reserve(frame_count);
        for _ in 0..frame_count {
            let Some((normalised_left, normalised_right)) = self.emit_oldest() else {
                break;
            };
            out_left.push(normalised_left);
            out_right.push(normalised_right);
        }
    }

    pub fn process_frame(&mut self, left: f64, right: f64) -> Option<(f64, f64)> {
        self.delayed_frames.push_back((left, right));
        (self.delayed_frames.len() > self.lookahead_frames)
            .then(|| self.emit_oldest())
            .flatten()
    }

    fn emit_oldest(&mut self) -> Option<(f64, f64)> {
        let linked_peak = self
            .delayed_frames
            .iter()
            .map(|(left, right)| left.abs().max(right.abs()))
            .fold(0.0, f64::max);
        let target_gain = if linked_peak <= f64::EPSILON {
            1.0
        } else {
            self.config.target / linked_peak
        };
        let seconds = if target_gain < self.gain {
            self.config.attack_seconds
        } else {
            self.config.release_seconds
        };
        self.gain = approach_gain(self.gain, target_gain, seconds, self.sample_rate);

        self.delayed_frames
            .pop_front()
            .map(|(left, right)| (left * self.gain, right * self.gain))
    }
}

fn validate_config(config: CausalNormaliserConfig) -> SynthResult<()> {
    for (name, value) in [
        ("target", config.target),
        ("lookahead_seconds", config.lookahead_seconds),
        ("attack_seconds", config.attack_seconds),
        ("release_seconds", config.release_seconds),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(SynthError::new(format!(
                "causal normaliser {name} must be finite and non-negative; got {value}."
            )));
        }
    }
    if config.target <= 0.0 {
        return Err(SynthError::new(
            "causal normaliser target must be greater than zero.",
        ));
    }
    Ok(())
}

fn approach_gain(current: f64, target: f64, seconds: f64, sample_rate: u32) -> f64 {
    if seconds <= 0.0 {
        return target;
    }
    let alpha = 1.0 - (-1.0 / (seconds * sample_rate as f64)).exp();
    current + (target - current) * alpha
}
