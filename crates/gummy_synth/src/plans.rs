use super::*;

pub(crate) fn parse_serialized_plan(payload: &[u8]) -> SynthResult<(Vec<EventPayload>, f64)> {
    if payload.len() < 16 {
        return Err(SynthError::new(
            "serialized synth physical plan is too short.",
        ));
    }
    if &payload[..8] != GSS_MAGIC {
        return Err(SynthError::new(
            "serialized synth physical plan has an invalid binary header.",
        ));
    }
    let compression = u32::from_be_bytes(payload[8..12].try_into().map_err(|_| {
        SynthError::new("serialized synth physical plan has an invalid compression header.")
    })?);
    let raw_size = u32::from_be_bytes(payload[12..16].try_into().map_err(|_| {
        SynthError::new("serialized synth physical plan has an invalid size header.")
    })?) as usize;
    if compression != GSS_COMPRESSION_ZLIB {
        return Err(SynthError::new(format!(
            "unsupported synth physical-plan compression mode {compression}."
        )));
    }
    let mut decoder = ZlibDecoder::new(&payload[16..]);
    let mut raw = Vec::with_capacity(raw_size);
    decoder.read_to_end(&mut raw).map_err(|err| {
        SynthError::new(format!(
            "could not decompress serialized synth physical plan: {err}"
        ))
    })?;
    if raw.len() != raw_size {
        return Err(SynthError::new(
            "serialized synth physical plan size check failed.",
        ));
    }
    let root: JsonValue = serde_json::from_slice(&raw).map_err(|err| {
        SynthError::new(format!(
            "serialized synth physical plan JSON is invalid: {err}"
        ))
    })?;
    let root = root.as_object().ok_or_else(|| {
        SynthError::new("serialized synth physical plan payload must be an object.")
    })?;
    let schema = root
        .get("schema")
        .and_then(JsonValue::as_str)
        .unwrap_or_default();
    if schema != PHYSICAL_PLAN_SCHEMA {
        return Err(SynthError::new(format!(
            "unsupported synth physical-plan schema {schema:?}."
        )));
    }
    let duration_seconds = root
        .get("duration_seconds")
        .and_then(JsonValue::as_f64)
        .unwrap_or(0.0);
    let mut controls = parse_serialized_controls(root.get("controls"))?;
    controls.sort_by(|a, b| {
        a.time_seconds
            .total_cmp(&b.time_seconds)
            .then_with(|| a.order.cmp(&b.order))
    });
    let scheduled_events = parse_serialized_events(root.get("events"))?;
    let events = scheduled_events
        .into_iter()
        .map(|event| event.with_controls(&controls))
        .collect();
    Ok((events, duration_seconds))
}

pub(crate) fn parse_serialized_events(
    value: Option<&JsonValue>,
) -> SynthResult<Vec<ScheduledEventPayload>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let events = value
        .as_array()
        .ok_or_else(|| SynthError::new("serialized synth physical plan events must be a list."))?;
    events.iter().map(parse_serialized_event).collect()
}

pub(crate) fn parse_serialized_event(value: &JsonValue) -> SynthResult<ScheduledEventPayload> {
    let object = value
        .as_object()
        .ok_or_else(|| SynthError::new("serialized synth event must be an object."))?;
    Ok(ScheduledEventPayload {
        instance_key: json_key(object.get("instance").unwrap_or(&JsonValue::Null)),
        node_id: json_u64(object.get("node_id"), 0),
        order: json_u64(object.get("order"), 0),
        kind: json_string(object.get("kind"), "play"),
        time_seconds: json_f64(object.get("time_seconds"), 0.0),
        value: json_to_synth_value(object.get("value").unwrap_or(&JsonValue::Null))?,
        opts: json_to_opt_map(object.get("opts"))?,
        synth_name: json_string(object.get("synth_name"), "beep"),
        synth_opts: json_to_opt_map(object.get("synth_opts"))?,
        fx_chain: parse_serialized_fx_chain(object.get("fx_chain"))?,
    })
}

pub(crate) fn parse_serialized_fx_chain(
    value: Option<&JsonValue>,
) -> SynthResult<Vec<ScheduledFxPayload>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let handles = value
        .as_array()
        .ok_or_else(|| SynthError::new("serialized synth event fx_chain must be a list."))?;
    handles
        .iter()
        .map(|value| {
            let object = value
                .as_object()
                .ok_or_else(|| SynthError::new("serialized synth FX handle must be an object."))?;
            Ok(ScheduledFxPayload {
                id: json_u64(object.get("id"), 0),
                name: json_string(object.get("name"), "level"),
                opts: json_to_opt_map(object.get("opts"))?,
            })
        })
        .collect()
}

pub(crate) fn parse_serialized_controls(
    value: Option<&JsonValue>,
) -> SynthResult<Vec<ScheduledControlPayload>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let controls = value.as_array().ok_or_else(|| {
        SynthError::new("serialized synth physical plan controls must be a list.")
    })?;
    controls
        .iter()
        .map(|value| {
            let object = value
                .as_object()
                .ok_or_else(|| SynthError::new("serialized synth control must be an object."))?;
            Ok(ScheduledControlPayload {
                target_instance_key: json_key(
                    object.get("target_instance").unwrap_or(&JsonValue::Null),
                ),
                target_id: json_u64(object.get("target_id"), 0),
                time_seconds: json_f64(object.get("time_seconds"), 0.0),
                opts: json_to_opt_map(object.get("opts"))?,
                order: json_u64(object.get("order"), 0),
            })
        })
        .collect()
}

pub(crate) fn fx_control_precedes_event(
    control: &ScheduledControlPayload,
    event_time_seconds: f64,
    event_order: u64,
) -> bool {
    control.time_seconds < event_time_seconds - 1e-9
        || ((control.time_seconds - event_time_seconds).abs() <= 1e-9
            && control.order < event_order)
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
        let event_time_seconds = self.time_seconds;
        let event_order = self.order;
        let fx_chain = self
            .fx_chain
            .into_iter()
            .map(|fx| {
                let mut opts = fx.opts;
                for control in controls {
                    if control.target_id == fx.id
                        && fx_control_precedes_event(control, event_time_seconds, event_order)
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
            order: self.order,
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

pub(crate) fn json_to_synth_value(value: &JsonValue) -> SynthResult<SynthValue> {
    match value {
        JsonValue::Null => Ok(SynthValue::None),
        JsonValue::Bool(value) => Ok(SynthValue::Bool(*value)),
        JsonValue::Number(value) => value.as_f64().map(SynthValue::Float).ok_or_else(|| {
            SynthError::new("serialized synth numeric value is not representable as f64.")
        }),
        JsonValue::String(value) => Ok(SynthValue::String(value.clone())),
        JsonValue::Array(values) => values
            .iter()
            .map(json_to_synth_value)
            .collect::<SynthResult<Vec<_>>>()
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

pub(crate) fn json_to_opt_map(value: Option<&JsonValue>) -> SynthResult<OptMap> {
    let Some(value) = value else {
        return Ok(OptMap::new());
    };
    let object = value
        .as_object()
        .ok_or_else(|| SynthError::new("serialized synth opts must be an object."))?;
    let mut output = OptMap::with_capacity(object.len());
    for (key, value) in object {
        output.insert(key.clone(), json_to_synth_value(value)?);
    }
    Ok(output)
}

pub(crate) fn json_key(value: &JsonValue) -> String {
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

pub(crate) fn json_string(value: Option<&JsonValue>, default: &str) -> String {
    value
        .and_then(JsonValue::as_str)
        .unwrap_or(default)
        .to_owned()
}

pub(crate) fn json_f64(value: Option<&JsonValue>, default: f64) -> f64 {
    value.and_then(JsonValue::as_f64).unwrap_or(default)
}

pub(crate) fn json_u64(value: Option<&JsonValue>, default: u64) -> u64 {
    value.and_then(JsonValue::as_u64).unwrap_or(default)
}
