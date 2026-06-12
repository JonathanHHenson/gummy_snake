"""Pillow-backed 2D renderer."""

from __future__ import annotations

from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw

from p5_py import constants as c
from p5_py.core.color import Color
from p5_py.core.state import StyleState
from p5_py.core.transform import Matrix2D
from p5_py.exceptions import ArgumentValidationError


def _rgba(color: Color | None) -> tuple[int, int, int, int] | None:
    return None if color is None else color.to_tuple()


def _stroke_width(style: StyleState, pixel_density: float) -> int:
    return max(1, int(round(style.stroke_weight * pixel_density)))


class PillowRenderer:
    """Deterministic raster renderer used by headless and Pyglet backends."""

    width: int
    height: int
    physical_width: int
    physical_height: int

    def __init__(self, width: int = 100, height: int = 100, pixel_density: float = 1.0) -> None:
        self.pixel_density = pixel_density
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
        self.image = Image.new("RGBA", (self.physical_width, self.physical_height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def begin_frame(self) -> None:
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def end_frame(self) -> None:
        pass

    def background(self, color: Color) -> None:
        self.draw.rectangle(
            (0, 0, self.physical_width, self.physical_height), fill=color.to_tuple()
        )

    def clear(self) -> None:
        self.image = Image.new("RGBA", (self.physical_width, self.physical_height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        color = style.stroke_color or style.fill_color
        if color is None:
            return
        tx, ty = self._physical_transform(transform).transform_point(x, y)
        radius = max(0.5, style.stroke_weight * self.pixel_density / 2)
        self.draw.ellipse(
            (tx - radius, ty - radius, tx + radius, ty + radius),
            fill=color.to_tuple(),
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
        if style.stroke_color is None:
            return
        physical_transform = self._physical_transform(transform)
        p1 = physical_transform.transform_point(x1, y1)
        p2 = physical_transform.transform_point(x2, y2)
        self.draw.line(
            (*p1, *p2),
            fill=style.stroke_color.to_tuple(),
            width=_stroke_width(style, self.pixel_density),
        )

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
        physical_transform = self._physical_transform(transform)
        transformed = [physical_transform.transform_point(x, y) for x, y in points]
        if len(transformed) == 1:
            self.point(points[0][0], points[0][1], style, transform)
            return
        if style.fill_color is not None and close and len(transformed) >= 3:
            self.draw.polygon(transformed, fill=style.fill_color.to_tuple())
        if style.stroke_color is not None:
            stroke_points = [*transformed, transformed[0]] if close else transformed
            self._draw_joined_polyline(stroke_points, style)

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
                physical_transform = self._physical_transform(transform)
                transformed = [physical_transform.transform_point(px, py) for px, py in arc_points]
                self._draw_joined_polyline(transformed, style)

    def _draw_joined_polyline(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
    ) -> None:
        if len(points) < 2 or style.stroke_color is None:
            return
        self.draw.line(
            points,
            fill=style.stroke_color.to_tuple(),
            width=_stroke_width(style, self.pixel_density),
            joint="curve",
        )

    def load_pixels(self) -> list[int]:
        return list(self.image.tobytes())

    def update_pixels(self, pixels: list[int]) -> None:
        expected = self.physical_width * self.physical_height * 4
        if len(pixels) != expected:
            raise ArgumentValidationError(
                f"Pixel buffer length must be {expected}, got {len(pixels)}."
            )
        self.image = Image.frombytes(
            "RGBA",
            (self.physical_width, self.physical_height),
            bytes(pixels),
        )
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def save(self, path: str | Path) -> None:
        self.image.save(path)

    def get_image(self) -> Image.Image:
        return self.image

    def _physical_transform(self, transform: Matrix2D) -> Matrix2D:
        return Matrix2D.scaling(self.pixel_density).multiply(transform)


def _angle_steps(count: int):
    return (2 * pi * index / count for index in range(count))
