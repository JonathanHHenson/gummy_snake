import importlib
import io
import time
import wave
from pathlib import Path
from typing import cast

import gummysnake as gs
from gummysnake import synth as sy
from gummysnake.synth import core as synth_core
from gummysnake.synth.builtins import SONIC_PI_SYNTH_KEYS


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


_DOCUMENTED_SONIC_PI_SYNTH_NAMES = SONIC_PI_SYNTH_KEYS


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
    payload = synth_core._event_payloads(physical)[0]
    assert payload["controls"] == [{"time_seconds": 0.125, "opts": {"note": "b2", "pan": 0.25}}]
    assert physical.duration_seconds == 0.5


def test_track_renders_to_wav_sound_and_file(tmp_path: Path, monkeypatch) -> None:
    runtime = _FakeSynthRuntime()
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)
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
    payloads = synth_core._event_payloads(plan)
    sample_values = [payload["value"] for payload in payloads if payload["kind"] == "sample"]

    assert (synth_core._BUILTIN_SAMPLE_PACKAGE_DIR / "README.md").exists()
    assert (synth_core._BUILTIN_SAMPLE_PACKAGE_DIR / "loop_amen.flac").exists()
    assert len(list(synth_core._BUILTIN_SAMPLE_PACKAGE_DIR.glob("*.flac"))) >= 200
    assert any(str(value).endswith("drum_heavy_kick.flac") for value in sample_values)
    assert any(str(value).endswith("loop_amen.flac") for value in sample_values)


def test_rust_renderer_decodes_packaged_flac_samples() -> None:
    payload = _packaged_sample_track().render(duration=0.1)

    assert payload.startswith(b"RIFF")
    assert len(payload) > 44


def test_serialized_plan_render_resolves_packaged_sample_names() -> None:
    plan = _packaged_sample_track().physical_plan(duration=0.1)
    runtime = synth_core._require_synth_runtime()

    serialized_payload = bytes(runtime.synth_render_serialized_plan_wav(plan.to_bytes(), 44_100))
    legacy_payload = bytes(
        runtime.synth_render_plan_wav(
            synth_core._event_payloads(plan),
            plan.duration_seconds,
            44_100,
        )
    )

    assert serialized_payload == legacy_payload


def test_track_save_gss_serializes_physical_plan(tmp_path: Path) -> None:
    output = tmp_path / "caller.gss"

    saved = _caller_track().save(output, duration=0.5)
    loaded = sy.load_physical_plan(output)
    loaded_from_bytes = sy.PhysicalPlan.from_bytes(output.read_bytes())

    assert saved == output
    assert output.read_bytes().startswith(synth_core._GSS_MAGIC)
    assert len(loaded.events) == 2
    assert loaded.duration_seconds == 0.5
    assert [event.value for event in loaded.events] == [60, 64]
    assert [event.value for event in loaded_from_bytes.events] == [60, 64]


def test_track_save_gsfx_serializes_fx_physical_plan(tmp_path: Path) -> None:
    output = tmp_path / "source_fx.gsfx"

    saved = _source_fx_track().save(output, duration=0.05)
    loaded = sy.load_physical_plan(output)

    assert saved == output
    assert output.read_bytes().startswith(synth_core._GSS_MAGIC)
    assert output.suffix == ".gsfx"
    assert len(loaded.events) == 1


def test_fx_decorator_expands_source_definition_to_generic_chain() -> None:
    physical = _source_fx_track().physical_plan(duration=0.05)
    payload = synth_core._event_payloads(physical)[0]
    fx_chain = cast(list[dict[str, object]], payload["fx_chain"])
    fx_payload = fx_chain[0]
    fx_opts = cast(dict[str, object], fx_payload["opts"])

    assert isinstance(_test_source_lowpass, sy.FxDefinition)
    assert fx_payload["name"] == "_chain"
    assert fx_opts["cutoff"] == 80
    assert fx_opts["mix"] == 0.5
    assert fx_opts["ops"] == [{"op": "filter", "kind": "low", "cutoff": 100}]


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


def test_control_on_source_synth_targets_layered_primitive() -> None:
    @sy.track
    def _track() -> None:
        with sy.synth("dsaw"):
            handle = sy.play(60, note_slide=0.5, cutoff_slide=0.5)
            sy.control(handle, note=64, cutoff=100)

    physical = _track().physical_plan(duration=0.6)
    payloads = synth_core._event_payloads(physical)

    assert [event.synth_name for event in physical.events] == ["_layered"]
    assert [event.value for event in physical.events] == [60]
    layers = cast(list[dict[str, object]], physical.events[0].opts["layers"])
    assert [layer["transpose"] for layer in layers] == [0.0, 0.1]
    assert len(physical.controls) == 1
    assert payloads[0]["controls"] == [{"time_seconds": 0.0, "opts": {"note": 64, "cutoff": 100}}]


@sy.track(seed=22)
def _detuned_source_synth_control_track() -> None:
    with sy.synth("dsaw"):
        handle = sy.play(60, detune=sy.rrand(0, 0.2), note_slide=0.5)
        sy.control(handle, note=64)


def test_source_synth_control_uses_event_detune_for_layer_timing() -> None:
    physical = _detuned_source_synth_control_track().physical_plan(duration=0.6)
    payloads = synth_core._event_payloads(physical)
    assert isinstance(physical.events[0].value, int | float)
    layers = cast(list[dict[str, object]], physical.events[0].opts["layers"])
    detune = float(cast(int | float, layers[1]["transpose"]))

    assert detune != 0.1
    assert [event.synth_name for event in physical.events] == ["_layered"]
    assert physical.events[0].value == 60
    assert [layer["wave"] for layer in layers] == ["saw", "saw"]
    assert payloads[0]["controls"] == [{"time_seconds": 0.0, "opts": {"note": 64}}]


def test_builtin_sonic_pi_synth_source_modules_are_separate_synth_defs() -> None:
    source_dir = Path(synth_core.__file__).parent / "builtins"
    source_names: set[str] = set()
    for path in source_dir.glob("*.py"):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        module = importlib.import_module(f"gummysnake.synth.builtins.{path.stem}")
        source_names.add(module.SYNTH_NAME)

    assert set(_DOCUMENTED_SONIC_PI_SYNTH_NAMES) == source_names
    assert "bass_foundation" in source_names
    assert "arpeg-click" in source_names
    assert "server-info" in source_names
    for synth_name in _DOCUMENTED_SONIC_PI_SYNTH_NAMES:
        module_name = synth_name.replace("-", "_")
        module = importlib.import_module(f"gummysnake.synth.builtins.{module_name}")

        assert synth_name == module.SYNTH_NAME
        assert isinstance(module.SYNTH_TRACK, sy.SynthDefinition)


def test_builtin_sonic_pi_sources_use_signal_builders() -> None:
    synth_source_dir = Path(synth_core.__file__).parent / "builtins"
    for path in synth_source_dir.glob("*.py"):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        text = path.read_text()
        assert "sy.synth_input(" in text, path.name
        assert "layered_design" not in text, path.name
        assert "sample_player" not in text, path.name
        assert "from gummysnake.synth.builtins._common import silence" not in text, path.name

    fx_source_dir = Path(synth_core.__file__).parent / "fx_builtins"
    for path in fx_source_dir.glob("*.py"):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        text = path.read_text()
        assert "sy.fx_input(" in text, path.name
        assert 'with sy.fx("_chain"' not in text, path.name
        assert "chain(" not in text, path.name
        assert "op(" not in text, path.name


def test_builtin_sonic_pi_synth_assets_are_compiled_gss() -> None:
    names = sy.builtin_synth_names()

    assert set(_DOCUMENTED_SONIC_PI_SYNTH_NAMES).issubset(names)
    for synth_name in _DOCUMENTED_SONIC_PI_SYNTH_NAMES:
        path = sy.builtin_synth_path(synth_name)
        plan = sy.load_builtin_synth_plan(synth_name)

        assert path.suffix == ".gss"
        assert path.read_bytes().startswith(synth_core._GSS_MAGIC)
        assert plan.events or synth_name in {"basic_mixer", "main_mixer", "sound_in"}


def test_builtin_sonic_pi_fx_assets_are_compiled_gsfx() -> None:
    names = sy.builtin_fx_names()

    assert set(_DOCUMENTED_SONIC_PI_FX_OPTS).issubset(names)
    for fx_name in _DOCUMENTED_SONIC_PI_FX_OPTS:
        path = sy.builtin_fx_path(fx_name)
        plan = sy.load_builtin_fx_plan(fx_name)

        assert path.suffix == ".gsfx"
        assert path.read_bytes().startswith(synth_core._GSS_MAGIC)
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
    wobble_payload = _wobble_fx_track().render(duration=0.25)
    slicer_payload = _slicer_fx_track().render(duration=0.25)

    assert wobble_payload.startswith(b"RIFF")
    assert slicer_payload.startswith(b"RIFF")
    assert wobble_payload != slicer_payload


def test_documented_sonic_pi_fx_render_to_wav() -> None:
    for fx_name in _DOCUMENTED_SONIC_PI_FX_OPTS:
        payload = _documented_fx_smoke_track(fx_name).render(duration=0.08, sample_rate=8_000)

        assert payload.startswith(b"RIFF"), fx_name
        assert len(payload) > 44, fx_name


def test_track_calls_can_inline_other_tracks() -> None:
    track = _caller_track()
    physical = track.physical_plan(duration=0.5)

    assert len(physical.events) == 2
    assert [event.value for event in physical.events] == [60, 64]


def test_lazy_track_call_arguments_bind_once_and_drive_loop_sleep() -> None:
    physical = _slice_loop().physical_plan(duration=1.0)

    assert [round(event.time_seconds, 3) for event in physical.events] == [
        0.0,
        0.25,
        0.5,
        0.625,
        0.75,
    ]
    assert [event.opts["start"] for event in physical.events] == [0.5, 0.5, 0.75, 0.75, 0.5]


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

    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)

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
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)

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
    monkeypatch.setattr(synth_core, "_require_synth_runtime", lambda: runtime)
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
