"""Deterministic PCM, signal, envelope, digest, and failure oracles."""

from __future__ import annotations

import io
import json
import math
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256


class SynthOracleError(AssertionError):
    """A Synth workload completed through the expected route but produced invalid output."""


@dataclass(frozen=True, slots=True)
class PcmSignal:
    """Decoded signed PCM normalized to floating-point channels."""

    sample_rate: int
    sample_width: int
    channels: int
    left: tuple[float, ...]
    right: tuple[float, ...]

    @property
    def frames(self) -> int:
        return min(len(self.left), len(self.right))

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate


@dataclass(frozen=True, slots=True)
class SignalSummary:
    """Stable output statistics emitted in suite diagnostics."""

    digest: str
    frames: int
    sample_rate: int
    peak: float
    rms: float
    dc: float
    left_rms: float
    right_rms: float
    correlation: float
    spectral_bands: Mapping[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "digest": self.digest,
            "frames": self.frames,
            "sample_rate": self.sample_rate,
            "peak": self.peak,
            "rms": self.rms,
            "dc": self.dc,
            "left_rms": self.left_rms,
            "right_rms": self.right_rms,
            "correlation": self.correlation,
            "spectral_bands": dict(self.spectral_bands),
        }


def _decode_sample(raw: bytes, sample_width: int) -> float:
    if sample_width == 1:
        return (raw[0] - 128.0) / 128.0
    if sample_width == 2:
        return int.from_bytes(raw, "little", signed=True) / 32768.0
    if sample_width == 4:
        return int.from_bytes(raw, "little", signed=True) / 2147483648.0
    raise SynthOracleError(f"unsupported PCM width in oracle: {sample_width}")


def decode_pcm_wav(payload: bytes | bytearray | memoryview) -> PcmSignal:
    """Decode mono/stereo 8/16/32-bit PCM WAV without a third-party dependency."""

    data = bytes(payload)
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            channels = reader.getnchannels()
            sample_width = reader.getsampwidth()
            sample_rate = reader.getframerate()
            frame_count = reader.getnframes()
            compression = reader.getcomptype()
            frames = reader.readframes(frame_count)
    except (EOFError, wave.Error) as error:
        raise SynthOracleError(f"output is not a valid PCM WAV: {error}") from error
    if compression != "NONE" or channels not in (1, 2) or sample_width not in (1, 2, 4):
        raise SynthOracleError("output WAV must be uncompressed mono/stereo 8/16/32-bit PCM")
    step = channels * sample_width
    if len(frames) != frame_count * step:
        raise SynthOracleError("WAV data length does not match its declared frame count")
    left: list[float] = []
    right: list[float] = []
    for offset in range(0, len(frames), step):
        left_sample = _decode_sample(frames[offset : offset + sample_width], sample_width)
        left.append(left_sample)
        if channels == 1:
            right.append(left_sample)
        else:
            right.append(
                _decode_sample(
                    frames[offset + sample_width : offset + sample_width * 2], sample_width
                )
            )
    return PcmSignal(sample_rate, sample_width, channels, tuple(left), tuple(right))


def _rms(values: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in values) / max(1, len(values)))


def _spectral_bands(values: Sequence[float], sample_rate: int) -> dict[str, float]:
    """Return deterministic coarse DFT energy using a bounded analysis window."""

    count = min(len(values), 1024)
    if count == 0:
        return {"sub": 0.0, "low": 0.0, "mid": 0.0, "high": 0.0}
    samples = values[:count]
    bands = {"sub": 0.0, "low": 0.0, "mid": 0.0, "high": 0.0}
    max_bin = min(count // 2, 192)
    for bin_index in range(1, max_bin + 1):
        real = 0.0
        imag = 0.0
        for index, sample in enumerate(samples):
            angle = math.tau * bin_index * index / count
            real += sample * math.cos(angle)
            imag -= sample * math.sin(angle)
        energy = (real * real + imag * imag) / (count * count)
        frequency = bin_index * sample_rate / count
        if frequency < 120.0:
            bands["sub"] += energy
        elif frequency < 600.0:
            bands["low"] += energy
        elif frequency < 2_500.0:
            bands["mid"] += energy
        else:
            bands["high"] += energy
    return bands


def summarize_wav(payload: bytes | bytearray | memoryview) -> SignalSummary:
    """Validate and summarize deterministic WAV output."""

    data = bytes(payload)
    pcm = decode_pcm_wav(data)
    values = (*pcm.left, *pcm.right)
    peak = max((abs(value) for value in values), default=0.0)
    left_rms = _rms(pcm.left)
    right_rms = _rms(pcm.right)
    rms = _rms(values)
    dc = sum(values) / max(1, len(values))
    cross = sum(left * right for left, right in zip(pcm.left, pcm.right, strict=True))
    denominator = math.sqrt(
        sum(value * value for value in pcm.left) * sum(value * value for value in pcm.right)
    )
    correlation = cross / denominator if denominator > 1e-15 else 0.0
    if not all(math.isfinite(value) for value in (peak, rms, dc, correlation)):
        raise SynthOracleError("PCM summary contains a non-finite value")
    return SignalSummary(
        "sha256:" + sha256(data).hexdigest(),
        pcm.frames,
        pcm.sample_rate,
        peak,
        rms,
        dc,
        left_rms,
        right_rms,
        correlation,
        _spectral_bands(pcm.left, pcm.sample_rate),
    )


def assert_wav_contract(
    payload: bytes | bytearray | memoryview,
    *,
    sample_rate: int,
    minimum_frames: int = 1,
    require_signal: bool = True,
) -> SignalSummary:
    """Require exact format/rate bounds, finite PCM, and an optional audible signal."""

    summary = summarize_wav(payload)
    if summary.sample_rate != sample_rate:
        raise SynthOracleError(f"WAV sample rate expected {sample_rate}, got {summary.sample_rate}")
    if summary.frames < minimum_frames:
        raise SynthOracleError(
            f"WAV frame count expected at least {minimum_frames}, got {summary.frames}"
        )
    if summary.peak > 1.0 or summary.rms > 1.0:
        raise SynthOracleError("WAV output exceeds normalized PCM range")
    if require_signal and summary.peak <= 1e-5:
        raise SynthOracleError("WAV output is unexpectedly silent")
    return summary


def assert_repeatable(first: bytes, second: bytes, *, label: str) -> str:
    """Require exact same-build bytes for deterministic production routes."""

    if first != second:
        raise SynthOracleError(f"{label} was not byte-exact across repeated renders")
    return "sha256:" + sha256(first).hexdigest()


def assert_frequency(
    payload: bytes,
    *,
    expected_hz: float,
    tolerance_hz: float,
) -> float:
    """Estimate frequency from positive zero crossings away from envelope boundaries."""

    pcm = decode_pcm_wav(payload)
    values = pcm.left
    start = min(len(values) // 5, 128)
    end = max(start, len(values) - start)
    crossings = [
        index for index in range(start + 1, end) if values[index - 1] <= 0.0 < values[index]
    ]
    if len(crossings) < 2:
        raise SynthOracleError("frequency oracle found too few positive zero crossings")
    periods = sorted(right - left for left, right in zip(crossings, crossings[1:], strict=False))
    midpoint = len(periods) // 2
    median_period = (
        periods[midpoint] if len(periods) % 2 else (periods[midpoint - 1] + periods[midpoint]) / 2.0
    )
    estimate = pcm.sample_rate / median_period
    if abs(estimate - expected_hz) > tolerance_hz:
        raise SynthOracleError(
            f"frequency expected {expected_hz}±{tolerance_hz} Hz, got {estimate:.3f} Hz"
        )
    return estimate


def assert_envelope_shape(payload: bytes) -> Mapping[str, float]:
    """Require attack growth and release decay using absolute-amplitude windows."""

    pcm = decode_pcm_wav(payload)
    values = tuple(abs(value) for value in pcm.left)
    if len(values) < 32:
        raise SynthOracleError("envelope oracle requires at least 32 PCM frames")
    quarter = len(values) // 4
    windows = {
        "attack": sum(values[:quarter]) / quarter,
        "middle": sum(values[quarter : quarter * 3]) / (quarter * 2),
        "release": sum(values[quarter * 3 :]) / max(1, len(values) - quarter * 3),
    }
    if not windows["attack"] < windows["middle"]:
        raise SynthOracleError(f"envelope attack did not grow into sustain: {windows}")
    if not windows["release"] < windows["middle"]:
        raise SynthOracleError(f"envelope release did not decay from sustain: {windows}")
    return windows


def semantic_plan_digest(plan_dict: Mapping[str, object]) -> str:
    """Hash plan semantics while normalizing process-global implementation identities."""

    normalized = _normalize_plan_value(plan_dict, key=None)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + sha256(payload).hexdigest()


def _normalize_plan_value(value: object, *, key: str | None) -> object:
    if key in {"node_id", "order", "instance", "target_instance", "id", "target_id"}:
        return "<plan-local-identity>"
    if isinstance(value, Mapping):
        return {
            str(child_key): _normalize_plan_value(child_value, key=str(child_key))
            for child_key, child_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list | tuple):
        return [_normalize_plan_value(item, key=key) for item in value]
    return value


def assert_expected_failure(
    operation: Callable[[], object],
    *,
    tokens: Sequence[str],
) -> str:
    """Require an actionable failure containing at least one expected diagnostic token."""

    try:
        operation()
    except Exception as error:
        message = str(error)
        lowered = message.lower()
        if not any(token.lower() in lowered for token in tokens):
            raise SynthOracleError(
                f"failure did not contain any expected token {tuple(tokens)!r}: {message}"
            ) from error
        return f"{type(error).__name__}: {message}"
    raise SynthOracleError("operation unexpectedly succeeded instead of failing closed")


def pcm_data(payload: bytes) -> bytes:
    """Return canonical interleaved PCM bytes for block-partition checks."""

    with wave.open(io.BytesIO(payload), "rb") as reader:
        return reader.readframes(reader.getnframes())


__all__ = [
    "PcmSignal",
    "SignalSummary",
    "SynthOracleError",
    "assert_envelope_shape",
    "assert_expected_failure",
    "assert_frequency",
    "assert_repeatable",
    "assert_wav_contract",
    "decode_pcm_wav",
    "pcm_data",
    "semantic_plan_digest",
    "summarize_wav",
]
