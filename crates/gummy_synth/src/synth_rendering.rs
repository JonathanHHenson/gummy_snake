use super::*;

pub(crate) fn render_dry_event(
    event: &EventPayload,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    if event.kind == "sample" {
        render_sample_event(event, sample_rate)
    } else {
        render_synth_event(event, sample_rate)
    }
}

pub(crate) fn render_event(
    event: &EventPayload,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let (mut left, mut right) = render_dry_event(event, sample_rate)?;
    for fx in event.fx_chain.iter().rev() {
        let (new_left, new_right) = apply_fx(
            &fx.name,
            left,
            right,
            &fx.opts,
            sample_rate,
            event.time_seconds,
        );
        left = new_left;
        right = new_right;
    }
    Ok((left, right))
}

/// Render one typed event to a stereo WAV payload.
pub fn render_event_wav(event: &EventPayload, sample_rate: u32) -> SynthResult<Vec<u8>> {
    let (left, right) = render_event(event, sample_rate)?;
    let (left, right) = output_limit_pair(&left, &right, sample_rate);
    Ok(stereo_wav_bytes(&left, &right, sample_rate))
}

pub(crate) fn render_synth_event(
    event: &EventPayload,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let kind = synth_kind(&event.synth_name);
    let mut opts = event.synth_opts.clone();
    opts.extend(event.opts.clone());

    if matches!(kind, SynthKind::Silence) {
        return Ok(render_no_source_event(&opts, sample_rate));
    }
    if matches!(kind, SynthKind::Layered) {
        return render_layered_synth_event(event, &opts, sample_rate);
    }

    let note_source = opts.get("note").unwrap_or(&event.value);
    let notes = note_values(note_source)?;
    if notes.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }

    let (default_attack, default_decay, default_sustain, default_release) =
        default_synth_envelope(kind);
    let attack = float_opt(&opts, "attack", default_attack).max(0.0);
    let decay = float_opt(&opts, "decay", default_decay).max(0.0);
    let sustain = float_opt(&opts, "sustain", default_sustain).max(0.0);
    let release = float_opt(&opts, "release", default_release).max(0.0);
    let natural_tail = natural_synth_tail(kind, &opts);
    let total_seconds = (attack + decay + sustain + release)
        .max(natural_tail)
        .max(0.01);
    let count = (total_seconds * sample_rate as f64).ceil() as usize;
    let amp = float_opt(&opts, "amp", 1.0).max(0.0) * synth_amp_fudge(kind, &opts);
    let env_curve = float_opt(&opts, "env_curve", 1.0).round() as i32;
    let attack_level = float_opt(&opts, "attack_level", 1.0).max(0.0);
    let sustain_level = float_opt(&opts, "sustain_level", 1.0).max(0.0);
    let decay_level = decay_level_opt(&opts, sustain_level);
    let waveform = synth_waveform(kind, &opts);
    let pan_base = float_opt(&opts, "pan", 0.0);
    let note_auto = automation(notes[0], "note", &event.controls, &opts, event.time_seconds);
    let cutoff_auto = automation(
        Some(float_opt(&opts, "cutoff", default_synth_cutoff(kind))),
        "cutoff",
        &event.controls,
        &opts,
        event.time_seconds,
    );
    let cutoff_is_automated = event
        .controls
        .iter()
        .any(|control| control.opts.contains_key("cutoff"));
    let pan_auto = automation(
        Some(pan_base),
        "pan",
        &event.controls,
        &opts,
        event.time_seconds,
    );
    let mut mono = Vec::with_capacity(count);
    let mut envelope_levels = Vec::with_capacity(count);
    let mut phases = vec![0.0; notes.len()];
    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed,
            attack,
            decay,
            sustain,
            release,
            attack_level,
            decay_level,
            sustain_level,
            env_curve,
        );
        let mut current_notes = notes.clone();
        if current_notes.len() == 1 {
            current_notes[0] = note_auto(elapsed);
        }
        let mut sample = 0.0;
        let mut active_voices = 0usize;
        for (note_index, midi_note) in current_notes.iter().enumerate() {
            let Some(midi_note) = midi_note else {
                continue;
            };
            let modulated_note = modulated_midi_note(kind, *midi_note, &opts, elapsed);
            let freq = note_frequency(modulated_note).max(0.0);
            let phase_delta = freq / sample_rate as f64;
            let voice = synth_voice(
                kind,
                waveform,
                phases[note_index],
                phase_delta,
                elapsed,
                level,
                index,
                note_index,
                &opts,
                event.node_id,
                sample_rate,
            );
            sample += voice;
            active_voices += 1;
            phases[note_index] = (phases[note_index] + phase_delta).rem_euclid(1.0);
        }
        if active_voices > 0 {
            sample /= active_voices as f64;
        }
        envelope_levels.push(level);
        mono.push(sample);
    }
    let (processed_left, processed_right) = apply_synth_post_processing(
        kind,
        mono.clone(),
        mono,
        &opts,
        sample_rate,
        &*cutoff_auto,
        cutoff_is_automated,
        Some(&envelope_levels),
    );
    let mut left = Vec::with_capacity(count);
    let mut right = Vec::with_capacity(count);
    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = envelope_levels.get(index).copied().unwrap_or(0.0);
        let pan = pan_auto(elapsed).unwrap_or(pan_base).clamp(-1.0, 1.0);
        let (left_gain, right_gain) = pan_gains(pan);
        left.push(processed_left.get(index).copied().unwrap_or(0.0) * level * amp * left_gain);
        right.push(processed_right.get(index).copied().unwrap_or(0.0) * level * amp * right_gain);
    }
    if bool_opt(&opts, "leak_dc", false) {
        (left, right) = leak_dc_pair(&left, &right);
    }
    Ok((left, right))
}

pub(crate) fn render_layered_synth_event(
    event: &EventPayload,
    opts: &OptMap,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let layers = layered_specs(opts);
    if layers.is_empty() {
        return Ok(render_no_source_event(opts, sample_rate));
    }

    let note_source = opts.get("note").unwrap_or(&event.value);
    let notes = note_values(note_source)?;
    if notes.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }

    let (default_attack, default_decay, default_sustain, default_release) =
        default_synth_envelope(SynthKind::Layered);
    let attack = float_opt(opts, "attack", default_attack).max(0.0);
    let decay = float_opt(opts, "decay", default_decay).max(0.0);
    let sustain = float_opt(opts, "sustain", default_sustain).max(0.0);
    let release = float_opt(opts, "release", default_release).max(0.0);
    let natural_tail = natural_synth_tail(SynthKind::Layered, opts);
    let total_seconds = (attack + decay + sustain + release)
        .max(natural_tail)
        .max(0.01);
    let count = (total_seconds * sample_rate as f64).ceil() as usize;
    let amp = float_opt(opts, "amp", 1.0).max(0.0) * synth_amp_fudge(SynthKind::Layered, opts);
    let env_curve = float_opt(opts, "env_curve", 1.0).round() as i32;
    let attack_level = float_opt(opts, "attack_level", 1.0).max(0.0);
    let sustain_level = float_opt(opts, "sustain_level", 1.0).max(0.0);
    let decay_level = decay_level_opt(opts, sustain_level);
    let pan_base = float_opt(opts, "pan", 0.0);
    let note_auto = automation(notes[0], "note", &event.controls, opts, event.time_seconds);
    let cutoff_auto = automation(
        Some(float_opt(
            opts,
            "cutoff",
            default_synth_cutoff(SynthKind::Layered),
        )),
        "cutoff",
        &event.controls,
        opts,
        event.time_seconds,
    );
    let cutoff_is_automated = event
        .controls
        .iter()
        .any(|control| control.opts.contains_key("cutoff"));
    let pan_auto = automation(
        Some(pan_base),
        "pan",
        &event.controls,
        opts,
        event.time_seconds,
    );
    let mut phases = vec![0.0; notes.len() * layers.len()];
    let mut mono = Vec::with_capacity(count);
    let mut envelope_levels = Vec::with_capacity(count);

    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = adsr_level(
            elapsed,
            attack,
            decay,
            sustain,
            release,
            attack_level,
            decay_level,
            sustain_level,
            env_curve,
        );
        let mut current_notes = notes.clone();
        if current_notes.len() == 1 {
            current_notes[0] = note_auto(elapsed);
        }
        let mut sample = 0.0;
        let mut active_base_notes = 0usize;
        for (note_index, midi_note) in current_notes.iter().enumerate() {
            let Some(midi_note) = midi_note else {
                continue;
            };
            active_base_notes += 1;
            for (layer_index, layer) in layers.iter().enumerate() {
                let phase_index = note_index * layers.len() + layer_index;
                let layer_note = *midi_note + layer.transpose;
                let modulated_note =
                    modulated_midi_note(layer.kind, layer_note, &layer.opts, elapsed);
                let freq = note_frequency(modulated_note).max(0.0);
                let phase_delta = freq / sample_rate as f64;
                let voice = synth_voice(
                    layer.kind,
                    layer.waveform,
                    phases[phase_index],
                    phase_delta,
                    elapsed,
                    level,
                    index,
                    phase_index,
                    &layer.opts,
                    event.node_id,
                    sample_rate,
                );
                sample += voice * layer.amp;
                phases[phase_index] = (phases[phase_index] + phase_delta).rem_euclid(1.0);
            }
        }
        if active_base_notes > 0 {
            sample /= active_base_notes as f64;
        }
        envelope_levels.push(level);
        mono.push(sample);
    }

    let (processed_left, processed_right) = apply_synth_post_processing(
        SynthKind::Layered,
        mono.clone(),
        mono,
        opts,
        sample_rate,
        &*cutoff_auto,
        cutoff_is_automated,
        Some(&envelope_levels),
    );
    let mut left = Vec::with_capacity(count);
    let mut right = Vec::with_capacity(count);
    for index in 0..count {
        let elapsed = index as f64 / sample_rate as f64;
        let level = envelope_levels.get(index).copied().unwrap_or(0.0);
        let pan = pan_auto(elapsed).unwrap_or(pan_base).clamp(-1.0, 1.0);
        let (left_gain, right_gain) = pan_gains(pan);
        left.push(processed_left.get(index).copied().unwrap_or(0.0) * level * amp * left_gain);
        right.push(processed_right.get(index).copied().unwrap_or(0.0) * level * amp * right_gain);
    }
    if bool_opt(opts, "leak_dc", false) {
        (left, right) = leak_dc_pair(&left, &right);
    }

    Ok((left, right))
}

pub(crate) fn layered_specs(opts: &OptMap) -> Vec<LayerSpec> {
    let Some(SynthValue::List(values)) = opts.get("layers") else {
        return Vec::new();
    };
    values
        .iter()
        .filter_map(|value| layer_spec(value, opts))
        .collect()
}

pub(crate) fn layer_spec(value: &SynthValue, base_opts: &OptMap) -> Option<LayerSpec> {
    let SynthValue::Dict(mapping) = value else {
        return None;
    };
    let wave = mapping.get("wave").and_then(value_as_str).unwrap_or("sine");
    let kind = synth_kind(&format!("_{}", wave.trim_start_matches('_')));
    let transpose = mapping
        .get("transpose")
        .and_then(value_as_f64)
        .unwrap_or(0.0);
    let amp = mapping.get("amp").and_then(value_as_f64).unwrap_or(1.0);
    let mut opts = base_opts.clone();
    opts.remove("layers");
    if let Some(SynthValue::Dict(layer_opts)) = mapping.get("opts") {
        opts.extend(layer_opts.clone());
    }
    Some(LayerSpec {
        kind,
        waveform: synth_waveform(kind, &opts),
        transpose,
        amp,
        opts,
    })
}
