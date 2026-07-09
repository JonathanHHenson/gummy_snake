use flate2::read::ZlibDecoder;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList, PyTuple};
use serde_json::Value as JsonValue;
use std::collections::HashMap;
use std::f64::consts::{FRAC_1_SQRT_2, PI, TAU};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

#[derive(Clone, Debug, PartialEq)]
enum SynthValue {
    None,
    Bool(bool),
    Float(f64),
    String(String),
    List(Vec<SynthValue>),
    Dict(OptMap),
}

type OptMap = HashMap<String, SynthValue>;

#[derive(Clone, Debug, PartialEq)]
struct FxPayload {
    id: u64,
    name: String,
    opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
struct ControlPayload {
    time_seconds: f64,
    opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
struct ScheduledControlPayload {
    target_instance_key: String,
    target_id: u64,
    time_seconds: f64,
    opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
struct EventPayload {
    node_id: u64,
    kind: String,
    time_seconds: f64,
    value: SynthValue,
    opts: OptMap,
    synth_name: String,
    synth_opts: OptMap,
    fx_chain: Vec<FxPayload>,
    controls: Vec<ControlPayload>,
}

#[derive(Clone, Debug, PartialEq)]
struct FxOptionSnapshot {
    time_seconds: f64,
    opts: OptMap,
}

#[derive(Clone, Debug)]
struct FxBusNode {
    fx: Option<FxPayload>,
    input_left: Vec<f64>,
    input_right: Vec<f64>,
    option_snapshots: Vec<FxOptionSnapshot>,
    children: Vec<FxBusNode>,
    time_origin_seconds: f64,
}

#[derive(Debug)]
pub struct SynthPlaybackPlan {
    events: Vec<EventPayload>,
    duration_seconds: f64,
    dry_event_cache: Mutex<HashMap<(usize, u32), Arc<StereoEventSignal>>>,
}

#[derive(Debug)]
struct StereoEventSignal {
    left: Vec<f64>,
    right: Vec<f64>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum SynthKind {
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
struct LayerSpec {
    kind: SynthKind,
    waveform: &'static str,
    transpose: f64,
    amp: f64,
    opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
struct ScheduledFxPayload {
    id: u64,
    name: String,
    opts: OptMap,
}

#[derive(Clone, Debug, PartialEq)]
struct ScheduledEventPayload {
    instance_key: String,
    node_id: u64,
    kind: String,
    time_seconds: f64,
    value: SynthValue,
    opts: OptMap,
    synth_name: String,
    synth_opts: OptMap,
    fx_chain: Vec<ScheduledFxPayload>,
}

const GSS_MAGIC: &[u8; 8] = b"GSSPLAN\x01";
const GSS_COMPRESSION_ZLIB: u32 = 1;
const PHYSICAL_PLAN_SCHEMA: &str = "gummysnake.synth.physical_plan.v1";

#[cfg(test)]
const PRIMITIVE_SYNTH_KEYS: &[&str] = &[
    "_silence", "_beep", "_sine", "_saw", "_pulse", "_square", "_tri", "_fm", "_noise", "_pnoise",
    "_bnoise", "_gnoise", "_cnoise", "_layered",
];

fn synth_key(name: &str) -> String {
    name.trim_start_matches(':').to_ascii_lowercase()
}

fn synth_kind(name: &str) -> SynthKind {
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

pub fn register_pyfunctions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(synth_render_event_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_render_plan_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_render_serialized_plan_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_sample_duration, m)?)?;
    Ok(())
}

#[pyfunction]
pub fn synth_render_event_wav<'py>(
    py: Python<'py>,
    event: &Bound<'_, PyDict>,
    sample_rate: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let event = parse_event(event)?;
    let (left, right) = render_event(&event, sample_rate)?;
    let (left, right) = output_limit_pair(&left, &right, sample_rate);
    let payload = stereo_wav_bytes(&left, &right, sample_rate);
    Ok(PyBytes::new_bound(py, &payload))
}

#[pyfunction]
pub fn synth_render_plan_wav<'py>(
    py: Python<'py>,
    events: &Bound<'_, PyList>,
    duration_seconds: f64,
    sample_rate: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let mut parsed_events = Vec::with_capacity(events.len());
    for event in events.iter() {
        let dict = event.downcast::<PyDict>()?;
        parsed_events.push(parse_event(dict)?);
    }
    let payload = render_plan_events(parsed_events, duration_seconds, sample_rate)?;
    Ok(PyBytes::new_bound(py, &payload))
}

#[pyfunction]
pub fn synth_render_serialized_plan_wav<'py>(
    py: Python<'py>,
    payload: &Bound<'_, PyBytes>,
    sample_rate: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let payload = render_serialized_plan_wav_bytes(payload.as_bytes(), sample_rate)?;
    Ok(PyBytes::new_bound(py, &payload))
}

pub fn render_serialized_plan_wav_bytes(payload: &[u8], sample_rate: u32) -> PyResult<Vec<u8>> {
    let (events, duration_seconds) = parse_serialized_plan(payload)?;
    render_plan_events(events, duration_seconds, sample_rate)
}

fn render_plan_events(
    mut parsed_events: Vec<EventPayload>,
    duration_seconds: f64,
    sample_rate: u32,
) -> PyResult<Vec<u8>> {
    if duration_seconds < 0.0 {
        return Err(PyValueError::new_err(
            "synth plan render duration cannot be negative.",
        ));
    }
    parsed_events.sort_by(|a, b| a.time_seconds.total_cmp(&b.time_seconds));
    let total_samples = (duration_seconds * sample_rate as f64).ceil().max(1.0) as usize;
    let mut root = FxBusNode::root(total_samples, 0.0);
    for event in parsed_events {
        let (event_left, event_right) = render_dry_event(&event, sample_rate)?;
        let start = (event.time_seconds * sample_rate as f64).round().max(0.0) as usize;
        root.mix_event(
            &event.fx_chain,
            event.time_seconds,
            start,
            &event_left,
            &event_right,
        );
    }
    let (left, right) = root.render(sample_rate);
    let (left, right) = output_limit_prefix(&left, &right, total_samples, sample_rate);
    Ok(stereo_wav_bytes(&left, &right, sample_rate))
}

fn render_plan_window_samples(
    plan: &SynthPlaybackPlan,
    start_seconds: f64,
    duration_seconds: f64,
    sample_rate: u32,
) -> PyResult<(Vec<f64>, Vec<f64>)> {
    if start_seconds < 0.0 || duration_seconds < 0.0 {
        return Err(PyValueError::new_err(
            "synth live render window start and duration cannot be negative.",
        ));
    }
    if sample_rate == 0 {
        return Err(PyValueError::new_err(
            "synth live render sample rate must be greater than zero.",
        ));
    }
    if start_seconds >= plan.duration_seconds || duration_seconds <= 0.0 {
        return Ok((Vec::new(), Vec::new()));
    }

    let window_start = start_seconds;
    let window_duration = duration_seconds.min(plan.duration_seconds - window_start);
    let window_samples = (window_duration * sample_rate as f64).ceil().max(0.0) as usize;
    if window_samples == 0 {
        return Ok((Vec::new(), Vec::new()));
    }

    let context_start = (window_start - live_render_context_seconds()).max(0.0);
    let context_end = window_start + window_duration;
    let context_samples = ((context_end - context_start) * sample_rate as f64)
        .ceil()
        .max(1.0) as usize;
    let mut root = FxBusNode::root(context_samples, context_start);
    let mut sorted_events: Vec<(usize, &EventPayload)> = plan.events.iter().enumerate().collect();
    sorted_events.sort_by(|(_, a), (_, b)| a.time_seconds.total_cmp(&b.time_seconds));

    for (event_index, event) in sorted_events {
        if event.time_seconds >= context_end {
            break;
        }
        let signal = plan.dry_event_signal(event_index, event, sample_rate)?;
        let event_len = signal.left.len().max(signal.right.len());
        if event_len == 0 {
            continue;
        }
        let event_end = event.time_seconds + event_len as f64 / sample_rate as f64;
        if event_end <= context_start {
            continue;
        }
        let skip = ((context_start - event.time_seconds) * sample_rate as f64)
            .round()
            .max(0.0) as usize;
        let skip_left = skip.min(signal.left.len());
        let skip_right = skip.min(signal.right.len());
        let start = ((event.time_seconds - context_start) * sample_rate as f64)
            .round()
            .max(0.0) as usize;
        root.mix_event(
            &event.fx_chain,
            event.time_seconds,
            start,
            &signal.left[skip_left..],
            &signal.right[skip_right..],
        );
    }

    let (left, right) = root.render(sample_rate);
    let offset = ((window_start - context_start) * sample_rate as f64)
        .round()
        .max(0.0) as usize;
    Ok(output_limit_window(
        &left,
        &right,
        offset,
        window_samples,
        sample_rate,
    ))
}

fn live_render_context_seconds() -> f64 {
    4.0
}

impl SynthPlaybackPlan {
    pub fn from_serialized_plan(payload: &[u8]) -> PyResult<Self> {
        let (events, duration_seconds) = parse_serialized_plan(payload)?;
        Ok(Self {
            events,
            duration_seconds,
            dry_event_cache: Mutex::new(HashMap::new()),
        })
    }

    pub fn duration_seconds(&self) -> f64 {
        self.duration_seconds
    }

    pub fn render_window_i16(
        &self,
        start_seconds: f64,
        duration_seconds: f64,
        sample_rate: u32,
    ) -> PyResult<Vec<i16>> {
        let (left, right) =
            render_plan_window_samples(self, start_seconds, duration_seconds, sample_rate)?;
        Ok(samples_to_interleaved_i16(
            &left,
            &right,
            left.len().min(right.len()),
        ))
    }

    fn dry_event_signal(
        &self,
        event_index: usize,
        event: &EventPayload,
        sample_rate: u32,
    ) -> PyResult<Arc<StereoEventSignal>> {
        let key = (event_index, sample_rate);
        if let Some(cached) = self
            .dry_event_cache
            .lock()
            .map_err(|_| PyValueError::new_err("synth dry-event cache lock was poisoned."))?
            .get(&key)
            .cloned()
        {
            return Ok(cached);
        }

        let (left, right) = render_dry_event(event, sample_rate)?;
        let rendered = Arc::new(StereoEventSignal { left, right });
        let mut cache = self
            .dry_event_cache
            .lock()
            .map_err(|_| PyValueError::new_err("synth dry-event cache lock was poisoned."))?;
        Ok(cache
            .entry(key)
            .or_insert_with(|| Arc::clone(&rendered))
            .clone())
    }
}

impl FxBusNode {
    fn root(total_samples: usize, time_origin_seconds: f64) -> Self {
        Self {
            fx: None,
            input_left: vec![0.0; total_samples],
            input_right: vec![0.0; total_samples],
            option_snapshots: Vec::new(),
            children: Vec::new(),
            time_origin_seconds,
        }
    }

    fn for_fx(fx: &FxPayload, total_samples: usize, time_origin_seconds: f64) -> Self {
        Self {
            fx: Some(fx.clone()),
            input_left: vec![0.0; total_samples],
            input_right: vec![0.0; total_samples],
            option_snapshots: Vec::new(),
            children: Vec::new(),
            time_origin_seconds,
        }
    }

    fn mix_event(
        &mut self,
        fx_chain: &[FxPayload],
        event_time_seconds: f64,
        start_sample: usize,
        left: &[f64],
        right: &[f64],
    ) {
        if let Some((fx, remaining_chain)) = fx_chain.split_first() {
            let child = self.child_mut(fx);
            child.option_snapshots.push(FxOptionSnapshot {
                time_seconds: event_time_seconds,
                opts: fx.opts.clone(),
            });
            child.mix_event(
                remaining_chain,
                event_time_seconds,
                start_sample,
                left,
                right,
            );
            return;
        }
        mix_signal_into(
            &mut self.input_left,
            &mut self.input_right,
            start_sample,
            left,
            right,
        );
    }

    fn child_mut(&mut self, fx: &FxPayload) -> &mut FxBusNode {
        if let Some(index) = self.children.iter().position(|child| child.matches_fx(fx)) {
            return &mut self.children[index];
        }
        let total_samples = self.input_left.len().max(self.input_right.len()).max(1);
        self.children.push(FxBusNode::for_fx(
            fx,
            total_samples,
            self.time_origin_seconds,
        ));
        self.children
            .last_mut()
            .expect("FX bus child was just appended")
    }

    fn matches_fx(&self, fx: &FxPayload) -> bool {
        self.fx
            .as_ref()
            .is_some_and(|current| current.id == fx.id && current.name == fx.name)
    }

    fn render(mut self, sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
        for child in self.children {
            let (child_left, child_right) = child.render(sample_rate);
            mix_signal_into(
                &mut self.input_left,
                &mut self.input_right,
                0,
                &child_left,
                &child_right,
            );
        }
        let Some(fx) = self.fx else {
            return (self.input_left, self.input_right);
        };
        render_fx_bus_signal(
            &fx,
            &self.option_snapshots,
            self.input_left,
            self.input_right,
            sample_rate,
            self.time_origin_seconds,
        )
    }
}

fn render_fx_bus_signal(
    fx: &FxPayload,
    snapshots: &[FxOptionSnapshot],
    input_left: Vec<f64>,
    input_right: Vec<f64>,
    sample_rate: u32,
    time_origin_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let segments = fx_option_segments(
        fx,
        snapshots,
        input_left.len().max(input_right.len()),
        sample_rate,
        time_origin_seconds,
    );
    if segments.len() == 1 && segments[0].0 == 0 {
        return apply_fx(
            &fx.name,
            input_left,
            input_right,
            &segments[0].2,
            sample_rate,
            time_origin_seconds,
        );
    }

    let mut output_left = vec![0.0; input_left.len().max(input_right.len())];
    let mut output_right = vec![0.0; input_left.len().max(input_right.len())];
    for (start, end, opts) in segments {
        if start >= end {
            continue;
        }
        let segment_left = slice_with_zeros(&input_left, start, end);
        let segment_right = slice_with_zeros(&input_right, start, end);
        if is_silent_pair(&segment_left, &segment_right) {
            continue;
        }
        let start_time_seconds = time_origin_seconds + start as f64 / sample_rate as f64;
        let (fx_left, fx_right) = apply_fx(
            &fx.name,
            segment_left,
            segment_right,
            &opts,
            sample_rate,
            start_time_seconds,
        );
        mix_signal_into(
            &mut output_left,
            &mut output_right,
            start,
            &fx_left,
            &fx_right,
        );
    }
    (output_left, output_right)
}

fn fx_option_segments(
    fx: &FxPayload,
    snapshots: &[FxOptionSnapshot],
    input_len: usize,
    sample_rate: u32,
    time_origin_seconds: f64,
) -> Vec<(usize, usize, OptMap)> {
    let bounded_len = input_len.max(1);
    let mut sorted = snapshots.to_vec();
    sorted.sort_by(|a, b| a.time_seconds.total_cmp(&b.time_seconds));
    let mut starts = vec![(0usize, fx.opts.clone())];
    for snapshot in sorted {
        let start = ((snapshot.time_seconds - time_origin_seconds) * sample_rate as f64)
            .round()
            .max(0.0) as usize;
        let start = start.min(bounded_len);
        if starts.last().is_some_and(|(last_start, last_opts)| {
            *last_start == start && *last_opts == snapshot.opts
        }) {
            continue;
        }
        if starts
            .last()
            .is_some_and(|(_last_start, last_opts)| *last_opts == snapshot.opts)
        {
            continue;
        }
        starts.push((start, snapshot.opts));
    }
    starts.sort_by(|a, b| a.0.cmp(&b.0));
    let mut segments = Vec::with_capacity(starts.len());
    for (index, (start, opts)) in starts.iter().enumerate() {
        let end = starts
            .get(index + 1)
            .map(|(next_start, _)| *next_start)
            .unwrap_or(bounded_len);
        if *start < end {
            segments.push((*start, end, opts.clone()));
        }
    }
    if segments.is_empty() {
        segments.push((0, bounded_len, fx.opts.clone()));
    }
    segments
}

fn mix_signal_into(
    target_left: &mut Vec<f64>,
    target_right: &mut Vec<f64>,
    start: usize,
    left: &[f64],
    right: &[f64],
) {
    let required = start + left.len().max(right.len());
    if target_left.len() < required {
        target_left.resize(required, 0.0);
    }
    if target_right.len() < required {
        target_right.resize(required, 0.0);
    }
    for index in 0..required.saturating_sub(start) {
        target_left[start + index] += left.get(index).copied().unwrap_or(0.0);
        target_right[start + index] += right.get(index).copied().unwrap_or(0.0);
    }
}

fn slice_with_zeros(samples: &[f64], start: usize, end: usize) -> Vec<f64> {
    (start..end)
        .map(|index| samples.get(index).copied().unwrap_or(0.0))
        .collect()
}

fn is_silent_pair(left: &[f64], right: &[f64]) -> bool {
    left.iter()
        .chain(right.iter())
        .all(|sample| sample.abs() <= f64::EPSILON)
}

#[pyfunction]
pub fn synth_sample_duration(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let value = parse_py_value(value)?;
    sample_source(&value, 44_100).map(|source| source.duration)
}

fn parse_event(dict: &Bound<'_, PyDict>) -> PyResult<EventPayload> {
    Ok(EventPayload {
        node_id: get_u64(dict, "node_id", 0)?,
        kind: get_string(dict, "kind", "play")?,
        time_seconds: get_f64(dict, "time_seconds", 0.0)?,
        value: parse_py_value(&get_item(dict, "value")?)?,
        opts: get_opt_map(dict, "opts")?,
        synth_name: get_string(dict, "synth_name", "beep")?,
        synth_opts: get_opt_map(dict, "synth_opts")?,
        fx_chain: get_fx_chain(dict)?,
        controls: get_controls(dict)?,
    })
}

fn get_item<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)?.ok_or_else(|| {
        PyValueError::new_err(format!(
            "synth event payload is missing required key {key:?}."
        ))
    })
}

fn get_u64(dict: &Bound<'_, PyDict>, key: &str, default: u64) -> PyResult<u64> {
    match dict.get_item(key)? {
        Some(value) => {
            if let Ok(value) = value.extract::<u64>() {
                Ok(value)
            } else if let Ok(value) = value.extract::<i64>() {
                Ok(value.max(0) as u64)
            } else {
                Err(PyValueError::new_err(format!(
                    "synth event key {key:?} must be an integer."
                )))
            }
        }
        None => Ok(default),
    }
}

fn get_f64(dict: &Bound<'_, PyDict>, key: &str, default: f64) -> PyResult<f64> {
    match dict.get_item(key)? {
        Some(value) => value.extract::<f64>().map_err(|_| {
            PyValueError::new_err(format!("synth event key {key:?} must be numeric."))
        }),
        None => Ok(default),
    }
}

fn get_string(dict: &Bound<'_, PyDict>, key: &str, default: &str) -> PyResult<String> {
    match dict.get_item(key)? {
        Some(value) => value.extract::<String>().map_err(|_| {
            PyValueError::new_err(format!("synth event key {key:?} must be a string."))
        }),
        None => Ok(default.to_owned()),
    }
}

fn get_opt_map(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<OptMap> {
    match dict.get_item(key)? {
        Some(value) => parse_opt_map(value.downcast::<PyDict>()?),
        None => Ok(OptMap::new()),
    }
}

fn get_fx_chain(dict: &Bound<'_, PyDict>) -> PyResult<Vec<FxPayload>> {
    let Some(value) = dict.get_item("fx_chain")? else {
        return Ok(Vec::new());
    };
    let list = value.downcast::<PyList>()?;
    let mut output = Vec::with_capacity(list.len());
    for item in list.iter() {
        let item = item.downcast::<PyDict>()?;
        output.push(FxPayload {
            id: get_u64(item, "id", 0)?,
            name: get_string(item, "name", "")?,
            opts: get_opt_map(item, "opts")?,
        });
    }
    Ok(output)
}

fn get_controls(dict: &Bound<'_, PyDict>) -> PyResult<Vec<ControlPayload>> {
    let Some(value) = dict.get_item("controls")? else {
        return Ok(Vec::new());
    };
    let list = value.downcast::<PyList>()?;
    let mut output = Vec::with_capacity(list.len());
    for item in list.iter() {
        let item = item.downcast::<PyDict>()?;
        output.push(ControlPayload {
            time_seconds: get_f64(item, "time_seconds", 0.0)?,
            opts: get_opt_map(item, "opts")?,
        });
    }
    output.sort_by(|a, b| a.time_seconds.total_cmp(&b.time_seconds));
    Ok(output)
}

fn parse_opt_map(dict: &Bound<'_, PyDict>) -> PyResult<OptMap> {
    let mut output = OptMap::with_capacity(dict.len());
    for (key, value) in dict.iter() {
        output.insert(key.extract::<String>()?, parse_py_value(&value)?);
    }
    Ok(output)
}

fn parse_py_value(value: &Bound<'_, PyAny>) -> PyResult<SynthValue> {
    if value.is_none() {
        return Ok(SynthValue::None);
    }
    if let Ok(value) = value.extract::<bool>() {
        return Ok(SynthValue::Bool(value));
    }
    if let Ok(value) = value.extract::<f64>() {
        return Ok(SynthValue::Float(value));
    }
    if let Ok(value) = value.extract::<String>() {
        return Ok(SynthValue::String(value));
    }
    if let Ok(list) = value.downcast::<PyList>() {
        return parse_sequence(list.iter());
    }
    if let Ok(tuple) = value.downcast::<PyTuple>() {
        return parse_sequence(tuple.iter());
    }
    if let Ok(dict) = value.downcast::<PyDict>() {
        return Ok(SynthValue::Dict(parse_opt_map(dict)?));
    }
    Err(PyValueError::new_err(
        "synth payload values must be None, bool, number, string, list, or tuple.",
    ))
}

fn parse_sequence<'py>(items: impl Iterator<Item = Bound<'py, PyAny>>) -> PyResult<SynthValue> {
    let mut output = Vec::new();
    for item in items {
        output.push(parse_py_value(&item)?);
    }
    Ok(SynthValue::List(output))
}

fn parse_serialized_plan(payload: &[u8]) -> PyResult<(Vec<EventPayload>, f64)> {
    if payload.len() < 16 {
        return Err(PyValueError::new_err(
            "serialized synth physical plan is too short.",
        ));
    }
    if &payload[..8] != GSS_MAGIC {
        return Err(PyValueError::new_err(
            "serialized synth physical plan has an invalid binary header.",
        ));
    }
    let compression = u32::from_be_bytes(payload[8..12].try_into().map_err(|_| {
        PyValueError::new_err("serialized synth physical plan has an invalid compression header.")
    })?);
    let raw_size = u32::from_be_bytes(payload[12..16].try_into().map_err(|_| {
        PyValueError::new_err("serialized synth physical plan has an invalid size header.")
    })?) as usize;
    if compression != GSS_COMPRESSION_ZLIB {
        return Err(PyValueError::new_err(format!(
            "unsupported synth physical-plan compression mode {compression}."
        )));
    }
    let mut decoder = ZlibDecoder::new(&payload[16..]);
    let mut raw = Vec::with_capacity(raw_size);
    decoder.read_to_end(&mut raw).map_err(|err| {
        PyValueError::new_err(format!(
            "could not decompress serialized synth physical plan: {err}"
        ))
    })?;
    if raw.len() != raw_size {
        return Err(PyValueError::new_err(
            "serialized synth physical plan size check failed.",
        ));
    }
    let root: JsonValue = serde_json::from_slice(&raw).map_err(|err| {
        PyValueError::new_err(format!(
            "serialized synth physical plan JSON is invalid: {err}"
        ))
    })?;
    let root = root.as_object().ok_or_else(|| {
        PyValueError::new_err("serialized synth physical plan payload must be an object.")
    })?;
    let schema = root
        .get("schema")
        .and_then(JsonValue::as_str)
        .unwrap_or_default();
    if schema != PHYSICAL_PLAN_SCHEMA {
        return Err(PyValueError::new_err(format!(
            "unsupported synth physical-plan schema {schema:?}."
        )));
    }
    let duration_seconds = root
        .get("duration_seconds")
        .and_then(JsonValue::as_f64)
        .unwrap_or(0.0);
    let controls = parse_serialized_controls(root.get("controls"))?;
    let scheduled_events = parse_serialized_events(root.get("events"))?;
    let events = scheduled_events
        .into_iter()
        .map(|event| event.with_controls(&controls))
        .collect();
    Ok((events, duration_seconds))
}

fn parse_serialized_events(value: Option<&JsonValue>) -> PyResult<Vec<ScheduledEventPayload>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let events = value.as_array().ok_or_else(|| {
        PyValueError::new_err("serialized synth physical plan events must be a list.")
    })?;
    events.iter().map(parse_serialized_event).collect()
}

fn parse_serialized_event(value: &JsonValue) -> PyResult<ScheduledEventPayload> {
    let object = value
        .as_object()
        .ok_or_else(|| PyValueError::new_err("serialized synth event must be an object."))?;
    Ok(ScheduledEventPayload {
        instance_key: json_key(object.get("instance").unwrap_or(&JsonValue::Null)),
        node_id: json_u64(object.get("node_id"), 0),
        kind: json_string(object.get("kind"), "play"),
        time_seconds: json_f64(object.get("time_seconds"), 0.0),
        value: json_to_synth_value(object.get("value").unwrap_or(&JsonValue::Null))?,
        opts: json_to_opt_map(object.get("opts"))?,
        synth_name: json_string(object.get("synth_name"), "beep"),
        synth_opts: json_to_opt_map(object.get("synth_opts"))?,
        fx_chain: parse_serialized_fx_chain(object.get("fx_chain"))?,
    })
}

fn parse_serialized_fx_chain(value: Option<&JsonValue>) -> PyResult<Vec<ScheduledFxPayload>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let handles = value
        .as_array()
        .ok_or_else(|| PyValueError::new_err("serialized synth event fx_chain must be a list."))?;
    handles
        .iter()
        .map(|value| {
            let object = value.as_object().ok_or_else(|| {
                PyValueError::new_err("serialized synth FX handle must be an object.")
            })?;
            Ok(ScheduledFxPayload {
                id: json_u64(object.get("id"), 0),
                name: json_string(object.get("name"), "level"),
                opts: json_to_opt_map(object.get("opts"))?,
            })
        })
        .collect()
}

fn parse_serialized_controls(value: Option<&JsonValue>) -> PyResult<Vec<ScheduledControlPayload>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let controls = value.as_array().ok_or_else(|| {
        PyValueError::new_err("serialized synth physical plan controls must be a list.")
    })?;
    controls
        .iter()
        .map(|value| {
            let object = value.as_object().ok_or_else(|| {
                PyValueError::new_err("serialized synth control must be an object.")
            })?;
            Ok(ScheduledControlPayload {
                target_instance_key: json_key(
                    object.get("target_instance").unwrap_or(&JsonValue::Null),
                ),
                target_id: json_u64(object.get("target_id"), 0),
                time_seconds: json_f64(object.get("time_seconds"), 0.0),
                opts: json_to_opt_map(object.get("opts"))?,
            })
        })
        .collect()
}

impl ScheduledEventPayload {
    fn with_controls(self, controls: &[ScheduledControlPayload]) -> EventPayload {
        let event_controls = controls
            .iter()
            .filter(|control| control.target_instance_key == self.instance_key)
            .map(|control| ControlPayload {
                time_seconds: control.time_seconds,
                opts: control.opts.clone(),
            })
            .collect();
        let fx_chain = self
            .fx_chain
            .into_iter()
            .map(|fx| {
                let mut opts = fx.opts;
                for control in controls {
                    if control.target_id == fx.id
                        && control.time_seconds <= self.time_seconds + 1e-9
                    {
                        opts.extend(control.opts.clone());
                    }
                }
                FxPayload {
                    id: fx.id,
                    name: fx.name,
                    opts,
                }
            })
            .collect();
        EventPayload {
            node_id: self.node_id,
            kind: self.kind,
            time_seconds: self.time_seconds,
            value: self.value,
            opts: self.opts,
            synth_name: self.synth_name,
            synth_opts: self.synth_opts,
            fx_chain,
            controls: event_controls,
        }
    }
}

fn json_to_synth_value(value: &JsonValue) -> PyResult<SynthValue> {
    match value {
        JsonValue::Null => Ok(SynthValue::None),
        JsonValue::Bool(value) => Ok(SynthValue::Bool(*value)),
        JsonValue::Number(value) => value.as_f64().map(SynthValue::Float).ok_or_else(|| {
            PyValueError::new_err("serialized synth numeric value is not representable as f64.")
        }),
        JsonValue::String(value) => Ok(SynthValue::String(value.clone())),
        JsonValue::Array(values) => values
            .iter()
            .map(json_to_synth_value)
            .collect::<PyResult<Vec<_>>>()
            .map(SynthValue::List),
        JsonValue::Object(mapping) => {
            let mut output = OptMap::with_capacity(mapping.len());
            for (key, value) in mapping {
                output.insert(key.clone(), json_to_synth_value(value)?);
            }
            Ok(SynthValue::Dict(output))
        }
    }
}

fn json_to_opt_map(value: Option<&JsonValue>) -> PyResult<OptMap> {
    let Some(value) = value else {
        return Ok(OptMap::new());
    };
    let object = value
        .as_object()
        .ok_or_else(|| PyValueError::new_err("serialized synth opts must be an object."))?;
    let mut output = OptMap::with_capacity(object.len());
    for (key, value) in object {
        output.insert(key.clone(), json_to_synth_value(value)?);
    }
    Ok(output)
}

fn json_key(value: &JsonValue) -> String {
    match value {
        JsonValue::Array(values) => {
            let parts: Vec<String> = values.iter().map(json_key).collect();
            format!("[{}]", parts.join(","))
        }
        JsonValue::Object(mapping) => {
            let mut parts: Vec<String> = mapping
                .iter()
                .map(|(key, value)| format!("{key}:{}", json_key(value)))
                .collect();
            parts.sort();
            format!("{{{}}}", parts.join(","))
        }
        other => other.to_string(),
    }
}

fn json_string(value: Option<&JsonValue>, default: &str) -> String {
    value
        .and_then(JsonValue::as_str)
        .unwrap_or(default)
        .to_owned()
}

fn json_f64(value: Option<&JsonValue>, default: f64) -> f64 {
    value.and_then(JsonValue::as_f64).unwrap_or(default)
}

fn json_u64(value: Option<&JsonValue>, default: u64) -> u64 {
    value.and_then(JsonValue::as_u64).unwrap_or(default)
}

fn render_dry_event(event: &EventPayload, sample_rate: u32) -> PyResult<(Vec<f64>, Vec<f64>)> {
    if event.kind == "sample" {
        render_sample_event(event, sample_rate)
    } else {
        render_synth_event(event, sample_rate)
    }
}

fn render_event(event: &EventPayload, sample_rate: u32) -> PyResult<(Vec<f64>, Vec<f64>)> {
    let (mut left, mut right) = render_dry_event(event, sample_rate)?;
    for fx in event.fx_chain.iter().rev() {
        let (new_left, new_right) = apply_fx(
            &fx.name,
            left,
            right,
            &fx.opts,
            sample_rate,
            event.time_seconds,
        );
        left = new_left;
        right = new_right;
    }
    Ok((left, right))
}

fn render_synth_event(event: &EventPayload, sample_rate: u32) -> PyResult<(Vec<f64>, Vec<f64>)> {
    let kind = synth_kind(&event.synth_name);
    let mut opts = event.synth_opts.clone();
    opts.extend(event.opts.clone());

    if matches!(kind, SynthKind::Silence) {
        return Ok(render_no_source_event(&opts, sample_rate));
    }
    if matches!(kind, SynthKind::Layered) {
        return render_layered_synth_event(event, &opts, sample_rate);
    }

    let note_source = opts.get("note").unwrap_or(&event.value);
    let notes = note_values(note_source)?;
    if notes.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }

    let (default_attack, default_decay, default_sustain, default_release) =
        default_synth_envelope(kind);
    let attack = float_opt(&opts, "attack", default_attack).max(0.0);
    let decay = float_opt(&opts, "decay", default_decay).max(0.0);
    let sustain = float_opt(&opts, "sustain", default_sustain).max(0.0);
    let release = float_opt(&opts, "release", default_release).max(0.0);
    let natural_tail = natural_synth_tail(kind, &opts);
    let total_seconds = (attack + decay + sustain + release)
        .max(natural_tail)
        .max(0.01);
    let count = (total_seconds * sample_rate as f64).ceil() as usize;
    let amp = float_opt(&opts, "amp", 1.0).max(0.0) * synth_amp_fudge(kind, &opts);
    let env_curve = float_opt(&opts, "env_curve", 1.0).round() as i32;
    let attack_level = float_opt(&opts, "attack_level", 1.0).max(0.0);
    let sustain_level = float_opt(&opts, "sustain_level", 1.0).max(0.0);
    let decay_level = decay_level_opt(&opts, sustain_level);
    let waveform = synth_waveform(kind, &opts);
    let pan_base = float_opt(&opts, "pan", 0.0);
    let note_auto = automation(notes[0], "note", &event.controls, &opts, event.time_seconds);
    let cutoff_auto = automation(
        Some(float_opt(&opts, "cutoff", default_synth_cutoff(kind))),
        "cutoff",
        &event.controls,
        &opts,
        event.time_seconds,
    );
    let cutoff_is_automated = event
        .controls
        .iter()
        .any(|control| control.opts.contains_key("cutoff"));
    let pan_auto = automation(
        Some(pan_base),
        "pan",
        &event.controls,
        &opts,
        event.time_seconds,
    );
    let mut mono = Vec::with_capacity(count);
    let mut phases = vec![0.0; notes.len()];
    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed,
            attack,
            decay,
            sustain,
            release,
            attack_level,
            decay_level,
            sustain_level,
            env_curve,
        );
        let mut current_notes = notes.clone();
        if current_notes.len() == 1 {
            current_notes[0] = note_auto(elapsed);
        }
        let mut sample = 0.0;
        let mut active_voices = 0usize;
        for (note_index, midi_note) in current_notes.iter().enumerate() {
            let Some(midi_note) = midi_note else {
                continue;
            };
            let modulated_note = modulated_midi_note(kind, *midi_note, &opts, elapsed);
            let freq = note_frequency(modulated_note).max(0.0);
            let phase_delta = freq / sample_rate as f64;
            let voice = synth_voice(
                kind,
                waveform,
                phases[note_index],
                phase_delta,
                elapsed,
                level,
                index,
                note_index,
                &opts,
                event.node_id,
                sample_rate,
            );
            sample += voice;
            active_voices += 1;
            phases[note_index] = (phases[note_index] + phase_delta).rem_euclid(1.0);
        }
        if active_voices > 0 {
            sample /= active_voices as f64;
        }
        mono.push(sample);
    }
    let (processed_left, processed_right) = apply_synth_post_processing(
        kind,
        mono.clone(),
        mono,
        &opts,
        sample_rate,
        &*cutoff_auto,
        cutoff_is_automated,
    );
    let mut left = Vec::with_capacity(count);
    let mut right = Vec::with_capacity(count);
    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed,
            attack,
            decay,
            sustain,
            release,
            attack_level,
            decay_level,
            sustain_level,
            env_curve,
        );
        let pan = pan_auto(elapsed).unwrap_or(pan_base).clamp(-1.0, 1.0);
        let (left_gain, right_gain) = pan_gains(pan);
        left.push(processed_left.get(index).copied().unwrap_or(0.0) * level * amp * left_gain);
        right.push(processed_right.get(index).copied().unwrap_or(0.0) * level * amp * right_gain);
    }
    Ok((left, right))
}

fn render_layered_synth_event(
    event: &EventPayload,
    opts: &OptMap,
    sample_rate: u32,
) -> PyResult<(Vec<f64>, Vec<f64>)> {
    let layers = layered_specs(opts);
    if layers.is_empty() {
        return Ok(render_no_source_event(opts, sample_rate));
    }

    let note_source = opts.get("note").unwrap_or(&event.value);
    let notes = note_values(note_source)?;
    if notes.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }

    let (default_attack, default_decay, default_sustain, default_release) =
        default_synth_envelope(SynthKind::Layered);
    let attack = float_opt(opts, "attack", default_attack).max(0.0);
    let decay = float_opt(opts, "decay", default_decay).max(0.0);
    let sustain = float_opt(opts, "sustain", default_sustain).max(0.0);
    let release = float_opt(opts, "release", default_release).max(0.0);
    let natural_tail = natural_synth_tail(SynthKind::Layered, opts);
    let total_seconds = (attack + decay + sustain + release)
        .max(natural_tail)
        .max(0.01);
    let count = (total_seconds * sample_rate as f64).ceil() as usize;
    let amp = float_opt(opts, "amp", 1.0).max(0.0) * synth_amp_fudge(SynthKind::Layered, opts);
    let env_curve = float_opt(opts, "env_curve", 1.0).round() as i32;
    let attack_level = float_opt(opts, "attack_level", 1.0).max(0.0);
    let sustain_level = float_opt(opts, "sustain_level", 1.0).max(0.0);
    let decay_level = decay_level_opt(opts, sustain_level);
    let pan_base = float_opt(opts, "pan", 0.0);
    let note_auto = automation(notes[0], "note", &event.controls, opts, event.time_seconds);
    let cutoff_auto = automation(
        Some(float_opt(
            opts,
            "cutoff",
            default_synth_cutoff(SynthKind::Layered),
        )),
        "cutoff",
        &event.controls,
        opts,
        event.time_seconds,
    );
    let cutoff_is_automated = event
        .controls
        .iter()
        .any(|control| control.opts.contains_key("cutoff"));
    let pan_auto = automation(
        Some(pan_base),
        "pan",
        &event.controls,
        opts,
        event.time_seconds,
    );
    let mut phases = vec![0.0; notes.len() * layers.len()];
    let mut mono = Vec::with_capacity(count);

    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed,
            attack,
            decay,
            sustain,
            release,
            attack_level,
            decay_level,
            sustain_level,
            env_curve,
        );
        let mut current_notes = notes.clone();
        if current_notes.len() == 1 {
            current_notes[0] = note_auto(elapsed);
        }
        let mut sample = 0.0;
        let mut active_base_notes = 0usize;
        for (note_index, midi_note) in current_notes.iter().enumerate() {
            let Some(midi_note) = midi_note else {
                continue;
            };
            active_base_notes += 1;
            for (layer_index, layer) in layers.iter().enumerate() {
                let phase_index = note_index * layers.len() + layer_index;
                let layer_note = *midi_note + layer.transpose;
                let modulated_note =
                    modulated_midi_note(layer.kind, layer_note, &layer.opts, elapsed);
                let freq = note_frequency(modulated_note).max(0.0);
                let phase_delta = freq / sample_rate as f64;
                let voice = synth_voice(
                    layer.kind,
                    layer.waveform,
                    phases[phase_index],
                    phase_delta,
                    elapsed,
                    level,
                    index,
                    phase_index,
                    &layer.opts,
                    event.node_id,
                    sample_rate,
                );
                sample += voice * layer.amp;
                phases[phase_index] = (phases[phase_index] + phase_delta).rem_euclid(1.0);
            }
        }
        if active_base_notes > 0 {
            sample /= active_base_notes as f64;
        }
        mono.push(sample);
    }

    let (processed_left, processed_right) = apply_synth_post_processing(
        SynthKind::Layered,
        mono.clone(),
        mono,
        opts,
        sample_rate,
        &*cutoff_auto,
        cutoff_is_automated,
    );
    let mut left = Vec::with_capacity(count);
    let mut right = Vec::with_capacity(count);
    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed,
            attack,
            decay,
            sustain,
            release,
            attack_level,
            decay_level,
            sustain_level,
            env_curve,
        );
        let pan = pan_auto(elapsed).unwrap_or(pan_base).clamp(-1.0, 1.0);
        let (left_gain, right_gain) = pan_gains(pan);
        left.push(processed_left.get(index).copied().unwrap_or(0.0) * level * amp * left_gain);
        right.push(processed_right.get(index).copied().unwrap_or(0.0) * level * amp * right_gain);
    }

    Ok((left, right))
}

fn layered_specs(opts: &OptMap) -> Vec<LayerSpec> {
    let Some(SynthValue::List(values)) = opts.get("layers") else {
        return Vec::new();
    };
    values
        .iter()
        .filter_map(|value| layer_spec(value, opts))
        .collect()
}

fn layer_spec(value: &SynthValue, base_opts: &OptMap) -> Option<LayerSpec> {
    let SynthValue::Dict(mapping) = value else {
        return None;
    };
    let wave = mapping.get("wave").and_then(value_as_str).unwrap_or("sine");
    let kind = synth_kind(&format!("_{}", wave.trim_start_matches('_')));
    let transpose = mapping
        .get("transpose")
        .and_then(value_as_f64)
        .unwrap_or(0.0);
    let amp = mapping.get("amp").and_then(value_as_f64).unwrap_or(1.0);
    let mut opts = base_opts.clone();
    opts.remove("layers");
    if let Some(SynthValue::Dict(layer_opts)) = mapping.get("opts") {
        opts.extend(layer_opts.clone());
    }
    Some(LayerSpec {
        kind,
        waveform: synth_waveform(kind, &opts),
        transpose,
        amp,
        opts,
    })
}

fn render_sample_event(event: &EventPayload, sample_rate: u32) -> PyResult<(Vec<f64>, Vec<f64>)> {
    let mut opts = event.synth_opts.clone();
    opts.extend(event.opts.clone());
    render_sample_event_with_opts(&event.value, &opts, sample_rate)
}

fn render_sample_event_with_opts(
    value: &SynthValue,
    opts: &OptMap,
    sample_rate: u32,
) -> PyResult<(Vec<f64>, Vec<f64>)> {
    let source = sample_source(value, sample_rate)?;
    let start = float_opt(opts, "start", 0.0).clamp(0.0, 1.0);
    let finish = float_opt(opts, "finish", 1.0).clamp(0.0, 1.0);
    let mut rate = float_opt(opts, "rate", 1.0);
    if opts.contains_key("rpitch") {
        rate *= 2.0_f64.powf(float_opt(opts, "rpitch", 0.0) / 12.0);
    }
    if opts.contains_key("pitch") {
        rate *= 2.0_f64.powf(float_opt(opts, "pitch", 0.0) / 12.0);
    }
    if opts.contains_key("beat_stretch") {
        rate = source.duration / float_opt(opts, "beat_stretch", 1.0).max(0.001);
    }
    if rate == 0.0 {
        return Err(PyValueError::new_err("sample rate cannot be zero."));
    }
    let reverse = rate < 0.0 || start > finish;
    let low = start.min(finish);
    let high = start.max(finish);
    let source_len = source.len();
    if source_len == 0 {
        return Ok((Vec::new(), Vec::new()));
    }
    let start_index = (low * source_len as f64) as usize;
    let end_index = ((high * source_len as f64) as usize).max(start_index + 1);
    let end_index = end_index.min(source_len);
    let mut segment_left = source.left[start_index..end_index].to_vec();
    let mut segment_right = source.right[start_index..end_index].to_vec();
    if reverse {
        segment_left.reverse();
        segment_right.reverse();
    }
    let pre_amp = float_opt(opts, "pre_amp", 1.0).max(0.0);
    if pre_amp != 1.0 {
        segment_left = scale_samples(&segment_left, pre_amp);
        segment_right = scale_samples(&segment_right, pre_amp);
    }
    let step = rate.abs();
    let output_count = ((segment_left.len() as f64 / step).ceil().max(1.0)) as usize;
    let attack = float_opt(opts, "attack", 0.0).max(0.0);
    let release = float_opt(opts, "release", 0.0).max(0.0);
    let sustain_opt = opts
        .get("sustain")
        .and_then(value_as_f64)
        .filter(|value| *value >= 0.0);
    let amp = float_opt(opts, "amp", 1.0).max(0.0);
    let env_curve = float_opt(opts, "env_curve", 1.0).round() as i32;
    let pan = float_opt(opts, "pan", 0.0);
    let (left_gain, right_gain) = pan_gains(pan);
    let total = output_count as f64 / sample_rate as f64;
    let sustain_auto = (total - attack - release).max(0.0);
    let sustain = sustain_opt.unwrap_or(sustain_auto);
    let mut left = Vec::with_capacity(output_count);
    let mut right = Vec::with_capacity(output_count);
    for index in 0..output_count {
        let source_pos = index as f64 * step;
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed, attack, 0.0, sustain, release, 1.0, 1.0, 1.0, env_curve,
        );
        let dry_left = sample_linear_clamped(&segment_left, source_pos) * level * amp;
        let dry_right = sample_linear_clamped(&segment_right, source_pos) * level * amp;
        if source.stereo {
            let balanced = balance2_sample(dry_left, dry_right, pan);
            left.push(balanced.0);
            right.push(balanced.1);
        } else {
            left.push(dry_left * left_gain);
            right.push(dry_left * right_gain);
        }
    }
    let cutoff = float_opt(opts, "cutoff", 0.0);
    if cutoff > 0.0 && cutoff < 130.5 {
        let res = float_opt(opts, "res", 0.0).clamp(0.0, 0.99);
        let cutoff_hz = note_frequency(cutoff).max(20.0);
        left = filter_samples(&left, cutoff_hz, sample_rate, FilterKind::Low, res);
        right = filter_samples(&right, cutoff_hz, sample_rate, FilterKind::Low, res);
    }
    if float_opt(opts, "norm", 0.0) >= 0.5 {
        (left, right) = normalise_pair(&left, &right, 1.0);
    }
    if float_opt(opts, "compress", 0.0) >= 0.5 {
        (left, right) = fx_compressor(&left, &right, opts, sample_rate);
    }
    Ok((left, right))
}

fn note_values(value: &SynthValue) -> PyResult<Vec<Option<f64>>> {
    match value {
        SynthValue::List(values) => values.iter().map(note).collect(),
        other => Ok(vec![note(other)?]),
    }
}

fn note(value: &SynthValue) -> PyResult<Option<f64>> {
    match value {
        SynthValue::None => Ok(None),
        SynthValue::Bool(false) => Ok(None),
        SynthValue::Bool(true) => Ok(Some(60.0)),
        SynthValue::Float(value) => Ok(Some(*value)),
        SynthValue::String(value) => note_name(value),
        SynthValue::List(_) | SynthValue::Dict(_) => Err(PyValueError::new_err(
            "Nested note values are not supported by the Rust synth renderer.",
        )),
    }
}

fn note_name(value: &str) -> PyResult<Option<f64>> {
    let text = value.trim().trim_start_matches(':').to_ascii_lowercase();
    if matches!(text.as_str(), "" | "r" | "rest" | "nil" | "none" | "false") {
        return Ok(None);
    }
    let mut chars = text.chars();
    let root = chars.next().unwrap_or('c');
    let rest: String = chars.collect();
    let (name, octave_text) =
        if rest.starts_with('#') || rest.starts_with('s') || rest.starts_with('b') {
            let accidental = if rest.starts_with('b') { "b" } else { "#" };
            (format!("{root}{accidental}"), rest[1..].to_owned())
        } else {
            (root.to_string(), rest)
        };
    let offset = match name.as_str() {
        "c" => 0,
        "c#" | "cs" | "db" => 1,
        "d" => 2,
        "d#" | "ds" | "eb" => 3,
        "e" => 4,
        "f" => 5,
        "f#" | "fs" | "gb" => 6,
        "g" => 7,
        "g#" | "gs" | "ab" => 8,
        "a" => 9,
        "a#" | "as" | "bb" => 10,
        "b" => 11,
        _ => {
            return Err(PyValueError::new_err(format!(
                "Unsupported note name: {value:?}."
            )))
        }
    };
    let octave = if octave_text.is_empty() {
        4
    } else {
        octave_text
            .parse::<i32>()
            .map_err(|_| PyValueError::new_err(format!("Unsupported note name: {value:?}.")))?
    };
    Ok(Some(((octave + 1) * 12 + offset) as f64))
}

fn note_frequency(midi: f64) -> f64 {
    440.0 * 2.0_f64.powf((midi - 69.0) / 12.0)
}

fn adsr_level(
    mut elapsed: f64,
    attack: f64,
    decay: f64,
    sustain: f64,
    release: f64,
    attack_level: f64,
    decay_level: f64,
    sustain_level: f64,
    env_curve: i32,
) -> f64 {
    if attack > 0.0 && elapsed < attack {
        return shaped_interpolate(0.0, attack_level, elapsed / attack, env_curve);
    }
    elapsed -= attack;
    if decay > 0.0 && elapsed < decay {
        return shaped_interpolate(attack_level, decay_level, elapsed / decay, env_curve);
    }
    elapsed -= decay;
    if elapsed < sustain {
        return sustain_level;
    }
    elapsed -= sustain;
    if release <= 0.0 {
        return 0.0;
    }
    shaped_interpolate(sustain_level, 0.0, elapsed / release, env_curve).max(0.0)
}

fn shaped_interpolate(start: f64, end: f64, position: f64, curve: i32) -> f64 {
    let t = position.clamp(0.0, 1.0);
    let amount = match curve {
        2 => exponential_curve_amount(start, end, t),
        3 => 0.5 - 0.5 * (PI * t).cos(),
        4 => {
            if end >= start {
                (PI * 0.5 * t).sin()
            } else {
                1.0 - (PI * 0.5 * (1.0 - t)).sin()
            }
        }
        6 => t * t,
        7 => t * t * t,
        _ => t,
    };
    start + (end - start) * amount.clamp(0.0, 1.0)
}

fn exponential_curve_amount(start: f64, end: f64, t: f64) -> f64 {
    if start > 1e-6 && end > 1e-6 && (start - end).abs() > 1e-9 {
        let value = start * (end / start).powf(t);
        return ((value - start) / (end - start)).clamp(0.0, 1.0);
    }
    if end >= start {
        t * t
    } else {
        1.0 - (1.0 - t) * (1.0 - t)
    }
}

fn decay_level_opt(opts: &OptMap, sustain_level: f64) -> f64 {
    let raw = float_opt(opts, "decay_level", -1.0);
    if raw < 0.0 {
        sustain_level
    } else {
        raw.max(0.0)
    }
}

fn default_synth_envelope(_kind: SynthKind) -> (f64, f64, f64, f64) {
    (0.0, 0.0, 0.0, 1.0)
}

fn natural_synth_tail(_kind: SynthKind, _opts: &OptMap) -> f64 {
    0.01
}

fn render_no_source_event(opts: &OptMap, sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
    let attack = float_opt(opts, "attack", 0.0).max(0.0);
    let decay = float_opt(opts, "decay", 0.0).max(0.0);
    let sustain = float_opt(opts, "sustain", 0.0).max(0.0);
    let release = float_opt(opts, "release", 0.01).max(0.01);
    let count = ((attack + decay + sustain + release) * sample_rate as f64)
        .ceil()
        .max(1.0) as usize;
    (vec![0.0; count], vec![0.0; count])
}

fn synth_waveform(kind: SynthKind, _opts: &OptMap) -> &'static str {
    match kind {
        SynthKind::Saw => "saw",
        SynthKind::Pulse => "square",
        SynthKind::Tri => "triangle",
        _ => "sine",
    }
}

#[allow(clippy::too_many_arguments)]
fn synth_voice(
    kind: SynthKind,
    waveform: &str,
    phase: f64,
    phase_delta: f64,
    elapsed: f64,
    env_level: f64,
    sample_index: usize,
    note_index: usize,
    opts: &OptMap,
    node_id: u64,
    _sample_rate: u32,
) -> f64 {
    let pulse_width = pulse_width_at(opts, elapsed).clamp(0.001, 0.999);
    let base = oscillator_value_with_width(waveform, phase, phase_delta, pulse_width);
    match kind {
        SynthKind::Fm => {
            let divisor = float_opt(opts, "divisor", 2.0).abs().max(0.001);
            let depth = float_opt(opts, "depth", 1.0);
            let modulator = (TAU * phase / divisor).sin();
            (TAU * phase + modulator * depth * divisor * env_level).sin()
        }
        SynthKind::Noise
        | SynthKind::PinkNoise
        | SynthKind::BrownNoise
        | SynthKind::GreyNoise
        | SynthKind::ClipNoise => noise_voice(kind, sample_index, note_index, node_id),
        _ => base,
    }
}

fn pulse_width_at(opts: &OptMap, elapsed: f64) -> f64 {
    let base = float_opt(opts, "pulse_width", 0.5);
    let rate = float_opt(opts, "pulse_width_lfo_rate", 0.0);
    let depth = float_opt(opts, "pulse_width_lfo_depth", 0.0);
    if rate.abs() <= f64::EPSILON || depth.abs() <= f64::EPSILON {
        return base;
    }
    let phase_seconds = (1.0 / rate.abs()).max(0.001);
    let phase_offset = float_opt(opts, "pulse_width_lfo_phase", 0.0);
    let wave = float_opt(opts, "pulse_width_lfo_wave", 3.0).round() as i32;
    let amount = lfo_amount(wave, elapsed, phase_seconds, phase_offset, 0.5) * 2.0 - 1.0;
    base + depth * amount
}

fn oscillator_value_with_width(
    waveform: &str,
    phase: f64,
    phase_delta: f64,
    pulse_width: f64,
) -> f64 {
    let phase = phase.rem_euclid(1.0);
    let dt = phase_delta.abs().clamp(1.0e-9, 0.5);
    match waveform {
        "square" => {
            let mut value = if phase < pulse_width { 1.0 } else { -1.0 };
            value += poly_blep(phase, dt);
            value -= poly_blep((phase - pulse_width).rem_euclid(1.0), dt);
            value.clamp(-1.0, 1.0)
        }
        "triangle" => 4.0 * (phase - 0.5).abs() - 1.0,
        "saw" => (2.0 * phase - 1.0) - poly_blep(phase, dt),
        _ => (TAU * phase).sin(),
    }
}

fn poly_blep(phase: f64, phase_delta: f64) -> f64 {
    if phase < phase_delta {
        let t = phase / phase_delta;
        t + t - t * t - 1.0
    } else if phase > 1.0 - phase_delta {
        let t = (phase - 1.0) / phase_delta;
        t * t + t + t + 1.0
    } else {
        0.0
    }
}

fn noise_voice(kind: SynthKind, sample_index: usize, note_index: usize, node_id: u64) -> f64 {
    let white = deterministic_noise(sample_index, note_index, node_id);
    match kind {
        SynthKind::ClipNoise => {
            if white >= 0.0 {
                1.0
            } else {
                -1.0
            }
        }
        SynthKind::GreyNoise => {
            let stepped = (white * 8.0).round() / 8.0;
            (stepped + deterministic_noise(sample_index / 2 + 13, note_index, node_id) * 0.25)
                .clamp(-1.0, 1.0)
        }
        SynthKind::PinkNoise => {
            (white + deterministic_noise(sample_index / 2 + 3, note_index, node_id) * 0.5) / 1.5
        }
        SynthKind::BrownNoise => {
            (white + deterministic_noise(sample_index / 4 + 5, note_index, node_id) * 0.8) / 1.8
        }
        _ => white,
    }
}

fn deterministic_noise(sample_index: usize, note_index: usize, node_id: u64) -> f64 {
    let x = (sample_index as f64 * 12.9898 + note_index as f64 * 78.233 + node_id as f64 * 37.719)
        .sin()
        * 43_758.545_3;
    (x - x.floor()) * 2.0 - 1.0
}

fn modulated_midi_note(_kind: SynthKind, midi_note: f64, _opts: &OptMap, _elapsed: f64) -> f64 {
    midi_note
}

fn apply_synth_post_processing(
    kind: SynthKind,
    mut left: Vec<f64>,
    mut right: Vec<f64>,
    opts: &OptMap,
    sample_rate: u32,
    cutoff_auto: &(dyn Fn(f64) -> Option<f64> + Send + Sync),
    cutoff_is_automated: bool,
) -> (Vec<f64>, Vec<f64>) {
    (left, right) = apply_pre_filter_shaping(left, right, opts);
    let cutoff = cutoff_auto(0.0).unwrap_or_else(|| default_synth_cutoff(kind));
    if cutoff > 0.0 && cutoff < 130.5 {
        let res = float_opt(opts, "res", default_synth_res(kind)).clamp(0.0, 0.99);
        let cutoff_envelope = cutoff_envelope_enabled(opts);
        if cutoff_is_automated || cutoff_envelope || res > 0.0 {
            let cutoff_hz = |index: usize| {
                let elapsed = index as f64 / sample_rate as f64;
                synth_cutoff_hz_at(kind, opts, cutoff_auto, cutoff, elapsed, sample_rate)
            };
            if res > 0.0 {
                (left, right) = resonant_modulated_filter_pair(
                    &left,
                    &right,
                    sample_rate,
                    FilterKind::Low,
                    sonic_filter_rq(res),
                    cutoff_hz,
                );
            } else {
                (left, right) = modulated_lowpass_pair(&left, &right, sample_rate, cutoff_hz);
            }
        } else {
            let cutoff_hz = note_frequency(cutoff).max(20.0);
            left = filter_samples(&left, cutoff_hz, sample_rate, FilterKind::Low, 0.0);
            right = filter_samples(&right, cutoff_hz, sample_rate, FilterKind::Low, 0.0);
        }
    }
    match kind {
        SynthKind::PinkNoise => {
            left = lowpass(&left, 6_000.0, sample_rate);
            right = lowpass(&right, 6_000.0, sample_rate);
        }
        SynthKind::BrownNoise => {
            left = lowpass(&left, 1_600.0, sample_rate);
            right = lowpass(&right, 1_600.0, sample_rate);
        }
        SynthKind::GreyNoise => {
            left = lowpass(&left, 2_400.0, sample_rate);
            right = lowpass(&right, 2_400.0, sample_rate);
        }
        _ => {}
    }
    if synth_normalise_enabled(kind, opts) {
        let level = float_opt(
            opts,
            "normalise_level",
            float_opt(opts, "normalize_level", 1.0),
        )
        .max(0.0);
        (left, right) = normalise_pair(&left, &right, level);
    }
    (left, right)
}

fn apply_pre_filter_shaping(
    mut left: Vec<f64>,
    mut right: Vec<f64>,
    opts: &OptMap,
) -> (Vec<f64>, Vec<f64>) {
    if bool_opt(opts, "pre_shape_normalise", false) || bool_opt(opts, "pre_shape_normalize", false)
    {
        let level = float_opt(opts, "pre_shape_level", 1.0).max(0.0);
        (left, right) = normalise_pair(&left, &right, level);
    }
    match string_opt(opts, "pre_filter_shape", "").as_str() {
        "square" | "squared" => {
            left = left.iter().map(|sample| sample * sample).collect();
            right = right.iter().map(|sample| sample * sample).collect();
        }
        "signed_square" | "signed_squared" => {
            left = left.iter().map(|sample| sample * sample.abs()).collect();
            right = right.iter().map(|sample| sample * sample.abs()).collect();
        }
        _ => {}
    }
    if bool_opt(opts, "pre_filter_normalise", false)
        || bool_opt(opts, "pre_filter_normalize", false)
    {
        let level = float_opt(opts, "pre_filter_level", 1.0).max(0.0);
        (left, right) = normalise_pair(&left, &right, level);
    }
    (left, right)
}

fn cutoff_envelope_enabled(opts: &OptMap) -> bool {
    [
        "cutoff_min",
        "cutoff_attack",
        "cutoff_decay",
        "cutoff_sustain",
        "cutoff_release",
        "cutoff_attack_level",
        "cutoff_decay_level",
        "cutoff_sustain_level",
    ]
    .iter()
    .any(|key| opts.contains_key(*key))
}

fn synth_cutoff_hz_at(
    kind: SynthKind,
    opts: &OptMap,
    cutoff_auto: &(dyn Fn(f64) -> Option<f64> + Send + Sync),
    default_cutoff: f64,
    elapsed: f64,
    sample_rate: u32,
) -> f64 {
    let cutoff_note = cutoff_auto(elapsed)
        .unwrap_or(default_cutoff)
        .clamp(0.001, 130.5);
    let cutoff_hz = note_frequency(cutoff_note);
    let hz = if cutoff_envelope_enabled(opts) {
        let cutoff_min_hz = note_frequency(float_opt(opts, "cutoff_min", 30.0).clamp(0.001, 130.5));
        cutoff_min_hz + cutoff_envelope_level(kind, opts, elapsed) * cutoff_hz
    } else {
        cutoff_hz
    };
    hz.clamp(20.0, sample_rate as f64 * 0.45)
}

fn cutoff_envelope_level(kind: SynthKind, opts: &OptMap, elapsed: f64) -> f64 {
    let (default_attack, default_decay, default_sustain, default_release) =
        default_synth_envelope(kind);
    let attack = float_opt(opts, "attack", default_attack).max(0.0);
    let decay = float_opt(opts, "decay", default_decay).max(0.0);
    let sustain = float_opt(opts, "sustain", default_sustain).max(0.0);
    let release = float_opt(opts, "release", default_release).max(0.0);
    let sustain_level = float_opt(
        opts,
        "cutoff_sustain_level",
        float_opt(opts, "sustain_level", 1.0),
    )
    .max(0.0);
    let attack_level = float_opt(opts, "cutoff_attack_level", 1.0).max(0.0);
    let decay_level_raw = float_opt(opts, "cutoff_decay_level", -1.0);
    let decay_level = if decay_level_raw < 0.0 {
        sustain_level
    } else {
        decay_level_raw.max(0.0)
    };
    let cutoff_attack = inherit_negative(float_opt(opts, "cutoff_attack", -1.0), attack);
    let cutoff_decay = inherit_negative(float_opt(opts, "cutoff_decay", -1.0), decay);
    let cutoff_sustain = inherit_negative(float_opt(opts, "cutoff_sustain", -1.0), sustain);
    let cutoff_release = inherit_negative(float_opt(opts, "cutoff_release", -1.0), release);
    adsr_level(
        elapsed,
        cutoff_attack,
        cutoff_decay,
        cutoff_sustain,
        cutoff_release,
        attack_level,
        decay_level,
        sustain_level,
        float_opt(opts, "cutoff_env_curve", float_opt(opts, "env_curve", 1.0)).round() as i32,
    )
}

fn inherit_negative(value: f64, inherited: f64) -> f64 {
    if value < 0.0 {
        inherited.max(0.0)
    } else {
        value.max(0.0)
    }
}

fn default_synth_cutoff(kind: SynthKind) -> f64 {
    match kind {
        SynthKind::Saw | SynthKind::Pulse | SynthKind::Tri | SynthKind::Fm | SynthKind::Layered => {
            100.0
        }
        SynthKind::Noise
        | SynthKind::PinkNoise
        | SynthKind::BrownNoise
        | SynthKind::GreyNoise
        | SynthKind::ClipNoise => 110.0,
        _ => 131.0,
    }
}

fn default_synth_res(_kind: SynthKind) -> f64 {
    0.0
}

fn synth_amp_fudge(_kind: SynthKind, opts: &OptMap) -> f64 {
    float_opt(opts, "amp_fudge", 1.0).max(0.0)
}

fn synth_normalise_enabled(kind: SynthKind, opts: &OptMap) -> bool {
    bool_opt(
        opts,
        "normalise",
        bool_opt(
            opts,
            "normalize",
            float_opt(
                opts,
                "norm",
                if default_synth_normalise(kind) {
                    1.0
                } else {
                    0.0
                },
            ) >= 0.5,
        ),
    )
}

fn default_synth_normalise(_kind: SynthKind) -> bool {
    false
}

fn automation(
    initial: Option<f64>,
    name: &str,
    controls: &[ControlPayload],
    opts: &OptMap,
    event_time: f64,
) -> Box<dyn Fn(f64) -> Option<f64> + Send + Sync> {
    let slide_default = float_opt(opts, &format!("{name}_slide"), 0.0);
    let mut points = Vec::new();
    for control in controls {
        let Some(target_value) = control.opts.get(name) else {
            continue;
        };
        let target = if name == "note" {
            note(target_value).ok().flatten()
        } else {
            value_as_f64(target_value)
        };
        let Some(target) = target else {
            continue;
        };
        let slide = control
            .opts
            .get(&format!("{name}_slide"))
            .and_then(value_as_f64)
            .unwrap_or(slide_default);
        points.push(((control.time_seconds - event_time).max(0.0), slide, target));
    }
    if points.is_empty() {
        return Box::new(move |_| initial);
    }
    Box::new(move |elapsed| {
        let mut value = initial.unwrap_or(0.0);
        for (control_time, slide, target) in &points {
            if elapsed < *control_time {
                break;
            }
            let start_value = value;
            if *slide <= 0.0 || elapsed >= control_time + slide {
                value = *target;
            } else {
                let t = (elapsed - control_time) / slide;
                value = start_value + (*target - start_value) * t;
                break;
            }
        }
        Some(value)
    })
}

#[derive(Clone, Debug)]
struct SampleSource {
    left: Arc<Vec<f64>>,
    right: Arc<Vec<f64>>,
    duration: f64,
    stereo: bool,
}

impl SampleSource {
    fn len(&self) -> usize {
        self.left.len().min(self.right.len())
    }
}

type SampleCache = HashMap<(String, u32), Arc<SampleSource>>;

fn sample_cache() -> &'static Mutex<SampleCache> {
    static SAMPLE_CACHE: OnceLock<Mutex<SampleCache>> = OnceLock::new();
    SAMPLE_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn sample_source(value: &SynthValue, sample_rate: u32) -> PyResult<SampleSource> {
    let sample_name = match value {
        SynthValue::List(values) => values.first(),
        other => Some(other),
    }
    .ok_or_else(|| PyValueError::new_err("sample event does not specify a sample name."))?;
    if let SynthValue::String(path) = sample_name {
        if fs::metadata(path).is_ok() {
            return cached_sample_file(path, sample_rate);
        }
    }
    let name = match sample_name {
        SynthValue::String(name) => name.trim_start_matches(':').to_owned(),
        _ => {
            return Err(PyValueError::new_err(
                "sample event value must be a sample name or file path.",
            ))
        }
    };
    if let Some(path) = packaged_sample_path(&name) {
        return cached_sample_file(path.to_string_lossy().as_ref(), sample_rate);
    }
    Err(PyValueError::new_err(format!(
        "Sample {name:?} was not found. Provide an existing file path or install the packaged Sonic Pi sample assets."
    )))
}

fn packaged_sample_path(name: &str) -> Option<PathBuf> {
    let trimmed = name.trim_start_matches(':');
    if trimmed.is_empty() {
        return None;
    }
    let stem = Path::new(trimmed)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or(trimmed);
    let file_names = [
        format!("{stem}.flac"),
        format!("{stem}.wav"),
        format!("{stem}.aif"),
        format!("{stem}.aiff"),
    ];
    for root in packaged_sample_roots() {
        for file_name in &file_names {
            let candidate = root.join(file_name);
            if fs::metadata(&candidate).is_ok() {
                return Some(candidate);
            }
        }
    }
    None
}

fn packaged_sample_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Ok(root) = std::env::var("GUMMYSNAKE_SAMPLE_DIR") {
        roots.push(PathBuf::from(root));
    }
    if let Ok(current_dir) = std::env::current_dir() {
        for ancestor in current_dir.ancestors() {
            roots.push(ancestor.join("assets/samples/sonic_pi"));
            roots.push(ancestor.join("gummy_snake/assets/samples/sonic_pi"));
        }
    }
    if let Some(manifest_dir) = option_env!("CARGO_MANIFEST_DIR") {
        let manifest = PathBuf::from(manifest_dir);
        roots.push(manifest.join("../../assets/samples/sonic_pi"));
    }
    roots
}

fn cached_sample_file(path: &str, sample_rate: u32) -> PyResult<SampleSource> {
    let cache_key = (sample_cache_key(path), sample_rate);
    if let Some(source) = sample_cache()
        .lock()
        .map_err(|_| PyValueError::new_err("synth sample cache lock was poisoned."))?
        .get(&cache_key)
        .cloned()
    {
        return Ok((*source).clone());
    }

    let source = Arc::new(load_sample_file(path, sample_rate)?);
    let mut cache = sample_cache()
        .lock()
        .map_err(|_| PyValueError::new_err("synth sample cache lock was poisoned."))?;
    Ok((**cache
        .entry(cache_key)
        .or_insert_with(|| Arc::clone(&source)))
    .clone())
}

fn sample_cache_key(path: &str) -> String {
    fs::canonicalize(path)
        .unwrap_or_else(|_| PathBuf::from(path))
        .to_string_lossy()
        .into_owned()
}

fn load_sample_file(path: &str, sample_rate: u32) -> PyResult<SampleSource> {
    let extension = Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if extension == "flac" {
        return load_flac_sample(path, sample_rate);
    }
    load_wav_sample(path, sample_rate)
}

fn load_wav_sample(path: &str, sample_rate: u32) -> PyResult<SampleSource> {
    let bytes = fs::read(path)
        .map_err(|err| PyValueError::new_err(format!("Could not load WAV sample {path}: {err}")))?;
    let wav = decode_wav_stereo(&bytes)?;
    let left = if wav.sample_rate == sample_rate {
        wav.left
    } else {
        resample(&wav.left, wav.sample_rate, sample_rate)
    };
    let right = if wav.sample_rate == sample_rate {
        wav.right
    } else {
        resample(&wav.right, wav.sample_rate, sample_rate)
    };
    let duration = left.len().min(right.len()) as f64 / sample_rate as f64;
    Ok(SampleSource {
        left: Arc::new(left),
        right: Arc::new(right),
        duration,
        stereo: wav.stereo,
    })
}

fn load_flac_sample(path: &str, sample_rate: u32) -> PyResult<SampleSource> {
    let mut reader = claxon::FlacReader::open(path).map_err(|err| {
        PyValueError::new_err(format!("Could not load FLAC sample {path}: {err}"))
    })?;
    let streaminfo = reader.streaminfo();
    let source_rate = streaminfo.sample_rate;
    let channels = streaminfo.channels as usize;
    let bits_per_sample = streaminfo.bits_per_sample as i32;
    if !matches!(channels, 1 | 2) || bits_per_sample <= 0 {
        return Err(PyValueError::new_err(format!(
            "Unsupported FLAC sample format for {path}; expected mono or stereo PCM data."
        )));
    }
    let denom = 2_f64.powi(bits_per_sample - 1);
    let mut left = Vec::new();
    let mut right = Vec::new();
    let mut channel = 0usize;
    let mut pending_left = 0.0;
    for sample in reader.samples() {
        let sample = sample.map_err(|err| {
            PyValueError::new_err(format!("Could not decode FLAC sample {path}: {err}"))
        })? as f64
            / denom;
        if channels == 1 {
            left.push(sample);
            right.push(sample);
            continue;
        }
        if channel == 0 {
            pending_left = sample;
            channel = 1;
        } else {
            left.push(pending_left);
            right.push(sample);
            channel = 0;
        }
    }
    if channel != 0 {
        return Err(PyValueError::new_err(format!(
            "Malformed FLAC sample {path}; incomplete stereo frame."
        )));
    }
    let left = if source_rate == sample_rate {
        left
    } else {
        resample(&left, source_rate, sample_rate)
    };
    let right = if source_rate == sample_rate {
        right
    } else {
        resample(&right, source_rate, sample_rate)
    };
    let duration = left.len().min(right.len()) as f64 / sample_rate as f64;
    Ok(SampleSource {
        left: Arc::new(left),
        right: Arc::new(right),
        duration,
        stereo: channels == 2,
    })
}

struct DecodedWav {
    left: Vec<f64>,
    right: Vec<f64>,
    sample_rate: u32,
    stereo: bool,
}

fn decode_wav_stereo(bytes: &[u8]) -> PyResult<DecodedWav> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err(PyValueError::new_err(
            "Rust synth sample rendering currently supports PCM WAV bytes.",
        ));
    }
    let mut offset = 12usize;
    let mut channels = None;
    let mut sample_rate = None;
    let mut bits_per_sample = None;
    let mut data = None;
    while offset.checked_add(8).is_some_and(|end| end <= bytes.len()) {
        let chunk_id = &bytes[offset..offset + 4];
        let chunk_len = u32::from_le_bytes([
            bytes[offset + 4],
            bytes[offset + 5],
            bytes[offset + 6],
            bytes[offset + 7],
        ]) as usize;
        offset += 8;
        if offset
            .checked_add(chunk_len)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(PyValueError::new_err("Malformed WAV chunk length."));
        }
        let chunk = &bytes[offset..offset + chunk_len];
        match chunk_id {
            b"fmt " => {
                if chunk.len() < 16 {
                    return Err(PyValueError::new_err("Malformed WAV fmt chunk."));
                }
                channels = Some(u16::from_le_bytes([chunk[2], chunk[3]]));
                sample_rate = Some(u32::from_le_bytes([chunk[4], chunk[5], chunk[6], chunk[7]]));
                bits_per_sample = Some(u16::from_le_bytes([chunk[14], chunk[15]]));
            }
            b"data" => data = Some(chunk.to_vec()),
            _ => {}
        }
        offset += chunk_len + (chunk_len % 2);
    }
    let channels = channels.ok_or_else(|| PyValueError::new_err("WAV missing fmt chunk."))?;
    let sample_rate =
        sample_rate.ok_or_else(|| PyValueError::new_err("WAV missing sample rate."))?;
    let bits_per_sample =
        bits_per_sample.ok_or_else(|| PyValueError::new_err("WAV missing depth."))?;
    let data = data.ok_or_else(|| PyValueError::new_err("WAV missing data chunk."))?;
    let width = usize::from(bits_per_sample.div_ceil(8));
    if !matches!(width, 1 | 2 | 4) || !matches!(channels, 1 | 2) {
        return Err(PyValueError::new_err(
            "Unsupported PCM WAV format; expected mono or stereo 8/16/32-bit PCM.",
        ));
    }
    let step = width * usize::from(channels);
    let mut left = Vec::with_capacity(data.len() / step);
    let mut right = Vec::with_capacity(data.len() / step);
    for frame in data.chunks_exact(step) {
        let left_sample = decode_pcm_sample(&frame[0..width]);
        left.push(left_sample);
        if channels == 1 {
            right.push(left_sample);
        } else {
            right.push(decode_pcm_sample(&frame[width..width * 2]));
        }
    }
    Ok(DecodedWav {
        left,
        right,
        sample_rate,
        stereo: channels == 2,
    })
}

fn decode_pcm_sample(raw: &[u8]) -> f64 {
    match raw.len() {
        1 => (f64::from(raw[0]) - 128.0) / 128.0,
        2 => f64::from(i16::from_le_bytes([raw[0], raw[1]])) / 32768.0,
        4 => f64::from(i32::from_le_bytes([raw[0], raw[1], raw[2], raw[3]])) / 2147483648.0,
        _ => 0.0,
    }
}

fn resample(samples: &[f64], source_rate: u32, target_rate: u32) -> Vec<f64> {
    if samples.is_empty() || source_rate == target_rate {
        return samples.to_vec();
    }
    let target_count = samples.len() * target_rate as usize / source_rate as usize;
    let mut output = Vec::with_capacity(target_count);
    for index in 0..target_count {
        let source_pos = index as f64 * source_rate as f64 / target_rate as f64;
        let low = source_pos.floor() as usize;
        let high = (low + 1).min(samples.len() - 1);
        let frac = source_pos - low as f64;
        output.push(samples[low] * (1.0 - frac) + samples[high] * frac);
    }
    output
}

fn apply_fx(
    name: &str,
    left: Vec<f64>,
    right: Vec<f64>,
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let key = name.trim_start_matches(':').to_ascii_lowercase();
    let primitive_key = key.strip_prefix('_').unwrap_or(key.as_str());
    let input_left = left;
    let input_right = right;
    let pre_amp = float_opt(opts, "pre_amp", 1.0).max(0.0);
    let fx_in_left = scale_samples(&input_left, pre_amp);
    let fx_in_right = scale_samples(&input_right, pre_amp);
    let pre_mix = float_opt(opts, "pre_mix", 1.0).clamp(0.0, 1.0);
    let dry_left = scale_samples(&fx_in_left, pre_mix);
    let dry_right = scale_samples(&fx_in_right, pre_mix);
    let bypass_left = scale_samples(&fx_in_left, 1.0 - pre_mix);
    let bypass_right = scale_samples(&fx_in_right, 1.0 - pre_mix);
    let wet = match primitive_key {
        "chain" => fx_chain(&dry_left, &dry_right, opts, sample_rate, start_time_seconds),
        "bitcrusher" => fx_bitcrusher(&dry_left, &dry_right, opts, sample_rate),
        "krush" => fx_krush(&dry_left, &dry_right, opts, sample_rate),
        "reverb" => fx_reverb(&dry_left, &dry_right, opts, sample_rate),
        "gverb" => fx_gverb(&dry_left, &dry_right, opts, sample_rate),
        "level" => (dry_left.clone(), dry_right.clone()),
        "echo" => fx_echo(&dry_left, &dry_right, opts, sample_rate),
        "slicer" => fx_slicer(&dry_left, &dry_right, opts, sample_rate, start_time_seconds),
        "panslicer" | "pan_slicer" => {
            fx_panslicer(&dry_left, &dry_right, opts, sample_rate, start_time_seconds)
        }
        "wobble" => fx_wobble(&dry_left, &dry_right, opts, sample_rate, start_time_seconds),
        "ixi_techno" => fx_ixi_techno(&dry_left, &dry_right, opts, sample_rate, start_time_seconds),
        "compressor" => fx_compressor(&dry_left, &dry_right, opts, sample_rate),
        "whammy" => fx_whammy(&dry_left, &dry_right, opts),
        "rlpf" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::Low,
            true,
            false,
        ),
        "nrlpf" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::Low,
            true,
            true,
        ),
        "rhpf" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::High,
            true,
            false,
        ),
        "nrhpf" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::High,
            true,
            true,
        ),
        "hpf" | "highpass" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::High,
            false,
            false,
        ),
        "nhpf" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::High,
            false,
            true,
        ),
        "lpf" | "lowpass" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::Low,
            false,
            false,
        ),
        "nlpf" => fx_filter_pair(
            &dry_left,
            &dry_right,
            opts,
            sample_rate,
            FilterKind::Low,
            false,
            true,
        ),
        "normaliser" | "normalizer" => fx_normaliser(&dry_left, &dry_right, opts),
        "distortion" => fx_distortion(&dry_left, &dry_right, opts),
        "pan" => fx_pan(&dry_left, &dry_right, opts),
        "bpf" => fx_bandpass_pair(&dry_left, &dry_right, opts, sample_rate, false, false),
        "nbpf" => fx_bandpass_pair(&dry_left, &dry_right, opts, sample_rate, false, true),
        "rbpf" => fx_bandpass_pair(&dry_left, &dry_right, opts, sample_rate, true, false),
        "nrbpf" => fx_bandpass_pair(&dry_left, &dry_right, opts, sample_rate, true, true),
        "band_eq" => fx_band_eq(&dry_left, &dry_right, opts, sample_rate),
        "tanh" => fx_tanh(&dry_left, &dry_right, opts),
        "pitch_shift" => fx_pitch_shift(&dry_left, &dry_right, opts),
        "ring_mod" => fx_ring_mod(&dry_left, &dry_right, opts, sample_rate, start_time_seconds),
        "octaver" => fx_octaver(&dry_left, &dry_right, opts, sample_rate),
        "vowel" => fx_vowel(&dry_left, &dry_right, opts, sample_rate),
        "flanger" => fx_flanger(&dry_left, &dry_right, opts, sample_rate, start_time_seconds),
        _ => return (input_left, input_right),
    };
    let wet = add_signal_pair(&wet.0, &wet.1, &bypass_left, &bypass_right);
    let mix = float_opt(opts, "mix", default_fx_mix(primitive_key)).clamp(0.0, 1.0);
    let amp = float_opt(opts, "amp", 1.0).max(0.0);
    blend_fx(&fx_in_left, &fx_in_right, &wet.0, &wet.1, mix, amp)
}

#[derive(Clone, Copy)]
enum FilterKind {
    Low,
    High,
}

fn fx_chain(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let Some(SynthValue::List(ops)) = opts.get("ops") else {
        return (left.to_vec(), right.to_vec());
    };
    let mut current_left = left.to_vec();
    let mut current_right = right.to_vec();
    for op_value in ops {
        let op_opts = fx_op_map(op_value);
        let op_name = string_opt(&op_opts, "op", "level");
        let merged = merge_chain_op_opts(opts, &op_opts);
        let next = fx_chain_op(
            &op_name,
            &current_left,
            &current_right,
            &merged,
            sample_rate,
            start_time_seconds,
        );
        current_left = next.0;
        current_right = next.1;
    }
    (current_left, current_right)
}

fn fx_op_map(value: &SynthValue) -> OptMap {
    match value {
        SynthValue::Dict(map) => map.clone(),
        SynthValue::List(values) => {
            let mut map = OptMap::new();
            if let Some(SynthValue::String(name)) = values.first() {
                map.insert("op".to_owned(), SynthValue::String(name.clone()));
            }
            let mut index = 1;
            while index + 1 < values.len() {
                if let SynthValue::String(key) = &values[index] {
                    map.insert(key.clone(), values[index + 1].clone());
                }
                index += 2;
            }
            map
        }
        _ => OptMap::new(),
    }
}

fn merge_chain_op_opts(chain_opts: &OptMap, op_opts: &OptMap) -> OptMap {
    let mut merged = op_opts.clone();
    for (key, value) in chain_opts {
        if key == "ops" || is_fx_wrapper_opt(key) {
            continue;
        }
        merged.insert(key.clone(), value.clone());
    }
    merged
}

fn is_fx_wrapper_opt(key: &str) -> bool {
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

fn fx_chain_op(
    name: &str,
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    match name {
        "level" => (left.to_vec(), right.to_vec()),
        "decimator" => fx_bitcrusher(left, right, opts, sample_rate),
        "krush_shape" => fx_krush_shape(left, right, opts),
        "distortion_shape" => fx_distortion(left, right, opts),
        "tanh_shape" => fx_tanh(left, right, opts),
        "filter" => {
            let kind = match string_opt(opts, "kind", "low").as_str() {
                "high" | "hpf" | "highpass" => FilterKind::High,
                _ => FilterKind::Low,
            };
            fx_filter_pair(
                left,
                right,
                opts,
                sample_rate,
                kind,
                bool_opt(opts, "resonant", false),
                bool_opt(opts, "normalise", false) || bool_opt(opts, "normalize", false),
            )
        }
        "bandpass" => fx_bandpass_pair(
            left,
            right,
            opts,
            sample_rate,
            bool_opt(opts, "resonant", false),
            bool_opt(opts, "normalise", false) || bool_opt(opts, "normalize", false),
        ),
        "band_eq" => fx_band_eq(left, right, opts, sample_rate),
        "normalise" | "normalize" => fx_normaliser(left, right, opts),
        "pan" => fx_pan(left, right, opts),
        "reverb" => fx_reverb(left, right, opts, sample_rate),
        "gverb" => fx_gverb(left, right, opts, sample_rate),
        "echo" => fx_echo(left, right, opts, sample_rate),
        "slicer" => fx_slicer(left, right, opts, sample_rate, start_time_seconds),
        "panslicer" => fx_panslicer(left, right, opts, sample_rate, start_time_seconds),
        "wobble" => fx_wobble(left, right, opts, sample_rate, start_time_seconds),
        "ixi_techno" => fx_ixi_techno(left, right, opts, sample_rate, start_time_seconds),
        "compressor" => fx_compressor(left, right, opts, sample_rate),
        "pitch_shift" => fx_pitch_shift(left, right, opts),
        "whammy" => fx_whammy(left, right, opts),
        "ring_mod" => fx_ring_mod(left, right, opts, sample_rate, start_time_seconds),
        "octaver" => fx_octaver(left, right, opts, sample_rate),
        "vowel" => fx_vowel(left, right, opts, sample_rate),
        "flanger" => fx_flanger(left, right, opts, sample_rate, start_time_seconds),
        _ => (left.to_vec(), right.to_vec()),
    }
}

fn default_fx_mix(name: &str) -> f64 {
    match name {
        "reverb" | "gverb" => 0.4,
        _ => 1.0,
    }
}

fn scale_samples(samples: &[f64], amount: f64) -> Vec<f64> {
    samples.iter().map(|sample| sample * amount).collect()
}

fn add_signal_pair(
    left_a: &[f64],
    right_a: &[f64],
    left_b: &[f64],
    right_b: &[f64],
) -> (Vec<f64>, Vec<f64>) {
    let len = left_a
        .len()
        .max(right_a.len())
        .max(left_b.len())
        .max(right_b.len());
    let mut out_left = Vec::with_capacity(len);
    let mut out_right = Vec::with_capacity(len);
    for index in 0..len {
        out_left.push(
            left_a.get(index).copied().unwrap_or(0.0) + left_b.get(index).copied().unwrap_or(0.0),
        );
        out_right.push(
            right_a.get(index).copied().unwrap_or(0.0) + right_b.get(index).copied().unwrap_or(0.0),
        );
    }
    (out_left, out_right)
}

fn blend_fx(
    dry_left: &[f64],
    dry_right: &[f64],
    wet_left: &[f64],
    wet_right: &[f64],
    mix: f64,
    amp: f64,
) -> (Vec<f64>, Vec<f64>) {
    let len = dry_left
        .len()
        .max(dry_right.len())
        .max(wet_left.len())
        .max(wet_right.len());
    let mut out_left = Vec::with_capacity(len);
    let mut out_right = Vec::with_capacity(len);
    for index in 0..len {
        let dry_l = *dry_left.get(index).unwrap_or(&0.0);
        let dry_r = *dry_right.get(index).unwrap_or(&0.0);
        let wet_l = *wet_left.get(index).unwrap_or(&0.0);
        let wet_r = *wet_right.get(index).unwrap_or(&0.0);
        let angle = mix.clamp(0.0, 1.0) * PI / 2.0;
        let dry_gain = angle.cos();
        let wet_gain = angle.sin();
        out_left.push((dry_l * dry_gain + wet_l * wet_gain) * amp);
        out_right.push((dry_r * dry_gain + wet_r * wet_gain) * amp);
    }
    (out_left, out_right)
}

fn fx_bitcrusher(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    render_sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let target_rate = float_opt(opts, "sample_rate", 10_000.0)
        .max(1.0)
        .min(render_sample_rate as f64);
    let step = (render_sample_rate as f64 / target_rate).round().max(1.0) as usize;
    let bits = float_opt(opts, "bits", 8.0).round().clamp(1.0, 16.0);
    let levels = 2.0_f64.powf(bits).max(2.0);
    let crush = |samples: &[f64]| -> Vec<f64> {
        let mut output = Vec::with_capacity(samples.len());
        let mut held = 0.0;
        for (index, sample) in samples.iter().enumerate() {
            if index % step == 0 {
                held = ((*sample).clamp(-1.0, 1.0) * (levels / 2.0)).round() / (levels / 2.0);
            }
            output.push(held);
        }
        output
    };
    let mut out_left = crush(left);
    let mut out_right = crush(right);
    let cutoff = float_opt(opts, "cutoff", 0.0);
    if cutoff > 0.0 {
        let cutoff_hz = note_frequency(cutoff).max(20.0);
        out_left = lowpass(&out_left, cutoff_hz, render_sample_rate);
        out_right = lowpass(&out_right, cutoff_hz, render_sample_rate);
    }
    (out_left, out_right)
}

fn fx_krush(left: &[f64], right: &[f64], opts: &OptMap, sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
    let (mut out_left, mut out_right) = fx_krush_shape(left, right, opts);
    let cutoff = note_frequency(float_opt(opts, "cutoff", 100.0)).max(20.0);
    out_left = lowpass(&out_left, cutoff, sample_rate);
    out_right = lowpass(&out_right, cutoff, sample_rate);
    let res = float_opt(opts, "res", 0.0).clamp(0.0, 0.99);
    if res > 0.0 {
        out_left = resonant_emphasis(left, &out_left, res);
        out_right = resonant_emphasis(right, &out_right, res);
    }
    (out_left, out_right)
}

fn fx_krush_shape(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let gain = float_opt(opts, "gain", 5.0).max(0.001);
    let distort = |sample: f64| {
        let abs_sample = sample.abs();
        let squared = abs_sample * abs_sample;
        (squared + gain * abs_sample) / (squared + abs_sample * (gain - 1.0) + 1.0)
    };
    (
        left.iter().map(|sample| distort(*sample)).collect(),
        right.iter().map(|sample| distort(*sample)).collect(),
    )
}

fn fx_reverb(left: &[f64], right: &[f64], opts: &OptMap, sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
    let room = float_opt(opts, "room", 0.6).clamp(0.0, 1.0);
    let damp = float_opt(opts, "damp", 0.5).clamp(0.0, 1.0);
    let tail_seconds = float_opt(opts, "tail", 0.7 + room * 2.4).max(0.05);
    let input_len = left.len().max(right.len());
    if input_len == 0 {
        return (Vec::new(), Vec::new());
    }
    let output_len = input_len + (tail_seconds * sample_rate as f64).ceil() as usize;
    let feedback = 0.70 + room * 0.24;
    let damp_amount = damp * 0.45;
    let damp1 = damp_amount;
    let damp2 = 1.0 - damp_amount;
    let wet_gain = 0.18 + room * 0.08;
    let input_gain = 0.025;

    let comb_left = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617];
    let comb_right = [1139, 1211, 1300, 1379, 1445, 1514, 1580, 1640];
    let allpass_left = [556, 441, 341, 225];
    let allpass_right = [579, 464, 364, 248];
    let mut combs_left: Vec<CombFilter> = comb_left
        .iter()
        .map(|delay| CombFilter::new(scaled_reverb_delay(*delay, sample_rate)))
        .collect();
    let mut combs_right: Vec<CombFilter> = comb_right
        .iter()
        .map(|delay| CombFilter::new(scaled_reverb_delay(*delay, sample_rate)))
        .collect();
    let mut allpasses_left: Vec<AllpassFilter> = allpass_left
        .iter()
        .map(|delay| AllpassFilter::new(scaled_reverb_delay(*delay, sample_rate), 0.5))
        .collect();
    let mut allpasses_right: Vec<AllpassFilter> = allpass_right
        .iter()
        .map(|delay| AllpassFilter::new(scaled_reverb_delay(*delay, sample_rate), 0.5))
        .collect();

    let mut out_left = Vec::with_capacity(output_len);
    let mut out_right = Vec::with_capacity(output_len);
    for index in 0..output_len {
        let input_left = left.get(index).copied().unwrap_or(0.0);
        let input_right = right.get(index).copied().unwrap_or(0.0);
        let mono_input = (input_left + input_right) * 0.5 * input_gain;
        let stereo_push = (input_left - input_right) * 0.25 * input_gain;
        let comb_input_left = mono_input + stereo_push;
        let comb_input_right = mono_input - stereo_push;

        let mut wet_left = 0.0;
        for comb in &mut combs_left {
            wet_left += comb.process(comb_input_left, feedback, damp1, damp2);
        }
        let mut wet_right = 0.0;
        for comb in &mut combs_right {
            wet_right += comb.process(comb_input_right, feedback, damp1, damp2);
        }
        wet_left /= combs_left.len() as f64;
        wet_right /= combs_right.len() as f64;
        for allpass in &mut allpasses_left {
            wet_left = allpass.process(wet_left);
        }
        for allpass in &mut allpasses_right {
            wet_right = allpass.process(wet_right);
        }
        out_left.push(wet_left * wet_gain);
        out_right.push(wet_right * wet_gain);
    }
    (out_left, out_right)
}

struct CombFilter {
    buffer: Vec<f64>,
    index: usize,
    filter_store: f64,
}

impl CombFilter {
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

struct AllpassFilter {
    buffer: Vec<f64>,
    index: usize,
    feedback: f64,
}

impl AllpassFilter {
    fn new(size: usize, feedback: f64) -> Self {
        Self {
            buffer: vec![0.0; size.max(1)],
            index: 0,
            feedback,
        }
    }

    fn process(&mut self, input: f64) -> f64 {
        let buffered = self.buffer[self.index];
        let output = buffered - input;
        self.buffer[self.index] = input + buffered * self.feedback;
        self.index = (self.index + 1) % self.buffer.len();
        output
    }
}

fn scaled_reverb_delay(delay_at_44k: usize, sample_rate: u32) -> usize {
    ((delay_at_44k as f64 * sample_rate as f64 / 44_100.0).round() as usize).max(1)
}

fn fx_echo(left: &[f64], right: &[f64], opts: &OptMap, sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 0.25).max(0.001);
    let decay = float_opt(opts, "decay", 2.0).max(0.0);
    let delay_samples = (phase * sample_rate as f64) as usize;
    let repeats = (decay / phase).max(1.0) as usize;
    let mut out_left = left.to_vec();
    let mut out_right = right.to_vec();
    out_left.resize(out_left.len() + delay_samples * repeats, 0.0);
    out_right.resize(out_right.len() + delay_samples * repeats, 0.0);
    for repeat in 1..=repeats {
        let elapsed = repeat as f64 * phase;
        let gain = if decay <= 0.0 {
            0.0
        } else {
            (-3.0 * elapsed / decay).exp()
        };
        let offset = delay_samples * repeat;
        for (index, sample) in left.iter().enumerate() {
            out_left[index + offset] += sample * gain;
        }
        for (index, sample) in right.iter().enumerate() {
            out_right[index + offset] += sample * gain;
        }
    }
    (out_left, out_right)
}

fn fx_gverb(left: &[f64], right: &[f64], opts: &OptMap, sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
    let room = (float_opt(opts, "room", 10.0) / 10.0).clamp(0.0, 2.0);
    let release = float_opt(opts, "release", 3.0).max(0.05);
    let spread = float_opt(opts, "spread", 0.5).clamp(0.0, 1.0);
    let dry = float_opt(opts, "dry", 1.0).max(0.0);
    let ref_level = float_opt(opts, "ref_level", 0.7).max(0.0);
    let tail_level = float_opt(opts, "tail_level", 0.5).max(0.0);
    let delays = [0.019, 0.043, 0.083, 0.149, 0.211, 0.293];
    let extra = (release * sample_rate as f64) as usize;
    let mut out_left = scale_samples(left, dry);
    let mut out_right = scale_samples(right, dry);
    out_left.resize(out_left.len() + extra, 0.0);
    out_right.resize(out_right.len() + extra, 0.0);
    for (delay_index, delay) in delays.iter().enumerate() {
        let offset = ((*delay * (1.0 + room)) * sample_rate as f64) as usize;
        let gain = (ref_level * 0.24 + tail_level * 0.2) * 0.68_f64.powi(delay_index as i32);
        for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
            let target = index + offset;
            if target >= out_left.len() {
                break;
            }
            let cross_l = left_sample * (1.0 - spread) + right_sample * spread;
            let cross_r = right_sample * (1.0 - spread) + left_sample * spread;
            out_left[target] += cross_l * gain;
            out_right[target] += cross_r * gain;
        }
    }
    let damp = float_opt(opts, "damp", 0.5).clamp(0.0, 1.0);
    if damp > 0.0 {
        let cutoff = 12_000.0 * (1.0 - damp) + 1_200.0 * damp;
        out_left = lowpass(&out_left, cutoff, sample_rate);
        out_right = lowpass(&out_right, cutoff, sample_rate);
    }
    (out_left, out_right)
}

fn fx_panslicer(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 0.25).max(0.001);
    let wave = float_opt(opts, "wave", 1.0) as i32;
    let pan_min = float_opt(opts, "pan_min", -1.0).clamp(-1.0, 1.0);
    let pan_max = float_opt(opts, "pan_max", 1.0).clamp(-1.0, 1.0);
    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    let mut previous_pan = 0.0;
    for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        let amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
        let target_pan = pan_min + (pan_max - pan_min) * amount;
        previous_pan = smooth_modulated_value(previous_pan, target_pan, opts, sample_rate);
        let (balanced_left, balanced_right) =
            balance2_sample(*left_sample, *right_sample, previous_pan);
        out_left.push(balanced_left);
        out_right.push(balanced_right);
    }
    (out_left, out_right)
}

fn fx_ixi_techno(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let mut local = opts.clone();
    local
        .entry("wave".to_owned())
        .or_insert(SynthValue::Float(3.0));
    local
        .entry("phase".to_owned())
        .or_insert(SynthValue::Float(4.0));
    local
        .entry("cutoff_min".to_owned())
        .or_insert(SynthValue::Float(60.0));
    local
        .entry("cutoff_max".to_owned())
        .or_insert(SynthValue::Float(120.0));
    fx_wobble(left, right, &local, sample_rate, start_time_seconds)
}

fn fx_compressor(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let threshold = float_opt(opts, "threshold", 0.2).max(0.0001);
    let slope_above = float_opt(opts, "slope_above", 0.5);
    let slope_below = float_opt(opts, "slope_below", 1.0);
    let clamp_time = float_opt(opts, "clamp_time", 0.01).max(0.0);
    let relax_time = float_opt(opts, "relax_time", 0.01).max(0.0);
    let attack_alpha = smoothing_alpha(clamp_time, sample_rate);
    let release_alpha = smoothing_alpha(relax_time, sample_rate);
    let mut gain = 1.0;
    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    for (left_sample, right_sample) in left.iter().zip(right.iter()) {
        let level = left_sample.abs().max(right_sample.abs()).max(1e-9);
        let target_level = if level > threshold {
            threshold + (level - threshold) * slope_above
        } else {
            threshold * (level / threshold).powf(slope_below)
        };
        let target_gain = (target_level / level).clamp(0.0, 16.0);
        let alpha = if target_gain < gain {
            attack_alpha
        } else {
            release_alpha
        };
        gain += (target_gain - gain) * alpha;
        out_left.push(left_sample * gain);
        out_right.push(right_sample * gain);
    }
    (out_left, out_right)
}

fn fx_whammy(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let transpose = float_opt(opts, "transpose", 12.0);
    let ratio = 2.0_f64.powf(transpose / 12.0);
    (
        pitch_shift_to_len(left, ratio),
        pitch_shift_to_len(right, ratio),
    )
}

fn fx_filter_pair(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    kind: FilterKind,
    resonant: bool,
    normalised: bool,
) -> (Vec<f64>, Vec<f64>) {
    let cutoff = note_frequency(float_opt(opts, "cutoff", 100.0)).max(20.0);
    let res = if resonant {
        float_opt(opts, "res", 0.5).clamp(0.0, 0.99)
    } else {
        0.0
    };
    let mut out_left = filter_samples(left, cutoff, sample_rate, kind, res);
    let mut out_right = filter_samples(right, cutoff, sample_rate, kind, res);
    if normalised {
        let normalised_pair = normalise_pair(&out_left, &out_right, 1.0);
        out_left = normalised_pair.0;
        out_right = normalised_pair.1;
    }
    (out_left, out_right)
}

fn fx_normaliser(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    normalise_pair(left, right, float_opt(opts, "level", 1.0).max(0.0))
}

fn fx_distortion(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let amount = float_opt(opts, "distort", float_opt(opts, "amount", 0.5)).clamp(0.0, 0.999);
    let k = (2.0 * amount) / (1.0 - amount).max(0.001);
    let distort = |sample: f64| sample * (1.0 + k) / (1.0 + k * sample.abs());
    (
        left.iter().map(|sample| distort(*sample)).collect(),
        right.iter().map(|sample| distort(*sample)).collect(),
    )
}

fn fx_pan(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let pan = float_opt(opts, "pan", 0.0).clamp(-1.0, 1.0);
    balance2_pair(left, right, pan)
}

fn fx_bandpass_pair(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    resonant: bool,
    normalised: bool,
) -> (Vec<f64>, Vec<f64>) {
    let centre = note_frequency(float_opt(opts, "centre", 100.0)).max(20.0);
    let public_res = float_opt(opts, "res", if resonant { 0.5 } else { 0.6 }).clamp(0.0, 0.99);
    let rq = sonic_filter_rq(public_res);
    let bandwidth = (centre * rq).max(20.0);
    let low_cut = (centre - bandwidth * 0.5).max(20.0);
    let high_cut = (centre + bandwidth * 0.5).max(low_cut + 20.0);
    let band = |samples: &[f64]| -> Vec<f64> {
        let high = highpass(samples, low_cut, sample_rate);
        let mut banded = lowpass(&high, high_cut, sample_rate);
        if resonant {
            banded = resonant_emphasis(samples, &banded, public_res);
        }
        banded
    };
    let mut out_left = band(left);
    let mut out_right = band(right);
    if normalised {
        let normalised_pair = normalise_pair(&out_left, &out_right, 1.0);
        out_left = normalised_pair.0;
        out_right = normalised_pair.1;
    }
    (out_left, out_right)
}

fn fx_band_eq(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let freq = note_frequency(float_opt(opts, "freq", 100.0)).max(20.0);
    let public_res = float_opt(opts, "res", 0.6).clamp(0.0, 0.99);
    let db = float_opt(opts, "db", 0.6);
    let gain = 10.0_f64.powf(db / 20.0) - 1.0;
    let bandwidth = (freq * sonic_filter_rq(public_res)).max(20.0);
    let apply = |samples: &[f64]| -> Vec<f64> {
        let band = lowpass(
            &highpass(samples, (freq - bandwidth * 0.5).max(20.0), sample_rate),
            freq + bandwidth * 0.5,
            sample_rate,
        );
        samples
            .iter()
            .zip(band.iter())
            .map(|(dry, band)| dry + band * gain)
            .collect()
    };
    (apply(left), apply(right))
}

fn fx_tanh(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let krunch = (float_opt(opts, "krunch", 5.0).max(0.0)).max(0.0001) * 5.0;
    let gain = 1.0 + krunch / 8.0;
    let shape = |sample: f64| (sample * krunch).tanh() / krunch * gain;
    (
        left.iter().map(|sample| shape(*sample)).collect(),
        right.iter().map(|sample| shape(*sample)).collect(),
    )
}

fn fx_pitch_shift(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let pitch = float_opt(opts, "pitch", 0.0).clamp(-72.0, 24.0);
    let ratio = 2.0_f64.powf(pitch / 12.0);
    (
        pitch_shift_to_len(left, ratio),
        pitch_shift_to_len(right, ratio),
    )
}

fn fx_ring_mod(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let freq = note_frequency(float_opt(opts, "freq", 30.0)).max(1.0);
    let mod_amp = float_opt(opts, "mod_amp", 1.0).max(0.0);
    let apply = |index: usize, sample: f64| {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        (sample * (1.0 + mod_amp * (TAU * freq * elapsed).sin())).clamp(-1.0, 1.0)
    };
    (
        left.iter()
            .enumerate()
            .map(|(index, sample)| apply(index, *sample))
            .collect(),
        right
            .iter()
            .enumerate()
            .map(|(index, sample)| apply(index, *sample))
            .collect(),
    )
}

fn fx_octaver(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let super_amp = float_opt(opts, "super_amp", 1.0).max(0.0);
    let sub_amp = float_opt(opts, "sub_amp", 1.0).max(0.0);
    let subsub_amp = float_opt(opts, "subsub_amp", 1.0).max(0.0);
    let apply = |samples: &[f64]| -> Vec<f64> {
        let direct = lowpass(samples, 440.0, sample_rate);
        let sub = octave_toggle(&direct, 1);
        let subsub = octave_toggle(&direct, 2);
        direct
            .iter()
            .enumerate()
            .map(|(index, sample)| {
                let super_oct = sample.abs() * 2.0;
                super_oct * super_amp
                    + sample * sub[index] * sub_amp
                    + sample * subsub[index] * subsub_amp
            })
            .collect()
    };
    (apply(left), apply(right))
}

fn fx_vowel(left: &[f64], right: &[f64], opts: &OptMap, sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
    let vowel = float_opt(opts, "vowel_sound", 1.0).round().clamp(1.0, 5.0) as usize;
    let voice = float_opt(opts, "voice", 0.0).round().clamp(0.0, 4.0) as usize;
    let scale = [1.25, 1.05, 0.95, 0.82, 0.65][voice];
    let formants = match vowel {
        1 => [800.0, 1150.0, 2900.0],
        2 => [400.0, 1600.0, 2700.0],
        3 => [350.0, 1700.0, 2700.0],
        4 => [450.0, 800.0, 2830.0],
        _ => [325.0, 700.0, 2530.0],
    };
    let apply = |samples: &[f64]| -> Vec<f64> {
        let mut acc = vec![0.0; samples.len()];
        for (formant_index, formant) in formants.iter().enumerate() {
            let center: f64 = *formant * scale;
            let width = center * 0.18;
            let band = lowpass(
                &highpass(samples, (center - width).max(20.0), sample_rate),
                center + width,
                sample_rate,
            );
            let gain = [1.0, 0.65, 0.35][formant_index];
            for (index, sample) in band.iter().enumerate() {
                acc[index] += sample * gain;
            }
        }
        acc
    };
    (apply(left), apply(right))
}

fn fx_flanger(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 4.0).max(0.001);
    let wave = float_opt(opts, "wave", 4.0) as i32;
    let delay_ms = float_opt(opts, "delay", 5.0).max(0.0);
    let depth_ms = float_opt(opts, "depth", 5.0).max(0.0);
    let feedback = float_opt(opts, "feedback", 0.0).clamp(0.0, 0.95);
    let invert = float_opt(opts, "invert_flange", 0.0) >= 0.5;
    let apply = |samples: &[f64], stereo_invert: bool| -> Vec<f64> {
        let mut output = Vec::with_capacity(samples.len());
        let mut delayed_feedback = 0.0;
        for (index, sample) in samples.iter().enumerate() {
            let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
            let mut amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
            if stereo_invert {
                amount = 1.0 - amount;
            }
            let delay = (delay_ms + depth_ms * amount) / 1000.0;
            let delay_samples = (delay * sample_rate as f64).round() as usize;
            let delayed = index
                .checked_sub(delay_samples)
                .and_then(|source| samples.get(source))
                .copied()
                .unwrap_or(0.0)
                + delayed_feedback * feedback;
            delayed_feedback = delayed;
            let flange = if invert { -delayed } else { delayed };
            output.push((sample + flange) * 0.5);
        }
        output
    };
    let stereo_invert = float_opt(opts, "stereo_invert_wave", 0.0) >= 0.5;
    (apply(left, false), apply(right, stereo_invert))
}

fn fx_slicer(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 0.25).max(0.001);
    let wave = float_opt(opts, "wave", 1.0) as i32;
    let amp_min = float_opt(opts, "amp_min", 0.0);
    let amp_max = float_opt(opts, "amp_max", 1.0);
    let smooth = float_opt(opts, "smooth", 0.0).max(0.0);
    let smooth_up = float_opt(opts, "smooth_up", 0.0).max(0.0);
    let smooth_down = float_opt(opts, "smooth_down", 0.0).max(0.0);
    let alpha_smooth = smoothing_alpha(smooth, sample_rate);
    let alpha_up = smoothing_alpha(smooth_up, sample_rate);
    let alpha_down = smoothing_alpha(smooth_down, sample_rate);
    let control_alpha = smoothing_alpha(slicer_control_block_seconds(sample_rate), sample_rate);
    let mut lag_ud_gain: Option<f64> = None;
    let mut lag_gain: Option<f64> = None;
    let mut control_gain: Option<f64> = None;

    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        let amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
        let target_gain = amp_min + (amp_max - amp_min) * amount;
        let previous_ud = lag_ud_gain.unwrap_or(target_gain);
        let alpha_ud = if target_gain >= previous_ud {
            alpha_up
        } else {
            alpha_down
        };
        let smoothed_ud = previous_ud + (target_gain - previous_ud) * alpha_ud;
        lag_ud_gain = Some(smoothed_ud);

        let previous_lag = lag_gain.unwrap_or(smoothed_ud);
        let lagged_gain = previous_lag + (smoothed_ud - previous_lag) * alpha_smooth;
        lag_gain = Some(lagged_gain);

        let previous_control = control_gain.unwrap_or(lagged_gain);
        let gain = previous_control + (lagged_gain - previous_control) * control_alpha;
        control_gain = Some(gain);
        out_left.push(left_sample * gain);
        out_right.push(right_sample * gain);
    }
    (out_left, out_right)
}

fn slicer_control_block_seconds(sample_rate: u32) -> f64 {
    64.0 / sample_rate.max(1) as f64
}

fn fx_wobble(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 0.5).max(0.001);
    let wave = float_opt(opts, "wave", 0.0) as i32;
    let cutoff_min = float_opt(opts, "cutoff_min", 60.0);
    let cutoff_max = float_opt(opts, "cutoff_max", float_opt(opts, "cutoff", 120.0));
    let filter = float_opt(opts, "filter", 0.0).round() as i32;
    let cutoff_min_hz = note_frequency(cutoff_min).max(20.0);
    let cutoff_max_hz = note_frequency(cutoff_max)
        .max(cutoff_min_hz)
        .min(sample_rate as f64 * 0.45);
    let public_res = float_opt(opts, "res", 0.8).clamp(0.0, 0.99);
    let rq = sonic_filter_rq(public_res);
    let cutoff_at = |index: usize| {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        let amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
        lin_exp(amount, cutoff_min_hz, cutoff_max_hz).clamp(20.0, sample_rate as f64 * 0.45)
    };
    resonant_modulated_filter_pair(
        left,
        right,
        sample_rate,
        if filter == 1 {
            FilterKind::High
        } else {
            FilterKind::Low
        },
        rq,
        cutoff_at,
    )
}

fn resonant_modulated_filter_pair(
    left: &[f64],
    right: &[f64],
    sample_rate: u32,
    kind: FilterKind,
    rq: f64,
    mut cutoff_at: impl FnMut(usize) -> f64,
) -> (Vec<f64>, Vec<f64>) {
    let mut left_state = BiquadState::default();
    let mut right_state = BiquadState::default();
    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
        let coeffs = BiquadCoefficients::resonant_filter(kind, cutoff_at(index), sample_rate, rq);
        out_left.push(left_state.process(*left_sample, coeffs));
        out_right.push(right_state.process(*right_sample, coeffs));
    }
    (out_left, out_right)
}

#[derive(Clone, Copy, Default)]
struct BiquadState {
    z1: f64,
    z2: f64,
}

impl BiquadState {
    fn process(&mut self, input: f64, coeffs: BiquadCoefficients) -> f64 {
        let output = coeffs.b0 * input + self.z1;
        self.z1 = coeffs.b1 * input - coeffs.a1 * output + self.z2;
        self.z2 = coeffs.b2 * input - coeffs.a2 * output;
        output
    }
}

#[derive(Clone, Copy)]
struct BiquadCoefficients {
    b0: f64,
    b1: f64,
    b2: f64,
    a1: f64,
    a2: f64,
}

impl BiquadCoefficients {
    fn resonant_filter(kind: FilterKind, cutoff_hz: f64, sample_rate: u32, rq: f64) -> Self {
        let q = (1.0 / rq.clamp(0.001, 1.0)).clamp(0.5, 20.0);
        Self::filter(kind, cutoff_hz, sample_rate, q)
    }

    fn filter(kind: FilterKind, cutoff_hz: f64, sample_rate: u32, q: f64) -> Self {
        let nyquist = sample_rate as f64 * 0.5;
        let cutoff = cutoff_hz.clamp(20.0, nyquist * 0.9);
        let q = q.clamp(0.1, 20.0);
        let omega = TAU * cutoff / sample_rate as f64;
        let sin_omega = omega.sin();
        let cos_omega = omega.cos();
        let alpha = sin_omega / (2.0 * q);
        let (b0, b1, b2) = match kind {
            FilterKind::Low => (
                (1.0 - cos_omega) * 0.5,
                1.0 - cos_omega,
                (1.0 - cos_omega) * 0.5,
            ),
            FilterKind::High => (
                (1.0 + cos_omega) * 0.5,
                -(1.0 + cos_omega),
                (1.0 + cos_omega) * 0.5,
            ),
        };
        let a0 = 1.0 + alpha;
        let a1 = -2.0 * cos_omega;
        let a2 = 1.0 - alpha;
        Self {
            b0: b0 / a0,
            b1: b1 / a0,
            b2: b2 / a0,
            a1: a1 / a0,
            a2: a2 / a0,
        }
    }
}

fn lin_exp(amount: f64, min_hz: f64, max_hz: f64) -> f64 {
    let amount = amount.clamp(0.0, 1.0);
    if min_hz <= 0.0 || max_hz <= min_hz {
        return min_hz.max(0.0);
    }
    min_hz * (max_hz / min_hz).powf(amount)
}

fn smooth_modulated_value(previous: f64, target: f64, opts: &OptMap, sample_rate: u32) -> f64 {
    let smooth = float_opt(opts, "smooth", 0.0)
        .max(float_opt(opts, "smooth_up", 0.0))
        .max(float_opt(opts, "smooth_down", 0.0));
    let alpha = smoothing_alpha(smooth, sample_rate);
    previous + (target - previous) * alpha
}

fn lfo_amount_from_opts(opts: &OptMap, wave: i32, elapsed_seconds: f64, phase_seconds: f64) -> f64 {
    let phase_offset = float_opt(opts, "phase_offset", 0.0);
    let pulse_width = float_opt(opts, "pulse_width", 0.5).clamp(0.001, 0.999);
    let mut amount = lfo_amount(
        wave,
        elapsed_seconds,
        phase_seconds,
        phase_offset,
        pulse_width,
    );
    if float_opt(opts, "invert_wave", 0.0) >= 0.5 {
        amount = 1.0 - amount;
    }
    amount
}

fn lfo_amount(
    wave: i32,
    elapsed_seconds: f64,
    phase_seconds: f64,
    phase_offset: f64,
    pulse_width: f64,
) -> f64 {
    let phase_pos = (elapsed_seconds / phase_seconds + phase_offset).rem_euclid(1.0);
    match wave {
        0 => phase_pos,
        2 => {
            if phase_pos < 0.5 {
                phase_pos * 2.0
            } else {
                2.0 - phase_pos * 2.0
            }
        }
        3 => 0.5 - 0.5 * (TAU * phase_pos).cos(),
        4 => {
            let sine = 0.5 - 0.5 * (TAU * phase_pos).cos();
            sine * sine * (3.0 - 2.0 * sine)
        }
        _ => {
            if phase_pos < pulse_width {
                1.0
            } else {
                0.0
            }
        }
    }
    .clamp(0.0, 1.0)
}

fn smoothing_alpha(seconds: f64, sample_rate: u32) -> f64 {
    if seconds <= 0.0 {
        1.0
    } else {
        (1.0 / (seconds * sample_rate as f64)).clamp(0.0001, 1.0)
    }
}

fn modulated_lowpass_pair(
    left: &[f64],
    right: &[f64],
    sample_rate: u32,
    mut cutoff_at: impl FnMut(usize) -> f64,
) -> (Vec<f64>, Vec<f64>) {
    let mut left_state = BiquadState::default();
    let mut right_state = BiquadState::default();
    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
        let coeffs = BiquadCoefficients::filter(
            FilterKind::Low,
            cutoff_at(index),
            sample_rate,
            FRAC_1_SQRT_2,
        );
        out_left.push(left_state.process(*left_sample, coeffs));
        out_right.push(right_state.process(*right_sample, coeffs));
    }
    (out_left, out_right)
}

fn filter_samples(
    samples: &[f64],
    cutoff_hz: f64,
    sample_rate: u32,
    kind: FilterKind,
    resonance: f64,
) -> Vec<f64> {
    let q = if resonance > 0.0 {
        1.0 / sonic_filter_rq(resonance)
    } else {
        FRAC_1_SQRT_2
    };
    biquad_filter_samples(samples, cutoff_hz, sample_rate, kind, q)
}

fn sonic_filter_rq(public_res: f64) -> f64 {
    (1.0 - public_res.clamp(0.0, 0.99)).clamp(0.001, 1.0)
}

fn resonant_emphasis(source: &[f64], filtered: &[f64], resonance: f64) -> Vec<f64> {
    source
        .iter()
        .zip(filtered.iter())
        .map(|(source, filtered)| filtered + (source - filtered) * resonance * 0.35)
        .collect()
}

fn normalise_pair(left: &[f64], right: &[f64], level: f64) -> (Vec<f64>, Vec<f64>) {
    let peak = left
        .iter()
        .chain(right.iter())
        .map(|sample| sample.abs())
        .fold(0.0, f64::max);
    if peak <= 1e-9 || level <= 0.0 {
        return (left.to_vec(), right.to_vec());
    }
    let gain = level / peak;
    (scale_samples(left, gain), scale_samples(right, gain))
}

fn pitch_shift_to_len(samples: &[f64], ratio: f64) -> Vec<f64> {
    if samples.is_empty() {
        return Vec::new();
    }
    let ratio = ratio.max(0.001);
    let mut shifted = Vec::with_capacity(samples.len());
    for index in 0..samples.len() {
        shifted.push(sample_linear(samples, index as f64 * ratio));
    }
    shifted
}

fn sample_linear(samples: &[f64], position: f64) -> f64 {
    if samples.is_empty() {
        return 0.0;
    }
    let wrapped = position.rem_euclid(samples.len() as f64);
    let low = wrapped.floor() as usize;
    let high = (low + 1) % samples.len();
    let frac = wrapped - low as f64;
    samples[low] * (1.0 - frac) + samples[high] * frac
}

fn sample_linear_clamped(samples: &[f64], position: f64) -> f64 {
    if samples.is_empty() {
        return 0.0;
    }
    let position = position.clamp(0.0, (samples.len() - 1) as f64);
    let low = position.floor() as usize;
    let high = (low + 1).min(samples.len() - 1);
    let frac = position - low as f64;
    samples[low] * (1.0 - frac) + samples[high] * frac
}

fn biquad_filter_samples(
    samples: &[f64],
    cutoff_hz: f64,
    sample_rate: u32,
    kind: FilterKind,
    q: f64,
) -> Vec<f64> {
    if samples.is_empty() {
        return Vec::new();
    }
    let coeffs = BiquadCoefficients::filter(kind, cutoff_hz, sample_rate, q);
    let mut state = BiquadState::default();
    let mut output = Vec::with_capacity(samples.len());
    for sample in samples {
        output.push(state.process(*sample, coeffs));
    }
    output
}

fn lowpass(samples: &[f64], cutoff_hz: f64, sample_rate: u32) -> Vec<f64> {
    biquad_filter_samples(
        samples,
        cutoff_hz,
        sample_rate,
        FilterKind::Low,
        FRAC_1_SQRT_2,
    )
}

fn highpass(samples: &[f64], cutoff_hz: f64, sample_rate: u32) -> Vec<f64> {
    biquad_filter_samples(
        samples,
        cutoff_hz,
        sample_rate,
        FilterKind::High,
        FRAC_1_SQRT_2,
    )
}

fn pan_gains(pan: f64) -> (f64, f64) {
    let angle = (pan.clamp(-1.0, 1.0) + 1.0) * PI / 4.0;
    (angle.cos(), angle.sin())
}

fn balance2_sample(left: f64, right: f64, pan: f64) -> (f64, f64) {
    let pan = pan.clamp(-1.0, 1.0);
    if pan < 0.0 {
        (left + right * -pan, right * (1.0 + pan))
    } else {
        (left * (1.0 - pan), right + left * pan)
    }
}

fn balance2_pair(left: &[f64], right: &[f64], pan: f64) -> (Vec<f64>, Vec<f64>) {
    let len = left.len().max(right.len());
    let mut out_left = Vec::with_capacity(len);
    let mut out_right = Vec::with_capacity(len);
    for index in 0..len {
        let left_sample = left.get(index).copied().unwrap_or(0.0);
        let right_sample = right.get(index).copied().unwrap_or(0.0);
        let balanced = balance2_sample(left_sample, right_sample, pan);
        out_left.push(balanced.0);
        out_right.push(balanced.1);
    }
    (out_left, out_right)
}

fn octave_toggle(samples: &[f64], divisions: usize) -> Vec<f64> {
    let mut output = Vec::with_capacity(samples.len());
    let mut sign = 1.0;
    let mut zero_crossings = 0usize;
    let mut previous = samples.first().copied().unwrap_or(0.0);
    let crossings_per_toggle = 2usize.pow(divisions as u32).max(1);
    for sample in samples {
        if (previous <= 0.0 && *sample > 0.0) || (previous >= 0.0 && *sample < 0.0) {
            zero_crossings += 1;
            if zero_crossings >= crossings_per_toggle {
                sign = -sign;
                zero_crossings = 0;
            }
        }
        output.push(sign);
        previous = *sample;
    }
    output
}

fn value_as_f64(value: &SynthValue) -> Option<f64> {
    match value {
        SynthValue::Bool(value) => Some(if *value { 1.0 } else { 0.0 }),
        SynthValue::Float(value) => Some(*value),
        SynthValue::String(value) => value.parse::<f64>().ok(),
        _ => None,
    }
}

fn value_as_str(value: &SynthValue) -> Option<&str> {
    match value {
        SynthValue::String(value) => Some(value),
        _ => None,
    }
}

fn float_opt(opts: &OptMap, name: &str, default: f64) -> f64 {
    opts.get(name).and_then(value_as_f64).unwrap_or(default)
}

fn string_opt(opts: &OptMap, name: &str, default: &str) -> String {
    match opts.get(name) {
        Some(SynthValue::String(value)) => value.clone(),
        Some(value) => value_as_f64(value)
            .map(|value| value.to_string())
            .unwrap_or_else(|| default.to_owned()),
        None => default.to_owned(),
    }
}

fn bool_opt(opts: &OptMap, name: &str, default: bool) -> bool {
    match opts.get(name) {
        Some(SynthValue::Bool(value)) => *value,
        Some(value) => value_as_f64(value)
            .map(|value| value != 0.0)
            .unwrap_or(default),
        None => default,
    }
}

const OUTPUT_LIMIT_CEILING: f64 = 0.92;
const OUTPUT_LIMIT_RELEASE_SECONDS: f64 = 0.08;

fn output_limit_pair(left: &[f64], right: &[f64], sample_rate: u32) -> (Vec<f64>, Vec<f64>) {
    output_limit_window(left, right, 0, left.len().max(right.len()), sample_rate)
}

fn output_limit_prefix(
    left: &[f64],
    right: &[f64],
    len: usize,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    output_limit_window(left, right, 0, len, sample_rate)
}

fn output_limit_window(
    left: &[f64],
    right: &[f64],
    start: usize,
    len: usize,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let process_len = start.saturating_add(len);
    let sample_rate = sample_rate.max(1) as f64;
    let release_alpha = 1.0 - (-1.0 / (OUTPUT_LIMIT_RELEASE_SECONDS * sample_rate)).exp();
    let mut envelope = 0.0;
    let mut gain = 1.0;
    let mut out_left = Vec::with_capacity(len);
    let mut out_right = Vec::with_capacity(len);

    for index in 0..process_len {
        let left_sample = left.get(index).copied().unwrap_or(0.0);
        let right_sample = right.get(index).copied().unwrap_or(0.0);
        let level = left_sample.abs().max(right_sample.abs());
        if level > envelope {
            envelope = level;
        } else {
            envelope += (level - envelope) * release_alpha;
        }
        let target_gain = if envelope > OUTPUT_LIMIT_CEILING {
            OUTPUT_LIMIT_CEILING / envelope
        } else {
            1.0
        };
        if target_gain < gain {
            gain = target_gain;
        } else {
            gain += (target_gain - gain) * release_alpha;
        }
        if index >= start {
            out_left.push((left_sample * gain).clamp(-OUTPUT_LIMIT_CEILING, OUTPUT_LIMIT_CEILING));
            out_right
                .push((right_sample * gain).clamp(-OUTPUT_LIMIT_CEILING, OUTPUT_LIMIT_CEILING));
        }
    }

    (out_left, out_right)
}

fn samples_to_interleaved_i16(left: &[f64], right: &[f64], frames: usize) -> Vec<i16> {
    let mut output = Vec::with_capacity(frames * 2);
    for index in 0..frames {
        for sample in [
            left.get(index).copied().unwrap_or(0.0),
            right.get(index).copied().unwrap_or(0.0),
        ] {
            output.push((sample.clamp(-1.0, 1.0) * 32767.0).round() as i16);
        }
    }
    output
}

fn stereo_wav_bytes(left: &[f64], right: &[f64], sample_rate: u32) -> Vec<u8> {
    let mut payload = Vec::with_capacity(44 + left.len().min(right.len()) * 4);
    let frames = left.len().min(right.len()) as u32;
    let data_len = frames * 4;
    payload.extend_from_slice(b"RIFF");
    payload.extend_from_slice(&(36 + data_len).to_le_bytes());
    payload.extend_from_slice(b"WAVE");
    payload.extend_from_slice(b"fmt ");
    payload.extend_from_slice(&16u32.to_le_bytes());
    payload.extend_from_slice(&1u16.to_le_bytes());
    payload.extend_from_slice(&2u16.to_le_bytes());
    payload.extend_from_slice(&sample_rate.to_le_bytes());
    payload.extend_from_slice(&(sample_rate * 4).to_le_bytes());
    payload.extend_from_slice(&4u16.to_le_bytes());
    payload.extend_from_slice(&16u16.to_le_bytes());
    payload.extend_from_slice(b"data");
    payload.extend_from_slice(&data_len.to_le_bytes());
    for (left_sample, right_sample) in left.iter().zip(right.iter()) {
        for sample in [*left_sample, *right_sample] {
            let clamped = sample.clamp(-1.0, 1.0);
            payload.extend_from_slice(&((clamped * 32767.0).round() as i16).to_le_bytes());
        }
    }
    payload
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decode_pcm_sample_sign_extends_16_bit_values() {
        assert_eq!(decode_pcm_sample(&0i16.to_le_bytes()), 0.0);
        assert!(decode_pcm_sample(&(-32768i16).to_le_bytes()) <= -1.0);
        assert!(decode_pcm_sample(&32767i16.to_le_bytes()) > 0.99);
    }

    #[test]
    fn reverb_produces_extended_diffuse_tail() {
        let sample_rate = 44_100;
        let mut left = vec![0.0; 512];
        let right = vec![0.0; 512];
        left[0] = 1.0;
        let mut opts = OptMap::new();
        opts.insert("room".to_owned(), SynthValue::Float(0.8));
        opts.insert("damp".to_owned(), SynthValue::Float(0.4));

        let (out_left, out_right) = fx_reverb(&left, &right, &opts, sample_rate);
        let tail_nonzero = out_left[512..]
            .iter()
            .chain(out_right[512..].iter())
            .filter(|sample| sample.abs() > 1.0e-9)
            .count();

        assert!(out_left.len() > left.len() + sample_rate as usize);
        assert!(tail_nonzero > 64, "tail_nonzero={tail_nonzero}");
    }

    #[test]
    fn slicer_default_edges_are_control_rate_dezipped() {
        let sample_rate = 1_000;
        let left = vec![1.0; 18];
        let right = vec![1.0; 18];
        let mut opts = OptMap::new();
        opts.insert("phase".to_owned(), SynthValue::Float(0.02));
        opts.insert("wave".to_owned(), SynthValue::Float(1.0));
        opts.insert("pulse_width".to_owned(), SynthValue::Float(0.5));

        let (out_left, out_right) = fx_slicer(&left, &right, &opts, sample_rate, 0.0);

        assert_eq!(out_left[0], 1.0);
        assert!(
            out_left[10] > 0.0 && out_left[10] < 1.0,
            "default slicer edge should dezipper instead of stepping to zero"
        );
        assert!(
            out_right[10] > 0.0 && out_right[10] < 1.0,
            "default slicer edge should dezipper instead of stepping to zero"
        );
    }

    #[test]
    fn slicer_smooth_options_lag_gate_edges() {
        let sample_rate = 1_000;
        let left = vec![1.0; 18];
        let right = vec![1.0; 18];
        let mut opts = OptMap::new();
        opts.insert("phase".to_owned(), SynthValue::Float(0.02));
        opts.insert("wave".to_owned(), SynthValue::Float(1.0));
        opts.insert("pulse_width".to_owned(), SynthValue::Float(0.5));
        opts.insert("smooth_down".to_owned(), SynthValue::Float(0.01));

        let (out_left, out_right) = fx_slicer(&left, &right, &opts, sample_rate, 0.0);

        assert_eq!(out_left[0], 1.0);
        assert!(
            out_left[10] > 0.0,
            "left edge should lag instead of hard-closing"
        );
        assert!(
            out_right[10] > 0.0,
            "right edge should lag instead of hard-closing"
        );
        assert!(
            out_left[17] < out_left[10],
            "lagged gate should continue moving toward amp_min"
        );
    }

    #[test]
    fn output_limiter_preserves_stereo_balance_for_hot_signals() {
        let left = vec![2.0; 128];
        let right = vec![1.0; 128];

        let (limited_left, limited_right) = output_limit_pair(&left, &right, 44_100);

        let peak = limited_left
            .iter()
            .chain(limited_right.iter())
            .map(|sample| sample.abs())
            .fold(0.0, f64::max);
        assert!(peak <= OUTPUT_LIMIT_CEILING);
        assert!((limited_left[0] / limited_right[0] - 2.0).abs() < 1e-9);
    }

    #[test]
    fn render_stereo_sample_preserves_channel_image() {
        let sample_rate = 8_000;
        let left_source = vec![0.8; 64];
        let right_source = vec![0.0; 64];
        let wav = stereo_wav_bytes(&left_source, &right_source, sample_rate);
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system clock should be valid")
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "gummy_synth_stereo_sample_{}_{}.wav",
            std::process::id(),
            nonce
        ));
        std::fs::write(&path, wav).expect("test WAV should be writable");
        let event = EventPayload {
            node_id: 3,
            kind: "sample".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::String(path.to_string_lossy().into_owned()),
            opts: OptMap::new(),
            synth_name: "sample".to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: Vec::new(),
            controls: Vec::new(),
        };

        let rendered = render_event(&event, sample_rate);
        let _ = std::fs::remove_file(&path);
        let (left, right) = rendered.expect("stereo sample event renders");
        let left_energy = left.iter().map(|sample| sample.abs()).sum::<f64>();
        let right_energy = right.iter().map(|sample| sample.abs()).sum::<f64>();

        assert!(left_energy > right_energy * 20.0);
    }

    #[test]
    fn render_synth_event_produces_stereo_samples() {
        let mut opts = OptMap::new();
        opts.insert("release".to_owned(), SynthValue::Float(0.05));
        let event = EventPayload {
            node_id: 1,
            kind: "play".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::Float(60.0),
            opts,
            synth_name: "_saw".to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: Vec::new(),
            controls: Vec::new(),
        };

        let (left, right) = render_event(&event, 8_000).expect("event renders");

        assert!(!left.is_empty());
        assert_eq!(left.len(), right.len());
        assert!(left.iter().any(|sample| sample.abs() > 0.0));
    }

    #[test]
    fn synth_cutoff_control_slides_filter_during_event() {
        let mut static_opts = OptMap::new();
        static_opts.insert("release".to_owned(), SynthValue::Float(0.15));
        static_opts.insert("cutoff".to_owned(), SynthValue::Float(40.0));
        static_opts.insert("cutoff_slide".to_owned(), SynthValue::Float(0.05));
        let static_event = EventPayload {
            node_id: 2,
            kind: "play".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::Float(48.0),
            opts: static_opts.clone(),
            synth_name: "_saw".to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: Vec::new(),
            controls: Vec::new(),
        };
        let mut control_opts = OptMap::new();
        control_opts.insert("cutoff".to_owned(), SynthValue::Float(120.0));
        let controlled_event = EventPayload {
            controls: vec![ControlPayload {
                time_seconds: 0.0,
                opts: control_opts,
            }],
            ..static_event.clone()
        };

        let (static_left, _) = render_event(&static_event, 8_000).expect("static event renders");
        let (controlled_left, _) =
            render_event(&controlled_event, 8_000).expect("controlled event renders");

        let static_energy = static_left.iter().map(|sample| sample.abs()).sum::<f64>();
        let controlled_energy = controlled_left
            .iter()
            .map(|sample| sample.abs())
            .sum::<f64>();
        assert!(controlled_energy > static_energy * 1.1);
    }

    #[test]
    fn synth_normalise_runs_before_amp_fudge() {
        let mut base_opts = OptMap::new();
        base_opts.insert("attack".to_owned(), SynthValue::Float(0.0));
        base_opts.insert("decay".to_owned(), SynthValue::Float(0.0));
        base_opts.insert("sustain".to_owned(), SynthValue::Float(0.0));
        base_opts.insert("release".to_owned(), SynthValue::Float(0.05));
        base_opts.insert("normalise".to_owned(), SynthValue::Bool(true));
        base_opts.insert("cutoff".to_owned(), SynthValue::Float(80.0));

        let mut quiet_opts = base_opts.clone();
        quiet_opts.insert("amp_fudge".to_owned(), SynthValue::Float(1.0));
        let mut loud_opts = base_opts;
        loud_opts.insert("amp_fudge".to_owned(), SynthValue::Float(2.0));
        let event = |opts: OptMap| EventPayload {
            node_id: 22,
            kind: "play".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::Float(52.0),
            opts,
            synth_name: "_saw".to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: Vec::new(),
            controls: Vec::new(),
        };

        let (quiet_left, quiet_right) =
            render_event(&event(quiet_opts), 8_000).expect("event renders");
        let (loud_left, loud_right) =
            render_event(&event(loud_opts), 8_000).expect("event renders");
        let quiet_peak = max_abs_pair(&quiet_left, &quiet_right);
        let loud_peak = max_abs_pair(&loud_left, &loud_right);

        assert!(
            loud_peak > quiet_peak * 1.9,
            "normalise should not cancel amp_fudge: quiet={quiet_peak}, loud={loud_peak}"
        );
    }

    #[test]
    fn synth_cutoff_envelope_sweeps_resonant_filter() {
        let mut opts = OptMap::new();
        opts.insert("attack".to_owned(), SynthValue::Float(0.0));
        opts.insert("decay".to_owned(), SynthValue::Float(0.0));
        opts.insert("sustain".to_owned(), SynthValue::Float(0.2));
        opts.insert("release".to_owned(), SynthValue::Float(0.01));
        opts.insert("sustain_level".to_owned(), SynthValue::Float(1.0));
        opts.insert("cutoff".to_owned(), SynthValue::Float(120.0));
        opts.insert("cutoff_min".to_owned(), SynthValue::Float(30.0));
        opts.insert("cutoff_attack".to_owned(), SynthValue::Float(0.0));
        opts.insert("cutoff_decay".to_owned(), SynthValue::Float(0.08));
        opts.insert("cutoff_sustain".to_owned(), SynthValue::Float(0.12));
        opts.insert("cutoff_release".to_owned(), SynthValue::Float(0.0));
        opts.insert("cutoff_attack_level".to_owned(), SynthValue::Float(1.0));
        opts.insert("cutoff_decay_level".to_owned(), SynthValue::Float(0.0));
        opts.insert("cutoff_sustain_level".to_owned(), SynthValue::Float(0.0));
        opts.insert("res".to_owned(), SynthValue::Float(0.9));
        let event = EventPayload {
            node_id: 21,
            kind: "play".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::Float(40.0),
            opts,
            synth_name: "_saw".to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: Vec::new(),
            controls: Vec::new(),
        };

        let (left, _) = render_event(&event, 8_000).expect("event renders");
        let early = average_abs_delta(&left[100..500]);
        let late = average_abs_delta(&left[1_200..1_600]);

        assert!(early > late * 1.5, "early={early}, late={late}");
    }

    #[test]
    fn wobble_fx_filters_high_frequency_content() {
        let mut opts = OptMap::new();
        opts.insert("phase".to_owned(), SynthValue::Float(0.5));
        opts.insert("cutoff_min".to_owned(), SynthValue::Float(40.0));
        opts.insert("cutoff_max".to_owned(), SynthValue::Float(55.0));
        opts.insert("mix".to_owned(), SynthValue::Float(1.0));
        let input: Vec<f64> = (0..4_000)
            .map(|index| if index % 2 == 0 { 1.0 } else { -1.0 })
            .collect();

        let (left, right) = fx_wobble(&input, &input, &opts, 8_000, 0.0);

        let input_energy =
            input.iter().map(|sample| sample.abs()).sum::<f64>() / input.len() as f64;
        let output_energy = left.iter().map(|sample| sample.abs()).sum::<f64>() / left.len() as f64;
        assert_eq!(left.len(), right.len());
        assert!(output_energy < input_energy * 0.25);
    }

    #[test]
    fn wobble_fx_uses_absolute_event_time_for_lfo_phase() {
        let mut opts = OptMap::new();
        opts.insert("phase".to_owned(), SynthValue::Float(1.0));
        opts.insert("cutoff_min".to_owned(), SynthValue::Float(35.0));
        opts.insert("cutoff_max".to_owned(), SynthValue::Float(110.0));
        opts.insert("mix".to_owned(), SynthValue::Float(1.0));
        let input = vec![1.0; 64];

        let (closed_left, _) = fx_wobble(&input, &input, &opts, 8_000, 0.0);
        let (open_left, _) = fx_wobble(&input, &input, &opts, 8_000, 0.5);

        assert!(open_left[0] > closed_left[0] * 4.0);
    }

    #[test]
    fn primitive_synth_keys_are_recognized_and_render() {
        let sample_rate = 8_000;
        for name in PRIMITIVE_SYNTH_KEYS {
            let kind = synth_kind(name);
            assert_ne!(
                kind,
                SynthKind::Unknown,
                "{name} is not mapped to a primitive synth kind"
            );
            let mut opts = OptMap::new();
            opts.insert("release".to_owned(), SynthValue::Float(0.04));
            if kind == SynthKind::Layered {
                let mut layer = OptMap::new();
                layer.insert("wave".to_owned(), SynthValue::String("sine".to_owned()));
                layer.insert("transpose".to_owned(), SynthValue::Float(0.0));
                layer.insert("amp".to_owned(), SynthValue::Float(1.0));
                layer.insert("opts".to_owned(), SynthValue::Dict(OptMap::new()));
                opts.insert(
                    "layers".to_owned(),
                    SynthValue::List(vec![SynthValue::Dict(layer)]),
                );
            }
            let event = EventPayload {
                node_id: 44,
                kind: "play".to_owned(),
                time_seconds: 0.0,
                value: SynthValue::Float(60.0),
                opts,
                synth_name: (*name).to_owned(),
                synth_opts: OptMap::new(),
                fx_chain: Vec::new(),
                controls: Vec::new(),
            };

            let (left, right) = render_event(&event, sample_rate).expect("primitive synth renders");

            assert!(!left.is_empty(), "{name} produced no left samples");
            assert_eq!(
                left.len(),
                right.len(),
                "{name} produced mismatched stereo samples"
            );
            let peak = left
                .iter()
                .chain(right.iter())
                .map(|sample| sample.abs())
                .fold(0.0, f64::max);
            if kind == SynthKind::Silence {
                assert_eq!(peak, 0.0, "{name} should be silent");
            } else {
                assert!(peak > 1e-5, "{name} rendered silence");
            }
        }
    }

    #[test]
    fn plan_renderer_groups_matching_fx_handles_into_shared_bus() {
        let mut synth_opts = OptMap::new();
        synth_opts.insert("release".to_owned(), SynthValue::Float(0.04));
        synth_opts.insert("amp".to_owned(), SynthValue::Float(1.0));
        let mut fx_opts = OptMap::new();
        fx_opts.insert("threshold".to_owned(), SynthValue::Float(0.05));
        fx_opts.insert("slope_above".to_owned(), SynthValue::Float(0.15));
        let event = EventPayload {
            node_id: 70,
            kind: "play".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::Float(48.0),
            opts: synth_opts,
            synth_name: "_saw".to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: vec![FxPayload {
                id: 9,
                name: "compressor".to_owned(),
                opts: fx_opts.clone(),
            }],
            controls: Vec::new(),
        };
        let mut same_bus_second = event.clone();
        same_bus_second.node_id = 71;
        same_bus_second.value = SynthValue::Float(55.0);
        let mut separate_bus_second = same_bus_second.clone();
        separate_bus_second.fx_chain[0].id = 10;

        let shared_bus = render_plan_events(vec![event.clone(), same_bus_second], 0.08, 8_000)
            .expect("shared FX bus renders");
        let separate_buses = render_plan_events(vec![event, separate_bus_second], 0.08, 8_000)
            .expect("separate FX buses render");

        assert_ne!(shared_bus, separate_buses);
    }

    #[test]
    fn documented_fx_keys_are_native_and_audible() {
        let sample_rate = 8_000;
        let left: Vec<f64> = (0..1_024)
            .map(|index| {
                let t = index as f64 / sample_rate as f64;
                (TAU * 180.0 * t).sin() * 0.45 + (TAU * 1_600.0 * t).sin() * 0.2
            })
            .collect();
        let right: Vec<f64> = (0..1_024)
            .map(|index| {
                let t = index as f64 / sample_rate as f64;
                (TAU * 260.0 * t).sin() * 0.35 + (TAU * 2_200.0 * t).sin() * 0.15
            })
            .collect();
        let names = [
            "bitcrusher",
            "krush",
            "reverb",
            "gverb",
            "level",
            "echo",
            "slicer",
            "panslicer",
            "wobble",
            "ixi_techno",
            "compressor",
            "whammy",
            "rlpf",
            "nrlpf",
            "rhpf",
            "nrhpf",
            "hpf",
            "nhpf",
            "lpf",
            "nlpf",
            "normaliser",
            "distortion",
            "pan",
            "bpf",
            "nbpf",
            "rbpf",
            "nrbpf",
            "band_eq",
            "tanh",
            "pitch_shift",
            "ring_mod",
            "octaver",
            "vowel",
            "flanger",
        ];

        for name in names {
            let opts = test_fx_opts(name);
            let (out_left, out_right) =
                apply_fx(name, left.clone(), right.clone(), &opts, sample_rate, 0.125);

            assert!(!out_left.is_empty(), "{name} produced no left samples");
            assert!(!out_right.is_empty(), "{name} produced no right samples");
            assert!(
                signal_changed(&left, &right, &out_left, &out_right),
                "{name} did not audibly affect the signal"
            );
        }
    }

    fn test_fx_opts(name: &str) -> OptMap {
        let mut opts = OptMap::new();
        match name {
            "bitcrusher" => {
                opts.insert("sample_rate".to_owned(), SynthValue::Float(1_000.0));
                opts.insert("bits".to_owned(), SynthValue::Float(4.0));
            }
            "level" => {
                opts.insert("amp".to_owned(), SynthValue::Float(0.5));
            }
            "normaliser" => {
                opts.insert("level".to_owned(), SynthValue::Float(0.25));
            }
            "pan" => {
                opts.insert("pan".to_owned(), SynthValue::Float(-0.8));
            }
            "pitch_shift" => {
                opts.insert("pitch".to_owned(), SynthValue::Float(7.0));
            }
            "band_eq" => {
                opts.insert("db".to_owned(), SynthValue::Float(-9.0));
            }
            "ring_mod" => {
                opts.insert("mod_amp".to_owned(), SynthValue::Float(0.8));
            }
            "flanger" => {
                opts.insert("feedback".to_owned(), SynthValue::Float(0.25));
            }
            "compressor" => {
                opts.insert("threshold".to_owned(), SynthValue::Float(0.05));
                opts.insert("slope_above".to_owned(), SynthValue::Float(0.25));
            }
            _ => {}
        }
        opts
    }

    fn signal_changed(left: &[f64], right: &[f64], out_left: &[f64], out_right: &[f64]) -> bool {
        if out_left.len() != left.len() || out_right.len() != right.len() {
            return true;
        }
        let left_delta = left
            .iter()
            .zip(out_left.iter())
            .map(|(before, after)| (before - after).abs())
            .sum::<f64>();
        let right_delta = right
            .iter()
            .zip(out_right.iter())
            .map(|(before, after)| (before - after).abs())
            .sum::<f64>();
        (left_delta + right_delta) / (left.len() + right.len()) as f64 > 1e-5
    }

    fn max_abs_pair(left: &[f64], right: &[f64]) -> f64 {
        left.iter()
            .chain(right.iter())
            .map(|sample| sample.abs())
            .fold(0.0, f64::max)
    }

    fn average_abs_delta(samples: &[f64]) -> f64 {
        if samples.len() < 2 {
            return 0.0;
        }
        samples
            .windows(2)
            .map(|pair| (pair[1] - pair[0]).abs())
            .sum::<f64>()
            / (samples.len() - 1) as f64
    }

    #[test]
    fn playback_plan_window_matches_full_render_window_for_simple_synth() {
        let sample_rate = 8_000;
        let mut opts = OptMap::new();
        opts.insert("release".to_owned(), SynthValue::Float(0.15));
        opts.insert("amp".to_owned(), SynthValue::Float(0.5));
        let plan = SynthPlaybackPlan {
            events: vec![EventPayload {
                node_id: 90,
                kind: "play".to_owned(),
                time_seconds: 0.0,
                value: SynthValue::Float(60.0),
                opts,
                synth_name: "_sine".to_owned(),
                synth_opts: OptMap::new(),
                fx_chain: Vec::new(),
                controls: Vec::new(),
            }],
            duration_seconds: 0.2,
            dry_event_cache: Mutex::new(HashMap::new()),
        };

        let full = plan
            .render_window_i16(0.0, 0.2, sample_rate)
            .expect("full window renders");
        let window = plan
            .render_window_i16(0.05, 0.04, sample_rate)
            .expect("live window renders");
        let offset = (0.05_f64 * sample_rate as f64).round() as usize * 2;
        let window_len = (0.04_f64 * sample_rate as f64).ceil() as usize * 2;

        assert_eq!(window, full[offset..offset + window_len]);
        assert!(plan
            .render_window_i16(0.25, 0.05, sample_rate)
            .expect("post-plan window renders")
            .is_empty());
    }

    #[test]
    fn stereo_wav_encoder_writes_expected_header() {
        let wav = stereo_wav_bytes(&[0.0, 0.5], &[0.0, -0.5], 44_100);

        assert_eq!(&wav[0..4], b"RIFF");
        assert_eq!(&wav[8..12], b"WAVE");
        assert_eq!(&wav[12..16], b"fmt ");
        assert_eq!(&wav[36..40], b"data");
        assert_eq!(wav.len(), 44 + 2 * 4);
    }
}
