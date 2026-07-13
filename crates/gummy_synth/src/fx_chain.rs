use super::*;

pub(crate) fn validate_fx_options(name: &str, opts: &OptMap) -> SynthResult<()> {
    validate_fx_name(name)?;
    let key = name.trim_start_matches(':').to_ascii_lowercase();
    let primitive_key = key.strip_prefix('_').unwrap_or(key.as_str());
    if primitive_key != "chain" {
        return Ok(());
    }
    let Some(SynthValue::List(ops)) = opts.get("ops") else {
        return Err(SynthError::new(
            "synth FX chain requires an 'ops' list; no dry-pass fallback is available.",
        ));
    };
    if ops.is_empty() {
        return Err(SynthError::new(
            "synth FX chain 'ops' cannot be empty; use the documented 'level' operation explicitly.",
        ));
    }
    for (index, op_value) in ops.iter().enumerate() {
        let op_opts = fx_op_map(op_value, index)?;
        let op_name = op_opts
            .get("op")
            .and_then(value_as_str)
            .filter(|name| !name.is_empty())
            .ok_or_else(|| {
                SynthError::new(format!(
                    "synth FX chain operation {index} requires a non-empty string 'op' key."
                ))
            })?;
        validate_fx_chain_operation(op_name, &op_opts)?;
    }
    Ok(())
}

pub(crate) fn validate_fx_chain_operation(name: &str, opts: &OptMap) -> SynthResult<()> {
    if !matches!(
        name,
        "level"
            | "decimator"
            | "krush_shape"
            | "distortion_shape"
            | "tanh_shape"
            | "filter"
            | "bandpass"
            | "band_eq"
            | "normalise"
            | "normalize"
            | "pan"
            | "reverb"
            | "gverb"
            | "echo"
            | "slicer"
            | "panslicer"
            | "wobble"
            | "ixi_techno"
            | "compressor"
            | "pitch_shift"
            | "whammy"
            | "ring_mod"
            | "octaver"
            | "vowel"
            | "flanger"
    ) {
        return Err(SynthError::new(format!(
            "unsupported synth FX chain operation {name:?}; no dry-pass fallback is available."
        )));
    }
    if name == "filter" {
        let kind = string_opt(opts, "kind", "low");
        if !matches!(
            kind.as_str(),
            "low" | "lpf" | "lowpass" | "high" | "hpf" | "highpass"
        ) {
            return Err(SynthError::new(format!(
                "unsupported synth FX chain filter kind {kind:?}."
            )));
        }
    }
    Ok(())
}

pub(crate) fn fx_chain(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let Some(SynthValue::List(ops)) = opts.get("ops") else {
        return Err(SynthError::new(
            "synth FX chain requires an 'ops' list; no dry-pass fallback is available.",
        ));
    };
    if ops.is_empty() {
        return Err(SynthError::new(
            "synth FX chain 'ops' cannot be empty; use the documented 'level' operation explicitly.",
        ));
    }
    let mut current_left = left.to_vec();
    let mut current_right = right.to_vec();
    for (index, op_value) in ops.iter().enumerate() {
        let op_opts = fx_op_map(op_value, index)?;
        let op_name = op_opts
            .get("op")
            .and_then(value_as_str)
            .filter(|name| !name.is_empty())
            .ok_or_else(|| {
                SynthError::new(format!(
                    "synth FX chain operation {index} requires a non-empty string 'op' key."
                ))
            })?
            .to_owned();
        let mut merged = merge_chain_op_opts(opts, &op_opts);
        if op_name == "reverb" {
            if let Some(mix) = opts.get("mix") {
                merged.insert("reverb_mix".to_owned(), mix.clone());
            }
        }
        let next = fx_chain_op(
            &op_name,
            &current_left,
            &current_right,
            &merged,
            sample_rate,
            start_time_seconds,
        )?;
        current_left = next.0;
        current_right = next.1;
    }
    Ok((current_left, current_right))
}

pub(crate) fn fx_op_map(value: &SynthValue, operation_index: usize) -> SynthResult<OptMap> {
    match value {
        SynthValue::Dict(map) => Ok(map.clone()),
        SynthValue::List(values) => {
            let mut map = OptMap::new();
            let Some(SynthValue::String(name)) = values.first() else {
                return Err(SynthError::new(format!(
                    "synth FX chain operation {operation_index} list form must start with an operation name string."
                )));
            };
            if values.len() % 2 == 0 {
                return Err(SynthError::new(format!(
                    "synth FX chain operation {operation_index} list form must contain key/value pairs after its name."
                )));
            }
            map.insert("op".to_owned(), SynthValue::String(name.clone()));
            let mut index = 1;
            while index + 1 < values.len() {
                let SynthValue::String(key) = &values[index] else {
                    return Err(SynthError::new(format!(
                        "synth FX chain operation {operation_index} option keys must be strings."
                    )));
                };
                if key.is_empty() {
                    return Err(SynthError::new(format!(
                        "synth FX chain operation {operation_index} option keys cannot be empty."
                    )));
                }
                map.insert(key.clone(), values[index + 1].clone());
                index += 2;
            }
            Ok(map)
        }
        _ => Err(SynthError::new(format!(
            "synth FX chain operation {operation_index} must be an object or list."
        ))),
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
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    validate_fx_chain_operation(name, opts)?;
    validate_fx_output_budget(name, left.len().max(right.len()), opts, sample_rate)?;
    let output = match name {
        "level" => (left.to_vec(), right.to_vec()),
        "decimator" => fx_bitcrusher(left, right, opts, sample_rate),
        "krush_shape" => fx_krush_shape(left, right, opts),
        "distortion_shape" => fx_distortion(left, right, opts),
        "tanh_shape" => fx_tanh(left, right, opts),
        "filter" => {
            let kind = match string_opt(opts, "kind", "low").as_str() {
                "low" | "lpf" | "lowpass" => FilterKind::Low,
                "high" | "hpf" | "highpass" => FilterKind::High,
                unsupported => {
                    return Err(SynthError::new(format!(
                        "unsupported synth FX chain filter kind {unsupported:?}."
                    )))
                }
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
        _ => {
            return Err(SynthError::new(format!(
                "unsupported synth FX chain operation {name:?}; no dry-pass fallback is available."
            )))
        }
    };
    if output.0.len().max(output.1.len()) > MAX_OUTPUT_FRAMES {
        return Err(SynthError::new(format!(
            "synth FX chain operation {name:?} output exceeds the synth output budget of {MAX_OUTPUT_FRAMES} frames."
        )));
    }
    Ok(output)
}
