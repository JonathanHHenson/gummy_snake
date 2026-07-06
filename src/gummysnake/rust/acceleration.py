"""Optional acceleration extension loading and status helpers."""

from __future__ import annotations

from typing import Protocol, cast


class AcceleratedModule(Protocol):
    """Protocol implemented by the optional compiled acceleration module."""

    def health_check(self) -> str:
        """Return a short status string from the compiled acceleration module.

        Returns:
            Human-readable status text reported by the extension.
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
        """Compute deterministic 3D noise using the compiled extension.

        Args:
            x: First coordinate in noise space.
            y: Second coordinate in noise space.
            z: Third coordinate in noise space, often time for animation.
            seed: Integer seed that selects the noise pattern.
            octaves: Number of layered noise passes to combine.
            falloff: Amplitude multiplier applied after each octave.

        Returns:
            A floating-point noise value.
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
        """Render an animated RGBA noise image using the compiled extension.

        Args:
            width: Output image width in pixels.
            height: Output image height in pixels.
            density: Pixel-density scale used for the generated pattern.
            time: Animation time coordinate.
            seed: Integer seed that selects the noise pattern.
            octaves: Number of layered noise passes to combine.
            falloff: Amplitude multiplier applied after each octave.

        Returns:
            RGBA bytes with four bytes per output pixel.
        """

        ...

    def exclusion_blend_rgb(self, base: bytes, overlay: bytes) -> bytes:
        """Blend two RGB byte buffers with the exclusion blend mode.

        Args:
            base: Base RGB pixels with three bytes per pixel.
            overlay: Overlay RGB pixels with the same length as ``base``.

        Returns:
            Blended RGB bytes.
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
    """Return the optional acceleration module when it is available and requested."""
    return accelerated if prefer_accelerated else None


def is_acceleration_available() -> bool:
    """Return whether the optional acceleration extension was imported successfully."""
    return acceleration_provider() is not None


def acceleration_import_error() -> ImportError | None:
    """Return the import error from loading the optional acceleration module, if any."""
    return _ACCELERATION_IMPORT_ERROR


def health_check() -> str:
    """Return a short status string for the acceleration layer."""
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
