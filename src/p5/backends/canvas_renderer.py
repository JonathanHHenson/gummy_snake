"""Renderer adapter for the experimental Rust canvas backend."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Buffer, Callable, Hashable, Sequence
from pathlib import Path
from typing import Any, cast

from p5 import constants as c
from p5.assets.image import Image, P5Image
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.exceptions import ArgumentValidationError, BackendCapabilityError

_TEXT_METRIC_CACHE_LIMIT = 256
_STYLE_PAYLOAD_CACHE_LIMIT = 256
_MATRIX_PAYLOAD_CACHE_LIMIT = 256
_IMAGE_VERSION_CACHE_LIMIT = 1024
_PERFORMANCE_COUNTER_KEYS = (
    "gpu_draws",
    "cpu_fallbacks",
    "pixel_readbacks",
    "pixel_uploads",
    "image_cache_hits",
    "image_cache_misses",
    "texture_cache_hits",
    "texture_uploads",
    "text_cache_hits",
    "text_cache_misses",
    "text_cache_evictions",
    "text_measurements",
    "bridge_calls",
    "frames_presented",
    "gpu_frames_rendered",
    "event_polls",
)
_TextMetricKey = tuple[str, str | None, tuple[tuple[str, Hashable], ...]]
_MatrixPayload = tuple[float, float, float, float, float, float]


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


def _text_metric_key(kind: str, style: StyleState, value: str | None = None) -> _TextMetricKey:
    payload = _style_payload(style)
    return (
        kind,
        value,
        tuple(
            sorted(
                (payload_key, cast(Hashable, payload_value))
                for payload_key, payload_value in payload.items()
            )
        ),
    )


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
        self._image_cache_versions: OrderedDict[int, int] = OrderedDict()
        self._text_metric_cache: OrderedDict[_TextMetricKey, float] = OrderedDict()
        self._style_payload_cache: dict[int, tuple[int, dict[str, object]]] = {}
        self._matrix_payload_cache: dict[int, tuple[Matrix2D, _MatrixPayload]] = {}
        self._line_batch: list[tuple[float, float, float, float]] = []
        self._line_batch_style: dict[str, object] | None = None
        self._line_batch_matrix: _MatrixPayload | None = None
        self._performance_counters: dict[str, int] = dict.fromkeys(_PERFORMANCE_COUNTER_KEYS, 0)

    def resize(
        self,
        width: int,
        height: int,
        pixel_density: float = 1.0,
        *,
        mode: str = "headless",
    ) -> None:
        self._flush_line_batch()
        canvas_type = self._canvas_type()
        try:
            if self._canvas is None:
                self._canvas = canvas_type(width, height, pixel_density, mode, c.P2D)
            else:
                self._canvas.resize(width, height, pixel_density, c.P2D)
            self._sync_dimensions()
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    def _style_payload(self, style: StyleState) -> dict[str, object]:
        revision = style.revision
        key = id(style)
        cached = self._style_payload_cache.get(key)
        if cached is not None and cached[0] == revision:
            return cached[1]
        payload = _style_payload(style)
        if len(self._style_payload_cache) >= _STYLE_PAYLOAD_CACHE_LIMIT:
            self._style_payload_cache.clear()
        self._style_payload_cache[key] = (revision, payload)
        return payload

    def _matrix_payload(self, transform: Matrix2D) -> _MatrixPayload:
        key = id(transform)
        cached = self._matrix_payload_cache.get(key)
        if cached is not None and cached[0] == transform:
            return cached[1]
        payload = _matrix_payload(transform)
        if len(self._matrix_payload_cache) >= _MATRIX_PAYLOAD_CACHE_LIMIT:
            self._matrix_payload_cache.clear()
        self._matrix_payload_cache[key] = (transform, payload)
        return payload

    def display_density(self) -> float:
        if self._canvas is None:
            return 1.0
        return float(self._call("display-density reporting", self._canvas.display_density))

    def performance_counters(self) -> dict[str, object]:
        counters: dict[str, object] = dict(self._performance_counters)
        canvas = self._canvas
        callback = getattr(canvas, "performance_counters", None) if canvas is not None else None
        if callable(callback):
            native = callback()
            if isinstance(native, dict):
                counters["native"] = {
                    str(key): int(value)
                    for key, value in native.items()
                    if isinstance(value, int | float)
                }
        return counters

    def reset_performance_counters(self) -> None:
        self._performance_counters = dict.fromkeys(_PERFORMANCE_COUNTER_KEYS, 0)
        canvas = self._canvas
        callback = (
            getattr(canvas, "reset_performance_counters", None) if canvas is not None else None
        )
        if callable(callback):
            callback()

    def _count(self, name: str, amount: int = 1) -> None:
        self._performance_counters[name] = int(self._performance_counters.get(name, 0)) + amount

    def begin_frame(self) -> None:
        self._require_canvas().begin_frame()

    def end_frame(self) -> None:
        self._flush_line_batch()
        self._require_canvas().end_frame()

    def present(self) -> None:
        self._flush_line_batch()
        self._require_canvas().present()
        self._count("frames_presented")

    def close(self) -> None:
        self._flush_line_batch()
        if self._canvas is not None:
            self._canvas.close()

    def runtime_canvas(self) -> Any:
        """Return the underlying Rust canvas/runtime object for backend event-loop calls."""

        return self._require_canvas()

    def background(self, color: Color) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call("background drawing", self._require_canvas().background, color.to_tuple())

    def clear(self) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call("canvas clearing", self._require_canvas().clear)

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call(
            "point drawing",
            self._require_canvas().point,
            x,
            y,
            self._style_payload(style),
            self._matrix_payload(transform),
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
        style_payload = self._style_payload(style)
        matrix_payload = self._matrix_payload(transform)
        if self._line_batch and (
            self._line_batch_style is not style_payload
            or self._line_batch_matrix is not matrix_payload
        ):
            self._flush_line_batch()
        self._line_batch.append((x1, y1, x2, y2))
        self._line_batch_style = style_payload
        self._line_batch_matrix = matrix_payload

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call(
            "polygon drawing",
            self._require_canvas().polygon,
            points,
            self._style_payload(style),
            self._matrix_payload(transform),
            close,
        )

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._flush_line_batch()
        callback = getattr(self._require_canvas(), "rect", None)
        if callable(callback):
            self._count("gpu_draws")
            self._call(
                "rectangle drawing",
                callback,
                x,
                y,
                width,
                height,
                self._style_payload(style),
                self._matrix_payload(transform),
            )
            return
        self.polygon(
            [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
            style,
            transform,
            close=True,
        )

    def triangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._flush_line_batch()
        callback = getattr(self._require_canvas(), "triangle", None)
        if callable(callback):
            self._count("gpu_draws")
            self._call(
                "triangle drawing",
                callback,
                x1,
                y1,
                x2,
                y2,
                x3,
                y3,
                self._style_payload(style),
                self._matrix_payload(transform),
            )
            return
        self.polygon([(x1, y1), (x2, y2), (x3, y3)], style, transform, close=True)

    def quad(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._flush_line_batch()
        callback = getattr(self._require_canvas(), "quad", None)
        if callable(callback):
            self._count("gpu_draws")
            self._call(
                "quadrilateral drawing",
                callback,
                x1,
                y1,
                x2,
                y2,
                x3,
                y3,
                x4,
                y4,
                self._style_payload(style),
                self._matrix_payload(transform),
            )
            return
        self.polygon([(x1, y1), (x2, y2), (x3, y3), (x4, y4)], style, transform, close=True)

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call(
            "ellipse drawing",
            self._require_canvas().ellipse,
            x,
            y,
            width,
            height,
            self._style_payload(style),
            self._matrix_payload(transform),
        )

    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: c.ArcMode,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
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
            self._style_payload(style),
            self._matrix_payload(transform),
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
        self._flush_line_batch()
        if isinstance(image, P5Image):
            self._count("gpu_draws")
            self._call(
                "image drawing",
                self._require_canvas().draw_canvas_image,
                image._rust_image,
                dx,
                dy,
                dw,
                dh,
                self._style_payload(style),
                self._matrix_payload(transform),
                source,
            )
            return
        if image.rust_image is not None:
            self._count("gpu_draws")
            self._call(
                "image drawing",
                self._require_canvas().draw_canvas_image,
                image.rust_image._rust_image,
                dx,
                dy,
                dw,
                dh,
                self._style_payload(style),
                self._matrix_payload(transform),
                source,
            )
            return
        image_key = image.cache_key
        cached_version = self._image_cache_versions.get(image_key) if cache else None
        image_pixels = None if cached_version == image.version else image.to_rgba_bytes()
        if image_pixels is None:
            self._count("image_cache_hits")
            self._count("texture_cache_hits")
        else:
            self._count("image_cache_misses")
            self._count("texture_uploads")
        callback = getattr(self._require_canvas(), "draw_cached_image", None)
        if cache and callable(callback):
            self._count("gpu_draws")
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
                self._style_payload(style),
                self._matrix_payload(transform),
                source,
            )
            self._remember_image_cache_version(image_key, image.version)
            return
        self._count("cpu_fallbacks")
        self._count("pixel_uploads")
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
            self._style_payload(style),
            self._matrix_payload(transform),
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
        self._flush_line_batch()
        if style.fill_color is None:
            return
        self._count("gpu_draws")
        self._call(
            "text drawing",
            self._require_canvas().text,
            value,
            x,
            y,
            self._style_payload(style),
            self._matrix_payload(transform),
        )

    def text_width(self, value: str, style: StyleState) -> float:
        self._flush_line_batch()
        return self._cached_text_metric(
            _text_metric_key("width", style, value),
            "text measurement",
            self._require_canvas().text_width,
            value,
            self._style_payload(style),
        )

    def text_ascent(self, style: StyleState) -> float:
        self._flush_line_batch()
        return self._cached_text_metric(
            _text_metric_key("ascent", style),
            "text ascent measurement",
            self._require_canvas().text_ascent,
            self._style_payload(style),
        )

    def text_descent(self, style: StyleState) -> float:
        self._flush_line_batch()
        return self._cached_text_metric(
            _text_metric_key("descent", style),
            "text descent measurement",
            self._require_canvas().text_descent,
            self._style_payload(style),
        )

    def load_pixels(self) -> list[int]:
        self._flush_line_batch()
        self._count("pixel_readbacks")
        pixels = self._call("pixel readback", self._require_canvas().load_pixels)
        return list(pixels)

    def load_pixel_bytes(self) -> bytes:
        self._flush_line_batch()
        self._count("pixel_readbacks")
        callback = getattr(self._require_canvas(), "load_pixel_bytes", None)
        if callable(callback):
            return bytes(self._call("pixel byte readback", callback))
        return bytes(self._call("pixel readback", self._require_canvas().load_pixels))

    def load_pixel_region(self, x: int, y: int, width: int, height: int) -> bytes:
        self._flush_line_batch()
        self._count("pixel_readbacks")
        return bytes(
            self._call(
                "pixel region readback",
                self._require_canvas().load_pixel_region,
                int(x),
                int(y),
                int(width),
                int(height),
            )
        )

    def update_pixels(self, pixels: Sequence[int] | Buffer) -> None:
        self._flush_line_batch()
        try:
            payload = bytes(pixels)
        except ValueError as exc:
            raise ArgumentValidationError(
                "Pixel values must be integers between 0 and 255."
            ) from exc
        self._count("pixel_uploads")
        self._call("pixel upload", self._require_canvas().update_pixels, payload)

    def update_pixel_region(
        self,
        pixels: Sequence[int] | Buffer,
        width: int,
        height: int,
        x: int,
        y: int,
        *,
        alpha_composite: bool = True,
    ) -> None:
        self._flush_line_batch()
        try:
            payload = bytes(pixels)
        except ValueError as exc:
            raise ArgumentValidationError(
                "Pixel values must be integers between 0 and 255."
            ) from exc
        self._count("pixel_uploads")
        self._call(
            "pixel region upload",
            self._require_canvas().update_pixel_region,
            payload,
            int(width),
            int(height),
            int(x),
            int(y),
            alpha_composite,
        )

    def filter_pixels(self, mode: c.ImageFilter, value: float | None = None) -> None:
        self._flush_line_batch()
        self._count("cpu_fallbacks")
        self._count("pixel_uploads")
        self._call("pixel filter", self._require_canvas().filter_pixels, mode.value, value)

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None:
        self._flush_line_batch()
        self._count("cpu_fallbacks")
        self._count("pixel_uploads")
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
        self._flush_line_batch()
        self._call("canvas export", self._require_canvas().save, str(path))

    def _flush_line_batch(self) -> None:
        if not self._line_batch:
            return
        lines = self._line_batch
        style = self._line_batch_style
        matrix = self._line_batch_matrix
        self._line_batch = []
        self._line_batch_style = None
        self._line_batch_matrix = None
        if style is None or matrix is None:
            return
        canvas = self._require_canvas()
        batch_lines = getattr(canvas, "batch_lines", None)
        if callable(batch_lines):
            self._count("gpu_draws", len(lines))
            self._call("batched line drawing", batch_lines, lines, style, matrix)
            return
        for x1, y1, x2, y2 in lines:
            self._count("gpu_draws")
            self._call("line drawing", canvas.line, x1, y1, x2, y2, style, matrix)

    def _remember_image_cache_version(self, image_key: int, version: int) -> None:
        self._image_cache_versions[image_key] = version
        self._image_cache_versions.move_to_end(image_key)
        while len(self._image_cache_versions) > _IMAGE_VERSION_CACHE_LIMIT:
            self._image_cache_versions.popitem(last=False)

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
        self._count("bridge_calls")
        try:
            return callback(*args)
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc
        except RuntimeError as exc:
            raise BackendCapabilityError(
                f"The 'canvas' backend failed during {operation}: {exc}"
            ) from exc

    def _cached_text_metric(
        self,
        key: _TextMetricKey,
        operation: str,
        callback: Callable[..., Any],
        *args: object,
    ) -> float:
        cached = self._text_metric_cache.get(key)
        if cached is not None:
            self._text_metric_cache.move_to_end(key)
            self._count("text_cache_hits")
            return cached
        self._count("text_cache_misses")
        self._count("text_measurements")
        value = float(self._call(operation, callback, *args))
        self._text_metric_cache[key] = value
        if len(self._text_metric_cache) > _TEXT_METRIC_CACHE_LIMIT:
            self._text_metric_cache.popitem(last=False)
            self._count("text_cache_evictions")
        return value
