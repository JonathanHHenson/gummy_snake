"""Renderer-independent correctness checks used by Canvas workloads."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import isclose, isfinite
from struct import unpack
from typing import Protocol
from zlib import crc32, decompress

from .fixtures import MediaFrameFixture, ObjFixture, ResourceResetFixture, TextCorpusFixture


class CanvasOracleError(AssertionError):
    """A Canvas workload completed with incorrect observable behavior."""


class CanvasDimensions(Protocol):
    """Public context attributes required for logical/physical checks."""

    width: int
    height: int

    def pixel_density(self) -> float: ...


class CanvasCompletedState(CanvasDimensions, Protocol):
    """Public completed-state attributes required by the state oracle."""

    frame_count: int


@dataclass(frozen=True, slots=True)
class PixelSentinel:
    """An exact expected top-left RGBA pixel."""

    x: int
    y: int
    rgba: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class PngOracleResult:
    """Validated PNG format and decoded RGBA identity."""

    width: int
    height: int
    rgba_sha256: str


@dataclass(frozen=True, slots=True)
class ResourceLifecycleExpectation:
    """Public counters required to prove that one releasable resource did not leak."""

    name: str
    resident_counter: str
    peak_counter: str
    allocation_counter: str
    destruction_counter: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.name,
                self.resident_counter,
                self.peak_counter,
                self.allocation_counter,
                self.destruction_counter,
            )
        ):
            raise ValueError("resource lifecycle expectation values must be non-empty")


def rgba_at(
    pixels: Sequence[int] | bytes, physical_width: int, x: int, y: int
) -> tuple[int, int, int, int]:
    """Read one exact RGBA value using the public top-left pixel convention."""

    if physical_width <= 0 or x < 0 or y < 0:
        raise CanvasOracleError("pixel coordinates and physical width must be non-negative")
    offset = (y * physical_width + x) * 4
    if offset + 4 > len(pixels):
        raise CanvasOracleError(f"pixel sentinel ({x}, {y}) is outside the supplied buffer")
    return (
        int(pixels[offset]),
        int(pixels[offset + 1]),
        int(pixels[offset + 2]),
        int(pixels[offset + 3]),
    )


def rgba_sha256(pixels: Sequence[int] | bytes) -> str:
    """Return an exact allocation-independent RGBA digest."""

    return "sha256:" + sha256(bytes(pixels)).hexdigest()


def assert_rgba_digest(pixels: Sequence[int] | bytes, expected: str) -> None:
    """Require an exact reviewed RGBA digest."""

    actual = rgba_sha256(pixels)
    if actual != expected:
        raise CanvasOracleError(f"RGBA digest expected {expected}, got {actual}")


def assert_rgba_sentinels(
    pixels: Sequence[int] | bytes, physical_width: int, sentinels: Iterable[PixelSentinel]
) -> None:
    """Require exact RGBA sentinels, useful for deterministic primitive/image paths."""

    for sentinel in sentinels:
        actual = rgba_at(pixels, physical_width, sentinel.x, sentinel.y)
        if actual != sentinel.rgba:
            raise CanvasOracleError(
                f"pixel ({sentinel.x}, {sentinel.y}) expected {sentinel.rgba}, got {actual}"
            )


def assert_ordered_layers(
    pixels: Sequence[int] | bytes, physical_width: int, layers: Iterable[PixelSentinel]
) -> None:
    """Assert visible sentinels from an ordered multi-family command stream."""

    assert_rgba_sentinels(pixels, physical_width, layers)


def assert_media_frame_rgba(fixture: MediaFrameFixture, actual_rgba: Sequence[int] | bytes) -> None:
    """Require an actual native media conversion to match reviewed RGBA bytes."""

    actual = bytes(actual_rgba)
    expected = fixture.expected_rgba.pixels
    if len(actual) != len(expected):
        raise CanvasOracleError(
            f"{fixture.name} RGBA byte length expected {len(expected)}, got {len(actual)}"
        )
    if actual != expected:
        raise CanvasOracleError(f"{fixture.name} native RGBA conversion did not match its fixture")


def assert_obj_fixture_topology(model: object, fixture: ObjFixture) -> None:
    """Require a real OBJ load to preserve the reviewed vertices and face order."""

    meshes = getattr(model, "meshes", None)
    if meshes is None:
        raise CanvasOracleError(f"{fixture.name} model does not expose public meshes")
    try:
        mesh_values = tuple(meshes)
    except TypeError as error:
        raise CanvasOracleError(f"{fixture.name} model meshes are not iterable") from error
    if len(mesh_values) != 1:
        raise CanvasOracleError(f"{fixture.name} expected one mesh, got {len(mesh_values)}")
    mesh = mesh_values[0]
    try:
        vertices = tuple(
            (float(vertex.x), float(vertex.y), float(vertex.z)) for vertex in mesh.vertices
        )
        faces = tuple(tuple(int(index) for index in face) for face in mesh.faces)
    except (AttributeError, TypeError, ValueError) as error:
        raise CanvasOracleError(
            f"{fixture.name} mesh does not expose numeric vertices and faces"
        ) from error
    if vertices != fixture.vertices:
        raise CanvasOracleError(f"{fixture.name} vertices did not match reviewed topology")
    if faces != fixture.faces:
        raise CanvasOracleError(f"{fixture.name} faces did not match reviewed topology")


def assert_text_corpus(fixture: TextCorpusFixture, corpus: Mapping[str, tuple[str, ...]]) -> None:
    """Require every reviewed Unicode input and category to remain exact."""

    actual = dict(corpus)
    expected = dict(fixture.corpus)
    if actual != expected:
        raise CanvasOracleError(f"{fixture.name} text corpus did not match reviewed Unicode inputs")


def assert_presented_frames(counters: Mapping[str, object], expected_frames: int) -> None:
    """Require every bounded native frame to reach the public presentation counter."""

    presented = counters.get("frames_presented")
    if (
        isinstance(expected_frames, bool)
        or not isinstance(expected_frames, int)
        or expected_frames < 1
    ):
        raise CanvasOracleError("expected presented frame count must be a positive integer")
    if isinstance(presented, bool) or not isinstance(presented, int):
        raise CanvasOracleError("renderer frames_presented counter must be an integer")
    if presented < expected_frames:
        raise CanvasOracleError(
            f"native workload presented {presented} frames, expected at least {expected_frames}"
        )


def assert_canvas_state(
    context: CanvasCompletedState,
    *,
    logical_width: int,
    logical_height: int,
    density: float,
    frame_count: int,
) -> None:
    """Require exact public logical dimensions, density, and completed frame count."""

    if frame_count < 0:
        raise CanvasOracleError("expected frame count must be non-negative")
    if context.frame_count != frame_count:
        raise CanvasOracleError(
            f"completed frame count expected {frame_count}, got {context.frame_count}"
        )
    if context.width != logical_width or context.height != logical_height:
        raise CanvasOracleError(
            f"logical dimensions expected {logical_width}x{logical_height}, "
            f"got {context.width}x{context.height}"
        )
    if context.pixel_density() != density:
        raise CanvasOracleError(f"pixel density expected {density}, got {context.pixel_density()}")


def assert_hidpi_dimensions(
    context: CanvasDimensions,
    pixels: Sequence[int] | bytes,
    *,
    logical_width: int,
    logical_height: int,
    density: float,
) -> None:
    """Check logical size and the exact physical RGBA byte length."""

    if context.width != logical_width or context.height != logical_height:
        raise CanvasOracleError(
            f"logical dimensions expected {logical_width}x{logical_height}, "
            f"got {context.width}x{context.height}"
        )
    actual_density = context.pixel_density()
    if actual_density != density:
        raise CanvasOracleError(f"pixel density expected {density}, got {actual_density}")
    physical_width = round(logical_width * density)
    physical_height = round(logical_height * density)
    expected_bytes = physical_width * physical_height * 4
    if len(pixels) != expected_bytes:
        raise CanvasOracleError(
            f"physical RGBA bytes expected {expected_bytes} ({physical_width}x{physical_height}), "
            f"got {len(pixels)}"
        )


def assert_effect_changed(
    before: Sequence[int] | bytes,
    after: Sequence[int] | bytes,
    *,
    minimum_changed_pixels: int = 1,
) -> None:
    """Detect a silent no-op effect using complete RGBA input/output buffers."""

    before_bytes = bytes(before)
    after_bytes = bytes(after)
    if len(before_bytes) != len(after_bytes) or len(before_bytes) % 4:
        raise CanvasOracleError("effect buffers must have equal complete RGBA lengths")
    if minimum_changed_pixels < 1:
        raise CanvasOracleError("minimum_changed_pixels must be positive")
    changed = sum(
        before_bytes[offset : offset + 4] != after_bytes[offset : offset + 4]
        for offset in range(0, len(before_bytes), 4)
    )
    if changed < minimum_changed_pixels:
        raise CanvasOracleError(
            f"effect changed {changed} pixels, expected at least {minimum_changed_pixels}"
        )


def assert_replay_updated(
    before: Sequence[int] | bytes,
    after: Sequence[int] | bytes,
    counters: Mapping[str, object],
    *,
    replay_counter: str = "retained_batch_cache_hits",
) -> None:
    """Detect stale retained replay after observable scene state changed."""

    if bytes(before) == bytes(after):
        raise CanvasOracleError("retained replay produced stale unchanged RGBA output")
    value = counters.get(replay_counter)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CanvasOracleError(
            f"replay counter {replay_counter!r} must be a non-negative public integer"
        )


def assert_numeric_samples_close(
    actual: Sequence[float],
    expected: Sequence[float],
    *,
    absolute_tolerance: float,
    label: str,
) -> None:
    """Tolerance oracle for text bounds, 3D samples, and rasterized signals."""

    if not isfinite(absolute_tolerance) or absolute_tolerance < 0:
        raise CanvasOracleError("absolute tolerance must be finite and non-negative")
    if len(actual) != len(expected):
        raise CanvasOracleError(f"{label} sample count expected {len(expected)}, got {len(actual)}")
    for index, (actual_value, expected_value) in enumerate(zip(actual, expected, strict=True)):
        if not isfinite(actual_value) or not isfinite(expected_value):
            raise CanvasOracleError(f"{label} sample {index} must be finite")
        if not isclose(actual_value, expected_value, rel_tol=0.0, abs_tol=absolute_tolerance):
            raise CanvasOracleError(
                f"{label} sample {index} expected {expected_value}±{absolute_tolerance}, "
                f"got {actual_value}"
            )


def assert_text_bounds_close(
    actual: Sequence[float], expected: Sequence[float], *, absolute_tolerance: float
) -> None:
    """Require four text-bound values within an explicit raster tolerance."""

    if len(actual) != 4 or len(expected) != 4:
        raise CanvasOracleError("text bounds must contain x, y, width, and height")
    assert_numeric_samples_close(
        actual,
        expected,
        absolute_tolerance=absolute_tolerance,
        label="text bounds",
    )


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _decode_png_rgba(scanlines: bytes, width: int, height: int) -> bytes:
    stride = width * 4
    expected = height * (stride + 1)
    if len(scanlines) != expected:
        raise CanvasOracleError(f"PNG decompressed bytes expected {expected}, got {len(scanlines)}")
    decoded = bytearray(height * stride)
    source_offset = 0
    for row in range(height):
        filter_kind = scanlines[source_offset]
        source_offset += 1
        if filter_kind > 4:
            raise CanvasOracleError(f"PNG uses unsupported filter type {filter_kind}")
        row_offset = row * stride
        for column in range(stride):
            raw = scanlines[source_offset + column]
            left = decoded[row_offset + column - 4] if column >= 4 else 0
            above = decoded[row_offset - stride + column] if row else 0
            upper_left = decoded[row_offset - stride + column - 4] if row and column >= 4 else 0
            if filter_kind == 0:
                value = raw
            elif filter_kind == 1:
                value = raw + left
            elif filter_kind == 2:
                value = raw + above
            elif filter_kind == 3:
                value = raw + ((left + above) // 2)
            else:
                value = raw + _paeth(left, above, upper_left)
            decoded[row_offset + column] = value & 0xFF
        source_offset += stride
    return bytes(decoded)


def assert_png_export(
    payload: bytes,
    *,
    width: int,
    height: int,
    expected_rgba: Sequence[int] | bytes | None = None,
) -> PngOracleResult:
    """Validate PNG magic/chunks/CRC/format and optionally exact decoded RGBA."""

    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise CanvasOracleError("export is not a PNG byte stream")
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise CanvasOracleError("PNG contains a truncated chunk")
        length = unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        data_end = offset + 8 + length
        chunk_end = data_end + 4
        if chunk_end > len(payload):
            raise CanvasOracleError("PNG chunk length exceeds the payload")
        data = payload[offset + 8 : data_end]
        expected_crc = unpack(">I", payload[data_end:chunk_end])[0]
        if crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise CanvasOracleError(f"PNG chunk {kind!r} has an invalid CRC")
        chunks.append((kind, data))
        offset = chunk_end
        if kind == b"IEND":
            break
    if offset != len(payload) or not chunks or chunks[0][0] != b"IHDR":
        raise CanvasOracleError("PNG chunk order or trailing bytes are invalid")
    if chunks[-1][0] != b"IEND" or len(chunks[-1][1]) != 0:
        raise CanvasOracleError("PNG is missing a valid IEND chunk")
    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        raise CanvasOracleError("PNG IHDR length is invalid")
    actual_width, actual_height, bit_depth, color_type, compression, filtering, interlace = unpack(
        ">IIBBBBB", ihdr
    )
    if (actual_width, actual_height) != (width, height):
        raise CanvasOracleError(
            f"PNG dimensions expected {width}x{height}, got {actual_width}x{actual_height}"
        )
    if (bit_depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
        raise CanvasOracleError(
            "PNG must be non-interlaced 8-bit RGBA with standard compression/filter methods"
        )
    idat = b"".join(data for kind, data in chunks if kind == b"IDAT")
    if not idat:
        raise CanvasOracleError("PNG contains no IDAT payload")
    try:
        rgba = _decode_png_rgba(decompress(idat), width, height)
    except Exception as error:
        if isinstance(error, CanvasOracleError):
            raise
        raise CanvasOracleError(f"PNG IDAT decompression failed: {error}") from error
    if expected_rgba is not None and rgba != bytes(expected_rgba):
        raise CanvasOracleError("PNG decoded RGBA does not match the reviewed output")
    return PngOracleResult(width, height, rgba_sha256(rgba))


def assert_capability_failure(operation: Callable[[], object], required: str) -> None:
    """Require an unavailable capability to fail clearly instead of falling back."""

    try:
        operation()
    except Exception as error:
        message = str(error).lower()
        required_tokens = tuple(
            token for token in required.lower().replace("-", " ").split() if token
        )
        if not required_tokens or not any(token in message for token in required_tokens):
            raise CanvasOracleError(
                f"capability failure did not identify required capability {required!r}: {error}"
            ) from error
        return
    raise CanvasOracleError(
        f"operation unexpectedly succeeded without required capability: {required}"
    )


def _resource_counter(counters: Mapping[str, object], name: str) -> int:
    value = counters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CanvasOracleError(f"resource counter {name!r} must be a non-negative integer")
    return value


def assert_resource_lifecycle_balanced(
    before: Mapping[str, object],
    after: Mapping[str, object],
    expectation: ResourceLifecycleExpectation,
) -> None:
    """Require a releasable resource to return to baseline without hidden leaks."""

    before_resident = _resource_counter(before, expectation.resident_counter)
    after_resident = _resource_counter(after, expectation.resident_counter)
    after_peak = _resource_counter(after, expectation.peak_counter)
    allocations = _resource_counter(after, expectation.allocation_counter) - _resource_counter(
        before, expectation.allocation_counter
    )
    destructions = _resource_counter(after, expectation.destruction_counter) - _resource_counter(
        before, expectation.destruction_counter
    )
    if after_resident > before_resident:
        raise CanvasOracleError(
            f"{expectation.name} resident bytes leaked: baseline {before_resident}, "
            f"final {after_resident}"
        )
    if after_peak < max(before_resident, after_resident):
        raise CanvasOracleError(
            f"{expectation.name} peak bytes {after_peak} are below observed resident bytes"
        )
    if allocations < 0 or destructions < 0:
        raise CanvasOracleError(f"{expectation.name} lifecycle counters moved backwards")
    if destructions < allocations:
        raise CanvasOracleError(
            f"{expectation.name} allocated {allocations} resources but destroyed {destructions}"
        )


def assert_resource_reset_preserves_warm_cache(
    before_reset: Mapping[str, object],
    after_reset: Mapping[str, object],
    fixture: ResourceResetFixture,
) -> None:
    """Require a counter reset to retain warm resources while clearing run activity.

    The fixture supplies only reviewed source bytes and public counter names. Both
    diagnostic mappings must come from an actual completed renderer run; this
    oracle never supplies absent counters or estimates resident memory.
    """

    source_bytes = len(fixture.source.pixels)
    for family in fixture.retained_families:
        before_resident = _resource_counter(before_reset, family.resident_counter)
        before_peak = _resource_counter(before_reset, family.peak_counter)
        after_resident = _resource_counter(after_reset, family.resident_counter)
        after_peak = _resource_counter(after_reset, family.peak_counter)
        if before_resident < source_bytes:
            raise CanvasOracleError(
                f"{fixture.name} did not retain {family.name} source bytes: "
                f"expected at least {source_bytes}, got {before_resident}"
            )
        if before_peak < before_resident:
            raise CanvasOracleError(
                f"{family.name} peak bytes {before_peak} are below resident bytes {before_resident}"
            )
        if after_resident != before_resident:
            raise CanvasOracleError(
                f"{fixture.name} reset changed {family.name} resident bytes from "
                f"{before_resident} to {after_resident}"
            )
        if after_peak != after_resident:
            raise CanvasOracleError(
                f"{fixture.name} reset peak bytes {after_peak} must equal retained resident "
                f"bytes {after_resident}"
            )
    for counter in fixture.reset_activity_counters:
        if (value := _resource_counter(after_reset, counter)) != 0:
            raise CanvasOracleError(
                f"{fixture.name} reset activity counter {counter!r} expected 0, got {value}"
            )


__all__ = [
    "CanvasCompletedState",
    "CanvasDimensions",
    "CanvasOracleError",
    "PixelSentinel",
    "PngOracleResult",
    "ResourceLifecycleExpectation",
    "assert_canvas_state",
    "assert_capability_failure",
    "assert_effect_changed",
    "assert_hidpi_dimensions",
    "assert_media_frame_rgba",
    "assert_obj_fixture_topology",
    "assert_numeric_samples_close",
    "assert_ordered_layers",
    "assert_png_export",
    "assert_presented_frames",
    "assert_replay_updated",
    "assert_resource_lifecycle_balanced",
    "assert_resource_reset_preserves_warm_cache",
    "assert_rgba_digest",
    "assert_rgba_sentinels",
    "assert_text_bounds_close",
    "assert_text_corpus",
    "rgba_at",
    "rgba_sha256",
]
