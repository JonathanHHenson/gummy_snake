"""Direct fast 3D camera, light, material, and primitive forwards."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from collections.abc import Callable

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class FastThreeDControlsMixin:
    """Forward 3D controls to the cached frame context and invalidate model batches."""

    __slots__ = ()

    _context: SketchContext
    _invalidate_model_batch_cache: Callable[[], None]

    def camera(self, *args: Any) -> Any:
        """Set or return the active 3D camera without global-mode lookup."""
        self._invalidate_model_batch_cache()
        return self._context.camera(*args)

    def set_camera(self, camera: Any) -> Any:
        """Set the active 3D camera without global-mode lookup."""
        self._invalidate_model_batch_cache()
        return self._context.set_camera(camera)

    def perspective(self, *args: Any) -> Any:
        """Set or return the active 3D perspective projection."""
        self._invalidate_model_batch_cache()
        return self._context.perspective(*args)

    def ortho(self, *args: Any) -> Any:
        """Set or return the active 3D orthographic projection."""
        self._invalidate_model_batch_cache()
        return self._context.ortho(*args)

    def frustum(self, *args: Any) -> Any:
        """Set the active 3D frustum projection."""
        self._invalidate_model_batch_cache()
        return self._context.frustum(*args)

    def ambient_light(self, *args: Any) -> None:
        """Add an ambient 3D light without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.ambient_light(*args)

    def directional_light(self, *args: Any) -> None:
        """Add a directional 3D light without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.directional_light(*args)

    def point_light(self, *args: Any) -> None:
        """Add a point 3D light without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.point_light(*args)

    def lights(self) -> None:
        """Enable default 3D lights without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.lights()

    def no_lights(self) -> None:
        """Disable 3D lights without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.no_lights()

    def ambient_material(self, *args: Any) -> None:
        """Set the active ambient 3D material."""
        self._invalidate_model_batch_cache()
        self._context.ambient_material(*args)

    def specular_material(self, *args: Any) -> None:
        """Set the active specular 3D material."""
        self._invalidate_model_batch_cache()
        self._context.specular_material(*args)

    def emissive_material(self, *args: Any) -> None:
        """Set the active emissive 3D material."""
        self._invalidate_model_batch_cache()
        self._context.emissive_material(*args)

    def normal_material(self) -> None:
        """Use normal-based 3D material coloring."""
        self._invalidate_model_batch_cache()
        self._context.normal_material()

    def shininess(self, value: float) -> None:
        """Set active 3D material shininess."""
        self._invalidate_model_batch_cache()
        self._context.shininess(float(value))

    def metalness(self, value: float) -> None:
        """Set active 3D material metalness."""
        self._invalidate_model_batch_cache()
        self._context.metalness(float(value))

    def plane(self, width: float, height: float | None = None) -> None:
        """Draw a 3D plane without global-mode lookup."""
        self._context.plane(float(width), None if height is None else float(height))

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        """Draw a 3D box without global-mode lookup."""
        self._context.box(
            float(width),
            None if height is None else float(height),
            None if depth is None else float(depth),
        )

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        """Draw a 3D sphere without global-mode lookup."""
        self._context.sphere(float(radius), int(detail_x), int(detail_y))

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        """Draw a 3D ellipsoid without global-mode lookup."""
        self._context.ellipsoid(
            float(radius_x),
            None if radius_y is None else float(radius_y),
            None if radius_z is None else float(radius_z),
            int(detail_x),
            int(detail_y),
        )

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
        """Draw a 3D cylinder without global-mode lookup."""
        self._context.cylinder(
            float(radius),
            float(height),
            int(detail_x),
            int(detail_y),
            bottom_cap=bottom_cap,
            top_cap=top_cap,
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
        """Draw a 3D cone without global-mode lookup."""
        self._context.cone(float(radius), float(height), int(detail_x), int(detail_y), cap=cap)

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        """Draw a 3D torus without global-mode lookup."""
        self._context.torus(
            float(radius),
            None if tube_radius is None else float(tube_radius),
            int(detail_x),
            int(detail_y),
        )
