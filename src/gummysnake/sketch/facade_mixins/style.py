"""Color and style forwards for object sketches."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.core.color import Color
from gummysnake.sketch.facade_mixins.base import ColorValue, Number, SketchFacadeBaseMixin


class SketchFacadeStyleMixin(SketchFacadeBaseMixin):
    """Object-mode color and drawing-style forwards."""

    @overload
    def color(self, value: ColorValue, /) -> Color:
        """Overload accepting color-compatible arguments and returning a Color.
        
        Args:
            value: The value value. Expected type: `ColorValue`.
        
        Returns:
            The return value. Type: `Color`.
        """
        ...

    @overload
    def color(self, gray: Number, /) -> Color:
        """Overload accepting color-compatible arguments and returning a Color.
        
        Args:
            gray: The gray value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Color`.
        """
        ...

    @overload
    def color(self, gray: Number, alpha: Number, /) -> Color:
        """Overload accepting color-compatible arguments and returning a Color.
        
        Args:
            gray: The gray value. Expected type: `Number`.
            alpha: The alpha value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Color`.
        """
        ...

    @overload
    def color(self, v1: Number, v2: Number, v3: Number, /) -> Color:
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
    def color(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> Color:
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

    def color(self, *args: Any) -> Color:
        """Create and return a Gummy Snake color value.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return cast(Color, cast(Any, self._ctx).color(*args))

    def color_mode(
        self,
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
        self._ctx.color_mode(mode, max1, max2, max3, max_alpha)

    def lerp_color(self, start: Color, stop: Color, amount: float) -> Color:
        """Interpolate between two colors.
        
        Args:
            start: The start value. Expected type: `Color`.
            stop: The stop value. Expected type: `Color`.
            amount: The amount value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return self._ctx.lerp_color(start, stop, amount)

    @overload
    def background(self, value: ColorValue, /) -> None:
        """Overload accepting color-compatible background arguments.
        
        Args:
            value: The value value. Expected type: `ColorValue`.
        
        Returns:
            None.
        """
        ...

    @overload
    def background(self, gray: Number, /) -> None:
        """Overload accepting color-compatible background arguments.
        
        Args:
            gray: The gray value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def background(self, gray: Number, alpha: Number, /) -> None:
        """Overload accepting color-compatible background arguments.
        
        Args:
            gray: The gray value. Expected type: `Number`.
            alpha: The alpha value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def background(self, v1: Number, v2: Number, v3: Number, /) -> None:
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
    def background(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
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

    def background(self, *args: Any) -> None:
        """Fill the canvas background with the requested color.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        cast(Any, self._ctx).background(*args)

    def clear(self) -> None:
        """Clear the active canvas.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.clear()

    @overload
    def fill(self, value: ColorValue, /) -> None:
        """Overload accepting color-compatible fill arguments.
        
        Args:
            value: The value value. Expected type: `ColorValue`.
        
        Returns:
            None.
        """
        ...

    @overload
    def fill(self, gray: Number, /) -> None:
        """Overload accepting color-compatible fill arguments.
        
        Args:
            gray: The gray value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def fill(self, gray: Number, alpha: Number, /) -> None:
        """Overload accepting color-compatible fill arguments.
        
        Args:
            gray: The gray value. Expected type: `Number`.
            alpha: The alpha value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def fill(self, v1: Number, v2: Number, v3: Number, /) -> None:
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
    def fill(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
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

    def fill(self, *args: Any) -> None:
        """Set the fill color for subsequent drawing.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        cast(Any, self._ctx).fill(*args)

    def no_fill(self) -> None:
        """Disable fill for subsequent drawing.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.no_fill()

    @overload
    def stroke(self, value: ColorValue, /) -> None:
        """Overload accepting color-compatible stroke arguments.
        
        Args:
            value: The value value. Expected type: `ColorValue`.
        
        Returns:
            None.
        """
        ...

    @overload
    def stroke(self, gray: Number, /) -> None:
        """Overload accepting color-compatible stroke arguments.
        
        Args:
            gray: The gray value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def stroke(self, gray: Number, alpha: Number, /) -> None:
        """Overload accepting color-compatible stroke arguments.
        
        Args:
            gray: The gray value. Expected type: `Number`.
            alpha: The alpha value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def stroke(self, v1: Number, v2: Number, v3: Number, /) -> None:
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
    def stroke(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
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

    def stroke(self, *args: Any) -> None:
        """Set the stroke color for subsequent drawing.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        cast(Any, self._ctx).stroke(*args)

    def no_stroke(self) -> None:
        """Disable stroke for subsequent drawing.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.no_stroke()

    def stroke_weight(self, weight: float) -> None:
        """Set the stroke width for subsequent drawing.
        
        Args:
            weight: The weight value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.stroke_weight(weight)

    def stroke_cap(self, cap: c.StrokeCap) -> None:
        """Set the stroke cap mode for subsequent lines.
        
        Args:
            cap: The cap value. Expected type: `c.StrokeCap`.
        
        Returns:
            None.
        """
        self._ctx.stroke_cap(cap)

    def stroke_join(self, join: c.StrokeJoin) -> None:
        """Set the stroke join mode for subsequent shapes.
        
        Args:
            join: The join value. Expected type: `c.StrokeJoin`.
        
        Returns:
            None.
        """
        self._ctx.stroke_join(join)

    def rect_mode(self, mode: c.ShapeMode) -> None:
        """Set how rectangle coordinates are interpreted.
        
        Args:
            mode: The mode value. Expected type: `c.ShapeMode`.
        
        Returns:
            None.
        """
        self._ctx.rect_mode(mode)

    def ellipse_mode(self, mode: c.ShapeMode) -> None:
        """Set how ellipse coordinates are interpreted.
        
        Args:
            mode: The mode value. Expected type: `c.ShapeMode`.
        
        Returns:
            None.
        """
        self._ctx.ellipse_mode(mode)

    def image_mode(self, mode: c.ShapeMode) -> None:
        """Set how image coordinates are interpreted.
        
        Args:
            mode: The mode value. Expected type: `c.ShapeMode`.
        
        Returns:
            None.
        """
        self._ctx.image_mode(mode)

    def image_sampling(self, mode: c.ImageSampling | None = None) -> c.ImageSampling:
        """Get or set image sampling mode.
        
        Args:
            mode: The mode value. Expected type: `c.ImageSampling | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `c.ImageSampling`.
        """
        return self._ctx.image_sampling(mode)

    def smooth(self) -> None:
        """Enable smoothed image and primitive rendering where supported.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.smooth()

    def no_smooth(self) -> None:
        """Disable smoothing where supported.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.no_smooth()

    @overload
    def tint(self, value: ColorValue, /) -> None:
        """Overload signature for tint().
        
        Args:
            value: The value value. Expected type: `ColorValue`.
        
        Returns:
            None.
        """
        ...

    @overload
    def tint(self, gray: Number, /) -> None:
        """Overload signature for tint().
        
        Args:
            gray: The gray value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def tint(self, gray: Number, alpha: Number, /) -> None:
        """Overload signature for tint().
        
        Args:
            gray: The gray value. Expected type: `Number`.
            alpha: The alpha value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def tint(self, v1: Number, v2: Number, v3: Number, /) -> None:
        """Overload signature for tint().
        
        Args:
            v1: The v1 value. Expected type: `Number`.
            v2: The v2 value. Expected type: `Number`.
            v3: The v3 value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    @overload
    def tint(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
        """Overload signature for tint().
        
        Args:
            v1: The v1 value. Expected type: `Number`.
            v2: The v2 value. Expected type: `Number`.
            v3: The v3 value. Expected type: `Number`.
            alpha: The alpha value. Expected type: `Number`.
        
        Returns:
            None.
        """
        ...

    def tint(self, *args: Any) -> None:
        """Tint for this SketchFacadeStyleMixin.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        cast(Any, self._ctx).tint(*args)

    def no_tint(self) -> None:
        """Disable tint.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.no_tint()
