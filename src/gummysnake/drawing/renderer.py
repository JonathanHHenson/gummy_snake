"""Renderer protocol shared by all drawing backends."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.pixels import PixelBuffer

if TYPE_CHECKING:
    from gummysnake.assets.image import CanvasImage


class Renderer(Protocol):
    width: int
    height: int
    physical_width: int
    physical_height: int
    pixel_density: float

    def resize(self, width: int, height: int, pixel_density: float = 1.0) -> None: ...

    def begin_frame(self) -> None: ...

    def end_frame(self) -> None: ...

    def background(self, color: Color) -> None: ...

    def clear(self) -> None: ...

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None: ...

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None: ...

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None: ...

    def complex_polygon(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None: ...

    def begin_clip(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        transform: Matrix2D,
    ) -> None: ...

    def end_clip(self) -> None: ...

    def clip_depth(self) -> int: ...

    def restore_clip_depth(self, depth: int) -> None: ...

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None: ...

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
    ) -> None: ...

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
    ) -> None: ...

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None: ...

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
    ) -> None: ...

    def draw_image(
        self,
        image: Image | CanvasImage,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: StyleState,
        transform: Matrix2D,
        *,
        source: tuple[int, int, int, int] | None = None,
    ) -> None: ...

    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None: ...

    def text_width(self, value: str, style: StyleState) -> float: ...

    def text_ascent(self, style: StyleState) -> float: ...

    def text_descent(self, style: StyleState) -> float: ...

    def load_pixels(self) -> PixelBuffer: ...

    def load_pixel_bytes(self) -> bytes: ...

    def load_pixel_region(self, x: int, y: int, width: int, height: int) -> bytes: ...

    def update_pixels(self, pixels: Sequence[int] | Buffer) -> None: ...

    def update_pixel_region(
        self,
        pixels: Sequence[int] | Buffer,
        width: int,
        height: int,
        x: int,
        y: int,
        *,
        alpha_composite: bool = True,
    ) -> None: ...

    def filter_pixels(self, mode: c.ImageFilter, value: float | None = None) -> None: ...

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None: ...

    def save(self, path: str | Path) -> None: ...
