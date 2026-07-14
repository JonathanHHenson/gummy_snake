from __future__ import annotations

import pytest

from tests.helpers.synth_tracks_fixtures import (
    _FakeCanvasAudioPlayback,
    _FakeSynthRuntime,
    _short_realtime_track,
    _tiny_realtime_loop,
    gs,
    patch_synth_runtime,
    sy,
)


def test_track_play_reports_native_session_errors(monkeypatch) -> None:
    runtime = _FakeSynthRuntime()

    def _play_compiled_program(_program: object, looping: bool = False) -> _FakeCanvasAudioPlayback:
        playback = _FakeCanvasAudioPlayback(1.0, looping=looping)
        playback.error = "block render failed"
        runtime.playbacks.append(playback)
        return playback

    monkeypatch.setattr(runtime, "synth_play_compiled_program", _play_compiled_program)
    patch_synth_runtime(monkeypatch, runtime)

    playback = _short_realtime_track().play(duration=0.08)

    assert isinstance(playback, sy.TrackPlayback)
    assert isinstance(playback.error, RuntimeError)
    assert "block render failed" in str(playback.error)
    playback.stop()
    assert runtime.playbacks[0].close_calls == 1
    assert runtime.playbacks[0].stop_calls == 2


def test_finite_track_compiles_once_and_starts_non_looping_native_session(monkeypatch) -> None:
    runtime = _FakeSynthRuntime()
    patch_synth_runtime(monkeypatch, runtime)

    playback = _short_realtime_track().play(duration=0.08)

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=2.0)
    assert playback.error is None
    assert len(runtime.compiled_program_calls) == 1
    assert len(runtime.play_serialized_plan_calls) == 1
    assert runtime.play_looping_flags == [False]
    assert runtime.plan_calls == []
    assert runtime.event_calls == []
    assert playback.playback_diagnostics()["blocks"] == 1


def test_open_track_compiles_one_native_rolling_program_without_python_horizons(
    monkeypatch,
) -> None:
    runtime = _FakeSynthRuntime()
    patch_synth_runtime(monkeypatch, runtime)

    playback = _tiny_realtime_loop().play()

    assert isinstance(playback, sy.TrackPlayback)
    assert len(runtime.compiled_program_calls) == 1
    assert len(runtime.play_serialized_plan_calls) == 1
    assert runtime.play_looping_flags == [True]
    assert runtime.plan_calls == []
    assert runtime.event_calls == []
    assert playback.playback_diagnostics()["looping"] is True
    playback.pause()
    playback.resume()
    assert runtime.playbacks[0].pause_calls == 1
    assert runtime.playbacks[0].play_calls == 1
    playback.stop()
    assert runtime.playbacks[0].close_calls == 1


def test_track_play_rejects_removed_custom_player_route(monkeypatch) -> None:
    runtime = _FakeSynthRuntime()
    patch_synth_runtime(monkeypatch, runtime)

    with pytest.raises(gs.ArgumentValidationError, match="native Gummy Snake SDL3"):
        _short_realtime_track().play(duration=0.08, player_factory=object())

    assert runtime.compiled_program_calls == []


def test_music_data_helpers_are_pythonic_and_wrapping() -> None:
    notes = sy.ring("c4", "e4", "g4")

    assert notes[4] == "e4"
    assert sy.note("c4") == 60
    assert sy.chord("c4", "minor") == sy.ring(60.0, 63.0, 67.0)
    assert sy.scale("c4", "major_pentatonic", num_octaves=1).take(3) == sy.ring(60.0, 62.0, 64.0)
    assert sy.knit("a", 2, "b", 1) == sy.ring("a", "a", "b")
    assert len(sy.spread(3, 8)) == 8


def test_package_exposes_synth_module() -> None:
    assert gs.synth is sy
    assert hasattr(sy, "_called_track")
