use super::{average_abs_delta, max_abs_pair};
use crate::*;

#[test]
fn render_synth_event_produces_stereo_samples() {
    let mut opts = OptMap::new();
    opts.insert("release".to_owned(), SynthValue::Float(0.05));
    let event = EventPayload {
        node_id: 1,
        seed: 0,
        order: 0,
        kind: "play".to_owned(),
        time_seconds: 0.0,
        value: SynthValue::Float(60.0),
        opts,
        synth_name: "_saw".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    };

    let (left, right) = render_event(&event, 8_000).expect("event renders");

    assert!(!left.is_empty());
    assert_eq!(left.len(), right.len());
    assert!(left.iter().any(|sample| sample.abs() > 0.0));
}

#[test]
fn synth_cutoff_control_slides_filter_during_event() {
    let mut static_opts = OptMap::new();
    static_opts.insert("release".to_owned(), SynthValue::Float(0.15));
    static_opts.insert("cutoff".to_owned(), SynthValue::Float(40.0));
    static_opts.insert("cutoff_slide".to_owned(), SynthValue::Float(0.05));
    let static_event = EventPayload {
        node_id: 2,
        seed: 0,
        order: 0,
        kind: "play".to_owned(),
        time_seconds: 0.0,
        value: SynthValue::Float(48.0),
        opts: static_opts.clone(),
        synth_name: "_saw".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    };
    let mut control_opts = OptMap::new();
    control_opts.insert("cutoff".to_owned(), SynthValue::Float(120.0));
    let controlled_event = EventPayload {
        controls: vec![ControlPayload {
            time_seconds: 0.0,
            opts: control_opts,
        }],
        ..static_event.clone()
    };

    let (static_left, _) = render_event(&static_event, 8_000).expect("static event renders");
    let (controlled_left, _) =
        render_event(&controlled_event, 8_000).expect("controlled event renders");

    let static_energy = static_left.iter().map(|sample| sample.abs()).sum::<f64>();
    let controlled_energy = controlled_left
        .iter()
        .map(|sample| sample.abs())
        .sum::<f64>();
    assert!(controlled_energy > static_energy * 1.1);
}

#[test]
fn synth_normalise_runs_before_amp_fudge() {
    let mut base_opts = OptMap::new();
    base_opts.insert("attack".to_owned(), SynthValue::Float(0.0));
    base_opts.insert("decay".to_owned(), SynthValue::Float(0.0));
    base_opts.insert("sustain".to_owned(), SynthValue::Float(0.0));
    base_opts.insert("release".to_owned(), SynthValue::Float(0.05));
    base_opts.insert("normalise".to_owned(), SynthValue::Bool(true));
    base_opts.insert("cutoff".to_owned(), SynthValue::Float(80.0));

    let mut quiet_opts = base_opts.clone();
    quiet_opts.insert("amp_fudge".to_owned(), SynthValue::Float(1.0));
    let mut loud_opts = base_opts;
    loud_opts.insert("amp_fudge".to_owned(), SynthValue::Float(2.0));
    let event = |opts: OptMap| EventPayload {
        node_id: 22,
        seed: 0,
        order: 0,
        kind: "play".to_owned(),
        time_seconds: 0.0,
        value: SynthValue::Float(52.0),
        opts,
        synth_name: "_saw".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    };

    let (quiet_left, quiet_right) = render_event(&event(quiet_opts), 8_000).expect("event renders");
    let (loud_left, loud_right) = render_event(&event(loud_opts), 8_000).expect("event renders");
    let quiet_peak = max_abs_pair(&quiet_left, &quiet_right);
    let loud_peak = max_abs_pair(&loud_left, &loud_right);

    assert!(
        loud_peak > quiet_peak * 1.9,
        "normalise should not cancel amp_fudge: quiet={quiet_peak}, loud={loud_peak}"
    );
}

#[test]
fn synth_cutoff_envelope_sweeps_resonant_filter() {
    let mut opts = OptMap::new();
    opts.insert("attack".to_owned(), SynthValue::Float(0.0));
    opts.insert("decay".to_owned(), SynthValue::Float(0.0));
    opts.insert("sustain".to_owned(), SynthValue::Float(0.2));
    opts.insert("release".to_owned(), SynthValue::Float(0.01));
    opts.insert("sustain_level".to_owned(), SynthValue::Float(1.0));
    opts.insert("cutoff".to_owned(), SynthValue::Float(120.0));
    opts.insert("cutoff_min".to_owned(), SynthValue::Float(30.0));
    opts.insert("cutoff_attack".to_owned(), SynthValue::Float(0.0));
    opts.insert("cutoff_decay".to_owned(), SynthValue::Float(0.08));
    opts.insert("cutoff_sustain".to_owned(), SynthValue::Float(0.12));
    opts.insert("cutoff_release".to_owned(), SynthValue::Float(0.0));
    opts.insert("cutoff_attack_level".to_owned(), SynthValue::Float(1.0));
    opts.insert("cutoff_decay_level".to_owned(), SynthValue::Float(0.0));
    opts.insert("cutoff_sustain_level".to_owned(), SynthValue::Float(0.0));
    opts.insert("res".to_owned(), SynthValue::Float(0.9));
    let event = EventPayload {
        node_id: 21,
        seed: 0,
        order: 0,
        kind: "play".to_owned(),
        time_seconds: 0.0,
        value: SynthValue::Float(40.0),
        opts,
        synth_name: "_saw".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    };

    let (left, _) = render_event(&event, 8_000).expect("event renders");
    let early = average_abs_delta(&left[100..500]);
    let late = average_abs_delta(&left[1_200..1_600]);

    assert!(early > late * 1.5, "early={early}, late={late}");
}

#[test]
fn wobble_fx_filters_high_frequency_content() {
    let mut opts = OptMap::new();
    opts.insert("phase".to_owned(), SynthValue::Float(0.5));
    opts.insert("cutoff_min".to_owned(), SynthValue::Float(40.0));
    opts.insert("cutoff_max".to_owned(), SynthValue::Float(55.0));
    opts.insert("mix".to_owned(), SynthValue::Float(1.0));
    let input: Vec<f64> = (0..4_000)
        .map(|index| if index % 2 == 0 { 1.0 } else { -1.0 })
        .collect();

    let (left, right) = fx_wobble(&input, &input, &opts, 8_000, 0.0);

    let input_energy = input.iter().map(|sample| sample.abs()).sum::<f64>() / input.len() as f64;
    let output_energy = left.iter().map(|sample| sample.abs()).sum::<f64>() / left.len() as f64;
    assert_eq!(left.len(), right.len());
    assert!(output_energy < input_energy * 0.25);
}

#[test]
fn wobble_fx_uses_absolute_event_time_for_lfo_phase() {
    let mut opts = OptMap::new();
    opts.insert("phase".to_owned(), SynthValue::Float(1.0));
    opts.insert("cutoff_min".to_owned(), SynthValue::Float(35.0));
    opts.insert("cutoff_max".to_owned(), SynthValue::Float(110.0));
    opts.insert("mix".to_owned(), SynthValue::Float(1.0));
    let input = vec![1.0; 64];

    let (closed_left, _) = fx_wobble(&input, &input, &opts, 8_000, 0.0);
    let (open_left, _) = fx_wobble(&input, &input, &opts, 8_000, 0.5);

    assert!(open_left[0] > closed_left[0] * 4.0);
}
