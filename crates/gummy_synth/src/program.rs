use super::*;
use std::ops::Range;

/// Stable frame time used by the compiled synth execution schedule.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct SynthFrame(u64);

impl SynthFrame {
    pub fn get(self) -> u64 {
        self.0
    }

    pub(crate) fn as_usize(self) -> usize {
        self.0 as usize
    }
}

/// Stable program-local event identifier.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct CompiledEventId(u32);

impl CompiledEventId {
    pub fn get(self) -> u32 {
        self.0
    }
}

/// Stable program-local identifier-table index.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct InternedIdentifier(u32);

impl InternedIdentifier {
    pub fn get(self) -> u32 {
        self.0
    }
}

/// Typed source route selected during compilation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CompiledEventKind {
    Play,
    Sample,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum CompiledBlockFxKind {
    Chain,
    Level,
    Distortion,
    Tanh,
    Pan,
    RingMod,
    LowPass,
    ResonantLowPass,
    HighPass,
    ResonantHighPass,
    Compressor,
    Echo,
    Bitcrusher,
    Krush,
    Reverb,
    Gverb,
    Slicer,
    PanSlicer,
    Wobble,
    IxiTechno,
    Whammy,
    NormalisedLowPass,
    NormalisedResonantLowPass,
    NormalisedHighPass,
    NormalisedResonantHighPass,
    BandPass,
    NormalisedBandPass,
    ResonantBandPass,
    NormalisedResonantBandPass,
    BandEq,
    Normaliser,
    PitchShift,
    Octaver,
    Vowel,
    Flanger,
    Unsupported,
}

#[derive(Clone, Debug)]
pub(crate) struct CompiledControlData {
    pub(crate) frame: SynthFrame,
    pub(crate) parameter_ids: Range<usize>,
}

#[derive(Clone, Debug)]
pub(crate) struct CompiledFxData {
    pub(crate) identifier: InternedIdentifier,
    pub(crate) kind: CompiledBlockFxKind,
}

#[derive(Clone, Debug)]
pub(crate) struct CompiledEventData {
    pub(crate) id: CompiledEventId,
    pub(crate) frame: SynthFrame,
    pub(crate) processor_frame_offset: usize,
    pub(crate) kind: CompiledEventKind,
    pub(crate) synth_kind: SynthKind,
    pub(crate) source_identifier: InternedIdentifier,
    pub(crate) options: OptMap,
    pub(crate) control_range: Range<usize>,
    pub(crate) fx_range: Range<usize>,
}

#[derive(Debug)]
struct CompiledProgramData {
    sample_rate: u32,
    duration_seconds: f64,
    duration_frames: usize,
    frame_bounded: bool,
    events: Box<[EventPayload]>,
    execution_events: Box<[CompiledEventData]>,
    controls: Box<[CompiledControlData]>,
    control_parameter_ids: Box<[InternedIdentifier]>,
    fx: Box<[CompiledFxData]>,
    identifiers: Box<[String]>,
    node_event_index: HashMap<u64, Vec<CompiledEventId>>,
    fx_target_index: HashMap<u64, Vec<CompiledEventId>>,
}

/// Immutable Rust-owned scheduling and execution form for a physical synth plan.
///
/// Cloning a program only clones an `Arc`. Event and control times are converted
/// once to integer frames, source and FX routes are typed, identifiers are
/// interned, controls and FX metadata are contiguous, and target indexes are
/// reusable by every render session.
#[derive(Clone, Debug)]
pub struct CompiledSynthProgram {
    inner: Arc<CompiledProgramData>,
}

impl CompiledSynthProgram {
    /// Validate and compile already-typed events into stable frame order.
    pub fn compile(
        events: Vec<EventPayload>,
        duration_seconds: f64,
        sample_rate: u32,
    ) -> SynthResult<Self> {
        Self::compile_with_processor_offsets(
            events.into_iter().map(|event| (event, 0)).collect(),
            duration_seconds,
            sample_rate,
            true,
        )
    }

    /// Compile one event as a standalone signal while preserving its absolute
    /// processor phase origin. This matches the established single-event WAV
    /// route, which does not prepend silence for `time_seconds`.
    pub(crate) fn compile_standalone_event(
        event: &EventPayload,
        sample_rate: u32,
    ) -> SynthResult<Self> {
        validate_event(event, sample_rate)?;
        let origin_frame = seconds_to_frame(event.time_seconds, sample_rate, "synth event time")?;
        let mut standalone = event.clone();
        standalone.time_seconds = 0.0;
        for control in &mut standalone.controls {
            control.time_seconds = (control.time_seconds - event.time_seconds).max(0.0);
        }
        Self::compile_with_processor_offsets(
            vec![(standalone, origin_frame)],
            0.0,
            sample_rate,
            false,
        )
    }

    fn compile_with_processor_offsets(
        events: Vec<(EventPayload, usize)>,
        duration_seconds: f64,
        sample_rate: u32,
        frame_bounded: bool,
    ) -> SynthResult<Self> {
        let duration_frames =
            checked_frame_count(duration_seconds, sample_rate, "synth plan duration", 1)?;
        if events.len() > MAX_PLAN_EVENTS {
            return Err(SynthError::new(format!(
                "synth plan event count {} exceeds the limit of {MAX_PLAN_EVENTS}.",
                events.len()
            )));
        }
        for (event, _) in &events {
            validate_event(event, sample_rate)?;
            if event.time_seconds > duration_seconds {
                return Err(SynthError::new(format!(
                    "synth event time {} exceeds plan duration {duration_seconds}.",
                    event.time_seconds
                )));
            }
        }
        let mut scheduled = Vec::with_capacity(events.len());
        for (event, processor_frame_offset) in events {
            let event_frame =
                seconds_to_frame(event.time_seconds, sample_rate, "synth event time")?;
            let mut control_frames = Vec::with_capacity(event.controls.len());
            for control in &event.controls {
                control_frames.push(seconds_to_frame(
                    control.time_seconds,
                    sample_rate,
                    "synth control time",
                )?);
            }
            scheduled.push((event, event_frame, processor_frame_offset, control_frames));
        }
        scheduled.sort_by(|(left, left_frame, _, _), (right, right_frame, _, _)| {
            left_frame
                .cmp(right_frame)
                .then_with(|| left.order.cmp(&right.order))
                .then_with(|| left.node_id.cmp(&right.node_id))
        });

        let mut interner = IdentifierInterner::default();
        let mut compiled_events = Vec::with_capacity(scheduled.len());
        let mut execution_events = Vec::with_capacity(scheduled.len());
        let mut controls = Vec::new();
        let mut control_parameter_ids = Vec::new();
        let mut compiled_fx = Vec::new();
        let mut node_event_index: HashMap<u64, Vec<CompiledEventId>> = HashMap::new();
        let mut fx_target_index: HashMap<u64, Vec<CompiledEventId>> = HashMap::new();

        for (index, (event, event_frame, processor_frame_offset, control_frames)) in
            scheduled.into_iter().enumerate()
        {
            let id = CompiledEventId(u32::try_from(index).map_err(|_| {
                SynthError::new("compiled synth event index exceeds the stable local ID range.")
            })?);
            let kind = match event.kind.as_str() {
                "play" => CompiledEventKind::Play,
                "sample" => CompiledEventKind::Sample,
                unsupported => {
                    return Err(SynthError::new(format!(
                        "unsupported synth event kind {unsupported:?}; expected 'play' or 'sample'."
                    )))
                }
            };
            let synth_kind = if kind == CompiledEventKind::Play {
                synth_kind(&event.synth_name)
            } else {
                SynthKind::Unknown
            };
            let source_name = match kind {
                CompiledEventKind::Play => synth_key(&event.synth_name),
                CompiledEventKind::Sample => "sample".to_owned(),
            };
            let source_identifier = interner.intern(source_name)?;
            let mut options = event.synth_opts.clone();
            options.extend(event.opts.clone());

            let control_start = controls.len();
            for (control, frame) in event.controls.iter().zip(control_frames) {
                let parameter_start = control_parameter_ids.len();
                let mut parameter_names = control.opts.keys().collect::<Vec<_>>();
                parameter_names.sort_unstable();
                for name in parameter_names {
                    control_parameter_ids.push(interner.intern(name.clone())?);
                }
                controls.push(CompiledControlData {
                    frame: SynthFrame(frame as u64),
                    parameter_ids: parameter_start..control_parameter_ids.len(),
                });
            }

            let fx_start = compiled_fx.len();
            for fx in &event.fx_chain {
                let normalised = normalise_fx_identifier(&fx.name);
                compiled_fx.push(CompiledFxData {
                    identifier: interner.intern(normalised.clone())?,
                    kind: compiled_block_fx_kind(&normalised),
                });
                fx_target_index.entry(fx.id).or_default().push(id);
            }

            node_event_index.entry(event.node_id).or_default().push(id);
            execution_events.push(CompiledEventData {
                id,
                frame: SynthFrame(event_frame as u64),
                processor_frame_offset,
                kind,
                synth_kind,
                source_identifier,
                options,
                control_range: control_start..controls.len(),
                fx_range: fx_start..compiled_fx.len(),
            });
            compiled_events.push(event);
        }

        Ok(Self {
            inner: Arc::new(CompiledProgramData {
                sample_rate,
                duration_seconds,
                duration_frames,
                frame_bounded,
                events: compiled_events.into_boxed_slice(),
                execution_events: execution_events.into_boxed_slice(),
                controls: controls.into_boxed_slice(),
                control_parameter_ids: control_parameter_ids.into_boxed_slice(),
                fx: compiled_fx.into_boxed_slice(),
                identifiers: interner.identifiers.into_boxed_slice(),
                node_event_index,
                fx_target_index,
            }),
        })
    }

    /// Decode and compile a serialized physical plan once for a target rate.
    pub fn from_serialized_plan(payload: &[u8], sample_rate: u32) -> SynthResult<Self> {
        let (events, duration_seconds) = parse_serialized_plan(payload)
            .map_err(|error| SynthError::new(format!("ValueError: {error}")))?;
        Self::compile(events, duration_seconds, sample_rate)
    }

    pub fn sample_rate(&self) -> u32 {
        self.inner.sample_rate
    }

    pub fn duration_seconds(&self) -> f64 {
        self.inner.duration_seconds
    }

    pub fn duration_frames(&self) -> usize {
        self.inner.duration_frames
    }

    pub fn event_count(&self) -> usize {
        self.inner.events.len()
    }

    pub fn event_id(&self, index: usize) -> Option<CompiledEventId> {
        self.inner.execution_events.get(index).map(|event| event.id)
    }

    pub fn event_time(&self, index: usize) -> Option<SynthFrame> {
        self.inner
            .execution_events
            .get(index)
            .map(|event| event.frame)
    }

    pub fn event_kind(&self, index: usize) -> Option<CompiledEventKind> {
        self.inner
            .execution_events
            .get(index)
            .map(|event| event.kind)
    }

    pub fn source_identifier(&self, index: usize) -> Option<InternedIdentifier> {
        self.inner
            .execution_events
            .get(index)
            .map(|event| event.source_identifier)
    }

    pub fn identifier_count(&self) -> usize {
        self.inner.identifiers.len()
    }

    pub fn identifier(&self, id: InternedIdentifier) -> Option<&str> {
        self.inner
            .identifiers
            .get(id.0 as usize)
            .map(String::as_str)
    }

    pub fn event_ids_for_node(&self, node_id: u64) -> &[CompiledEventId] {
        self.inner
            .node_event_index
            .get(&node_id)
            .map(Vec::as_slice)
            .unwrap_or_default()
    }

    pub fn event_ids_for_fx_target(&self, fx_id: u64) -> &[CompiledEventId] {
        self.inner
            .fx_target_index
            .get(&fx_id)
            .map(Vec::as_slice)
            .unwrap_or_default()
    }

    pub fn control_count(&self) -> usize {
        self.inner.controls.len()
    }

    pub fn control_parameter_count(&self) -> usize {
        self.inner.control_parameter_ids.len()
    }

    pub fn control_time(&self, event_index: usize, control_index: usize) -> Option<SynthFrame> {
        let event = self.inner.execution_events.get(event_index)?;
        self.inner
            .controls
            .get(event.control_range.start.saturating_add(control_index))
            .filter(|_| control_index < event.control_range.len())
            .map(|control| control.frame)
    }

    pub fn control_parameters(
        &self,
        event_index: usize,
        control_index: usize,
    ) -> Option<&[InternedIdentifier]> {
        let event = self.inner.execution_events.get(event_index)?;
        let control = self
            .inner
            .controls
            .get(event.control_range.start.saturating_add(control_index))
            .filter(|_| control_index < event.control_range.len())?;
        Some(&self.inner.control_parameter_ids[control.parameter_ids.clone()])
    }

    pub(crate) fn is_frame_bounded(&self) -> bool {
        self.inner.frame_bounded
    }

    pub(crate) fn event_frame(&self, index: usize) -> Option<usize> {
        self.event_time(index).map(SynthFrame::as_usize)
    }

    pub(crate) fn control_frames(&self, index: usize) -> Option<Vec<usize>> {
        let event = self.inner.execution_events.get(index)?;
        Some(
            self.inner.controls[event.control_range.clone()]
                .iter()
                .map(|control| control.frame.as_usize())
                .collect(),
        )
    }

    pub(crate) fn events(&self) -> &[EventPayload] {
        &self.inner.events
    }

    pub(crate) fn execution_event(&self, index: usize) -> Option<&CompiledEventData> {
        self.inner.execution_events.get(index)
    }

    pub(crate) fn execution_fx(&self, index: usize) -> Option<&[CompiledFxData]> {
        let event = self.inner.execution_events.get(index)?;
        Some(&self.inner.fx[event.fx_range.clone()])
    }
}

#[derive(Default)]
struct IdentifierInterner {
    identifiers: Vec<String>,
    indexes: HashMap<String, InternedIdentifier>,
}

impl IdentifierInterner {
    fn intern(&mut self, value: String) -> SynthResult<InternedIdentifier> {
        if let Some(id) = self.indexes.get(&value) {
            return Ok(*id);
        }
        let id = InternedIdentifier(u32::try_from(self.identifiers.len()).map_err(|_| {
            SynthError::new("compiled synth identifier table exceeds the stable local ID range.")
        })?);
        self.identifiers.push(value.clone());
        self.indexes.insert(value, id);
        Ok(id)
    }
}

fn normalise_fx_identifier(name: &str) -> String {
    name.trim_start_matches(':')
        .trim_start_matches('_')
        .to_ascii_lowercase()
}

fn compiled_block_fx_kind(name: &str) -> CompiledBlockFxKind {
    match name {
        "chain" => CompiledBlockFxKind::Chain,
        "level" => CompiledBlockFxKind::Level,
        "distortion" => CompiledBlockFxKind::Distortion,
        "tanh" => CompiledBlockFxKind::Tanh,
        "pan" => CompiledBlockFxKind::Pan,
        "ring_mod" => CompiledBlockFxKind::RingMod,
        "lpf" | "lowpass" => CompiledBlockFxKind::LowPass,
        "rlpf" => CompiledBlockFxKind::ResonantLowPass,
        "hpf" | "highpass" => CompiledBlockFxKind::HighPass,
        "rhpf" => CompiledBlockFxKind::ResonantHighPass,
        "compressor" => CompiledBlockFxKind::Compressor,
        "echo" => CompiledBlockFxKind::Echo,
        "bitcrusher" => CompiledBlockFxKind::Bitcrusher,
        "krush" => CompiledBlockFxKind::Krush,
        "reverb" => CompiledBlockFxKind::Reverb,
        "gverb" => CompiledBlockFxKind::Gverb,
        "slicer" => CompiledBlockFxKind::Slicer,
        "panslicer" | "pan_slicer" => CompiledBlockFxKind::PanSlicer,
        "wobble" => CompiledBlockFxKind::Wobble,
        "ixi_techno" => CompiledBlockFxKind::IxiTechno,
        "whammy" => CompiledBlockFxKind::Whammy,
        "nrlpf" => CompiledBlockFxKind::NormalisedResonantLowPass,
        "nrhpf" => CompiledBlockFxKind::NormalisedResonantHighPass,
        "nhpf" => CompiledBlockFxKind::NormalisedHighPass,
        "nlpf" => CompiledBlockFxKind::NormalisedLowPass,
        "bpf" => CompiledBlockFxKind::BandPass,
        "nbpf" => CompiledBlockFxKind::NormalisedBandPass,
        "rbpf" => CompiledBlockFxKind::ResonantBandPass,
        "nrbpf" => CompiledBlockFxKind::NormalisedResonantBandPass,
        "band_eq" => CompiledBlockFxKind::BandEq,
        "normaliser" | "normalizer" => CompiledBlockFxKind::Normaliser,
        "pitch_shift" => CompiledBlockFxKind::PitchShift,
        "octaver" => CompiledBlockFxKind::Octaver,
        "vowel" => CompiledBlockFxKind::Vowel,
        "flanger" => CompiledBlockFxKind::Flanger,
        _ => CompiledBlockFxKind::Unsupported,
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
