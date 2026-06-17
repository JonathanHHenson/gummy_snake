"""Renderer adapter for the experimental Rust canvas backend."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from p5 import constants as c
from p5.assets.image import Image
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.exceptions import ArgumentValidationError, BackendCapabilityError


def _color_payload(color: Color | None) -> tuple[int, int, int, int] | None:
    return None if color is None else color.to_tuple()


def _style_payload(style: StyleState) -> dict[str, object]:
    return {
        "fill": _color_payload(style.fill_color),
        "stroke": _color_payload(style.stroke_color),
        "stroke_weight": float(style.stroke_weight),
        "blend_mode": style.blend_mode,
        "erasing": style.erasing,
    }


def _matrix_payload(transform: Matrix2D) -> tuple[float, float, float, float, float, float]:
    return (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)


class CanvasRenderer:
    """Renderer protocol adapter for ``p5.rust._canvas``.

    The adapter keeps Python-facing renderer attributes mirrored from the Rust
    canvas and translates p5-py state objects into primitive bridge payloads.
    """

    def __init__(self, canvas_module: object | None = None) -> None:
        self._canvas_module = canvas_module
        self._canvas: Any | None = None
        self.width = 0
        self.height = 0
        self.physical_width = 0
        self.physical_height = 0
        self.pixel_density = 1.0

    def resize(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        canvas_type = self._canvas_type()
        try:
            if self._canvas is None:
                self._canvas = canvas_type(width, height, pixel_density, "headless", c.P2D)
            else:
                self._canvas.resize(width, height, pixel_density, c.P2D)
            self._sync_dimensions()
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    def display_density(self) -> float:
        if self._canvas is None:
            return 1.0
        return float(self._call("display-density reporting", self._canvas.display_density))

    def begin_frame(self) -> None:
        self._require_canvas().begin_frame()

    def end_frame(self) -> None:
        self._require_canvas().end_frame()

    def present(self) -> None:
        self._require_canvas().present()

    def close(self) -> None:
        if self._canvas is not None:
            self._canvas.close()

    def background(self, color: Color) -> None:
        self._call("background drawing", self._require_canvas().background, color.to_tuple())

    def clear(self) -> None:
        self._call("canvas clearing", self._require_canvas().clear)

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        self._call(
            "point drawing",
            self._require_canvas().point,
            x,
            y,
            _style_payload(style),
            _matrix_payload(transform),
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._call(
            "line drawing",
            self._require_canvas().line,
            x1,
            y1,
            x2,
            y2,
            _style_payload(style),
            _matrix_payload(transform),
        )

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        self._call(
            "polygon drawing",
            self._require_canvas().polygon,
            points,
            _style_payload(style),
            _matrix_payload(transform),
            close,
        )

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._call(
            "ellipse drawing",
            self._require_canvas().ellipse,
            x,
            y,
            width,
            height,
            _style_payload(style),
            _matrix_payload(transform),
        )

    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: str,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._call(
            "arc drawing",
            self._require_canvas().arc,
            x,
            y,
            width,
            height,
            start,
            stop,
            mode,
            _style_payload(style),
            _matrix_payload(transform),
        )

    def draw_image(
        self,
        image: Image,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: StyleState,
        transform: Matrix2D,
        *,
        source: tuple[int, int, int, int] | None = None,
    ) -> None:
        self._raise_unimplemented("image drawing")

    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._raise_unimplemented("text drawing")

    def text_width(self, value: str, style: StyleState) -> float:
        self._raise_unimplemented("text metrics")

    def text_ascent(self, style: StyleState) -> float:
        self._raise_unimplemented("text metrics")

    def text_descent(self, style: StyleState) -> float:
        self._raise_unimplemented("text metrics")

    def load_pixels(self) -> list[int]:
        pixels = self._call("pixel readback", self._require_canvas().load_pixels)
        return list(pixels)

    def update_pixels(self, pixels: Sequence[int]) -> None:
        try:
            payload = bytes(pixels)
        except ValueError as exc:
            raise ArgumentValidationError(
                "Pixel values must be integers between 0 and 255."
            ) from exc
        self._call("pixel upload", self._require_canvas().update_pixels, payload)

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: str,
    ) -> None:
        self._raise_unimplemented("region blending")

    def save(self, path: str | Path) -> None:
        self._call("canvas export", self._require_canvas().save, str(path))

    def _canvas_type(self) -> type[Any]:
        canvas_type = getattr(self._canvas_module, "Canvas", None)
        if canvas_type is None:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend found p5.rust._canvas, but the extension does "
                "not expose Canvas. Rebuild p5_canvas or select backend='headless'."
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
        if self._canvas is None:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend has not allocated a canvas yet. Call "
                "create_canvas() before drawing."
            )
        return self._canvas

    def _call(self, operation: str, callback: Callable[..., Any], *args: object) -> Any:
        try:
            return callback(*args)
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc
        except RuntimeError as exc:
            raise BackendCapabilityError(
                f"The 'canvas' backend failed during {operation}: {exc}"
            ) from exc

    def _raise_unimplemented(self, operation: str) -> NoReturn:
        raise BackendCapabilityError(
            "The experimental 'canvas' backend found p5.rust._canvas, but "
            f"{operation} is not implemented yet. Use backend='pyglet' or "
            "backend='headless' for that feature."
        )
