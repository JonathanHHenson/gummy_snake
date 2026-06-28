"""Renderer protocol shared by all drawing backends."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.core.pixels import PixelBuffer
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D

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
    ) -> None:
        """Line.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        """Polygon.
        
        Args:
            points: The points value. Expected type: `list[tuple[float, float]]`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
            close: The close value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        ...

    def complex_polygon(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        """Complex polygon.
        
        Args:
            outer: The outer value. Expected type: `list[tuple[float, float]]`.
            contours: The contours value. Expected type: `list[list[tuple[float, float]]]`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
            close: The close value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        ...

    def begin_clip(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        transform: Matrix2D,
    ) -> None:
        """Begin clip.
        
        Args:
            outer: The outer value. Expected type: `list[tuple[float, float]]`.
            contours: The contours value. Expected type: `list[list[tuple[float, float]]]`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

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
    ) -> None:
        """Rect.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

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
        """Triangle.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

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
        """Quad.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
            x4: The x4 value. Expected type: `float`.
            y4: The y4 value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        """Ellipse.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

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
        """Arc.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            start: The start value. Expected type: `float`.
            stop: The stop value. Expected type: `float`.
            mode: The mode value. Expected type: `c.ArcMode`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

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
    ) -> None:
        """Draw image.
        
        Args:
            image: The image value. Expected type: `Image | CanvasImage`.
            dx: The dx value. Expected type: `float`.
            dy: The dy value. Expected type: `float`.
            dw: The dw value. Expected type: `float`.
            dh: The dh value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
            source: The source value. Expected type: `tuple[int, int, int, int] | None`. Defaults to
                `None`.
        
        Returns:
            None.
        """
        ...

    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        """Text.
        
        Args:
            value: The value value. Expected type: `str`.
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        ...

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
    ) -> None:
        """Update pixel region.
        
        Args:
            pixels: The pixels value. Expected type: `Sequence[int] | Buffer`.
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            x: The x value. Expected type: `int`.
            y: The y value. Expected type: `int`.
            alpha_composite: The alpha composite value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        ...

    def filter_pixels(self, mode: c.ImageFilter, value: float | None = None) -> None: ...

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None:
        """Blend region.
        
        Args:
            source_image: The source image value. Expected type: `object | None`.
            source: The source value. Expected type: `tuple[int, int, int, int]`.
            destination: The destination value. Expected type: `tuple[int, int, int, int]`.
            mode: The mode value. Expected type: `c.BlendMode`.
        
        Returns:
            None.
        """
        ...

    def save(self, path: str | Path) -> None: ...
