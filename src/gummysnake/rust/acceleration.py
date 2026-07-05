"""Optional acceleration extension loading and status helpers."""

from __future__ import annotations

from typing import Protocol, cast


class AcceleratedModule(Protocol):
    """Protocol implemented by the optional compiled acceleration module."""

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


def acceleration_provider(prefer_accelerated: bool = True) -> AcceleratedModule | None:
    return accelerated if prefer_accelerated else None


def is_acceleration_available() -> bool:
    return acceleration_provider() is not None


def acceleration_import_error() -> ImportError | None:
    return _ACCELERATION_IMPORT_ERROR


def health_check() -> str:
    if accelerated is None:
        return "python-fallback"
    return str(accelerated.health_check())


__all__ = [
    "AcceleratedModule",
    "acceleration_import_error",
    "acceleration_provider",
    "accelerated",
    "health_check",
    "is_acceleration_available",
]
