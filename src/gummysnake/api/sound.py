"""Global-mode sound loading wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.audio import (
    FFT,
    Amplitude,
    AudioBuffer,
    AudioFilter,
    AudioInput,
    Envelope,
    Oscillator,
    create_amplitude,
    create_audio_in,
    create_envelope,
    create_fft,
    create_filter,
    create_oscillator,
)
from gummysnake.assets.sound import Sound
from gummysnake.assets.sound import load_sound as _load_sound
from gummysnake.assets.sound import load_sound_async as _load_sound_async


def load_sound(path: str | Path) -> Sound:
    return _load_sound(path)


async def load_sound_async(path: str | Path) -> Sound:
    return await _load_sound_async(path)


def create_audio(path: str | Path) -> Sound:
    return _load_sound(path)


def get_audio_context() -> dict[str, object]:
    return {
        "backend": "gummy-snake-native",
        "analysis": True,
        "synthesis": True,
        "playback": "platform-player",
        "web_audio": False,
    }


__all__ = [
    "load_sound",
    "load_sound_async",
    "create_audio",
    "Amplitude",
    "AudioBuffer",
    "FFT",
    "Oscillator",
    "Envelope",
    "AudioFilter",
    "AudioInput",
    "create_amplitude",
    "create_fft",
    "create_oscillator",
    "create_envelope",
    "create_filter",
    "create_audio_in",
    "get_audio_context",
]
