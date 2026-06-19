"""Renderer protocol shared by all drawing backends."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from p5.assets.image import Image
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D

if TYPE_CHECKING:
    from p5.assets.image import P5Image


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
        mode: str,
        style: StyleState,
        transform: Matrix2D,
    ) -> None: ...

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

    def load_pixels(self) -> list[int]: ...

    def update_pixels(self, pixels: Sequence[int]) -> None: ...

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: str,
    ) -> None: ...

    def save(self, path: str | Path) -> None: ...
