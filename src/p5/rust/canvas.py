"""Optional Rust canvas backend bridge.

The public package remains importable without the compiled extension. Selecting
``backend="canvas"`` requires :mod:`p5.rust._canvas` and fails with a clear
package-specific error when the extension is absent.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any, Protocol, cast

from p5.exceptions import BackendCapabilityError

P5_CANVAS_BUILD_COMMAND = (
    "uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml"
)


class _CanvasModule(Protocol):
    Canvas: type[Any]

    def health_check(self) -> str: ...


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
    return str(_canvas.health_check())


def require_canvas_extension() -> _CanvasModule:
    """Return the loaded canvas extension or raise a backend capability error."""

    if _canvas is not None:
        return _canvas

    detail = f" Import failed: {_CANVAS_IMPORT_ERROR}" if _CANVAS_IMPORT_ERROR else ""
    raise BackendCapabilityError(
        "The 'canvas' backend requires the optional Rust extension p5.rust._canvas. "
        f"Build it locally with `{P5_CANVAS_BUILD_COMMAND}` or select backend='pyglet' "
        f"or backend='headless'.{detail}"
    )


__all__ = [
    "P5_CANVAS_BUILD_COMMAND",
    "canvas_health_check",
    "canvas_import_error",
    "is_canvas_available",
    "require_canvas_extension",
]
