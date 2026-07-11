use super::*;

pub(crate) fn smooth_modulated_value(
    previous: f64,
    target: f64,
    opts: &OptMap,
    sample_rate: u32,
) -> f64 {
    let smooth = float_opt(opts, "smooth", 0.0)
        .max(float_opt(opts, "smooth_up", 0.0))
        .max(float_opt(opts, "smooth_down", 0.0));
    let alpha = smoothing_alpha(smooth, sample_rate);
    previous + (target - previous) * alpha
}

pub(crate) fn lfo_amount_from_opts(
    opts: &OptMap,
    wave: i32,
    elapsed_seconds: f64,
    phase_seconds: f64,
) -> f64 {
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

pub(crate) fn lfo_amount(
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

pub(crate) fn smoothing_alpha(seconds: f64, sample_rate: u32) -> f64 {
    if seconds <= 0.0 {
        1.0
    } else {
        (1.0 / (seconds * sample_rate as f64)).clamp(0.0001, 1.0)
    }
}

pub(crate) fn modulated_lowpass_pair(
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

pub(crate) fn filter_samples(
    samples: &[f64],
    cutoff_hz: f64,
    sample_rate: u32,
    kind: FilterKind,
    resonance: f64,
) -> Vec<f64> {
    let (q, output_gain) = if resonance > 0.0 {
        let rq = sonic_filter_rq(resonance);
        (1.0 / rq, resonant_output_gain(rq))
    } else {
        (FRAC_1_SQRT_2, 1.0)
    };
    let mut output = biquad_filter_samples(samples, cutoff_hz, sample_rate, kind, q);
    if output_gain != 1.0 {
        output = scale_samples(&output, output_gain);
    }
    output
}

pub(crate) fn sonic_filter_rq(public_res: f64) -> f64 {
    (1.0 - public_res.clamp(0.0, 0.99)).clamp(0.001, 1.0)
}

pub(crate) fn resonant_output_gain(rq: f64) -> f64 {
    rq.clamp(0.001, 1.0).powf(0.25).clamp(0.45, 1.0)
}

pub(crate) fn resonant_emphasis(source: &[f64], filtered: &[f64], resonance: f64) -> Vec<f64> {
    source
        .iter()
        .zip(filtered.iter())
        .map(|(source, filtered)| filtered + (source - filtered) * resonance * 0.35)
        .collect()
}

pub(crate) fn normalise_pair(left: &[f64], right: &[f64], level: f64) -> (Vec<f64>, Vec<f64>) {
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

pub(crate) fn multiply_pair_by_envelope(
    left: &[f64],
    right: &[f64],
    envelope_levels: &[f64],
) -> (Vec<f64>, Vec<f64>) {
    let len = left.len().max(right.len());
    let mut out_left = Vec::with_capacity(len);
    let mut out_right = Vec::with_capacity(len);
    for index in 0..len {
        let level = envelope_levels.get(index).copied().unwrap_or(0.0);
        out_left.push(left.get(index).copied().unwrap_or(0.0) * level);
        out_right.push(right.get(index).copied().unwrap_or(0.0) * level);
    }
    (out_left, out_right)
}

pub(crate) fn leak_dc_pair(left: &[f64], right: &[f64]) -> (Vec<f64>, Vec<f64>) {
    (leak_dc(left), leak_dc(right))
}

pub(crate) fn leak_dc(samples: &[f64]) -> Vec<f64> {
    let coefficient = 0.995;
    let mut previous_input = 0.0;
    let mut previous_output = 0.0;
    let mut output = Vec::with_capacity(samples.len());
    for sample in samples {
        let filtered = sample - previous_input + coefficient * previous_output;
        previous_input = *sample;
        previous_output = filtered;
        output.push(filtered);
    }
    output
}

pub(crate) fn pitch_shift_to_len(samples: &[f64], ratio: f64) -> Vec<f64> {
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

pub(crate) fn sample_antialias_enabled(opts: &OptMap) -> bool {
    bool_opt(
        opts,
        "anti_alias",
        bool_opt(opts, "antialias", bool_opt(opts, "sample_antialias", true)),
    )
}

pub(crate) fn anti_alias_sample_segment(
    left: Vec<f64>,
    right: Vec<f64>,
    playback_rate: f64,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    if playback_rate <= 1.0 || left.is_empty() || right.is_empty() {
        return (left, right);
    }
    let nyquist = sample_rate as f64 * 0.5;
    let cutoff_hz = (nyquist * 0.9 / playback_rate.sqrt()).clamp(20.0, nyquist * 0.9);
    if cutoff_hz >= nyquist * 0.88 {
        return (left, right);
    }
    (
        lowpass(&left, cutoff_hz, sample_rate),
        lowpass(&right, cutoff_hz, sample_rate),
    )
}

pub(crate) fn smooth_high_rate_sample_output(
    left: Vec<f64>,
    right: Vec<f64>,
    playback_rate: f64,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    if playback_rate <= 2.0 || left.is_empty() || right.is_empty() {
        return (left, right);
    }
    let nyquist = sample_rate as f64 * 0.5;
    let max_cutoff = nyquist * 0.9;
    let min_cutoff = 4_000.0_f64.min(max_cutoff * 0.5).max(20.0);
    let cutoff_hz = (nyquist * 0.9 / playback_rate.powf(0.1)).clamp(min_cutoff, max_cutoff);
    if cutoff_hz >= nyquist * 0.88 {
        return (left, right);
    }
    (
        lowpass(&left, cutoff_hz, sample_rate),
        lowpass(&right, cutoff_hz, sample_rate),
    )
}

pub(crate) fn sample_linear(samples: &[f64], position: f64) -> f64 {
    if samples.is_empty() {
        return 0.0;
    }
    let wrapped = position.rem_euclid(samples.len() as f64);
    let low = wrapped.floor() as usize;
    let high = (low + 1) % samples.len();
    let frac = wrapped - low as f64;
    samples[low] * (1.0 - frac) + samples[high] * frac
}

pub(crate) fn sample_linear_clamped(samples: &[f64], position: f64) -> f64 {
    if samples.is_empty() {
        return 0.0;
    }
    let position = position.clamp(0.0, (samples.len() - 1) as f64);
    let low = position.floor() as usize;
    let high = (low + 1).min(samples.len() - 1);
    let frac = position - low as f64;
    samples[low] * (1.0 - frac) + samples[high] * frac
}

pub(crate) fn biquad_filter_samples(
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

pub(crate) fn lowpass(samples: &[f64], cutoff_hz: f64, sample_rate: u32) -> Vec<f64> {
    biquad_filter_samples(
        samples,
        cutoff_hz,
        sample_rate,
        FilterKind::Low,
        FRAC_1_SQRT_2,
    )
}

pub(crate) fn highpass(samples: &[f64], cutoff_hz: f64, sample_rate: u32) -> Vec<f64> {
    biquad_filter_samples(
        samples,
        cutoff_hz,
        sample_rate,
        FilterKind::High,
        FRAC_1_SQRT_2,
    )
}

pub(crate) fn pan_gains(pan: f64) -> (f64, f64) {
    let angle = (pan.clamp(-1.0, 1.0) + 1.0) * PI / 4.0;
    (angle.cos(), angle.sin())
}

pub(crate) fn balance2_sample(left: f64, right: f64, pan: f64) -> (f64, f64) {
    let pan = pan.clamp(-1.0, 1.0);
    if pan < 0.0 {
        (left + right * -pan, right * (1.0 + pan))
    } else {
        (left * (1.0 - pan), right + left * pan)
    }
}

pub(crate) fn balance2_pair(left: &[f64], right: &[f64], pan: f64) -> (Vec<f64>, Vec<f64>) {
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

pub(crate) fn octave_toggle(samples: &[f64], divisions: usize) -> Vec<f64> {
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

pub(crate) fn value_as_f64(value: &SynthValue) -> Option<f64> {
    match value {
        SynthValue::Bool(value) => Some(if *value { 1.0 } else { 0.0 }),
        SynthValue::Float(value) => Some(*value),
        SynthValue::String(value) => value.parse::<f64>().ok(),
        _ => None,
    }
}

pub(crate) fn value_as_str(value: &SynthValue) -> Option<&str> {
    match value {
        SynthValue::String(value) => Some(value),
        _ => None,
    }
}

pub(crate) fn float_opt(opts: &OptMap, name: &str, default: f64) -> f64 {
    opts.get(name).and_then(value_as_f64).unwrap_or(default)
}

pub(crate) fn string_opt(opts: &OptMap, name: &str, default: &str) -> String {
    match opts.get(name) {
        Some(SynthValue::String(value)) => value.clone(),
        Some(value) => value_as_f64(value)
            .map(|value| value.to_string())
            .unwrap_or_else(|| default.to_owned()),
        None => default.to_owned(),
    }
}

pub(crate) fn bool_opt(opts: &OptMap, name: &str, default: bool) -> bool {
    match opts.get(name) {
        Some(SynthValue::Bool(value)) => *value,
        Some(value) => value_as_f64(value)
            .map(|value| value != 0.0)
            .unwrap_or(default),
        None => default,
    }
}

pub(crate) const OUTPUT_LIMIT_CEILING: f64 = 0.99;
pub(crate) const OUTPUT_LIMIT_RELEASE_SECONDS: f64 = 0.01;
