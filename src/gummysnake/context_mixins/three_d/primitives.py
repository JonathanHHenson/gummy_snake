"""3D primitive factory methods for SketchContext."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from gummysnake.context_mixins.three_d._protocols import ThreeDContextHost
from gummysnake.drawing.renderer3d import Mesh3D, Model3D
from gummysnake.drawing.software3d import (
    box_model,
    cone_model,
    cylinder_model,
    ellipsoid_model,
    plane_model,
    sphere_model,
    torus_model,
)
from gummysnake.drawing.software3d import save_obj as save_obj_model
from gummysnake.drawing.software3d import save_stl as save_stl_model
from gummysnake.exceptions import ArgumentValidationError


def _three_d(self: Any) -> ThreeDContextHost:
    return cast(ThreeDContextHost, self)


class ThreeDPrimitivesMixin:
    _geometry_build_models: list[Model3D] | None
    _current_3d_normal: Any
    _current_vertex_properties: dict[str, object]

    def _emit_3d_model(self, model: Model3D) -> None:
        if self._geometry_build_models is not None:
            self._geometry_build_models.append(model)
            return
        _three_d(self).model(model)

    def plane(self, width: float, height: float | None = None) -> None:
        """Plane.
        
        Args:
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self._emit_3d_model(plane_model(float(width), None if height is None else float(height)))

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        """Box.
        
        Args:
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.
            depth: The depth value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self._emit_3d_model(
            box_model(
                float(width),
                None if height is None else float(height),
                None if depth is None else float(depth),
            )
        )

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        """Sphere.
        
        Args:
            radius: The radius value. Expected type: `float`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `16`.
        
        Returns:
            None.
        """
        self._emit_3d_model(sphere_model(float(radius), int(detail_x), int(detail_y)))

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        """Ellipsoid.
        
        Args:
            radius_x: The radius x value. Expected type: `float`.
            radius_y: The radius y value. Expected type: `float | None`. Defaults to `None`.
            radius_z: The radius z value. Expected type: `float | None`. Defaults to `None`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `16`.
        
        Returns:
            None.
        """
        self._emit_3d_model(
            ellipsoid_model(
                float(radius_x),
                None if radius_y is None else float(radius_y),
                None if radius_z is None else float(radius_z),
                int(detail_x),
                int(detail_y),
            )
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
        """Cylinder.
        
        Args:
            radius: The radius value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
            bottom_cap: The bottom cap value. Expected type: `bool`. Defaults to `True`.
            top_cap: The top cap value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        self._emit_3d_model(
            cylinder_model(
                float(radius),
                float(height),
                int(detail_x),
                int(detail_y),
                bottom_cap=bottom_cap,
                top_cap=top_cap,
            )
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
        """Cone.
        
        Args:
            radius: The radius value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
            cap: The cap value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        self._emit_3d_model(
            cone_model(float(radius), float(height), int(detail_x), int(detail_y), cap=cap)
        )

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        """Torus.
        
        Args:
            radius: The radius value. Expected type: `float`.
            tube_radius: The tube radius value. Expected type: `float | None`. Defaults to `None`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `12`.
        
        Returns:
            None.
        """
        self._emit_3d_model(
            torus_model(
                float(radius),
                None if tube_radius is None else float(tube_radius),
                int(detail_x),
                int(detail_y),
            )
        )

    def create_model(self, mesh: Mesh3D | Model3D) -> Model3D:
        """Create model.
        
        Args:
            mesh: The mesh value. Expected type: `Mesh3D | Model3D`.
        
        Returns:
            The return value. Type: `Model3D`.
        """
        if isinstance(mesh, Model3D):
            return mesh
        if isinstance(mesh, Mesh3D):
            return Model3D(meshes=(mesh,))
        raise ArgumentValidationError("create_model() requires a Mesh3D or Model3D value.")

    def normal(self, x: float, y: float, z: float) -> None:
        """Normal.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            z: The z value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._current_3d_normal = (float(x), float(y), float(z))

    def vertex_property(self, name: str, value: object) -> None:
        """Vertex property.
        
        Args:
            name: The name value. Expected type: `str`.
            value: The value value. Expected type: `object`.
        
        Returns:
            None.
        """
        if not str(name):
            raise ArgumentValidationError("vertex_property() name cannot be empty.")
        self._current_vertex_properties[str(name)] = value

    def build_geometry(self, callback: Any) -> Model3D:
        """Build geometry.
        
        Args:
            callback: The callback value. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Model3D`.
        """
        if not callable(callback):
            raise ArgumentValidationError("build_geometry() requires a drawing callback.")
        previous = self._geometry_build_models
        self._geometry_build_models = []
        try:
            result = callback()
            captured = self._geometry_build_models
        finally:
            self._geometry_build_models = previous
        if isinstance(result, Model3D):
            return result
        if isinstance(result, Mesh3D):
            return Model3D(meshes=(result,))
        if not captured:
            raise ArgumentValidationError(
                "build_geometry() callback did not create any 3D geometry."
            )
        if len(captured) == 1:
            return captured[0]
        meshes: list[Mesh3D] = []
        for model in captured:
            meshes.extend(model.meshes)
        return Model3D(meshes=tuple(meshes))

    def free_geometry(self, model: Model3D) -> None:
        """Free geometry.
        
        Args:
            model: The model value. Expected type: `Model3D`.
        
        Returns:
            None.
        """
        if not isinstance(model, Model3D):
            raise ArgumentValidationError("free_geometry() requires a Model3D value.")
        meshes = tuple(model.meshes)
        model._rust_handle = None
        model._meshes = meshes

    def flip_u(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        """Flip u.
        
        Args:
            mesh_or_model: The mesh or model value. Expected type: `Mesh3D | Model3D`.
        
        Returns:
            The return value. Type: `Mesh3D | Model3D`.
        """
        if isinstance(mesh_or_model, Mesh3D):
            return mesh_or_model.flip_u()
        if isinstance(mesh_or_model, Model3D):
            return Model3D(meshes=tuple(mesh.flip_u() for mesh in mesh_or_model.meshes))
        raise ArgumentValidationError("flip_u() requires a Mesh3D or Model3D value.")

    def flip_v(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        """Flip v.
        
        Args:
            mesh_or_model: The mesh or model value. Expected type: `Mesh3D | Model3D`.
        
        Returns:
            The return value. Type: `Mesh3D | Model3D`.
        """
        if isinstance(mesh_or_model, Mesh3D):
            return mesh_or_model.flip_v()
        if isinstance(mesh_or_model, Model3D):
            return Model3D(meshes=tuple(mesh.flip_v() for mesh in mesh_or_model.meshes))
        raise ArgumentValidationError("flip_v() requires a Mesh3D or Model3D value.")

    def save_obj(self, model: Model3D, path: str | Path) -> Path:
        """Save obj.
        
        Args:
            model: The model value. Expected type: `Model3D`.
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `Path`.
        """
        return save_obj_model(model, path)

    def save_stl(self, model: Model3D, path: str | Path) -> Path:
        """Save stl.
        
        Args:
            model: The model value. Expected type: `Model3D`.
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `Path`.
        """
        return save_stl_model(model, path)
