use crate::*;

#[test]
fn reverb_produces_extended_diffuse_tail() {
    let sample_rate = 44_100;
    let mut left = vec![0.0; 512];
    let right = vec![0.0; 512];
    left[0] = 1.0;
    let mut opts = OptMap::new();
    opts.insert("room".to_owned(), SynthValue::Float(0.8));
    opts.insert("damp".to_owned(), SynthValue::Float(0.4));

    let (out_left, out_right) = fx_reverb(&left, &right, &opts, sample_rate);
    let tail_nonzero = out_left[512..]
        .iter()
        .chain(out_right[512..].iter())
        .filter(|sample| sample.abs() > 1.0e-9)
        .count();

    assert!(out_left.len() > left.len() + sample_rate as usize);
    assert!(tail_nonzero > 64, "tail_nonzero={tail_nonzero}");
}

#[test]
fn reverb_diffuses_mono_input_into_stereo_tail() {
    let sample_rate = 44_100;
    let mut input = vec![0.0; 512];
    input[0] = 1.0;
    let mut opts = OptMap::new();
    opts.insert("room".to_owned(), SynthValue::Float(0.8));
    opts.insert("damp".to_owned(), SynthValue::Float(0.4));
    opts.insert("reverb_mix".to_owned(), SynthValue::Float(1.0));

    let (out_left, out_right) = fx_reverb(&input, &input, &opts, sample_rate);
    let side_energy = out_left[512..]
        .iter()
        .zip(out_right[512..].iter())
        .map(|(left, right)| (left - right).abs())
        .sum::<f64>()
        / (out_left.len() - 512) as f64;

    assert!(side_energy > 1.0e-5, "side_energy={side_energy}");
}

#[test]
fn echo_uses_feedback_comb_decay_time() {
    let sample_rate = 1_000;
    let mut left = vec![0.0; 1];
    let right = vec![0.0; 1];
    left[0] = 1.0;
    let mut opts = OptMap::new();
    opts.insert("phase".to_owned(), SynthValue::Float(0.01));
    opts.insert("decay".to_owned(), SynthValue::Float(0.04));
    opts.insert("max_phase".to_owned(), SynthValue::Float(0.1));

    let (out_left, out_right) = fx_echo(&left, &right, &opts, sample_rate);

    assert_eq!(
        out_right.iter().map(|sample| sample.abs()).sum::<f64>(),
        0.0
    );
    assert!(out_left[10] > 0.15 && out_left[10] < 0.2);
    assert!(out_left[40] > 0.0005 && out_left[40] < 0.002);
}

#[test]
fn leak_dc_removes_constant_offset() {
    let input = vec![0.5; 5_000];

    let output = leak_dc(&input);
    let tail_average = output[4_000..]
        .iter()
        .map(|sample| sample.abs())
        .sum::<f64>()
        / 1_000.0;

    assert!(tail_average < 1.0e-6, "tail_average={tail_average}");
}

#[test]
fn slicer_default_edges_are_control_rate_dezipped() {
    let sample_rate = 1_000;
    let left = vec![1.0; 18];
    let right = vec![1.0; 18];
    let mut opts = OptMap::new();
    opts.insert("phase".to_owned(), SynthValue::Float(0.02));
    opts.insert("wave".to_owned(), SynthValue::Float(1.0));
    opts.insert("pulse_width".to_owned(), SynthValue::Float(0.5));

    let (out_left, out_right) = fx_slicer(&left, &right, &opts, sample_rate, 0.0);

    assert_eq!(out_left[0], 1.0);
    assert!(
        out_left[10] > 0.0 && out_left[10] < 1.0,
        "default slicer edge should dezipper instead of stepping to zero"
    );
    assert!(
        out_right[10] > 0.0 && out_right[10] < 1.0,
        "default slicer edge should dezipper instead of stepping to zero"
    );
}

#[test]
fn slicer_smooth_options_lag_gate_edges() {
    let sample_rate = 1_000;
    let left = vec![1.0; 18];
    let right = vec![1.0; 18];
    let mut opts = OptMap::new();
    opts.insert("phase".to_owned(), SynthValue::Float(0.02));
    opts.insert("wave".to_owned(), SynthValue::Float(1.0));
    opts.insert("pulse_width".to_owned(), SynthValue::Float(0.5));
    opts.insert("smooth_down".to_owned(), SynthValue::Float(0.01));

    let (out_left, out_right) = fx_slicer(&left, &right, &opts, sample_rate, 0.0);

    assert_eq!(out_left[0], 1.0);
    assert!(
        out_left[10] > 0.0,
        "left edge should lag instead of hard-closing"
    );
    assert!(
        out_right[10] > 0.0,
        "right edge should lag instead of hard-closing"
    );
    assert!(
        out_left[17] < out_left[10],
        "lagged gate should continue moving toward amp_min"
    );
}
