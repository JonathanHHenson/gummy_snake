"""Private PCM WAV helpers for deterministic audio features."""

from __future__ import annotations

import io
import wave
from collections.abc import Sequence

from gummysnake.assets.sound import Sound
from gummysnake.exceptions import ArgumentValidationError


class MemorySoundSource:
    """In-memory byte source accepted by :class:`gummysnake.assets.sound.Sound`."""

    __slots__ = ("_payload", "duration")

    def __init__(self, payload: bytes, *, duration: float) -> None:
        self._payload = payload
        self.duration = duration

    def to_bytes(self) -> bytes:
        """Return the stored audio payload."""
        return self._payload


def decode_sound(sound: Sound) -> tuple[float, ...]:
    """Decode mono sample values from a PCM WAV sound."""
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
    return _decode_pcm_frames(frames, channels=channels, sample_width=sample_width)


def wav_bytes(samples: Sequence[float], *, sample_rate: int) -> bytes:
    """Encode normalized mono samples as 16-bit PCM WAV bytes."""
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(_pcm16_payload(samples))
    return output.getvalue()


def unit_interval(value: float, name: str) -> float:
    """Validate and return a floating-point value between 0 and 1."""
    numeric = float(value)
    if not 0.0 <= numeric <= 1.0:
        raise ArgumentValidationError(f"{name} must be between 0 and 1.")
    return numeric


def _decode_pcm_frames(frames: bytes, *, channels: int, sample_width: int) -> tuple[float, ...]:
    samples: list[float] = []
    step = sample_width * channels
    for offset in range(0, len(frames), step):
        channel_values = []
        for channel in range(channels):
            start = offset + channel * sample_width
            channel_values.append(_decode_pcm_sample(frames[start : start + sample_width]))
        samples.append(sum(channel_values) / len(channel_values))
    return tuple(samples)


def _decode_pcm_sample(raw: bytes) -> float:
    if len(raw) == 1:
        return (raw[0] - 128) / 128.0
    return int.from_bytes(raw, "little", signed=True) / float(2 ** (len(raw) * 8 - 1))


def _pcm16_payload(samples: Sequence[float]) -> bytes:
    payload = bytearray()
    for sample in samples:
        clamped = max(-1.0, min(1.0, float(sample)))
        payload.extend(int(round(clamped * 32767.0)).to_bytes(2, "little", signed=True))
    return bytes(payload)
