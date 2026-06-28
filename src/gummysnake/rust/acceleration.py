"""Optional acceleration extension loading and status helpers."""

from __future__ import annotations

from typing import Protocol, cast


class AcceleratedModule(Protocol):
    """Protocol implemented by the optional compiled acceleration module."""

    def health_check(self) -> str:
        """Return a short status string for the acceleration provider.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str`.
        """
        ...

    def noise3(
        self,
        x: float,
        y: float,
        z: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> float:
        """Return accelerated 3D noise for the provided coordinates.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            z: The z value. Expected type: `float`.
            seed: The seed value. Expected type: `int`.
            octaves: The octaves value. Expected type: `int`.
            falloff: The falloff value. Expected type: `float`.
        
        Returns:
            The return value. Type: `float`.
        """
        ...

    def animated_noise_rgba(
        self,
        width: int,
        height: int,
        density: float,
        time: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> bytes:
        """Return an accelerated RGBA noise frame.
        
        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            density: The density value. Expected type: `float`.
            time: The time value. Expected type: `float`.
            seed: The seed value. Expected type: `int`.
            octaves: The octaves value. Expected type: `int`.
            falloff: The falloff value. Expected type: `float`.
        
        Returns:
            The return value. Type: `bytes`.
        """
        ...

    def exclusion_blend_rgb(self, base: bytes, overlay: bytes) -> bytes:
        """Blend two RGB byte buffers with the exclusion blend mode.
        
        Args:
            base: The base value. Expected type: `bytes`.
            overlay: The overlay value. Expected type: `bytes`.
        
        Returns:
            The return value. Type: `bytes`.
        """
        ...


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
    """Return the active optional acceleration module when callers allow it.
    
    Args:
        prefer_accelerated: The prefer accelerated value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        The return value. Type: `AcceleratedModule | None`.
    """

    return accelerated if prefer_accelerated else None


def is_acceleration_available() -> bool:
    """Return whether the optional compiled extension is active.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """

    return acceleration_provider() is not None


def acceleration_import_error() -> ImportError | None:
    """Return the import error that disabled acceleration, if any.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `ImportError | None`.
    """

    return _ACCELERATION_IMPORT_ERROR


def health_check() -> str:
    """Report which acceleration backend is currently serving wrapper calls.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `str`.
    """

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
