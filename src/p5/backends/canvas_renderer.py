"""Renderer adapter for the experimental Rust canvas backend."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from p5 import constants as c
from p5.assets.image import Image, P5Image
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
        "image_sampling": style.image_sampling,
        "text_font_path": str(style.text_font.path) if style.text_font.path is not None else None,
        "text_font_name": style.text_font.name,
        "text_size": float(style.text_size),
        "text_align_x": style.text_align_x,
        "text_align_y": style.text_align_y,
        "text_leading": float(style.text_leading),
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
        self._image_cache_versions: dict[int, int] = {}

    def resize(
        self,
        width: int,
        height: int,
        pixel_density: float = 1.0,
        *,
        mode: str = "headless",
    ) -> None:
        canvas_type = self._canvas_type()
        try:
            if self._canvas is None:
                self._canvas = canvas_type(width, height, pixel_density, mode, c.P2D)
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

    def runtime_canvas(self) -> Any:
        """Return the underlying Rust canvas/runtime object for backend event-loop calls."""

        return self._require_canvas()

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
        image: Image | P5Image,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: StyleState,
        transform: Matrix2D,
        *,
        source: tuple[int, int, int, int] | None = None,
        cache: bool = True,
    ) -> None:
        if isinstance(image, P5Image):
            self._call(
                "image drawing",
                self._require_canvas().draw_canvas_image,
                image._rust_image,
                dx,
                dy,
                dw,
                dh,
                _style_payload(style),
                _matrix_payload(transform),
                source,
            )
            return
        image_key = id(image)
        cached_version = self._image_cache_versions.get(image_key) if cache else None
        image_pixels = None if cached_version == image.version else image.to_rgba_bytes()
        callback = getattr(self._require_canvas(), "draw_cached_image", None)
        if cache and callable(callback):
            self._call(
                "image drawing",
                callback,
                image_key,
                image.version,
                image_pixels,
                image.width,
                image.height,
                dx,
                dy,
                dw,
                dh,
                _style_payload(style),
                _matrix_payload(transform),
                source,
            )
            self._image_cache_versions[image_key] = image.version
            return
        self._call(
            "image drawing",
            self._require_canvas().draw_image,
            image_pixels if image_pixels is not None else image.to_rgba_bytes(),
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            _style_payload(style),
            _matrix_payload(transform),
            source,
        )

    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if style.fill_color is None:
            return
        self._call(
            "text drawing",
            self._require_canvas().text,
            value,
            x,
            y,
            _style_payload(style),
            _matrix_payload(transform),
        )

    def text_width(self, value: str, style: StyleState) -> float:
        return float(
            self._call(
                "text measurement",
                self._require_canvas().text_width,
                value,
                _style_payload(style),
            )
        )

    def text_ascent(self, style: StyleState) -> float:
        return float(
            self._call(
                "text ascent measurement",
                self._require_canvas().text_ascent,
                _style_payload(style),
            )
        )

    def text_descent(self, style: StyleState) -> float:
        return float(
            self._call(
                "text descent measurement",
                self._require_canvas().text_descent,
                _style_payload(style),
            )
        )

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
        if isinstance(source_image, Image):
            self._call(
                "region blending",
                self._require_canvas().blend_region,
                source_image.to_rgba_bytes(),
                source_image.width,
                source_image.height,
                source,
                destination,
                mode,
            )
            return
        if source_image is None:
            self._call(
                "region blending",
                self._require_canvas().blend_region,
                None,
                None,
                None,
                source,
                destination,
                mode,
            )
            return
        convert = getattr(source_image, "convert", None)
        if callable(convert):
            source_image = convert("RGBA")
        width = getattr(source_image, "width", None)
        height = getattr(source_image, "height", None)
        tobytes = getattr(source_image, "tobytes", None)
        if not isinstance(width, int) or not isinstance(height, int) or not callable(tobytes):
            raise ArgumentValidationError("blend_region() source image must expose RGBA pixels.")
        self._call(
            "region blending",
            self._require_canvas().blend_region,
            tobytes(),
            width,
            height,
            source,
            destination,
            mode,
        )

    def save(self, path: str | Path) -> None:
        self._call("canvas export", self._require_canvas().save, str(path))

    def _canvas_type(self) -> type[Any]:
        canvas_type = getattr(self._canvas_module, "Canvas", None)
        if canvas_type is None:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend found p5.rust._canvas, but the extension does "
                "not expose Canvas. Rebuild p5_canvas before running p5-py."
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
