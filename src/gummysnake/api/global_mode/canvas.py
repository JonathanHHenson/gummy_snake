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
    """Create the sketch canvas with the requested size and renderer.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        renderer: The renderer value. Expected type: `c.RendererMode`. Defaults to `c.P2D`.
        pixel_density: The pixel density value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    require_context().create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)


def resize_canvas(width: int, height: int, *, pixel_density: float | None = None) -> None:
    """Resize the active sketch canvas.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        pixel_density: The pixel density value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    require_context().resize_canvas(width, height, pixel_density=pixel_density)


def width() -> int:
    """Return the logical width of the active canvas.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int`.
    """
    return require_context().width


def height() -> int:
    """Return the logical height of the active canvas.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int`.
    """
    return require_context().height


def pixel_density(value: float | None = None) -> float:
    """Get or set the active canvas pixel density.
    
    Args:
        value: The value value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().pixel_density(value)


def display_density() -> float:
    """Return the native display density when available.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().display_density()


def fast() -> FastDrawScope:
    """Return a frame-local fast drawing facade for dense drawing loops.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `FastDrawScope`.
    """
    return require_context().fast()


def enable_performance_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    """Enable or disable sketch performance diagnostics.
    
    Args:
        enabled: The enabled value. Expected type: `bool`. Defaults to `True`.
        reset: The reset value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        None.
    """
    require_context().enable_performance_diagnostics(enabled, reset=reset)


def reset_performance_diagnostics() -> None:
    """Reset collected sketch performance diagnostics.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().reset_performance_diagnostics()


def performance_diagnostics() -> dict[str, Any]:
    """Return collected sketch performance diagnostics.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `dict[str, Any]`.
    """
    return require_context().performance_diagnostics()


def renderer_performance_counters() -> dict[str, Any]:
    """Return renderer performance counters for the active sketch.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `dict[str, Any]`.
    """
    return require_context().renderer_performance_counters()


def reset_renderer_performance_counters() -> None:
    """Reset renderer performance counters for the active sketch.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().reset_renderer_performance_counters()


def enable_frame_pacing_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    """Enable or disable frame-pacing diagnostics.
    
    Args:
        enabled: The enabled value. Expected type: `bool`. Defaults to `True`.
        reset: The reset value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        None.
    """
    require_context().enable_frame_pacing_diagnostics(enabled, reset=reset)


def frame_pacing_diagnostics() -> dict[str, Any]:
    """Return collected frame-pacing diagnostics.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `dict[str, Any]`.
    """
    return require_context().frame_pacing_diagnostics()


def reset_frame_pacing_diagnostics() -> None:
    """Reset collected frame-pacing diagnostics.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().reset_frame_pacing_diagnostics()


@overload
def background(value: ColorValue, /) -> None:
    """Overload accepting color-compatible background arguments.
    
    Args:
        value: The value value. Expected type: `ColorValue`.
    
    Returns:
        None.
    """
    ...


@overload
def background(gray: Number, /) -> None:
    """Overload accepting color-compatible background arguments.
    
    Args:
        gray: The gray value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def background(gray: Number, alpha: Number, /) -> None:
    """Overload accepting color-compatible background arguments.
    
    Args:
        gray: The gray value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def background(v1: Number, v2: Number, v3: Number, /) -> None:
    """Overload accepting color-compatible background arguments.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def background(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
    """Overload accepting color-compatible background arguments.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


def background(*args: Any) -> None:
    """Fill the canvas background with the requested color.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
    cast(Any, require_context()).background(*args)


def clear() -> None:
    """Clear the active canvas.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().clear()


@overload
def color(value: ColorValue, /) -> Color:
    """Overload accepting color-compatible arguments and returning a Color.
    
    Args:
        value: The value value. Expected type: `ColorValue`.
    
    Returns:
        The return value. Type: `Color`.
    """
    ...


@overload
def color(gray: Number, /) -> Color:
    """Overload accepting color-compatible arguments and returning a Color.
    
    Args:
        gray: The gray value. Expected type: `Number`.
    
    Returns:
        The return value. Type: `Color`.
    """
    ...


@overload
def color(gray: Number, alpha: Number, /) -> Color:
    """Overload accepting color-compatible arguments and returning a Color.
    
    Args:
        gray: The gray value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        The return value. Type: `Color`.
    """
    ...


@overload
def color(v1: Number, v2: Number, v3: Number, /) -> Color:
    """Overload accepting color-compatible arguments and returning a Color.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
    
    Returns:
        The return value. Type: `Color`.
    """
    ...


@overload
def color(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> Color:
    """Overload accepting color-compatible arguments and returning a Color.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        The return value. Type: `Color`.
    """
    ...


def color(*args: Any) -> Color:
    """Create and return a Gummy Snake color value.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        The return value. Type: `Color`.
    """
    return cast(Color, cast(Any, require_context()).color(*args))


def color_mode(
    mode: c.ColorMode,
    max1: float | None = None,
    max2: float | None = None,
    max3: float | None = None,
    max_alpha: float | None = None,
) -> None:
    """Set the active color interpretation mode and ranges.
    
    Args:
        mode: The mode value. Expected type: `c.ColorMode`.
        max1: The max1 value. Expected type: `float | None`. Defaults to `None`.
        max2: The max2 value. Expected type: `float | None`. Defaults to `None`.
        max3: The max3 value. Expected type: `float | None`. Defaults to `None`.
        max_alpha: The max alpha value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    require_context().color_mode(mode, max1, max2, max3, max_alpha)


def lerp_color(start: Color, stop: Color, amount: float) -> Color:
    """Interpolate between two colors.
    
    Args:
        start: The start value. Expected type: `Color`.
        stop: The stop value. Expected type: `Color`.
        amount: The amount value. Expected type: `float`.
    
    Returns:
        The return value. Type: `Color`.
    """
    return require_context().lerp_color(start, stop, amount)


@overload
def fill(value: ColorValue, /) -> None:
    """Overload accepting color-compatible fill arguments.
    
    Args:
        value: The value value. Expected type: `ColorValue`.
    
    Returns:
        None.
    """
    ...


@overload
def fill(gray: Number, /) -> None:
    """Overload accepting color-compatible fill arguments.
    
    Args:
        gray: The gray value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def fill(gray: Number, alpha: Number, /) -> None:
    """Overload accepting color-compatible fill arguments.
    
    Args:
        gray: The gray value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def fill(v1: Number, v2: Number, v3: Number, /) -> None:
    """Overload accepting color-compatible fill arguments.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def fill(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
    """Overload accepting color-compatible fill arguments.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


def fill(*args: Any) -> None:
    """Set the fill color for subsequent drawing.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
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
    """Disable fill for subsequent drawing.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().no_fill()


@overload
def stroke(value: ColorValue, /) -> None:
    """Overload accepting color-compatible stroke arguments.
    
    Args:
        value: The value value. Expected type: `ColorValue`.
    
    Returns:
        None.
    """
    ...


@overload
def stroke(gray: Number, /) -> None:
    """Overload accepting color-compatible stroke arguments.
    
    Args:
        gray: The gray value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def stroke(gray: Number, alpha: Number, /) -> None:
    """Overload accepting color-compatible stroke arguments.
    
    Args:
        gray: The gray value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def stroke(v1: Number, v2: Number, v3: Number, /) -> None:
    """Overload accepting color-compatible stroke arguments.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


@overload
def stroke(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
    """Overload accepting color-compatible stroke arguments.
    
    Args:
        v1: The v1 value. Expected type: `Number`.
        v2: The v2 value. Expected type: `Number`.
        v3: The v3 value. Expected type: `Number`.
        alpha: The alpha value. Expected type: `Number`.
    
    Returns:
        None.
    """
    ...


def stroke(*args: Any) -> None:
    """Set the stroke color for subsequent drawing.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
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
    """Disable stroke for subsequent drawing.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().no_stroke()


def stroke_weight(weight: float) -> None:
    """Set the stroke width for subsequent drawing.
    
    Args:
        weight: The weight value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().stroke_weight(weight)


def stroke_cap(cap: c.StrokeCap) -> None:
    """Set the stroke cap mode for subsequent lines.
    
    Args:
        cap: The cap value. Expected type: `c.StrokeCap`.
    
    Returns:
        None.
    """
    require_context().stroke_cap(cap)


def stroke_join(join: c.StrokeJoin) -> None:
    """Set the stroke join mode for subsequent shapes.
    
    Args:
        join: The join value. Expected type: `c.StrokeJoin`.
    
    Returns:
        None.
    """
    require_context().stroke_join(join)


def rect_mode(mode: c.ShapeMode) -> None:
    """Set how rectangle coordinates are interpreted.
    
    Args:
        mode: The mode value. Expected type: `c.ShapeMode`.
    
    Returns:
        None.
    """
    require_context().rect_mode(mode)


def ellipse_mode(mode: c.ShapeMode) -> None:
    """Set how ellipse coordinates are interpreted.
    
    Args:
        mode: The mode value. Expected type: `c.ShapeMode`.
    
    Returns:
        None.
    """
    require_context().ellipse_mode(mode)


def image_mode(mode: c.ShapeMode) -> None:
    """Set how image coordinates are interpreted.
    
    Args:
        mode: The mode value. Expected type: `c.ShapeMode`.
    
    Returns:
        None.
    """
    require_context().image_mode(mode)


def image_sampling(mode: c.ImageSampling | None = None) -> c.ImageSampling:
    """Get or set image sampling mode.
    
    Args:
        mode: The mode value. Expected type: `c.ImageSampling | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `c.ImageSampling`.
    """
    return require_context().image_sampling(mode)


def smooth() -> None:
    """Enable smoothed image and primitive rendering where supported.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().smooth()


def no_smooth() -> None:
    """Disable smoothing where supported.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().no_smooth()
