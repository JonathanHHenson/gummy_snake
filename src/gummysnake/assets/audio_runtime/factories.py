from __future__ import annotations

from collections.abc import Sequence

from gummysnake.assets.audio_runtime.analysis import Amplitude, AudioBuffer, FFT
from gummysnake.assets.audio_runtime.synthesis import (
    AudioFilter,
    Envelope,
    FilterType,
    Oscillator,
    WaveformName,
)
from gummysnake.assets.sound import Sound


class AudioInput:
    """Headless-safe audio input buffer.

    Native microphone providers can feed this object later; today it supplies an
    explicit synthetic input buffer so analysis code is deterministic in CI.
    """

    def __init__(self, *, sample_rate: int = 44_100) -> None:
        """Create a deterministic audio input buffer.

        Args:
            sample_rate: Number of samples per second for pushed sample data.
        """
        self.sample_rate = int(sample_rate)
        self.is_started = False
        self._buffer = AudioBuffer((), sample_rate=self.sample_rate)

    def start(self) -> None:
        """Mark this input as started."""
        self.is_started = True

    def stop(self) -> None:
        """Mark this input as stopped."""
        self.is_started = False

    def push_samples(self, samples: Sequence[float]) -> None:
        """Replace the current input buffer with explicit samples.

        Args:
            samples: Sample values to make available through ``read()``.
        """
        self._buffer = AudioBuffer(
            tuple(float(sample) for sample in samples), sample_rate=self.sample_rate
        )

    def read(self, count: int | None = None) -> AudioBuffer:
        """Read samples from the current input buffer.

        Args:
            count: Optional maximum number of samples to return. Leave as
                ``None`` to read the full buffer.

        Returns:
            An ``AudioBuffer`` containing the requested samples.
        """
        if count is None:
            return self._buffer
        samples = self._buffer.samples[: max(0, int(count))]
        return AudioBuffer(samples, sample_rate=self.sample_rate)


def create_amplitude(
    source: Sound | AudioBuffer | Sequence[float] | None = None, *, smoothing: float = 0.0
) -> Amplitude:
    """Create an amplitude analyzer.

    Args:
        source: Optional sound, audio buffer, or samples to analyze by default.
        smoothing: Blend factor from ``0`` to ``1`` for slower level changes.

    Returns:
        A new ``Amplitude`` analyzer.
    """
    return Amplitude(source, smoothing=smoothing)


def create_fft(
    source: Sound | AudioBuffer | Sequence[float] | None = None,
    *,
    bins: int = 1024,
    smoothing: float = 0.0,
) -> FFT:
    """Create a frequency analyzer.

    Args:
        source: Optional sound, audio buffer, or samples to analyze by default.
        bins: Number of frequency bins to report.
        smoothing: Blend factor from ``0`` to ``1`` for slower spectrum changes.

    Returns:
        A new ``FFT`` analyzer.
    """
    return FFT(source, bins=bins, smoothing=smoothing)


def create_oscillator(
    waveform: WaveformName = "sine", *, frequency: float = 440.0, amplitude: float = 1.0
) -> Oscillator:
    """Create a deterministic oscillator.

    Args:
        waveform: Wave shape: ``"sine"``, ``"square"``, ``"triangle"``, or
            ``"sawtooth"``.
        frequency: Wave frequency in Hertz.
        amplitude: Output level from ``0`` to ``1``.

    Returns:
        A new ``Oscillator``.
    """
    return Oscillator(waveform, frequency=frequency, amplitude=amplitude)


def create_envelope(
    attack: float = 0.01, decay: float = 0.1, sustain: float = 0.7, release: float = 0.2
) -> Envelope:
    """Create an ADSR envelope.

    Args:
        attack: Seconds to rise from silence to full level.
        decay: Seconds to move from full level to sustain level.
        sustain: Held level from ``0`` to ``1``.
        release: Seconds to fade out after the note gate closes.

    Returns:
        A new ``Envelope``.
    """
    return Envelope(attack=attack, decay=decay, sustain=sustain, release=release)


def create_filter(
    filter_type: FilterType = "lowpass", *, frequency: float = 1_000.0, resonance: float = 0.0
) -> AudioFilter:
    """Create a low-pass or high-pass audio filter.

    Args:
        filter_type: ``"lowpass"`` or ``"highpass"``.
        frequency: Cutoff frequency in Hertz.
        resonance: Reserved for future richer filters and currently stored only.

    Returns:
        A new ``AudioFilter``.
    """
    return AudioFilter(filter_type, frequency=frequency, resonance=resonance)


def create_audio_in(*, sample_rate: int = 44_100) -> AudioInput:
    """Create a headless-safe audio input buffer.

    Args:
        sample_rate: Number of samples per second for pushed sample data.

    Returns:
        A new ``AudioInput``.
    """
    return AudioInput(sample_rate=sample_rate)


__all__ = [
    "AudioInput",
    "create_amplitude",
    "create_audio_in",
    "create_envelope",
    "create_fft",
    "create_filter",
    "create_oscillator",
]
