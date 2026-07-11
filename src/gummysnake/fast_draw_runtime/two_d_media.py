"""Direct 2D primitive, image, and text methods for :class:`FastDrawScope`."""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from gummysnake import constants as c
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.geometry import resolve_ellipse, resolve_rect
from gummysnake.drawing.primitive_fast_path import (
    PRIMITIVE_ELLIPSE,
    PRIMITIVE_RECT,
    PRIMITIVE_TRIANGLE,
    queue_fill_primitive,
)
from gummysnake.fast_draw_runtime.image_batches import queue_fast_image
from gummysnake.fast_draw_runtime.scope_helpers import SupportsText

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class FastTwoDMediaMixin:
    """Forward normalized 2D drawing directly to the cached frame context."""

    __slots__ = ()

    _context: SketchContext

    def point(self, x: float, y: float) -> None:
        """Draw a point using the current fast-scope style and 2D transform."""
        context = self._context
        context.renderer.point(
            float(x),
            float(y),
            context.state.style,
            context.state.transform.matrix,
        )

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Draw a line using the current fast-scope style and 2D transform."""
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
        """Draw a rectangle with the current rect mode, style, and 2D transform."""
        context = self._context
        fx = float(x)
        fy = float(y)
        fw = float(width)
        if height is not None and context.state.style.rect_mode == c.CORNER:
            fh = float(height)
            if queue_fill_primitive(context, PRIMITIVE_RECT, (fx, fy, fw, fh, 0.0, 0.0)):
                return
            context.renderer.rect(
                fx,
                fy,
                fw,
                fh,
                context.state.style,
                context.state.transform.matrix,
            )
            return
        h = width if height is None else height
        rx, ry, rw, rh = resolve_rect(
            context.state.style.rect_mode,
            fx,
            fy,
            fw,
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
        """Draw a square using the current rectangle mode and drawing state."""
        self.rect(x, y, size, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        """Draw an ellipse with the current ellipse mode, style, and 2D transform."""
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
        """Draw a circle with the current ellipse mode, style, and 2D transform."""
        context = self._context
        if context.state.style.ellipse_mode == c.CENTER:
            fx = float(x)
            fy = float(y)
            d = float(diameter)
            left = fx - d / 2.0
            top = fy - d / 2.0
            if queue_fill_primitive(context, PRIMITIVE_ELLIPSE, (left, top, d, d, 0.0, 0.0)):
                return
            context.renderer.ellipse(
                left,
                top,
                d,
                d,
                context.state.style,
                context.state.transform.matrix,
            )
            return
        self.ellipse(x, y, diameter, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        """Draw a triangle using the current style and 2D transform."""
        context = self._context
        values = (float(x1), float(y1), float(x2), float(y2), float(x3), float(y3))
        if queue_fill_primitive(context, PRIMITIVE_TRIANGLE, values):
            return
        context.renderer.triangle(
            values[0],
            values[1],
            values[2],
            values[3],
            values[4],
            values[5],
            context.state.style,
            context.state.transform.matrix,
        )

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
        """Draw an image, retaining the ordered Rust image-batch path when applicable."""
        context = self._context
        if len(args) == 2:
            dx = float(x)
            dy = float(y)
            dw = float(args[0])
            dh = float(args[1])
            if context.state.style.image_mode == c.CENTER:
                dx -= dw / 2.0
                dy -= dh / 2.0
            elif context.state.style.image_mode != c.CORNER:
                context._draw_image_fast(image, x, y, *args)
                return
            context._record_image_diagnostics(image)
            queue_fast_image(self, image, dx, dy, dw, dh)
            return
        context._draw_image_fast(image, x, y, *args)

    def text(self, value: SupportsText, x: float, y: float) -> None:
        """Draw text using the current fast-scope style and 2D transform."""
        context = self._context
        context.renderer.text(
            str(value),
            float(x),
            float(y),
            context.state.style,
            context.state.transform.matrix,
        )

    def text_width(self, value: SupportsText) -> float:
        """Return the width of text measured with the current fast-scope style."""
        context = self._context
        return context.renderer.text_width(str(value), context.state.style)
