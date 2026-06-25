from __future__ import annotations

import inspect
import re

import gummysnake as gs
import gummysnake.api.global_mode as global_mode
from gummysnake.assets.image import ops as image_ops
from gummysnake.drawing.software3d import transform_model
from gummysnake.events.input_state import (
    InputState,
    KeyboardEvent,
    MouseEvent,
    TouchEvent,
    TouchPoint,
)

_SNAKE_CASE_RE = re.compile(r"^[a-z_][a-z0-9_]*$|^[A-Z][A-Za-z0-9_]*$")


def test_public_function_exports_remain_snake_case_only():
    for name in gs.__all__:
        value = getattr(gs, name)
        if inspect.isfunction(value):
            assert _SNAKE_CASE_RE.fullmatch(name), name
            assert not any(
                char.islower() and next_char.isupper()
                for char, next_char in zip(name, name[1:], strict=False)
            )


def test_global_mode_all_exports_are_importable():
    assert "text_batch" in global_mode.__all__
    assert "text_widths" in global_mode.__all__
    for name in global_mode.__all__:
        assert hasattr(global_mode, name), name


def test_cleanup_sensitive_compatibility_imports_remain_available():
    assert callable(image_ops.resize_rgba)
    assert callable(transform_model)
    assert InputState is not None
    assert MouseEvent is not None
    assert KeyboardEvent is not None
    assert TouchPoint is not None
    assert TouchEvent is not None


def test_removed_browser_and_p5_exports_are_absent():
    removed_names = {
        "COMPATIBILITY_MATRIX",
        "CompatibilityStatus",
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
        "rotation_z",
        "orientation_y",
        "device_moved",
        "create_graphics",
        "create_framebuffer",
        "no_canvas",
        "frustum",
        "set_camera",
        "roll",
        "screen_to_world",
        "world_to_screen",
        "debug_mode",
        "no_debug_mode",
        "lights",
        "no_lights",
        "spot_light",
        "image_light",
        "panorama",
        "light_falloff",
        "specular_color",
        "emissive_material",
        "metalness",
        "texture_mode",
        "texture_wrap",
        "webgpu_context",
        "create_compute_shader",
        "create_audio_in",
        "amplitude",
        "create_amplitude",
        "fft",
        "create_fft",
        "waveform",
        "spectrum",
        "create_oscillator",
        "create_envelope",
        "create_filter",
        "get_audio_context",
        "set_attributes",
        "webgl_version",
        "clear_depth",
        "drawing_context",
        "create_storage_buffer",
        "update_storage_buffer",
        "read_storage_buffer",
        "dispatch_compute",
        "set_move_threshold",
        "set_shake_threshold",
        "device_turned",
        "device_shaken",
        "normal",
        "vertex_property",
        "build_geometry",
        "free_geometry",
        "flip_u",
        "flip_v",
    }

    for name in removed_names:
        assert not hasattr(gs, name), name
        assert name not in gs.__all__
