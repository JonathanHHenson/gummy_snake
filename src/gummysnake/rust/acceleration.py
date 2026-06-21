"""Optional acceleration extension loading and status helpers."""

from __future__ import annotations

from typing import Protocol, cast


class AcceleratedModule(Protocol):
    def health_check(self) -> str: ...

    def noise3(
        self,
        x: float,
        y: float,
        z: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> float: ...

    def animated_noise_rgba(
        self,
        width: int,
        height: int,
        density: float,
        time: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> bytes: ...

    def exclusion_blend_rgb(self, base: bytes, overlay: bytes) -> bytes: ...


_loaded_accelerated: AcceleratedModule | None

try:
    from gummysnake.rust import _accelerated as _loaded_accelerated
except ImportError as exc:
    _loaded_accelerated = None
    _ACCELERATION_IMPORT_ERROR: ImportError | None = exc
else:
    _ACCELERATION_IMPORT_ERROR = None

accelerated = cast(AcceleratedModule | None, _loaded_accelerated)


def is_acceleration_available() -> bool:
    """Return whether the optional compiled extension is active."""

    return accelerated is not None


def acceleration_import_error() -> ImportError | None:
    """Return the import error that disabled acceleration, if any."""

    return _ACCELERATION_IMPORT_ERROR


def health_check() -> str:
    """Report which acceleration backend is currently serving wrapper calls."""

    if accelerated is None:
        return "python-fallback"
    return str(accelerated.health_check())


__all__ = [
    "AcceleratedModule",
    "acceleration_import_error",
    "accelerated",
    "health_check",
    "is_acceleration_available",
]
