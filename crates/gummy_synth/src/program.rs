use super::*;

/// Immutable Rust-owned scheduling form for a physical synth plan.
///
/// This is the canonical boundary between plan decoding and execution. The
/// current full-buffer renderer still consumes the event payloads while the
/// block renderer is migrated, but it no longer needs to sort or convert times
/// during execution.
#[derive(Clone, Debug)]
pub struct CompiledSynthProgram {
    sample_rate: u32,
    duration_seconds: f64,
    duration_frames: usize,
    events: Vec<EventPayload>,
    event_frames: Vec<usize>,
    control_frames: Vec<Vec<usize>>,
}

impl CompiledSynthProgram {
    /// Validate and compile already-typed events into stable frame order.
    pub fn compile(
        events: Vec<EventPayload>,
        duration_seconds: f64,
        sample_rate: u32,
    ) -> SynthResult<Self> {
        let duration_frames = validate_plan_render(&events, duration_seconds, sample_rate)?;
        let mut scheduled = Vec::with_capacity(events.len());
        for event in events {
            let event_frame =
                seconds_to_frame(event.time_seconds, sample_rate, "synth event time")?;
            let mut controls = Vec::with_capacity(event.controls.len());
            for control in &event.controls {
                controls.push(seconds_to_frame(
                    control.time_seconds,
                    sample_rate,
                    "synth control time",
                )?);
            }
            scheduled.push((event, event_frame, controls));
        }
        scheduled.sort_by(|(left, left_frame, _), (right, right_frame, _)| {
            left_frame
                .cmp(right_frame)
                .then_with(|| left.order.cmp(&right.order))
                .then_with(|| left.node_id.cmp(&right.node_id))
        });

        let mut compiled_events = Vec::with_capacity(scheduled.len());
        let mut event_frames = Vec::with_capacity(scheduled.len());
        let mut control_frames = Vec::with_capacity(scheduled.len());
        for (event, event_frame, controls) in scheduled {
            compiled_events.push(event);
            event_frames.push(event_frame);
            control_frames.push(controls);
        }

        Ok(Self {
            sample_rate,
            duration_seconds,
            duration_frames,
            events: compiled_events,
            event_frames,
            control_frames,
        })
    }

    /// Decode and compile a serialized physical plan once for a target rate.
    pub fn from_serialized_plan(payload: &[u8], sample_rate: u32) -> SynthResult<Self> {
        let (events, duration_seconds) = parse_serialized_plan(payload)
            .map_err(|error| SynthError::new(format!("ValueError: {error}")))?;
        Self::compile(events, duration_seconds, sample_rate)
    }

    pub fn sample_rate(&self) -> u32 {
        self.sample_rate
    }

    pub fn duration_seconds(&self) -> f64 {
        self.duration_seconds
    }

    pub fn duration_frames(&self) -> usize {
        self.duration_frames
    }

    pub fn event_count(&self) -> usize {
        self.events.len()
    }

    pub fn event_frame(&self, index: usize) -> Option<usize> {
        self.event_frames.get(index).copied()
    }

    pub fn control_frames(&self, index: usize) -> Option<&[usize]> {
        self.control_frames.get(index).map(Vec::as_slice)
    }

    pub(crate) fn events(&self) -> &[EventPayload] {
        &self.events
    }
}

fn seconds_to_frame(seconds: f64, sample_rate: u32, label: &str) -> SynthResult<usize> {
    validate_finite_non_negative(seconds, label)?;
    validate_sample_rate(sample_rate)?;
    let frame = (seconds * sample_rate as f64).round();
    if !frame.is_finite() || frame > MAX_OUTPUT_FRAMES as f64 {
        return Err(SynthError::new(format!(
            "{label} exceeds the synth output budget of {MAX_OUTPUT_FRAMES} frames."
        )));
    }
    Ok(frame as usize)
}
