"""Color and style methods for SketchContext."""

from __future__ import annotations

from typing import Any, overload

from gummysnake import constants as c
from gummysnake.core.color import Color, lerp_color
from gummysnake.exceptions import ArgumentValidationError

Number = int | float
ColorValue = Color | str


class StyleContextMixin:
    state: Any
    renderer: Any

    def _mark_style_changed(self) -> None:
        self.state.style.mark_changed()
        sync_style = getattr(self.renderer, "set_current_style", None)
        if callable(sync_style) and getattr(self.renderer, "renderer_mode", None) != c.P2D:
            sync_style(self.state.style)

    def _color_from_args(self, args: tuple[Any, ...]) -> Color:
        return Color.from_args(
            args, mode=self.state.color_mode.mode, ranges=self.state.color_mode.ranges
        )

    def _rgb255_color_from_args(self, args: tuple[Any, ...]) -> Color | None:
        if (
            self.state.color_mode.mode != c.RGB
            or self.state.color_mode.ranges != (255.0, 255.0, 255.0, 255.0)
            or len(args) not in {3, 4}
            or not all(isinstance(value, int | float) for value in args)
        ):
            return None
        red = round(max(0.0, min(255.0, float(args[0]))))
        green = round(max(0.0, min(255.0, float(args[1]))))
        blue = round(max(0.0, min(255.0, float(args[2]))))
        alpha = round(max(0.0, min(255.0, float(args[3])))) if len(args) == 4 else 255
        return Color(int(red), int(green), int(blue), int(alpha))

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
        """Color.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return self._color_from_args(args)

    def color_mode(
        self,
        mode: c.ColorMode,
        max1: float | None = None,
        max2: float | None = None,
        max3: float | None = None,
        max_alpha: float | None = None,
    ) -> None:
        """Color mode.
        
        Args:
            mode: The mode value. Expected type: `c.ColorMode`.
            max1: The max1 value. Expected type: `float | None`. Defaults to `None`.
            max2: The max2 value. Expected type: `float | None`. Defaults to `None`.
            max3: The max3 value. Expected type: `float | None`. Defaults to `None`.
            max_alpha: The max alpha value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        if mode not in {c.RGB, c.HSB, c.HSL}:
            raise ArgumentValidationError(f"Unsupported color mode {mode!r}.")
        if max1 is None:
            ranges = (255.0, 255.0, 255.0, 255.0) if mode == c.RGB else (360.0, 100.0, 100.0, 1.0)
        else:
            ranges = (
                float(max1),
                float(max1 if max2 is None else max2),
                float(max1 if max3 is None else max3),
                float(max1 if max_alpha is None else max_alpha),
            )
        self.state.color_mode.mode = mode
        self.state.color_mode.ranges = ranges

    def lerp_color(self, start: Color, stop: Color, amount: float) -> Color:
        """Lerp color.
        
        Args:
            start: The start value. Expected type: `Color`.
            stop: The stop value. Expected type: `Color`.
            amount: The amount value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return lerp_color(start, stop, amount)

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
        """Background.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        self.renderer.background(self._color_from_args(args))

    def clear(self) -> None:
        """Clear.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.renderer.clear()

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
        """Fill.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        self.state.style.fill_color = self._rgb255_color_from_args(args) or self._color_from_args(
            args
        )
        self._mark_style_changed()

    def no_fill(self) -> None:
        """No fill.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.state.style.fill_color = None
        self._mark_style_changed()

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
        """Stroke.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        self.state.style.stroke_color = self._rgb255_color_from_args(args) or self._color_from_args(
            args
        )
        self._mark_style_changed()

    def no_stroke(self) -> None:
        """No stroke.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.state.style.stroke_color = None
        self._mark_style_changed()

    def stroke_weight(self, weight: float) -> None:
        """Stroke weight.
        
        Args:
            weight: The weight value. Expected type: `float`.
        
        Returns:
            None.
        """
        if weight < 0:
            raise ArgumentValidationError("stroke_weight() cannot be negative.")
        self.state.style.stroke_weight = float(weight)
        self._mark_style_changed()

    def stroke_cap(self, cap: c.StrokeCap) -> None:
        """Stroke cap.
        
        Args:
            cap: The cap value. Expected type: `c.StrokeCap`.
        
        Returns:
            None.
        """
        if cap not in {c.ROUND, c.SQUARE, c.PROJECT}:
            raise ArgumentValidationError(f"Unsupported stroke cap {cap!r}.")
        self.state.style.stroke_cap = cap
        self._mark_style_changed()

    def stroke_join(self, join: c.StrokeJoin) -> None:
        """Stroke join.
        
        Args:
            join: The join value. Expected type: `c.StrokeJoin`.
        
        Returns:
            None.
        """
        if join not in {c.MITER, c.BEVEL, c.ROUND}:
            raise ArgumentValidationError(f"Unsupported stroke join {join!r}.")
        self.state.style.stroke_join = join
        self._mark_style_changed()

    def rect_mode(self, mode: c.ShapeMode) -> None:
        """Rect mode.
        
        Args:
            mode: The mode value. Expected type: `c.ShapeMode`.
        
        Returns:
            None.
        """
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported rect mode {mode!r}.")
        self.state.style.rect_mode = mode
        self._mark_style_changed()

    def ellipse_mode(self, mode: c.ShapeMode) -> None:
        """Ellipse mode.
        
        Args:
            mode: The mode value. Expected type: `c.ShapeMode`.
        
        Returns:
            None.
        """
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported ellipse mode {mode!r}.")
        self.state.style.ellipse_mode = mode
        self._mark_style_changed()

    def image_mode(self, mode: c.ShapeMode) -> None:
        """Image mode.
        
        Args:
            mode: The mode value. Expected type: `c.ShapeMode`.
        
        Returns:
            None.
        """
        if mode not in {c.CORNER, c.CORNERS, c.CENTER}:
            raise ArgumentValidationError(f"Unsupported image mode {mode!r}.")
        self.state.style.image_mode = mode
        self._mark_style_changed()

    def image_sampling(self, mode: c.ImageSampling | None = None) -> c.ImageSampling:
        """Image sampling.
        
        Args:
            mode: The mode value. Expected type: `c.ImageSampling | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `c.ImageSampling`.
        """
        if mode is not None:
            if mode not in {c.LINEAR, c.NEAREST}:
                raise ArgumentValidationError(f"Unsupported image sampling mode {mode!r}.")
            self.state.style.image_sampling = mode
            self._mark_style_changed()
        return self.state.style.image_sampling

    def smooth(self) -> None:
        """Smooth.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.state.style.image_sampling = c.LINEAR
        self._mark_style_changed()

    def no_smooth(self) -> None:
        """No smooth.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.state.style.image_sampling = c.NEAREST
        self._mark_style_changed()

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
        """Tint.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        self.state.style.image_tint = self._color_from_args(args)
        self._mark_style_changed()

    def no_tint(self) -> None:
        """No tint.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.state.style.image_tint = None
        self._mark_style_changed()
