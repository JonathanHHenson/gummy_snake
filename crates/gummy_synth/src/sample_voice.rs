use super::*;

pub(crate) fn render_sample_event(
    event: &EventPayload,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let mut opts = event.synth_opts.clone();
    opts.extend(event.opts.clone());
    render_sample_event_with_opts(&event.value, &opts, sample_rate)
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
