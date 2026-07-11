"""3D primitive forwards for object-mode sketches."""

from __future__ import annotations

from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadePrimitivesMixin(SketchFacadeBaseMixin):
    """Draw built-in 3D primitives through the active object-mode context."""

    __facade_doc_topic__ = "Draw built-in primitives in this sketch's active 3D scene."

    def plane(self, width: float, height: float | None = None) -> None:
        self._ctx.plane(width, height)

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self._ctx.box(width, height, depth)

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self._ctx.sphere(radius, detail_x, detail_y)

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        self._ctx.ellipsoid(radius_x, radius_y, radius_z, detail_x, detail_y)

    def cylinder(
        self,
        radius: float,
        height: float,
        detail_x: int = 24,
        detail_y: int = 1,
        *,
        bottom_cap: bool = True,
        top_cap: bool = True,
    ) -> None:
        self._ctx.cylinder(
            radius, height, detail_x, detail_y, bottom_cap=bottom_cap, top_cap=top_cap
        )

    def cone(
        self,
        radius: float,
        height: float,
        detail_x: int = 24,
        detail_y: int = 1,
        *,
        cap: bool = True,
    ) -> None:
        self._ctx.cone(radius, height, detail_x, detail_y, cap=cap)

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        self._ctx.torus(radius, tube_radius, detail_x, detail_y)
