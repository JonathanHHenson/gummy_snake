from __future__ import annotations

from tests.helpers.synth_tracks_fixtures import (
    Path,
    _beat_loop,
    _caller_track,
    _FakeSynthRuntime,
    _lead_line,
    _packaged_sample_track,
    _source_fx_track,
    _test_source_lowpass,
    _wav_duration,
    cast,
    gs,
    patch_synth_runtime,
    sy,
    synth_foundation,
    synth_rendering,
)


def test_track_builds_logical_and_physical_plan() -> None:
    track = _lead_line()

    assert "play" in track.explain()
    physical = track.physical_plan(duration=0.5)

    assert len(physical.events) == 1
    assert physical.events[0].synth_name == "_layered"
    assert "synth:dsaw" in physical.events[0].instance
    layers = cast(list[dict[str, object]], physical.events[0].opts["layers"])
    assert [layer["wave"] for layer in layers] == ["saw", "saw"]
    assert [layer["transpose"] for layer in layers] == [0.0, 0.1]
    assert len(physical.controls) == 1
    payload = synth_rendering._event_payloads(physical)[0]
    assert payload["controls"] == [{"time_seconds": 0.125, "opts": {"note": "b2", "pan": 0.25}}]
    assert physical.duration_seconds == 0.5


def test_track_renders_to_wav_sound_and_file(tmp_path: Path, monkeypatch) -> None:
    runtime = _FakeSynthRuntime()
    patch_synth_runtime(monkeypatch, runtime)
    track = _beat_loop()
    output = tmp_path / "beat.wav"

    saved = track.save(output, duration=sy.duration(secs=1))
    sound = track.to_sound("beat.wav", duration=1.0)

    assert saved == output
    assert output.read_bytes().startswith(b"RIFF")
    assert _wav_duration(output) == 1.0
    assert isinstance(sound, gs.Sound)
    assert sound.duration == 1.0
    assert sound.to_bytes().startswith(b"RIFF")
    assert len(runtime.serialized_plan_calls) == 1
    assert sy.PhysicalPlan.from_bytes(runtime.serialized_plan_calls[0][0]).duration_seconds == 1.0
    assert runtime.plan_calls == []
    assert runtime.event_calls == []


def test_builtin_sonic_pi_samples_are_packaged_and_serialized_as_paths() -> None:
    track = _beat_loop()
    plan = track.physical_plan(duration=0.5)
    payloads = synth_rendering._event_payloads(plan)
    sample_values = [payload["value"] for payload in payloads if payload["kind"] == "sample"]

    assert (synth_foundation._BUILTIN_SAMPLE_PACKAGE_DIR / "README.md").exists()
    assert (synth_foundation._BUILTIN_SAMPLE_PACKAGE_DIR / "loop_amen.flac").exists()
    assert len(list(synth_foundation._BUILTIN_SAMPLE_PACKAGE_DIR.glob("*.flac"))) >= 200
    assert any(str(value).endswith("drum_heavy_kick.flac") for value in sample_values)
    assert any(str(value).endswith("loop_amen.flac") for value in sample_values)


def test_rust_renderer_decodes_packaged_flac_samples() -> None:
    payload = _packaged_sample_track().render(duration=0.1)

    assert payload.startswith(b"RIFF")
    assert len(payload) > 44


def test_serialized_plan_render_resolves_packaged_sample_names() -> None:
    plan = _packaged_sample_track().physical_plan(duration=0.1)
    runtime = synth_rendering._require_synth_runtime()

    serialized_payload = bytes(runtime.synth_render_serialized_plan_wav(plan.to_bytes(), 44_100))
    legacy_payload = bytes(
        runtime.synth_render_plan_wav(
            synth_rendering._event_payloads(plan),
            plan.duration_seconds,
            44_100,
        )
    )

    assert serialized_payload == legacy_payload


def test_serialized_plan_render_is_repeatable_with_packaged_samples_and_fx() -> None:
    track = _source_fx_track()

    first = track.render(duration=0.05)
    second = track.render(duration=0.05)

    assert first == second
    assert first.startswith(b"RIFF")
    assert len(first) > 44


def test_track_save_gss_serializes_physical_plan(tmp_path: Path) -> None:
    output = tmp_path / "caller.gss"

    saved = _caller_track().save(output, duration=0.5)
    loaded = sy.load_physical_plan(output)
    loaded_from_bytes = sy.PhysicalPlan.from_bytes(output.read_bytes())

    assert saved == output
    assert output.read_bytes().startswith(synth_foundation._GSS_MAGIC)
    assert len(loaded.events) == 2
    assert loaded.duration_seconds == 0.5
    assert [event.value for event in loaded.events] == [60, 64]
    assert [event.value for event in loaded_from_bytes.events] == [60, 64]


def test_track_save_gsfx_serializes_fx_physical_plan(tmp_path: Path) -> None:
    output = tmp_path / "source_fx.gsfx"

    saved = _source_fx_track().save(output, duration=0.05)
    loaded = sy.load_physical_plan(output)

    assert saved == output
    assert output.read_bytes().startswith(synth_foundation._GSS_MAGIC)
    assert output.suffix == ".gsfx"
    assert len(loaded.events) == 1


def test_fx_decorator_expands_source_definition_to_generic_chain() -> None:
    physical = _source_fx_track().physical_plan(duration=0.05)
    payload = synth_rendering._event_payloads(physical)[0]
    fx_chain = cast(list[dict[str, object]], payload["fx_chain"])
    fx_payload = fx_chain[0]
    fx_opts = cast(dict[str, object], fx_payload["opts"])

    assert isinstance(_test_source_lowpass, sy.FxDefinition)
    assert fx_payload["name"] == "_chain"
    assert fx_opts["cutoff"] == 80
    assert fx_opts["mix"] == 0.5
    assert fx_opts["ops"] == [{"op": "filter", "kind": "low", "cutoff": 100}]


def test_same_time_fx_controls_follow_source_order() -> None:
    @sy.track
    def _track() -> None:
        with sy.fx("reverb") as reverb:
            sy.control(reverb, mix=0.1)
            sy.sample("ambi_lunar_land", amp=0.1)
            sy.control(reverb, mix=0.8)
            sy.play(60, release=0.01, amp=0.1)

    payloads = synth_rendering._event_payloads(_track().physical_plan(duration=0.1))
    first_fx = cast(list[dict[str, object]], payloads[0]["fx_chain"])[0]
    second_fx = cast(list[dict[str, object]], payloads[1]["fx_chain"])[0]

    assert payloads[0]["time_seconds"] == payloads[1]["time_seconds"] == 0.0
    assert cast(dict[str, object], first_fx["opts"])["mix"] == 0.1
    assert cast(dict[str, object], second_fx["opts"])["mix"] == 0.8


def test_synth_decorator_expands_source_definition_to_primitive_events() -> None:
    @sy.synth(name="unit_test_chime")
    def _unit_test_chime(note: object = 60, **opts: object) -> None:
        signal = sy.synth_input(note, defaults={"release": 0.05}, **opts).layer("sine", amp=0.4)
        signal.output()
        sy.synth_input(note, defaults={"release": 0.05}).layer("saw", amp=0.2).output()

    @sy.track
    def _track() -> None:
        with sy.synth("unit_test_chime"):
            sy.play(64, cutoff=90)

    physical = _track().physical_plan(duration=0.2)

    assert isinstance(_unit_test_chime, sy.SynthDefinition)
    assert [event.synth_name for event in physical.events] == ["_sine", "_saw"]
    assert all("synth:unit_test_chime" in event.instance for event in physical.events)
    assert physical.events[0].opts["cutoff"] == 90
