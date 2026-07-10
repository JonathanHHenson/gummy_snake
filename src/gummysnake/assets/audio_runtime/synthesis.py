from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from gummysnake.assets._audio_codec import unit_interval
from gummysnake.assets.audio_runtime.analysis import AudioBuffer
from gummysnake.assets.sound import Sound
from gummysnake.exceptions import ArgumentValidationError

WaveformName = Literal["sine", "square", "triangle", "sawtooth"]
FilterType = Literal["lowpass", "highpass"]


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


__all__ = ["AudioFilter", "Envelope", "FilterType", "Oscillator", "WaveformName"]
