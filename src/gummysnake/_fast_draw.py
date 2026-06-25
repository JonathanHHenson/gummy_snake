"""Frame-local fast drawing facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, overload

from gummysnake import constants as c
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.geometry import resolve_ellipse, resolve_rect

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class SupportsText(Protocol):
    def __str__(self) -> str: ...


_PRIMITIVE_RECT = 1
_PRIMITIVE_TRIANGLE = 2
_PRIMITIVE_ELLIPSE = 3


def _queue_fill_primitive(context: Any, kind: int, coords: tuple[float, ...]) -> bool:
    queue = getattr(context.renderer, "queue_fill_primitive_fast_path", None)
    if not callable(queue):
        return False
    return bool(queue(kind, coords, context.state.style, context.state.transform.matrix))


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
        fx = float(x)
        fy = float(y)
        fw = float(width)
        if height is not None and context.state.style.rect_mode == c.CORNER:
            fh = float(height)
            if _queue_fill_primitive(context, _PRIMITIVE_RECT, (fx, fy, fw, fh, 0.0, 0.0)):
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
        context = self._context
        if context.state.style.ellipse_mode == c.CENTER:
            fx = float(x)
            fy = float(y)
            d = float(diameter)
            left = fx - d / 2.0
            top = fy - d / 2.0
            if _queue_fill_primitive(context, _PRIMITIVE_ELLIPSE, (left, top, d, d, 0.0, 0.0)):
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
        context = self._context
        values = (float(x1), float(y1), float(x2), float(y2), float(x3), float(y3))
        if _queue_fill_primitive(context, _PRIMITIVE_TRIANGLE, values):
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
            context.renderer.draw_image(
                image,
                dx,
                dy,
                dw,
                dh,
                context.state.style,
                context.state.transform.matrix,
                source=None,
            )
            return
        context._draw_image_fast(image, x, y, *args)

    def text(self, value: SupportsText, x: float, y: float) -> None:
        context = self._context
        context.renderer.text(
            str(value), float(x), float(y), context.state.style, context.state.transform.matrix
        )

    def text_width(self, value: SupportsText) -> float:
        context = self._context
        return context.renderer.text_width(str(value), context.state.style)
