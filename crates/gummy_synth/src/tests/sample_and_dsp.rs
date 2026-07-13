use crate::*;

fn render_controlled_sample(
    left: Vec<f64>,
    right: Vec<f64>,
    opts: OptMap,
    controls: Vec<ControlPayload>,
) -> (Vec<f64>, Vec<f64>) {
    let sample_rate = 1_000;
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("system clock should be valid")
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "gummy_synth_sample_controls_{}_{}.wav",
        std::process::id(),
        nonce
    ));
    std::fs::write(&path, stereo_wav_bytes(&left, &right, sample_rate))
        .expect("test WAV should be writable");
    let event = EventPayload {
        node_id: 100,
        seed: 0,
        order: 0,
        kind: "sample".to_owned(),
        time_seconds: 0.0,
        value: SynthValue::String(path.to_string_lossy().into_owned()),
        opts,
        synth_name: "sample".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls,
    };
    let rendered = render_event(&event, sample_rate);
    let _ = std::fs::remove_file(path);
    rendered.expect("sample event renders")
}

#[test]
fn sample_amp_control_applies_at_its_target_frame() {
    let mut control_opts = OptMap::new();
    control_opts.insert("amp".to_owned(), SynthValue::Float(0.25));
    let (left, right) = render_controlled_sample(
        vec![0.5; 16],
        vec![0.5; 16],
        OptMap::new(),
        vec![ControlPayload {
            time_seconds: 0.0044,
            opts: control_opts,
        }],
    );

    assert!((left[3] - 0.5).abs() < 0.0001);
    assert!((right[3] - 0.5).abs() < 0.0001);
    assert!((left[4] - 0.125).abs() < 0.0001);
    assert!((right[4] - 0.125).abs() < 0.0001);
}

#[test]
fn sample_amp_slide_starts_at_its_target_frame() {
    let mut control_opts = OptMap::new();
    control_opts.insert("amp".to_owned(), SynthValue::Float(1.0));
    control_opts.insert("amp_slide".to_owned(), SynthValue::Float(0.002));
    let mut opts = OptMap::new();
    opts.insert("amp".to_owned(), SynthValue::Float(0.0));
    let (left, right) = render_controlled_sample(
        vec![0.5; 16],
        vec![0.5; 16],
        opts,
        vec![ControlPayload {
            time_seconds: 0.004,
            opts: control_opts,
        }],
    );

    assert!(left[4].abs() < 0.0001);
    assert!(right[4].abs() < 0.0001);
    assert!((left[5] - 0.25).abs() < 0.0001);
    assert!((right[5] - 0.25).abs() < 0.0001);
    assert!((left[6] - 0.5).abs() < 0.0001);
    assert!((right[6] - 0.5).abs() < 0.0001);
}

#[test]
fn sample_pan_control_applies_at_its_target_frame() {
    let mut control_opts = OptMap::new();
    control_opts.insert("pan".to_owned(), SynthValue::Float(1.0));
    let (left, right) = render_controlled_sample(
        vec![0.5; 16],
        vec![0.5; 16],
        OptMap::new(),
        vec![ControlPayload {
            time_seconds: 0.004,
            opts: control_opts,
        }],
    );

    assert!((left[3] - 0.5).abs() < 0.0001);
    assert!((right[3] - 0.5).abs() < 0.0001);
    assert!(left[4].abs() < 0.0001);
    assert!((right[4] - 1.0).abs() < 0.0001);
}

#[test]
fn sample_rate_control_advances_the_source_cursor_at_its_target_frame() {
    let source: Vec<f64> = (0..16).map(|index| index as f64 / 20.0).collect();
    let mut opts = OptMap::new();
    opts.insert("anti_alias".to_owned(), SynthValue::Bool(false));
    let mut control_opts = OptMap::new();
    control_opts.insert("rate".to_owned(), SynthValue::Float(2.0));
    let (left, _) = render_controlled_sample(
        source.clone(),
        source,
        opts,
        vec![ControlPayload {
            time_seconds: 0.004,
            opts: control_opts,
        }],
    );

    assert!((left[4] - 0.2).abs() < 0.0001);
    assert!((left[5] - 0.3).abs() < 0.0001);
}

#[test]
fn same_time_sample_controls_use_stable_input_order() {
    let mut first = OptMap::new();
    first.insert("amp".to_owned(), SynthValue::Float(0.0));
    let mut second = OptMap::new();
    second.insert("amp".to_owned(), SynthValue::Float(0.5));
    let controls = vec![
        ControlPayload {
            time_seconds: 0.004,
            opts: first,
        },
        ControlPayload {
            time_seconds: 0.004,
            opts: second,
        },
    ];
    let (left, right) =
        render_controlled_sample(vec![0.5; 16], vec![0.5; 16], OptMap::new(), controls);

    assert!((left[4] - 0.25).abs() < 0.0001);
    assert!((right[4] - 0.25).abs() < 0.0001);
}

#[test]
fn decode_pcm_sample_sign_extends_16_bit_values() {
    assert_eq!(decode_pcm_sample(&0i16.to_le_bytes()), 0.0);
    assert!(decode_pcm_sample(&(-32768i16).to_le_bytes()) <= -1.0);
    assert!(decode_pcm_sample(&32767i16.to_le_bytes()) > 0.99);
}

#[test]
fn high_rate_sample_antialias_filters_folded_treble() {
    let sample_rate = 8_000;
    let input: Vec<f64> = (0..4_000)
        .map(|index| if index % 2 == 0 { 1.0 } else { -1.0 })
        .collect();

    let (filtered_left, filtered_right) =
        anti_alias_sample_segment(input.clone(), input, 8.0, sample_rate);
    let tail_rms = (filtered_left[1_000..]
        .iter()
        .chain(filtered_right[1_000..].iter())
        .map(|sample| sample * sample)
        .sum::<f64>()
        / ((filtered_left.len() - 1_000) * 2) as f64)
        .sqrt();

    assert!(tail_rms < 0.1, "tail_rms={tail_rms}");
}

#[test]
fn high_rate_sample_output_smoothing_tames_piercing_treble() {
    let sample_rate = 44_100;
    let input: Vec<f64> = (0..4_410)
        .map(|index| (TAU * 12_000.0 * index as f64 / sample_rate as f64).sin())
        .collect();

    let (filtered_left, filtered_right) =
        smooth_high_rate_sample_output(input.clone(), input.clone(), 12.0, sample_rate);
    let input_rms =
        (input.iter().map(|sample| sample * sample).sum::<f64>() / input.len() as f64).sqrt();
    let filtered_rms = (filtered_left[1_000..]
        .iter()
        .chain(filtered_right[1_000..].iter())
        .map(|sample| sample * sample)
        .sum::<f64>()
        / ((filtered_left.len() - 1_000) * 2) as f64)
        .sqrt();

    assert!(
        filtered_rms < input_rms * 0.98,
        "filtered_rms={filtered_rms}"
    );
    assert!(
        filtered_rms > input_rms * 0.8,
        "filtered_rms={filtered_rms}"
    );
}
