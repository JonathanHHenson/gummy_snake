"""Implemented advanced 3D and sound APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast, overload

from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.assets.media import Capture, Video
from gummysnake.assets.media import create_capture as _create_capture
from gummysnake.assets.media import create_capture_async as _create_capture_async
from gummysnake.assets.media import create_video as _create_video
from gummysnake.assets.media import create_video_async as _create_video_async
from gummysnake.assets.model import load_model as _load_model
from gummysnake.assets.model import load_model_async as _load_model_async
from gummysnake.assets.shader import create_shader as _create_shader
from gummysnake.assets.shader import load_shader as _load_shader
from gummysnake.assets.shader import load_shader_async as _load_shader_async
from gummysnake.assets.sound import Sound
from gummysnake.assets.sound import load_sound as _load_sound
from gummysnake.assets.sound import load_sound_async as _load_sound_async
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
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


def save_obj(model_value: Model3D, path: str | Path) -> Path:
    return require_context().save_obj(model_value, path)


def save_stl(model_value: Model3D, path: str | Path) -> Path:
    return require_context().save_stl(model_value, path)


def load_model(path: str | Path, normalize: bool = False, *, package: str | None = None) -> Model3D:
    return _load_model(path, normalize, package=package)


async def load_model_async(
    path: str | Path, normalize: bool = False, *, package: str | None = None
) -> Model3D:
    return await _load_model_async(path, normalize, package=package)


def model(shape: Mesh3D | Model3D) -> None:
    require_context().model(shape)


def load_shader(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    return _load_shader(vertex_path, fragment_path)


async def load_shader_async(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    return await _load_shader_async(vertex_path, fragment_path)


def create_shader(vertex_source: str, fragment_source: str) -> Shader3D:
    return _create_shader(vertex_source, fragment_source)


def shader(shader_program: Shader3D) -> None:
    require_context().shader(shader_program)


def reset_shader() -> None:
    require_context().reset_shader()


def load_sound(path: str | Path) -> Sound:
    return _load_sound(path)


async def load_sound_async(path: str | Path) -> Sound:
    return await _load_sound_async(path)


def create_audio(path: str | Path) -> Sound:
    return _load_sound(path)


def create_video(path: str | Path) -> Video:
    return _create_video(path)


async def create_video_async(path: str | Path) -> Video:
    return await _create_video_async(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture:
    return _create_capture(kind, device=device, width=width, height=height)


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture:
    return await _create_capture_async(kind, device=device, width=width, height=height)


__all__ = [
    "Sound",
    "Video",
    "Capture",
    "ambient_light",
    "orbit_control",
    "ambient_material",
    "box",
    "camera",
    "create_audio",
    "create_video",
    "create_video_async",
    "create_capture",
    "create_capture_async",
    "create_camera",
    "directional_light",
    "load_model",
    "load_model_async",
    "load_shader",
    "load_shader_async",
    "create_shader",
    "shader",
    "reset_shader",
    "load_sound",
    "load_sound_async",
    "model",
    "normal_material",
    "ortho",
    "perspective",
    "texture",
    "plane",
    "point_light",
    "shininess",
    "specular_material",
    "sphere",
    "ellipsoid",
    "cylinder",
    "cone",
    "torus",
    "create_model",
    "save_obj",
    "save_stl",
]
