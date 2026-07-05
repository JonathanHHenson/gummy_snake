"""Global-mode WEBGL-style 3D camera, lighting, material, and primitive wrappers."""

from __future__ import annotations

from collections.abc import Callable
from typing import overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import Camera3D, Mesh3D, Model3D, Vec3
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
)

Number = int | float
ColorValue = Color | str
CameraArg = Camera3D | Number
ColorArg = ColorValue | Number


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


def create_camera(*args: CameraArg) -> Camera3D:
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


def camera(*args: CameraArg) -> Camera3D:
    return require_context().camera(*args)


def set_camera(camera_value: Camera3D) -> Camera3D:
    return require_context().set_camera(camera_value)


def roll(angle: Number) -> Camera3D:
    return require_context().roll(angle)


def world_to_screen(x: Number, y: Number, z: Number) -> tuple[float, float, float]:
    return require_context().world_to_screen(x, y, z)


def screen_to_world(x: Number, y: Number, depth: Number = 0.0) -> Vec3:
    return require_context().screen_to_world(x, y, depth)


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


def perspective(*args: Number) -> PerspectiveProjection:
    return require_context().perspective(*args)


@overload
def ortho() -> OrthographicProjection: ...


@overload
def ortho(width: Number, height: Number, /) -> OrthographicProjection: ...


@overload
def ortho(
    width: Number, height: Number, near: Number, far: Number, /
) -> OrthographicProjection: ...


def ortho(*args: Number) -> OrthographicProjection:
    return require_context().ortho(*args)


def frustum(
    left: Number,
    right: Number,
    bottom: Number,
    top: Number,
    near: Number = 0.1,
    far: Number = 10_000.0,
) -> FrustumProjection:
    return require_context().frustum(left, right, bottom, top, near, far)


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


def orbit_control(*args: Number) -> Camera3D:
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


def ambient_light(*args: ColorArg) -> None:
    _context_call("ambient_light", *args)


def lights() -> None:
    require_context().lights()


def no_lights() -> None:
    require_context().no_lights()


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


def directional_light(*args: ColorArg) -> None:
    _context_call("directional_light", *args)


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


def point_light(*args: ColorArg) -> None:
    _context_call("point_light", *args)


def spot_light(*args: ColorArg) -> None:
    _context_call("spot_light", *args)


def image_light(image: Image, intensity: float = 1.0) -> None:
    require_context().image_light(image, intensity)


def panorama(image: Image | None = None) -> Image | None:
    return require_context().panorama(image)


def light_falloff(constant: float, linear: float, quadratic: float) -> None:
    require_context().light_falloff(constant, linear, quadratic)


def specular_color(*args: ColorArg) -> None:
    _context_call("specular_color", *args)


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


def ambient_material(*args: ColorArg) -> None:
    _context_call("ambient_material", *args)


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


def specular_material(*args: ColorArg) -> None:
    _context_call("specular_material", *args)


def shininess(value: float) -> None:
    require_context().shininess(value)


def emissive_material(*args: ColorArg) -> None:
    _context_call("emissive_material", *args)


def metalness(value: float) -> None:
    require_context().metalness(value)


def texture_mode(mode: c.TextureCoordinateMode | str | None = None) -> c.TextureCoordinateMode:
    return require_context().texture_mode(mode)


def texture_wrap(
    wrap_x: c.TextureWrapMode | str | None = None,
    wrap_y: c.TextureWrapMode | str | None = None,
) -> tuple[c.TextureWrapMode, c.TextureWrapMode]:
    return require_context().texture_wrap(wrap_x, wrap_y)


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


def normal(x: float, y: float, z: float) -> None:
    require_context().normal(x, y, z)


def vertex_property(name: str, value: object) -> None:
    require_context().vertex_property(name, value)


def build_geometry(callback: Callable[[], object]) -> Model3D:
    return require_context().build_geometry(callback)


def free_geometry(model_value: Model3D) -> None:
    require_context().free_geometry(model_value)


def flip_u(mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
    return require_context().flip_u(mesh_or_model)


def flip_v(mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
    return require_context().flip_v(mesh_or_model)


def model(shape: Mesh3D | Model3D) -> None:
    require_context().model(shape)


__all__ = [
    "create_camera",
    "camera",
    "set_camera",
    "roll",
    "world_to_screen",
    "screen_to_world",
    "perspective",
    "frustum",
    "ortho",
    "orbit_control",
    "ambient_light",
    "lights",
    "no_lights",
    "directional_light",
    "point_light",
    "spot_light",
    "image_light",
    "panorama",
    "light_falloff",
    "specular_color",
    "normal_material",
    "ambient_material",
    "specular_material",
    "shininess",
    "emissive_material",
    "metalness",
    "texture_mode",
    "texture_wrap",
    "texture",
    "plane",
    "box",
    "sphere",
    "ellipsoid",
    "cylinder",
    "cone",
    "torus",
    "create_model",
    "normal",
    "vertex_property",
    "build_geometry",
    "free_geometry",
    "flip_u",
    "flip_v",
    "model",
]
