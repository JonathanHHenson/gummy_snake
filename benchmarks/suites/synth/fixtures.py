"""Deterministic runtime-generated signals and PCM WAV fixtures for Synth benchmarks."""

from __future__ import annotations

import importlib.metadata
import json
import math
import shutil
import tempfile
import wave
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlparse


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


@dataclass(frozen=True, slots=True)
class PcmVariantCase:
    """One generated PCM decoder case with an explicit rate/channel/width identity."""

    name: str
    signal_kind: str
    sample_rate: int
    duration_seconds: float
    sample_width: int
    force_mono: bool


@dataclass(frozen=True, slots=True)
class PcmVariantManifestEntry:
    """Stable metadata for one generated PCM WAV variant."""

    name: str
    frames: int
    channels: int
    sample_rate: int
    sample_width: int
    duration_seconds: float
    byte_length: int
    sha256: str
    peak: float
    rms: float
    dc: float
    spectral_bands: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class PackagedSampleCase:
    """Pinned package-owned FLAC used for realistic decoder/cache scales."""

    name: str
    relative_path: str
    role: str
    byte_length: int
    sha256: str
    expected_duration_seconds: float
    license: str


@dataclass(frozen=True, slots=True)
class CodecCapability:
    """Availability of an external codec route without an encoder substitute."""

    codec: str
    available: bool
    executable: str | None
    reason: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "codec": self.codec,
            "available": self.available,
            "executable": self.executable,
            "reason": self.reason,
            "substitute_used": False,
        }


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

_REVIEWED_SIGNAL_DIGESTS = {
    "impulse-mono": "471926153586190d9152180f3825a5c4c546bd64bef296c261d5ef45446772a1",
    "impulse-stereo": "6b21980fc507d7315f5ca5af75b3a46e613fe391917be3baf8e21c446dfceb8d",
    "silence": "1fac9c5a2a5f63cb0bed663b416a8d32ce32d0c7736ff3f097eed7ee60711ee4",
    "sine": "5fe10283bd5cdb1cf73a4f740af9ea10a128a75974cf26bb2392f9c1c42a3ed7",
    "dual-tone": "6b48976c90c2b09358f831b62dac0ac824fb2b1be9daeb8843d1e21602bdf3eb",
    "chirp": "21bd3746e273e6247121c0865bd908080633b5ad0bf42273249f3fadd0d9b731",
    "noise": "65d840c79dbd5bb0f4de5b0c3e93ffbdc4f8194a385429be0deb1642f5993a98",
    "asymmetric-stereo": "0f6581e93c4a4b7e1e5ad138dba8e03af7cacd9eeaf86c49f2c4f0c9ed4c8225",
    "transients": "a0ab0b7179048e21d58f9d87d082aa2e510d288f147bf6c3d7cc00b7793c4478",
    "envelope-control": "ad8dff09142f8dd120008dd84c04fd26dec0cda01014daf650107972cd6d1937",
}

_PACKAGED_SAMPLE_CASES = (
    PackagedSampleCase(
        "reviewed-minimal-flac",
        "assets/samples/sonic_pi/bd_pure.flac",
        "minimal-real-flac-decoder-fixture",
        18_056,
        "cd70fc3260302262f65c8f66f012faf7531853598a6d2a01a8af73bd3816c6b3",
        0.43324263038548755,
        "CC0-1.0",
    ),
    PackagedSampleCase(
        "packaged-transient-flac",
        "assets/samples/sonic_pi/drum_cymbal_closed.flac",
        "short-transient-decoder-and-cache-scale",
        20_943,
        "f3b9d6bb14f75ba06ef633baf58b1f75f0e2ea5e07edd491f0a22aedb2480d62",
        0.2069387755102041,
        "CC0-1.0",
    ),
    PackagedSampleCase(
        "packaged-loop-flac",
        "assets/samples/sonic_pi/loop_amen.flac",
        "long-loop-decoder-resampler-and-cache-scale",
        210_769,
        "96d3c6ea1fdadce5db26290275d4b34add11e8503a18fb6f405b8897d06ba50d",
        1.753310657596372,
        "CC0-1.0",
    ),
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
    actual_digests = {entry.name: entry.sha256 for entry in expected}
    if actual_digests != _REVIEWED_SIGNAL_DIGESTS:
        raise ValueError("generated Synth fixture bytes differ from reviewed signal hashes")


def pcm_variant_catalog() -> tuple[PcmVariantCase, ...]:
    """Return all reviewed mono/stereo, width, and sample-rate PCM combinations."""

    cases: list[PcmVariantCase] = []
    for sample_rate in (8_000, 16_000, 44_100, 48_000):
        for sample_width in (1, 2, 4):
            cases.extend(
                (
                    PcmVariantCase(
                        f"mono-{sample_rate}hz-{sample_width * 8}bit",
                        "dual-tone",
                        sample_rate,
                        0.032,
                        sample_width,
                        True,
                    ),
                    PcmVariantCase(
                        f"stereo-{sample_rate}hz-{sample_width * 8}bit",
                        "asymmetric-stereo",
                        sample_rate,
                        0.032,
                        sample_width,
                        False,
                    ),
                )
            )
    return tuple(cases)


def pcm_variant_manifest() -> tuple[PcmVariantManifestEntry, ...]:
    """Generate exact hashes and signal statistics for the full PCM variant matrix."""

    entries: list[PcmVariantManifestEntry] = []
    for case in pcm_variant_catalog():
        fixture = generate_signal(
            case.signal_kind,
            sample_rate=case.sample_rate,
            duration_seconds=case.duration_seconds,
        )
        payload = pcm_wav_bytes(fixture, sample_width=case.sample_width, force_mono=case.force_mono)
        peak, rms, dc, bands = _signal_stats(fixture)
        entries.append(
            PcmVariantManifestEntry(
                case.name,
                fixture.frames,
                1 if case.force_mono else fixture.channels,
                case.sample_rate,
                case.sample_width,
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


def validate_pcm_variant_manifest(
    manifest: tuple[PcmVariantManifestEntry, ...] | None = None,
) -> None:
    """Reject malformed, incomplete, or stale generated PCM variant metadata."""

    expected = pcm_variant_manifest()
    if manifest is not None and manifest != expected:
        raise ValueError("generated PCM variant manifest does not match fixture bytes")
    expected_names = {case.name for case in pcm_variant_catalog()}
    if {entry.name for entry in expected} != expected_names or len(expected) != 24:
        raise ValueError("generated PCM variant manifest is incomplete")
    if {entry.sample_width for entry in expected} != {1, 2, 4}:
        raise ValueError("generated PCM variant manifest does not cover supported widths")
    if {entry.channels for entry in expected} != {1, 2}:
        raise ValueError("generated PCM variant manifest does not cover mono and stereo")


def packaged_sample_catalog() -> tuple[PackagedSampleCase, ...]:
    """Return the explicitly reviewed package-owned FLAC decoder cases."""

    return _PACKAGED_SAMPLE_CASES


def _editable_distribution_file(distribution: object, relative: Path) -> Path | None:
    read_text = getattr(distribution, "read_text", None)
    if not callable(read_text):
        return None
    direct_url = read_text("direct_url.json")
    if not isinstance(direct_url, str):
        return None
    try:
        metadata = json.loads(direct_url)
    except json.JSONDecodeError:
        return None
    if not isinstance(metadata, Mapping):
        return None
    directory = metadata.get("dir_info")
    url = metadata.get("url")
    if (
        not isinstance(directory, Mapping)
        or directory.get("editable") is not True
        or not isinstance(url, str)
    ):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    candidate = (Path(unquote(parsed.path)) / relative).resolve()
    return candidate if candidate.is_file() else None


def _packaged_sample_path(case: PackagedSampleCase) -> Path:
    relative = Path(case.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"packaged Synth sample fixture path is invalid: {case.relative_path}")
    try:
        distribution = importlib.metadata.distribution("gummy-snake")
    except importlib.metadata.PackageNotFoundError as error:
        raise ValueError(
            "installed gummy-snake distribution metadata is unavailable; "
            f"cannot locate Synth sample fixture: {case.relative_path}"
        ) from error
    candidate = Path(str(distribution.locate_file(relative.as_posix()))).resolve()
    if candidate.is_file():
        return candidate
    editable_candidate = _editable_distribution_file(distribution, relative)
    if editable_candidate is not None:
        return editable_candidate
    raise ValueError(
        f"installed gummy-snake distribution is missing Synth sample fixture: {case.relative_path}"
    )


def validate_packaged_sample_catalog(
    duration_probe: Callable[[str], float] | None = None,
) -> Mapping[str, Path]:
    """Verify pinned FLAC bytes and optionally validate native decoder durations."""

    paths: dict[str, Path] = {}
    for case in packaged_sample_catalog():
        path = _packaged_sample_path(case)
        payload = path.read_bytes()
        if not payload.startswith(b"fLaC"):
            raise ValueError(f"packaged Synth sample is not FLAC: {case.relative_path}")
        if len(payload) != case.byte_length or sha256(payload).hexdigest() != case.sha256:
            raise ValueError(f"packaged Synth sample fixture is stale: {case.relative_path}")
        if duration_probe is not None:
            duration = float(duration_probe(str(path)))
            if abs(duration - case.expected_duration_seconds) > 1e-12:
                raise ValueError(
                    f"packaged Synth sample duration changed for {case.name}: {duration}"
                )
        paths[case.name] = path
    return paths


def ffmpeg_mp3_capability() -> CodecCapability:
    """Report the optional FFmpeg MP3 route without selecting another encoder."""

    executable = shutil.which("ffmpeg")
    if executable is None:
        return CodecCapability(
            "mp3-ffmpeg",
            False,
            None,
            "FFmpeg is not available on PATH; MP3 coverage is unavailable and no substitute "
            "encoder is permitted",
        )
    return CodecCapability("mp3-ffmpeg", True, executable, None)


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
    "CodecCapability",
    "FixtureManifestEntry",
    "GeneratedSampleFiles",
    "PackagedSampleCase",
    "PcmVariantCase",
    "PcmVariantManifestEntry",
    "SignalFixture",
    "ffmpeg_mp3_capability",
    "fixture_manifest",
    "generate_signal",
    "generated_sample_files",
    "packaged_sample_catalog",
    "pcm_variant_catalog",
    "pcm_variant_manifest",
    "pcm_wav_bytes",
    "validate_manifest",
    "validate_packaged_sample_catalog",
    "validate_pcm_variant_manifest",
]
