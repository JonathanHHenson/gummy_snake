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

#[test]
fn sample_duration_probes_wav_metadata_without_populating_decode_caches() {
    let sample_rate = 8_000;
    let wav = stereo_wav_bytes(&vec![0.25; 800], &vec![-0.25; 800], sample_rate);
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "gummy_synth_metadata_probe_{}_{}.wav",
        std::process::id(),
        nonce
    ));
    std::fs::write(&path, wav).unwrap();

    let duration =
        sample_duration(&SynthValue::String(path.to_string_lossy().into_owned())).unwrap();
    let cache_contains_probe = sample_cache_contains_path(&path);
    let _ = std::fs::remove_file(path);

    assert!((duration - 0.1).abs() < 1e-12);
    assert!(!cache_contains_probe);
}

#[test]
fn sample_cache_reuses_native_and_target_rate_sources_and_invalidates_stale_files() {
    let source_rate = 8_000;
    let target_rate = 16_000;
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "gummy_synth_versioned_cache_{}_{}.wav",
        std::process::id(),
        nonce
    ));
    std::fs::write(
        &path,
        stereo_wav_bytes(&vec![0.1; 80], &vec![0.1; 80], source_rate),
    )
    .unwrap();
    let value = SynthValue::String(path.to_string_lossy().into_owned());

    let first = sample_source(&value, target_rate).unwrap();
    let second = sample_source(&value, target_rate).unwrap();
    assert_eq!(first.len(), second.len());
    assert!(Arc::ptr_eq(&first.left, &second.left));
    assert!(Arc::ptr_eq(&first.right, &second.right));

    std::fs::write(
        &path,
        stereo_wav_bytes(&vec![0.2; 160], &vec![0.2; 160], source_rate),
    )
    .unwrap();
    let refreshed = sample_source(&value, target_rate).unwrap();
    let refreshed_diagnostics = sample_cache_diagnostics();
    let _ = std::fs::remove_file(path);

    assert_eq!(refreshed.len(), 320);
    assert!(!Arc::ptr_eq(&first.left, &refreshed.left));
    assert!(!Arc::ptr_eq(&first.right, &refreshed.right));
    assert!(refreshed_diagnostics.source_bytes <= SAMPLE_SOURCE_CACHE_BUDGET_BYTES);
    assert!(refreshed_diagnostics.resample_bytes <= SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES);
}

#[test]
fn band_limited_resampler_preserves_duration_and_rejects_downsample_aliases() {
    let source_rate = 48_000;
    let target_rate = 16_000;
    let frames = 4_800;
    let passband = (0..frames)
        .map(|index| (TAU * 1_000.0 * index as f64 / source_rate as f64).sin())
        .collect::<Vec<_>>();
    let stopband = (0..frames)
        .map(|index| (TAU * 12_000.0 * index as f64 / source_rate as f64).sin())
        .collect::<Vec<_>>();

    let passband_output = resample(&passband, source_rate, target_rate);
    let stopband_output = resample(&stopband, source_rate, target_rate);
    let passband_rms = (passband_output[32..]
        .iter()
        .map(|sample| sample * sample)
        .sum::<f64>()
        / (passband_output.len() - 32) as f64)
        .sqrt();
    let stopband_rms = (stopband_output[32..]
        .iter()
        .map(|sample| sample * sample)
        .sum::<f64>()
        / (stopband_output.len() - 32) as f64)
        .sqrt();

    assert_eq!(passband_output.len(), 1_600);
    assert!(passband_rms > 0.65, "passband_rms={passband_rms}");
    assert!(stopband_rms < 0.08, "stopband_rms={stopband_rms}");
}
