"""Native Pyglet renderer implementation."""

from __future__ import annotations

from math import atan2, cos, hypot, pi, sin
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from p5_py import constants as c
from p5_py.assets.image import Image
from p5_py.core.color import Color
from p5_py.core.state import StyleState
from p5_py.core.transform import Matrix2D
from p5_py.exceptions import ArgumentValidationError, BackendCapabilityError


def _rgba(color: Color | None) -> tuple[int, int, int, int] | None:
    return None if color is None else color.to_tuple()


class PygletRenderer:
    """Pyglet-native 2D renderer used by the interactive backend.

    The renderer accepts p5-py logical coordinates from ``SketchContext`` and maps them into
    physical framebuffer coordinates. Pyglet uses a bottom-left origin, so the mapping also flips
    the y axis from p5's top-left coordinate system.
    """

    width: int
    height: int
    physical_width: int
    physical_height: int
    pixel_density: float

    def __init__(
        self,
        width: int = 100,
        height: int = 100,
        pixel_density: float = 1.0,
        *,
        pyglet: Any | None = None,
    ) -> None:
        self._pyglet = pyglet
        self._batch: Any | None = None
        self._drawables: list[Any] = []
        self.resize(width, height, pixel_density)

    def resize(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        if width <= 0 or height <= 0:
            raise ArgumentValidationError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ArgumentValidationError("Pixel density must be positive.")
        self.width = int(width)
        self.height = int(height)
        self.pixel_density = float(pixel_density)
        self.physical_width = max(1, int(round(self.width * self.pixel_density)))
        self.physical_height = max(1, int(round(self.height * self.pixel_density)))
        self._reset_batch()

    def begin_frame(self) -> None:
        self._reset_batch()

    def end_frame(self) -> None:
        pass

    def background(self, color: Color) -> None:
        self.clear()
        self._filled_polygon(
            [
                (0, 0),
                (self.width, 0),
                (self.width, self.height),
                (0, self.height),
            ],
            color.to_tuple(),
            Matrix2D.identity(),
        )

    def clear(self) -> None:
        self._reset_batch()

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        color = _rgba(style.stroke_color or style.fill_color)
        if color is None:
            return
        px, py = self._to_framebuffer(*transform.transform_point(x, y))
        radius = max(0.5, style.stroke_weight * self.pixel_density / 2)
        self._add_shape("Circle", px, py, radius, color=color)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if style.stroke_color is None:
            return
        p1 = self._to_framebuffer(*transform.transform_point(x1, y1))
        p2 = self._to_framebuffer(*transform.transform_point(x2, y2))
        self._line_between(p1, p2, style)

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        if not points:
            return
        if len(points) == 1:
            self.point(points[0][0], points[0][1], style, transform)
            return
        transformed = [self._to_framebuffer(*transform.transform_point(x, y)) for x, y in points]
        if style.fill_color is not None and close and len(transformed) >= 3:
            self._raw_polygon(transformed, style.fill_color.to_tuple())
        if style.stroke_color is not None:
            self._joined_polyline(transformed, style, closed=close)

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        cx = x + width / 2
        cy = y + height / 2
        rx = width / 2
        ry = height / 2
        points = [(cx + cos(t) * rx, cy + sin(t) * ry) for t in _angle_steps(64)]
        self.polygon(points, style, transform, close=True)

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
        cx = x + width / 2
        cy = y + height / 2
        rx = width / 2
        ry = height / 2
        while stop < start:
            stop += 2 * pi
        steps = max(8, int(abs(stop - start) / (2 * pi) * 64))
        arc_points = [
            (
                cx + cos(start + (stop - start) * index / steps) * rx,
                cy + sin(start + (stop - start) * index / steps) * ry,
            )
            for index in range(steps + 1)
        ]
        if mode == c.PIE:
            self.polygon([(cx, cy), *arc_points], style, transform, close=True)
        elif mode == c.CHORD:
            self.polygon(arc_points, style, transform, close=True)
        else:
            if style.fill_color is not None and mode != c.OPEN:
                self.polygon(arc_points, style, transform, close=True)
            if style.stroke_color is not None:
                transformed = [
                    self._to_framebuffer(*transform.transform_point(px, py))
                    for px, py in arc_points
                ]
                self._joined_polyline(transformed, style, closed=False)

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
        del style
        if dw <= 0 or dh <= 0:
            return
        texture = self._texture_for_image(image, source)
        left, bottom, width, height, rotation = self._transformed_framebuffer_rect(
            dx, dy, dw, dh, transform
        )
        sprite = self._make_sprite(texture, x=left, y=bottom)
        sprite.scale_x = width / max(1, texture.width)
        sprite.scale_y = height / max(1, texture.height)
        if rotation:
            sprite.rotation = rotation
        self._drawables.append(sprite)

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
        lines = str(value).splitlines() or [""]
        for line_index, line in enumerate(lines):
            tx, ty = transform.transform_point(x, y + line_index * style.text_leading)
            px, py = self._to_framebuffer(tx, ty)
            label = self._make_label(
                line,
                x=px,
                y=py,
                style=style,
                transform=transform,
            )
            self._drawables.append(label)

    def text_width(self, value: str, style: StyleState) -> float:
        labels = [self._measure_label(line, style) for line in (str(value).splitlines() or [""])]
        return max(
            (float(getattr(label, "content_width", 0.0)) / self.pixel_density for label in labels),
            default=0.0,
        )

    def text_ascent(self, style: StyleState) -> float:
        font = self._load_pyglet_font(style)
        ascent = getattr(font, "ascent", None)
        if ascent is None:
            return style.text_size * 0.8
        return float(ascent) / self.pixel_density

    def text_descent(self, style: StyleState) -> float:
        font = self._load_pyglet_font(style)
        descent = getattr(font, "descent", None)
        if descent is None:
            return style.text_size * 0.2
        return abs(float(descent)) / self.pixel_density

    def load_pixels(self) -> list[int]:
        return list(self._read_framebuffer_rgba())

    def update_pixels(self, pixels: list[int]) -> None:
        raise BackendCapabilityError(
            "update_pixels() is not supported by the native Pyglet renderer yet. "
            "Use the headless backend for pixel-buffer workflows."
        )

    def save(self, path: str | Path) -> None:
        image = PILImage.frombytes(
            "RGBA",
            (self.physical_width, self.physical_height),
            self._read_framebuffer_rgba(),
        )
        image.save(path)

    def draw(self) -> None:
        if self._batch is not None:
            self._batch.draw()

    def bind_pyglet(self, pyglet: Any) -> None:
        if self._pyglet is pyglet:
            return
        self._pyglet = pyglet
        self._reset_batch()

    def _load_pyglet(self) -> Any:
        if self._pyglet is None:
            import pyglet

            self._pyglet = pyglet
        return self._pyglet

    def _reset_batch(self) -> None:
        self._drawables = []
        if self._pyglet is None:
            self._batch = None
            return
        self._batch = self._load_pyglet().graphics.Batch()

    def _to_framebuffer(self, x: float, y: float) -> tuple[float, float]:
        return x * self.pixel_density, self.physical_height - y * self.pixel_density

    def _line_between(
        self, p1: tuple[float, float], p2: tuple[float, float], style: StyleState
    ) -> None:
        color = _rgba(style.stroke_color)
        if color is None:
            return
        self._add_shape(
            "Line",
            p1[0],
            p1[1],
            p2[0],
            p2[1],
            thickness=max(1, style.stroke_weight * self.pixel_density),
            color=color,
        )

    def _joined_polyline(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        *,
        closed: bool,
    ) -> None:
        color = _rgba(style.stroke_color)
        if len(points) < 2 or color is None:
            return
        self._add_shape(
            "MultiLine",
            *points,
            closed=closed,
            thickness=max(1, style.stroke_weight * self.pixel_density),
            color=color,
        )

    def _filled_polygon(
        self,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        transform: Matrix2D,
    ) -> None:
        transformed = [self._to_framebuffer(*transform.transform_point(x, y)) for x, y in points]
        self._raw_polygon(transformed, color)

    def _raw_polygon(
        self, points: list[tuple[float, float]], color: tuple[int, int, int, int]
    ) -> None:
        if len(points) < 3:
            return
        self._add_shape("Polygon", *points, color=color)

    def _add_shape(self, name: str, *args: Any, **kwargs: Any) -> None:
        pyglet = self._load_pyglet()
        if self._batch is None:
            self._batch = pyglet.graphics.Batch()
        shape_class = getattr(pyglet.shapes, name)
        shape = shape_class(*args, **kwargs, batch=self._batch)
        self._drawables.append(shape)

    def _texture_for_image(
        self, image: Image, source: tuple[int, int, int, int] | None = None
    ) -> Any:
        source_image = image.pillow
        if source is not None:
            sx, sy, sw, sh = source
            source_image = source_image.crop((sx, sy, sx + sw, sy + sh))
        source_image = source_image.convert("RGBA")
        pyglet = self._load_pyglet()
        image_data = pyglet.image.ImageData(
            source_image.width,
            source_image.height,
            "RGBA",
            source_image.tobytes(),
            pitch=-source_image.width * 4,
        )
        texture_getter = getattr(image_data, "get_texture", None)
        return texture_getter() if callable(texture_getter) else image_data

    def _make_sprite(self, texture: Any, *, x: float, y: float) -> Any:
        pyglet = self._load_pyglet()
        if self._batch is None:
            self._batch = pyglet.graphics.Batch()
        return pyglet.sprite.Sprite(texture, x=x, y=y, batch=self._batch)

    def _transformed_framebuffer_rect(
        self, x: float, y: float, width: float, height: float, transform: Matrix2D
    ) -> tuple[float, float, float, float, float]:
        p1 = transform.transform_point(x, y)
        p2 = transform.transform_point(x + width, y)
        p3 = transform.transform_point(x, y + height)
        fb_points = [self._to_framebuffer(*point) for point in (p1, p2, p3)]
        left = fb_points[0][0]
        top = fb_points[0][1]
        width_px = max(0.0, hypot(fb_points[1][0] - left, fb_points[1][1] - top))
        height_px = max(0.0, hypot(fb_points[2][0] - left, fb_points[2][1] - top))
        bottom = top - height_px
        rotation = -atan2(fb_points[1][1] - top, fb_points[1][0] - left) * 180 / pi
        return left, bottom, width_px, height_px, rotation

    def _make_label(
        self,
        value: str,
        *,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> Any:
        pyglet = self._load_pyglet()
        if self._batch is None:
            self._batch = pyglet.graphics.Batch()
        label = pyglet.text.Label(
            value,
            font_name=self._pyglet_font_name(style),
            font_size=style.text_size * self.pixel_density,
            x=x,
            y=y,
            anchor_x=self._pyglet_anchor_x(style),
            anchor_y=self._pyglet_anchor_y(style),
            color=style.fill_color.to_tuple() if style.fill_color is not None else (0, 0, 0, 0),
            batch=self._batch,
        )
        rotation = -atan2(transform.b, transform.a) * 180 / pi
        if rotation:
            label.rotation = rotation
        return label

    def _measure_label(self, value: str, style: StyleState) -> Any:
        pyglet = self._load_pyglet()
        return pyglet.text.Label(
            value,
            font_name=self._pyglet_font_name(style),
            font_size=style.text_size * self.pixel_density,
        )

    def _load_pyglet_font(self, style: StyleState) -> Any:
        pyglet = self._load_pyglet()
        font_name = self._pyglet_font_name(style)
        return pyglet.font.load(font_name, style.text_size * self.pixel_density)

    def _pyglet_font_name(self, style: StyleState) -> str | None:
        font = style.text_font
        if font.path is not None:
            pyglet = self._load_pyglet()
            add_file = getattr(pyglet.font, "add_file", None)
            if callable(add_file):
                add_file(str(font.path))
            return font.name or font.path.stem
        return None if font.name == "default" else font.name

    def _pyglet_anchor_x(self, style: StyleState) -> str:
        if style.text_align_x == c.CENTER:
            return "center"
        if style.text_align_x == c.RIGHT:
            return "right"
        return "left"

    def _pyglet_anchor_y(self, style: StyleState) -> str:
        if style.text_align_y == c.TOP:
            return "top"
        if style.text_align_y == c.CENTER:
            return "center"
        if style.text_align_y == c.BOTTOM:
            return "bottom"
        return "baseline"

    def _read_framebuffer_rgba(self) -> bytes:
        self.draw()
        pyglet = self._load_pyglet()
        manager = pyglet.image.get_buffer_manager()
        color_buffer = manager.get_color_buffer()
        image_data_getter = getattr(color_buffer, "get_image_data", None)
        image_data = image_data_getter() if callable(image_data_getter) else color_buffer
        width = int(getattr(image_data, "width", self.physical_width))
        height = int(getattr(image_data, "height", self.physical_height))
        get_data = getattr(image_data, "get_data", None)
        if not callable(get_data):
            raise BackendCapabilityError("Pyglet framebuffer readback is unavailable.")
        data: Any = get_data("RGBA", -width * 4)
        if width == self.physical_width and height == self.physical_height:
            return bytes(data)
        image = PILImage.frombytes("RGBA", (width, height), bytes(data))
        return image.resize(
            (self.physical_width, self.physical_height), PILImage.Resampling.NEAREST
        ).tobytes()


def _angle_steps(count: int):
    return (2 * pi * index / count for index in range(count))
