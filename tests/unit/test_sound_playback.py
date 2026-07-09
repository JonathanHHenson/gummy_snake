import wave
from pathlib import Path

import pytest

import gummysnake as gs
from gummysnake import BackendCapabilityError
from gummysnake.assets import sound as sound_module


class _FakePlayer:
    instances = []

    def __init__(self, path: Path) -> None:
        self.path = path
        self.queued = []
        self.play_calls = 0
        self.pause_calls = 0
        self.seek_calls = []
        self.delete_calls = 0
        self.volume = 0.0
        self.pitch = 0.0
        self.position = (0.0, 0.0, 0.0)
        self.loop = False
        self._time = 0.0
        _FakePlayer.instances.append(self)

    def queue(self, source) -> None:
        self.queued.append(source)

    def play(self) -> None:
        self.play_calls += 1

    def pause(self) -> None:
        self.pause_calls += 1

    def seek(self, value: float) -> None:
        self.seek_calls.append(value)
        self._time = value

    def time(self) -> float:
        return self._time

    def delete(self) -> None:
        self.delete_calls += 1


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 10000)


def test_load_sound_and_create_audio_use_backend_neutral_player(monkeypatch, tmp_path: Path):
    sound_path = tmp_path / "tone.wav"
    _write_wav(sound_path)
    _FakePlayer.instances.clear()
    monkeypatch.setattr(sound_module, "_NativeAudioPlayer", _FakePlayer)

    clip = gs.load_sound(sound_path)

    assert isinstance(clip._rust_sound, sound_module.CanvasSound)
    assert clip.byte_len == sound_path.stat().st_size
    assert clip.to_bytes() == sound_path.read_bytes()

    clip.volume(0.4)
    clip.rate(1.5)
    clip.pan(-0.25)
    clip.looping(True)
    clip.play()
    clip.seek(0.5)

    assert clip.duration == 1.25
    player = clip._player
    assert player is not None
    assert player.path == sound_path
    assert player.play_calls == 1
    assert player.volume == 0.4
    assert player.pitch == 1.5
    assert player.position == (-0.25, 0.0, 0.0)
    assert player.loop is True
    assert player.seek_calls == [0.5]
    assert clip.time() == 0.5
    assert clip.is_playing() is True

    clip.pause()
    assert clip.is_paused() is True
    clip.no_loop()
    assert clip.looping() is False
    clip.close()

    assert player.pause_calls >= 2
    assert player.seek_calls == [0.5, 0.0]
    assert player.delete_calls == 1
    assert clip._player is None

    created = gs.create_audio(sound_path)
    assert isinstance(created, sound_module.Sound)

    import gummysnake.assets as assets

    assert assets.load_sound is sound_module.load_sound
    assert assets.load_sound_async is sound_module.load_sound_async


def test_sound_play_preserves_specific_backend_capability_errors(tmp_path: Path):
    sound_path = tmp_path / "tone.wav"
    _write_wav(sound_path)

    class MissingPlayer(_FakePlayer):
        def play(self) -> None:
            raise BackendCapabilityError("Audio playback requires an available platform player.")

    clip = sound_module.Sound(object(), path=sound_path, player_factory=MissingPlayer)

    with pytest.raises(BackendCapabilityError, match="available platform player"):
        clip.play()


def test_native_audio_player_cleanup_stops_spawned_process(monkeypatch, tmp_path: Path):
    sound_path = tmp_path / "tone.wav"
    _write_wav(sound_path)

    class _FakeProcess:
        def __init__(self) -> None:
            self.terminate_calls = 0
            self.wait_calls = 0
            self.kill_calls = 0
            self.is_running = True

        def poll(self):
            return None if self.is_running else 0

        def terminate(self) -> None:
            self.terminate_calls += 1
            self.is_running = False

        def wait(self, timeout=None):
            self.wait_calls += 1
            return 0

        def kill(self) -> None:
            self.kill_calls += 1
            self.is_running = False

    process = _FakeProcess()
    monkeypatch.setattr(
        sound_module, "_platform_play_command", lambda path: ["fake-player", str(path)]
    )
    monkeypatch.setattr(sound_module.subprocess, "Popen", lambda *args, **kwargs: process)

    player = sound_module._NativeAudioPlayer(sound_path)
    player.play()
    sound_module._stop_active_native_audio_players()
    sound_module._stop_active_native_audio_players()

    assert process.terminate_calls == 1
    assert process.wait_calls == 1
    assert process.kill_calls == 0


def test_generated_oscillator_sound_materializes_temp_file_for_playback(monkeypatch):
    _FakePlayer.instances.clear()
    monkeypatch.setattr(sound_module, "_NativeAudioPlayer", _FakePlayer)

    clip = gs.create_oscillator("sine", frequency=220.0, amplitude=0.5).to_sound(
        0.05, sample_rate=8000
    )
    payload = clip.to_bytes()

    clip.play()

    player = clip._player
    assert player is not None
    assert player.path != Path("generated.wav")
    assert player.path.exists()
    assert player.path.read_bytes() == payload
    temporary_path = player.path

    clip.stop()

    assert not temporary_path.exists()


def test_audio_analysis_and_synthesis_helpers_are_deterministic():
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
    assert generated_sound.duration == pytest.approx(samples.duration)
    assert generated_sound.to_bytes().startswith(b"RIFF")

    envelope = gs.create_envelope(attack=0.5, decay=0.0, sustain=0.5, release=0.5)
    assert envelope.value_at(0.25) == pytest.approx(0.5)

    audio_filter = gs.create_filter("lowpass", frequency=1000.0)
    filtered = audio_filter.process([1.0, 0.0, 0.0], sample_rate=8000)
    assert len(filtered.samples) == 3

    audio_in = gs.create_audio_in(sample_rate=8000)
    audio_in.start()
    audio_in.push_samples([0.1, 0.2])
    assert audio_in.read().sample_rate == 8000
    assert audio_in.read().samples == (0.1, 0.2)

    context = gs.get_audio_context()
    assert context["analysis"] is True
    assert context["synthesis"] is True
