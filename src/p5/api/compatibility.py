"""Compatibility metadata and unsupported browser/data/advanced-media APIs."""

from __future__ import annotations

from enum import StrEnum

from p5.api import advanced as _advanced
from p5.exceptions import UnsupportedFeatureError


class CompatibilityStatus(StrEnum):
    """Support status values used by ``COMPATIBILITY_MATRIX``."""

    SUPPORTED = "supported"
    PARTIAL = "partial"
    DEFERRED = "deferred"
    EXCLUDED = "excluded"


COMPATIBILITY_MATRIX: dict[str, CompatibilityStatus] = {
    "lifecycle": CompatibilityStatus.SUPPORTED,
    "global_mode": CompatibilityStatus.SUPPORTED,
    "canvas": CompatibilityStatus.SUPPORTED,
    "2d_primitives": CompatibilityStatus.SUPPORTED,
    "paths_and_curves": CompatibilityStatus.PARTIAL,
    "color": CompatibilityStatus.SUPPORTED,
    "transforms": CompatibilityStatus.SUPPORTED,
    "mouse_keyboard_input": CompatibilityStatus.PARTIAL,
    "dom": CompatibilityStatus.EXCLUDED,
    "xml": CompatibilityStatus.EXCLUDED,
    "table": CompatibilityStatus.EXCLUDED,
    "webgl": CompatibilityStatus.PARTIAL,
    "webgl_renderer": CompatibilityStatus.PARTIAL,
    "3d_primitives": CompatibilityStatus.PARTIAL,
    "camera_projection": CompatibilityStatus.PARTIAL,
    "lights_materials": CompatibilityStatus.PARTIAL,
    "textures": CompatibilityStatus.PARTIAL,
    "models": CompatibilityStatus.PARTIAL,
    "shaders": CompatibilityStatus.PARTIAL,
    "sound": CompatibilityStatus.PARTIAL,
    "sound_playback": CompatibilityStatus.PARTIAL,
    "sound_analysis": CompatibilityStatus.DEFERRED,
    "sound_synthesis": CompatibilityStatus.DEFERRED,
    "media_playback": CompatibilityStatus.PARTIAL,
    "media_capture": CompatibilityStatus.PARTIAL,
    "math_data_environment": CompatibilityStatus.PARTIAL,
    "browser_url_storage": CompatibilityStatus.EXCLUDED,
    "device_sensors": CompatibilityStatus.DEFERRED,
    "accessibility_output": CompatibilityStatus.DEFERRED,
    "webgpu": CompatibilityStatus.DEFERRED,
    "strands_compute": CompatibilityStatus.EXCLUDED,
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


def _deferred_webgpu_api(name: str) -> None:
    unsupported_feature(
        name,
        "WebGPU, storage-buffer, and compute-style APIs are deferred until the Rust "
        "canvas runtime exposes a safe native GPU abstraction.",
    )


def _deferred_offscreen_api(name: str) -> None:
    unsupported_feature(
        name,
        "Offscreen graphics and framebuffer APIs are deferred until p5_canvas owns "
        "native render-target allocation, readback, resize, and cleanup semantics. "
        "See docs/technical/offscreen_graphics_framebuffer_design.md.",
    )


def _deferred_canvas_api(name: str) -> None:
    unsupported_feature(
        name,
        "This canvas API is deferred until p5_canvas exposes the required native "
        "path, clipping, tinting, or frame-export semantics.",
    )


def _deferred_advanced_3d_api(name: str) -> None:
    unsupported_feature(
        name,
        "This advanced WEBGL-style API is deferred until the native canvas runtime "
        "supports the corresponding 3D camera, debug, lighting, or material state. "
        "See docs/technical/advanced_3d_media_strategy.md.",
    )


def _deferred_sound_api(name: str) -> None:
    unsupported_feature(
        name,
        "Sound analysis, synthesis, and capture APIs are deferred pending a native "
        "Python audio backend decision. "
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


def select_all(*_args, **_kwargs) -> None:
    unsupported_feature("select_all", "DOM APIs are intentionally excluded.")


def remove_elements(*_args, **_kwargs) -> None:
    unsupported_feature("remove_elements", "DOM APIs are intentionally excluded.")


def create_input(*_args, **_kwargs) -> None:
    unsupported_feature("create_input", "DOM form APIs are intentionally excluded.")


def create_slider(*_args, **_kwargs) -> None:
    unsupported_feature("create_slider", "DOM form APIs are intentionally excluded.")


def create_checkbox(*_args, **_kwargs) -> None:
    unsupported_feature("create_checkbox", "DOM form APIs are intentionally excluded.")


def create_select(*_args, **_kwargs) -> None:
    unsupported_feature("create_select", "DOM form APIs are intentionally excluded.")


def create_radio(*_args, **_kwargs) -> None:
    unsupported_feature("create_radio", "DOM form APIs are intentionally excluded.")


def create_color_picker(*_args, **_kwargs) -> None:
    unsupported_feature(
        "create_color_picker",
        "DOM form APIs are intentionally excluded; use native Python UI libraries outside p5-py.",
    )


def create_file_input(*_args, **_kwargs) -> None:
    unsupported_feature(
        "create_file_input",
        "Browser file input APIs are intentionally excluded; use explicit local file paths.",
    )


def load_xml(*_args, **_kwargs) -> None:
    unsupported_feature("load_xml", "p5.XML is intentionally excluded.")


def load_table(*_args, **_kwargs) -> None:
    unsupported_feature(
        "load_table",
        "p5.Table and p5.TableRow are intentionally excluded.",
    )


def table_row(*_args, **_kwargs) -> None:
    unsupported_feature("table_row", "p5.TableRow is intentionally excluded.")


def create_blob(*_args, **_kwargs) -> None:
    unsupported_feature(
        "create_blob",
        "Browser Blob APIs are intentionally excluded; use bytes, pathlib, or io.BytesIO.",
    )


def save_blob(*_args, **_kwargs) -> None:
    unsupported_feature(
        "save_blob",
        "Browser Blob/client-side save APIs are intentionally excluded; use save_bytes().",
    )


def load_blob(*_args, **_kwargs) -> None:
    unsupported_feature(
        "load_blob",
        "Browser Blob APIs are intentionally excluded; use load_bytes().",
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


def device_shaken(*_args, **_kwargs) -> None:
    _deferred_sensor_api("device_shaken")


def previous_acceleration_x(*_args, **_kwargs) -> None:
    _deferred_sensor_api("previous_acceleration_x")


def previous_acceleration_y(*_args, **_kwargs) -> None:
    _deferred_sensor_api("previous_acceleration_y")


def previous_acceleration_z(*_args, **_kwargs) -> None:
    _deferred_sensor_api("previous_acceleration_z")


def previous_rotation_x(*_args, **_kwargs) -> None:
    _deferred_sensor_api("previous_rotation_x")


def previous_rotation_y(*_args, **_kwargs) -> None:
    _deferred_sensor_api("previous_rotation_y")


def previous_rotation_z(*_args, **_kwargs) -> None:
    _deferred_sensor_api("previous_rotation_z")


def request_pointer_lock(*_args, **_kwargs) -> None:
    unsupported_feature(
        "request_pointer_lock",
        "Browser pointer lock is intentionally excluded until a native cross-platform "
        "pointer-capture design exists.",
    )


def exit_pointer_lock(*_args, **_kwargs) -> None:
    unsupported_feature(
        "exit_pointer_lock",
        "Browser pointer lock is intentionally excluded until a native cross-platform "
        "pointer-capture design exists.",
    )


def begin_contour(*_args, **_kwargs) -> None:
    _deferred_canvas_api("begin_contour")


def end_contour(*_args, **_kwargs) -> None:
    _deferred_canvas_api("end_contour")


def begin_clip(*_args, **_kwargs) -> None:
    _deferred_canvas_api("begin_clip")


def clip(*_args, **_kwargs) -> None:
    _deferred_canvas_api("clip")


def end_clip(*_args, **_kwargs) -> None:
    _deferred_canvas_api("end_clip")


def tint(*_args, **_kwargs) -> None:
    _deferred_canvas_api("tint")


def no_tint(*_args, **_kwargs) -> None:
    _deferred_canvas_api("no_tint")


def save_frames(*_args, **_kwargs) -> None:
    _deferred_canvas_api("save_frames")


def save_gif(*_args, **_kwargs) -> None:
    _deferred_canvas_api("save_gif")


def normal(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("normal")


def vertex_property(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("vertex_property")


def text_to_points(*_args, **_kwargs) -> None:
    unsupported_feature(
        "text_to_points",
        "Font outline/path helpers are deferred until p5_canvas exposes deterministic "
        "native font shaping and contour data.",
    )


def text_to_paths(*_args, **_kwargs) -> None:
    unsupported_feature(
        "text_to_paths",
        "Font outline/path helpers are deferred until p5_canvas exposes deterministic "
        "native font shaping and contour data.",
    )


def text_to_contours(*_args, **_kwargs) -> None:
    unsupported_feature(
        "text_to_contours",
        "Font outline/path helpers are deferred until p5_canvas exposes deterministic "
        "native font shaping and contour data.",
    )


def text_to_model(*_args, **_kwargs) -> None:
    unsupported_feature(
        "text_to_model",
        "Font outline/path helpers are deferred until p5_canvas exposes deterministic "
        "native font shaping and contour data.",
    )


def create_graphics(*_args, **_kwargs) -> None:
    _deferred_offscreen_api("create_graphics")


def create_framebuffer(*_args, **_kwargs) -> None:
    _deferred_offscreen_api("create_framebuffer")


def drawing_context(*_args, **_kwargs) -> None:
    _deferred_offscreen_api("drawing_context")


def no_canvas(*_args, **_kwargs) -> None:
    unsupported_feature(
        "no_canvas",
        "p5-py currently requires a p5_canvas surface even for bounded/headless runs. "
        "A future no-presentation mode must still preserve SketchContext lifecycle and "
        "canvas-owned export/readback semantics. See "
        "docs/technical/offscreen_graphics_framebuffer_design.md.",
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


def frustum(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("frustum")


def set_camera(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("set_camera")


def roll(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("roll")


def screen_to_world(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("screen_to_world")


def world_to_screen(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("world_to_screen")


def debug_mode(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("debug_mode")


def no_debug_mode(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("no_debug_mode")


def ambient_light(*args, **kwargs) -> None:
    _advanced.ambient_light(*args, **kwargs)


def directional_light(*args, **kwargs) -> None:
    _advanced.directional_light(*args, **kwargs)


def point_light(*args, **kwargs) -> None:
    _advanced.point_light(*args, **kwargs)


def lights(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("lights")


def no_lights(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("no_lights")


def spot_light(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("spot_light")


def image_light(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("image_light")


def panorama(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("panorama")


def light_falloff(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("light_falloff")


def specular_color(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("specular_color")


def normal_material(*args, **kwargs) -> None:
    _advanced.normal_material(*args, **kwargs)


def ambient_material(*args, **kwargs) -> None:
    _advanced.ambient_material(*args, **kwargs)


def specular_material(*args, **kwargs) -> None:
    _advanced.specular_material(*args, **kwargs)


def shininess(*args, **kwargs) -> None:
    _advanced.shininess(*args, **kwargs)


def emissive_material(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("emissive_material")


def metalness(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("metalness")


def texture(*args, **kwargs) -> None:
    _advanced.texture(*args, **kwargs)


def texture_mode(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("texture_mode")


def texture_wrap(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("texture_wrap")


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


def build_geometry(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("build_geometry")


def free_geometry(*_args, **_kwargs) -> None:
    _deferred_advanced_3d_api("free_geometry")


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


def create_filter_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("create_filter_shader")


def filter_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("filter_shader")


def create_image_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("create_image_shader")


def create_stroke_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("create_stroke_shader")


def create_color_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("create_color_shader")


def create_material_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("create_material_shader")


def normal_shader(*_args, **_kwargs) -> None:
    _deferred_webgl_api("normal_shader")


def webgpu_context(*_args, **_kwargs) -> None:
    _deferred_webgpu_api("webgpu_context")


def create_storage_buffer(*_args, **_kwargs) -> None:
    _deferred_webgpu_api("create_storage_buffer")


def update_storage_buffer(*_args, **_kwargs) -> None:
    _deferred_webgpu_api("update_storage_buffer")


def read_storage_buffer(*_args, **_kwargs) -> None:
    _deferred_webgpu_api("read_storage_buffer")


def create_compute_shader(*_args, **_kwargs) -> None:
    _deferred_webgpu_api("create_compute_shader")


def dispatch_compute(*_args, **_kwargs) -> None:
    _deferred_webgpu_api("dispatch_compute")


def strands(*_args, **_kwargs) -> None:
    unsupported_feature(
        "strands",
        "p5.strands browser/WebGPU semantics are intentionally excluded unless a native "
        "Rust GPU abstraction is designed.",
    )


def load_sound(*args, **kwargs):
    return _advanced.load_sound(*args, **kwargs)


def create_audio(*args, **kwargs):
    return _advanced.create_audio(*args, **kwargs)


def create_video(*args, **kwargs):
    return _advanced.create_video(*args, **kwargs)


def create_capture(*args, **kwargs):
    return _advanced.create_capture(*args, **kwargs)


def create_amplitude(*_args, **_kwargs) -> None:
    _deferred_sound_api("create_amplitude")


def create_fft(*_args, **_kwargs) -> None:
    _deferred_sound_api("create_fft")


def create_audio_in(*_args, **_kwargs) -> None:
    _deferred_sound_api("create_audio_in")


def create_audio_input(*_args, **_kwargs) -> None:
    _deferred_sound_api("create_audio_input")


def create_oscillator(*_args, **_kwargs) -> None:
    _deferred_sound_api("create_oscillator")


def create_envelope(*_args, **_kwargs) -> None:
    _deferred_sound_api("create_envelope")


def create_sound_filter(*_args, **_kwargs) -> None:
    _deferred_sound_api("create_sound_filter")


def get_audio_context(*_args, **_kwargs) -> None:
    _deferred_sound_api("get_audio_context")


__all__ = [
    "CompatibilityStatus",
    "COMPATIBILITY_MATRIX",
    "unsupported_feature",
    "create_div",
    "create_button",
    "select",
    "select_all",
    "remove_elements",
    "create_input",
    "create_slider",
    "create_checkbox",
    "create_select",
    "create_radio",
    "create_color_picker",
    "create_file_input",
    "load_xml",
    "load_table",
    "table_row",
    "create_blob",
    "save_blob",
    "load_blob",
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
    "device_shaken",
    "previous_acceleration_x",
    "previous_acceleration_y",
    "previous_acceleration_z",
    "previous_rotation_x",
    "previous_rotation_y",
    "previous_rotation_z",
    "request_pointer_lock",
    "exit_pointer_lock",
    "begin_contour",
    "end_contour",
    "begin_clip",
    "clip",
    "end_clip",
    "tint",
    "no_tint",
    "save_frames",
    "save_gif",
    "normal",
    "vertex_property",
    "text_to_points",
    "text_to_paths",
    "text_to_contours",
    "text_to_model",
    "create_graphics",
    "create_framebuffer",
    "drawing_context",
    "no_canvas",
    "create_camera",
    "camera",
    "perspective",
    "ortho",
    "orbit_control",
    "frustum",
    "set_camera",
    "roll",
    "screen_to_world",
    "world_to_screen",
    "debug_mode",
    "no_debug_mode",
    "ambient_light",
    "directional_light",
    "point_light",
    "lights",
    "no_lights",
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
    "texture",
    "texture_mode",
    "texture_wrap",
    "plane",
    "box",
    "sphere",
    "ellipsoid",
    "cylinder",
    "cone",
    "torus",
    "create_model",
    "build_geometry",
    "free_geometry",
    "save_obj",
    "save_stl",
    "load_model",
    "model",
    "load_shader",
    "create_shader",
    "shader",
    "reset_shader",
    "create_filter_shader",
    "filter_shader",
    "create_image_shader",
    "create_stroke_shader",
    "create_color_shader",
    "create_material_shader",
    "normal_shader",
    "webgpu_context",
    "create_storage_buffer",
    "update_storage_buffer",
    "read_storage_buffer",
    "create_compute_shader",
    "dispatch_compute",
    "strands",
    "load_sound",
    "create_audio",
    "create_video",
    "create_capture",
    "create_amplitude",
    "create_fft",
    "create_audio_in",
    "create_audio_input",
    "create_oscillator",
    "create_envelope",
    "create_sound_filter",
    "get_audio_context",
]
