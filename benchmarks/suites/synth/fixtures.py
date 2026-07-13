"""Deterministic runtime-generated signals and PCM WAV fixtures for Synth benchmarks."""

from __future__ import annotations

import math
import tempfile
import wave
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SignalFixture:
    """One bounded mono or stereo floating-point signal."""

    name: str
    sample_rate: int
    left: tuple[float, ...]
    right: tuple[float, ...]

    @property
    def frames(self) -> int:
        return min(len(self.left), len(self.right))

    @property
    def channels(self) -> int:
        return 1 if self.left == self.right else 2

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate


@dataclass(frozen=True, slots=True)
class FixtureManifestEntry:
    """Reviewed structural and signal identity for generated 16-bit PCM."""

    name: str
    frames: int
    channels: int
    sample_rate: int
    duration_seconds: float
    byte_length: int
    sha256: str
    peak: float
    rms: float
    dc: float
    spectral_bands: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class GeneratedSampleFiles:
    """Temporary generated WAV variants consumed by the Rust sample decoder."""

    root: Path
    paths: Mapping[str, Path]


def _noise_values(count: int, seed: int) -> tuple[float, ...]:
    state = seed & 0xFFFFFFFF
    values: list[float] = []
    for _ in range(count):
        state ^= state << 13 & 0xFFFFFFFF
        state ^= state >> 17
        state ^= state << 5 & 0xFFFFFFFF
        values.append(((state & 0xFFFF) / 32767.5 - 1.0) * 0.55)
    return tuple(values)


def _chirp(index: int, sample_rate: int, duration: float) -> float:
    time = index / sample_rate
    start_hz = 80.0
    end_hz = min(4_000.0, sample_rate * 0.4)
    slope = (end_hz - start_hz) / duration
    return 0.55 * math.sin(math.tau * (start_hz * time + 0.5 * slope * time * time))


def generate_signal(
    kind: str,
    *,
    sample_rate: int = 16_000,
    duration_seconds: float = 0.125,
) -> SignalFixture:
    """Generate a canonical bounded signal without files, network, or random globals."""

    if sample_rate < 1 or not 0.001 <= duration_seconds <= 10.0:
        raise ValueError("signal fixture rate and duration must be positive and bounded")
    count = max(1, round(sample_rate * duration_seconds))
    zeros = (0.0,) * count
    if kind == "silence":
        return SignalFixture(kind, sample_rate, zeros, zeros)
    if kind == "impulse-mono":
        mono = (0.9, *([0.0] * (count - 1)))
        return SignalFixture(kind, sample_rate, mono, mono)
    if kind == "impulse-stereo":
        left = (0.9, *([0.0] * (count - 1)))
        right_index = min(count - 1, 7)
        right = tuple(0.65 if index == right_index else 0.0 for index in range(count))
        return SignalFixture(kind, sample_rate, left, right)
    if kind == "sine":
        mono = tuple(
            0.55 * math.sin(math.tau * 440.0 * index / sample_rate) for index in range(count)
        )
        return SignalFixture(kind, sample_rate, mono, mono)
    if kind == "dual-tone":
        mono = tuple(
            0.35 * math.sin(math.tau * 220.0 * index / sample_rate)
            + 0.2 * math.sin(math.tau * 880.0 * index / sample_rate)
            for index in range(count)
        )
        return SignalFixture(kind, sample_rate, mono, mono)
    if kind == "chirp":
        mono = tuple(_chirp(index, sample_rate, duration_seconds) for index in range(count))
        return SignalFixture(kind, sample_rate, mono, mono)
    if kind == "noise":
        mono = _noise_values(count, 0x3105A17)
        return SignalFixture(kind, sample_rate, mono, mono)
    if kind == "asymmetric-stereo":
        left = tuple(
            0.5 * math.sin(math.tau * 330.0 * index / sample_rate) for index in range(count)
        )
        right = tuple(
            0.2 * math.sin(math.tau * 660.0 * index / sample_rate) for index in range(count)
        )
        return SignalFixture(kind, sample_rate, left, right)
    if kind == "transients":
        transient_frames = {0: 0.9, count // 4: -0.75, count // 2: 0.6, 3 * count // 4: -0.45}
        mono = tuple(transient_frames.get(index, 0.0) for index in range(count))
        return SignalFixture(kind, sample_rate, mono, mono)
    if kind == "envelope-control":
        attack = max(1, count // 4)
        release_start = 3 * count // 4
        mono = tuple(
            0.5
            * math.sin(math.tau * 440.0 * index / sample_rate)
            * (
                index / attack
                if index < attack
                else (count - index - 1) / max(1, count - release_start)
                if index >= release_start
                else 1.0
            )
            for index in range(count)
        )
        return SignalFixture(kind, sample_rate, mono, mono)
    raise ValueError(f"unknown generated signal fixture: {kind!r}")


def _pcm_sample(value: float, sample_width: int) -> bytes:
    clamped = max(-1.0, min(1.0, value))
    if sample_width == 1:
        return bytes((round((clamped + 1.0) * 127.5),))
    if sample_width == 2:
        return round(clamped * 32767.0).to_bytes(2, "little", signed=True)
    if sample_width == 4:
        return round(clamped * 2147483647.0).to_bytes(4, "little", signed=True)
    raise ValueError("PCM WAV sample width must be 1, 2, or 4 bytes")


def pcm_wav_bytes(
    fixture: SignalFixture, *, sample_width: int = 2, force_mono: bool = False
) -> bytes:
    """Encode a generated signal as standard-library PCM WAV bytes."""

    import io

    channels = 1 if force_mono else fixture.channels
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(fixture.sample_rate)
        frames = bytearray()
        for left, right in zip(fixture.left, fixture.right, strict=True):
            frames.extend(_pcm_sample(left, sample_width))
            if channels == 2:
                frames.extend(_pcm_sample(right, sample_width))
        writer.writeframes(frames)
    return output.getvalue()


def _signal_stats(fixture: SignalFixture) -> tuple[float, float, float, dict[str, float]]:
    values = (*fixture.left, *fixture.right)
    peak = max(abs(value) for value in values)
    rms = math.sqrt(sum(value * value for value in values) / len(values))
    dc = sum(values) / len(values)
    deltas = tuple(
        fixture.left[index] - fixture.left[index - 1] for index in range(1, fixture.frames)
    )
    high = sum(value * value for value in deltas) / max(1, len(deltas))
    total = sum(value * value for value in fixture.left) / fixture.frames
    return peak, rms, dc, {"signal": total, "difference": high}


_FIXTURE_KINDS = (
    "impulse-mono",
    "impulse-stereo",
    "silence",
    "sine",
    "dual-tone",
    "chirp",
    "noise",
    "asymmetric-stereo",
    "transients",
    "envelope-control",
)


def fixture_manifest() -> tuple[FixtureManifestEntry, ...]:
    """Return stable hashes and signal metadata for the complete generated corpus."""

    entries: list[FixtureManifestEntry] = []
    for kind in _FIXTURE_KINDS:
        fixture = generate_signal(kind)
        payload = pcm_wav_bytes(fixture)
        peak, rms, dc, bands = _signal_stats(fixture)
        entries.append(
            FixtureManifestEntry(
                kind,
                fixture.frames,
                fixture.channels,
                fixture.sample_rate,
                fixture.duration_seconds,
                len(payload),
                sha256(payload).hexdigest(),
                peak,
                rms,
                dc,
                bands,
            )
        )
    return tuple(entries)


def validate_manifest(manifest: tuple[FixtureManifestEntry, ...] | None = None) -> None:
    """Regenerate every fixture and reject stale structural or digest metadata."""

    expected = fixture_manifest()
    if manifest is not None and manifest != expected:
        raise ValueError(
            "generated Synth fixture manifest does not match fixture bytes and statistics"
        )
    if {entry.name for entry in expected} != set(_FIXTURE_KINDS):
        raise ValueError("generated Synth fixture manifest is incomplete")
    if any(entry.frames <= 0 or entry.byte_length <= 44 for entry in expected):
        raise ValueError("generated Synth fixture manifest contains an empty signal")


@contextmanager
def generated_sample_files(*, sample_rate: int = 16_000) -> Iterator[GeneratedSampleFiles]:
    """Write decoder fixtures to an isolated temporary directory and remove it on exit."""

    with tempfile.TemporaryDirectory(prefix="gummysnake-synth-bench-") as temporary:
        root = Path(temporary)
        sources = {
            "mono": generate_signal("dual-tone", sample_rate=sample_rate),
            "stereo": generate_signal("asymmetric-stereo", sample_rate=sample_rate),
            "transients": generate_signal("transients", sample_rate=sample_rate),
        }
        paths: dict[str, Path] = {}
        for source_name, fixture in sources.items():
            for sample_width in (1, 2, 4):
                name = f"{source_name}-{sample_width * 8}bit"
                path = root / f"{name}.wav"
                path.write_bytes(
                    pcm_wav_bytes(
                        fixture,
                        sample_width=sample_width,
                        force_mono=source_name == "mono",
                    )
                )
                paths[name] = path
        yield GeneratedSampleFiles(root, paths)


__all__ = [
    "FixtureManifestEntry",
    "GeneratedSampleFiles",
    "SignalFixture",
    "fixture_manifest",
    "generate_signal",
    "generated_sample_files",
    "pcm_wav_bytes",
    "validate_manifest",
]
