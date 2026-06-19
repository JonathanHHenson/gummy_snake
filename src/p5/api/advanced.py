"""Implemented advanced 3D and sound APIs."""

from __future__ import annotations

from pathlib import Path

from p5.api.current import require_context
from p5.assets.media import Capture, Video
from p5.assets.media import create_capture as _create_capture
from p5.assets.media import create_video as _create_video
from p5.assets.model import load_model as _load_model
from p5.assets.shader import create_shader as _create_shader
from p5.assets.shader import load_shader as _load_shader
from p5.assets.sound import Sound
from p5.assets.sound import load_sound as _load_sound


def create_camera(*args: object):
    return require_context().create_camera(*args)


def camera(*args: object):
    return require_context().camera(*args)


def perspective(*args: object):
    return require_context().perspective(*args)


def ortho(*args: object):
    return require_context().ortho(*args)


def orbit_control(*args: object):
    return require_context().orbit_control(*args)


def ambient_light(*args: object) -> None:
    require_context().ambient_light(*args)


def directional_light(*args: object) -> None:
    require_context().directional_light(*args)


def point_light(*args: object) -> None:
    require_context().point_light(*args)


def normal_material() -> None:
    require_context().normal_material()


def ambient_material(*args: object) -> None:
    require_context().ambient_material(*args)


def specular_material(*args: object) -> None:
    require_context().specular_material(*args)


def shininess(value: float) -> None:
    require_context().shininess(value)


def texture(image) -> None:
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


def create_model(mesh: object):
    return require_context().create_model(mesh)


def save_obj(model_value, path: str | Path):
    return require_context().save_obj(model_value, path)


def save_stl(model_value, path: str | Path):
    return require_context().save_stl(model_value, path)


def load_model(path: str | Path, normalize: bool = False, *, package: str | None = None):
    return _load_model(path, normalize, package=package)


def model(shape: object) -> None:
    require_context().model(shape)


def load_shader(vertex_path: str | Path, fragment_path: str | Path):
    return _load_shader(vertex_path, fragment_path)


def create_shader(vertex_source: str, fragment_source: str):
    return _create_shader(vertex_source, fragment_source)


def shader(shader_program) -> None:
    require_context().shader(shader_program)


def reset_shader() -> None:
    require_context().reset_shader()


def load_sound(path: str | Path) -> Sound:
    return _load_sound(path)


def create_audio(path: str | Path) -> Sound:
    return _load_sound(path)


def create_video(path: str | Path) -> Video:
    return _create_video(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture:
    return _create_capture(kind, device=device, width=width, height=height)


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
    "create_capture",
    "create_camera",
    "directional_light",
    "load_model",
    "load_shader",
    "create_shader",
    "shader",
    "reset_shader",
    "load_sound",
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
