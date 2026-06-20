# pyright: reportConstantRedefinition=false
"""Optional Rust canvas runtime bridge.

The public package remains importable without the compiled extension. Running
sketches requires :mod:`gummysnake.rust._canvas` and fails with a clear package-specific
error when the extension is absent.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any, Protocol, cast

from gummysnake.exceptions import BackendCapabilityError

GUMMY_CANVAS_BUILD_COMMAND = (
    "uvx maturin develop --release --manifest-path crates/gummy_canvas/Cargo.toml"
)
EXPECTED_CANVAS_ABI_VERSION = 1


class _RustCanvasImage(Protocol):
    width: int
    height: int
    version: int

    @staticmethod
    def from_file(path: str) -> _RustCanvasImage: ...

    @staticmethod
    def from_rgba_bytes(width: int, height: int, pixels: bytes) -> _RustCanvasImage: ...

    def save(self, path: str) -> None: ...

    def to_rgba_bytes(self) -> bytes: ...


class _CanvasModule(Protocol):
    Canvas: type[Any]
    CanvasImage: type[_RustCanvasImage]

    def health_check(self) -> str: ...

    def canvas_abi_version(self) -> int: ...

    def native_window_available(self) -> bool: ...

    def gpu_available(self) -> bool: ...

    def image_resize_rgba(
        self, width: int, height: int, pixels: bytes, target_width: int, target_height: int
    ) -> bytes: ...

    def image_crop_rgba(
        self, width: int, height: int, pixels: bytes, sx: int, sy: int, sw: int, sh: int
    ) -> bytes: ...

    def image_alpha_composite_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        source_width: int,
        source_height: int,
        source_pixels: bytes,
        dx: int,
        dy: int,
    ) -> bytes: ...

    def image_mask_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        mask_width: int,
        mask_height: int,
        mask_pixels: bytes,
    ) -> bytes: ...

    def image_filter_rgba(
        self, width: int, height: int, pixels: bytes, mode: str, value: float | None = None
    ) -> bytes: ...

    def media_frame_to_rgba(
        self, width: int, height: int, channels: int, pixels: bytes
    ) -> bytes: ...

    def parse_obj_model(self, text: str, source: str, normalize: bool) -> dict[str, Any]: ...

    def project_shade_faces(
        self,
        meshes: list[dict[str, Any]],
        camera: dict[str, Any],
        projection: dict[str, Any],
        viewport_width: float,
        viewport_height: float,
        material: dict[str, Any],
        lights: list[dict[str, Any]],
        normal_material: bool,
        cull_backfaces: bool,
    ) -> list[dict[str, Any]]: ...

    def rasterize_faces_rgba(
        self, width: int, height: int, faces: list[dict[str, Any]]
    ) -> bytes: ...


_loaded_canvas: ModuleType | None
_CANVAS_IMPORT_ERROR: ImportError | None

try:
    _loaded_canvas = import_module("gummysnake.rust._canvas")
except ImportError as exc:
    _loaded_canvas = None
    _CANVAS_IMPORT_ERROR = exc
else:
    _CANVAS_IMPORT_ERROR = None

_canvas = cast(_CanvasModule | None, _loaded_canvas)


def is_canvas_available() -> bool:
    """Return whether the optional ``gummysnake.rust._canvas`` extension is importable."""

    return _canvas is not None


def canvas_import_error() -> ImportError | None:
    """Return the import error that made the Rust canvas extension unavailable."""

    return _CANVAS_IMPORT_ERROR


def canvas_health_check() -> str:
    """Report the Rust canvas bridge health state."""

    if _canvas is None:
        return "unavailable"
    try:
        return str(_canvas.health_check())
    except Exception as exc:
        return f"unhealthy: {exc}"


def canvas_abi_version() -> int | None:
    """Return the loaded canvas extension ABI marker when available."""

    if _canvas is None:
        return None
    marker = getattr(_canvas, "canvas_abi_version", None)
    try:
        value = marker() if callable(marker) else getattr(_canvas, "CANVAS_ABI_VERSION", None)
    except Exception:
        return None
    if value is None:
        return None
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return None


def canvas_native_window_available() -> bool:
    """Return whether the loaded canvas extension has native window support."""

    if _canvas is None:
        return False
    native_window_available = getattr(_canvas, "native_window_available", None)
    return bool(native_window_available()) if callable(native_window_available) else False


def canvas_gpu_available() -> bool:
    """Return whether the loaded canvas extension can initialize a GPU adapter."""

    if _canvas is None:
        return False
    gpu_available = getattr(_canvas, "gpu_available", None)
    return bool(gpu_available()) if callable(gpu_available) else False


def canvas_gpu_status() -> str:
    """Return an actionable GPU availability diagnostic for the loaded extension."""

    if _canvas is None:
        return "unavailable: gummysnake.rust._canvas is not installed"
    try:
        available = canvas_gpu_available()
    except Exception as exc:
        return f"unavailable: GPU capability probe failed: {exc}"
    if available:
        return "available"
    return (
        "unavailable: headless rendering can continue through CPU-backed canvas paths, "
        "but native interactive presentation and GPU-accelerated drawing may be disabled "
        "or slower on this machine/build."
    )


def require_canvas_extension() -> _CanvasModule:
    """Return the loaded canvas extension or raise a backend capability error."""

    if _canvas is not None:
        _validate_canvas_module(_canvas)
        return _canvas

    detail = f" Import failed: {_CANVAS_IMPORT_ERROR}" if _CANVAS_IMPORT_ERROR else ""
    raise BackendCapabilityError(
        "Gummy Snake requires the Rust canvas extension gummysnake.rust._canvas. "
        f"Build it locally with `{GUMMY_CANVAS_BUILD_COMMAND}`; bounded runs use "
        f"headless=True or max_frames, while interactive runs require a canvas extension "
        f"built with native window support.{detail}"
    )


def _validate_canvas_module(module: _CanvasModule) -> None:
    marker = canvas_abi_version()
    if marker != EXPECTED_CANVAS_ABI_VERSION:
        found = "missing" if marker is None else str(marker)
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas extension is incompatible with this "
            f"Gummy Snake build (expected canvas ABI {EXPECTED_CANVAS_ABI_VERSION}, "
            f"found {found}). "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}` or reinstall gummy-snake so the "
            "Python package and Rust canvas runtime come from the same build."
        )

    health_check = getattr(module, "health_check", None)
    if not callable(health_check):
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas extension is missing health_check(). "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )
    try:
        health = str(health_check())
    except Exception as exc:
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas extension failed its health check. "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`. Health check error: {exc}"
        ) from exc
    if not health or health == "unavailable":
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas extension reported an unhealthy runtime "
            f"state ({health!r}). Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )


__all__ = [
    "GUMMY_CANVAS_BUILD_COMMAND",
    "EXPECTED_CANVAS_ABI_VERSION",
    "canvas_abi_version",
    "canvas_health_check",
    "canvas_gpu_available",
    "canvas_gpu_status",
    "canvas_native_window_available",
    "canvas_import_error",
    "is_canvas_available",
    "require_canvas_extension",
]
