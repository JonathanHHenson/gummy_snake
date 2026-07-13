use crate::*;

#[test]
fn output_limiter_preserves_stereo_balance_for_hot_signals() {
    let left = vec![2.0; 128];
    let right = vec![1.0; 128];

    let (limited_left, limited_right) = output_limit_pair(&left, &right, 44_100);

    let peak = limited_left
        .iter()
        .chain(limited_right.iter())
        .map(|sample| sample.abs())
        .fold(0.0, f64::max);
    assert!(peak <= OUTPUT_LIMIT_CEILING);
    assert!((limited_left[0] / limited_right[0] - 2.0).abs() < 1e-9);
}

#[test]
fn render_stereo_sample_preserves_channel_image() {
    let sample_rate = 8_000;
    let left_source = vec![0.8; 64];
    let right_source = vec![0.0; 64];
    let wav = stereo_wav_bytes(&left_source, &right_source, sample_rate);
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("system clock should be valid")
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "gummy_synth_stereo_sample_{}_{}.wav",
        std::process::id(),
        nonce
    ));
    std::fs::write(&path, wav).expect("test WAV should be writable");
    let event = EventPayload {
        node_id: 3,
        seed: 0,
        order: 0,
        kind: "sample".to_owned(),
        time_seconds: 0.0,
        value: SynthValue::String(path.to_string_lossy().into_owned()),
        opts: OptMap::new(),
        synth_name: "sample".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    };

    let rendered = render_event(&event, sample_rate);
    let _ = std::fs::remove_file(&path);
    let (left, right) = rendered.expect("stereo sample event renders");
    let left_energy = left.iter().map(|sample| sample.abs()).sum::<f64>();
    let right_energy = right.iter().map(|sample| sample.abs()).sum::<f64>();

    assert!(left_energy > right_energy * 20.0);
}
