"""Optional Rust canvas runtime bridge.

The public package remains importable without the compiled extension. Running
sketches requires :mod:`p5.rust._canvas` and fails with a clear package-specific
error when the extension is absent.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any, Protocol, cast

from p5.exceptions import BackendCapabilityError

P5_CANVAS_BUILD_COMMAND = (
    "uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml"
)
EXPECTED_CANVAS_ABI_VERSION = 1


class _RustP5Image(Protocol):
    width: int
    height: int
    version: int

    @staticmethod
    def from_file(path: str) -> _RustP5Image: ...

    @staticmethod
    def from_rgba_bytes(width: int, height: int, pixels: bytes) -> _RustP5Image: ...

    def save(self, path: str) -> None: ...

    def to_rgba_bytes(self) -> bytes: ...


class _CanvasModule(Protocol):
    Canvas: type[Any]
    P5Image: type[_RustP5Image]

    def health_check(self) -> str: ...

    def canvas_abi_version(self) -> int: ...

    def native_window_available(self) -> bool: ...

    def gpu_available(self) -> bool: ...


_loaded_canvas: ModuleType | None
_CANVAS_IMPORT_ERROR: ImportError | None

try:
    _loaded_canvas = import_module("p5.rust._canvas")
except ImportError as exc:
    _loaded_canvas = None
    _CANVAS_IMPORT_ERROR = exc
else:
    _CANVAS_IMPORT_ERROR = None

_canvas = cast(_CanvasModule | None, _loaded_canvas)


def is_canvas_available() -> bool:
    """Return whether the optional ``p5.rust._canvas`` extension is importable."""

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
        return int(value)
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
        return "unavailable: p5.rust._canvas is not installed"
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
        "p5-py requires the Rust canvas extension p5.rust._canvas. "
        f"Build it locally with `{P5_CANVAS_BUILD_COMMAND}`; bounded runs use "
        f"headless=True or max_frames, while interactive runs require a canvas extension "
        f"built with native window support.{detail}"
    )


def _validate_canvas_module(module: _CanvasModule) -> None:
    marker = canvas_abi_version()
    if marker != EXPECTED_CANVAS_ABI_VERSION:
        found = "missing" if marker is None else str(marker)
        raise BackendCapabilityError(
            "The installed p5.rust._canvas extension is incompatible with this p5py build "
            f"(expected canvas ABI {EXPECTED_CANVAS_ABI_VERSION}, found {found}). "
            f"Rebuild it with `{P5_CANVAS_BUILD_COMMAND}` or reinstall p5py_vibe so the "
            "Python package and Rust canvas runtime come from the same build."
        )

    health_check = getattr(module, "health_check", None)
    if not callable(health_check):
        raise BackendCapabilityError(
            "The installed p5.rust._canvas extension is missing health_check(). "
            f"Rebuild it with `{P5_CANVAS_BUILD_COMMAND}`."
        )
    try:
        health = str(health_check())
    except Exception as exc:
        raise BackendCapabilityError(
            "The installed p5.rust._canvas extension failed its health check. "
            f"Rebuild it with `{P5_CANVAS_BUILD_COMMAND}`. Health check error: {exc}"
        ) from exc
    if not health or health == "unavailable":
        raise BackendCapabilityError(
            "The installed p5.rust._canvas extension reported an unhealthy runtime "
            f"state ({health!r}). Rebuild it with `{P5_CANVAS_BUILD_COMMAND}`."
        )


__all__ = [
    "P5_CANVAS_BUILD_COMMAND",
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
