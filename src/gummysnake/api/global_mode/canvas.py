"""Global-mode canvas, style, and diagnostics wrappers."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake._fast_draw import FastDrawScope
from gummysnake.api.current import require_context
from gummysnake.core.color import Color

Number = int | float
ColorValue = Color | str


def create_canvas(
    width: int, height: int, renderer: c.RendererMode = c.P2D, *, pixel_density: float | None = None
) -> None:
    require_context().create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)


def resize_canvas(width: int, height: int, *, pixel_density: float | None = None) -> None:
    require_context().resize_canvas(width, height, pixel_density=pixel_density)


def width() -> int:
    return require_context().width


def height() -> int:
    return require_context().height


def pixel_density(value: float | None = None) -> float:
    return require_context().pixel_density(value)


def display_density() -> float:
    return require_context().display_density()


def fast() -> FastDrawScope:
    return require_context().fast()


def enable_performance_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    require_context().enable_performance_diagnostics(enabled, reset=reset)


def reset_performance_diagnostics() -> None:
    require_context().reset_performance_diagnostics()


def performance_diagnostics() -> dict[str, Any]:
    return require_context().performance_diagnostics()


def renderer_performance_counters() -> dict[str, Any]:
    return require_context().renderer_performance_counters()


def reset_renderer_performance_counters() -> None:
    require_context().reset_renderer_performance_counters()


def enable_frame_pacing_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    require_context().enable_frame_pacing_diagnostics(enabled, reset=reset)


def frame_pacing_diagnostics() -> dict[str, Any]:
    return require_context().frame_pacing_diagnostics()


def reset_frame_pacing_diagnostics() -> None:
    require_context().reset_frame_pacing_diagnostics()


@overload
def background(value: ColorValue, /) -> None: ...


@overload
def background(gray: Number, /) -> None: ...


@overload
def background(gray: Number, alpha: Number, /) -> None: ...


@overload
def background(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def background(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def background(*args: Any) -> None:
    cast(Any, require_context()).background(*args)


def clear() -> None:
    require_context().clear()


@overload
def color(value: ColorValue, /) -> Color: ...


@overload
def color(gray: Number, /) -> Color: ...


@overload
def color(gray: Number, alpha: Number, /) -> Color: ...


@overload
def color(v1: Number, v2: Number, v3: Number, /) -> Color: ...


@overload
def color(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> Color: ...


def color(*args: Any) -> Color:
    return cast(Color, cast(Any, require_context()).color(*args))


def color_mode(
    mode: c.ColorMode,
    max1: float | None = None,
    max2: float | None = None,
    max3: float | None = None,
    max_alpha: float | None = None,
) -> None:
    require_context().color_mode(mode, max1, max2, max3, max_alpha)


def lerp_color(start: Color, stop: Color, amount: float) -> Color:
    return require_context().lerp_color(start, stop, amount)


@overload
def fill(value: ColorValue, /) -> None: ...


@overload
def fill(gray: Number, /) -> None: ...


@overload
def fill(gray: Number, alpha: Number, /) -> None: ...


@overload
def fill(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def fill(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def fill(*args: Any) -> None:
    cast(Any, require_context()).fill(*args)


def no_fill() -> None:
    require_context().no_fill()


@overload
def stroke(value: ColorValue, /) -> None: ...


@overload
def stroke(gray: Number, /) -> None: ...


@overload
def stroke(gray: Number, alpha: Number, /) -> None: ...


@overload
def stroke(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def stroke(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def stroke(*args: Any) -> None:
    cast(Any, require_context()).stroke(*args)


def no_stroke() -> None:
    require_context().no_stroke()


def stroke_weight(weight: float) -> None:
    require_context().stroke_weight(weight)


def stroke_cap(cap: c.StrokeCap) -> None:
    require_context().stroke_cap(cap)


def stroke_join(join: c.StrokeJoin) -> None:
    require_context().stroke_join(join)


def rect_mode(mode: c.ShapeMode) -> None:
    require_context().rect_mode(mode)


def ellipse_mode(mode: c.ShapeMode) -> None:
    require_context().ellipse_mode(mode)


def image_mode(mode: c.ShapeMode) -> None:
    require_context().image_mode(mode)


def image_sampling(mode: c.ImageSampling | None = None) -> c.ImageSampling:
    return require_context().image_sampling(mode)


def smooth() -> None:
    require_context().smooth()


def no_smooth() -> None:
    require_context().no_smooth()
