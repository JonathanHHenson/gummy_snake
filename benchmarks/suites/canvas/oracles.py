"""Renderer-independent correctness checks used by Canvas workloads."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .fixtures import MediaFrameFixture, ObjFixture, ResourceResetFixture, TextCorpusFixture


class CanvasOracleError(AssertionError):
    """A Canvas workload completed with incorrect observable behavior."""


class CanvasDimensions(Protocol):
    """Public context attributes required for logical/physical checks."""

    width: int
    height: int

    def pixel_density(self) -> float: ...


@dataclass(frozen=True, slots=True)
class PixelSentinel:
    """An exact expected top-left RGBA pixel."""

    x: int
    y: int
    rgba: tuple[int, int, int, int]


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
    "CanvasDimensions",
    "CanvasOracleError",
    "PixelSentinel",
    "assert_capability_failure",
    "assert_hidpi_dimensions",
    "assert_media_frame_rgba",
    "assert_obj_fixture_topology",
    "assert_ordered_layers",
    "assert_presented_frames",
    "assert_resource_reset_preserves_warm_cache",
    "assert_rgba_sentinels",
    "assert_text_corpus",
    "rgba_at",
]
