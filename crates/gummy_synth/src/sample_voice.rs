use super::*;

pub(crate) fn render_sample_event(
    event: &EventPayload,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let mut opts = event.synth_opts.clone();
    opts.extend(event.opts.clone());
    if sample_controls_active(&event.controls) {
        render_sample_event_with_controls(
            &event.value,
            &opts,
            &event.controls,
            event.time_seconds,
            sample_rate,
        )
    } else {
        render_sample_event_with_opts(&event.value, &opts, sample_rate)
    }
}

fn sample_controls_active(controls: &[ControlPayload]) -> bool {
    controls.iter().any(|control| {
        control.opts.contains_key("amp")
            || control.opts.contains_key("pan")
            || control.opts.contains_key("rate")
    })
}

fn sorted_sample_controls(controls: &[ControlPayload]) -> Vec<ControlPayload> {
    let mut sorted = controls.to_vec();
    sorted.sort_by(|left, right| left.time_seconds.total_cmp(&right.time_seconds));
    sorted
}

fn sample_automation(
    initial: f64,
    name: &str,
    controls: &[ControlPayload],
    opts: &OptMap,
    event_time: f64,
    sample_rate: u32,
) -> Box<dyn Fn(f64) -> f64 + Send + Sync> {
    let slide_default = float_opt(opts, &format!("{name}_slide"), 0.0);
    let mut targets = Vec::new();
    for control in sorted_sample_controls(controls) {
        let Some(target) = control.opts.get(name).and_then(value_as_f64) else {
            continue;
        };
        let slide = control
            .opts
            .get(&format!("{name}_slide"))
            .and_then(value_as_f64)
            .unwrap_or(slide_default);
        let time = ((control.time_seconds - event_time).max(0.0) * sample_rate as f64).round()
            / sample_rate as f64;
        if targets
            .last()
            .is_some_and(|(last_time, _, _)| *last_time == time)
        {
            targets.pop();
        }
        targets.push((time, slide, target));
    }

    let mut points = Vec::with_capacity(targets.len());
    let mut value = initial;
    for (time, slide, target) in targets {
        if let Some((previous_time, previous_start, previous_target, previous_slide)) =
            points.last().copied()
        {
            value = if previous_slide <= 0.0 || time >= previous_time + previous_slide {
                previous_target
            } else {
                let t = (time - previous_time) / previous_slide;
                previous_start + (previous_target - previous_start) * t
            };
        }
        points.push((time, value, target, slide));
    }
    Box::new(move |elapsed| {
        let Some((control_time, start, target, slide)) = points
            .iter()
            .rev()
            .find(|(control_time, _, _, _)| elapsed >= *control_time)
        else {
            return initial;
        };
        if *slide <= 0.0 || elapsed >= control_time + slide {
            *target
        } else {
            let t = (elapsed - control_time) / slide;
            start + (target - start) * t
        }
    })
}

fn sample_playback_rate(opts: &OptMap, source: &SampleSource) -> f64 {
    let mut rate = float_opt(opts, "rate", 1.0);
    if opts.contains_key("rpitch") {
        rate *= 2.0_f64.powf(float_opt(opts, "rpitch", 0.0) / 12.0);
    }
    if opts.contains_key("pitch") {
        rate *= 2.0_f64.powf(float_opt(opts, "pitch", 0.0) / 12.0);
    }
    if opts.contains_key("beat_stretch") {
        rate = source.duration / float_opt(opts, "beat_stretch", 1.0).max(0.001);
    }
    rate
}

fn apply_sample_post_processing(
    mut left: Vec<f64>,
    mut right: Vec<f64>,
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let cutoff = float_opt(opts, "cutoff", 0.0);
    if cutoff > 0.0 && cutoff < 130.5 {
        let res = float_opt(opts, "res", 0.0).clamp(0.0, 0.99);
        let cutoff_hz = note_frequency(cutoff).max(20.0);
        left = filter_samples(&left, cutoff_hz, sample_rate, FilterKind::Low, res);
        right = filter_samples(&right, cutoff_hz, sample_rate, FilterKind::Low, res);
    }
    if float_opt(opts, "norm", 0.0) >= 0.5 {
        (left, right) = normalise_pair(&left, &right, 1.0);
    }
    if float_opt(opts, "compress", 0.0) >= 0.5 {
        (left, right) = fx_compressor(&left, &right, opts, sample_rate);
    }
    (left, right)
}

fn render_sample_event_with_controls(
    value: &SynthValue,
    opts: &OptMap,
    controls: &[ControlPayload],
    event_time: f64,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let source = sample_source(value, sample_rate)?;
    let start = float_opt(opts, "start", 0.0).clamp(0.0, 1.0);
    let finish = float_opt(opts, "finish", 1.0).clamp(0.0, 1.0);
    let rate = sample_playback_rate(opts, &source);
    if rate == 0.0 {
        return Err(SynthError::new("sample rate cannot be zero."));
    }
    let reverse = rate < 0.0 || start > finish;
    let low = start.min(finish);
    let high = start.max(finish);
    let source_len = source.len();
    if source_len == 0 {
        return Ok((Vec::new(), Vec::new()));
    }
    let start_index = (low * source_len as f64) as usize;
    let end_index = ((high * source_len as f64) as usize)
        .max(start_index + 1)
        .min(source_len);
    let mut segment_left = source.left[start_index..end_index].to_vec();
    let mut segment_right = source.right[start_index..end_index].to_vec();
    if reverse {
        segment_left.reverse();
        segment_right.reverse();
    }
    let pre_amp = float_opt(opts, "pre_amp", 1.0).max(0.0);
    if pre_amp != 1.0 {
        segment_left = scale_samples(&segment_left, pre_amp);
        segment_right = scale_samples(&segment_right, pre_amp);
    }

    if controls
        .iter()
        .filter_map(|control| control.opts.get("rate").and_then(value_as_f64))
        .any(|rate| rate <= 0.0)
    {
        return Err(SynthError::new(
            "sample rate controls must be positive; dynamic reverse playback is unsupported.",
        ));
    }
    let rate_auto = sample_automation(rate, "rate", controls, opts, event_time, sample_rate);
    let amp_auto = sample_automation(
        float_opt(opts, "amp", 1.0).max(0.0),
        "amp",
        controls,
        opts,
        event_time,
        sample_rate,
    );
    let pan_auto = sample_automation(
        float_opt(opts, "pan", 0.0),
        "pan",
        controls,
        opts,
        event_time,
        sample_rate,
    );
    let mut source_positions = Vec::new();
    let mut rates = Vec::new();
    let mut source_position = 0.0;
    while source_position < segment_left.len() as f64 {
        if source_positions.len() >= MAX_OUTPUT_FRAMES {
            return Err(SynthError::new(format!(
                "sample playback output exceeds the synth output budget of {MAX_OUTPUT_FRAMES} frames."
            )));
        }
        let elapsed = source_positions.len() as f64 / sample_rate as f64;
        let current_rate = rate_auto(elapsed);
        if current_rate == 0.0 {
            return Err(SynthError::new("sample rate control cannot be zero."));
        }
        source_positions.push(source_position);
        rates.push(current_rate.abs());
        source_position += current_rate.abs();
    }

    let attack = float_opt(opts, "attack", 0.0).max(0.0);
    let release = float_opt(opts, "release", 0.0).max(0.0);
    let sustain_opt = opts
        .get("sustain")
        .and_then(value_as_f64)
        .filter(|value| *value >= 0.0);
    let env_curve = float_opt(opts, "env_curve", 1.0).round() as i32;
    let total = source_positions.len() as f64 / sample_rate as f64;
    let sustain = sustain_opt.unwrap_or((total - attack - release).max(0.0));
    let mut left = Vec::with_capacity(source_positions.len());
    let mut right = Vec::with_capacity(source_positions.len());
    for (index, source_position) in source_positions.iter().enumerate() {
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed, attack, 0.0, sustain, release, 1.0, 1.0, 1.0, env_curve,
        );
        let amp = amp_auto(elapsed).max(0.0);
        let pan = pan_auto(elapsed);
        let dry_left = sample_linear_clamped(&segment_left, *source_position) * level * amp;
        let dry_right = sample_linear_clamped(&segment_right, *source_position) * level * amp;
        if source.stereo {
            let balanced = balance2_sample(dry_left, dry_right, pan);
            left.push(balanced.0);
            right.push(balanced.1);
        } else {
            let (left_gain, right_gain) = pan_gains(pan);
            left.push(dry_left * left_gain);
            right.push(dry_left * right_gain);
        }
    }

    if sample_antialias_enabled(opts) && rates.iter().copied().fold(0.0, f64::max) > 1.0 {
        let nyquist = sample_rate as f64 * 0.5;
        (left, right) = modulated_lowpass_pair(&left, &right, sample_rate, |index| {
            let rate = rates.get(index).copied().unwrap_or(1.0);
            (nyquist * 0.9 / rate.sqrt()).clamp(20.0, nyquist * 0.9)
        });
    }
    Ok(apply_sample_post_processing(left, right, opts, sample_rate))
}

pub(crate) fn render_sample_event_with_opts(
    value: &SynthValue,
    opts: &OptMap,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let source = sample_source(value, sample_rate)?;
    let start = float_opt(opts, "start", 0.0).clamp(0.0, 1.0);
    let finish = float_opt(opts, "finish", 1.0).clamp(0.0, 1.0);
    let mut rate = float_opt(opts, "rate", 1.0);
    if opts.contains_key("rpitch") {
        rate *= 2.0_f64.powf(float_opt(opts, "rpitch", 0.0) / 12.0);
    }
    if opts.contains_key("pitch") {
        rate *= 2.0_f64.powf(float_opt(opts, "pitch", 0.0) / 12.0);
    }
    if opts.contains_key("beat_stretch") {
        rate = source.duration / float_opt(opts, "beat_stretch", 1.0).max(0.001);
    }
    if rate == 0.0 {
        return Err(SynthError::new("sample rate cannot be zero."));
    }
    let reverse = rate < 0.0 || start > finish;
    let low = start.min(finish);
    let high = start.max(finish);
    let source_len = source.len();
    if source_len == 0 {
        return Ok((Vec::new(), Vec::new()));
    }
    let start_index = (low * source_len as f64) as usize;
    let end_index = ((high * source_len as f64) as usize).max(start_index + 1);
    let end_index = end_index.min(source_len);
    let mut segment_left = source.left[start_index..end_index].to_vec();
    let mut segment_right = source.right[start_index..end_index].to_vec();
    if reverse {
        segment_left.reverse();
        segment_right.reverse();
    }
    let pre_amp = float_opt(opts, "pre_amp", 1.0).max(0.0);
    if pre_amp != 1.0 {
        segment_left = scale_samples(&segment_left, pre_amp);
        segment_right = scale_samples(&segment_right, pre_amp);
    }
    let step = rate.abs();
    if sample_antialias_enabled(opts) && step > 1.0 {
        (segment_left, segment_right) =
            anti_alias_sample_segment(segment_left, segment_right, step, sample_rate);
    }
    let output_count_value = (segment_left.len() as f64 / step).ceil().max(1.0);
    if !output_count_value.is_finite() || output_count_value > MAX_OUTPUT_FRAMES as f64 {
        return Err(SynthError::new(format!(
            "sample playback output exceeds the synth output budget of {MAX_OUTPUT_FRAMES} frames."
        )));
    }
    let output_count = output_count_value as usize;
    let attack = float_opt(opts, "attack", 0.0).max(0.0);
    let release = float_opt(opts, "release", 0.0).max(0.0);
    let sustain_opt = opts
        .get("sustain")
        .and_then(value_as_f64)
        .filter(|value| *value >= 0.0);
    let amp = float_opt(opts, "amp", 1.0).max(0.0);
    let env_curve = float_opt(opts, "env_curve", 1.0).round() as i32;
    let pan = float_opt(opts, "pan", 0.0);
    let (left_gain, right_gain) = pan_gains(pan);
    let total = output_count as f64 / sample_rate as f64;
    let sustain_auto = (total - attack - release).max(0.0);
    let sustain = sustain_opt.unwrap_or(sustain_auto);
    let mut left = Vec::with_capacity(output_count);
    let mut right = Vec::with_capacity(output_count);
    for index in 0..output_count {
        let source_pos = index as f64 * step;
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed, attack, 0.0, sustain, release, 1.0, 1.0, 1.0, env_curve,
        );
        let dry_left = sample_linear_clamped(&segment_left, source_pos) * level * amp;
        let dry_right = sample_linear_clamped(&segment_right, source_pos) * level * amp;
        if source.stereo {
            let balanced = balance2_sample(dry_left, dry_right, pan);
            left.push(balanced.0);
            right.push(balanced.1);
        } else {
            left.push(dry_left * left_gain);
            right.push(dry_left * right_gain);
        }
    }
    if sample_antialias_enabled(opts) && step > 1.0 {
        (left, right) = smooth_high_rate_sample_output(left, right, step, sample_rate);
    }
    let cutoff = float_opt(opts, "cutoff", 0.0);
    if cutoff > 0.0 && cutoff < 130.5 {
        let res = float_opt(opts, "res", 0.0).clamp(0.0, 0.99);
        let cutoff_hz = note_frequency(cutoff).max(20.0);
        left = filter_samples(&left, cutoff_hz, sample_rate, FilterKind::Low, res);
        right = filter_samples(&right, cutoff_hz, sample_rate, FilterKind::Low, res);
    }
    if float_opt(opts, "norm", 0.0) >= 0.5 {
        (left, right) = normalise_pair(&left, &right, 1.0);
    }
    if float_opt(opts, "compress", 0.0) >= 0.5 {
        (left, right) = fx_compressor(&left, &right, opts, sample_rate);
    }
    Ok((left, right))
}
