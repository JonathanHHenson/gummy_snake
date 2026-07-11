"""Sound and audio-analysis forwards for object-mode sketches."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gummysnake.api.sound import AudioContextInfo
from gummysnake.api.sound import get_audio_context as _get_audio_context
from gummysnake.assets.audio import (
    FFT,
    Amplitude,
    AudioBuffer,
    AudioFilter,
    AudioInput,
    Envelope,
    FilterType,
    Oscillator,
    WaveformName,
)
from gummysnake.assets.audio import create_amplitude as _create_amplitude
from gummysnake.assets.audio import create_audio_in as _create_audio_in
from gummysnake.assets.audio import create_envelope as _create_envelope
from gummysnake.assets.audio import create_fft as _create_fft
from gummysnake.assets.audio import create_filter as _create_filter
from gummysnake.assets.audio import create_oscillator as _create_oscillator
from gummysnake.assets.sound import Sound
from gummysnake.assets.sound import load_sound as _load_sound
from gummysnake.assets.sound import load_sound_async as _load_sound_async
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeAudioMixin(SketchFacadeBaseMixin):
    """Load sounds and create object-mode audio helpers."""

    __facade_doc_topic__ = "Load sounds or configure audio playback and analysis for this sketch."

    def load_sound(self, path: str | Path) -> Sound:
        return _load_sound(path)

    async def load_sound_async(self, path: str | Path) -> Sound:
        return await _load_sound_async(path)

    def create_audio(self, path: str | Path) -> Sound:
        return _load_sound(path)

    def create_amplitude(
        self, source: Sound | AudioBuffer | Sequence[float] | None = None, *, smoothing: float = 0.0
    ) -> Amplitude:
        return _create_amplitude(source, smoothing=smoothing)

    def create_fft(
        self,
        source: Sound | AudioBuffer | Sequence[float] | None = None,
        *,
        bins: int = 1024,
        smoothing: float = 0.0,
    ) -> FFT:
        return _create_fft(source, bins=bins, smoothing=smoothing)

    def create_oscillator(
        self, waveform: WaveformName = "sine", *, frequency: float = 440.0, amplitude: float = 1.0
    ) -> Oscillator:
        return _create_oscillator(waveform, frequency=frequency, amplitude=amplitude)

    def create_envelope(
        self, attack: float = 0.01, decay: float = 0.1, sustain: float = 0.7, release: float = 0.2
    ) -> Envelope:
        return _create_envelope(attack=attack, decay=decay, sustain=sustain, release=release)

    def create_filter(
        self,
        filter_type: FilterType = "lowpass",
        *,
        frequency: float = 1_000.0,
        resonance: float = 0.0,
    ) -> AudioFilter:
        return _create_filter(filter_type, frequency=frequency, resonance=resonance)

    def create_audio_in(self, *, sample_rate: int = 44_100) -> AudioInput:
        return _create_audio_in(sample_rate=sample_rate)

    def get_audio_context(self) -> AudioContextInfo:
        return _get_audio_context()
