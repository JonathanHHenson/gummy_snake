use super::*;

#[derive(Clone, Debug, PartialEq)]
pub enum SynthValue {
    None,
    Bool(bool),
    Float(f64),
    String(String),
    List(Vec<SynthValue>),
    Dict(OptMap),
}

pub type OptMap = HashMap<String, SynthValue>;

/// Rust-owned failure detail for synth plan decoding, sample rendering, and DSP.
/// `gummy_canvas` maps this typed error to the established extension exception surface.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SynthError {
    message: String,
}

impl SynthError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }

    pub fn message(&self) -> &str {
        &self.message
    }
}

impl std::fmt::Display for SynthError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for SynthError {}

pub type SynthResult<T> = Result<T, SynthError>;

#[derive(Clone, Debug, PartialEq)]
pub struct FxPayload {
    pub id: u64,
    pub name: String,
    pub opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ControlPayload {
    pub time_seconds: f64,
    pub opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ScheduledControlPayload {
    pub(crate) target_instance_key: String,
    pub(crate) target_id: u64,
    pub(crate) time_seconds: f64,
    pub(crate) opts: OptMap,
    pub(crate) order: u64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EventPayload {
    pub node_id: u64,
    pub seed: u64,
    pub order: u64,
    pub kind: String,
    pub time_seconds: f64,
    pub value: SynthValue,
    pub opts: OptMap,
    pub synth_name: String,
    pub synth_opts: OptMap,
    pub fx_chain: Vec<FxPayload>,
    pub controls: Vec<ControlPayload>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum SynthKind {
    Silence,
    Sine,
    Saw,
    Pulse,
    Tri,
    Fm,
    Noise,
    PinkNoise,
    BrownNoise,
    GreyNoise,
    ClipNoise,
    Layered,
    Unknown,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct LayerSpec {
    pub(crate) kind: SynthKind,
    pub(crate) waveform: &'static str,
    pub(crate) transpose: f64,
    pub(crate) amp: f64,
    pub(crate) opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ScheduledFxPayload {
    pub(crate) id: u64,
    pub(crate) name: String,
    pub(crate) opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ScheduledEventPayload {
    pub(crate) instance_key: String,
    pub(crate) node_id: u64,
    pub(crate) seed: u64,
    pub(crate) order: u64,
    pub(crate) kind: String,
    pub(crate) time_seconds: f64,
    pub(crate) value: SynthValue,
    pub(crate) opts: OptMap,
    pub(crate) synth_name: String,
    pub(crate) synth_opts: OptMap,
    pub(crate) fx_chain: Vec<ScheduledFxPayload>,
}

pub(crate) const GSS_MAGIC: &[u8; 8] = b"GSSPLAN\x01";
pub(crate) const GSS_COMPRESSION_ZLIB: u32 = 1;
pub(crate) const PHYSICAL_PLAN_SCHEMA: &str = "gummysnake.synth.physical_plan.v1";

#[cfg(test)]
pub(crate) const PRIMITIVE_SYNTH_KEYS: &[&str] = &[
    "_silence", "_beep", "_sine", "_saw", "_pulse", "_square", "_tri", "_fm", "_noise", "_pnoise",
    "_bnoise", "_gnoise", "_cnoise", "_layered",
];

pub(crate) fn synth_key(name: &str) -> String {
    name.trim_start_matches(':').to_ascii_lowercase()
}

pub(crate) fn synth_kind(name: &str) -> SynthKind {
    match synth_key(name).as_str() {
        "_silence" => SynthKind::Silence,
        "_beep" | "_sine" => SynthKind::Sine,
        "_saw" => SynthKind::Saw,
        "_pulse" | "_square" => SynthKind::Pulse,
        "_tri" => SynthKind::Tri,
        "_fm" => SynthKind::Fm,
        "_noise" => SynthKind::Noise,
        "_pnoise" => SynthKind::PinkNoise,
        "_bnoise" => SynthKind::BrownNoise,
        "_gnoise" => SynthKind::GreyNoise,
        "_cnoise" => SynthKind::ClipNoise,
        "_layered" => SynthKind::Layered,
        _ => SynthKind::Unknown,
    }
}
