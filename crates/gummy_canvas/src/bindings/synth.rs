//! PyO3 parsing and error adaptation for the `_canvas` synth functions.
//!
//! `gummy_synth` accepts only Rust-owned typed inputs and returns `SynthResult`.
//! This module preserves the established Python values, defaults, function names,
//! and `ValueError` surface at the mandatory canvas extension boundary.

use gummy_synth::{ControlPayload, EventPayload, FxPayload, OptMap, SynthResult, SynthValue};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList, PyModule, PyTuple};

pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(synth_render_event_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_render_plan_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_render_serialized_plan_wav, m)?)?;
    m.add_function(wrap_pyfunction!(synth_sample_duration, m)?)?;
    Ok(())
}

#[pyfunction]
fn synth_render_event_wav<'py>(
    py: Python<'py>,
    event: &Bound<'_, PyDict>,
    sample_rate: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let event = parse_event(event)?;
    let payload = synth_value_result(gummy_synth::render_event_wav(&event, sample_rate))?;
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
    let payload = synth_value_result(gummy_synth::render_plan_events(
        parsed_events,
        duration_seconds,
        sample_rate,
    ))?;
    Ok(PyBytes::new_bound(py, &payload))
}

#[pyfunction]
fn synth_render_serialized_plan_wav<'py>(
    py: Python<'py>,
    payload: &Bound<'_, PyBytes>,
    sample_rate: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let payload = synth_value_result(gummy_synth::render_serialized_plan_wav_bytes(
        payload.as_bytes(),
        sample_rate,
    ))?;
    Ok(PyBytes::new_bound(py, &payload))
}

#[pyfunction]
fn synth_sample_duration(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let value = parse_py_value(value)?;
    synth_value_result(gummy_synth::sample_duration(&value))
}

fn synth_value_result<T>(result: SynthResult<T>) -> PyResult<T> {
    result.map_err(|error| PyValueError::new_err(error.message().to_owned()))
}

fn parse_event(dict: &Bound<'_, PyDict>) -> PyResult<EventPayload> {
    Ok(EventPayload {
        node_id: get_u64(dict, "node_id", 0)?,
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
