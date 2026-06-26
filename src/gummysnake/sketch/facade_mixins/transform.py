"""Transform and scoped state forwards for object sketches."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.api.global_mode.helpers import (
    _UNSET,
    ColorArgument,
    CoordinatePair,
    ScaleArgument,
    Unset,
    style_color_args,
    xy,
)
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeTransformMixin(SketchFacadeBaseMixin):
    def push(self) -> None:
        self._ctx.push()

    def pop(self) -> None:
        self._ctx.pop()

    @contextmanager
    def pushed(self) -> Generator[None]:
        self.push()
        try:
            yield
        finally:
            self.pop()

    @contextmanager
    def style(
        self,
        *,
        fill: ColorArgument | None | Unset = _UNSET,
        stroke: ColorArgument | None | Unset = _UNSET,
        stroke_weight: float | None = None,
        stroke_cap: c.StrokeCap | None = None,
        stroke_join: c.StrokeJoin | None = None,
        rect_mode: c.ShapeMode | None = None,
        ellipse_mode: c.ShapeMode | None = None,
        image_mode: c.ShapeMode | None = None,
        blend_mode: c.BlendMode | None = None,
    ) -> Generator[None]:
        self.push()
        try:
            if fill is None:
                self._ctx.no_fill()
            elif fill is not _UNSET:
                cast(Any, self._ctx).fill(*style_color_args(fill))
            if stroke is None:
                self._ctx.no_stroke()
            elif stroke is not _UNSET:
                cast(Any, self._ctx).stroke(*style_color_args(stroke))
            if stroke_weight is not None:
                self._ctx.stroke_weight(stroke_weight)
            if stroke_cap is not None:
                self._ctx.stroke_cap(stroke_cap)
            if stroke_join is not None:
                self._ctx.stroke_join(stroke_join)
            if rect_mode is not None:
                self._ctx.rect_mode(rect_mode)
            if ellipse_mode is not None:
                self._ctx.ellipse_mode(ellipse_mode)
            if image_mode is not None:
                self._ctx.image_mode(image_mode)
            if blend_mode is not None:
                self._ctx.blend_mode(blend_mode)
            yield
        finally:
            self.pop()

    @contextmanager
    def transform(
        self,
        *,
        translate: CoordinatePair | Unset = _UNSET,
        rotate: float | None = None,
        scale: ScaleArgument | Unset = _UNSET,
    ) -> Generator[None]:
        self.push()
        try:
            if translate is not _UNSET:
                tx, ty = xy(translate)
                self._ctx.translate(tx, ty)
            if rotate is not None:
                self._ctx.rotate(rotate)
            if scale is not _UNSET:
                if isinstance(scale, Sequence) and not isinstance(scale, str | bytes | bytearray):
                    sx, sy = xy(scale)
                    self._ctx.scale(sx, sy)
                else:
                    self._ctx.scale(float(cast(float, scale)))
            yield
        finally:
            self.pop()

    def translate(self, x: float, y: float) -> None:
        self._ctx.translate(x, y)

    def rotate(self, angle: float) -> None:
        self._ctx.rotate(angle)

    def scale(self, x: float, y: float | None = None) -> None:
        self._ctx.scale(x, y)

    def shear_x(self, angle: float) -> None:
        self._ctx.shear_x(angle)

    def shear_y(self, angle: float) -> None:
        self._ctx.shear_y(angle)

    def apply_matrix(self, a: float, b: float, cc: float, d: float, e: float, f: float) -> None:
        self._ctx.apply_matrix(a, b, cc, d, e, f)

    def reset_matrix(self) -> None:
        self._ctx.reset_matrix()

    def angle_mode(self, mode: c.AngleMode) -> None:
        self._ctx.angle_mode(mode)
