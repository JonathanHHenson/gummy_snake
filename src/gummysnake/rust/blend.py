"""RGB blend acceleration wrappers and Python fallbacks."""

from __future__ import annotations

from gummysnake.rust.acceleration import acceleration_provider
from gummysnake.rust.validation import ByteBuffer, validate_same_length


def exclusion_blend_rgb(
    base: ByteBuffer,
    overlay: ByteBuffer,
    *,
    prefer_accelerated: bool = True,
) -> bytes:
    """Blend packed RGB bytes with Gummy Snake's ``EXCLUSION`` formula."""

    base_bytes = bytes(base)
    overlay_bytes = bytes(overlay)
    validate_same_length(base_bytes, overlay_bytes)
    provider = acceleration_provider(prefer_accelerated)
    if provider is not None:
        return bytes(provider.exclusion_blend_rgb(base_bytes, overlay_bytes))
    return exclusion_blend_rgb_bytes(base_bytes, overlay_bytes)


def exclusion_blend_rgb_python(base: ByteBuffer, overlay: ByteBuffer) -> bytes:
    """Pure-Python reference implementation for ``exclusion_blend_rgb``."""

    base_bytes = bytes(base)
    overlay_bytes = bytes(overlay)
    validate_same_length(base_bytes, overlay_bytes)
    return exclusion_blend_rgb_bytes(base_bytes, overlay_bytes)


def exclusion_blend_rgb_bytes(base: bytes, overlay: bytes) -> bytes:
    return bytes(
        max(0, min(255, b + o - 2 * b * o // 255)) for b, o in zip(base, overlay, strict=True)
    )


__all__ = ["exclusion_blend_rgb", "exclusion_blend_rgb_python"]
