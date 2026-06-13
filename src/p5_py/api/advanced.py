"""Implemented advanced 3D and sound APIs."""

from __future__ import annotations

from pathlib import Path

from p5_py.api.current import require_context
from p5_py.assets.media import Capture, Video
from p5_py.assets.media import create_capture as _create_capture
from p5_py.assets.media import create_video as _create_video
from p5_py.assets.model import load_model as _load_model
from p5_py.assets.shader import create_shader as _create_shader
from p5_py.assets.shader import load_shader as _load_shader
from p5_py.assets.sound import Sound
from p5_py.assets.sound import load_sound as _load_sound


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


createCamera = create_camera
orbitControl = orbit_control
ambientLight = ambient_light
directionalLight = directional_light
pointLight = point_light
normalMaterial = normal_material
ambientMaterial = ambient_material
specularMaterial = specular_material
loadModel = load_model
loadShader = load_shader
createShader = create_shader
loadSound = load_sound
createAudio = create_audio
createVideo = create_video
createCapture = create_capture
resetShader = reset_shader


__all__ = [
    "Sound",
    "Video",
    "Capture",
    "ambient_light",
    "orbit_control",
    "ambient_material",
    "ambientLight",
    "ambientMaterial",
    "box",
    "camera",
    "create_audio",
    "create_video",
    "create_capture",
    "create_camera",
    "createAudio",
    "createVideo",
    "createCapture",
    "createCamera",
    "directional_light",
    "directionalLight",
    "load_model",
    "load_shader",
    "create_shader",
    "shader",
    "reset_shader",
    "load_sound",
    "loadModel",
    "loadShader",
    "createShader",
    "loadSound",
    "model",
    "normal_material",
    "normalMaterial",
    "ortho",
    "perspective",
    "texture",
    "plane",
    "resetShader",
    "point_light",
    "pointLight",
    "shininess",
    "specular_material",
    "specularMaterial",
    "sphere",
    "orbitControl",
]
