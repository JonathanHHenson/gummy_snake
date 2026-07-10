"""Native, deterministic audio analysis and synthesis helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gummysnake.assets._audio_codec import (
    MemorySoundSource,
    decode_sound,
    unit_interval,
    wav_bytes,
)
from gummysnake.assets.sound import Sound
from gummysnake.exceptions import ArgumentValidationError

WaveformName = Literal["sine", "square", "triangle", "sawtooth"]
FilterType = Literal["lowpass", "highpass"]


@dataclass(frozen=True, slots=True)
class AudioBuffer:
    """Immutable mono audio samples.

    Attributes:
        samples: Normalized sample values, usually between ``-1.0`` and ``1.0``.
        sample_rate: Number of samples per second.
    """

    samples: tuple[float, ...]
    sample_rate: int = 44_100

    @property
    def duration(self) -> float:
        """Length of the buffer in seconds.

        Returns:
            ``len(samples) / sample_rate`` as a floating-point number.
        """
        return len(self.samples) / float(self.sample_rate)

    def to_sound(self, path: str | Path = "generated.wav") -> Sound:
        """Encode this buffer as a playable ``Sound``.

        Args:
            path: Display path to attach to the generated sound. The bytes stay
                in memory until playback needs a temporary file.

        Returns:
            A ``Sound`` containing this buffer encoded as 16-bit PCM WAV data.
        """
        payload = wav_bytes(self.samples, sample_rate=self.sample_rate)
        return Sound(MemorySoundSource(payload, duration=self.duration), path=Path(path))


class Amplitude:
    """RMS amplitude analyzer for sounds, audio buffers, or sample sequences."""

    def __init__(
        self, source: Sound | AudioBuffer | Sequence[float] | None = None, *, smoothing: float = 0.0
    ) -> None:
        """Create an RMS amplitude analyzer.

        Args:
            source: Optional sound, audio buffer, or sample sequence to analyze
                when ``analyze()`` is called without samples.
            smoothing: Blend factor from ``0`` to ``1``. Larger values make the
                reported level change more slowly.
        """
        self._source = source
        self._smoothing = unit_interval(smoothing, "smoothing")
        self._level = 0.0

    def set_input(self, source: Sound | AudioBuffer | Sequence[float] | None) -> None:
        """Replace the default input used by ``analyze()``.

        Args:
            source: Sound, audio buffer, sample sequence, or ``None`` for silence.
        """
        self._source = source

    def smoothing(self, value: float | None = None) -> float:
        """Read or update the smoothing amount.

        Args:
            value: New smoothing amount from ``0`` to ``1``. Leave as ``None`` to
                read the current value.

        Returns:
            The current smoothing amount.
        """
        if value is not None:
            self._smoothing = unit_interval(value, "smoothing")
        return self._smoothing

    def analyze(self, samples: Sequence[float] | None = None) -> float:
        """Measure RMS amplitude.

        Args:
            samples: Optional sample sequence to analyze for this call. When
                omitted, the analyzer uses the current input source.

        Returns:
            Smoothed RMS level between silence and the input amplitude.
        """
        data = _samples_from_source(samples if samples is not None else self._source)
        raw = 0.0 if not data else math.sqrt(sum(sample * sample for sample in data) / len(data))
        self._level = self._level * self._smoothing + raw * (1.0 - self._smoothing)
        return self._level

    def level(self, samples: Sequence[float] | None = None) -> float:
        """Alias for ``analyze()``.

        Args:
            samples: Optional sample sequence to analyze for this call.

        Returns:
            The current smoothed RMS level.
        """
        return self.analyze(samples)

    def get_level(self) -> float:
        """Return the most recently analyzed level.

        Returns:
            Last value produced by ``analyze()`` or ``0.0`` before analysis.
        """
        return self._level


class FFT:
    """Small deterministic DFT analyzer for tests and headless audio-reactive sketches."""

    def __init__(
        self,
        source: Sound | AudioBuffer | Sequence[float] | None = None,
        *,
        bins: int = 1024,
        smoothing: float = 0.0,
    ) -> None:
        """Create a deterministic frequency analyzer.

        Args:
            source: Optional sound, audio buffer, or sample sequence to analyze
                when methods are called without samples.
            bins: Number of frequency bins to report.
            smoothing: Blend factor from ``0`` to ``1``. Larger values make the
                spectrum change more slowly.
        """
        if bins <= 0:
            raise ArgumentValidationError("FFT bins must be positive.")
        self._source = source
        self._bins = int(bins)
        self._smoothing = unit_interval(smoothing, "smoothing")
        self._spectrum = tuple(0.0 for _ in range(self._bins))

    def set_input(self, source: Sound | AudioBuffer | Sequence[float] | None) -> None:
        """Replace the default input used by ``waveform()`` and ``spectrum()``.

        Args:
            source: Sound, audio buffer, sample sequence, or ``None`` for silence.
        """
        self._source = source

    def waveform(self, samples: Sequence[float] | None = None) -> tuple[float, ...]:
        """Return a fixed-size waveform window.

        Args:
            samples: Optional sample sequence to use for this call. When omitted,
                the analyzer uses the current input source.

        Returns:
            Exactly ``bins * 2`` samples, truncated or padded with zeros.
        """
        data = list(_samples_from_source(samples if samples is not None else self._source))
        target = self._bins * 2
        if len(data) >= target:
            return tuple(data[:target])
        return tuple(data + [0.0] * (target - len(data)))

    def spectrum(self, samples: Sequence[float] | None = None) -> tuple[float, ...]:
        """Return normalized frequency magnitudes.

        Args:
            samples: Optional sample sequence to analyze for this call.

        Returns:
            ``bins`` smoothed magnitude values clamped to ``0`` through ``1``.
        """
        wave_samples = self.waveform(samples)
        n = len(wave_samples)
        magnitudes: list[float] = []
        for k in range(self._bins):
            real = 0.0
            imag = 0.0
            for index, sample in enumerate(wave_samples):
                angle = -2.0 * math.pi * k * index / n
                real += sample * math.cos(angle)
                imag += sample * math.sin(angle)
            magnitudes.append(min(1.0, math.sqrt(real * real + imag * imag) / max(1.0, n / 2.0)))
        self._spectrum = tuple(
            old * self._smoothing + new * (1.0 - self._smoothing)
            for old, new in zip(self._spectrum, magnitudes, strict=True)
        )
        return self._spectrum

    def analyze(self, samples: Sequence[float] | None = None) -> tuple[float, ...]:
        """Alias for ``spectrum()``.

        Args:
            samples: Optional sample sequence to analyze for this call.

        Returns:
            The current smoothed frequency spectrum.
        """
        return self.spectrum(samples)


def _samples_from_source(source: Sound | AudioBuffer | Sequence[float] | None) -> tuple[float, ...]:
    if source is None:
        return ()
    if isinstance(source, AudioBuffer):
        return source.samples
    if isinstance(source, Sound):
        return decode_sound(source)
    return tuple(float(sample) for sample in source)


__all__ = ["Amplitude", "AudioBuffer", "FFT"]
