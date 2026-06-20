import wave
from pathlib import Path

import gummysnake as gs
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
        _FakePlayer.instances.append(self)

    def queue(self, source) -> None:
        self.queued.append(source)

    def play(self) -> None:
        self.play_calls += 1

    def pause(self) -> None:
        self.pause_calls += 1

    def seek(self, value: float) -> None:
        self.seek_calls.append(value)

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
    clip.volume(0.4)
    clip.rate(1.5)
    clip.pan(-0.25)
    clip.play()

    assert clip.duration == 1.25
    player = clip._player
    assert player is not None
    assert player.path == sound_path
    assert player.play_calls == 1
    assert player.volume == 0.4
    assert player.pitch == 1.5
    assert player.position == (-0.25, 0.0, 0.0)

    clip.pause()
    clip.stop()

    assert player.pause_calls >= 2
    assert player.seek_calls == [0.0]
    assert player.delete_calls == 1
    assert clip._player is None

    created = gs.create_audio(sound_path)
    assert isinstance(created, sound_module.Sound)
