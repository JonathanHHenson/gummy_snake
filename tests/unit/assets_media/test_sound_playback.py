import inspect
import wave
from pathlib import Path

import pytest

import gummysnake as gs
from gummysnake import BackendCapabilityError
from gummysnake.assets import sound as sound_module
from gummysnake.assets.sound_runtime import loading_and_playback
from gummysnake.assets.sound_runtime.canvas_sound import CanvasSound


class _FakePlayback:
    def __init__(self, duration: float, *, looping: bool, position: float) -> None:
        self.duration = duration
        self.error = None
        self._playing = True
        self._paused = False
        self._looping = looping
        self._time = position
        self._ended = 0
        self.stop_calls = 0
        self.close_calls = 0
        self.volume_updates: list[float] = []
        self.rate_updates: list[float] = []
        self.pan_updates: list[float] = []
        self.seek_updates: list[float] = []

    def play(self) -> None:
        self._playing = True
        self._paused = False

    def pause(self) -> None:
        self._playing = False
        self._paused = True

    def stop(self) -> None:
        self.stop_calls += 1
        self._playing = False
        self._paused = False
        self._time = 0.0

    def close(self) -> None:
        self.close_calls += 1

    def looping(self, value: bool | None = None) -> bool:
        if value is not None:
            self._looping = value
        return self._looping

    def set_volume(self, value: float) -> None:
        self.volume_updates.append(value)

    def set_rate(self, value: float) -> None:
        self.rate_updates.append(value)

    def set_pan(self, value: float) -> None:
        self.pan_updates.append(value)

    def seek(self, seconds: float) -> None:
        self.seek_updates.append(seconds)
        self._time = seconds

    def time(self) -> float:
        return self._time

    def is_playing(self) -> bool:
        if self.error:
            raise RuntimeError(self.error)
        return self._playing

    def is_paused(self) -> bool:
        return self._paused

    def take_ended(self) -> bool:
        if self._ended <= 0:
            return False
        self._ended -= 1
        return True

    def diagnostics(self) -> dict[str, object]:
        return {
            "duration_seconds": self.duration,
            "position_seconds": self._time,
            "playing": self._playing,
            "paused": self._paused,
            "looping": self._looping,
            "blocks": 3,
            "rendered_frames": 96,
            "ended_generation": 1 if self._ended else 0,
            "error": self.error,
        }

    def finish_naturally(self) -> None:
        self._playing = False
        self._paused = False
        self._time = self.duration
        self._ended += 1


class _FakeRustSound:
    def __init__(self, path: str = "tone.wav", payload: bytes = b"RIFFfake") -> None:
        self.path = path
        self.duration = 1.25
        self.byte_len = len(payload)
        self.sample_rate = 8_000
        self.frame_count = 10_000
        self.payload = payload
        self.play_calls: list[tuple[float, float, float, bool, float]] = []
        self.playbacks: list[_FakePlayback] = []
        self.play_error: Exception | None = None

    def to_bytes(self) -> bytes:
        return self.payload

    def play(
        self,
        volume: float = 1.0,
        rate: float = 1.0,
        pan: float = 0.0,
        looping: bool = False,
        position: float = 0.0,
    ) -> _FakePlayback:
        if self.play_error is not None:
            raise self.play_error
        self.play_calls.append((volume, rate, pan, looping, position))
        playback = _FakePlayback(self.duration, looping=looping, position=position)
        self.playbacks.append(playback)
        return playback


def _sound() -> tuple[sound_module.Sound, _FakeRustSound]:
    rust = _FakeRustSound()
    asset = CanvasSound.from_rust(rust)
    return sound_module.Sound(asset, path=Path(rust.path), rust_sound=asset), rust


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8_000)
        wav.writeframes(b"\0\0" * 10_000)


def test_public_sound_contract_and_legacy_loader_keep_public_identity(tmp_path: Path):
    sound_path = tmp_path / "tone.wav"
    _write_wav(sound_path)

    import gummysnake.assets as assets

    assert gs.Sound is sound_module.Sound
    assert gs.CanvasSound is sound_module.CanvasSound
    assert assets.Sound is sound_module.Sound
    assert assets.CanvasSound is sound_module.CanvasSound
    assert assets.load_sound is sound_module.load_sound
    assert assets.load_sound_async is sound_module.load_sound_async
    assert str(inspect.signature(sound_module.load_sound)) == "(path: 'str | Path') -> 'Sound'"
    assert (
        str(inspect.signature(sound_module.load_sound_async)) == "(path: 'str | Path') -> 'Sound'"
    )

    original = sound_module.CanvasSound.from_file
    sound_module.CanvasSound.from_file = lambda _path: CanvasSound.from_rust(_FakeRustSound())
    try:
        loaded = loading_and_playback.load_sound(sound_path)
    finally:
        sound_module.CanvasSound.from_file = original
    assert type(loaded) is sound_module.Sound


def test_sound_uses_atomic_native_controls_and_independent_voice_state() -> None:
    clip, rust = _sound()
    clip.volume(0.4)
    clip.rate(1.5)
    clip.pan(-0.25)
    clip.looping(True)
    clip.seek(0.5)

    clip.play()

    assert rust.play_calls == [(0.4, 1.5, -0.25, True, 0.5)]
    playback = rust.playbacks[0]
    assert clip.duration == 1.25
    assert clip.byte_len == len(rust.payload)
    assert clip.to_bytes() == rust.payload
    assert clip.is_playing() is True

    clip.seek(0.5)
    clip.volume(0.25)
    clip.rate(0.75)
    clip.pan(0.5)
    clip.pause()
    assert playback.seek_updates == [0.5]
    assert playback.volume_updates == [0.25]
    assert playback.rate_updates == [0.75]
    assert playback.pan_updates == [0.5]
    assert clip.time() == 0.5
    assert clip.is_paused() is True

    clip.no_loop()
    assert playback.looping() is False
    clip.close()
    assert playback.stop_calls == 1
    assert playback.close_calls == 1
    assert clip.is_playing() is False


def test_sound_delivers_natural_end_once_on_python_owner_poll() -> None:
    clip, rust = _sound()
    calls: list[sound_module.Sound] = []
    clip.on_ended(calls.append)
    clip.play()
    rust.playbacks[0].finish_naturally()

    assert clip.is_playing() is False
    assert clip.time() == pytest.approx(clip.duration)
    assert calls == [clip]


def test_sound_native_errors_are_actionable_capability_errors() -> None:
    clip, rust = _sound()
    rust.play_error = RuntimeError("no SDL device")

    with pytest.raises(BackendCapabilityError, match="SDL3 audio support"):
        clip.play()

    rust.play_error = None
    clip.play()
    rust.playbacks[0].error = "device lost"
    with pytest.raises(BackendCapabilityError, match="device lost"):
        clip.is_playing()


def test_generated_oscillator_builds_rust_asset_without_temp_file(monkeypatch) -> None:
    created: list[tuple[Path, bytes]] = []

    def _from_bytes(path: str | Path, payload: bytes) -> CanvasSound:
        created.append((Path(path), payload))
        return CanvasSound.from_rust(_FakeRustSound(str(path), payload))

    monkeypatch.setattr(CanvasSound, "from_bytes", _from_bytes)

    clip = gs.create_oscillator("sine", frequency=220.0, amplitude=0.5).to_sound(
        0.05, sample_rate=8_000
    )

    assert created[0][0] == Path("generated.wav")
    assert created[0][1].startswith(b"RIFF")
    assert clip.to_bytes() == created[0][1]
    assert not hasattr(sound_module, "_NativeAudioPlayer")
    assert not hasattr(sound_module, "_platform_play_command")


def test_sound_validation_and_native_diagnostics() -> None:
    clip, rust = _sound()
    for value in (-1.0, float("nan"), float("inf")):
        with pytest.raises(gs.ArgumentValidationError):
            clip.volume(value)
    for value in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(gs.ArgumentValidationError):
            clip.rate(value)
    with pytest.raises(gs.ArgumentValidationError):
        clip.seek(clip.duration + 0.1)
    with pytest.raises(gs.ArgumentValidationError):
        sound_module.Sound(
            CanvasSound.from_rust(rust),
            path=Path("tone.wav"),
            rust_sound=CanvasSound.from_rust(rust),
            player_factory=object(),
        )

    clip.play()
    diagnostics = clip.playback_diagnostics()
    assert diagnostics["blocks"] == 3
    assert diagnostics["rendered_frames"] == 96


def test_audio_analysis_and_synthesis_helpers_are_deterministic(monkeypatch):
    monkeypatch.setattr(
        CanvasSound,
        "from_bytes",
        lambda path, payload: CanvasSound.from_rust(_FakeRustSound(str(path), payload)),
    )
    amplitude = gs.create_amplitude([1.0, -1.0, 1.0, -1.0])
    assert amplitude.analyze() == pytest.approx(1.0)

    fft = gs.create_fft([1.0, 0.0, -1.0, 0.0], bins=2)
    assert len(fft.waveform()) == 4
    assert len(fft.analyze()) == 2

    oscillator = gs.create_oscillator("sine", frequency=1.0, amplitude=1.0)
    samples = oscillator.sample(0.25, sample_rate=4)
    assert samples.samples == pytest.approx((0.0,))
    generated_sound = samples.to_sound("buffer.wav")
    assert generated_sound.path == Path("buffer.wav")
    assert generated_sound.duration == pytest.approx(1.25)
    assert generated_sound.to_bytes().startswith(b"RIFF")

    envelope = gs.create_envelope(attack=0.5, decay=0.0, sustain=0.5, release=0.5)
    assert envelope.value_at(0.25) == pytest.approx(0.5)

    context = gs.get_audio_context()
    assert context["analysis"] is True
    assert context["synthesis"] is True
    assert context["playback"] == "rust-sdl3-mixer"
