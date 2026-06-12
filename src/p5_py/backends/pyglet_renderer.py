"""Native Pyglet renderer implementation."""

from __future__ import annotations

from math import cos, pi, sin
from pathlib import Path
from typing import Any

from p5_py import constants as c
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

    def load_pixels(self) -> list[int]:
        raise BackendCapabilityError(
            "load_pixels() is not supported by the native Pyglet renderer yet. "
            "Use the headless backend for deterministic pixel reads."
        )

    def update_pixels(self, pixels: list[int]) -> None:
        raise BackendCapabilityError(
            "update_pixels() is not supported by the native Pyglet renderer yet. "
            "Use the headless backend for pixel-buffer workflows."
        )

    def save(self, path: str | Path) -> None:
        raise BackendCapabilityError(
            "save_canvas() is not supported by the native Pyglet renderer yet. "
            "Use the headless backend for deterministic image export."
        )

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


def _angle_steps(count: int):
    return (2 * pi * index / count for index in range(count))
