"""Global-mode WEBGL-style 3D camera, lighting, material, and primitive wrappers."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
)

Number = int | float
ColorValue = Color | str


@overload
def create_camera() -> Camera3D: ...


@overload
def create_camera(camera: Camera3D, /) -> Camera3D: ...


@overload
def create_camera(
    eye_x: Number,
    eye_y: Number,
    eye_z: Number,
    center_x: Number,
    center_y: Number,
    center_z: Number,
    up_x: Number,
    up_y: Number,
    up_z: Number,
    /,
) -> Camera3D: ...


def create_camera(*args: Any) -> Camera3D:
    return require_context().create_camera(*args)


@overload
def camera() -> Camera3D: ...


@overload
def camera(camera: Camera3D, /) -> Camera3D: ...


@overload
def camera(
    eye_x: Number,
    eye_y: Number,
    eye_z: Number,
    center_x: Number,
    center_y: Number,
    center_z: Number,
    up_x: Number,
    up_y: Number,
    up_z: Number,
    /,
) -> Camera3D: ...


def camera(*args: Any) -> Camera3D:
    return require_context().camera(*args)


@overload
def perspective() -> PerspectiveProjection: ...


@overload
def perspective(fov: Number, /) -> PerspectiveProjection: ...


@overload
def perspective(fov: Number, aspect: Number, /) -> PerspectiveProjection: ...


@overload
def perspective(fov: Number, aspect: Number, near: Number, /) -> PerspectiveProjection: ...


@overload
def perspective(
    fov: Number, aspect: Number, near: Number, far: Number, /
) -> PerspectiveProjection: ...


def perspective(*args: Any) -> PerspectiveProjection:
    return require_context().perspective(*args)


@overload
def ortho() -> OrthographicProjection: ...


@overload
def ortho(width: Number, height: Number, /) -> OrthographicProjection: ...


@overload
def ortho(
    width: Number, height: Number, near: Number, far: Number, /
) -> OrthographicProjection: ...


def ortho(*args: Any) -> OrthographicProjection:
    return require_context().ortho(*args)


@overload
def orbit_control() -> Camera3D: ...


@overload
def orbit_control(sensitivity_x: Number, /) -> Camera3D: ...


@overload
def orbit_control(sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D: ...


@overload
def orbit_control(
    sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
) -> Camera3D: ...


def orbit_control(*args: Any) -> Camera3D:
    return require_context().orbit_control(*args)


@overload
def ambient_light(value: ColorValue, /) -> None: ...


@overload
def ambient_light(gray: Number, /) -> None: ...


@overload
def ambient_light(gray: Number, alpha: Number, /) -> None: ...


@overload
def ambient_light(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def ambient_light(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def ambient_light(*args: Any) -> None:
    cast(Any, require_context()).ambient_light(*args)


@overload
def directional_light(value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def directional_light(gray: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def directional_light(gray: Number, alpha: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def directional_light(
    v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
) -> None: ...


@overload
def directional_light(
    v1: Number,
    v2: Number,
    v3: Number,
    alpha: Number,
    x: Number,
    y: Number,
    z: Number,
    /,
) -> None: ...


def directional_light(*args: Any) -> None:
    cast(Any, require_context()).directional_light(*args)


@overload
def point_light(value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(gray: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(gray: Number, alpha: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(
    v1: Number,
    v2: Number,
    v3: Number,
    alpha: Number,
    x: Number,
    y: Number,
    z: Number,
    /,
) -> None: ...


def point_light(*args: Any) -> None:
    cast(Any, require_context()).point_light(*args)


def normal_material() -> None:
    require_context().normal_material()


@overload
def ambient_material(value: ColorValue, /) -> None: ...


@overload
def ambient_material(gray: Number, /) -> None: ...


@overload
def ambient_material(gray: Number, alpha: Number, /) -> None: ...


@overload
def ambient_material(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def ambient_material(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def ambient_material(*args: Any) -> None:
    cast(Any, require_context()).ambient_material(*args)


@overload
def specular_material(value: ColorValue, /) -> None: ...


@overload
def specular_material(gray: Number, /) -> None: ...


@overload
def specular_material(gray: Number, alpha: Number, /) -> None: ...


@overload
def specular_material(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def specular_material(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def specular_material(*args: Any) -> None:
    cast(Any, require_context()).specular_material(*args)


def shininess(value: float) -> None:
    require_context().shininess(value)


def texture(image: Image) -> None:
    require_context().texture(image)


def plane(width: float, height: float | None = None) -> None:
    require_context().plane(width, height)


def box(width: float, height: float | None = None, depth: float | None = None) -> None:
    require_context().box(width, height, depth)


def sphere(radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
    require_context().sphere(radius, detail_x, detail_y)


def ellipsoid(
    radius_x: float,
    radius_y: float | None = None,
    radius_z: float | None = None,
    detail_x: int = 24,
    detail_y: int = 16,
) -> None:
    require_context().ellipsoid(radius_x, radius_y, radius_z, detail_x, detail_y)


def cylinder(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    bottom_cap: bool = True,
    top_cap: bool = True,
) -> None:
    require_context().cylinder(
        radius, height, detail_x, detail_y, bottom_cap=bottom_cap, top_cap=top_cap
    )


def cone(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    cap: bool = True,
) -> None:
    require_context().cone(radius, height, detail_x, detail_y, cap=cap)


def torus(
    radius: float,
    tube_radius: float | None = None,
    detail_x: int = 24,
    detail_y: int = 12,
) -> None:
    require_context().torus(radius, tube_radius, detail_x, detail_y)


def create_model(mesh: Mesh3D | Model3D) -> Model3D:
    return require_context().create_model(mesh)


def model(shape: Mesh3D | Model3D) -> None:
    require_context().model(shape)


__all__ = [
    "create_camera",
    "camera",
    "perspective",
    "ortho",
    "orbit_control",
    "ambient_light",
    "directional_light",
    "point_light",
    "normal_material",
    "ambient_material",
    "specular_material",
    "shininess",
    "texture",
    "plane",
    "box",
    "sphere",
    "ellipsoid",
    "cylinder",
    "cone",
    "torus",
    "create_model",
    "model",
]
