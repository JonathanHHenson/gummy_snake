"""Color and style methods for SketchContext."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake.core.color import Color, lerp_color
from gummysnake.exceptions import ArgumentValidationError


class StyleContextMixin:
    state: Any
    renderer: Any

    def _mark_style_changed(self) -> None:
        self.state.style.mark_changed()

    def color(self, *args: object) -> Color:
        return Color.from_args(
            args, mode=self.state.color_mode.mode, ranges=self.state.color_mode.ranges
        )

    def color_mode(
        self,
        mode: c.ColorMode,
        max1: float | None = None,
        max2: float | None = None,
        max3: float | None = None,
        max_alpha: float | None = None,
    ) -> None:
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
        return lerp_color(start, stop, amount)

    def background(self, *args: object) -> None:
        self.renderer.background(self.color(*args))

    def clear(self) -> None:
        self.renderer.clear()

    def fill(self, *args: object) -> None:
        self.state.style.fill_color = self.color(*args)
        self._mark_style_changed()

    def no_fill(self) -> None:
        self.state.style.fill_color = None
        self._mark_style_changed()

    def stroke(self, *args: object) -> None:
        self.state.style.stroke_color = self.color(*args)
        self._mark_style_changed()

    def no_stroke(self) -> None:
        self.state.style.stroke_color = None
        self._mark_style_changed()

    def stroke_weight(self, weight: float) -> None:
        if weight < 0:
            raise ArgumentValidationError("stroke_weight() cannot be negative.")
        self.state.style.stroke_weight = float(weight)
        self._mark_style_changed()

    def stroke_cap(self, cap: c.StrokeCap) -> None:
        if cap not in {c.ROUND, c.SQUARE, c.PROJECT}:
            raise ArgumentValidationError(f"Unsupported stroke cap {cap!r}.")
        self.state.style.stroke_cap = cap
        self._mark_style_changed()

    def stroke_join(self, join: c.StrokeJoin) -> None:
        if join not in {c.MITER, c.BEVEL, c.ROUND}:
            raise ArgumentValidationError(f"Unsupported stroke join {join!r}.")
        self.state.style.stroke_join = join
        self._mark_style_changed()

    def rect_mode(self, mode: c.ShapeMode) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported rect mode {mode!r}.")
        self.state.style.rect_mode = mode
        self._mark_style_changed()

    def ellipse_mode(self, mode: c.ShapeMode) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported ellipse mode {mode!r}.")
        self.state.style.ellipse_mode = mode
        self._mark_style_changed()

    def image_mode(self, mode: c.ShapeMode) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER}:
            raise ArgumentValidationError(f"Unsupported image mode {mode!r}.")
        self.state.style.image_mode = mode
        self._mark_style_changed()

    def image_sampling(self, mode: c.ImageSampling | None = None) -> c.ImageSampling:
        if mode is not None:
            if mode not in {c.LINEAR, c.NEAREST}:
                raise ArgumentValidationError(f"Unsupported image sampling mode {mode!r}.")
            self.state.style.image_sampling = mode
            self._mark_style_changed()
        return self.state.style.image_sampling

    def smooth(self) -> None:
        self.state.style.image_sampling = c.LINEAR
        self._mark_style_changed()

    def no_smooth(self) -> None:
        self.state.style.image_sampling = c.NEAREST
        self._mark_style_changed()
