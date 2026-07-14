"""Global-mode sound loading wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

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


class AudioContextInfo(TypedDict):
    """Capabilities reported by ``get_audio_context()``.

    Attributes:
        backend: Name of the active audio backend family.
        analysis: Whether amplitude/FFT analysis helpers are available.
        synthesis: Whether oscillator/envelope synthesis helpers are available.
        playback: Playback implementation used for loaded sounds.
        web_audio: ``False`` because Gummy Snake uses native Python/Rust runtime APIs.
    """

    backend: str
    analysis: bool
    synthesis: bool
    playback: str
    web_audio: bool


def load_sound(path: str | Path) -> Sound:
    """Load a sound file for playback and analysis.

    Args:
        path: Path to a sound file supported by the installed runtime.

    Returns:
        A ``Sound`` object with playback controls and metadata.
    """

    return _load_sound(path)


async def load_sound_async(path: str | Path) -> Sound:
    """Load a sound file without blocking an async sketch callback.

    Args:
        path: Path to a sound file supported by the installed runtime.

    Returns:
        A ``Sound`` object with playback controls and metadata.
    """

    return await _load_sound_async(path)


def create_audio(path: str | Path) -> Sound:
    """Create a sound object from an audio file.

    Args:
        path: Path to a sound file supported by the installed runtime.

    Returns:
        A ``Sound`` object with playback controls and metadata.
    """

    return _load_sound(path)


def get_audio_context() -> AudioContextInfo:
    """Return a small description of Gummy Snake's native audio capabilities.

    Returns:
        A dictionary describing the active backend and supported audio features.
    """

    return {
        "backend": "gummy-snake-native",
        "analysis": True,
        "synthesis": True,
        "playback": "rust-sdl3-mixer",
        "web_audio": False,
    }


__all__ = [
    "load_sound",
    "load_sound_async",
    "create_audio",
    "AudioContextInfo",
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
