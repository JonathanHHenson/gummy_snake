# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""3D primitive factory methods for SketchContext."""

from __future__ import annotations

from pathlib import Path

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


class ThreeDPrimitivesMixin:
    def plane(self, width: float, height: float | None = None) -> None:
        self.model(plane_model(float(width), None if height is None else float(height)))

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self.model(
            box_model(
                float(width),
                None if height is None else float(height),
                None if depth is None else float(depth),
            )
        )

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self.model(sphere_model(float(radius), int(detail_x), int(detail_y)))

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        self.model(
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
        self.model(
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
        self.model(cone_model(float(radius), float(height), int(detail_x), int(detail_y), cap=cap))

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        self.model(
            torus_model(
                float(radius),
                None if tube_radius is None else float(tube_radius),
                int(detail_x),
                int(detail_y),
            )
        )

    def create_model(self, mesh: object) -> Model3D:
        if isinstance(mesh, Model3D):
            return mesh
        if isinstance(mesh, Mesh3D):
            return Model3D(meshes=(mesh,))
        raise ArgumentValidationError("create_model() requires a Mesh3D or Model3D value.")

    def save_obj(self, model: Model3D, path: str | Path) -> Path:
        return save_obj_model(model, path)

    def save_stl(self, model: Model3D, path: str | Path) -> Path:
        return save_stl_model(model, path)
