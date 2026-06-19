"""Compatibility metadata and unsupported browser/data/advanced-media APIs."""

from __future__ import annotations

from p5.api import advanced as _advanced
from p5.exceptions import UnsupportedFeatureError

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
    "math_data_environment": "partial",
    "browser_url_storage": "excluded",
    "device_sensors": "deferred",
    "accessibility_output": "deferred",
    "webgpu": "deferred",
    "strands_compute": "excluded",
}


def unsupported_feature(name: str, reason: str) -> None:
    raise UnsupportedFeatureError(f"{name} is not supported by p5-py. {reason}")


def _deferred_webgl_api(name: str) -> None:
    unsupported_feature(
        name,
        "This WEBGL-style API is deferred on the current software 3D path. "
        "See docs/technical/advanced_3d_media_strategy.md for the supported slice "
        "and native-renderer follow-on work.",
    )


def _deferred_sound_api(name: str) -> None:
    unsupported_feature(
        name,
        "Sound APIs are deferred pending a native Python audio backend decision. "
        "See docs/technical/advanced_3d_media_strategy.md.",
    )


def _deferred_media_api(name: str) -> None:
    unsupported_feature(
        name,
        "Native media playback/capture APIs are deferred because they have platform, "
        "privacy, and dependency implications outside the browser. "
        "See docs/technical/advanced_3d_media_strategy.md.",
    )


def create_div(*_args, **_kwargs) -> None:
    unsupported_feature("create_div", "DOM APIs are intentionally excluded.")


def create_button(*_args, **_kwargs) -> None:
    unsupported_feature("create_button", "DOM APIs are intentionally excluded.")


def select(*_args, **_kwargs) -> None:
    unsupported_feature("select", "DOM APIs are intentionally excluded.")


def load_xml(*_args, **_kwargs) -> None:
    unsupported_feature("load_xml", "p5.XML is intentionally excluded.")


def load_table(*_args, **_kwargs) -> None:
    unsupported_feature(
        "load_table",
        "p5.Table and p5.TableRow are intentionally excluded.",
    )


def get_url(*_args, **_kwargs) -> None:
    unsupported_feature("get_url", "Browser URL APIs are intentionally excluded; use urllib.parse.")


def get_url_path(*_args, **_kwargs) -> None:
    unsupported_feature(
        "get_url_path", "Browser URL APIs are intentionally excluded; use urllib.parse."
    )


def get_url_params(*_args, **_kwargs) -> None:
    unsupported_feature(
        "get_url_params", "Browser URL APIs are intentionally excluded; use urllib.parse."
    )


def local_storage(*_args, **_kwargs) -> None:
    unsupported_feature(
        "local_storage",
        "Browser localStorage is intentionally excluded; use explicit local files or a database.",
    )


def _deferred_sensor_api(name: str) -> None:
    unsupported_feature(
        name,
        "Device acceleration/orientation APIs are deferred until p5-py has a native "
        "sensor provider.",
    )


def acceleration_x(*_args, **_kwargs) -> None:
    _deferred_sensor_api("acceleration_x")


def acceleration_y(*_args, **_kwargs) -> None:
    _deferred_sensor_api("acceleration_y")


def acceleration_z(*_args, **_kwargs) -> None:
    _deferred_sensor_api("acceleration_z")


def rotation_x(*_args, **_kwargs) -> None:
    _deferred_sensor_api("rotation_x")


def rotation_y(*_args, **_kwargs) -> None:
    _deferred_sensor_api("rotation_y")


def rotation_z(*_args, **_kwargs) -> None:
    _deferred_sensor_api("rotation_z")


def orientation_x(*_args, **_kwargs) -> None:
    _deferred_sensor_api("orientation_x")


def orientation_y(*_args, **_kwargs) -> None:
    _deferred_sensor_api("orientation_y")


def orientation_z(*_args, **_kwargs) -> None:
    _deferred_sensor_api("orientation_z")


def device_moved(*_args, **_kwargs) -> None:
    _deferred_sensor_api("device_moved")


def device_turned(*_args, **_kwargs) -> None:
    _deferred_sensor_api("device_turned")


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


def ellipsoid(*args, **kwargs) -> None:
    _advanced.ellipsoid(*args, **kwargs)


def cylinder(*args, **kwargs) -> None:
    _advanced.cylinder(*args, **kwargs)


def cone(*args, **kwargs) -> None:
    _advanced.cone(*args, **kwargs)


def torus(*args, **kwargs) -> None:
    _advanced.torus(*args, **kwargs)


def create_model(*args, **kwargs):
    return _advanced.create_model(*args, **kwargs)


def save_obj(*args, **kwargs):
    return _advanced.save_obj(*args, **kwargs)


def save_stl(*args, **kwargs):
    return _advanced.save_stl(*args, **kwargs)


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


__all__ = [
    "COMPATIBILITY_MATRIX",
    "unsupported_feature",
    "create_div",
    "create_button",
    "select",
    "load_xml",
    "load_table",
    "get_url",
    "get_url_path",
    "get_url_params",
    "local_storage",
    "acceleration_x",
    "acceleration_y",
    "acceleration_z",
    "rotation_x",
    "rotation_y",
    "rotation_z",
    "orientation_x",
    "orientation_y",
    "orientation_z",
    "device_moved",
    "device_turned",
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
    "save_obj",
    "save_stl",
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
]
