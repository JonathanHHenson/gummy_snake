"""Renderer-independent correctness checks used by Canvas workloads."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol


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


__all__ = [
    "CanvasDimensions",
    "CanvasOracleError",
    "PixelSentinel",
    "assert_capability_failure",
    "assert_hidpi_dimensions",
    "assert_ordered_layers",
    "assert_rgba_sentinels",
    "rgba_at",
]
