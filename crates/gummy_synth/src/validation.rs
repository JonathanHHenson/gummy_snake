use super::*;

pub(crate) const MAX_SERIALIZED_PLAN_BYTES: usize = 16 * 1024 * 1024;
pub(crate) const MAX_DECOMPRESSED_PLAN_BYTES: usize = 64 * 1024 * 1024;
pub(crate) const MAX_PLAN_EVENTS: usize = 100_000;
pub(crate) const MAX_PLAN_CONTROLS: usize = 100_000;
pub(crate) const MAX_FX_CHAIN_DEPTH: usize = 64;
pub(crate) const MAX_VALUE_DEPTH: usize = 64;
pub(crate) const MAX_VALUE_ITEMS: usize = 1_000_000;
pub(crate) const MAX_SAMPLE_RATE: u32 = 384_000;
pub(crate) const MAX_OUTPUT_FRAMES: usize = 50_000_000;

pub(crate) fn validate_sample_rate(sample_rate: u32) -> SynthResult<()> {
    if sample_rate == 0 || sample_rate > MAX_SAMPLE_RATE {
        return Err(SynthError::new(format!(
            "synth sample rate must be in 1..={MAX_SAMPLE_RATE} Hz; got {sample_rate}."
        )));
    }
    Ok(())
}

pub(crate) fn checked_frame_count(
    seconds: f64,
    sample_rate: u32,
    label: &str,
    minimum: usize,
) -> SynthResult<usize> {
    if !seconds.is_finite() || seconds < 0.0 {
        return Err(SynthError::new(format!(
            "{label} must be finite and non-negative; got {seconds}."
        )));
    }
    validate_sample_rate(sample_rate)?;
    let frames = (seconds * sample_rate as f64).ceil();
    if !frames.is_finite() || frames > MAX_OUTPUT_FRAMES as f64 {
        return Err(SynthError::new(format!(
            "{label} exceeds the synth output budget of {MAX_OUTPUT_FRAMES} frames."
        )));
    }
    Ok((frames as usize).max(minimum))
}

pub(crate) fn checked_extended_frame_count(
    base_frames: usize,
    extra_seconds: f64,
    sample_rate: u32,
    label: &str,
) -> SynthResult<usize> {
    if base_frames > MAX_OUTPUT_FRAMES {
        return Err(SynthError::new(format!(
            "{label} input exceeds the synth output budget of {MAX_OUTPUT_FRAMES} frames."
        )));
    }
    let extra_frames = checked_frame_count(extra_seconds, sample_rate, label, 0)?;
    base_frames
        .checked_add(extra_frames)
        .filter(|value| *value <= MAX_OUTPUT_FRAMES)
        .ok_or_else(|| {
            SynthError::new(format!(
                "{label} exceeds the synth output budget of {MAX_OUTPUT_FRAMES} frames."
            ))
        })
}

pub(crate) fn validate_event(event: &EventPayload, sample_rate: u32) -> SynthResult<()> {
    validate_sample_rate(sample_rate)?;
    if !matches!(event.kind.as_str(), "play" | "sample") {
        return Err(SynthError::new(format!(
            "unsupported synth event kind {:?}; expected 'play' or 'sample'.",
            event.kind
        )));
    }
    validate_finite_non_negative(event.time_seconds, "synth event time_seconds")?;
    let mut item_count = 0usize;
    validate_synth_value(&event.value, 0, &mut item_count, "synth event value")?;
    validate_opt_map(&event.opts, 0, &mut item_count, "synth event opts")?;
    validate_opt_map(
        &event.synth_opts,
        0,
        &mut item_count,
        "synth event synth_opts",
    )?;
    if event.kind == "play" && synth_kind(&event.synth_name) == SynthKind::Unknown {
        return Err(SynthError::new(format!(
            "unsupported primitive synth {:?}; public synths must expand to a documented '_' primitive before Rust execution.",
            event.synth_name
        )));
    }
    if event.kind == "sample" {
        if let SynthValue::List(values) = &event.value {
            if values.len() != 1 {
                return Err(SynthError::new(
                    "serialized sample events do not support positional filter values; use documented sample options or an explicit FX chain.",
                ));
            }
        }
    }
    if event.fx_chain.len() > MAX_FX_CHAIN_DEPTH {
        return Err(SynthError::new(format!(
            "synth FX chain depth {} exceeds the limit of {MAX_FX_CHAIN_DEPTH}.",
            event.fx_chain.len()
        )));
    }
    for fx in &event.fx_chain {
        validate_fx_options(&fx.name, &fx.opts)?;
        validate_opt_map(&fx.opts, 0, &mut item_count, "synth FX opts")?;
    }
    if event.controls.len() > MAX_PLAN_CONTROLS {
        return Err(SynthError::new(format!(
            "synth event control count {} exceeds the limit of {MAX_PLAN_CONTROLS}.",
            event.controls.len()
        )));
    }
    for control in &event.controls {
        validate_finite_non_negative(control.time_seconds, "synth control time_seconds")?;
        validate_opt_map(&control.opts, 0, &mut item_count, "synth control opts")?;
    }
    Ok(())
}

pub(crate) fn validate_fx_name(name: &str) -> SynthResult<()> {
    let key = name.trim_start_matches(':').to_ascii_lowercase();
    let primitive_key = key.strip_prefix('_').unwrap_or(key.as_str());
    if matches!(
        primitive_key,
        "chain"
            | "bitcrusher"
            | "krush"
            | "reverb"
            | "gverb"
            | "level"
            | "echo"
            | "slicer"
            | "panslicer"
            | "pan_slicer"
            | "wobble"
            | "ixi_techno"
            | "compressor"
            | "whammy"
            | "rlpf"
            | "nrlpf"
            | "rhpf"
            | "nrhpf"
            | "hpf"
            | "highpass"
            | "nhpf"
            | "lpf"
            | "lowpass"
            | "nlpf"
            | "normaliser"
            | "normalizer"
            | "distortion"
            | "pan"
            | "bpf"
            | "nbpf"
            | "rbpf"
            | "nrbpf"
            | "band_eq"
            | "tanh"
            | "pitch_shift"
            | "ring_mod"
            | "octaver"
            | "vowel"
            | "flanger"
    ) {
        return Ok(());
    }
    Err(SynthError::new(format!(
        "unsupported synth FX name {name:?}; no dry-pass fallback is available."
    )))
}

pub(crate) fn validate_finite_non_negative(value: f64, label: &str) -> SynthResult<()> {
    if !value.is_finite() || value < 0.0 {
        return Err(SynthError::new(format!(
            "{label} must be finite and non-negative; got {value}."
        )));
    }
    Ok(())
}

pub(crate) fn validate_synth_value(
    value: &SynthValue,
    depth: usize,
    item_count: &mut usize,
    label: &str,
) -> SynthResult<()> {
    if depth > MAX_VALUE_DEPTH {
        return Err(SynthError::new(format!(
            "{label} nesting exceeds the limit of {MAX_VALUE_DEPTH}."
        )));
    }
    *item_count = item_count.checked_add(1).ok_or_else(|| {
        SynthError::new(format!(
            "{label} item count overflowed the validation budget."
        ))
    })?;
    if *item_count > MAX_VALUE_ITEMS {
        return Err(SynthError::new(format!(
            "{label} item count exceeds the limit of {MAX_VALUE_ITEMS}."
        )));
    }
    match value {
        SynthValue::Float(number) if !number.is_finite() => Err(SynthError::new(format!(
            "{label} contains a non-finite numeric value."
        ))),
        SynthValue::List(values) => {
            for value in values {
                validate_synth_value(value, depth + 1, item_count, label)?;
            }
            Ok(())
        }
        SynthValue::Dict(mapping) => validate_opt_map(mapping, depth + 1, item_count, label),
        _ => Ok(()),
    }
}

pub(crate) fn validate_opt_map(
    mapping: &OptMap,
    depth: usize,
    item_count: &mut usize,
    label: &str,
) -> SynthResult<()> {
    if depth > MAX_VALUE_DEPTH {
        return Err(SynthError::new(format!(
            "{label} nesting exceeds the limit of {MAX_VALUE_DEPTH}."
        )));
    }
    for (key, value) in mapping {
        if key.is_empty() {
            return Err(SynthError::new(format!(
                "{label} contains an empty option key."
            )));
        }
        validate_synth_value(value, depth + 1, item_count, label)?;
    }
    Ok(())
}
