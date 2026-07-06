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


class Oscillator:
    """Simple oscillator that can generate deterministic sample buffers or Sound objects."""

    def __init__(
        self, waveform: WaveformName = "sine", *, frequency: float = 440.0, amplitude: float = 1.0
    ) -> None:
        """Create an oscillator for deterministic sound synthesis.

        Args:
            waveform: Shape of the generated wave: ``"sine"``, ``"square"``,
                ``"triangle"``, or ``"sawtooth"``.
            frequency: Wave frequency in Hertz.
            amplitude: Output level from ``0`` to ``1``.
        """
        if waveform not in {"sine", "square", "triangle", "sawtooth"}:
            raise ArgumentValidationError("Unsupported oscillator waveform.")
        if frequency <= 0:
            raise ArgumentValidationError("Oscillator frequency must be positive.")
        self.waveform = waveform
        self.frequency = float(frequency)
        self.amplitude = unit_interval(amplitude, "amplitude")
        self.is_started = False
        self.phase = 0.0

    def start(self) -> None:
        """Mark the oscillator as started for sketch state tracking."""
        self.is_started = True

    def stop(self) -> None:
        """Mark the oscillator as stopped for sketch state tracking."""
        self.is_started = False

    def freq(self, value: float | None = None) -> float:
        """Read or update the oscillator frequency.

        Args:
            value: New positive frequency in Hertz. Leave as ``None`` to read the
                current value.

        Returns:
            Current frequency in Hertz.
        """
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Oscillator frequency must be positive.")
            self.frequency = float(value)
        return self.frequency

    def amp(self, value: float | None = None) -> float:
        """Read or update the oscillator amplitude.

        Args:
            value: New amplitude from ``0`` to ``1``. Leave as ``None`` to read
                the current value.

        Returns:
            Current amplitude.
        """
        if value is not None:
            self.amplitude = unit_interval(value, "amplitude")
        return self.amplitude

    def sample(self, duration: float, *, sample_rate: int = 44_100) -> AudioBuffer:
        """Generate oscillator samples.

        Args:
            duration: Number of seconds to generate.
            sample_rate: Number of samples per second.

        Returns:
            An ``AudioBuffer`` containing the generated mono samples.
        """
        if duration < 0:
            raise ArgumentValidationError("Oscillator sample duration cannot be negative.")
        count = int(round(duration * sample_rate))
        samples = []
        for index in range(count):
            phase = (self.phase + self.frequency * index / sample_rate) % 1.0
            samples.append(self._value_at_phase(phase) * self.amplitude)
        self.phase = (self.phase + self.frequency * duration) % 1.0
        return AudioBuffer(tuple(samples), sample_rate=sample_rate)

    def to_sound(self, duration: float, *, sample_rate: int = 44_100) -> Sound:
        """Generate a playable ``Sound`` from oscillator samples.

        Args:
            duration: Number of seconds to generate.
            sample_rate: Number of samples per second.

        Returns:
            A generated ``Sound`` encoded as in-memory WAV data.
        """
        return self.sample(duration, sample_rate=sample_rate).to_sound()

    def _value_at_phase(self, phase: float) -> float:
        if self.waveform == "sine":
            return math.sin(2.0 * math.pi * phase)
        if self.waveform == "square":
            return 1.0 if phase < 0.5 else -1.0
        if self.waveform == "triangle":
            return 4.0 * abs(phase - 0.5) - 1.0
        return 2.0 * phase - 1.0


@dataclass(slots=True)
class Envelope:
    """ADSR envelope used to shape generated audio.

    Attributes:
        attack: Seconds to rise from silence to full level.
        decay: Seconds to move from full level to sustain level.
        sustain: Held level from ``0`` to ``1`` while the note gate is open.
        release: Seconds to fade out after the note gate closes.
    """

    attack: float = 0.01
    decay: float = 0.1
    sustain: float = 0.7
    release: float = 0.2

    def __post_init__(self) -> None:
        if self.attack < 0 or self.decay < 0 or self.release < 0:
            raise ArgumentValidationError("Envelope times cannot be negative.")
        self.sustain = unit_interval(self.sustain, "sustain")

    def set_adsr(self, attack: float, decay: float, sustain: float, release: float) -> None:
        """Update all ADSR envelope values.

        Args:
            attack: Seconds to rise from silence to full level.
            decay: Seconds to move from full level to sustain level.
            sustain: Held level from ``0`` to ``1``.
            release: Seconds to fade out after the note gate closes.
        """
        self.attack = float(attack)
        self.decay = float(decay)
        self.sustain = float(sustain)
        self.release = float(release)
        self.__post_init__()

    def value_at(self, time_seconds: float, *, gate_duration: float | None = None) -> float:
        """Evaluate the envelope at a time point.

        Args:
            time_seconds: Seconds from the start of the note.
            gate_duration: Optional note length. When provided, release begins
                after this many seconds.

        Returns:
            Envelope level from ``0`` to ``1``.
        """
        t = max(0.0, float(time_seconds))
        if self.attack > 0 and t < self.attack:
            return t / self.attack
        t -= self.attack
        if self.decay > 0 and t < self.decay:
            return 1.0 + (self.sustain - 1.0) * (t / self.decay)
        if gate_duration is None or time_seconds < gate_duration:
            return self.sustain
        release_t = time_seconds - gate_duration
        if self.release <= 0:
            return 0.0
        return max(0.0, self.sustain * (1.0 - release_t / self.release))

    def apply(self, buffer: AudioBuffer, *, gate_duration: float | None = None) -> AudioBuffer:
        """Apply this envelope to every sample in a buffer.

        Args:
            buffer: Audio samples to shape.
            gate_duration: Optional note length used to start the release phase.

        Returns:
            A new ``AudioBuffer`` with the same sample rate and shaped samples.
        """
        return AudioBuffer(
            tuple(
                sample * self.value_at(index / buffer.sample_rate, gate_duration=gate_duration)
                for index, sample in enumerate(buffer.samples)
            ),
            sample_rate=buffer.sample_rate,
        )


class AudioFilter:
    """Simple one-pole filter for deterministic sample processing."""

    def __init__(
        self,
        filter_type: FilterType = "lowpass",
        *,
        frequency: float = 1_000.0,
        resonance: float = 0.0,
    ) -> None:
        """Create a low-pass or high-pass audio filter.

        Args:
            filter_type: ``"lowpass"`` to smooth high frequencies or
                ``"highpass"`` to reduce low frequencies.
            frequency: Cutoff frequency in Hertz.
            resonance: Reserved for future richer filters; stored for API
                compatibility but not used by this one-pole implementation.
        """
        if filter_type not in {"lowpass", "highpass"}:
            raise ArgumentValidationError("create_filter() supports 'lowpass' and 'highpass'.")
        if frequency <= 0:
            raise ArgumentValidationError("Filter frequency must be positive.")
        self.filter_type = filter_type
        self.frequency = float(frequency)
        self.resonance = float(resonance)

    def process(
        self, buffer: AudioBuffer | Sequence[float], *, sample_rate: int = 44_100
    ) -> AudioBuffer:
        """Filter an audio buffer or sample sequence.

        Args:
            buffer: ``AudioBuffer`` or raw sample sequence to process.
            sample_rate: Sample rate to use when ``buffer`` is a raw sequence.

        Returns:
            A new ``AudioBuffer`` with filtered samples.
        """
        source = (
            buffer
            if isinstance(buffer, AudioBuffer)
            else AudioBuffer(tuple(float(v) for v in buffer), sample_rate)
        )
        rc = 1.0 / (2.0 * math.pi * self.frequency)
        dt = 1.0 / source.sample_rate
        alpha = dt / (rc + dt)
        output: list[float] = []
        previous = 0.0
        previous_input = 0.0
        for sample in source.samples:
            if self.filter_type == "lowpass":
                previous = previous + alpha * (sample - previous)
                output.append(previous)
            else:
                high = alpha * (previous + sample - previous_input)
                output.append(high)
                previous = high
                previous_input = sample
        return AudioBuffer(tuple(output), sample_rate=source.sample_rate)


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


def _samples_from_source(source: Sound | AudioBuffer | Sequence[float] | None) -> tuple[float, ...]:
    if source is None:
        return ()
    if isinstance(source, AudioBuffer):
        return source.samples
    if isinstance(source, Sound):
        return decode_sound(source)
    return tuple(float(sample) for sample in source)


__all__ = [
    "Amplitude",
    "AudioBuffer",
    "AudioFilter",
    "AudioInput",
    "Envelope",
    "FFT",
    "Oscillator",
    "create_amplitude",
    "create_audio_in",
    "create_envelope",
    "create_fft",
    "create_filter",
    "create_oscillator",
]
