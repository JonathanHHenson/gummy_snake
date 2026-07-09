# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
# pyright: reportUnknownMemberType=false
from __future__ import annotations

from tests.helpers.synth_tracks_fixtures import *  # noqa: F403


def test_track_play_reports_rust_callback_errors(monkeypatch) -> None:
    class _ErrorPlayback(_FakeCanvasAudioPlayback):
        @property
        def error(self) -> str:
            return "callback render failed"

    runtime = _FakeSynthRuntime()

    def _play_serialized_plan(payload: bytes, sample_rate: int) -> _FakeCanvasAudioPlayback:
        runtime.play_serialized_plan_calls.append((bytes(payload), sample_rate))
        playback = _ErrorPlayback(1.0)
        runtime.playbacks.append(playback)
        return playback

    monkeypatch.setattr(runtime, "synth_play_serialized_plan", _play_serialized_plan)
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)

    playback = _short_realtime_track().play()

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=2.0)
    assert isinstance(playback.error, RuntimeError)
    assert "callback render failed" in str(playback.error)
    assert runtime.playbacks[0].close_calls == 1
    assert runtime.playbacks[0].stop_calls == 1


def test_track_play_reuses_saved_wav_without_rendering_again(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)
    track = _short_realtime_track()
    output = tmp_path / "short.wav"

    track.save(output, duration=0.08)
    playback = track.play(duration=0.08, player_factory=_FakePlayer, look_ahead=0.0)

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=2.0)
    assert playback.error is None
    assert len(runtime.serialized_plan_calls) == 1
    assert [player.path for player in _FakePlayer.instances] == [output]
    assert [player.play_calls for player in _FakePlayer.instances] == [1]


def test_bounded_realtime_playback_renders_plan_before_playback_clock(monkeypatch) -> None:
    order: list[str] = []

    class _OrderingRuntime(_FakeSynthRuntime):
        def synth_render_serialized_plan_wav(self, payload: bytes, sample_rate: int) -> bytes:
            order.append("render_plan")
            self.serialized_plan_calls.append((bytes(payload), sample_rate))
            plan = sy.PhysicalPlan.from_bytes(payload)
            return _wav_payload(plan.duration_seconds, sample_rate)

    class _FakePlayer:
        instances = []

        def __init__(self, path: Path) -> None:
            self.path = path
            self.index = len(_FakePlayer.instances)
            self.play_calls = 0
            self.pause_calls = 0
            self.seek_calls: list[float] = []
            self.delete_calls = 0
            _FakePlayer.instances.append(self)

        def play(self) -> None:
            self.play_calls += 1
            order.append(f"play:{self.index}")

        def pause(self) -> None:
            self.pause_calls += 1

        def seek(self, value: float) -> None:
            self.seek_calls.append(value)

        def delete(self) -> None:
            self.delete_calls += 1

    runtime = _OrderingRuntime()
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)

    playback = _short_realtime_track().play(
        duration=0.08,
        player_factory=_FakePlayer,
        look_ahead=0.0,
    )

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=2.0)
    assert playback.error is None
    assert runtime.event_calls == []
    assert order == ["render_plan", "play:0"]


def test_event_time_groups_collect_same_time_events() -> None:
    physical = _same_time_realtime_track().physical_plan(duration=0.02)

    groups = synth_core._event_time_groups(physical.events)

    assert len(groups) == 1
    assert [event.time_seconds for event in groups[0]] == [0.0, 0.0]


def test_bounded_realtime_playback_stops_at_track_duration(monkeypatch) -> None:
    class _LongPlanRuntime(_FakeSynthRuntime):
        def synth_render_serialized_plan_wav(self, payload: bytes, sample_rate: int) -> bytes:
            self.serialized_plan_calls.append((bytes(payload), sample_rate))
            return _wav_payload(1.0, sample_rate)

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

    runtime = _LongPlanRuntime()
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)

    start = time.monotonic()
    playback = _short_realtime_track().play(
        duration=0.08,
        player_factory=_FakePlayer,
        look_ahead=0.0,
    )

    assert isinstance(playback, sy.TrackPlayback)
    assert playback.wait_until_stop(timeout=0.5)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5
    assert len(runtime.serialized_plan_calls) == 1
    assert runtime.plan_calls == []
    assert runtime.event_calls == []
    assert [player.play_calls for player in _FakePlayer.instances] == [1]
    assert all(player.delete_calls == 1 for player in _FakePlayer.instances)


def test_looping_track_play_without_duration_rolls_until_stopped(monkeypatch) -> None:
    class _FakePlayer:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.play_calls = 0
            self.pause_calls = 0
            self.seek_calls: list[float] = []
            self.delete_calls = 0

        def play(self) -> None:
            self.play_calls += 1

        def pause(self) -> None:
            self.pause_calls += 1

        def seek(self, value: float) -> None:
            self.seek_calls.append(value)

        def delete(self) -> None:
            self.delete_calls += 1

    runtime = _FakeSynthRuntime()
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)

    playback = _tiny_realtime_loop().play(
        player_factory=_FakePlayer,
        look_ahead=0.0,
    )
    assert isinstance(playback, sy.TrackPlayback)
    deadline = time.monotonic() + 1.0
    while len(runtime.event_calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    playback.stop()

    assert playback.wait_until_stop(timeout=1.0)
    assert len(runtime.event_calls) >= 3
    assert runtime.plan_calls == []


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
