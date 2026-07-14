//! Stateful, bounded block renderer for compiled synth programs.
//!
//! The renderer owns source, automation, filter, processor, limiter, and
//! normaliser state across arbitrary block partitions. It currently supports all
//! primitive oscillator families, layered oscillator banks, sample readers, and
//! a reviewed subset of stateful FX. FX handles are compiled into a shared bus
//! graph; unsupported processors fail during construction and are never
//! delegated to the legacy duration-sized renderer.

use super::*;
use crate::program::{CompiledBlockFxKind, CompiledEventData, CompiledEventKind, CompiledFxData};

#[derive(Clone)]
struct AutomationPoint {
    frame: usize,
    start: f64,
    target: f64,
    slide_frames: usize,
}

#[derive(Clone)]
struct AutomationCursor {
    initial: f64,
    points: Vec<AutomationPoint>,
    next_point: usize,
    active_point: Option<usize>,
}

impl AutomationCursor {
    fn compile(
        initial: f64,
        name: &str,
        controls: &[ControlPayload],
        control_frames: &[usize],
        event_frame: usize,
        sample_rate: u32,
    ) -> SynthResult<Self> {
        if controls.len() != control_frames.len() {
            return Err(SynthError::new(
                "stateful renderer control-frame schedule is malformed.",
            ));
        }
        let slide_name = format!("{name}_slide");
        let mut points: Vec<AutomationPoint> = Vec::new();
        for (control, &absolute_frame) in controls.iter().zip(control_frames) {
            let Some(target) = control.opts.get(name).and_then(value_as_f64) else {
                continue;
            };
            if !target.is_finite() {
                return Err(SynthError::new(format!(
                    "stateful {name} control target must be finite."
                )));
            }
            let slide_seconds = control
                .opts
                .get(&slide_name)
                .and_then(value_as_f64)
                .unwrap_or(0.0);
            if !slide_seconds.is_finite() || slide_seconds < 0.0 {
                return Err(SynthError::new(format!(
                    "stateful {slide_name} must be finite and non-negative."
                )));
            }
            let frame = absolute_frame.saturating_sub(event_frame);
            let slide_frames = checked_frame_count(
                slide_seconds,
                sample_rate,
                &format!("stateful {slide_name}"),
                0,
            )?;
            let start = automation_value_at(&points, initial, frame);
            if points.last().is_some_and(|point| point.frame == frame) {
                let previous = points.pop().expect("same-frame point exists");
                points.push(AutomationPoint {
                    frame,
                    start: previous.start,
                    target,
                    slide_frames,
                });
            } else {
                points.push(AutomationPoint {
                    frame,
                    start,
                    target,
                    slide_frames,
                });
            }
        }
        Ok(Self {
            initial,
            points,
            next_point: 0,
            active_point: None,
        })
    }

    fn value_at(&mut self, frame: usize) -> f64 {
        while self
            .points
            .get(self.next_point)
            .is_some_and(|point| point.frame <= frame)
        {
            self.active_point = Some(self.next_point);
            self.next_point += 1;
        }
        self.active_point.map_or(self.initial, |index| {
            point_value(&self.points[index], frame)
        })
    }

    fn has_points(&self) -> bool {
        !self.points.is_empty()
    }

    fn state_bytes(&self) -> usize {
        self.points.capacity() * std::mem::size_of::<AutomationPoint>()
    }
}

fn automation_value_at(points: &[AutomationPoint], initial: f64, frame: usize) -> f64 {
    points
        .iter()
        .rev()
        .find(|point| point.frame <= frame)
        .map_or(initial, |point| point_value(point, frame))
}

fn point_value(point: &AutomationPoint, frame: usize) -> f64 {
    if point.slide_frames == 0 || frame >= point.frame.saturating_add(point.slide_frames) {
        point.target
    } else {
        let amount = frame.saturating_sub(point.frame) as f64 / point.slide_frames as f64;
        point.start + (point.target - point.start) * amount
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum EnvelopeStage {
    Attack,
    Decay,
    Sustain,
    Release,
    Done,
}

#[derive(Clone)]
struct EnvelopeState {
    stage: EnvelopeStage,
    attack: f64,
    decay: f64,
    sustain: f64,
    release: f64,
    attack_level: f64,
    decay_level: f64,
    sustain_level: f64,
    curve: i32,
}

impl EnvelopeState {
    #[allow(clippy::too_many_arguments)]
    fn new(
        attack: f64,
        decay: f64,
        sustain: f64,
        release: f64,
        attack_level: f64,
        decay_level: f64,
        sustain_level: f64,
        curve: i32,
    ) -> Self {
        let stage = if attack > 0.0 {
            EnvelopeStage::Attack
        } else if decay > 0.0 {
            EnvelopeStage::Decay
        } else if sustain > 0.0 {
            EnvelopeStage::Sustain
        } else if release > 0.0 {
            EnvelopeStage::Release
        } else {
            EnvelopeStage::Done
        };
        Self {
            stage,
            attack,
            decay,
            sustain,
            release,
            attack_level,
            decay_level,
            sustain_level,
            curve,
        }
    }

    fn level_at(&mut self, frame: usize, sample_rate: u32) -> f64 {
        let elapsed = frame as f64 / sample_rate as f64;
        loop {
            match self.stage {
                EnvelopeStage::Attack => {
                    if elapsed < self.attack {
                        return shaped_interpolate(
                            0.0,
                            self.attack_level,
                            elapsed / self.attack,
                            self.curve,
                        );
                    }
                    self.stage = if self.decay > 0.0 {
                        EnvelopeStage::Decay
                    } else if self.sustain > 0.0 {
                        EnvelopeStage::Sustain
                    } else if self.release > 0.0 {
                        EnvelopeStage::Release
                    } else {
                        EnvelopeStage::Done
                    };
                }
                EnvelopeStage::Decay => {
                    let stage_elapsed = elapsed - self.attack;
                    if stage_elapsed < self.decay {
                        return shaped_interpolate(
                            self.attack_level,
                            self.decay_level,
                            stage_elapsed / self.decay,
                            self.curve,
                        );
                    }
                    self.stage = if self.sustain > 0.0 {
                        EnvelopeStage::Sustain
                    } else if self.release > 0.0 {
                        EnvelopeStage::Release
                    } else {
                        EnvelopeStage::Done
                    };
                }
                EnvelopeStage::Sustain => {
                    if elapsed - self.attack - self.decay < self.sustain {
                        return self.sustain_level;
                    }
                    self.stage = if self.release > 0.0 {
                        EnvelopeStage::Release
                    } else {
                        EnvelopeStage::Done
                    };
                }
                EnvelopeStage::Release => {
                    if self.release <= 0.0 {
                        self.stage = EnvelopeStage::Done;
                        continue;
                    }
                    let stage_elapsed = elapsed - self.attack - self.decay - self.sustain;
                    if stage_elapsed >= self.release {
                        self.stage = EnvelopeStage::Done;
                        continue;
                    }
                    return shaped_interpolate(
                        self.sustain_level,
                        0.0,
                        stage_elapsed / self.release,
                        self.curve,
                    )
                    .max(0.0);
                }
                EnvelopeStage::Done => return 0.0,
            }
        }
    }
}

#[derive(Clone)]
struct StereoFilterState {
    left: BiquadState,
    right: BiquadState,
}

impl StereoFilterState {
    fn process_coefficients(
        &mut self,
        left: f64,
        right: f64,
        coefficients: BiquadCoefficients,
    ) -> (f64, f64) {
        (
            self.left.process(left, coefficients),
            self.right.process(right, coefficients),
        )
    }

    fn process(
        &mut self,
        left: f64,
        right: f64,
        kind: FilterKind,
        cutoff_hz: f64,
        sample_rate: u32,
        resonance: f64,
    ) -> (f64, f64) {
        let coefficients = if resonance > 0.0 {
            BiquadCoefficients::resonant_filter(
                kind,
                cutoff_hz,
                sample_rate,
                sonic_filter_rq(resonance),
            )
        } else {
            BiquadCoefficients::filter(kind, cutoff_hz, sample_rate, 0.707)
        };
        self.process_coefficients(left, right, coefficients)
    }
}

#[derive(Clone)]
struct SourceFilter {
    state: StereoFilterState,
    cutoff: AutomationCursor,
    resonance: AutomationCursor,
    static_coefficients: Option<BiquadCoefficients>,
}

impl SourceFilter {
    fn process(&mut self, left: f64, right: f64, frame: usize, sample_rate: u32) -> (f64, f64) {
        if let Some(coefficients) = self.static_coefficients {
            return self.state.process_coefficients(left, right, coefficients);
        }
        let cutoff_note = self.cutoff.value_at(frame);
        if cutoff_note <= 0.0 || cutoff_note >= 130.5 {
            return (left, right);
        }
        self.state.process(
            left,
            right,
            FilterKind::Low,
            note_frequency(cutoff_note).clamp(20.0, sample_rate as f64 * 0.45),
            sample_rate,
            self.resonance.value_at(frame).clamp(0.0, 0.99),
        )
    }

    fn state_bytes(&self) -> usize {
        std::mem::size_of::<Self>() + self.cutoff.state_bytes() + self.resonance.state_bytes()
    }
}

#[derive(Clone)]
struct DcBlocker {
    previous_input_left: f64,
    previous_input_right: f64,
    previous_output_left: f64,
    previous_output_right: f64,
}

impl DcBlocker {
    fn process(&mut self, left: f64, right: f64) -> (f64, f64) {
        let output_left = left - self.previous_input_left + 0.995 * self.previous_output_left;
        let output_right = right - self.previous_input_right + 0.995 * self.previous_output_right;
        self.previous_input_left = left;
        self.previous_input_right = right;
        self.previous_output_left = output_left;
        self.previous_output_right = output_right;
        (output_left, output_right)
    }
}

#[derive(Clone)]
struct OscillatorLane {
    kind: SynthKind,
    waveform: &'static str,
    phase: f64,
    base_note: f64,
    static_phase_delta: f64,
    transpose: f64,
    gain: f64,
    fm_divisor: f64,
    fm_depth: f64,
    pulse_width: f64,
    noise_index: usize,
}

#[derive(Clone)]
struct OscillatorSource {
    lanes: Vec<OscillatorLane>,
    base_note_count: usize,
    rendered_frames: usize,
    total_frames: usize,
    envelope: EnvelopeState,
    amplitude: AutomationCursor,
    pan: AutomationCursor,
    static_pan_gains: Option<(f64, f64)>,
    note: Option<AutomationCursor>,
    note_root: Option<f64>,
    pulse_width: AutomationCursor,
    filter: Option<SourceFilter>,
    normalise_level: Option<f64>,
    linked_peak: f64,
    dc_blocker: Option<DcBlocker>,
    stochastic_identity: u64,
}

impl OscillatorSource {
    fn from_event(
        event: &EventPayload,
        execution: &CompiledEventData,
        sample_rate: u32,
        control_frames: &[usize],
    ) -> SynthResult<Self> {
        let kind = execution.synth_kind;
        if kind == SynthKind::Unknown {
            return Err(SynthError::new(format!(
                "unsupported primitive synth {:?}; no sine substitution is available.",
                event.synth_name
            )));
        }
        let opts = &execution.options;
        let event_frame = execution.frame.as_usize();
        validate_source_control_keys(
            event,
            &["note", "amp", "pan", "pulse_width", "cutoff", "res"],
        )?;
        validate_option_keys(
            opts,
            &[
                "note",
                "attack",
                "decay",
                "sustain",
                "release",
                "attack_level",
                "decay_level",
                "sustain_level",
                "env_curve",
                "amp",
                "amp_slide",
                "pan",
                "pan_slide",
                "note_slide",
                "pulse_width",
                "pulse_width_slide",
                "cutoff",
                "cutoff_slide",
                "res",
                "res_slide",
                "amp_fudge",
                "divisor",
                "depth",
                "layers",
                "leak_dc",
                "normalise",
                "normalize",
                "norm",
                "normalise_level",
                "normalize_level",
                "metadata",
            ],
            "stateful oscillator option",
        )?;
        let note_source = opts.get("note").unwrap_or(&event.value);
        let notes = note_values(note_source)?;
        let active_notes: Vec<f64> = notes.into_iter().flatten().collect();
        let (default_attack, default_decay, default_sustain, default_release) =
            default_synth_envelope(kind);
        let attack = float_opt(opts, "attack", default_attack).max(0.0);
        let decay = float_opt(opts, "decay", default_decay).max(0.0);
        let sustain = float_opt(opts, "sustain", default_sustain).max(0.0);
        let release = float_opt(opts, "release", default_release).max(0.0);
        let total_seconds = (attack + decay + sustain + release)
            .max(natural_synth_tail(kind, opts))
            .max(0.01);
        let total_frames = checked_frame_count(
            total_seconds,
            sample_rate,
            "stateful oscillator envelope duration",
            1,
        )?;
        let layers = if kind == SynthKind::Layered {
            Some(layered_specs(opts)?)
        } else {
            None
        };
        let mut lanes = Vec::new();
        for (note_index, note) in active_notes.iter().copied().enumerate() {
            if let Some(layers) = &layers {
                for (layer_index, layer) in layers.iter().enumerate() {
                    lanes.push(OscillatorLane {
                        kind: layer.kind,
                        waveform: layer.waveform,
                        phase: 0.0,
                        base_note: note,
                        static_phase_delta: note_frequency(note + layer.transpose).max(0.0)
                            / sample_rate as f64,
                        transpose: layer.transpose,
                        gain: layer.amp,
                        fm_divisor: float_opt(&layer.opts, "divisor", 2.0).abs().max(0.001),
                        fm_depth: float_opt(&layer.opts, "depth", 1.0),
                        pulse_width: float_opt(&layer.opts, "pulse_width", 0.5),
                        noise_index: note_index * layers.len() + layer_index,
                    });
                }
            } else if kind != SynthKind::Silence {
                lanes.push(OscillatorLane {
                    kind,
                    waveform: synth_waveform(kind, opts),
                    phase: 0.0,
                    base_note: note,
                    static_phase_delta: note_frequency(note).max(0.0) / sample_rate as f64,
                    transpose: 0.0,
                    gain: 1.0,
                    fm_divisor: float_opt(opts, "divisor", 2.0).abs().max(0.001),
                    fm_depth: float_opt(opts, "depth", 1.0),
                    pulse_width: float_opt(opts, "pulse_width", 0.5),
                    noise_index: note_index,
                });
            }
        }
        let note_root = active_notes.first().copied();
        let note = note_root
            .map(|root| {
                AutomationCursor::compile(
                    root,
                    "note",
                    &event.controls,
                    control_frames,
                    event_frame,
                    sample_rate,
                )
            })
            .transpose()?
            .filter(AutomationCursor::has_points);
        let cutoff = AutomationCursor::compile(
            float_opt(opts, "cutoff", default_synth_cutoff(kind)),
            "cutoff",
            &event.controls,
            control_frames,
            event_frame,
            sample_rate,
        )?;
        let resonance = AutomationCursor::compile(
            float_opt(opts, "res", default_synth_res(kind)),
            "res",
            &event.controls,
            control_frames,
            event_frame,
            sample_rate,
        )?;
        let filter_is_static = !cutoff.has_points() && !resonance.has_points();
        let static_coefficients =
            (filter_is_static && cutoff.initial > 0.0 && cutoff.initial < 130.5).then(|| {
                let cutoff_hz =
                    note_frequency(cutoff.initial).clamp(20.0, sample_rate as f64 * 0.45);
                if resonance.initial > 0.0 {
                    BiquadCoefficients::resonant_filter(
                        FilterKind::Low,
                        cutoff_hz,
                        sample_rate,
                        sonic_filter_rq(resonance.initial.clamp(0.0, 0.99)),
                    )
                } else {
                    BiquadCoefficients::filter(FilterKind::Low, cutoff_hz, sample_rate, 0.707)
                }
            });
        let filter = (cutoff.initial < 130.5 || cutoff.has_points()).then(|| SourceFilter {
            state: StereoFilterState {
                left: BiquadState::default(),
                right: BiquadState::default(),
            },
            cutoff,
            resonance,
            static_coefficients,
        });
        let sustain_level = float_opt(opts, "sustain_level", 1.0).max(0.0);
        let attack_level = float_opt(opts, "attack_level", 1.0).max(0.0);
        let decay_level = decay_level_opt(opts, sustain_level);
        let env_curve = float_opt(opts, "env_curve", 1.0).round() as i32;
        let pan = AutomationCursor::compile(
            float_opt(opts, "pan", 0.0),
            "pan",
            &event.controls,
            control_frames,
            event_frame,
            sample_rate,
        )?;
        let static_pan_gains = (!pan.has_points()).then(|| pan_gains(pan.initial));
        Ok(Self {
            lanes,
            base_note_count: active_notes.len(),
            rendered_frames: 0,
            total_frames,
            envelope: EnvelopeState::new(
                attack,
                decay,
                sustain,
                release,
                attack_level,
                decay_level,
                sustain_level,
                env_curve,
            ),
            amplitude: AutomationCursor::compile(
                float_opt(opts, "amp", 1.0).max(0.0) * synth_amp_fudge(kind, opts),
                "amp",
                &event.controls,
                control_frames,
                event_frame,
                sample_rate,
            )?,
            pan,
            static_pan_gains,
            note,
            note_root,
            pulse_width: AutomationCursor::compile(
                float_opt(opts, "pulse_width", 0.5),
                "pulse_width",
                &event.controls,
                control_frames,
                event_frame,
                sample_rate,
            )?,
            filter,
            normalise_level: synth_normalise_enabled(kind, opts).then(|| {
                float_opt(
                    opts,
                    "normalise_level",
                    float_opt(opts, "normalize_level", 1.0),
                )
                .max(0.0)
            }),
            linked_peak: 0.0,
            dc_blocker: bool_opt(opts, "leak_dc", false).then_some(DcBlocker {
                previous_input_left: 0.0,
                previous_input_right: 0.0,
                previous_output_left: 0.0,
                previous_output_right: 0.0,
            }),
            stochastic_identity: stochastic_identity(event.seed, event.node_id),
        })
    }

    fn next_sample(&mut self, sample_rate: u32) -> Option<(f64, f64)> {
        if self.rendered_frames >= self.total_frames {
            return None;
        }
        let frame = self.rendered_frames;
        let envelope = self.envelope.level_at(frame, sample_rate);
        let automated_note = self.note.as_mut().map(|note| note.value_at(frame));
        let pulse_width = self.pulse_width.value_at(frame).clamp(0.001, 0.999);
        let mut mono = 0.0;
        for lane in &mut self.lanes {
            let phase_delta = automated_note.map_or(lane.static_phase_delta, |root| {
                let midi_note = root + lane.base_note - self.note_root.unwrap_or(lane.base_note)
                    + lane.transpose;
                note_frequency(midi_note).max(0.0) / sample_rate as f64
            });
            let value = match lane.kind {
                SynthKind::Fm => {
                    let modulator = (TAU * lane.phase / lane.fm_divisor).sin();
                    (TAU * lane.phase + modulator * lane.fm_depth * lane.fm_divisor * envelope)
                        .sin()
                }
                SynthKind::Noise
                | SynthKind::PinkNoise
                | SynthKind::BrownNoise
                | SynthKind::GreyNoise
                | SynthKind::ClipNoise => {
                    noise_voice(lane.kind, frame, lane.noise_index, self.stochastic_identity)
                }
                _ => oscillator_value_with_width(
                    lane.waveform,
                    lane.phase,
                    phase_delta,
                    if lane.kind == SynthKind::Pulse {
                        pulse_width
                    } else {
                        lane.pulse_width
                    },
                ),
            };
            mono += value * lane.gain;
            lane.phase = (lane.phase + phase_delta).rem_euclid(1.0);
        }
        if self.base_note_count > 0 {
            mono /= self.base_note_count as f64;
        }
        let mut pair = (mono, mono);
        if let Some(filter) = &mut self.filter {
            pair = filter.process(pair.0, pair.1, frame, sample_rate);
        }
        if let Some(level) = self.normalise_level {
            self.linked_peak = self.linked_peak.max(pair.0.abs().max(pair.1.abs()));
            if self.linked_peak > 1e-9 && level > 0.0 {
                let gain = level / self.linked_peak;
                pair = (pair.0 * gain, pair.1 * gain);
            }
        }
        let amplitude = self.amplitude.value_at(frame).max(0.0) * envelope;
        let (left_gain, right_gain) = self
            .static_pan_gains
            .unwrap_or_else(|| pan_gains(self.pan.value_at(frame)));
        pair = (
            pair.0 * amplitude * left_gain,
            pair.1 * amplitude * right_gain,
        );
        if let Some(blocker) = &mut self.dc_blocker {
            pair = blocker.process(pair.0, pair.1);
        }
        self.rendered_frames += 1;
        Some(pair)
    }

    fn state_bytes(&self) -> usize {
        self.lanes.capacity() * std::mem::size_of::<OscillatorLane>()
            + self.amplitude.state_bytes()
            + self.pan.state_bytes()
            + self.pulse_width.state_bytes()
            + self.note.as_ref().map_or(0, AutomationCursor::state_bytes)
            + self.filter.as_ref().map_or(0, SourceFilter::state_bytes)
    }
}

#[derive(Clone)]
struct SampleSourceState {
    source: SampleSource,
    low: usize,
    high: usize,
    position: f64,
    reverse: bool,
    rendered_frames: usize,
    envelope_frames: usize,
    envelope: EnvelopeState,
    pre_amp: f64,
    amplitude: AutomationCursor,
    pan: AutomationCursor,
    static_pan_gains: Option<(f64, f64)>,
    rate: AutomationCursor,
    filter: Option<StereoFilterState>,
    static_filter_coefficients: Option<BiquadCoefficients>,
    cutoff_note: f64,
    resonance: f64,
    anti_alias: bool,
}

impl SampleSourceState {
    fn from_event(
        event: &EventPayload,
        execution: &CompiledEventData,
        sample_rate: u32,
        control_frames: &[usize],
    ) -> SynthResult<Self> {
        let opts = &execution.options;
        let event_frame = execution.frame.as_usize();
        validate_source_control_keys(event, &["amp", "pan", "rate"])?;
        validate_option_keys(
            opts,
            &[
                "start",
                "finish",
                "rate",
                "rate_slide",
                "rpitch",
                "pitch",
                "beat_stretch",
                "attack",
                "sustain",
                "release",
                "env_curve",
                "amp",
                "amp_slide",
                "pan",
                "pan_slide",
                "pre_amp",
                "anti_alias",
                "cutoff",
                "res",
                "metadata",
            ],
            "stateful sample option",
        )?;
        let source = sample_source(&event.value, sample_rate)?;
        let start = float_opt(opts, "start", 0.0).clamp(0.0, 1.0);
        let finish = float_opt(opts, "finish", 1.0).clamp(0.0, 1.0);
        let mut initial_rate = float_opt(opts, "rate", 1.0);
        if opts.contains_key("rpitch") {
            initial_rate *= 2.0_f64.powf(float_opt(opts, "rpitch", 0.0) / 12.0);
        }
        if opts.contains_key("pitch") {
            initial_rate *= 2.0_f64.powf(float_opt(opts, "pitch", 0.0) / 12.0);
        }
        if opts.contains_key("beat_stretch") {
            initial_rate = source.duration / float_opt(opts, "beat_stretch", 1.0).max(0.001);
        }
        if initial_rate == 0.0 {
            return Err(SynthError::new("sample rate cannot be zero."));
        }
        for control in &event.controls {
            if control
                .opts
                .get("rate")
                .and_then(value_as_f64)
                .is_some_and(|rate| rate <= 0.0)
            {
                return Err(SynthError::new(
                    "sample rate controls must be positive; dynamic reverse playback is unsupported.",
                ));
            }
        }
        let reverse = initial_rate < 0.0 || start > finish;
        let low_fraction = start.min(finish);
        let high_fraction = start.max(finish);
        let low = (low_fraction * source.len() as f64) as usize;
        let high = ((high_fraction * source.len() as f64) as usize)
            .max(low.saturating_add(1))
            .min(source.len());
        let source_frames = high.saturating_sub(low);
        let estimated_output_frames =
            ((source_frames as f64 / initial_rate.abs()).ceil() as usize).max(1);
        let attack = float_opt(opts, "attack", 0.0).max(0.0);
        let release = float_opt(opts, "release", 0.0).max(0.0);
        let estimated_seconds = estimated_output_frames as f64 / sample_rate as f64;
        let sustain = opts
            .get("sustain")
            .and_then(value_as_f64)
            .filter(|value| *value >= 0.0)
            .unwrap_or((estimated_seconds - attack - release).max(0.0));
        let envelope_frames = checked_frame_count(
            attack + sustain + release,
            sample_rate,
            "stateful sample envelope duration",
            1,
        )?;
        let cutoff_note = float_opt(opts, "cutoff", 131.0);
        let anti_alias = bool_opt(opts, "anti_alias", true);
        let pan = AutomationCursor::compile(
            float_opt(opts, "pan", 0.0),
            "pan",
            &event.controls,
            control_frames,
            event_frame,
            sample_rate,
        )?;
        let static_pan_gains = (!pan.has_points()).then(|| pan_gains(pan.initial));
        let rate = AutomationCursor::compile(
            initial_rate.abs(),
            "rate",
            &event.controls,
            control_frames,
            event_frame,
            sample_rate,
        )?;
        let static_filter_coefficients =
            (!rate.has_points() && (cutoff_note < 130.5 || anti_alias)).then(|| {
                let mut cutoff_hz = if cutoff_note > 0.0 && cutoff_note < 130.5 {
                    note_frequency(cutoff_note)
                } else {
                    sample_rate as f64 * 0.45
                };
                if anti_alias && rate.initial > 1.0 {
                    cutoff_hz = cutoff_hz.min(sample_rate as f64 * 0.45 / rate.initial.sqrt());
                }
                if float_opt(opts, "res", 0.0) > 0.0 {
                    BiquadCoefficients::resonant_filter(
                        FilterKind::Low,
                        cutoff_hz.max(20.0),
                        sample_rate,
                        sonic_filter_rq(float_opt(opts, "res", 0.0).clamp(0.0, 0.99)),
                    )
                } else {
                    BiquadCoefficients::filter(
                        FilterKind::Low,
                        cutoff_hz.max(20.0),
                        sample_rate,
                        0.707,
                    )
                }
            });
        Ok(Self {
            source,
            low,
            high,
            position: if reverse {
                high.saturating_sub(1) as f64
            } else {
                low as f64
            },
            reverse,
            rendered_frames: 0,
            envelope_frames,
            envelope: EnvelopeState::new(
                attack,
                0.0,
                sustain,
                release,
                1.0,
                1.0,
                1.0,
                float_opt(opts, "env_curve", 1.0).round() as i32,
            ),
            pre_amp: float_opt(opts, "pre_amp", 1.0).max(0.0),
            amplitude: AutomationCursor::compile(
                float_opt(opts, "amp", 1.0).max(0.0),
                "amp",
                &event.controls,
                control_frames,
                event_frame,
                sample_rate,
            )?,
            pan,
            static_pan_gains,
            rate,
            filter: (cutoff_note < 130.5 || anti_alias).then(|| StereoFilterState {
                left: BiquadState::default(),
                right: BiquadState::default(),
            }),
            static_filter_coefficients,
            cutoff_note,
            resonance: float_opt(opts, "res", 0.0).clamp(0.0, 0.99),
            anti_alias,
        })
    }

    fn next_sample(&mut self, sample_rate: u32) -> Option<(f64, f64)> {
        if self.low >= self.high
            || self.position < self.low as f64
            || self.position > self.high.saturating_sub(1) as f64
        {
            return None;
        }
        let frame = self.rendered_frames;
        let rate = self.rate.value_at(frame);
        if rate <= 0.0 {
            return None;
        }
        let left = sample_between(&self.source.left, self.position, self.low, self.high);
        let right = sample_between(&self.source.right, self.position, self.low, self.high);
        let envelope = self.envelope.level_at(frame, sample_rate);
        let amp = self.amplitude.value_at(frame).max(0.0) * envelope * self.pre_amp;
        let pan = self.pan.value_at(frame);
        let mut pair = if self.source.stereo {
            balance2_sample(left * amp, right * amp, pan)
        } else {
            let (left_gain, right_gain) = self.static_pan_gains.unwrap_or_else(|| pan_gains(pan));
            (left * amp * left_gain, left * amp * right_gain)
        };
        if let Some(filter) = &mut self.filter {
            if let Some(coefficients) = self.static_filter_coefficients {
                pair = filter.process_coefficients(pair.0, pair.1, coefficients);
            } else {
                let mut cutoff_hz = if self.cutoff_note > 0.0 && self.cutoff_note < 130.5 {
                    note_frequency(self.cutoff_note)
                } else {
                    sample_rate as f64 * 0.45
                };
                if self.anti_alias && rate > 1.0 {
                    cutoff_hz = cutoff_hz.min(sample_rate as f64 * 0.45 / rate.sqrt());
                }
                pair = filter.process(
                    pair.0,
                    pair.1,
                    FilterKind::Low,
                    cutoff_hz.max(20.0),
                    sample_rate,
                    self.resonance,
                );
            }
        }
        self.position += if self.reverse { -rate } else { rate };
        self.rendered_frames += 1;
        if self.rendered_frames > MAX_OUTPUT_FRAMES
            || self.rendered_frames > self.envelope_frames * 64
        {
            return None;
        }
        Some(pair)
    }

    fn state_bytes(&self) -> usize {
        // Decoded source storage belongs to the shared sample cache, not renderer workspace.
        self.amplitude.state_bytes() + self.pan.state_bytes() + self.rate.state_bytes()
    }
}

fn sample_between(samples: &[f64], position: f64, low: usize, high: usize) -> f64 {
    if low >= high || samples.is_empty() {
        return 0.0;
    }
    let position = position.clamp(low as f64, high.saturating_sub(1) as f64);
    let lower = position.floor() as usize;
    let upper = (lower + 1).min(high - 1);
    let fraction = position - lower as f64;
    samples[lower] * (1.0 - fraction) + samples[upper] * fraction
}

#[derive(Clone)]
enum ActiveSource {
    Oscillator(OscillatorSource),
    Sample(SampleSourceState),
}

impl ActiveSource {
    fn from_event(
        event: &EventPayload,
        execution: &CompiledEventData,
        sample_rate: u32,
        control_frames: &[usize],
    ) -> SynthResult<Self> {
        match execution.kind {
            CompiledEventKind::Play => {
                OscillatorSource::from_event(event, execution, sample_rate, control_frames)
                    .map(Self::Oscillator)
            }
            CompiledEventKind::Sample => {
                SampleSourceState::from_event(event, execution, sample_rate, control_frames)
                    .map(Self::Sample)
            }
        }
    }

    fn next_sample(&mut self, sample_rate: u32) -> Option<(f64, f64)> {
        match self {
            Self::Oscillator(source) => source.next_sample(sample_rate),
            Self::Sample(source) => source.next_sample(sample_rate),
        }
    }

    fn state_bytes(&self) -> usize {
        match self {
            Self::Oscillator(source) => source.state_bytes(),
            Self::Sample(source) => source.state_bytes(),
        }
    }
}

#[derive(Clone)]
struct EchoState {
    left: Vec<f64>,
    right: Vec<f64>,
    index: usize,
    feedback: f64,
    tail_frames: usize,
}

#[derive(Clone)]
struct CompressorState {
    gain: f64,
    threshold: f64,
    slope_above: f64,
    slope_below: f64,
    attack_alpha: f64,
    release_alpha: f64,
}

#[derive(Clone)]
struct BitcrusherState {
    hold_frames: usize,
    remaining: usize,
    levels: f64,
    held_left: f64,
    held_right: f64,
}

#[derive(Clone)]
struct CombState {
    buffer: Vec<f64>,
    index: usize,
    filter_store: f64,
}

impl CombState {
    fn new(size: usize) -> Self {
        Self {
            buffer: vec![0.0; size.max(1)],
            index: 0,
            filter_store: 0.0,
        }
    }

    fn process(&mut self, input: f64, feedback: f64, damp1: f64, damp2: f64) -> f64 {
        let output = self.buffer[self.index];
        self.filter_store = output * damp2 + self.filter_store * damp1;
        self.buffer[self.index] = input + self.filter_store * feedback;
        self.index = (self.index + 1) % self.buffer.len();
        output
    }
}

#[derive(Clone)]
struct AllpassState {
    buffer: Vec<f64>,
    index: usize,
}

impl AllpassState {
    fn new(size: usize) -> Self {
        Self {
            buffer: vec![0.0; size.max(1)],
            index: 0,
        }
    }

    fn process(&mut self, input: f64) -> f64 {
        let buffered = self.buffer[self.index];
        let output = buffered - input;
        self.buffer[self.index] = input + buffered * 0.5;
        self.index = (self.index + 1) % self.buffer.len();
        output
    }
}

#[derive(Clone)]
struct ReverbState {
    combs_left: Vec<CombState>,
    combs_right: Vec<CombState>,
    allpasses_left: Vec<AllpassState>,
    allpasses_right: Vec<AllpassState>,
    feedback: f64,
    damp1: f64,
    damp2: f64,
    internal_mix: f64,
    wet1: f64,
    wet2: f64,
    tail_frames: usize,
}

#[derive(Clone)]
struct GverbState {
    left: Vec<f64>,
    right: Vec<f64>,
    index: usize,
    delays: Vec<(usize, f64)>,
    spread: f64,
    dry: f64,
    filter: Option<StereoFilterState>,
    damp_cutoff: f64,
    tail_frames: usize,
}

#[derive(Clone)]
struct SlicerState {
    phase: f64,
    wave: i32,
    amp_min: f64,
    amp_max: f64,
    phase_offset: f64,
    pulse_width: f64,
    invert: bool,
    alpha_smooth: f64,
    alpha_up: f64,
    alpha_down: f64,
    control_alpha: f64,
    lag_ud: Option<f64>,
    lag: Option<f64>,
    control: Option<f64>,
}

#[derive(Clone)]
struct PanSlicerState {
    phase: f64,
    wave: i32,
    pan_min: f64,
    pan_max: f64,
    phase_offset: f64,
    pulse_width: f64,
    invert: bool,
    alpha: f64,
    previous: f64,
    stereo_invert: bool,
}

#[derive(Clone)]
struct ModFilterState {
    phase: f64,
    wave: i32,
    cutoff_min_hz: f64,
    cutoff_max_hz: f64,
    phase_offset: f64,
    pulse_width: f64,
    invert: bool,
    kind: FilterKind,
    rq: f64,
    output_gain: f64,
    state: StereoFilterState,
}

#[derive(Clone)]
struct BandFilterState {
    high: StereoFilterState,
    low: StereoFilterState,
    low_cut: f64,
    high_cut: f64,
    resonance: f64,
    gain: f64,
    normalise_level: Option<f64>,
    linked_peak: f64,
}

#[derive(Clone)]
struct PitchState {
    left: Vec<f64>,
    right: Vec<f64>,
    write: usize,
    filled: usize,
    delay: f64,
    ratio: f64,
}

#[derive(Clone, Default)]
struct OctaverChannel {
    previous: f64,
    sub_sign: f64,
    subsub_sign: f64,
    sub_crossings: usize,
    subsub_crossings: usize,
}

#[derive(Clone)]
struct FlangerState {
    left: Vec<f64>,
    right: Vec<f64>,
    write: usize,
    phase: f64,
    wave: i32,
    delay_ms: f64,
    depth_ms: f64,
    feedback: f64,
    delayed_left: f64,
    delayed_right: f64,
    invert: bool,
    stereo_invert: bool,
    phase_offset: f64,
    pulse_width: f64,
    invert_wave: bool,
}

#[derive(Clone)]
enum BlockFxKind {
    Chain(Vec<BlockFx>),
    Level,
    Distortion {
        amount: f64,
    },
    Tanh {
        krunch: f64,
    },
    Pan {
        pan: f64,
    },
    RingMod {
        frequency: f64,
        amount: f64,
    },
    Filter {
        coefficients: BiquadCoefficients,
        state: StereoFilterState,
        normalise_level: Option<f64>,
        linked_peak: f64,
    },
    Compressor(CompressorState),
    Echo(EchoState),
    Bitcrusher(BitcrusherState),
    Krush {
        gain: f64,
        resonance: f64,
        filter: StereoFilterState,
        coefficients: BiquadCoefficients,
    },
    Normaliser(CausalNormaliser),
    Reverb(ReverbState),
    Gverb(GverbState),
    Slicer(SlicerState),
    PanSlicer(PanSlicerState),
    ModFilter(ModFilterState),
    BandFilter(BandFilterState),
    PitchShift(PitchState),
    Octaver {
        filter: StereoFilterState,
        left: OctaverChannel,
        right: OctaverChannel,
        super_amp: f64,
        sub_amp: f64,
        subsub_amp: f64,
    },
    Vowel {
        bands: Box<[BandFilterState; 3]>,
        gains: [f64; 3],
    },
    Flanger(FlangerState),
}

fn compile_reverb_state(opts: &OptMap, sample_rate: u32) -> SynthResult<ReverbState> {
    let room = float_opt(opts, "room", 0.6).clamp(0.0, 1.0);
    let damp1 = float_opt(opts, "damp", 0.5).clamp(0.0, 1.0) * 0.4;
    let width = float_opt(opts, "width", 1.0).clamp(0.0, 1.0);
    let wet = 0.42;
    let comb_left = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617];
    let comb_right = [1139, 1211, 1300, 1379, 1445, 1514, 1580, 1640];
    let allpass_left = [556, 441, 341, 225];
    let allpass_right = [579, 464, 364, 248];
    Ok(ReverbState {
        combs_left: comb_left
            .into_iter()
            .map(|delay| CombState::new(scaled_reverb_delay(delay, sample_rate)))
            .collect(),
        combs_right: comb_right
            .into_iter()
            .map(|delay| CombState::new(scaled_reverb_delay(delay, sample_rate)))
            .collect(),
        allpasses_left: allpass_left
            .into_iter()
            .map(|delay| AllpassState::new(scaled_reverb_delay(delay, sample_rate)))
            .collect(),
        allpasses_right: allpass_right
            .into_iter()
            .map(|delay| AllpassState::new(scaled_reverb_delay(delay, sample_rate)))
            .collect(),
        feedback: 0.70 + room * 0.28,
        damp1,
        damp2: 1.0 - damp1,
        internal_mix: float_opt(opts, "reverb_mix", float_opt(opts, "mix", 0.4)).clamp(0.0, 1.0),
        wet1: wet * (width * 0.5 + 0.5),
        wet2: wet * ((1.0 - width) * 0.5),
        tail_frames: checked_frame_count(
            float_opt(opts, "tail", 0.7 + room * 2.4).max(0.05),
            sample_rate,
            "stateful reverb tail",
            1,
        )?,
    })
}

fn compile_gverb_state(opts: &OptMap, sample_rate: u32) -> SynthResult<GverbState> {
    let room = (float_opt(opts, "room", 10.0) / 10.0).clamp(0.0, 2.0);
    let ref_level = float_opt(opts, "ref_level", 0.7).max(0.0);
    let tail_level = float_opt(opts, "tail_level", 0.5).max(0.0);
    let delays = [0.019, 0.043, 0.083, 0.149, 0.211, 0.293]
        .into_iter()
        .enumerate()
        .map(|(index, delay)| {
            (
                (delay * (1.0 + room) * sample_rate as f64).round() as usize,
                (ref_level * 0.24 + tail_level * 0.2) * 0.68_f64.powi(index as i32),
            )
        })
        .collect::<Vec<_>>();
    let delay_frames = delays.iter().map(|(delay, _)| *delay).max().unwrap_or(1);
    let damp = float_opt(opts, "damp", 0.5).clamp(0.0, 1.0);
    Ok(GverbState {
        left: vec![0.0; delay_frames.saturating_add(1)],
        right: vec![0.0; delay_frames.saturating_add(1)],
        index: 0,
        delays,
        spread: float_opt(opts, "spread", 0.5).clamp(0.0, 1.0),
        dry: float_opt(opts, "dry", 1.0).max(0.0),
        filter: (damp > 0.0).then(|| StereoFilterState {
            left: BiquadState::default(),
            right: BiquadState::default(),
        }),
        damp_cutoff: 12_000.0 * (1.0 - damp) + 1_200.0 * damp,
        tail_frames: checked_frame_count(
            float_opt(opts, "release", 3.0).max(0.05),
            sample_rate,
            "stateful gverb tail",
            1,
        )?,
    })
}

fn lfo_from_fields(
    frame: usize,
    sample_rate: u32,
    phase: f64,
    wave: i32,
    phase_offset: f64,
    pulse_width: f64,
    invert: bool,
) -> f64 {
    let mut amount = lfo_amount(
        wave,
        frame as f64 / sample_rate as f64,
        phase,
        phase_offset,
        pulse_width,
    );
    if invert {
        amount = 1.0 - amount;
    }
    amount
}

fn compile_slicer_state(opts: &OptMap, sample_rate: u32, _unused: bool) -> SlicerState {
    SlicerState {
        phase: float_opt(opts, "phase", 0.25).max(0.001),
        wave: float_opt(opts, "wave", 1.0) as i32,
        amp_min: float_opt(opts, "amp_min", 0.0),
        amp_max: float_opt(opts, "amp_max", 1.0),
        phase_offset: float_opt(opts, "phase_offset", 0.0),
        pulse_width: float_opt(opts, "pulse_width", 0.5).clamp(0.001, 0.999),
        invert: float_opt(opts, "invert_wave", 0.0) >= 0.5,
        alpha_smooth: smoothing_alpha(float_opt(opts, "smooth", 0.0).max(0.0), sample_rate),
        alpha_up: smoothing_alpha(float_opt(opts, "smooth_up", 0.0).max(0.0), sample_rate),
        alpha_down: smoothing_alpha(float_opt(opts, "smooth_down", 0.0).max(0.0), sample_rate),
        control_alpha: smoothing_alpha(slicer_control_block_seconds(sample_rate), sample_rate),
        lag_ud: None,
        lag: None,
        control: None,
    }
}

fn compile_pan_slicer_state(opts: &OptMap, sample_rate: u32) -> PanSlicerState {
    let smooth = float_opt(opts, "smooth", 0.0)
        .max(float_opt(opts, "smooth_up", 0.0))
        .max(float_opt(opts, "smooth_down", 0.0));
    PanSlicerState {
        phase: float_opt(opts, "phase", 0.25).max(0.001),
        wave: float_opt(opts, "wave", 1.0) as i32,
        pan_min: float_opt(opts, "pan_min", -1.0).clamp(-1.0, 1.0),
        pan_max: float_opt(opts, "pan_max", 1.0).clamp(-1.0, 1.0),
        phase_offset: float_opt(opts, "phase_offset", 0.0),
        pulse_width: float_opt(opts, "pulse_width", 0.5).clamp(0.001, 0.999),
        invert: float_opt(opts, "invert_wave", 0.0) >= 0.5,
        alpha: smoothing_alpha(smooth, sample_rate),
        previous: 0.0,
        stereo_invert: float_opt(opts, "stereo_invert_wave", 0.0) >= 0.5,
    }
}

fn compile_mod_filter_state(opts: &OptMap, ixi: bool, sample_rate: u32) -> ModFilterState {
    let phase = float_opt(opts, "phase", if ixi { 4.0 } else { 0.5 }).max(0.001);
    let wave = float_opt(opts, "wave", if ixi { 3.0 } else { 0.0 }) as i32;
    let cutoff_min = float_opt(opts, "cutoff_min", 60.0);
    let cutoff_max = float_opt(opts, "cutoff_max", float_opt(opts, "cutoff", 120.0));
    let cutoff_min_hz = note_frequency(cutoff_min).max(20.0);
    let cutoff_max_hz = note_frequency(cutoff_max)
        .max(cutoff_min_hz)
        .min(sample_rate as f64 * 0.45);
    let rq = sonic_filter_rq(float_opt(opts, "res", 0.8).clamp(0.0, 0.99));
    ModFilterState {
        phase,
        wave,
        cutoff_min_hz,
        cutoff_max_hz,
        phase_offset: float_opt(opts, "phase_offset", 0.0),
        pulse_width: float_opt(opts, "pulse_width", 0.5).clamp(0.001, 0.999),
        invert: float_opt(opts, "invert_wave", 0.0) >= 0.5,
        kind: if float_opt(opts, "filter", 0.0).round() as i32 == 1 {
            FilterKind::High
        } else {
            FilterKind::Low
        },
        rq,
        output_gain: resonant_output_gain(rq),
        state: StereoFilterState {
            left: BiquadState::default(),
            right: BiquadState::default(),
        },
    }
}

fn compile_band_filter_state(opts: &OptMap, kind: CompiledBlockFxKind) -> BandFilterState {
    let centre = note_frequency(float_opt(opts, "centre", 100.0)).max(20.0);
    let resonant = matches!(
        kind,
        CompiledBlockFxKind::ResonantBandPass | CompiledBlockFxKind::NormalisedResonantBandPass
    );
    let public_res = float_opt(opts, "res", if resonant { 0.5 } else { 0.6 }).clamp(0.0, 0.99);
    let bandwidth = (centre * sonic_filter_rq(public_res)).max(20.0);
    BandFilterState {
        high: StereoFilterState {
            left: BiquadState::default(),
            right: BiquadState::default(),
        },
        low: StereoFilterState {
            left: BiquadState::default(),
            right: BiquadState::default(),
        },
        low_cut: (centre - bandwidth * 0.5).max(20.0),
        high_cut: (centre + bandwidth * 0.5).max((centre - bandwidth * 0.5).max(20.0) + 20.0),
        resonance: if resonant { public_res } else { 0.0 },
        gain: 1.0,
        normalise_level: matches!(
            kind,
            CompiledBlockFxKind::NormalisedBandPass
                | CompiledBlockFxKind::NormalisedResonantBandPass
        )
        .then_some(1.0),
        linked_peak: 0.0,
    }
}

fn compile_band_eq_state(opts: &OptMap) -> BandFilterState {
    let freq = note_frequency(float_opt(opts, "freq", 100.0)).max(20.0);
    let bandwidth = (freq * sonic_filter_rq(float_opt(opts, "res", 0.6))).max(20.0);
    BandFilterState {
        high: StereoFilterState {
            left: BiquadState::default(),
            right: BiquadState::default(),
        },
        low: StereoFilterState {
            left: BiquadState::default(),
            right: BiquadState::default(),
        },
        low_cut: (freq - bandwidth * 0.5).max(20.0),
        high_cut: freq + bandwidth * 0.5,
        resonance: 0.0,
        gain: 10.0_f64.powf(float_opt(opts, "db", 0.6) / 20.0) - 1.0,
        normalise_level: None,
        linked_peak: 0.0,
    }
}

fn compile_pitch_state(semitones: f64, sample_rate: u32) -> PitchState {
    let capacity = ((sample_rate as f64 * 0.05).ceil() as usize).max(64);
    PitchState {
        left: vec![0.0; capacity],
        right: vec![0.0; capacity],
        write: 0,
        filled: 0,
        delay: capacity as f64 * 0.5,
        ratio: 2.0_f64.powf(semitones / 12.0).max(0.001),
    }
}

fn compile_vowel_state(opts: &OptMap) -> ([BandFilterState; 3], [f64; 3]) {
    let vowel = float_opt(opts, "vowel_sound", 1.0).round().clamp(1.0, 5.0) as usize;
    let voice = float_opt(opts, "voice", 0.0).round().clamp(0.0, 4.0) as usize;
    let scale = [1.25, 1.05, 0.95, 0.82, 0.65][voice];
    let formants: [f64; 3] = match vowel {
        1 => [800.0, 1150.0, 2900.0],
        2 => [400.0, 1600.0, 2700.0],
        3 => [350.0, 1700.0, 2700.0],
        4 => [450.0, 800.0, 2830.0],
        _ => [325.0, 700.0, 2530.0],
    };
    let bands = std::array::from_fn(|index| {
        let centre = formants[index] * scale;
        let width = centre * 0.18;
        BandFilterState {
            high: StereoFilterState {
                left: BiquadState::default(),
                right: BiquadState::default(),
            },
            low: StereoFilterState {
                left: BiquadState::default(),
                right: BiquadState::default(),
            },
            low_cut: (centre - width).max(20.0),
            high_cut: centre + width,
            resonance: 0.0,
            gain: 1.0,
            normalise_level: None,
            linked_peak: 0.0,
        }
    });
    (bands, [1.0, 0.65, 0.35])
}

fn compile_flanger_state(opts: &OptMap, sample_rate: u32) -> SynthResult<FlangerState> {
    let delay_ms = float_opt(opts, "delay", 5.0).max(0.0);
    let depth_ms = float_opt(opts, "depth", 5.0).max(0.0);
    let frames = checked_frame_count(
        (delay_ms + depth_ms) / 1000.0,
        sample_rate,
        "stateful flanger delay",
        1,
    )?
    .saturating_add(2);
    Ok(FlangerState {
        left: vec![0.0; frames],
        right: vec![0.0; frames],
        write: 0,
        phase: float_opt(opts, "phase", 4.0).max(0.001),
        wave: float_opt(opts, "wave", 4.0) as i32,
        delay_ms,
        depth_ms,
        feedback: float_opt(opts, "feedback", 0.0).clamp(0.0, 0.95),
        delayed_left: 0.0,
        delayed_right: 0.0,
        invert: float_opt(opts, "invert_flange", 0.0) >= 0.5,
        stereo_invert: float_opt(opts, "stereo_invert_wave", 0.0) >= 0.5,
        phase_offset: float_opt(opts, "phase_offset", 0.0),
        pulse_width: float_opt(opts, "pulse_width", 0.5).clamp(0.001, 0.999),
        invert_wave: float_opt(opts, "invert_wave", 0.0) >= 0.5,
    })
}

#[derive(Clone)]
struct BlockFx {
    pre_amp: f64,
    pre_mix: f64,
    dry_gain: f64,
    wet_gain: f64,
    amp: f64,
    kind: BlockFxKind,
}

fn compile_stateful_chain(
    payload: &FxPayload,
    compiled: &CompiledFxData,
    identifier: &str,
    sample_rate: u32,
) -> SynthResult<Vec<BlockFx>> {
    let Some(SynthValue::List(operations)) = payload.opts.get("ops") else {
        return Err(SynthError::new(
            "stateful synth FX chain requires an 'ops' list.",
        ));
    };
    let mut processors = Vec::with_capacity(operations.len());
    for (index, operation) in operations.iter().enumerate() {
        let mut opts = fx_op_map(operation, index)?;
        let name = opts
            .remove("op")
            .and_then(|value| match value {
                SynthValue::String(value) => Some(value),
                _ => None,
            })
            .ok_or_else(|| SynthError::new("stateful synth FX chain operation is missing 'op'."))?;
        for (key, value) in &payload.opts {
            if key != "ops" && !is_chain_wrapper_option(key) {
                opts.insert(key.clone(), value.clone());
            }
        }
        if name == "reverb" {
            if let Some(mix) = payload.opts.get("mix") {
                opts.insert("reverb_mix".to_owned(), mix.clone());
            }
        }
        let kind = stateful_chain_operation_kind(&name, &mut opts)?;
        for key in ["pre_amp", "pre_mix", "mix", "amp"] {
            opts.insert(key.to_owned(), SynthValue::Float(1.0));
        }
        let operation_payload = FxPayload {
            id: payload.id,
            name: name.clone(),
            opts,
        };
        let mut operation_compiled = compiled.clone();
        operation_compiled.kind = kind;
        processors.push(BlockFx::compile_chain_operation(
            &operation_payload,
            &operation_compiled,
            identifier,
            sample_rate,
        )?);
    }
    Ok(processors)
}

fn is_chain_wrapper_option(key: &str) -> bool {
    matches!(
        key,
        "amp"
            | "amp_slide"
            | "amp_slide_shape"
            | "amp_slide_curve"
            | "mix"
            | "mix_slide"
            | "mix_slide_shape"
            | "mix_slide_curve"
            | "pre_amp"
            | "pre_amp_slide"
            | "pre_amp_slide_shape"
            | "pre_amp_slide_curve"
            | "pre_mix"
            | "pre_mix_slide"
            | "pre_mix_slide_shape"
            | "pre_mix_slide_curve"
    )
}

fn stateful_chain_operation_kind(
    name: &str,
    opts: &mut OptMap,
) -> SynthResult<CompiledBlockFxKind> {
    let kind = match name {
        "level" => CompiledBlockFxKind::Level,
        "decimator" => CompiledBlockFxKind::Bitcrusher,
        "krush_shape" => CompiledBlockFxKind::Krush,
        "distortion_shape" => CompiledBlockFxKind::Distortion,
        "tanh_shape" => CompiledBlockFxKind::Tanh,
        "filter" => {
            let filter = string_opt(opts, "kind", "low");
            let resonant = bool_opt(opts, "resonant", false);
            let normalised =
                bool_opt(opts, "normalise", false) || bool_opt(opts, "normalize", false);
            opts.remove("kind");
            opts.remove("resonant");
            opts.remove("normalise");
            opts.remove("normalize");
            match (filter.as_str(), resonant, normalised) {
                ("low" | "lpf" | "lowpass", false, false) => CompiledBlockFxKind::LowPass,
                ("low" | "lpf" | "lowpass", true, false) => CompiledBlockFxKind::ResonantLowPass,
                ("low" | "lpf" | "lowpass", false, true) => CompiledBlockFxKind::NormalisedLowPass,
                ("low" | "lpf" | "lowpass", true, true) => {
                    CompiledBlockFxKind::NormalisedResonantLowPass
                }
                ("high" | "hpf" | "highpass", false, false) => CompiledBlockFxKind::HighPass,
                ("high" | "hpf" | "highpass", true, false) => CompiledBlockFxKind::ResonantHighPass,
                ("high" | "hpf" | "highpass", false, true) => {
                    CompiledBlockFxKind::NormalisedHighPass
                }
                ("high" | "hpf" | "highpass", true, true) => {
                    CompiledBlockFxKind::NormalisedResonantHighPass
                }
                _ => return Err(SynthError::new("unsupported stateful chain filter kind.")),
            }
        }
        "bandpass" => {
            let resonant = bool_opt(opts, "resonant", false);
            let normalised =
                bool_opt(opts, "normalise", false) || bool_opt(opts, "normalize", false);
            opts.remove("resonant");
            opts.remove("normalise");
            opts.remove("normalize");
            match (resonant, normalised) {
                (false, false) => CompiledBlockFxKind::BandPass,
                (true, false) => CompiledBlockFxKind::ResonantBandPass,
                (false, true) => CompiledBlockFxKind::NormalisedBandPass,
                (true, true) => CompiledBlockFxKind::NormalisedResonantBandPass,
            }
        }
        "band_eq" => CompiledBlockFxKind::BandEq,
        "normalise" | "normalize" => CompiledBlockFxKind::Normaliser,
        "pan" => CompiledBlockFxKind::Pan,
        "reverb" => CompiledBlockFxKind::Reverb,
        "gverb" => CompiledBlockFxKind::Gverb,
        "echo" => CompiledBlockFxKind::Echo,
        "slicer" => CompiledBlockFxKind::Slicer,
        "panslicer" => CompiledBlockFxKind::PanSlicer,
        "wobble" => CompiledBlockFxKind::Wobble,
        "ixi_techno" => CompiledBlockFxKind::IxiTechno,
        "compressor" => CompiledBlockFxKind::Compressor,
        "pitch_shift" => CompiledBlockFxKind::PitchShift,
        "whammy" => CompiledBlockFxKind::Whammy,
        "ring_mod" => CompiledBlockFxKind::RingMod,
        "octaver" => CompiledBlockFxKind::Octaver,
        "vowel" => CompiledBlockFxKind::Vowel,
        "flanger" => CompiledBlockFxKind::Flanger,
        unsupported => {
            return Err(SynthError::new(format!(
                "unsupported stateful synth FX chain operation {unsupported:?}."
            )))
        }
    };
    Ok(kind)
}

fn compile_static_filter(
    kind: FilterKind,
    cutoff_hz: f64,
    sample_rate: u32,
    resonance: f64,
) -> BiquadCoefficients {
    if resonance > 0.0 {
        BiquadCoefficients::resonant_filter(
            kind,
            cutoff_hz,
            sample_rate,
            sonic_filter_rq(resonance),
        )
    } else {
        BiquadCoefficients::filter(kind, cutoff_hz, sample_rate, 0.707)
    }
}

fn process_band_filter(
    state: &mut BandFilterState,
    input: (f64, f64),
    sample_rate: u32,
) -> (f64, f64) {
    let high = state.high.process(
        input.0,
        input.1,
        FilterKind::High,
        state.low_cut,
        sample_rate,
        0.0,
    );
    let mut band = state.low.process(
        high.0,
        high.1,
        FilterKind::Low,
        state.high_cut,
        sample_rate,
        0.0,
    );
    if state.resonance > 0.0 {
        band.0 += (input.0 - band.0) * state.resonance * 0.35;
        band.1 += (input.1 - band.1) * state.resonance * 0.35;
    }
    band = (input.0 + band.0 * state.gain, input.1 + band.1 * state.gain);
    if state.gain == 1.0 {
        band = (band.0 - input.0, band.1 - input.1);
    }
    if let Some(level) = state.normalise_level {
        state.linked_peak = state.linked_peak.max(band.0.abs().max(band.1.abs()));
        if state.linked_peak > 1e-9 {
            let gain = level / state.linked_peak;
            band = (band.0 * gain, band.1 * gain);
        }
    }
    band
}

fn process_pitch_state(state: &mut PitchState, input: (f64, f64)) -> (f64, f64) {
    state.left[state.write] = input.0;
    state.right[state.write] = input.1;
    state.write = (state.write + 1) % state.left.len();
    state.filled = state.filled.saturating_add(1).min(state.left.len());
    if state.filled < 2 {
        return input;
    }
    let max_delay = state.filled.saturating_sub(1).max(1) as f64;
    state.delay = (state.delay + state.ratio - 1.0)
        .rem_euclid(max_delay)
        .max(1.0);
    let delay_low = state.delay.floor() as usize;
    let delay_high = (delay_low + 1).min(state.filled - 1);
    let fraction = state.delay - delay_low as f64;
    let read = |buffer: &[f64], delay: usize| {
        let index = (state.write + buffer.len() - 1 - delay.min(buffer.len() - 1)) % buffer.len();
        buffer[index]
    };
    (
        read(&state.left, delay_low) * (1.0 - fraction) + read(&state.left, delay_high) * fraction,
        read(&state.right, delay_low) * (1.0 - fraction)
            + read(&state.right, delay_high) * fraction,
    )
}

fn process_octaver_channel(state: &mut OctaverChannel, sample: f64) -> (f64, f64) {
    if (state.previous <= 0.0 && sample > 0.0) || (state.previous >= 0.0 && sample < 0.0) {
        state.sub_crossings += 1;
        state.subsub_crossings += 1;
        if state.sub_crossings >= 2 {
            state.sub_sign = if state.sub_sign == 0.0 {
                -1.0
            } else {
                -state.sub_sign
            };
            state.sub_crossings = 0;
        }
        if state.subsub_crossings >= 4 {
            state.subsub_sign = if state.subsub_sign == 0.0 {
                -1.0
            } else {
                -state.subsub_sign
            };
            state.subsub_crossings = 0;
        }
    }
    state.previous = sample;
    (sample * state.sub_sign, sample * state.subsub_sign)
}

impl BlockFx {
    fn compile(
        payload: &FxPayload,
        compiled: &CompiledFxData,
        identifier: &str,
        sample_rate: u32,
    ) -> SynthResult<Self> {
        Self::compile_with_option_validation(payload, compiled, identifier, sample_rate, true)
    }

    fn compile_chain_operation(
        payload: &FxPayload,
        compiled: &CompiledFxData,
        identifier: &str,
        sample_rate: u32,
    ) -> SynthResult<Self> {
        Self::compile_with_option_validation(payload, compiled, identifier, sample_rate, false)
    }

    fn compile_with_option_validation(
        payload: &FxPayload,
        compiled: &CompiledFxData,
        identifier: &str,
        sample_rate: u32,
        validate_keys: bool,
    ) -> SynthResult<Self> {
        let common = ["pre_amp", "pre_mix", "mix", "amp"];
        let operation_keys: &[&str] = match compiled.kind {
            CompiledBlockFxKind::Chain => &["ops"],
            CompiledBlockFxKind::Level => &[],
            CompiledBlockFxKind::Distortion => &["distort", "amount"],
            CompiledBlockFxKind::Tanh => &["krunch"],
            CompiledBlockFxKind::Pan => &["pan"],
            CompiledBlockFxKind::RingMod => &["freq", "mod_amp"],
            CompiledBlockFxKind::LowPass | CompiledBlockFxKind::HighPass => &["cutoff"],
            CompiledBlockFxKind::ResonantLowPass
            | CompiledBlockFxKind::ResonantHighPass => &["cutoff", "res"],
            CompiledBlockFxKind::Compressor => &[
                "threshold",
                "slope_above",
                "slope_below",
                "clamp_time",
                "relax_time",
            ],
            CompiledBlockFxKind::Echo => &["phase", "max_phase", "decay"],
            CompiledBlockFxKind::Bitcrusher => &["sample_rate", "bits"],
            CompiledBlockFxKind::Krush => &["gain", "cutoff", "res"],
            CompiledBlockFxKind::Reverb => &["room", "damp", "tail", "reverb_mix", "width"],
            CompiledBlockFxKind::Gverb => &[
                "room", "release", "spread", "dry", "ref_level", "tail_level", "damp",
            ],
            CompiledBlockFxKind::Slicer => &[
                "phase", "wave", "amp_min", "amp_max", "smooth", "smooth_up", "smooth_down",
                "phase_offset", "pulse_width", "invert_wave",
            ],
            CompiledBlockFxKind::PanSlicer => &[
                "phase", "wave", "pan_min", "pan_max", "smooth", "smooth_up", "smooth_down",
                "phase_offset", "pulse_width", "invert_wave", "stereo_invert_wave",
            ],
            CompiledBlockFxKind::Wobble | CompiledBlockFxKind::IxiTechno => &[
                "phase", "wave", "cutoff_min", "cutoff_max", "cutoff", "filter", "res",
                "phase_offset", "pulse_width", "invert_wave",
            ],
            CompiledBlockFxKind::Whammy => &["transpose"],
            CompiledBlockFxKind::NormalisedLowPass
            | CompiledBlockFxKind::NormalisedHighPass => &["cutoff"],
            CompiledBlockFxKind::NormalisedResonantLowPass
            | CompiledBlockFxKind::NormalisedResonantHighPass => &["cutoff", "res"],
            CompiledBlockFxKind::BandPass
            | CompiledBlockFxKind::NormalisedBandPass
            | CompiledBlockFxKind::ResonantBandPass
            | CompiledBlockFxKind::NormalisedResonantBandPass => &["centre", "res"],
            CompiledBlockFxKind::BandEq => &["freq", "res", "db"],
            CompiledBlockFxKind::Normaliser => &["level"],
            CompiledBlockFxKind::PitchShift => &["pitch"],
            CompiledBlockFxKind::Octaver => &["super_amp", "sub_amp", "subsub_amp"],
            CompiledBlockFxKind::Vowel => &["vowel_sound", "voice"],
            CompiledBlockFxKind::Flanger => &[
                "phase", "wave", "delay", "depth", "feedback", "invert_flange",
                "stereo_invert_wave", "phase_offset", "pulse_width", "invert_wave",
            ],
            CompiledBlockFxKind::Unsupported => {
                return Err(SynthError::new(format!(
                    "stateful block renderer does not yet support FX {:?}; no legacy or dry-pass fallback is used.",
                    payload.name
                )))
            }
        };
        let mut allowed = common.to_vec();
        allowed.extend_from_slice(operation_keys);
        if validate_keys && compiled.kind != CompiledBlockFxKind::Chain {
            validate_option_keys(&payload.opts, &allowed, "stateful FX option")?;
        }
        let kind = match compiled.kind {
            CompiledBlockFxKind::Chain => BlockFxKind::Chain(compile_stateful_chain(
                payload,
                compiled,
                identifier,
                sample_rate,
            )?),
            CompiledBlockFxKind::Level => BlockFxKind::Level,
            CompiledBlockFxKind::Distortion => BlockFxKind::Distortion {
                amount: float_opt(
                    &payload.opts,
                    "distort",
                    float_opt(&payload.opts, "amount", 0.5),
                )
                .clamp(0.0, 0.999),
            },
            CompiledBlockFxKind::Tanh => BlockFxKind::Tanh {
                krunch: float_opt(&payload.opts, "krunch", 5.0).max(0.0001) * 5.0,
            },
            CompiledBlockFxKind::Pan => BlockFxKind::Pan {
                pan: float_opt(&payload.opts, "pan", 0.0).clamp(-1.0, 1.0),
            },
            CompiledBlockFxKind::RingMod => BlockFxKind::RingMod {
                frequency: note_frequency(float_opt(&payload.opts, "freq", 30.0)).max(1.0),
                amount: float_opt(&payload.opts, "mod_amp", 1.0).max(0.0),
            },
            CompiledBlockFxKind::LowPass
            | CompiledBlockFxKind::ResonantLowPass
            | CompiledBlockFxKind::NormalisedLowPass
            | CompiledBlockFxKind::NormalisedResonantLowPass => BlockFxKind::Filter {
                coefficients: compile_static_filter(
                    FilterKind::Low,
                    note_frequency(float_opt(&payload.opts, "cutoff", 100.0)).max(20.0),
                    sample_rate,
                    if matches!(
                        compiled.kind,
                        CompiledBlockFxKind::ResonantLowPass
                            | CompiledBlockFxKind::NormalisedResonantLowPass
                    ) {
                        float_opt(&payload.opts, "res", 0.5).clamp(0.0, 0.99)
                    } else {
                        0.0
                    },
                ),
                state: StereoFilterState {
                    left: BiquadState::default(),
                    right: BiquadState::default(),
                },
                normalise_level: matches!(
                    compiled.kind,
                    CompiledBlockFxKind::NormalisedLowPass
                        | CompiledBlockFxKind::NormalisedResonantLowPass
                )
                .then_some(1.0),
                linked_peak: 0.0,
            },
            CompiledBlockFxKind::HighPass
            | CompiledBlockFxKind::ResonantHighPass
            | CompiledBlockFxKind::NormalisedHighPass
            | CompiledBlockFxKind::NormalisedResonantHighPass => BlockFxKind::Filter {
                coefficients: compile_static_filter(
                    FilterKind::High,
                    note_frequency(float_opt(&payload.opts, "cutoff", 100.0)).max(20.0),
                    sample_rate,
                    if matches!(
                        compiled.kind,
                        CompiledBlockFxKind::ResonantHighPass
                            | CompiledBlockFxKind::NormalisedResonantHighPass
                    ) {
                        float_opt(&payload.opts, "res", 0.5).clamp(0.0, 0.99)
                    } else {
                        0.0
                    },
                ),
                state: StereoFilterState {
                    left: BiquadState::default(),
                    right: BiquadState::default(),
                },
                normalise_level: matches!(
                    compiled.kind,
                    CompiledBlockFxKind::NormalisedHighPass
                        | CompiledBlockFxKind::NormalisedResonantHighPass
                )
                .then_some(1.0),
                linked_peak: 0.0,
            },
            CompiledBlockFxKind::Compressor => BlockFxKind::Compressor(CompressorState {
                gain: 1.0,
                threshold: float_opt(&payload.opts, "threshold", 0.2).max(0.0001),
                slope_above: float_opt(&payload.opts, "slope_above", 0.5),
                slope_below: float_opt(&payload.opts, "slope_below", 1.0),
                attack_alpha: smoothing_alpha(
                    float_opt(&payload.opts, "clamp_time", 0.01).max(0.0),
                    sample_rate,
                ),
                release_alpha: smoothing_alpha(
                    float_opt(&payload.opts, "relax_time", 0.01).max(0.0),
                    sample_rate,
                ),
            }),
            CompiledBlockFxKind::Echo => {
                let max_phase = float_opt(&payload.opts, "max_phase", 2.0).max(0.001);
                let phase = float_opt(&payload.opts, "phase", 0.25).clamp(0.001, max_phase);
                let decay = float_opt(&payload.opts, "decay", 2.0).max(0.0);
                let delay_frames =
                    checked_frame_count(phase, sample_rate, "stateful echo delay", 1)?;
                let repeats = if decay <= 0.0 {
                    0
                } else {
                    (decay / phase).ceil().max(1.0) as usize
                };
                BlockFxKind::Echo(EchoState {
                    left: vec![0.0; delay_frames],
                    right: vec![0.0; delay_frames],
                    index: 0,
                    feedback: if decay <= 0.0 {
                        0.0
                    } else {
                        0.001_f64.powf(phase / decay).clamp(0.0, 0.999)
                    },
                    tail_frames: delay_frames.saturating_mul(repeats),
                })
            }
            CompiledBlockFxKind::Bitcrusher => {
                let target_rate = float_opt(&payload.opts, "sample_rate", 10_000.0)
                    .max(1.0)
                    .min(sample_rate as f64);
                let bits = float_opt(&payload.opts, "bits", 8.0)
                    .round()
                    .clamp(1.0, 16.0);
                BlockFxKind::Bitcrusher(BitcrusherState {
                    hold_frames: (sample_rate as f64 / target_rate).round().max(1.0) as usize,
                    remaining: 0,
                    levels: 2.0_f64.powf(bits).max(2.0),
                    held_left: 0.0,
                    held_right: 0.0,
                })
            }
            CompiledBlockFxKind::Krush => BlockFxKind::Krush {
                gain: float_opt(&payload.opts, "gain", 5.0).max(0.001),
                resonance: float_opt(&payload.opts, "res", 0.0).clamp(0.0, 0.99),
                filter: StereoFilterState {
                    left: BiquadState::default(),
                    right: BiquadState::default(),
                },
                coefficients: compile_static_filter(
                    FilterKind::Low,
                    note_frequency(float_opt(&payload.opts, "cutoff", 100.0)).max(20.0),
                    sample_rate,
                    0.0,
                ),
            },
            CompiledBlockFxKind::Normaliser => {
                let level = float_opt(&payload.opts, "level", 1.0).max(0.0);
                if level <= 0.0 {
                    BlockFxKind::Level
                } else {
                    BlockFxKind::Normaliser(CausalNormaliser::new(
                        sample_rate,
                        CausalNormaliserConfig {
                            target: level,
                            ..CausalNormaliserConfig::default()
                        },
                    )?)
                }
            }
            CompiledBlockFxKind::Reverb => {
                BlockFxKind::Reverb(compile_reverb_state(&payload.opts, sample_rate)?)
            }
            CompiledBlockFxKind::Gverb => {
                BlockFxKind::Gverb(compile_gverb_state(&payload.opts, sample_rate)?)
            }
            CompiledBlockFxKind::Slicer => {
                BlockFxKind::Slicer(compile_slicer_state(&payload.opts, sample_rate, false))
            }
            CompiledBlockFxKind::PanSlicer => {
                BlockFxKind::PanSlicer(compile_pan_slicer_state(&payload.opts, sample_rate))
            }
            CompiledBlockFxKind::Wobble | CompiledBlockFxKind::IxiTechno => {
                BlockFxKind::ModFilter(compile_mod_filter_state(
                    &payload.opts,
                    compiled.kind == CompiledBlockFxKind::IxiTechno,
                    sample_rate,
                ))
            }
            CompiledBlockFxKind::Whammy | CompiledBlockFxKind::PitchShift => {
                let semitones = if compiled.kind == CompiledBlockFxKind::Whammy {
                    float_opt(&payload.opts, "transpose", 12.0)
                } else {
                    float_opt(&payload.opts, "pitch", 0.0).clamp(-72.0, 24.0)
                };
                BlockFxKind::PitchShift(compile_pitch_state(semitones, sample_rate))
            }
            CompiledBlockFxKind::BandPass
            | CompiledBlockFxKind::NormalisedBandPass
            | CompiledBlockFxKind::ResonantBandPass
            | CompiledBlockFxKind::NormalisedResonantBandPass => {
                BlockFxKind::BandFilter(compile_band_filter_state(&payload.opts, compiled.kind))
            }
            CompiledBlockFxKind::BandEq => {
                BlockFxKind::BandFilter(compile_band_eq_state(&payload.opts))
            }
            CompiledBlockFxKind::Octaver => BlockFxKind::Octaver {
                filter: StereoFilterState {
                    left: BiquadState::default(),
                    right: BiquadState::default(),
                },
                left: OctaverChannel {
                    sub_sign: 1.0,
                    subsub_sign: 1.0,
                    ..OctaverChannel::default()
                },
                right: OctaverChannel {
                    sub_sign: 1.0,
                    subsub_sign: 1.0,
                    ..OctaverChannel::default()
                },
                super_amp: float_opt(&payload.opts, "super_amp", 1.0).max(0.0),
                sub_amp: float_opt(&payload.opts, "sub_amp", 1.0).max(0.0),
                subsub_amp: float_opt(&payload.opts, "subsub_amp", 1.0).max(0.0),
            },
            CompiledBlockFxKind::Vowel => {
                let (bands, gains) = compile_vowel_state(&payload.opts);
                BlockFxKind::Vowel {
                    bands: Box::new(bands),
                    gains,
                }
            }
            CompiledBlockFxKind::Flanger => {
                BlockFxKind::Flanger(compile_flanger_state(&payload.opts, sample_rate)?)
            }

            CompiledBlockFxKind::Unsupported => {
                unreachable!("unsupported stateful FX was rejected before compilation")
            }
        };
        let mix = float_opt(&payload.opts, "mix", default_fx_mix(identifier)).clamp(0.0, 1.0);
        let angle = mix * PI / 2.0;
        Ok(Self {
            pre_amp: float_opt(&payload.opts, "pre_amp", 1.0).max(0.0),
            pre_mix: float_opt(&payload.opts, "pre_mix", 1.0).clamp(0.0, 1.0),
            dry_gain: angle.cos(),
            wet_gain: angle.sin(),
            amp: float_opt(&payload.opts, "amp", 1.0).max(0.0),
            kind,
        })
    }

    fn process(
        &mut self,
        input: (f64, f64),
        absolute_frame: usize,
        sample_rate: u32,
    ) -> (f64, f64) {
        let fx_input = (input.0 * self.pre_amp, input.1 * self.pre_amp);
        let dry = (fx_input.0 * self.pre_mix, fx_input.1 * self.pre_mix);
        let bypass = (
            fx_input.0 * (1.0 - self.pre_mix),
            fx_input.1 * (1.0 - self.pre_mix),
        );
        let processed = match &mut self.kind {
            BlockFxKind::Chain(processors) => {
                processors.iter_mut().fold(dry, |sample, processor| {
                    processor.process(sample, absolute_frame, sample_rate)
                })
            }
            BlockFxKind::Level => dry,
            BlockFxKind::Distortion { amount } => {
                let k = (2.0 * *amount) / (1.0 - *amount).max(0.001);
                let shape = |sample: f64| sample * (1.0 + k) / (1.0 + k * sample.abs());
                (shape(dry.0), shape(dry.1))
            }
            BlockFxKind::Tanh { krunch } => {
                let gain = 1.0 + *krunch / 8.0;
                let shape = |sample: f64| (sample * *krunch).tanh() / *krunch * gain;
                (shape(dry.0), shape(dry.1))
            }
            BlockFxKind::Pan { pan } => balance2_sample(dry.0, dry.1, *pan),
            BlockFxKind::RingMod { frequency, amount } => {
                let modulation = 1.0
                    + *amount
                        * (TAU * *frequency * absolute_frame as f64 / sample_rate as f64).sin();
                (
                    (dry.0 * modulation).clamp(-1.0, 1.0),
                    (dry.1 * modulation).clamp(-1.0, 1.0),
                )
            }
            BlockFxKind::Filter {
                coefficients,
                state,
                normalise_level,
                linked_peak,
            } => {
                let mut output = state.process_coefficients(dry.0, dry.1, *coefficients);
                if let Some(level) = normalise_level {
                    *linked_peak = linked_peak.max(output.0.abs().max(output.1.abs()));
                    if *linked_peak > 1e-9 {
                        let gain = *level / *linked_peak;
                        output = (output.0 * gain, output.1 * gain);
                    }
                }
                output
            }
            BlockFxKind::Compressor(state) => {
                let level = dry.0.abs().max(dry.1.abs()).max(1e-9);
                let target_level = if level > state.threshold {
                    state.threshold + (level - state.threshold) * state.slope_above
                } else {
                    state.threshold * (level / state.threshold).powf(state.slope_below)
                };
                let target_gain = (target_level / level).clamp(0.0, 16.0);
                let alpha = if target_gain < state.gain {
                    state.attack_alpha
                } else {
                    state.release_alpha
                };
                state.gain += (target_gain - state.gain) * alpha;
                (dry.0 * state.gain, dry.1 * state.gain)
            }
            BlockFxKind::Echo(state) => {
                let delayed = (state.left[state.index], state.right[state.index]);
                let output = (dry.0 + delayed.0, dry.1 + delayed.1);
                state.left[state.index] = output.0 * state.feedback;
                state.right[state.index] = output.1 * state.feedback;
                state.index = (state.index + 1) % state.left.len();
                output
            }
            BlockFxKind::Bitcrusher(state) => {
                if state.remaining == 0 {
                    let quantize = |sample: f64| {
                        (sample.clamp(-1.0, 1.0) * (state.levels / 2.0)).round()
                            / (state.levels / 2.0)
                    };
                    state.held_left = quantize(dry.0);
                    state.held_right = quantize(dry.1);
                    state.remaining = state.hold_frames;
                }
                state.remaining = state.remaining.saturating_sub(1);
                (state.held_left, state.held_right)
            }
            BlockFxKind::Krush {
                gain,
                resonance,
                filter,
                coefficients,
            } => {
                let shape = |sample: f64| {
                    let absolute = sample.abs();
                    let squared = absolute * absolute;
                    (squared + *gain * absolute) / (squared + absolute * (*gain - 1.0) + 1.0)
                };
                let shaped = (shape(dry.0), shape(dry.1));
                let filtered = filter.process_coefficients(shaped.0, shaped.1, *coefficients);
                (
                    filtered.0 + (dry.0 - filtered.0) * *resonance * 0.35,
                    filtered.1 + (dry.1 - filtered.1) * *resonance * 0.35,
                )
            }
            BlockFxKind::Normaliser(normaliser) => {
                normaliser.process_frame(dry.0, dry.1).unwrap_or((0.0, 0.0))
            }
            BlockFxKind::Reverb(state) => {
                let comb_left = (dry.0 * 0.75 + dry.1 * 0.25) * 0.015;
                let comb_right = (dry.1 * 0.75 + dry.0 * 0.25) * 0.015;
                let mut wet_left = state
                    .combs_left
                    .iter_mut()
                    .map(|comb| comb.process(comb_left, state.feedback, state.damp1, state.damp2))
                    .sum::<f64>();
                let mut wet_right = state
                    .combs_right
                    .iter_mut()
                    .map(|comb| comb.process(comb_right, state.feedback, state.damp1, state.damp2))
                    .sum::<f64>();
                for allpass in &mut state.allpasses_left {
                    wet_left = allpass.process(wet_left);
                }
                for allpass in &mut state.allpasses_right {
                    wet_right = allpass.process(wet_right);
                }
                (
                    dry.0 * (1.0 - state.internal_mix)
                        + (wet_left * state.wet1 + wet_right * state.wet2) * state.internal_mix,
                    dry.1 * (1.0 - state.internal_mix)
                        + (wet_right * state.wet1 + wet_left * state.wet2) * state.internal_mix,
                )
            }
            BlockFxKind::Gverb(state) => {
                state.left[state.index] = dry.0;
                state.right[state.index] = dry.1;
                let mut output = (dry.0 * state.dry, dry.1 * state.dry);
                for &(delay, gain) in &state.delays {
                    let read = (state.index + state.left.len() - delay % state.left.len())
                        % state.left.len();
                    output.0 += (state.left[read] * (1.0 - state.spread)
                        + state.right[read] * state.spread)
                        * gain;
                    output.1 += (state.right[read] * (1.0 - state.spread)
                        + state.left[read] * state.spread)
                        * gain;
                }
                state.index = (state.index + 1) % state.left.len();
                if let Some(filter) = &mut state.filter {
                    output = filter.process(
                        output.0,
                        output.1,
                        FilterKind::Low,
                        state.damp_cutoff,
                        sample_rate,
                        0.0,
                    );
                }
                output
            }
            BlockFxKind::Slicer(state) => {
                let amount = lfo_from_fields(
                    absolute_frame,
                    sample_rate,
                    state.phase,
                    state.wave,
                    state.phase_offset,
                    state.pulse_width,
                    state.invert,
                );
                let target = state.amp_min + (state.amp_max - state.amp_min) * amount;
                let previous_ud = state.lag_ud.unwrap_or(target);
                let alpha_ud = if target >= previous_ud {
                    state.alpha_up
                } else {
                    state.alpha_down
                };
                let smoothed_ud = previous_ud + (target - previous_ud) * alpha_ud;
                state.lag_ud = Some(smoothed_ud);
                let previous = state.lag.unwrap_or(smoothed_ud);
                let lagged = previous + (smoothed_ud - previous) * state.alpha_smooth;
                state.lag = Some(lagged);
                let previous = state.control.unwrap_or(lagged);
                let gain = previous + (lagged - previous) * state.control_alpha;
                state.control = Some(gain);
                (dry.0 * gain, dry.1 * gain)
            }
            BlockFxKind::PanSlicer(state) => {
                let amount = lfo_from_fields(
                    absolute_frame,
                    sample_rate,
                    state.phase,
                    state.wave,
                    state.phase_offset,
                    state.pulse_width,
                    state.invert,
                );
                let target = state.pan_min + (state.pan_max - state.pan_min) * amount;
                state.previous += (target - state.previous) * state.alpha;
                let pan = if state.stereo_invert {
                    -state.previous
                } else {
                    state.previous
                };
                balance2_sample(dry.0, dry.1, pan)
            }
            BlockFxKind::ModFilter(state) => {
                let amount = lfo_from_fields(
                    absolute_frame,
                    sample_rate,
                    state.phase,
                    state.wave,
                    state.phase_offset,
                    state.pulse_width,
                    state.invert,
                );
                let cutoff = lin_exp(amount, state.cutoff_min_hz, state.cutoff_max_hz)
                    .clamp(20.0, sample_rate as f64 * 0.45);
                let coefficients =
                    BiquadCoefficients::resonant_filter(state.kind, cutoff, sample_rate, state.rq);
                (
                    state.state.left.process(dry.0, coefficients) * state.output_gain,
                    state.state.right.process(dry.1, coefficients) * state.output_gain,
                )
            }
            BlockFxKind::BandFilter(state) => process_band_filter(state, dry, sample_rate),
            BlockFxKind::PitchShift(state) => process_pitch_state(state, dry),
            BlockFxKind::Octaver {
                filter,
                left,
                right,
                super_amp,
                sub_amp,
                subsub_amp,
            } => {
                let direct = filter.process(dry.0, dry.1, FilterKind::Low, 440.0, sample_rate, 0.0);
                let left_octaves = process_octaver_channel(left, direct.0);
                let right_octaves = process_octaver_channel(right, direct.1);
                (
                    direct.0.abs() * 2.0 * *super_amp
                        + left_octaves.0 * *sub_amp
                        + left_octaves.1 * *subsub_amp,
                    direct.1.abs() * 2.0 * *super_amp
                        + right_octaves.0 * *sub_amp
                        + right_octaves.1 * *subsub_amp,
                )
            }
            BlockFxKind::Vowel { bands, gains } => {
                let mut output = (0.0, 0.0);
                for (band, gain) in bands.iter_mut().zip(gains.iter()) {
                    let filtered = process_band_filter(band, dry, sample_rate);
                    output.0 += filtered.0 * gain;
                    output.1 += filtered.1 * gain;
                }
                output
            }
            BlockFxKind::Flanger(state) => {
                let amount_left = lfo_from_fields(
                    absolute_frame,
                    sample_rate,
                    state.phase,
                    state.wave,
                    state.phase_offset,
                    state.pulse_width,
                    state.invert_wave,
                );
                let amount_right = if state.stereo_invert {
                    1.0 - amount_left
                } else {
                    amount_left
                };
                let delay_index = |amount: f64, len: usize| {
                    (((state.delay_ms + state.depth_ms * amount) / 1000.0 * sample_rate as f64)
                        .round() as usize)
                        .min(len - 1)
                };
                let read_left = (state.write + state.left.len()
                    - delay_index(amount_left, state.left.len()))
                    % state.left.len();
                let read_right = (state.write + state.right.len()
                    - delay_index(amount_right, state.right.len()))
                    % state.right.len();
                let delayed_left = state.left[read_left] + state.delayed_left * state.feedback;
                let delayed_right = state.right[read_right] + state.delayed_right * state.feedback;
                state.delayed_left = delayed_left;
                state.delayed_right = delayed_right;
                state.left[state.write] = dry.0;
                state.right[state.write] = dry.1;
                state.write = (state.write + 1) % state.left.len();
                let sign = if state.invert { -1.0 } else { 1.0 };
                (
                    (dry.0 + delayed_left * sign) * 0.5,
                    (dry.1 + delayed_right * sign) * 0.5,
                )
            }
        };
        let wet = (processed.0 + bypass.0, processed.1 + bypass.1);
        (
            (fx_input.0 * self.dry_gain + wet.0 * self.wet_gain) * self.amp,
            (fx_input.1 * self.dry_gain + wet.1 * self.wet_gain) * self.amp,
        )
    }

    fn tail_frames(&self) -> usize {
        match &self.kind {
            BlockFxKind::Chain(processors) => processors.iter().map(BlockFx::tail_frames).sum(),
            BlockFxKind::Echo(state) => state.tail_frames,
            BlockFxKind::Reverb(state) => state.tail_frames,
            BlockFxKind::Gverb(state) => state.tail_frames,
            BlockFxKind::Normaliser(normaliser) => normaliser.latency_frames(),
            _ => 0,
        }
    }

    fn state_bytes(&self) -> usize {
        let dynamic_samples = match &self.kind {
            BlockFxKind::Chain(processors) => {
                return std::mem::size_of::<Self>()
                    + processors.capacity() * std::mem::size_of::<BlockFx>()
                    + processors.iter().map(BlockFx::state_bytes).sum::<usize>();
            }
            BlockFxKind::Echo(state) => state.left.capacity() + state.right.capacity(),
            BlockFxKind::Reverb(state) => {
                state
                    .combs_left
                    .iter()
                    .chain(&state.combs_right)
                    .map(|comb| comb.buffer.capacity())
                    .sum::<usize>()
                    + state
                        .allpasses_left
                        .iter()
                        .chain(&state.allpasses_right)
                        .map(|allpass| allpass.buffer.capacity())
                        .sum::<usize>()
            }
            BlockFxKind::Gverb(state) => state.left.capacity() + state.right.capacity(),
            BlockFxKind::PitchShift(state) => state.left.capacity() + state.right.capacity(),
            BlockFxKind::Flanger(state) => state.left.capacity() + state.right.capacity(),
            _ => 0,
        };
        std::mem::size_of::<Self>() + dynamic_samples * std::mem::size_of::<f64>()
    }
}

#[derive(Clone)]
struct FxBusSnapshot {
    frame: usize,
    order: u64,
    payload: FxPayload,
}

#[derive(Clone)]
struct StatefulFxBus {
    id: u64,
    name: String,
    parent: Option<usize>,
    compiled: CompiledFxData,
    identifier: String,
    processor_frame_offset: usize,
    current_opts: OptMap,
    processor: BlockFx,
    snapshots: Vec<FxBusSnapshot>,
    next_snapshot: usize,
    input_left: f64,
    input_right: f64,
    input_active: bool,
    tail_remaining: usize,
}

impl StatefulFxBus {
    fn apply_snapshots(&mut self, frame: usize, sample_rate: u32) -> SynthResult<()> {
        while self
            .snapshots
            .get(self.next_snapshot)
            .is_some_and(|snapshot| snapshot.frame <= frame)
        {
            let snapshot = &self.snapshots[self.next_snapshot];
            if snapshot.payload.opts != self.current_opts {
                self.processor = BlockFx::compile(
                    &snapshot.payload,
                    &self.compiled,
                    &self.identifier,
                    sample_rate,
                )?;
                self.current_opts = snapshot.payload.opts.clone();
                self.tail_remaining = 0;
            }
            self.next_snapshot += 1;
        }
        Ok(())
    }

    fn process(&mut self, frame: usize, sample_rate: u32) -> SynthResult<Option<(f64, f64)>> {
        self.apply_snapshots(frame, sample_rate)?;
        let active = if self.input_active {
            self.tail_remaining = self.processor.tail_frames();
            true
        } else if self.tail_remaining > 0 {
            self.tail_remaining -= 1;
            true
        } else {
            false
        };
        let input = (self.input_left, self.input_right);
        self.input_left = 0.0;
        self.input_right = 0.0;
        self.input_active = false;
        let processor_frame = frame.saturating_add(self.processor_frame_offset);
        Ok(active.then(|| self.processor.process(input, processor_frame, sample_rate)))
    }

    fn state_bytes(&self) -> usize {
        self.processor.state_bytes()
            + self.snapshots.capacity() * std::mem::size_of::<FxBusSnapshot>()
            + self.current_opts.capacity() * std::mem::size_of::<(String, SynthValue)>()
    }
}

#[derive(Clone, Default)]
struct StatefulFxBusGraph {
    buses: Vec<StatefulFxBus>,
}

impl StatefulFxBusGraph {
    fn compile(program: &CompiledSynthProgram) -> SynthResult<(Self, Vec<Option<usize>>)> {
        let mut graph = Self::default();
        let mut routes = Vec::with_capacity(program.event_count());
        for index in 0..program.event_count() {
            let event = program
                .events()
                .get(index)
                .ok_or_else(|| SynthError::new("compiled synth event index is malformed."))?;
            let execution = program.execution_event(index).ok_or_else(|| {
                SynthError::new("compiled synth execution event index is malformed.")
            })?;
            let compiled_fx = program
                .execution_fx(index)
                .ok_or_else(|| SynthError::new("compiled synth FX range is malformed."))?;
            let mut parent = None;
            for (payload, compiled) in event.fx_chain.iter().zip(compiled_fx) {
                let bus_index = graph
                    .buses
                    .iter()
                    .position(|bus| {
                        bus.parent == parent && bus.id == payload.id && bus.name == payload.name
                    })
                    .map_or_else(
                        || {
                            let identifier = program
                                .identifier(compiled.identifier)
                                .ok_or_else(|| {
                                    SynthError::new(
                                        "compiled synth FX identifier index is malformed.",
                                    )
                                })?
                                .to_owned();
                            let processor = BlockFx::compile(
                                payload,
                                compiled,
                                &identifier,
                                program.sample_rate(),
                            )?;
                            let bus_index = graph.buses.len();
                            graph.buses.push(StatefulFxBus {
                                id: payload.id,
                                name: payload.name.clone(),
                                parent,
                                compiled: compiled.clone(),
                                identifier,
                                processor_frame_offset: execution.processor_frame_offset,
                                current_opts: payload.opts.clone(),
                                processor,
                                snapshots: Vec::new(),
                                next_snapshot: 0,
                                input_left: 0.0,
                                input_right: 0.0,
                                input_active: false,
                                tail_remaining: 0,
                            });
                            Ok(bus_index)
                        },
                        Ok,
                    )?;
                BlockFx::compile(
                    payload,
                    compiled,
                    &graph.buses[bus_index].identifier,
                    program.sample_rate(),
                )?;
                graph.buses[bus_index].snapshots.push(FxBusSnapshot {
                    frame: execution.frame.as_usize(),
                    order: event.order,
                    payload: payload.clone(),
                });
                parent = Some(bus_index);
            }
            routes.push(parent);
        }
        for bus in &mut graph.buses {
            bus.snapshots.sort_by(|left, right| {
                left.frame
                    .cmp(&right.frame)
                    .then_with(|| left.order.cmp(&right.order))
            });
        }
        Ok((graph, routes))
    }

    fn mix_into(&mut self, route: Option<usize>, sample: (f64, f64)) -> SynthResult<()> {
        let Some(index) = route else {
            return Err(SynthError::new(
                "stateful FX bus route is missing its root accumulator.",
            ));
        };
        let bus = self
            .buses
            .get_mut(index)
            .ok_or_else(|| SynthError::new("stateful FX bus route index is malformed."))?;
        bus.input_left += sample.0;
        bus.input_right += sample.1;
        bus.input_active = true;
        Ok(())
    }

    fn process_frame(
        &mut self,
        frame: usize,
        sample_rate: u32,
        mut root: (f64, f64),
        mut root_active: bool,
    ) -> SynthResult<((f64, f64), bool)> {
        for index in (0..self.buses.len()).rev() {
            let parent = self.buses[index].parent;
            let output = self.buses[index].process(frame, sample_rate)?;
            let Some(output) = output else {
                continue;
            };
            if let Some(parent) = parent {
                let parent = self
                    .buses
                    .get_mut(parent)
                    .ok_or_else(|| SynthError::new("stateful FX bus parent index is malformed."))?;
                parent.input_left += output.0;
                parent.input_right += output.1;
                parent.input_active = true;
            } else {
                root.0 += output.0;
                root.1 += output.1;
                root_active = true;
            }
        }
        Ok((root, root_active))
    }

    fn is_idle(&self) -> bool {
        self.buses
            .iter()
            .all(|bus| !bus.input_active && bus.tail_remaining == 0)
    }

    fn state_bytes(&self) -> usize {
        self.buses.capacity() * std::mem::size_of::<StatefulFxBus>()
            + self
                .buses
                .iter()
                .map(StatefulFxBus::state_bytes)
                .sum::<usize>()
    }
}

#[derive(Clone)]
struct ActiveEvent {
    source: ActiveSource,
    route: Option<usize>,
    source_finished: bool,
}

impl ActiveEvent {
    fn from_program(
        program: &CompiledSynthProgram,
        index: usize,
        route: Option<usize>,
    ) -> SynthResult<Self> {
        let event = program
            .events()
            .get(index)
            .ok_or_else(|| SynthError::new("compiled synth event index is malformed."))?;
        let execution = program
            .execution_event(index)
            .ok_or_else(|| SynthError::new("compiled synth execution event index is malformed."))?;
        let control_frames = program
            .control_frames(index)
            .ok_or_else(|| SynthError::new("compiled synth control range is malformed."))?;
        let source =
            ActiveSource::from_event(event, execution, program.sample_rate(), &control_frames)?;
        Ok(Self {
            source,
            route,
            source_finished: false,
        })
    }

    fn next_sample(&mut self, sample_rate: u32) -> Option<(f64, f64)> {
        if self.source_finished {
            return None;
        }
        let sample = self.source.next_sample(sample_rate);
        if sample.is_none() {
            self.source_finished = true;
        }
        sample
    }

    fn is_finished(&self) -> bool {
        self.source_finished
    }

    fn state_bytes(&self) -> usize {
        self.source.state_bytes()
    }
}

#[derive(Clone)]
struct StatefulLimiter {
    gain: f64,
    release_alpha: f64,
    lookahead_frames: usize,
    next_frame: usize,
    delayed: VecDeque<(usize, f64, f64)>,
    maxima: VecDeque<(usize, f64)>,
}

impl StatefulLimiter {
    fn new(sample_rate: u32) -> Self {
        let lookahead_frames =
            (OUTPUT_LIMIT_RELEASE_SECONDS * sample_rate.max(1) as f64).ceil() as usize;
        Self {
            gain: 1.0,
            release_alpha: smoothing_alpha(OUTPUT_LIMIT_RELEASE_SECONDS, sample_rate),
            lookahead_frames,
            next_frame: 0,
            delayed: VecDeque::with_capacity(lookahead_frames.saturating_add(1)),
            maxima: VecDeque::with_capacity(lookahead_frames.saturating_add(1)),
        }
    }

    fn latency_frames(&self) -> usize {
        self.lookahead_frames
    }

    fn is_idle(&self) -> bool {
        self.delayed.is_empty()
    }

    fn process_into(
        &mut self,
        left: &[f64],
        right: &[f64],
        out_left: &mut Vec<f64>,
        out_right: &mut Vec<f64>,
    ) -> SynthResult<()> {
        if left.len() != right.len() {
            return Err(SynthError::new(
                "stateful limiter requires equal-length left and right blocks.",
            ));
        }
        out_left.clear();
        out_right.clear();
        out_left.reserve(left.len());
        out_right.reserve(right.len());
        for (&left, &right) in left.iter().zip(right) {
            self.push(left, right);
            if self.delayed.len() > self.lookahead_frames {
                self.emit_oldest(out_left, out_right);
            }
        }
        Ok(())
    }

    fn flush_up_to_into(
        &mut self,
        max_frames: usize,
        out_left: &mut Vec<f64>,
        out_right: &mut Vec<f64>,
    ) {
        out_left.clear();
        out_right.clear();
        let frames = self.delayed.len().min(max_frames);
        out_left.reserve(frames);
        out_right.reserve(frames);
        for _ in 0..frames {
            self.emit_oldest(out_left, out_right);
        }
    }

    fn push(&mut self, left: f64, right: f64) {
        let frame = self.next_frame;
        self.next_frame = self.next_frame.saturating_add(1);
        let level = left.abs().max(right.abs());
        while self
            .maxima
            .back()
            .is_some_and(|(_, candidate)| *candidate <= level)
        {
            self.maxima.pop_back();
        }
        self.maxima.push_back((frame, level));
        self.delayed.push_back((frame, left, right));
    }

    fn emit_oldest(&mut self, out_left: &mut Vec<f64>, out_right: &mut Vec<f64>) {
        let Some((frame, left, right)) = self.delayed.pop_front() else {
            return;
        };
        let peak = self.maxima.front().map_or(0.0, |(_, level)| *level);
        let target = if peak > OUTPUT_LIMIT_CEILING {
            OUTPUT_LIMIT_CEILING / peak
        } else {
            1.0
        };
        if target < self.gain {
            self.gain = target;
        } else {
            self.gain += (target - self.gain) * self.release_alpha;
        }
        out_left.push((left * self.gain).clamp(-OUTPUT_LIMIT_CEILING, OUTPUT_LIMIT_CEILING));
        out_right.push((right * self.gain).clamp(-OUTPUT_LIMIT_CEILING, OUTPUT_LIMIT_CEILING));
        if self
            .maxima
            .front()
            .is_some_and(|(candidate, _)| *candidate == frame)
        {
            self.maxima.pop_front();
        }
    }
}

#[derive(Clone)]
struct RenderState {
    next_event: usize,
    current_frame: usize,
    events: Vec<ActiveEvent>,
    fx_buses: StatefulFxBusGraph,
    normaliser: Option<CausalNormaliser>,
    limiter: StatefulLimiter,
}

/// Rust-owned session that renders supported compiled programs into fixed blocks.
///
/// Construction fails for every unsupported source, shared bus, control, or
/// processor instead of selecting a legacy renderer. `gummy_canvas` uses this
/// same session for bounded SDL render-ahead delivery.
pub struct StatefulBlockRenderer {
    program: CompiledSynthProgram,
    config: BlockRenderConfig,
    state: RenderState,
    event_templates: Vec<ActiveEvent>,
    block_pcm: Vec<i16>,
    raw_left: Vec<f64>,
    raw_right: Vec<f64>,
    processed_left: Vec<f64>,
    processed_right: Vec<f64>,
    limited_left: Vec<f64>,
    limited_right: Vec<f64>,
    pending_pcm: Option<Vec<i16>>,
    pending_state: Option<RenderState>,
    pending_input_frames: usize,
    diagnostics: BlockRenderDiagnostics,
    sink_finished: bool,
}

impl std::fmt::Debug for StatefulBlockRenderer {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("StatefulBlockRenderer")
            .field("event_count", &self.program.event_count())
            .field("block_frames", &self.config.block_frames)
            .field("current_frame", &self.state.current_frame)
            .field("active_events", &self.state.events.len())
            .field("has_pending_pcm", &self.pending_pcm.is_some())
            .finish()
    }
}

impl StatefulBlockRenderer {
    pub fn new(program: CompiledSynthProgram, config: BlockRenderConfig) -> SynthResult<Self> {
        Self::new_inner(program, config, None)
    }

    #[allow(dead_code)]
    pub(crate) fn new_with_normaliser(
        program: CompiledSynthProgram,
        config: BlockRenderConfig,
        normaliser_config: CausalNormaliserConfig,
    ) -> SynthResult<Self> {
        let normaliser = CausalNormaliser::new(program.sample_rate(), normaliser_config)?;
        Self::new_inner(program, config, Some(normaliser))
    }

    fn new_inner(
        program: CompiledSynthProgram,
        config: BlockRenderConfig,
        normaliser: Option<CausalNormaliser>,
    ) -> SynthResult<Self> {
        let config = config.validate()?;
        let (fx_buses, routes) = StatefulFxBusGraph::compile(&program)?;
        let event_templates = routes
            .into_iter()
            .enumerate()
            .map(|(index, route)| ActiveEvent::from_program(&program, index, route))
            .collect::<SynthResult<Vec<_>>>()?;
        let pcm_capacity = config
            .block_frames
            .checked_mul(2)
            .ok_or_else(|| SynthError::new("stateful render block PCM capacity overflowed."))?;
        let limiter = StatefulLimiter::new(program.sample_rate());
        let mut diagnostics = BlockRenderDiagnostics {
            normaliser_latency_frames: normaliser
                .as_ref()
                .map_or(0, CausalNormaliser::latency_frames),
            limiter_latency_frames: limiter.latency_frames(),
            ..BlockRenderDiagnostics::default()
        };
        let scratch_bytes = pcm_capacity * std::mem::size_of::<i16>()
            + config.block_frames * 6 * std::mem::size_of::<f64>();
        diagnostics.observe_scratch(scratch_bytes);
        Ok(Self {
            state: RenderState {
                next_event: 0,
                current_frame: 0,
                events: Vec::new(),
                fx_buses,
                normaliser,
                limiter,
            },
            program,
            config,
            event_templates,
            block_pcm: Vec::with_capacity(pcm_capacity),
            raw_left: Vec::with_capacity(config.block_frames),
            raw_right: Vec::with_capacity(config.block_frames),
            processed_left: Vec::with_capacity(config.block_frames),
            processed_right: Vec::with_capacity(config.block_frames),
            limited_left: Vec::with_capacity(config.block_frames),
            limited_right: Vec::with_capacity(config.block_frames),
            pending_pcm: None,
            pending_state: None,
            pending_input_frames: 0,
            diagnostics,
            sink_finished: false,
        })
    }

    #[allow(dead_code)]
    pub fn diagnostics(&self) -> BlockRenderDiagnostics {
        self.diagnostics
    }

    pub fn render_to_sink<S: PcmSink>(&mut self, sink: &mut S) -> SynthResult<()> {
        while self.step(sink)? != BlockRenderStep::Finished {}
        Ok(())
    }

    pub fn step<S: PcmSink>(&mut self, sink: &mut S) -> SynthResult<BlockRenderStep> {
        if self.pending_pcm.is_some() {
            return self.accept_or_retain_pending(sink);
        }
        if self.is_finished() {
            if !self.sink_finished {
                sink.finish()?;
                self.sink_finished = true;
            }
            return Ok(BlockRenderStep::Finished);
        }

        let before = self.state.clone();
        let input_frames = self.render_block()?;
        let produced_frames = self.block_pcm.len() / 2;
        if produced_frames == 0 {
            self.observe_accepted_block(input_frames, 0);
            return Ok(BlockRenderStep::Produced { frames: 0 });
        }
        let after = self.state.clone();
        match sink.write_interleaved_i16(&self.block_pcm)? {
            SinkWrite::Accepted => {
                self.observe_accepted_block(input_frames, produced_frames);
                Ok(BlockRenderStep::Produced {
                    frames: produced_frames,
                })
            }
            SinkWrite::WouldBlock => {
                self.pending_pcm = Some(self.block_pcm.clone());
                self.pending_state = Some(after);
                self.pending_input_frames = input_frames;
                self.state = before;
                self.diagnostics.sink_would_block_count += 1;
                self.diagnostics.sink_pending_peak_frames = self
                    .diagnostics
                    .sink_pending_peak_frames
                    .max(produced_frames);
                Ok(BlockRenderStep::Produced { frames: 0 })
            }
        }
    }

    fn accept_or_retain_pending<S: PcmSink>(
        &mut self,
        sink: &mut S,
    ) -> SynthResult<BlockRenderStep> {
        let pending = self
            .pending_pcm
            .as_ref()
            .ok_or_else(|| SynthError::new("stateful renderer lost pending PCM."))?;
        let frames = pending.len() / 2;
        match sink.write_interleaved_i16(pending)? {
            SinkWrite::Accepted => {
                self.state = self.pending_state.take().ok_or_else(|| {
                    SynthError::new("stateful renderer lost pending render state.")
                })?;
                self.pending_pcm = None;
                let input_frames = std::mem::take(&mut self.pending_input_frames);
                self.observe_accepted_block(input_frames, frames);
                Ok(BlockRenderStep::Produced { frames })
            }
            SinkWrite::WouldBlock => {
                self.diagnostics.sink_would_block_count += 1;
                Ok(BlockRenderStep::Produced { frames: 0 })
            }
        }
    }

    fn render_block(&mut self) -> SynthResult<usize> {
        self.block_pcm.clear();
        self.raw_left.clear();
        self.raw_right.clear();
        self.processed_left.clear();
        self.processed_right.clear();
        self.limited_left.clear();
        self.limited_right.clear();
        let end_frame = self
            .state
            .current_frame
            .saturating_add(self.config.block_frames);
        while self.state.current_frame < end_frame && !self.sources_finished() {
            while self.program.event_frame(self.state.next_event) == Some(self.state.current_frame)
            {
                self.state.events.push(
                    self.event_templates
                        .get(self.state.next_event)
                        .ok_or_else(|| {
                            SynthError::new("compiled synth event template index is malformed.")
                        })?
                        .clone(),
                );
                self.state.next_event += 1;
            }
            let mut root = (0.0, 0.0);
            let mut root_active = false;
            for event in &mut self.state.events {
                if let Some(sample) = event.next_sample(self.program.sample_rate()) {
                    if event.route.is_some() {
                        self.state.fx_buses.mix_into(event.route, sample)?;
                    } else {
                        root.0 += sample.0;
                        root.1 += sample.1;
                        root_active = true;
                    }
                }
            }
            self.state.events.retain(|event| !event.is_finished());
            let (root, bus_active) = self.state.fx_buses.process_frame(
                self.state.current_frame,
                self.program.sample_rate(),
                root,
                root_active,
            )?;
            if !self.program.is_frame_bounded()
                && self.state.next_event >= self.program.event_count()
                && self.state.events.is_empty()
                && !bus_active
            {
                break;
            }
            self.raw_left.push(root.0);
            self.raw_right.push(root.1);
            self.state.current_frame += 1;
        }
        let input_frames = self.raw_left.len();
        if let Some(normaliser) = self.state.normaliser.as_mut() {
            if self.raw_left.is_empty() {
                normaliser.flush_up_to_into(
                    self.config.block_frames,
                    &mut self.processed_left,
                    &mut self.processed_right,
                );
            } else {
                normaliser.process_into(
                    &self.raw_left,
                    &self.raw_right,
                    &mut self.processed_left,
                    &mut self.processed_right,
                )?;
            }
        } else {
            self.processed_left.extend_from_slice(&self.raw_left);
            self.processed_right.extend_from_slice(&self.raw_right);
        }
        if self.processed_left.is_empty()
            && self.sources_finished()
            && self
                .state
                .normaliser
                .as_ref()
                .is_none_or(CausalNormaliser::is_idle)
        {
            self.state.limiter.flush_up_to_into(
                self.config.block_frames,
                &mut self.limited_left,
                &mut self.limited_right,
            );
        } else {
            self.state.limiter.process_into(
                &self.processed_left,
                &self.processed_right,
                &mut self.limited_left,
                &mut self.limited_right,
            )?;
        }
        for (&left, &right) in self.limited_left.iter().zip(&self.limited_right) {
            self.block_pcm.push(float_to_pcm(left));
            self.block_pcm.push(float_to_pcm(right));
        }
        let active = self.state.events.len();
        let tailing = self
            .state
            .fx_buses
            .buses
            .iter()
            .filter(|bus| bus.tail_remaining > 0)
            .count();
        self.diagnostics
            .observe_active_state(active, self.state.fx_buses.buses.len());
        self.diagnostics.processor_state_bytes = self
            .state
            .events
            .iter()
            .map(ActiveEvent::state_bytes)
            .sum::<usize>()
            + self.state.fx_buses.state_bytes()
            + self.state.normaliser.as_ref().map_or(0, |normaliser| {
                normaliser.latency_frames() * 2 * std::mem::size_of::<f64>()
            })
            + self.state.limiter.lookahead_frames * 4 * std::mem::size_of::<f64>()
            + std::mem::size_of::<StatefulLimiter>();
        self.diagnostics.tail_frames_rendered += tailing as u64;
        Ok(input_frames)
    }

    fn observe_accepted_block(&mut self, input_frames: usize, output_frames: usize) {
        self.diagnostics.blocks += 1;
        self.diagnostics.rendered_input_frames += input_frames as u64;
        self.diagnostics.rendered_output_frames += output_frames as u64;
    }

    fn sources_finished(&self) -> bool {
        if self.program.is_frame_bounded() {
            self.state.current_frame >= self.program.duration_frames()
        } else {
            self.state.next_event >= self.program.event_count()
                && self.state.events.is_empty()
                && self.state.fx_buses.is_idle()
        }
    }

    fn is_finished(&self) -> bool {
        self.sources_finished()
            && self
                .state
                .normaliser
                .as_ref()
                .is_none_or(CausalNormaliser::is_idle)
            && self.state.limiter.is_idle()
    }
}

fn validate_source_control_keys(event: &EventPayload, supported: &[&str]) -> SynthResult<()> {
    for control in &event.controls {
        for key in control.opts.keys() {
            let base = key.strip_suffix("_slide").unwrap_or(key);
            if !supported.contains(&base) {
                return Err(SynthError::new(format!(
                    "stateful block renderer does not support control field {key:?} for {} events.",
                    event.kind
                )));
            }
        }
    }
    Ok(())
}

fn validate_option_keys(opts: &OptMap, supported: &[&str], label: &str) -> SynthResult<()> {
    let mut unsupported: Vec<&str> = opts
        .keys()
        .map(String::as_str)
        .filter(|key| !supported.contains(key))
        .collect();
    unsupported.sort_unstable();
    if unsupported.is_empty() {
        Ok(())
    } else {
        Err(SynthError::new(format!(
            "{label} is not yet supported for key(s): {}.",
            unsupported.join(", ")
        )))
    }
}

fn float_to_pcm(sample: f64) -> i16 {
    (sample.clamp(-1.0, 1.0) * i16::MAX as f64).round() as i16
}
