"""Native, deterministic audio analysis and synthesis helpers."""

from __future__ import annotations

import io
import math
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gummysnake.assets.sound import Sound
from gummysnake.exceptions import ArgumentValidationError

WaveformName = Literal["sine", "square", "triangle", "sawtooth"]
FilterType = Literal["lowpass", "highpass"]


@dataclass(frozen=True, slots=True)
class AudioBuffer:
    samples: tuple[float, ...]
    sample_rate: int = 44_100

    @property
    def duration(self) -> float:
        return len(self.samples) / float(self.sample_rate)

    def to_sound(self, path: str | Path = "generated.wav") -> Sound:
        payload = _wav_bytes(self.samples, sample_rate=self.sample_rate)
        return Sound(_MemorySoundSource(payload, duration=self.duration), path=Path(path))


class _MemorySoundSource:
    def __init__(self, payload: bytes, *, duration: float) -> None:
        self._payload = payload
        self.duration = duration

    def to_bytes(self) -> bytes:
        return self._payload


class Amplitude:
    """RMS amplitude analyzer for sounds, audio buffers, or sample sequences."""

    def __init__(
        self, source: Sound | AudioBuffer | Sequence[float] | None = None, *, smoothing: float = 0.0
    ) -> None:
        self._source = source
        self._smoothing = _unit_interval(smoothing, "smoothing")
        self._level = 0.0

    def set_input(self, source: Sound | AudioBuffer | Sequence[float] | None) -> None:
        self._source = source

    def smoothing(self, value: float | None = None) -> float:
        if value is not None:
            self._smoothing = _unit_interval(value, "smoothing")
        return self._smoothing

    def analyze(self, samples: Sequence[float] | None = None) -> float:
        data = _samples_from_source(samples if samples is not None else self._source)
        raw = 0.0 if not data else math.sqrt(sum(sample * sample for sample in data) / len(data))
        self._level = self._level * self._smoothing + raw * (1.0 - self._smoothing)
        return self._level

    def level(self, samples: Sequence[float] | None = None) -> float:
        return self.analyze(samples)

    def get_level(self) -> float:
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
        if bins <= 0:
            raise ArgumentValidationError("FFT bins must be positive.")
        self._source = source
        self._bins = int(bins)
        self._smoothing = _unit_interval(smoothing, "smoothing")
        self._spectrum = tuple(0.0 for _ in range(self._bins))

    def set_input(self, source: Sound | AudioBuffer | Sequence[float] | None) -> None:
        self._source = source

    def waveform(self, samples: Sequence[float] | None = None) -> tuple[float, ...]:
        data = list(_samples_from_source(samples if samples is not None else self._source))
        target = self._bins * 2
        if len(data) >= target:
            return tuple(data[:target])
        return tuple(data + [0.0] * (target - len(data)))

    def spectrum(self, samples: Sequence[float] | None = None) -> tuple[float, ...]:
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
        return self.spectrum(samples)


class Oscillator:
    """Simple oscillator that can generate deterministic sample buffers or Sound objects."""

    def __init__(
        self, waveform: WaveformName = "sine", *, frequency: float = 440.0, amplitude: float = 1.0
    ) -> None:
        if waveform not in {"sine", "square", "triangle", "sawtooth"}:
            raise ArgumentValidationError("Unsupported oscillator waveform.")
        if frequency <= 0:
            raise ArgumentValidationError("Oscillator frequency must be positive.")
        self.waveform = waveform
        self.frequency = float(frequency)
        self.amplitude = _unit_interval(amplitude, "amplitude")
        self.is_started = False
        self.phase = 0.0

    def start(self) -> None:
        self.is_started = True

    def stop(self) -> None:
        self.is_started = False

    def freq(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Oscillator frequency must be positive.")
            self.frequency = float(value)
        return self.frequency

    def amp(self, value: float | None = None) -> float:
        if value is not None:
            self.amplitude = _unit_interval(value, "amplitude")
        return self.amplitude

    def sample(self, duration: float, *, sample_rate: int = 44_100) -> AudioBuffer:
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
    attack: float = 0.01
    decay: float = 0.1
    sustain: float = 0.7
    release: float = 0.2

    def __post_init__(self) -> None:
        if self.attack < 0 or self.decay < 0 or self.release < 0:
            raise ArgumentValidationError("Envelope times cannot be negative.")
        self.sustain = _unit_interval(self.sustain, "sustain")

    def set_adsr(self, attack: float, decay: float, sustain: float, release: float) -> None:
        self.attack = float(attack)
        self.decay = float(decay)
        self.sustain = float(sustain)
        self.release = float(release)
        self.__post_init__()

    def value_at(self, time_seconds: float, *, gate_duration: float | None = None) -> float:
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
        return AudioBuffer(
            tuple(
                sample * self.value_at(index / buffer.sample_rate, gate_duration=gate_duration)
                for index, sample in enumerate(buffer.samples)
            ),
            sample_rate=buffer.sample_rate,
        )


class AudioFilter:
    def __init__(
        self,
        filter_type: FilterType = "lowpass",
        *,
        frequency: float = 1_000.0,
        resonance: float = 0.0,
    ) -> None:
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
        self.sample_rate = int(sample_rate)
        self.is_started = False
        self._buffer = AudioBuffer((), sample_rate=self.sample_rate)

    def start(self) -> None:
        self.is_started = True

    def stop(self) -> None:
        self.is_started = False

    def push_samples(self, samples: Sequence[float]) -> None:
        self._buffer = AudioBuffer(
            tuple(float(sample) for sample in samples), sample_rate=self.sample_rate
        )

    def read(self, count: int | None = None) -> AudioBuffer:
        if count is None:
            return self._buffer
        samples = self._buffer.samples[: max(0, int(count))]
        return AudioBuffer(samples, sample_rate=self.sample_rate)


def create_amplitude(
    source: Sound | AudioBuffer | Sequence[float] | None = None, *, smoothing: float = 0.0
) -> Amplitude:
    return Amplitude(source, smoothing=smoothing)


def create_fft(
    source: Sound | AudioBuffer | Sequence[float] | None = None,
    *,
    bins: int = 1024,
    smoothing: float = 0.0,
) -> FFT:
    return FFT(source, bins=bins, smoothing=smoothing)


def create_oscillator(
    waveform: WaveformName = "sine", *, frequency: float = 440.0, amplitude: float = 1.0
) -> Oscillator:
    return Oscillator(waveform, frequency=frequency, amplitude=amplitude)


def create_envelope(
    attack: float = 0.01, decay: float = 0.1, sustain: float = 0.7, release: float = 0.2
) -> Envelope:
    return Envelope(attack=attack, decay=decay, sustain=sustain, release=release)


def create_filter(
    filter_type: FilterType = "lowpass", *, frequency: float = 1_000.0, resonance: float = 0.0
) -> AudioFilter:
    return AudioFilter(filter_type, frequency=frequency, resonance=resonance)


def create_audio_in(*, sample_rate: int = 44_100) -> AudioInput:
    return AudioInput(sample_rate=sample_rate)


def _samples_from_source(source: Sound | AudioBuffer | Sequence[float] | None) -> tuple[float, ...]:
    if source is None:
        return ()
    if isinstance(source, AudioBuffer):
        return source.samples
    if isinstance(source, Sound):
        return _decode_sound(source)
    return tuple(float(sample) for sample in source)


def _decode_sound(sound: Sound) -> tuple[float, ...]:
    payload = sound.to_bytes()
    try:
        with wave.open(io.BytesIO(payload), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            frames = wav.readframes(wav.getnframes())
    except wave.Error as exc:
        raise ArgumentValidationError("Sound analysis currently requires PCM WAV bytes.") from exc
    if sample_width not in {1, 2, 4}:
        raise ArgumentValidationError("Unsupported PCM sample width for sound analysis.")
    samples: list[float] = []
    step = sample_width * channels
    for offset in range(0, len(frames), step):
        channel_values = []
        for channel in range(channels):
            start = offset + channel * sample_width
            raw = frames[start : start + sample_width]
            if sample_width == 1:
                value = (raw[0] - 128) / 128.0
            else:
                value = int.from_bytes(raw, "little", signed=True) / float(
                    2 ** (sample_width * 8 - 1)
                )
            channel_values.append(value)
        samples.append(sum(channel_values) / len(channel_values))
    return tuple(samples)


def _wav_bytes(samples: Sequence[float], *, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        payload = bytearray()
        for sample in samples:
            clamped = max(-1.0, min(1.0, float(sample)))
            payload.extend(int(round(clamped * 32767.0)).to_bytes(2, "little", signed=True))
        wav.writeframes(bytes(payload))
    return output.getvalue()


def _unit_interval(value: float, name: str) -> float:
    numeric = float(value)
    if not 0.0 <= numeric <= 1.0:
        raise ArgumentValidationError(f"{name} must be between 0 and 1.")
    return numeric


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
