use crate::*;

#[test]
fn playback_plan_window_matches_full_render_window_for_simple_synth() {
    let sample_rate = 8_000;
    let mut opts = OptMap::new();
    opts.insert("release".to_owned(), SynthValue::Float(0.15));
    opts.insert("amp".to_owned(), SynthValue::Float(0.5));
    let plan = SynthPlaybackPlan {
        events: vec![EventPayload {
            node_id: 90,
            order: 0,
            kind: "play".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::Float(60.0),
            opts,
            synth_name: "_sine".to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: Vec::new(),
            controls: Vec::new(),
        }],
        duration_seconds: 0.2,
        dry_event_cache: Mutex::new(HashMap::new()),
    };

    let full = plan
        .render_window_i16(0.0, 0.2, sample_rate)
        .expect("full window renders");
    let window = plan
        .render_window_i16(0.05, 0.04, sample_rate)
        .expect("live window renders");
    let offset = (0.05_f64 * sample_rate as f64).round() as usize * 2;
    let window_len = (0.04_f64 * sample_rate as f64).ceil() as usize * 2;

    assert_eq!(window, full[offset..offset + window_len]);

    assert!(plan
        .render_window_i16(0.25, 0.05, sample_rate)
        .expect("post-plan window renders")
        .is_empty());
}

#[test]
fn typed_plan_render_api_renders_a_wav_payload() {
    let wav = render_plan_events(Vec::new(), 0.0, 8_000).expect("typed plan renders");

    assert!(wav.starts_with(b"RIFF"));
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
