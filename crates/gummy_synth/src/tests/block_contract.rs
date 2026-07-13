use crate::*;

#[test]
fn block_render_config_has_a_bounded_reviewed_default() {
    let config = BlockRenderConfig::default().validate().unwrap();

    assert_eq!(config.block_frames, DEFAULT_RENDER_BLOCK_FRAMES);
    assert!(config.block_frames <= MAX_RENDER_BLOCK_FRAMES);
}

#[test]
fn block_render_config_rejects_zero_and_unbounded_capacities() {
    for block_frames in [0, MAX_RENDER_BLOCK_FRAMES + 1] {
        let error = BlockRenderConfig { block_frames }.validate().unwrap_err();
        assert!(error.to_string().contains("block_frames"));
    }
}

#[test]
fn block_diagnostics_track_high_water_without_duration_storage() {
    let mut diagnostics = BlockRenderDiagnostics::default();

    diagnostics.observe_active_state(2, 1);
    diagnostics.observe_active_state(1, 3);
    diagnostics.observe_scratch(256);
    diagnostics.observe_scratch(128);

    assert_eq!(diagnostics.active_voices, 1);
    assert_eq!(diagnostics.peak_active_voices, 2);
    assert_eq!(diagnostics.active_buses, 3);
    assert_eq!(diagnostics.peak_active_buses, 3);
    assert_eq!(diagnostics.scratch_current_bytes, 128);
    assert_eq!(diagnostics.scratch_peak_bytes, 256);
}
