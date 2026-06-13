"""Compatibility metadata and unsupported browser/data/advanced-media APIs."""

from __future__ import annotations

from p5_py.api import advanced as _advanced
from p5_py.exceptions import UnsupportedFeatureError

COMPATIBILITY_MATRIX = {
    "lifecycle": "supported",
    "global_mode": "supported",
    "canvas": "supported",
    "2d_primitives": "supported",
    "paths_and_curves": "partial",
    "color": "supported",
    "transforms": "supported",
    "mouse_keyboard_input": "partial",
    "dom": "excluded",
    "xml": "excluded",
    "table": "excluded",
    "webgl": "partial",
    "webgl_renderer": "partial",
    "3d_primitives": "partial",
    "camera_projection": "partial",
    "lights_materials": "partial",
    "textures": "partial",
    "models": "partial",
    "shaders": "partial",
    "sound": "partial",
    "sound_playback": "partial",
    "sound_analysis": "deferred",
    "sound_synthesis": "deferred",
    "media_playback": "partial",
    "media_capture": "partial",
}


def unsupported_feature(name: str, reason: str) -> None:
    raise UnsupportedFeatureError(f"{name} is not supported by p5-py. {reason}")


def _deferred_webgl_api(name: str) -> None:
    unsupported_feature(
        name,
        "This WEBGL-style API is deferred on the current software 3D path. "
        "See docs/advanced_3d_media_strategy.md for the supported slice "
        "and native-renderer follow-on work.",
    )


def _deferred_sound_api(name: str) -> None:
    unsupported_feature(
        name,
        "Sound APIs are deferred pending a native Python audio backend decision. "
        "See docs/advanced_3d_media_strategy.md.",
    )


def _deferred_media_api(name: str) -> None:
    unsupported_feature(
        name,
        "Native media playback/capture APIs are deferred because they have platform, "
        "privacy, and dependency implications outside the browser. "
        "See docs/advanced_3d_media_strategy.md.",
    )


def create_div(*_args, **_kwargs) -> None:
    unsupported_feature("create_div/createDiv", "DOM APIs are intentionally excluded.")


def create_button(*_args, **_kwargs) -> None:
    unsupported_feature("create_button/createButton", "DOM APIs are intentionally excluded.")


def select(*_args, **_kwargs) -> None:
    unsupported_feature("select", "DOM APIs are intentionally excluded.")


def load_xml(*_args, **_kwargs) -> None:
    unsupported_feature("load_xml/loadXML", "p5.XML is intentionally excluded.")


def load_table(*_args, **_kwargs) -> None:
    unsupported_feature(
        "load_table/loadTable",
        "p5.Table and p5.TableRow are intentionally excluded.",
    )


def create_camera(*args, **kwargs):
    return _advanced.create_camera(*args, **kwargs)


def camera(*args, **kwargs):
    return _advanced.camera(*args, **kwargs)


def perspective(*args, **kwargs):
    return _advanced.perspective(*args, **kwargs)


def ortho(*args, **kwargs):
    return _advanced.ortho(*args, **kwargs)


def orbit_control(*args, **kwargs):
    return _advanced.orbit_control(*args, **kwargs)


def ambient_light(*args, **kwargs) -> None:
    _advanced.ambient_light(*args, **kwargs)


def directional_light(*args, **kwargs) -> None:
    _advanced.directional_light(*args, **kwargs)


def point_light(*args, **kwargs) -> None:
    _advanced.point_light(*args, **kwargs)


def normal_material(*args, **kwargs) -> None:
    _advanced.normal_material(*args, **kwargs)


def ambient_material(*args, **kwargs) -> None:
    _advanced.ambient_material(*args, **kwargs)


def specular_material(*args, **kwargs) -> None:
    _advanced.specular_material(*args, **kwargs)


def shininess(*args, **kwargs) -> None:
    _advanced.shininess(*args, **kwargs)


def texture(*args, **kwargs) -> None:
    _advanced.texture(*args, **kwargs)


def plane(*args, **kwargs) -> None:
    _advanced.plane(*args, **kwargs)


def box(*args, **kwargs) -> None:
    _advanced.box(*args, **kwargs)


def sphere(*args, **kwargs) -> None:
    _advanced.sphere(*args, **kwargs)


def load_model(*args, **kwargs):
    return _advanced.load_model(*args, **kwargs)


def model(*args, **kwargs) -> None:
    _advanced.model(*args, **kwargs)


def load_shader(*args, **kwargs):
    return _advanced.load_shader(*args, **kwargs)


def create_shader(*args, **kwargs):
    return _advanced.create_shader(*args, **kwargs)


def shader(*args, **kwargs) -> None:
    _advanced.shader(*args, **kwargs)


def reset_shader(*args, **kwargs) -> None:
    _advanced.reset_shader(*args, **kwargs)


def load_sound(*args, **kwargs):
    return _advanced.load_sound(*args, **kwargs)


def create_audio(*args, **kwargs):
    return _advanced.create_audio(*args, **kwargs)


def create_video(*args, **kwargs):
    return _advanced.create_video(*args, **kwargs)


def create_capture(*args, **kwargs):
    return _advanced.create_capture(*args, **kwargs)


createDiv = create_div
createButton = create_button
loadXML = load_xml
loadTable = load_table
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
resetShader = reset_shader
loadSound = load_sound
createAudio = create_audio
createVideo = create_video
createCapture = create_capture

__all__ = [
    "COMPATIBILITY_MATRIX",
    "unsupported_feature",
    "create_div",
    "create_button",
    "select",
    "load_xml",
    "load_table",
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
    "load_model",
    "model",
    "load_shader",
    "create_shader",
    "shader",
    "reset_shader",
    "load_sound",
    "create_audio",
    "create_video",
    "create_capture",
    "createDiv",
    "createButton",
    "loadXML",
    "loadTable",
    "createCamera",
    "orbitControl",
    "ambientLight",
    "directionalLight",
    "pointLight",
    "normalMaterial",
    "ambientMaterial",
    "specularMaterial",
    "loadModel",
    "loadShader",
    "createShader",
    "resetShader",
    "loadSound",
    "createAudio",
    "createVideo",
    "createCapture",
]
