use super::*;

pub(crate) fn note_values(value: &SynthValue) -> SynthResult<Vec<Option<f64>>> {
    match value {
        SynthValue::List(values) => values.iter().map(note).collect(),
        other => Ok(vec![note(other)?]),
    }
}

pub(crate) fn note(value: &SynthValue) -> SynthResult<Option<f64>> {
    match value {
        SynthValue::None => Ok(None),
        SynthValue::Bool(false) => Ok(None),
        SynthValue::Bool(true) => Ok(Some(60.0)),
        SynthValue::Float(value) => Ok(Some(*value)),
        SynthValue::String(value) => note_name(value),
        SynthValue::List(_) | SynthValue::Dict(_) => Err(SynthError::new(
            "Nested note values are not supported by the Rust synth renderer.",
        )),
    }
}

pub(crate) fn note_name(value: &str) -> SynthResult<Option<f64>> {
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
            return Err(SynthError::new(format!(
                "Unsupported note name: {value:?}."
            )))
        }
    };
    let octave = if octave_text.is_empty() {
        4
    } else {
        octave_text
            .parse::<i32>()
            .map_err(|_| SynthError::new(format!("Unsupported note name: {value:?}.")))?
    };
    Ok(Some(((octave + 1) * 12 + offset) as f64))
}

pub(crate) fn note_frequency(midi: f64) -> f64 {
    440.0 * 2.0_f64.powf((midi - 69.0) / 12.0)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn adsr_level(
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

pub(crate) fn shaped_interpolate(start: f64, end: f64, position: f64, curve: i32) -> f64 {
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

pub(crate) fn exponential_curve_amount(start: f64, end: f64, t: f64) -> f64 {
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

pub(crate) fn decay_level_opt(opts: &OptMap, sustain_level: f64) -> f64 {
    let raw = float_opt(opts, "decay_level", -1.0);
    if raw < 0.0 {
        sustain_level
    } else {
        raw.max(0.0)
    }
}

pub(crate) fn default_synth_envelope(_kind: SynthKind) -> (f64, f64, f64, f64) {
    (0.0, 0.0, 0.0, 1.0)
}

pub(crate) fn natural_synth_tail(_kind: SynthKind, _opts: &OptMap) -> f64 {
    0.01
}

pub(crate) fn render_no_source_event(
    opts: &OptMap,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let attack = float_opt(opts, "attack", 0.0).max(0.0);
    let decay = float_opt(opts, "decay", 0.0).max(0.0);
    let sustain = float_opt(opts, "sustain", 0.0).max(0.0);
    let release = float_opt(opts, "release", 0.01).max(0.01);
    let count = checked_frame_count(
        attack + decay + sustain + release,
        sample_rate,
        "silent synth event envelope duration",
        1,
    )?;
    Ok((vec![0.0; count], vec![0.0; count]))
}

pub(crate) fn synth_waveform(kind: SynthKind, _opts: &OptMap) -> &'static str {
    match kind {
        SynthKind::Saw => "saw",
        SynthKind::Pulse => "square",
        SynthKind::Tri => "triangle",
        _ => "sine",
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn synth_voice(
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

pub(crate) fn pulse_width_at(opts: &OptMap, elapsed: f64) -> f64 {
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

pub(crate) fn oscillator_value_with_width(
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

pub(crate) fn poly_blep(phase: f64, phase_delta: f64) -> f64 {
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

pub(crate) fn noise_voice(
    kind: SynthKind,
    sample_index: usize,
    note_index: usize,
    node_id: u64,
) -> f64 {
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

pub(crate) fn stochastic_identity(plan_seed: u64, node_id: u64) -> u64 {
    let mut value = plan_seed ^ node_id.wrapping_add(0x9e37_79b9_7f4a_7c15);
    value = (value ^ (value >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    value = (value ^ (value >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    value ^ (value >> 31)
}

pub(crate) fn deterministic_noise(sample_index: usize, note_index: usize, node_id: u64) -> f64 {
    let identity = node_id as f64;
    let x = (sample_index as f64 * 12.9898 + note_index as f64 * 78.233 + identity * 37.719).sin()
        * 43_758.545_3;
    (x - x.floor()) * 2.0 - 1.0
}

pub(crate) fn modulated_midi_note(
    _kind: SynthKind,
    midi_note: f64,
    _opts: &OptMap,
    _elapsed: f64,
) -> f64 {
    midi_note
}
