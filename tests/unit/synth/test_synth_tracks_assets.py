from __future__ import annotations

from typing import Any

from tests.helpers.synth_tracks_fixtures import (
    _DOCUMENTED_SONIC_PI_FX_OPTS,
    _DOCUMENTED_SONIC_PI_SYNTH_NAMES,
    _FX_SOURCE_DIR,
    _SYNTH_SOURCE_DIR,
    _asset_source_files,
    _caller_track,
    _constant_string,
    _detuned_source_synth_control_track,
    _documented_fx_smoke_track,
    _slice_loop,
    _slicer_fx_track,
    _wobble_fx_track,
    cast,
    sy,
    synth_foundation,
    synth_rendering,
)


def test_control_on_source_synth_targets_layered_primitive() -> None:
    @sy.track
    def _track() -> None:
        with sy.synth("dsaw"):
            handle = sy.play(60, note_slide=0.5, cutoff_slide=0.5)
            sy.control(handle, note=64, cutoff=100)

    track = cast(Any, _track())
    physical = track.physical_plan(duration=0.6)
    payloads = synth_rendering._event_payloads(physical)

    assert [event.synth_name for event in physical.events] == ["_layered"]
    assert [event.value for event in physical.events] == [60]
    layers = cast(list[dict[str, object]], physical.events[0].opts["layers"])
    assert [layer["transpose"] for layer in layers] == [0.0, 0.1]
    assert len(physical.controls) == 1
    assert payloads[0]["controls"] == [{"time_seconds": 0.0, "opts": {"note": 64, "cutoff": 100}}]


def test_source_synth_control_uses_event_detune_for_layer_timing() -> None:
    track = cast(Any, _detuned_source_synth_control_track())
    physical = track.physical_plan(duration=0.6)
    payloads = synth_rendering._event_payloads(physical)
    assert isinstance(physical.events[0].value, int | float)
    layers = cast(list[dict[str, object]], physical.events[0].opts["layers"])
    detune = float(cast(int | float, layers[1]["transpose"]))

    assert detune != 0.1
    assert [event.synth_name for event in physical.events] == ["_layered"]
    assert physical.events[0].value == 60
    assert [layer["wave"] for layer in layers] == ["saw", "saw"]
    assert payloads[0]["controls"] == [{"time_seconds": 0.0, "opts": {"note": 64}}]


def test_builtin_sonic_pi_synth_source_modules_are_separate_synth_defs() -> None:
    source_names = {
        _constant_string(path, "SYNTH_NAME") for path in _asset_source_files(_SYNTH_SOURCE_DIR)
    }

    assert set(_DOCUMENTED_SONIC_PI_SYNTH_NAMES) == source_names
    assert "bass_foundation" in source_names
    assert "arpeg-click" in source_names
    assert "server-info" in source_names
    for path in _asset_source_files(_SYNTH_SOURCE_DIR):
        synth_name = _constant_string(path, "SYNTH_NAME")
        expected_module_name = synth_name.replace("-", "_")

        assert path.stem == expected_module_name
        text = path.read_text()
        assert "@sy.synth" in text
        assert "SYNTH_TRACK" in text


def test_builtin_sonic_pi_sources_use_signal_builders() -> None:
    old_synth_package = "from " + "gummysnake.synth." + "builtins"
    old_fx_package = "from " + "gummysnake.synth." + "fx_builtins"

    for path in _asset_source_files(_SYNTH_SOURCE_DIR):
        text = path.read_text()
        assert "sy.synth_input(" in text, path.name
        assert "layered_design" not in text, path.name
        assert "sample_player" not in text, path.name
        assert old_synth_package not in text, path.name

    for path in _asset_source_files(_FX_SOURCE_DIR):
        text = path.read_text()
        assert "sy.fx_input(" in text, path.name
        assert 'with sy.fx("_chain"' not in text, path.name
        assert "chain(" not in text, path.name
        assert "op(" not in text, path.name
        assert old_fx_package not in text, path.name


def test_builtin_sonic_pi_synth_assets_are_compiled_gss() -> None:
    names = sy.builtin_synth_names()

    assert set(_DOCUMENTED_SONIC_PI_SYNTH_NAMES).issubset(names)
    for synth_name in _DOCUMENTED_SONIC_PI_SYNTH_NAMES:
        path = sy.builtin_synth_path(synth_name)
        plan = sy.load_builtin_synth_plan(synth_name)

        assert path.suffix == ".gss"
        assert path.read_bytes().startswith(synth_foundation._GSS_MAGIC)
        assert plan.events or synth_name in {"basic_mixer", "main_mixer", "sound_in"}


def test_builtin_sonic_pi_fx_assets_are_compiled_gsfx() -> None:
    names = sy.builtin_fx_names()

    assert set(_DOCUMENTED_SONIC_PI_FX_OPTS).issubset(names)
    for fx_name in _DOCUMENTED_SONIC_PI_FX_OPTS:
        path = sy.builtin_fx_path(fx_name)
        plan = sy.load_builtin_fx_plan(fx_name)

        assert path.suffix == ".gsfx"
        assert path.read_bytes().startswith(synth_foundation._GSS_MAGIC)
        assert len(plan.events) == 1

    tb303_event = sy.load_builtin_synth_plan("tb303").events[0]
    assert tb303_event.synth_name == "_saw"
    assert tb303_event.opts["cutoff_min"] == 30
    assert tb303_event.opts["res"] == 0.9
    prophet_event = sy.load_builtin_synth_plan("prophet").events[0]
    prophet_layers = cast(list[dict[str, object]], prophet_event.opts["layers"])
    assert prophet_event.synth_name == "_layered"
    assert [layer["wave"] for layer in prophet_layers] == ["pulse"] * 5
    assert any(
        "pulse_width_lfo_rate" in cast(dict[str, object], layer["opts"]) for layer in prophet_layers
    )
    assert sy.load_builtin_synth_plan("arpeg-click").events[0].synth_name == "_layered"


def test_wobble_fx_is_distinct_from_slicer_fx() -> None:
    wobble_track = cast(Any, _wobble_fx_track())
    slicer_track = cast(Any, _slicer_fx_track())
    wobble_payload = wobble_track.render(duration=0.25)
    slicer_payload = slicer_track.render(duration=0.25)

    assert wobble_payload.startswith(b"RIFF")
    assert slicer_payload.startswith(b"RIFF")
    assert wobble_payload != slicer_payload


def test_documented_sonic_pi_fx_render_to_wav() -> None:
    for fx_name in _DOCUMENTED_SONIC_PI_FX_OPTS:
        track = cast(Any, _documented_fx_smoke_track(fx_name))
        payload = track.render(duration=0.08, sample_rate=8_000)

        assert payload.startswith(b"RIFF"), fx_name
        assert len(payload) > 44, fx_name


def test_track_calls_can_inline_other_tracks() -> None:
    track = cast(Any, _caller_track())
    physical = track.physical_plan(duration=0.5)

    assert len(physical.events) == 2
    assert [event.value for event in physical.events] == [60, 64]


def test_lazy_track_call_arguments_bind_once_and_drive_loop_sleep() -> None:
    track = cast(Any, _slice_loop())
    physical = track.physical_plan(duration=1.0)

    assert [round(event.time_seconds, 3) for event in physical.events] == [
        0.0,
        0.25,
        0.5,
        0.625,
        0.75,
    ]
    assert [event.opts["start"] for event in physical.events] == [0.5, 0.5, 0.75, 0.75, 0.5]
