"""Generated primitive meshes for software 3D."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, cast

import numpy as np

from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3
from gummysnake.exceptions import ArgumentValidationError

from .types import UVCoord

_MESH_CACHE_SIZE = 256


def _rust_primitive_model(function_name: str, *args: object) -> Model3D | None:
    from gummysnake.rust.canvas import is_canvas_runtime_available, require_canvas_runtime

    if not is_canvas_runtime_available():
        return None
    runtime = require_canvas_runtime()
    factory = getattr(runtime, function_name, None)
    if factory is None:
        return None
    try:
        return Model3D(meshes=None, rust_handle=factory(*args))
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc


def clear_primitive_model_cache() -> None:
    for fn in (
        plane_model,
        box_model,
        sphere_model,
        ellipsoid_model,
        cylinder_model,
        cone_model,
        torus_model,
    ):
        cast(Any, fn).cache_clear()


def primitive_model_cache_info() -> dict[str, Any]:
    return {
        "plane": cast(Any, plane_model).cache_info(),
        "box": cast(Any, box_model).cache_info(),
        "sphere": cast(Any, sphere_model).cache_info(),
        "ellipsoid": cast(Any, ellipsoid_model).cache_info(),
        "cylinder": cast(Any, cylinder_model).cache_info(),
        "cone": cast(Any, cone_model).cache_info(),
        "torus": cast(Any, torus_model).cache_info(),
    }


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def plane_model(width: float, height: float | None = None) -> Model3D:
    plane_height = width if height is None else height
    if rust_model := _rust_primitive_model("create_plane_model_handle", width, height):
        return rust_model
    if width <= 0 or plane_height <= 0:
        raise ArgumentValidationError("plane() dimensions must be positive.")
    hw, hh = width / 2.0, plane_height / 2.0
    mesh = Mesh3D(
        vertices=(Vec3(-hw, -hh, 0.0), Vec3(hw, -hh, 0.0), Vec3(hw, hh, 0.0), Vec3(-hw, hh, 0.0)),
        faces=((0, 1, 2, 3),),
        texcoords=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
    )
    return Model3D(meshes=(mesh,))


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def box_model(width: float, height: float | None = None, depth: float | None = None) -> Model3D:
    box_height = width if height is None else height
    box_depth = width if depth is None else depth
    if rust_model := _rust_primitive_model("create_box_model_handle", width, height, depth):
        return rust_model
    if width <= 0 or box_height <= 0 or box_depth <= 0:
        raise ArgumentValidationError("box() dimensions must be positive.")
    hw, hh, hd = width / 2.0, box_height / 2.0, box_depth / 2.0
    face_specs = (
        (
            (Vec3(-hw, hh, -hd), Vec3(hw, hh, -hd), Vec3(hw, -hh, -hd), Vec3(-hw, -hh, -hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(-hw, -hh, hd), Vec3(hw, -hh, hd), Vec3(hw, hh, hd), Vec3(-hw, hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(-hw, -hh, -hd), Vec3(hw, -hh, -hd), Vec3(hw, -hh, hd), Vec3(-hw, -hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(hw, hh, -hd), Vec3(-hw, hh, -hd), Vec3(-hw, hh, hd), Vec3(hw, hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(hw, -hh, -hd), Vec3(hw, hh, -hd), Vec3(hw, hh, hd), Vec3(hw, -hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(-hw, -hh, hd), Vec3(-hw, hh, hd), Vec3(-hw, hh, -hd), Vec3(-hw, -hh, -hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
    )
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    for face_vertices, face_texcoords in face_specs:
        start = len(vertices)
        vertices.extend(face_vertices)
        texcoords.extend(face_texcoords)
        faces.append((start, start + 1, start + 2, start + 3))
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def sphere_model(radius: float, detail_x: int = 24, detail_y: int = 16) -> Model3D:
    if rust_model := _rust_primitive_model(
        "create_sphere_model_handle", radius, detail_x, detail_y
    ):
        return rust_model
    if radius <= 0:
        raise ArgumentValidationError("sphere() radius must be positive.")
    if detail_x < 3 or detail_y < 2:
        raise ArgumentValidationError("sphere() detail values must be at least 3 and 2.")
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    for iy in range(detail_y + 1):
        phi = math.pi * iy / detail_y
        y = math.cos(phi) * radius
        ring_radius = math.sin(phi) * radius
        for ix in range(detail_x):
            theta = math.tau * ix / detail_x
            vertices.append(Vec3(math.cos(theta) * ring_radius, y, math.sin(theta) * ring_radius))
            texcoords.append((ix / detail_x, 1.0 - iy / detail_y))

    def vertex_index(ix: int, iy: int) -> int:
        return iy * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            tl, tr = vertex_index(ix, iy), vertex_index(ix + 1, iy)
            bl, br = vertex_index(ix, iy + 1), vertex_index(ix + 1, iy + 1)
            faces.append(
                (tl, bl, br)
                if iy == 0
                else (tl, tr, bl)
                if iy == detail_y - 1
                else (tl, tr, br, bl)
            )
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def ellipsoid_model(
    radius_x: float,
    radius_y: float | None = None,
    radius_z: float | None = None,
    detail_x: int = 24,
    detail_y: int = 16,
) -> Model3D:
    if rust_model := _rust_primitive_model(
        "create_ellipsoid_model_handle", radius_x, radius_y, radius_z, detail_x, detail_y
    ):
        return rust_model
    ry = radius_x if radius_y is None else radius_y
    rz = radius_x if radius_z is None else radius_z
    if radius_x <= 0 or ry <= 0 or rz <= 0:
        raise ArgumentValidationError("ellipsoid() radius values must be positive.")
    mesh = sphere_model(1.0, detail_x, detail_y).meshes[0]
    vertices = mesh.vertex_array() * np.array((radius_x, ry, rz), dtype=np.float64)
    return Model3D(
        meshes=(
            Mesh3D.from_arrays(
                vertices,
                face_indices=mesh.face_index_array(),
                face_offsets=mesh.face_offset_array(),
                texcoords=mesh.texcoord_array(),
            ),
        )
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def cylinder_model(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    bottom_cap: bool = True,
    top_cap: bool = True,
) -> Model3D:
    if rust_model := _rust_primitive_model(
        "create_cylinder_model_handle", radius, height, detail_x, detail_y, bottom_cap, top_cap
    ):
        return rust_model
    if radius <= 0 or height <= 0:
        raise ArgumentValidationError("cylinder() radius and height must be positive.")
    if detail_x < 3 or detail_y < 1:
        raise ArgumentValidationError("cylinder() detail values must be at least 3 and 1.")
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    half_height = height / 2.0
    for iy in range(detail_y + 1):
        y = -half_height + height * iy / detail_y
        for ix in range(detail_x):
            theta = math.tau * ix / detail_x
            vertices.append(Vec3(math.cos(theta) * radius, y, math.sin(theta) * radius))
            texcoords.append((ix / detail_x, iy / detail_y))

    def vertex_index(ix: int, iy: int) -> int:
        return iy * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            faces.append(
                (
                    vertex_index(ix, iy),
                    vertex_index(ix + 1, iy),
                    vertex_index(ix + 1, iy + 1),
                    vertex_index(ix, iy + 1),
                )
            )
    if bottom_cap:
        center = len(vertices)
        vertices.append(Vec3(0.0, -half_height, 0.0))
        texcoords.append((0.5, 0.5))
        for ix in range(detail_x):
            faces.append((center, vertex_index(ix + 1, 0), vertex_index(ix, 0)))
    if top_cap:
        center = len(vertices)
        vertices.append(Vec3(0.0, half_height, 0.0))
        texcoords.append((0.5, 0.5))
        for ix in range(detail_x):
            faces.append((center, vertex_index(ix, detail_y), vertex_index(ix + 1, detail_y)))
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def cone_model(
    radius: float, height: float, detail_x: int = 24, detail_y: int = 1, *, cap: bool = True
) -> Model3D:
    if rust_model := _rust_primitive_model(
        "create_cone_model_handle", radius, height, detail_x, detail_y, cap
    ):
        return rust_model
    if radius <= 0 or height <= 0:
        raise ArgumentValidationError("cone() radius and height must be positive.")
    if detail_x < 3 or detail_y < 1:
        raise ArgumentValidationError("cone() detail values must be at least 3 and 1.")
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    half_height = height / 2.0
    for iy in range(detail_y + 1):
        fraction = iy / detail_y
        ring_radius = radius * (1.0 - fraction)
        y = -half_height + height * fraction
        for ix in range(detail_x):
            theta = math.tau * ix / detail_x
            vertices.append(Vec3(math.cos(theta) * ring_radius, y, math.sin(theta) * ring_radius))
            texcoords.append((ix / detail_x, fraction))

    def vertex_index(ix: int, iy: int) -> int:
        return iy * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            if iy == detail_y - 1:
                faces.append(
                    (vertex_index(ix, iy), vertex_index(ix + 1, iy), vertex_index(ix, iy + 1))
                )
            else:
                faces.append(
                    (
                        vertex_index(ix, iy),
                        vertex_index(ix + 1, iy),
                        vertex_index(ix + 1, iy + 1),
                        vertex_index(ix, iy + 1),
                    )
                )
    if cap:
        center = len(vertices)
        vertices.append(Vec3(0.0, -half_height, 0.0))
        texcoords.append((0.5, 0.5))
        for ix in range(detail_x):
            faces.append((center, vertex_index(ix + 1, 0), vertex_index(ix, 0)))
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def torus_model(
    radius: float, tube_radius: float | None = None, detail_x: int = 24, detail_y: int = 12
) -> Model3D:
    if rust_model := _rust_primitive_model(
        "create_torus_model_handle", radius, tube_radius, detail_x, detail_y
    ):
        return rust_model
    tube = radius / 4.0 if tube_radius is None else tube_radius
    if radius <= 0 or tube <= 0:
        raise ArgumentValidationError("torus() radius values must be positive.")
    if detail_x < 3 or detail_y < 3:
        raise ArgumentValidationError("torus() detail values must be at least 3.")
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    for iy in range(detail_y):
        phi = math.tau * iy / detail_y
        cos_phi, sin_phi = math.cos(phi), math.sin(phi)
        for ix in range(detail_x):
            theta = math.tau * ix / detail_x
            ring = radius + tube * math.cos(theta)
            vertices.append(Vec3(ring * cos_phi, tube * math.sin(theta), ring * sin_phi))
            texcoords.append((ix / detail_x, iy / detail_y))

    def vertex_index(ix: int, iy: int) -> int:
        return (iy % detail_y) * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            faces.append(
                (
                    vertex_index(ix, iy),
                    vertex_index(ix + 1, iy),
                    vertex_index(ix + 1, iy + 1),
                    vertex_index(ix, iy + 1),
                )
            )
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )
