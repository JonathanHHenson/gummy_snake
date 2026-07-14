//! PyO3 parsing and error adaptation for the `_canvas` synth functions.
//!
//! `gummy_synth` accepts only Rust-owned typed inputs and returns `SynthResult`.
//! This module preserves the established Python values, defaults, function names,
//! and `ValueError` surface at the mandatory canvas extension boundary.

use crate::sound::CanvasSound;
use gummy_synth::{
    CompiledSynthProgram, ControlPayload, EventPayload, FxPayload, GilReleasedOperation, OptMap,
    SynthResult, SynthValue,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBool, PyBytes, PyDict, PyList, PyModule, PyTuple};
use std::fs;
use std::path::PathBuf;

pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CanvasSynthProgram>()?;
    m.add_function(wrap_pyfunction!(synth_render_event_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_render_plan_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_render_serialized_plan_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_render_serialized_plan_wav_file, m)?)?;
    m.add_function(wrap_pyfunction!(synth_write_wav_file, m)?)?;
    m.add_function(wrap_pyfunction!(synth_sample_duration, m)?)?;
    m.add_function(wrap_pyfunction!(synth_set_worker_count, m)?)?;
    m.add_function(wrap_pyfunction!(synth_diagnostics, m)?)?;
    m.add_function(wrap_pyfunction!(synth_reset_diagnostics, m)?)?;
    Ok(())
}

/// Rust-owned compiled synth scheduling program.
///
/// This internal bridge handle parses and validates the serialized physical plan
/// once, then serves render and playback routes without repeating that work.
#[pyclass(name = "CanvasSynthProgram", unsendable)]
pub(crate) struct CanvasSynthProgram {
    program: CompiledSynthProgram,
}

#[pymethods]
impl CanvasSynthProgram {
    #[staticmethod]
    fn from_serialized(
        py: Python<'_>,
        payload: &Bound<'_, PyBytes>,
        sample_rate: u32,
    ) -> PyResult<Self> {
        let payload = payload.as_bytes().to_vec();
        gummy_synth::record_gil_released_call(GilReleasedOperation::Compile);
        let program = py
            .allow_threads(move || {
                CompiledSynthProgram::from_serialized_plan(&payload, sample_rate)
            })
            .map_err(synth_error)?;
        Ok(Self { program })
    }

    #[getter]
    fn sample_rate(&self) -> u32 {
        self.program.sample_rate()
    }

    #[getter]
    fn duration(&self) -> f64 {
        self.program.duration_seconds()
    }

    #[getter]
    fn duration_frames(&self) -> usize {
        self.program.duration_frames()
    }

    #[getter]
    fn event_count(&self) -> usize {
        self.program.event_count()
    }

    fn render_wav<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let program = self.program.clone();
        gummy_synth::record_gil_released_call(GilReleasedOperation::Render);
        let payload = py
            .allow_threads(move || gummy_synth::render_compiled_program_wav(&program))
            .map_err(synth_error)?;
        Ok(PyBytes::new_bound(py, &payload))
    }

    fn render_sound(&self, py: Python<'_>, path: String) -> PyResult<CanvasSound> {
        let program = self.program.clone();
        gummy_synth::record_gil_released_call(GilReleasedOperation::Render);
        let payload = py
            .allow_threads(move || gummy_synth::render_compiled_program_wav(&program))
            .map_err(synth_error)?;
        CanvasSound::from_encoded_bytes(path, payload)
    }

    fn render_wav_file(&self, py: Python<'_>, path: String) -> PyResult<()> {
        let program = self.program.clone();
        let path = PathBuf::from(path);
        gummy_synth::record_gil_released_call(GilReleasedOperation::Render);
        gummy_synth::record_gil_released_call(GilReleasedOperation::WriteWav);
        py.allow_threads(move || gummy_synth::render_compiled_program_wav_file(&program, &path))
            .map_err(synth_error)
    }
}

impl CanvasSynthProgram {
    pub(crate) fn cloned_program(&self) -> CompiledSynthProgram {
        self.program.clone()
    }
}

#[pyfunction]
fn synth_render_event_wav<'py>(
    py: Python<'py>,
    event: &Bound<'_, PyDict>,
    sample_rate: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let event = parse_event(event)?;
    gummy_synth::record_gil_released_call(GilReleasedOperation::Render);
    let payload = py
        .allow_threads(move || gummy_synth::render_event_wav(&event, sample_rate))
        .map_err(synth_error)?;
    Ok(PyBytes::new_bound(py, &payload))
}

#[pyfunction]
fn synth_render_plan_wav<'py>(
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
    gummy_synth::record_gil_released_call(GilReleasedOperation::Render);
    let payload = py
        .allow_threads(move || {
            gummy_synth::render_plan_events(parsed_events, duration_seconds, sample_rate)
        })
        .map_err(synth_error)?;
    Ok(PyBytes::new_bound(py, &payload))
}

#[pyfunction]
fn synth_render_serialized_plan_wav<'py>(
    py: Python<'py>,
    payload: &Bound<'_, PyBytes>,
    sample_rate: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let payload = payload.as_bytes().to_vec();
    gummy_synth::record_gil_released_call(GilReleasedOperation::CompileAndRender);
    let payload = py
        .allow_threads(move || gummy_synth::render_serialized_plan_wav_bytes(&payload, sample_rate))
        .map_err(synth_error)?;
    Ok(PyBytes::new_bound(py, &payload))
}

#[pyfunction]
fn synth_render_serialized_plan_wav_file(
    py: Python<'_>,
    payload: &Bound<'_, PyBytes>,
    sample_rate: u32,
    path: String,
) -> PyResult<()> {
    let payload = payload.as_bytes().to_vec();
    let path = PathBuf::from(path);
    gummy_synth::record_gil_released_call(GilReleasedOperation::CompileRenderAndWriteWav);
    py.allow_threads(move || {
        gummy_synth::render_serialized_plan_wav_file(&payload, sample_rate, &path)
    })
    .map_err(synth_error)
}

#[pyfunction]
fn synth_write_wav_file(
    py: Python<'_>,
    payload: &Bound<'_, PyBytes>,
    path: String,
) -> PyResult<()> {
    let payload = payload.as_bytes().to_vec();
    let path = PathBuf::from(path);
    let display_path = path.display().to_string();
    gummy_synth::record_gil_released_call(GilReleasedOperation::WriteWav);
    py.allow_threads(move || fs::write(&path, payload))
        .map_err(|error| {
            PyValueError::new_err(format!(
                "could not write rendered synth WAV {display_path}: {error}"
            ))
        })
}

#[pyfunction]
fn synth_sample_duration(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let value = parse_py_value(value)?;
    gummy_synth::record_gil_released_call(GilReleasedOperation::Decode);
    py.allow_threads(move || gummy_synth::sample_duration(&value))
        .map_err(synth_error)
}

#[pyfunction]
fn synth_set_worker_count(value: &Bound<'_, PyAny>) -> PyResult<usize> {
    let worker_count = if value.is_instance_of::<PyBool>() {
        return Err(PyValueError::new_err(
            "synth worker count must be one of 1, 2, 4, 8, or 'auto'.",
        ));
    } else if let Ok(value) = value.extract::<String>() {
        if value != "auto" {
            return Err(PyValueError::new_err(
                "synth worker count must be one of 1, 2, 4, 8, or 'auto'.",
            ));
        }
        None
    } else if let Ok(value) = value.extract::<usize>() {
        Some(value)
    } else {
        return Err(PyValueError::new_err(
            "synth worker count must be one of 1, 2, 4, 8, or 'auto'.",
        ));
    };
    synth_value_result(gummy_synth::set_worker_count(worker_count))
}

#[pyfunction]
fn synth_diagnostics<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let diagnostics = gummy_synth::diagnostics();
    let payload = PyDict::new_bound(py);
    payload.set_item(
        "configured_worker_count",
        diagnostics.configured_worker_count,
    )?;
    payload.set_item(
        "worker_mode",
        if diagnostics.configured_worker_count.is_some() {
            "explicit"
        } else {
            "auto"
        },
    )?;
    payload.set_item("worker_count", diagnostics.worker_count)?;
    payload.set_item("worker_pool_capacity", diagnostics.worker_pool_capacity)?;
    payload.set_item(
        "worker_pool_initializations",
        diagnostics.worker_pool_initializations,
    )?;
    payload.set_item("gil_released_calls", diagnostics.gil_released_calls)?;
    payload.set_item(
        "gil_released_render_calls",
        diagnostics.gil_released_render_calls,
    )?;
    payload.set_item(
        "gil_released_compile_calls",
        diagnostics.gil_released_compile_calls,
    )?;
    payload.set_item(
        "gil_released_decode_calls",
        diagnostics.gil_released_decode_calls,
    )?;
    payload.set_item(
        "gil_released_wav_write_calls",
        diagnostics.gil_released_wav_write_calls,
    )?;
    payload.set_item("parallel_regions", diagnostics.parallel_regions)?;
    payload.set_item("parallel_tasks", diagnostics.parallel_tasks)?;
    payload.set_item("parallel_events", diagnostics.parallel_events)?;
    payload.set_item("serial_events", diagnostics.serial_events)?;
    payload.set_item(
        "parallel_scratch_peak_bytes",
        diagnostics.parallel_scratch_peak_bytes,
    )?;
    payload.set_item(
        "parallel_scratch_limit_bytes",
        diagnostics.parallel_scratch_limit_bytes,
    )?;
    payload.set_item(
        "parallel_min_scratch_bytes",
        diagnostics.parallel_min_scratch_bytes,
    )?;
    payload.set_item(
        "sample_source_cache_hits",
        diagnostics.sample_cache.source_hits,
    )?;
    payload.set_item(
        "sample_source_cache_misses",
        diagnostics.sample_cache.source_misses,
    )?;
    payload.set_item(
        "sample_source_cache_evictions",
        diagnostics.sample_cache.source_evictions,
    )?;
    payload.set_item(
        "sample_source_cache_bytes",
        diagnostics.sample_cache.source_bytes,
    )?;
    payload.set_item(
        "sample_source_cache_entries",
        diagnostics.sample_cache.source_entries,
    )?;
    payload.set_item(
        "sample_source_cache_budget_bytes",
        diagnostics.sample_cache.source_budget_bytes,
    )?;
    payload.set_item(
        "sample_resample_cache_hits",
        diagnostics.sample_cache.resample_hits,
    )?;
    payload.set_item(
        "sample_resample_cache_misses",
        diagnostics.sample_cache.resample_misses,
    )?;
    payload.set_item(
        "sample_resample_cache_evictions",
        diagnostics.sample_cache.resample_evictions,
    )?;
    payload.set_item(
        "sample_resample_cache_bytes",
        diagnostics.sample_cache.resample_bytes,
    )?;
    payload.set_item(
        "sample_resample_cache_entries",
        diagnostics.sample_cache.resample_entries,
    )?;
    payload.set_item(
        "sample_resample_cache_budget_bytes",
        diagnostics.sample_cache.resample_budget_bytes,
    )?;
    payload.set_item(
        "sample_cache_stale_invalidations",
        diagnostics.sample_cache.stale_invalidations,
    )?;
    payload.set_item(
        "sample_cache_lock_contentions",
        diagnostics.sample_cache.lock_contentions,
    )?;
    payload.set_item(
        "causal_normaliser_contract_version",
        gummy_synth::CAUSAL_NORMALISER_CONTRACT_VERSION,
    )?;
    let audio = crate::sound::audio_diagnostics();
    payload.set_item(
        "audio_manager_initializations",
        audio.manager_initializations,
    )?;
    payload.set_item("audio_device_open_count", audio.device_open_count)?;
    payload.set_item("audio_device_error_count", audio.device_error_count)?;
    payload.set_item("audio_active_voices", audio.active_voices)?;
    payload.set_item("audio_peak_active_voices", audio.peak_active_voices)?;
    payload.set_item("audio_active_synth_sessions", audio.active_synth_sessions)?;
    payload.set_item(
        "audio_peak_active_synth_sessions",
        audio.peak_active_synth_sessions,
    )?;
    payload.set_item("audio_mixed_blocks", audio.mixed_blocks)?;
    payload.set_item("audio_mixed_frames", audio.mixed_frames)?;
    payload.set_item("audio_command_count", audio.command_count)?;
    payload.set_item("audio_queue_frames", audio.queue_frames)?;
    payload.set_item("audio_queue_min_frames", audio.queue_min_frames)?;
    payload.set_item("audio_queue_peak_frames", audio.queue_peak_frames)?;
    payload.set_item("audio_queue_low_water_frames", audio.queue_low_water_frames)?;
    payload.set_item(
        "audio_queue_high_water_frames",
        audio.queue_high_water_frames,
    )?;
    payload.set_item("audio_queue_underruns", audio.queue_underruns)?;
    payload.set_item("audio_asset_bytes", audio.asset_bytes)?;
    payload.set_item("audio_asset_voice_starts", audio.asset_voice_starts)?;
    payload.set_item("audio_synth_session_starts", audio.synth_session_starts)?;
    Ok(payload)
}

#[pyfunction]
fn synth_reset_diagnostics() {
    gummy_synth::reset_diagnostics();
    crate::sound::reset_audio_diagnostics();
}

fn synth_error(error: gummy_synth::SynthError) -> PyErr {
    PyValueError::new_err(error.message().to_owned())
}

fn synth_value_result<T>(result: SynthResult<T>) -> PyResult<T> {
    result.map_err(synth_error)
}

fn parse_event(dict: &Bound<'_, PyDict>) -> PyResult<EventPayload> {
    validate_dict_keys(
        dict,
        &[
            "node_id",
            "seed",
            "order",
            "kind",
            "time_seconds",
            "value",
            "opts",
            "synth_name",
            "synth_opts",
            "fx_chain",
            "controls",
        ],
        "synth event payload",
    )?;
    Ok(EventPayload {
        node_id: get_u64(dict, "node_id", 0)?,
        seed: get_u64(dict, "seed", 0)?,
        order: get_u64(dict, "order", 0)?,
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
        Some(value) => {
            let value = value.extract::<f64>().map_err(|_| {
                PyValueError::new_err(format!("synth event key {key:?} must be numeric."))
            })?;
            if !value.is_finite() {
                return Err(PyValueError::new_err(format!(
                    "synth event key {key:?} must be finite."
                )));
            }
            Ok(value)
        }
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
        validate_dict_keys(item, &["id", "name", "opts"], "synth FX handle")?;
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
        validate_dict_keys(item, &["time_seconds", "opts"], "synth control payload")?;
        output.push(ControlPayload {
            time_seconds: get_f64(item, "time_seconds", 0.0)?,
            opts: get_opt_map(item, "opts")?,
        });
    }
    output.sort_by(|a, b| a.time_seconds.total_cmp(&b.time_seconds));
    Ok(output)
}

fn parse_opt_map(dict: &Bound<'_, PyDict>) -> PyResult<OptMap> {
    let mut item_count = 0usize;
    let mut output = OptMap::with_capacity(dict.len());
    for (key, value) in dict.iter() {
        let key = key.extract::<String>().map_err(|_| {
            PyValueError::new_err(
                "synth option mapping keys must be strings; keys are not coerced.",
            )
        })?;
        if key.is_empty() {
            return Err(PyValueError::new_err(
                "synth option mapping keys cannot be empty.",
            ));
        }
        output.insert(key, parse_py_value_at_depth(&value, 0, &mut item_count)?);
    }
    Ok(output)
}

fn parse_py_value(value: &Bound<'_, PyAny>) -> PyResult<SynthValue> {
    let mut item_count = 0usize;
    parse_py_value_at_depth(value, 0, &mut item_count)
}

fn parse_py_value_at_depth(
    value: &Bound<'_, PyAny>,
    depth: usize,
    item_count: &mut usize,
) -> PyResult<SynthValue> {
    const MAX_VALUE_DEPTH: usize = 64;
    const MAX_VALUE_ITEMS: usize = 1_000_000;
    if depth > MAX_VALUE_DEPTH {
        return Err(PyValueError::new_err(format!(
            "synth payload nesting exceeds the limit of {MAX_VALUE_DEPTH}."
        )));
    }
    *item_count = item_count.checked_add(1).ok_or_else(|| {
        PyValueError::new_err("synth payload item count overflowed the validation budget.")
    })?;
    if *item_count > MAX_VALUE_ITEMS {
        return Err(PyValueError::new_err(format!(
            "synth payload item count exceeds the limit of {MAX_VALUE_ITEMS}."
        )));
    }
    if value.is_none() {
        return Ok(SynthValue::None);
    }
    if let Ok(value) = value.extract::<bool>() {
        return Ok(SynthValue::Bool(value));
    }
    if let Ok(value) = value.extract::<f64>() {
        if !value.is_finite() {
            return Err(PyValueError::new_err(
                "synth payload numeric values must be finite.",
            ));
        }
        return Ok(SynthValue::Float(value));
    }
    if let Ok(value) = value.extract::<String>() {
        return Ok(SynthValue::String(value));
    }
    if let Ok(list) = value.downcast::<PyList>() {
        return parse_sequence(list.iter(), depth + 1, item_count);
    }
    if let Ok(tuple) = value.downcast::<PyTuple>() {
        return parse_sequence(tuple.iter(), depth + 1, item_count);
    }
    if let Ok(dict) = value.downcast::<PyDict>() {
        let mut output = OptMap::with_capacity(dict.len());
        for (key, value) in dict.iter() {
            let key = key.extract::<String>().map_err(|_| {
                PyValueError::new_err(
                    "synth payload mapping keys must be strings; keys are not coerced.",
                )
            })?;
            if key.is_empty() {
                return Err(PyValueError::new_err(
                    "synth payload mapping keys cannot be empty.",
                ));
            }
            output.insert(key, parse_py_value_at_depth(&value, depth + 1, item_count)?);
        }
        return Ok(SynthValue::Dict(output));
    }
    Err(PyValueError::new_err(
        "synth payload values must be None, bool, finite number, string, list, tuple, or string-keyed mapping.",
    ))
}

fn parse_sequence<'py>(
    items: impl Iterator<Item = Bound<'py, PyAny>>,
    depth: usize,
    item_count: &mut usize,
) -> PyResult<SynthValue> {
    let mut output = Vec::new();
    for item in items {
        output.push(parse_py_value_at_depth(&item, depth, item_count)?);
    }
    Ok(SynthValue::List(output))
}

fn validate_dict_keys(dict: &Bound<'_, PyDict>, allowed: &[&str], label: &str) -> PyResult<()> {
    let mut unexpected = Vec::new();
    for (key, _) in dict.iter() {
        let key = key.extract::<String>().map_err(|_| {
            PyValueError::new_err(format!(
                "{label} keys must be strings; keys are not coerced."
            ))
        })?;
        if !allowed.contains(&key.as_str()) {
            unexpected.push(key);
        }
    }
    unexpected.sort();
    if unexpected.is_empty() {
        return Ok(());
    }
    Err(PyValueError::new_err(format!(
        "{label} contains unsupported key(s): {}.",
        unexpected.join(", ")
    )))
}
