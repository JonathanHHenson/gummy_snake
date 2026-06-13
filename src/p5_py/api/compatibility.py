"""Compatibility metadata and unsupported browser/data/advanced-media APIs."""

from __future__ import annotations

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
    "webgl": "deferred",
    "webgl_renderer": "deferred",
    "3d_primitives": "deferred",
    "camera_projection": "deferred",
    "lights_materials": "deferred",
    "textures": "deferred",
    "models": "deferred",
    "shaders": "deferred",
    "sound": "deferred",
    "sound_playback": "deferred",
    "sound_analysis": "deferred",
    "sound_synthesis": "deferred",
    "media_playback": "deferred",
    "media_capture": "deferred",
}


def unsupported_feature(name: str, reason: str) -> None:
    raise UnsupportedFeatureError(f"{name} is not supported by p5-py. {reason}")


def _deferred_webgl_api(name: str) -> None:
    unsupported_feature(
        name,
        "WEBGL-like 3D rendering is deferred pending a native Python renderer. "
        "See docs/advanced_3d_media_strategy.md.",
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


def create_camera(*_args, **_kwargs) -> None:
    _deferred_webgl_api("create_camera/createCamera")


def camera(*_args, **_kwargs) -> None:
    _deferred_webgl_api("camera")


def perspective(*_args, **_kwargs) -> None:
    _deferred_webgl_api("perspective")


def ortho(*_args, **_kwargs) -> None:
    _deferred_webgl_api("ortho")


def orbit_control(*_args, **_kwargs) -> None:
    _deferred_webgl_api("orbit_control/orbitControl")


def ambient_light(*_args, **_kwargs) -> None:
    _deferred_webgl_api("ambient_light/ambientLight")


def directional_light(*_args, **_kwargs) -> None:
    _deferred_webgl_api("directional_light/directionalLight")


def point_light(*_args, **_kwargs) -> None:
    _deferred_webgl_api("point_light/pointLight")


def normal_material(*_args, **_kwargs) -> None:
    _deferred_webgl_api("normal_material/normalMaterial")


def ambient_material(*_args, **_kwargs) -> None:
    _deferred_webgl_api("ambient_material/ambientMaterial")


def specular_material(*_args, **_kwargs) -> None:
    _deferred_webgl_api("specular_material/specularMaterial")


def shininess(*_args, **_kwargs) -> None:
    _deferred_webgl_api("shininess")


def texture(*_args, **_kwargs) -> None:
    _deferred_webgl_api("texture")


def plane(*_args, **_kwargs) -> None:
    _deferred_webgl_api("plane")


def box(*_args, **_kwargs) -> None:
    _deferred_webgl_api("box")


def sphere(*_args, **_kwargs) -> None:
    _deferred_webgl_api("sphere")


def load_model(*_args, **_kwargs) -> None:
    _deferred_webgl_api("load_model/loadModel")


def model(*_args, **_kwargs) -> None:
    _deferred_webgl_api("model")


def load_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("load_shader/loadShader")


def create_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("create_shader/createShader")


def shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("shader")


def reset_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("reset_shader/resetShader")


def load_sound(*_args, **_kwargs) -> None:
    _deferred_sound_api("load_sound/loadSound")


def create_audio(*_args, **_kwargs) -> None:
    _deferred_media_api("create_audio/createAudio")


def create_video(*_args, **_kwargs) -> None:
    _deferred_media_api("create_video/createVideo")


def create_capture(*_args, **_kwargs) -> None:
    _deferred_media_api("create_capture/createCapture")


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
