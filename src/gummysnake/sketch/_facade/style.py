"""Color and style forwards for object sketches."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.core.color import Color
from gummysnake.sketch._facade.base import ColorValue, Number, SketchFacadeBaseMixin


class SketchFacadeStyleMixin(SketchFacadeBaseMixin):
    @overload
    def color(self, value: ColorValue, /) -> Color: ...

    @overload
    def color(self, gray: Number, /) -> Color: ...

    @overload
    def color(self, gray: Number, alpha: Number, /) -> Color: ...

    @overload
    def color(self, v1: Number, v2: Number, v3: Number, /) -> Color: ...

    @overload
    def color(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> Color: ...

    def color(self, *args: Any) -> Color:
        return cast(Color, cast(Any, self._ctx).color(*args))

    def color_mode(
        self,
        mode: c.ColorMode,
        max1: float | None = None,
        max2: float | None = None,
        max3: float | None = None,
        max_alpha: float | None = None,
    ) -> None:
        self._ctx.color_mode(mode, max1, max2, max3, max_alpha)

    def lerp_color(self, start: Color, stop: Color, amount: float) -> Color:
        return self._ctx.lerp_color(start, stop, amount)

    @overload
    def background(self, value: ColorValue, /) -> None: ...

    @overload
    def background(self, gray: Number, /) -> None: ...

    @overload
    def background(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def background(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def background(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def background(self, *args: Any) -> None:
        cast(Any, self._ctx).background(*args)

    def clear(self) -> None:
        self._ctx.clear()

    @overload
    def fill(self, value: ColorValue, /) -> None: ...

    @overload
    def fill(self, gray: Number, /) -> None: ...

    @overload
    def fill(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def fill(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def fill(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def fill(self, *args: Any) -> None:
        cast(Any, self._ctx).fill(*args)

    def no_fill(self) -> None:
        self._ctx.no_fill()

    @overload
    def stroke(self, value: ColorValue, /) -> None: ...

    @overload
    def stroke(self, gray: Number, /) -> None: ...

    @overload
    def stroke(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def stroke(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def stroke(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def stroke(self, *args: Any) -> None:
        cast(Any, self._ctx).stroke(*args)

    def no_stroke(self) -> None:
        self._ctx.no_stroke()

    def stroke_weight(self, weight: float) -> None:
        self._ctx.stroke_weight(weight)

    def stroke_cap(self, cap: c.StrokeCap) -> None:
        self._ctx.stroke_cap(cap)

    def stroke_join(self, join: c.StrokeJoin) -> None:
        self._ctx.stroke_join(join)

    def rect_mode(self, mode: c.ShapeMode) -> None:
        self._ctx.rect_mode(mode)

    def ellipse_mode(self, mode: c.ShapeMode) -> None:
        self._ctx.ellipse_mode(mode)

    def image_mode(self, mode: c.ShapeMode) -> None:
        self._ctx.image_mode(mode)

    def image_sampling(self, mode: c.ImageSampling | None = None) -> c.ImageSampling:
        return self._ctx.image_sampling(mode)

    def smooth(self) -> None:
        self._ctx.smooth()

    def no_smooth(self) -> None:
        self._ctx.no_smooth()

    @overload
    def tint(self, value: ColorValue, /) -> None: ...

    @overload
    def tint(self, gray: Number, /) -> None: ...

    @overload
    def tint(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def tint(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def tint(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def tint(self, *args: Any) -> None:
        cast(Any, self._ctx).tint(*args)

    def no_tint(self) -> None:
        self._ctx.no_tint()
