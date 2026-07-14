use crate::*;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use std::io::Write;

#[test]
fn dynamic_band_limited_sampling_is_finite_and_rate_sensitive() {
    let source = [0.0, 1.0, 0.0, -1.0, 0.0];

    let normal = band_limited_sample(&source, 1.5, 1.0);
    let downsampled = band_limited_sample(&source, 1.5, 2.0);

    assert!(normal.is_finite());
    assert!(downsampled.is_finite());
    assert_ne!(normal, downsampled);
    assert_eq!(band_limited_sample(&source, 1.0, 0.0), 0.0);
}

#[test]
fn standalone_event_wav_preserves_simple_legacy_pcm_exactly() {
    let sample_rate = 8_000;
    let mut opts = OptMap::new();
    opts.insert("attack".to_owned(), SynthValue::Float(0.003));
    opts.insert("sustain".to_owned(), SynthValue::Float(0.012));
    opts.insert("release".to_owned(), SynthValue::Float(0.02));
    opts.insert("amp".to_owned(), SynthValue::Float(0.4));
    let event = EventPayload {
        node_id: 320,
        seed: 7,
        order: 0,
        kind: "play".to_owned(),
        time_seconds: 0.25,
        value: SynthValue::Float(64.0),
        opts,
        synth_name: "_sine".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    };
    let (left, right) = render_event(&event, sample_rate).unwrap();
    let (left, right) = output_limit_pair(&left, &right, sample_rate);
    let expected = stereo_wav_bytes(&left, &right, sample_rate);

    let actual = render_event_wav(&event, sample_rate).unwrap();

    assert_eq!(actual, expected);
}

#[test]
fn typed_plan_render_api_renders_a_wav_payload() {
    let wav = render_plan_events(Vec::new(), 0.0, 8_000).expect("typed plan renders");

    assert!(wav.starts_with(b"RIFF"));
}

#[test]
fn serialized_file_route_streams_the_same_exact_wav_as_the_memory_route() {
    let raw = br#"{"schema":"gummysnake.synth.physical_plan.v1","duration_seconds":0.01,"sample_rate":8000,"events":[],"controls":[]}"#;
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
    encoder.write_all(raw).unwrap();
    let compressed = encoder.finish().unwrap();
    let mut payload = Vec::new();
    payload.extend_from_slice(GSS_MAGIC);
    payload.extend_from_slice(&GSS_COMPRESSION_ZLIB.to_be_bytes());
    payload.extend_from_slice(&(raw.len() as u32).to_be_bytes());
    payload.extend_from_slice(&compressed);
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "gummy_synth_block_output_{}_{}.wav",
        std::process::id(),
        nonce
    ));

    let expected = render_serialized_plan_wav_bytes(&payload, 8_000).unwrap();
    render_serialized_plan_wav_file(&payload, 8_000, &path).unwrap();
    let written = std::fs::read(&path).unwrap();
    let _ = std::fs::remove_file(path);

    assert_eq!(written, expected);
    assert_eq!(written.len(), 44 + 80 * 4);
}

#[test]
fn serialized_file_route_preserves_existing_destination_when_compile_fails() {
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "gummy_synth_atomic_output_{}_{}.wav",
        std::process::id(),
        nonce
    ));
    std::fs::write(&path, b"existing-user-audio").unwrap();

    let error = render_serialized_plan_wav_file(b"not-a-plan", 8_000, &path).unwrap_err();
    let retained = std::fs::read(&path).unwrap();
    let _ = std::fs::remove_file(path);

    assert!(error.message().contains("ValueError"));
    assert_eq!(retained, b"existing-user-audio");
}

#[test]
fn stereo_wav_encoder_writes_expected_header() {
    let wav = stereo_wav_bytes(&[0.0, 0.5], &[0.0, -0.5], 44_100);

    assert_eq!(&wav[0..4], b"RIFF");
    assert_eq!(&wav[8..12], b"WAVE");
    assert_eq!(&wav[12..16], b"fmt ");
    assert_eq!(&wav[36..40], b"data");
    assert_eq!(wav.len(), 44 + 2 * 4);
}
