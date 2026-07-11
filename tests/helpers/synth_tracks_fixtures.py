import ast
import io
import time
import wave
from pathlib import Path
from typing import Any, cast

from pytest import MonkeyPatch

import gummysnake as gs
from gummysnake import synth as sy
from gummysnake.synth.synth_runtime.physical import rendering as synth_rendering
from gummysnake.synth.synth_runtime.playback_export import playback as synth_playback
from gummysnake.synth.synth_runtime.values import foundation as synth_foundation


def patch_synth_runtime(monkeypatch: MonkeyPatch, runtime: Any) -> None:
    """Patch every direct synth runtime lookup used by track rendering and playback tests."""

    monkeypatch.setattr(synth_rendering, "_require_synth_runtime", lambda: runtime)
    monkeypatch.setattr(synth_playback, "_require_synth_runtime", lambda: runtime)


@sy.track(seed=12)
def _lead_line() -> None:
    with sy.synth("dsaw"), sy.fx("slicer", phase=0.125), sy.fx("reverb", mix=0.1):
        handle = sy.play(
            sy.choose(sy.chord(sy.choose(["e2", "g2"]), "minor")),
            release=0.25,
            cutoff=sy.rrand(70, 100),
            pan=sy.rrand(-0.5, 0.5),
            note_slide=0.1,
        )
        sy.sleep(0.125)
        sy.control(handle, note="b2", pan=0.25)
        sy.sleep(0.125)


@sy.track(loop=True, seed=7)
def _beat_loop() -> None:
    with sy.thread(), sy.loop():
        sy.sample("drum_heavy_kick")
        sy.sleep(0.5)
    with sy.loop(times=2):
        sy.sample("loop_amen", start=0.0, finish=0.25, rate=sy.choose([1, -1]))
        sy.sleep(0.25)


@sy.track
def _called_track(n: int) -> None:
    sy.play(n, release=0.1)
    sy.sleep(0.1)


@sy.track
def _caller_track() -> None:
    sy._called_track(60)
    sy._called_track(64)


@sy.track
def _short_realtime_track() -> None:
    sy.play(60, release=0.01)
    sy.sleep(0.03)
    sy.play(64, release=0.01)


@sy.track
def _same_time_realtime_track() -> None:
    sy.play(60, release=0.01)
    sy.play(64, release=0.01)


@sy.track(loop=True)
def _tiny_realtime_loop() -> None:
    sy.play(60, release=0.001)
    sy.sleep(0.02)


@sy.track(loop=True)
def _boundary_loop() -> None:
    sy.play(60, release=0.01)
    sy.sleep(1)


@sy.track
def _packaged_sample_track() -> None:
    sy.sample("bd_haus", amp=0.2)
    sy.sleep(0.1)


@sy.track
def _wobble_fx_track() -> None:
    with sy.fx("wobble", phase=0.25, cutoff_min=40, cutoff_max=55, mix=1.0):
        sy.sample("loop_amen", amp=0.5)
        sy.sleep(0.25)


@sy.fx(name="test_source_lowpass")
def _test_source_lowpass(**opts: object) -> None:
    signal = sy.fx_input().filter(kind="low", cutoff=100)
    sy.fx_output(signal, **opts)


@sy.track
def _source_fx_track() -> None:
    with sy.fx("test_source_lowpass", cutoff=90, mix=0.5) as fx_handle:
        sy.control(fx_handle, cutoff=80)
        sy.play(60, release=0.01, amp=0.1)
        sy.sleep(0.01)


@sy.track
def _slicer_fx_track() -> None:
    with sy.fx("slicer", phase=0.25, mix=1.0):
        sy.sample("loop_amen", amp=0.5)
        sy.sleep(0.25)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SYNTH_SOURCE_DIR = _PROJECT_ROOT / "assets" / "synths" / "src"
_FX_SOURCE_DIR = _PROJECT_ROOT / "assets" / "fx" / "src"


def _asset_source_files(source_dir: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in source_dir.glob("*.py")
            if path.name != "__init__.py" and not path.name.startswith("_")
        )
    )


def _constant_string(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError(f"{path} does not define string constant {name}")


_DOCUMENTED_SONIC_PI_SYNTH_NAMES = tuple(
    sorted(_constant_string(path, "SYNTH_NAME") for path in _asset_source_files(_SYNTH_SOURCE_DIR))
)


_PRIMITIVE_SYNTH_NAMES = {
    "_silence",
    "_beep",
    "_sine",
    "_saw",
    "_pulse",
    "_square",
    "_tri",
    "_fm",
    "_noise",
    "_pnoise",
    "_bnoise",
    "_gnoise",
    "_cnoise",
    "_layered",
}


_DOCUMENTED_SONIC_PI_FX_OPTS: dict[str, dict[str, object]] = {
    "bitcrusher": {"sample_rate": 1_000, "bits": 4},
    "krush": {"gain": 8, "cutoff": 90, "res": 0.2},
    "reverb": {"room": 0.7, "damp": 0.4},
    "gverb": {"room": 8, "release": 0.05, "spread": 0.7},
    "level": {"amp": 0.7},
    "echo": {"phase": 0.01, "decay": 0.03},
    "slicer": {"phase": 0.02, "wave": 2},
    "panslicer": {"phase": 0.02, "wave": 2},
    "wobble": {"phase": 0.04, "cutoff_min": 40, "cutoff_max": 100},
    "ixi_techno": {"phase": 0.05, "cutoff_min": 45, "cutoff_max": 95},
    "compressor": {"threshold": 0.05, "slope_above": 0.25},
    "whammy": {"transpose": 7},
    "rlpf": {"cutoff": 80, "res": 0.4},
    "nrlpf": {"cutoff": 80, "res": 0.4},
    "rhpf": {"cutoff": 70, "res": 0.4},
    "nrhpf": {"cutoff": 70, "res": 0.4},
    "hpf": {"cutoff": 70},
    "nhpf": {"cutoff": 70},
    "lpf": {"cutoff": 80},
    "nlpf": {"cutoff": 80},
    "normaliser": {"level": 0.4},
    "distortion": {"distort": 0.6},
    "pan": {"pan": -0.5},
    "bpf": {"centre": 80, "res": 0.5},
    "nbpf": {"centre": 80, "res": 0.5},
    "rbpf": {"centre": 80, "res": 0.5},
    "nrbpf": {"centre": 80, "res": 0.5},
    "band_eq": {"freq": 80, "db": -6},
    "tanh": {"krunch": 8},
    "pitch_shift": {"pitch": 7, "window_size": 0.02},
    "ring_mod": {"freq": 38, "mod_amp": 0.8},
    "octaver": {"super_amp": 0.6, "sub_amp": 0.4, "subsub_amp": 0.2},
    "vowel": {"vowel_sound": 3, "voice": 2},
    "flanger": {"phase": 0.04, "delay": 2, "depth": 4, "feedback": 0.2},
}


def _documented_fx_smoke_track(fx_name: str) -> sy.Track:
    opts = _DOCUMENTED_SONIC_PI_FX_OPTS[fx_name]

    @sy.track
    def _track() -> None:
        with sy.synth("saw"), sy.fx(fx_name, **opts):
            sy.play(60, release=0.04, amp=0.25)
            sy.sleep(0.04)

    return _track()


@sy.track
def _slice_step(n: int) -> None:
    sy.sample("fake_loop", start=1 - (1.0 / n))
    sy.sleep(sy.sample_duration("fake_loop") / n)


@sy.track(seed=3)
def _slice_loop() -> None:
    with sy.loop(times=5):
        sy._slice_step(sy.choose([2, 4]))


@sy.track(seed=200)
def _choose_before_inner_loop_track() -> None:
    with sy.loop(times=2):
        rate = sy.choose([0.5, 1 / 3, 3 / 5])
        with sy.loop(times=4):
            sy.sample("fake_loop", rate=rate, pan=sy.rrand(-1, 1))
            sy.sleep(0.1)


@sy.track(seed=200)
def _choose_inside_inner_loop_track() -> None:
    with sy.loop(times=4):
        sy.sample("fake_loop", rate=sy.choose([0.5, 1 / 3, 3 / 5]))
        sy.sleep(0.1)


@sy.track(seed=201)
def _all_scoped_expression_types_track() -> None:
    with sy.loop(times=2):
        ticked = sy.tick("outer_expression_scope")
        note = sy.note("c4") + ticked
        amp = -sy.choose([0.2, 0.3])
        release = sy.sample_duration("fake_loop") / sy.choose([2, 4])
        chord_value = sy.chord(sy.choose(["c4", "e4"]), "major")
        condition = note >= sy.note("c4")
        with sy.loop(times=4):
            sy.play(note, amp=amp, release=release).when(condition)
            sy.play(chord_value, pan=release)
            sy.sleep(0.1)


@sy.track
def _compare_expression_before_inner_loop_track() -> None:
    with sy.loop(times=2):
        first_outer_iteration = sy.tick("condition_expression_scope") == 0
        with sy.loop(times=4):
            sy.play(60).when(first_outer_iteration)
            sy.sleep(0.1)


@sy.track
def _inline_tick_inside_loop_track() -> None:
    with sy.loop(times=4):
        sy.play(sy.note("c4") + sy.tick("inline_expression_scope"))
        sy.sleep(0.1)


@sy.track(seed=22)
def _detuned_source_synth_control_track() -> None:
    with sy.synth("dsaw"):
        handle = sy.play(60, detune=sy.rrand(0, 0.2), note_slide=0.5)
        sy.control(handle, note=64)


def _wav_payload(duration_seconds: float, sample_rate: int = 44_100) -> bytes:
    output = io.BytesIO()
    frames = max(1, int(round(duration_seconds * sample_rate)))
    with wave.open(output, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00\x00\x00" * frames)
    return output.getvalue()


class _FakeCanvasAudioPlayback:
    def __init__(self, duration: float) -> None:
        self.duration = duration
        self.stop_calls = 0
        self.close_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def close(self) -> None:
        self.close_calls += 1
        self.stop()

    def wait_until_stop(self, timeout: float | None = None) -> bool:
        return True

    def is_playing(self) -> bool:
        return False


class _FakeSynthRuntime:
    def __init__(self) -> None:
        self.serialized_plan_calls: list[tuple[bytes, int]] = []
        self.play_serialized_plan_calls: list[tuple[bytes, int]] = []
        self.play_wav_bytes_calls: list[bytes] = []
        self.playbacks: list[_FakeCanvasAudioPlayback] = []
        self.plan_calls: list[tuple[list[dict[str, object]], float, int]] = []
        self.event_calls: list[tuple[dict[str, object], int]] = []

    def synth_render_serialized_plan_wav(self, payload: bytes, sample_rate: int) -> bytes:
        self.serialized_plan_calls.append((bytes(payload), sample_rate))
        plan = sy.PhysicalPlan.from_bytes(payload)
        return _wav_payload(plan.duration_seconds, sample_rate)

    def synth_play_serialized_plan(
        self, payload: bytes, sample_rate: int
    ) -> _FakeCanvasAudioPlayback:
        self.play_serialized_plan_calls.append((bytes(payload), sample_rate))
        plan = sy.PhysicalPlan.from_bytes(payload)
        playback = _FakeCanvasAudioPlayback(plan.duration_seconds)
        self.playbacks.append(playback)
        return playback

    def synth_play_wav_bytes(self, payload: bytes) -> _FakeCanvasAudioPlayback:
        payload = bytes(payload)
        self.play_wav_bytes_calls.append(payload)
        playback = _FakeCanvasAudioPlayback(_wav_payload_duration(payload))
        self.playbacks.append(playback)
        return playback

    def synth_render_plan_wav(
        self, events: list[dict[str, object]], duration_seconds: float, sample_rate: int
    ) -> bytes:
        self.plan_calls.append((events, duration_seconds, sample_rate))
        return _wav_payload(duration_seconds, sample_rate)

    def synth_render_event_wav(self, event: dict[str, object], sample_rate: int) -> bytes:
        self.event_calls.append((event, sample_rate))
        return _wav_payload(0.01, sample_rate)

    def synth_sample_duration(self, value: object) -> float:
        return 1.0


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def _wav_payload_duration(payload: bytes) -> float:
    with wave.open(io.BytesIO(payload), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


__all__ = [
    "Path",
    "ast",
    "cast",
    "gs",
    "io",
    "sy",
    "synth_foundation",
    "synth_playback",
    "synth_rendering",
    "patch_synth_runtime",
    "time",
    "wave",
    "_FakeCanvasAudioPlayback",
    "_DOCUMENTED_SONIC_PI_FX_OPTS",
    "_DOCUMENTED_SONIC_PI_SYNTH_NAMES",
    "_FX_SOURCE_DIR",
    "_FakeSynthRuntime",
    "_PRIMITIVE_SYNTH_NAMES",
    "_PROJECT_ROOT",
    "_SYNTH_SOURCE_DIR",
    "_all_scoped_expression_types_track",
    "_asset_source_files",
    "_beat_loop",
    "_boundary_loop",
    "_called_track",
    "_caller_track",
    "_choose_before_inner_loop_track",
    "_choose_inside_inner_loop_track",
    "_compare_expression_before_inner_loop_track",
    "_constant_string",
    "_detuned_source_synth_control_track",
    "_documented_fx_smoke_track",
    "_inline_tick_inside_loop_track",
    "_lead_line",
    "_packaged_sample_track",
    "_same_time_realtime_track",
    "_short_realtime_track",
    "_slice_loop",
    "_slice_step",
    "_slicer_fx_track",
    "_source_fx_track",
    "_test_source_lowpass",
    "_tiny_realtime_loop",
    "_wav_duration",
    "_wav_payload",
    "_wav_payload_duration",
    "_wobble_fx_track",
]
