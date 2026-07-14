"""Bridge helpers for calls into the Rust canvas runtime."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class _BridgeHost(Protocol):
    _canvas_module: object | None
    _canvas: Any | None

    def _count(self, name: str, amount: int = 1) -> None: ...


class CanvasRendererBridgeMixin:
    width: int
    height: int
    physical_width: int
    physical_height: int
    pixel_density: float

    def display_density(self) -> float:
        host = cast(_BridgeHost, self)
        if host._canvas is None:
            return 1.0
        return float(self._call("display-density reporting", host._canvas.display_density))

    def _canvas_type(self) -> type[Any]:
        host = cast(_BridgeHost, self)
        canvas_type = getattr(host._canvas_module, "Canvas", None)
        if canvas_type is None:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend found gummysnake.rust._canvas, but the "
                "runtime does not expose Canvas. Rebuild gummy_canvas before running Gummy Snake."
            )
        return canvas_type

    def _sync_dimensions(self) -> None:
        logical_width, logical_height, physical_width, physical_height, pixel_density = (
            self._require_canvas().dimensions()
        )
        self.width = int(logical_width)
        self.height = int(logical_height)
        self.physical_width = int(physical_width)
        self.physical_height = int(physical_height)
        self.pixel_density = float(pixel_density)

    def _require_canvas(self) -> Any:
        canvas = cast(_BridgeHost, self)._canvas
        if canvas is None:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend has not allocated a canvas yet. "
                "Call create_canvas() before drawing."
            )
        return canvas

    def _call[T](self, operation: str, callback: Callable[..., T], *args: object) -> T:
        host = cast(_BridgeHost, self)
        host._count("bridge_calls")
        try:
            return callback(*args)
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc
        except RuntimeError as exc:
            raise BackendCapabilityError(
                f"The 'canvas' backend failed during {operation}: {exc}"
            ) from exc

    def _should_close(self) -> bool:
        canvas = cast(_BridgeHost, self)._canvas
        should_close = getattr(canvas, "should_close", None) if canvas is not None else None
        return bool(should_close()) if callable(should_close) else False

    def _require_canvas_method(self, name: str, operation: str) -> Callable[..., Any]:
        callback = getattr(self._require_canvas(), name, None)
        if callable(callback):
            return callback
        raise BackendCapabilityError(
            f"The installed gummysnake.rust._canvas runtime does not expose {name}() for "
            f"{operation}. Rebuild gummy_canvas before using this drawing feature."
        )
