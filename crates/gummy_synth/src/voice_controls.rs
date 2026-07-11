use super::*;

#[allow(clippy::too_many_arguments)]
pub(crate) fn apply_synth_post_processing(
    kind: SynthKind,
    mut left: Vec<f64>,
    mut right: Vec<f64>,
    opts: &OptMap,
    sample_rate: u32,
    cutoff_auto: &(dyn Fn(f64) -> Option<f64> + Send + Sync),
    cutoff_is_automated: bool,
    envelope_levels: Option<&[f64]>,
) -> (Vec<f64>, Vec<f64>) {
    (left, right) = apply_pre_filter_shaping(left, right, opts, envelope_levels);
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

pub(crate) fn apply_pre_filter_shaping(
    mut left: Vec<f64>,
    mut right: Vec<f64>,
    opts: &OptMap,
    envelope_levels: Option<&[f64]>,
) -> (Vec<f64>, Vec<f64>) {
    if bool_opt(opts, "pre_shape_normalise", false) || bool_opt(opts, "pre_shape_normalize", false)
    {
        let level = float_opt(opts, "pre_shape_level", 1.0).max(0.0);
        (left, right) = normalise_pair(&left, &right, level);
    }
    if bool_opt(opts, "pre_filter_env", false) {
        if let Some(envelope_levels) = envelope_levels {
            (left, right) = multiply_pair_by_envelope(&left, &right, envelope_levels);
        }
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

pub(crate) fn cutoff_envelope_enabled(opts: &OptMap) -> bool {
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

pub(crate) fn synth_cutoff_hz_at(
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

pub(crate) fn cutoff_envelope_level(kind: SynthKind, opts: &OptMap, elapsed: f64) -> f64 {
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

pub(crate) fn inherit_negative(value: f64, inherited: f64) -> f64 {
    if value < 0.0 {
        inherited.max(0.0)
    } else {
        value.max(0.0)
    }
}

pub(crate) fn default_synth_cutoff(kind: SynthKind) -> f64 {
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

pub(crate) fn default_synth_res(_kind: SynthKind) -> f64 {
    0.0
}

pub(crate) fn synth_amp_fudge(_kind: SynthKind, opts: &OptMap) -> f64 {
    float_opt(opts, "amp_fudge", 1.0).max(0.0)
}

pub(crate) fn synth_normalise_enabled(kind: SynthKind, opts: &OptMap) -> bool {
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

pub(crate) fn default_synth_normalise(_kind: SynthKind) -> bool {
    false
}

pub(crate) fn automation(
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
