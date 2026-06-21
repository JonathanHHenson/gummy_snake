"""Frame-local fast drawing facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, overload

from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.geometry import resolve_ellipse, resolve_rect

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class SupportsText(Protocol):
    def __str__(self) -> str: ...


class FastDrawScope:
    """Frame-local facade for dense drawing loops."""

    __slots__ = ("_context",)

    def __init__(self, context: SketchContext) -> None:
        self._context = context

    @property
    def width(self) -> int:
        return self._context.width

    @property
    def height(self) -> int:
        return self._context.height

    def point(self, x: float, y: float) -> None:
        context = self._context
        context.renderer.point(
            float(x),
            float(y),
            context.state.style,
            context.state.transform.matrix,
        )

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        context = self._context
        context.renderer.line(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            context.state.style,
            context.state.transform.matrix,
        )

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        context = self._context
        h = width if height is None else height
        rx, ry, rw, rh = resolve_rect(
            context.state.style.rect_mode,
            float(x),
            float(y),
            float(width),
            float(h),
        )
        context.renderer.rect(
            rx,
            ry,
            rw,
            rh,
            context.state.style,
            context.state.transform.matrix,
        )

    def square(self, x: float, y: float, size: float) -> None:
        self.rect(x, y, size, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        context = self._context
        h = width if height is None else height
        ex, ey, ew, eh = resolve_ellipse(
            context.state.style.ellipse_mode,
            float(x),
            float(y),
            float(width),
            float(h),
        )
        context.renderer.ellipse(
            ex,
            ey,
            ew,
            eh,
            context.state.style,
            context.state.transform.matrix,
        )

    def circle(self, x: float, y: float, diameter: float) -> None:
        self.ellipse(x, y, diameter, diameter)

    @overload
    def image(self, image: Image | CanvasImage, x: float, y: float, /) -> None: ...

    @overload
    def image(
        self, image: Image | CanvasImage, x: float, y: float, width: float, height: float, /
    ) -> None: ...

    @overload
    def image(
        self,
        image: Image | CanvasImage,
        x: float,
        y: float,
        width: float,
        height: float,
        sx: float,
        sy: float,
        sw: float,
        sh: float,
        /,
    ) -> None: ...

    def image(self, image: Image | CanvasImage, x: float, y: float, *args: float) -> None:
        self._context._draw_image_fast(image, x, y, *args)

    def text(self, value: SupportsText, x: float, y: float) -> None:
        context = self._context
        context.renderer.text(
            str(value), float(x), float(y), context.state.style, context.state.transform.matrix
        )

    def text_width(self, value: SupportsText) -> float:
        context = self._context
        return context.renderer.text_width(str(value), context.state.style)
