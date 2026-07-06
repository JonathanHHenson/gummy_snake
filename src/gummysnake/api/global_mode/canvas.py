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
    """Create the sketch canvas with the given size and renderer."""
    require_context().create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)


def resize_canvas(width: int, height: int, *, pixel_density: float | None = None) -> None:
    """Resize the current sketch canvas."""
    require_context().resize_canvas(width, height, pixel_density=pixel_density)


def width() -> int:
    """Return the canvas width in logical pixels."""
    return require_context().width


def height() -> int:
    """Return the canvas height in logical pixels."""
    return require_context().height


def pixel_density(value: float | None = None) -> float:
    """Get or set the ratio between logical and physical pixels."""
    return require_context().pixel_density(value)


def display_density() -> float:
    """Return the current display scale when the backend knows it."""
    return require_context().display_density()


def fast() -> FastDrawScope:
    """Return a faster helper for dense per-frame drawing loops."""
    return require_context().fast()


def enable_performance_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    """Turn high-level performance diagnostics on or off."""
    require_context().enable_performance_diagnostics(enabled, reset=reset)


def reset_performance_diagnostics() -> None:
    """Clear the collected high-level performance diagnostics."""
    require_context().reset_performance_diagnostics()


def performance_diagnostics() -> dict[str, Any]:
    """Return high-level performance diagnostics for the active sketch."""
    return require_context().performance_diagnostics()


def renderer_performance_counters() -> dict[str, Any]:
    """Return renderer counters for the active sketch."""
    return require_context().renderer_performance_counters()


def reset_renderer_performance_counters() -> None:
    """Clear renderer performance counters for the active sketch."""
    require_context().reset_renderer_performance_counters()


def enable_frame_pacing_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    """Turn frame timing diagnostics on or off."""
    require_context().enable_frame_pacing_diagnostics(enabled, reset=reset)


def frame_pacing_diagnostics() -> dict[str, Any]:
    """Return recent frame timing diagnostics."""
    return require_context().frame_pacing_diagnostics()


def reset_frame_pacing_diagnostics() -> None:
    """Clear the collected frame timing diagnostics."""
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
    """Fill the whole canvas with a color."""
    cast(Any, require_context()).background(*args)


def clear() -> None:
    """Clear the canvas to transparent pixels."""
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
    """Build a Color from gray, color values, or a color string."""
    return cast(Color, cast(Any, require_context()).color(*args))


def color_mode(
    mode: c.ColorMode,
    max1: float | None = None,
    max2: float | None = None,
    max3: float | None = None,
    max_alpha: float | None = None,
) -> None:
    """Choose how numeric color values are interpreted."""
    require_context().color_mode(mode, max1, max2, max3, max_alpha)


def lerp_color(start: Color, stop: Color, amount: float) -> Color:
    """Blend between two colors by the given amount."""
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
    """Set the fill color used for closed shapes."""
    context = require_context()
    if (
        context.state.color_mode.mode == c.RGB
        and context.state.color_mode.ranges == (255.0, 255.0, 255.0, 255.0)
        and len(args) in {3, 4}
        and all(isinstance(value, int | float) for value in args)
    ):
        red = int(round(max(0.0, min(255.0, float(args[0])))))
        green = int(round(max(0.0, min(255.0, float(args[1])))))
        blue = int(round(max(0.0, min(255.0, float(args[2])))))
        alpha = int(round(max(0.0, min(255.0, float(args[3]))))) if len(args) == 4 else 255
        context.state.style.fill_color = Color(red, green, blue, alpha)
        context.state.style.mark_changed()
        return
    cast(Any, context).fill(*args)


def no_fill() -> None:
    """Disable filling for closed shapes."""
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
    """Set the outline color used for shapes and lines."""
    context = require_context()
    if (
        context.state.color_mode.mode == c.RGB
        and context.state.color_mode.ranges == (255.0, 255.0, 255.0, 255.0)
        and len(args) in {3, 4}
        and all(isinstance(value, int | float) for value in args)
    ):
        red = int(round(max(0.0, min(255.0, float(args[0])))))
        green = int(round(max(0.0, min(255.0, float(args[1])))))
        blue = int(round(max(0.0, min(255.0, float(args[2])))))
        alpha = int(round(max(0.0, min(255.0, float(args[3]))))) if len(args) == 4 else 255
        context.state.style.stroke_color = Color(red, green, blue, alpha)
        context.state.style.mark_changed()
        return
    cast(Any, context).stroke(*args)


def no_stroke() -> None:
    """Disable outlines for shapes and lines."""
    require_context().no_stroke()


def stroke_weight(weight: float) -> None:
    """Set the thickness of shape outlines and lines."""
    require_context().stroke_weight(weight)


def stroke_cap(cap: c.StrokeCap) -> None:
    """Set the style used at the ends of lines."""
    require_context().stroke_cap(cap)


def stroke_join(join: c.StrokeJoin) -> None:
    """Set how corners are drawn where stroke segments meet."""
    require_context().stroke_join(join)


def rect_mode(mode: c.ShapeMode) -> None:
    """Set how rectangle coordinates are interpreted."""
    require_context().rect_mode(mode)


def ellipse_mode(mode: c.ShapeMode) -> None:
    """Set how ellipse coordinates are interpreted."""
    require_context().ellipse_mode(mode)


def image_mode(mode: c.ShapeMode) -> None:
    """Set how image coordinates are interpreted."""
    require_context().image_mode(mode)


def image_sampling(mode: c.ImageSampling | None = None) -> c.ImageSampling:
    """Get or set how images are sampled when scaled."""
    return require_context().image_sampling(mode)


def smooth() -> None:
    """Use smoothed drawing for supported shapes and images."""
    require_context().smooth()


def no_smooth() -> None:
    """Turn off smoothing for supported shapes and images."""
    require_context().no_smooth()
