from __future__ import annotations

from tests.helpers.synth_tracks_fixtures import (
    Path,
    _all_scoped_expression_types_track,
    _boundary_loop,
    _choose_before_inner_loop_track,
    _choose_inside_inner_loop_track,
    _compare_expression_before_inner_loop_track,
    _FakeSynthRuntime,
    _inline_tick_inside_loop_track,
    _short_realtime_track,
    patch_synth_runtime,
    sy,
)


def test_lazy_choice_before_inner_loop_binds_once_per_outer_iteration() -> None:
    physical = _choose_before_inner_loop_track().physical_plan(duration=1.0)
    rates = [event.opts["rate"] for event in physical.events]
    pans = [event.opts["pan"] for event in physical.events]

    assert len(rates) == 8
    assert len(set(rates[:4])) == 1
    assert len(set(rates[4:])) == 1
    assert len(set(pans[:4])) > 1
    assert len(set(pans[4:])) > 1


def test_inline_lazy_choice_inside_loop_evaluates_per_iteration() -> None:
    physical = _choose_inside_inner_loop_track().physical_plan(duration=0.5)
    rates = [event.opts["rate"] for event in physical.events]

    assert len(rates) == 4
    assert len(set(rates)) > 1


def test_all_lazy_expression_types_bind_to_creation_loop_scope() -> None:
    physical = _all_scoped_expression_types_track().physical_plan(duration=1.0)
    single_notes = [event for event in physical.events if isinstance(event.value, int | float)]
    chords = [event for event in physical.events if isinstance(event.value, tuple)]

    assert [event.value for event in single_notes[:4]] == [60.0] * 4
    assert [event.value for event in single_notes[4:]] == [61.0] * 4
    assert len(set(event.opts["amp"] for event in single_notes[:4])) == 1
    assert len(set(event.opts["release"] for event in single_notes[:4])) == 1
    assert len(set(event.opts["release"] for event in single_notes[4:])) == 1
    assert len(set(event.value for event in chords[:4])) == 1
    assert len(set(event.value for event in chords[4:])) == 1
    assert len(set(event.opts["pan"] for event in chords[:4])) == 1
    assert len(set(event.opts["pan"] for event in chords[4:])) == 1


def test_compare_expression_before_inner_loop_binds_once_per_outer_iteration() -> None:
    physical = _compare_expression_before_inner_loop_track().physical_plan(duration=1.0)

    assert len(physical.events) == 4
    assert [round(event.time_seconds, 3) for event in physical.events] == [0.0, 0.1, 0.2, 0.3]


def test_inline_tick_inside_loop_still_evaluates_per_iteration() -> None:
    physical = _inline_tick_inside_loop_track().physical_plan(duration=0.5)

    assert [event.value for event in physical.events] == [60.0, 61.0, 62.0, 63.0]


def test_bounded_loop_excludes_event_at_exact_duration_boundary() -> None:
    physical = _boundary_loop().physical_plan(duration=2.0)

    assert [event.time_seconds for event in physical.events] == [0.0, 1.0]


def test_track_play_uses_rust_plan_render_for_bounded_realtime(monkeypatch) -> None:
    class _FakePlayer:
        instances = []

        def __init__(self, path: Path) -> None:
            self.path = path
            self.play_calls = 0
            self.pause_calls = 0
            self.seek_calls: list[float] = []
            self.delete_calls = 0
            _FakePlayer.instances.append(self)

        def play(self) -> None:
            self.play_calls += 1

        def pause(self) -> None:
            self.pause_calls += 1

        def seek(self, value: float) -> None:
            self.seek_calls.append(value)

        def delete(self) -> None:
            self.delete_calls += 1

    runtime = _FakeSynthRuntime()

    patch_synth_runtime(monkeypatch, runtime)

    playback = _short_realtime_track().play(
        duration=0.08,
        player_factory=_FakePlayer,
        look_ahead=0.0,
    )

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=2.0)
    assert not playback.is_playing()
    assert [player.play_calls for player in _FakePlayer.instances] == [1]
    assert len(runtime.serialized_plan_calls) == 1
    assert sy.PhysicalPlan.from_bytes(runtime.serialized_plan_calls[0][0]).duration_seconds == 0.08
    assert runtime.plan_calls == []
    assert runtime.event_calls == []


def test_track_play_uses_rust_audio_bridge_by_default(monkeypatch) -> None:
    runtime = _FakeSynthRuntime()
    patch_synth_runtime(monkeypatch, runtime)

    playback = _short_realtime_track().play(duration=0.08, look_ahead=0.0)

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=2.0)
    assert playback.error is None
    assert runtime.serialized_plan_calls == []
    assert len(runtime.play_serialized_plan_calls) == 1
    assert (
        sy.PhysicalPlan.from_bytes(runtime.play_serialized_plan_calls[0][0]).duration_seconds
        == 0.08
    )
    assert runtime.play_wav_bytes_calls == []
    assert runtime.playbacks[0].close_calls == 1
    assert runtime.playbacks[0].stop_calls == 1


def test_track_play_streams_plan_with_rust_audio_bridge_even_when_wav_is_cached(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = _FakeSynthRuntime()
    patch_synth_runtime(monkeypatch, runtime)
    track = _short_realtime_track()
    output = tmp_path / "cached.wav"

    track.save(output, duration=0.08)
    playback = track.play(duration=0.08)

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=2.0)
    assert playback.error is None
    assert len(runtime.serialized_plan_calls) == 1
    assert len(runtime.play_serialized_plan_calls) == 1
    assert (
        sy.PhysicalPlan.from_bytes(runtime.play_serialized_plan_calls[0][0]).duration_seconds
        == 0.08
    )
    assert runtime.play_wav_bytes_calls == []
    assert runtime.playbacks[0].close_calls == 1
    assert runtime.playbacks[0].stop_calls == 1
