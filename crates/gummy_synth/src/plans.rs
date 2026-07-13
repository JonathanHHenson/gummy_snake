use super::*;

pub(crate) fn parse_serialized_plan(payload: &[u8]) -> SynthResult<(Vec<EventPayload>, f64)> {
    if payload.len() > MAX_SERIALIZED_PLAN_BYTES {
        return Err(SynthError::new(format!(
            "serialized synth physical plan exceeds the compressed payload limit of {MAX_SERIALIZED_PLAN_BYTES} bytes."
        )));
    }
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
    if raw_size > MAX_DECOMPRESSED_PLAN_BYTES {
        return Err(SynthError::new(format!(
            "serialized synth physical plan declares {raw_size} decompressed bytes, exceeding the limit of {MAX_DECOMPRESSED_PLAN_BYTES}."
        )));
    }
    let decoder = ZlibDecoder::new(&payload[16..]);
    let mut raw = Vec::with_capacity(raw_size.min(MAX_DECOMPRESSED_PLAN_BYTES));
    decoder
        .take((MAX_DECOMPRESSED_PLAN_BYTES + 1) as u64)
        .read_to_end(&mut raw)
        .map_err(|err| {
            SynthError::new(format!(
                "could not decompress serialized synth physical plan: {err}"
            ))
        })?;
    if raw.len() > MAX_DECOMPRESSED_PLAN_BYTES {
        return Err(SynthError::new(format!(
            "serialized synth physical plan decompressed payload exceeds the limit of {MAX_DECOMPRESSED_PLAN_BYTES} bytes."
        )));
    }
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
    validate_json_object_keys(
        root,
        &[
            "schema",
            "duration_seconds",
            "sample_rate",
            "events",
            "controls",
            "metadata",
        ],
        "serialized synth physical plan",
    )?;
    let schema = required_json_string(root.get("schema"), "serialized synth physical plan schema")?;
    if schema != PHYSICAL_PLAN_SCHEMA {
        return Err(SynthError::new(format!(
            "unsupported synth physical-plan schema {schema:?}."
        )));
    }
    let duration_seconds = required_json_f64(
        root.get("duration_seconds"),
        "serialized synth physical plan duration_seconds",
    )?;
    validate_finite_non_negative(
        duration_seconds,
        "serialized synth physical plan duration_seconds",
    )?;
    if let Some(sample_rate) = root.get("sample_rate") {
        let sample_rate = required_json_u64(
            Some(sample_rate),
            "serialized synth physical plan sample_rate",
        )?;
        let sample_rate = u32::try_from(sample_rate).map_err(|_| {
            SynthError::new("serialized synth physical plan sample_rate is out of range.")
        })?;
        validate_sample_rate(sample_rate)?;
    }
    if let Some(metadata) = root.get("metadata") {
        let metadata = json_to_synth_value(metadata)?;
        let mut item_count = 0;
        validate_synth_value(&metadata, 0, &mut item_count, "serialized synth metadata")?;
    }
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
    let value = value.ok_or_else(|| {
        SynthError::new("serialized synth physical plan is missing required key \"events\".")
    })?;
    let events = value
        .as_array()
        .ok_or_else(|| SynthError::new("serialized synth physical plan events must be a list."))?;
    if events.len() > MAX_PLAN_EVENTS {
        return Err(SynthError::new(format!(
            "serialized synth plan event count {} exceeds the limit of {MAX_PLAN_EVENTS}.",
            events.len()
        )));
    }
    events.iter().map(parse_serialized_event).collect()
}

pub(crate) fn parse_serialized_event(value: &JsonValue) -> SynthResult<ScheduledEventPayload> {
    let object = value
        .as_object()
        .ok_or_else(|| SynthError::new("serialized synth event must be an object."))?;
    validate_json_object_keys(
        object,
        &[
            "instance",
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
        ],
        "serialized synth event",
    )?;
    Ok(ScheduledEventPayload {
        instance_key: json_identity_key(required_json_value(
            object.get("instance"),
            "serialized synth event instance",
        )?)?,
        node_id: required_json_u64(object.get("node_id"), "serialized synth event node_id")?,
        seed: optional_json_u64(object.get("seed"), 0, "serialized synth event seed")?,
        order: required_json_u64(object.get("order"), "serialized synth event order")?,
        kind: required_json_string(object.get("kind"), "serialized synth event kind")?,
        time_seconds: required_json_f64(
            object.get("time_seconds"),
            "serialized synth event time_seconds",
        )?,
        value: json_to_synth_value(required_json_value(
            object.get("value"),
            "serialized synth event value",
        )?)?,
        opts: json_to_required_opt_map(object.get("opts"), "serialized synth event opts")?,
        synth_name: required_json_string(
            object.get("synth_name"),
            "serialized synth event synth_name",
        )?,
        synth_opts: json_to_required_opt_map(
            object.get("synth_opts"),
            "serialized synth event synth_opts",
        )?,
        fx_chain: parse_serialized_fx_chain(object.get("fx_chain"))?,
    })
}

pub(crate) fn parse_serialized_fx_chain(
    value: Option<&JsonValue>,
) -> SynthResult<Vec<ScheduledFxPayload>> {
    let value = value.ok_or_else(|| {
        SynthError::new("serialized synth event is missing required key \"fx_chain\".")
    })?;
    let handles = value
        .as_array()
        .ok_or_else(|| SynthError::new("serialized synth event fx_chain must be a list."))?;
    if handles.len() > MAX_FX_CHAIN_DEPTH {
        return Err(SynthError::new(format!(
            "serialized synth FX chain depth {} exceeds the limit of {MAX_FX_CHAIN_DEPTH}.",
            handles.len()
        )));
    }
    handles
        .iter()
        .map(|value| {
            let object = value
                .as_object()
                .ok_or_else(|| SynthError::new("serialized synth FX handle must be an object."))?;
            validate_json_object_keys(
                object,
                &["id", "name", "opts"],
                "serialized synth FX handle",
            )?;
            Ok(ScheduledFxPayload {
                id: required_json_u64(object.get("id"), "serialized synth FX handle id")?,
                name: required_json_string(object.get("name"), "serialized synth FX handle name")?,
                opts: json_to_required_opt_map(
                    object.get("opts"),
                    "serialized synth FX handle opts",
                )?,
            })
        })
        .collect()
}

pub(crate) fn parse_serialized_controls(
    value: Option<&JsonValue>,
) -> SynthResult<Vec<ScheduledControlPayload>> {
    let value = value.ok_or_else(|| {
        SynthError::new("serialized synth physical plan is missing required key \"controls\".")
    })?;
    let controls = value.as_array().ok_or_else(|| {
        SynthError::new("serialized synth physical plan controls must be a list.")
    })?;
    if controls.len() > MAX_PLAN_CONTROLS {
        return Err(SynthError::new(format!(
            "serialized synth plan control count {} exceeds the limit of {MAX_PLAN_CONTROLS}.",
            controls.len()
        )));
    }
    controls
        .iter()
        .map(|value| {
            let object = value
                .as_object()
                .ok_or_else(|| SynthError::new("serialized synth control must be an object."))?;
            validate_json_object_keys(
                object,
                &[
                    "target_instance",
                    "target_id",
                    "time_seconds",
                    "opts",
                    "order",
                ],
                "serialized synth control",
            )?;
            Ok(ScheduledControlPayload {
                target_instance_key: json_identity_key(required_json_value(
                    object.get("target_instance"),
                    "serialized synth control target_instance",
                )?)?,
                target_id: required_json_u64(
                    object.get("target_id"),
                    "serialized synth control target_id",
                )?,
                time_seconds: required_json_f64(
                    object.get("time_seconds"),
                    "serialized synth control time_seconds",
                )?,
                opts: json_to_required_opt_map(
                    object.get("opts"),
                    "serialized synth control opts",
                )?,
                order: required_json_u64(object.get("order"), "serialized synth control order")?,
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
            seed: self.seed,
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
    json_to_synth_value_at_depth(value, 0)
}

fn json_to_synth_value_at_depth(value: &JsonValue, depth: usize) -> SynthResult<SynthValue> {
    if depth > MAX_VALUE_DEPTH {
        return Err(SynthError::new(format!(
            "serialized synth value nesting exceeds the limit of {MAX_VALUE_DEPTH}."
        )));
    }
    match value {
        JsonValue::Null => Ok(SynthValue::None),
        JsonValue::Bool(value) => Ok(SynthValue::Bool(*value)),
        JsonValue::Number(value) => value
            .as_f64()
            .filter(|value| value.is_finite())
            .map(SynthValue::Float)
            .ok_or_else(|| {
                SynthError::new(
                    "serialized synth numeric value must be finite and representable as f64.",
                )
            }),
        JsonValue::String(value) => Ok(SynthValue::String(value.clone())),
        JsonValue::Array(values) => values
            .iter()
            .map(|value| json_to_synth_value_at_depth(value, depth + 1))
            .collect::<SynthResult<Vec<_>>>()
            .map(SynthValue::List),
        JsonValue::Object(mapping) => {
            let mut output = OptMap::with_capacity(mapping.len());
            for (key, value) in mapping {
                if key.is_empty() {
                    return Err(SynthError::new(
                        "serialized synth mappings cannot contain empty keys.",
                    ));
                }
                output.insert(key.clone(), json_to_synth_value_at_depth(value, depth + 1)?);
            }
            Ok(SynthValue::Dict(output))
        }
    }
}

pub(crate) fn json_to_required_opt_map(
    value: Option<&JsonValue>,
    label: &str,
) -> SynthResult<OptMap> {
    let value = required_json_value(value, label)?;
    let object = value
        .as_object()
        .ok_or_else(|| SynthError::new(format!("{label} must be an object.")))?;
    let mut output = OptMap::with_capacity(object.len());
    for (key, value) in object {
        if key.is_empty() {
            return Err(SynthError::new(format!(
                "{label} cannot contain an empty key."
            )));
        }
        output.insert(key.clone(), json_to_synth_value(value)?);
    }
    Ok(output)
}

pub(crate) fn json_identity_key(value: &JsonValue) -> SynthResult<String> {
    json_identity_key_at_depth(value, 0)
}

fn json_identity_key_at_depth(value: &JsonValue, depth: usize) -> SynthResult<String> {
    if depth > MAX_VALUE_DEPTH {
        return Err(SynthError::new(format!(
            "serialized synth identity nesting exceeds the limit of {MAX_VALUE_DEPTH}."
        )));
    }
    match value {
        JsonValue::Null | JsonValue::Bool(_) | JsonValue::String(_) => Ok(value.to_string()),
        JsonValue::Number(number) if number.as_i64().is_some() || number.as_u64().is_some() => {
            Ok(value.to_string())
        }
        JsonValue::Array(values) => {
            let parts = values
                .iter()
                .map(|value| json_identity_key_at_depth(value, depth + 1))
                .collect::<SynthResult<Vec<_>>>()?;
            Ok(format!("[{}]", parts.join(",")))
        }
        JsonValue::Number(_) => Err(SynthError::new(
            "serialized synth identity values must use integer numbers.",
        )),
        JsonValue::Object(_) => Err(SynthError::new(
            "serialized synth identity values do not support mappings.",
        )),
    }
}

pub(crate) fn validate_json_object_keys(
    object: &serde_json::Map<String, JsonValue>,
    allowed: &[&str],
    label: &str,
) -> SynthResult<()> {
    let mut unexpected: Vec<&str> = object
        .keys()
        .map(String::as_str)
        .filter(|key| !allowed.contains(key))
        .collect();
    unexpected.sort_unstable();
    if unexpected.is_empty() {
        return Ok(());
    }
    Err(SynthError::new(format!(
        "{label} contains unsupported key(s): {}.",
        unexpected.join(", ")
    )))
}

pub(crate) fn required_json_value<'a>(
    value: Option<&'a JsonValue>,
    label: &str,
) -> SynthResult<&'a JsonValue> {
    value.ok_or_else(|| SynthError::new(format!("{label} is required.")))
}

pub(crate) fn required_json_string(value: Option<&JsonValue>, label: &str) -> SynthResult<String> {
    required_json_value(value, label)?
        .as_str()
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| SynthError::new(format!("{label} must be a non-empty string.")))
}

pub(crate) fn required_json_f64(value: Option<&JsonValue>, label: &str) -> SynthResult<f64> {
    required_json_value(value, label)?
        .as_f64()
        .filter(|value| value.is_finite())
        .ok_or_else(|| SynthError::new(format!("{label} must be a finite number.")))
}

pub(crate) fn required_json_u64(value: Option<&JsonValue>, label: &str) -> SynthResult<u64> {
    required_json_value(value, label)?
        .as_u64()
        .ok_or_else(|| SynthError::new(format!("{label} must be a non-negative integer.")))
}

pub(crate) fn optional_json_u64(
    value: Option<&JsonValue>,
    default: u64,
    label: &str,
) -> SynthResult<u64> {
    match value {
        Some(value) => value
            .as_u64()
            .ok_or_else(|| SynthError::new(format!("{label} must be a non-negative integer."))),
        None => Ok(default),
    }
}
