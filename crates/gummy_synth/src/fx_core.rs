use super::*;

pub(crate) fn apply_fx(
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
pub(crate) enum FilterKind {
    Low,
    High,
}

pub(crate) fn fx_chain(
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
        );
        current_left = next.0;
        current_right = next.1;
    }
    (current_left, current_right)
}

pub(crate) fn fx_op_map(value: &SynthValue) -> OptMap {
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

pub(crate) fn merge_chain_op_opts(chain_opts: &OptMap, op_opts: &OptMap) -> OptMap {
    let mut merged = op_opts.clone();
    for (key, value) in chain_opts {
        if key == "ops" || is_fx_wrapper_opt(key) {
            continue;
        }
        merged.insert(key.clone(), value.clone());
    }
    merged
}

pub(crate) fn is_fx_wrapper_opt(key: &str) -> bool {
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

pub(crate) fn fx_chain_op(
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

pub(crate) fn default_fx_mix(name: &str) -> f64 {
    match name {
        "reverb" | "gverb" => 0.4,
        _ => 1.0,
    }
}

pub(crate) fn scale_samples(samples: &[f64], amount: f64) -> Vec<f64> {
    samples.iter().map(|sample| sample * amount).collect()
}

pub(crate) fn add_signal_pair(
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

pub(crate) fn blend_fx(
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

pub(crate) fn fx_bitcrusher(
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

pub(crate) fn fx_krush(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
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
