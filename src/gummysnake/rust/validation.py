"""Validation helpers for optional acceleration fallbacks."""

from __future__ import annotations

ByteBuffer = bytes | bytearray | memoryview


def validate_noise_octaves(octaves: int) -> None:
    if octaves < 1:
        msg = "octaves must be at least 1."
        raise ValueError(msg)


def validate_same_length(base: bytes, overlay: bytes) -> None:
    if len(base) != len(overlay):
        msg = f"Buffers must have the same length, got {len(base)} and {len(overlay)}."
        raise ValueError(msg)


__all__ = ["ByteBuffer", "validate_noise_octaves", "validate_same_length"]
