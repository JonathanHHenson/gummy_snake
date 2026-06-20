from __future__ import annotations

import inspect
import math
import re

import pytest

import gummysnake as gs

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


def test_color_gap_helpers_and_immutable_mutators():
    color = gs.Color(128, 64, 32, 200)
    assert gs.red(color) == 128
    assert gs.green(color) == 64
    assert gs.blue(color) == 32
    assert gs.alpha(color) == 200
    assert gs.hue(gs.Color(255, 0, 0)) == pytest.approx(0)
    assert gs.saturation(gs.Color(255, 0, 0)) == pytest.approx(100)
    assert gs.brightness(gs.Color(255, 0, 0)) == pytest.approx(100)
    assert gs.lightness(gs.Color(255, 0, 0)) == pytest.approx(50)
    assert color.with_alpha(10) == gs.Color(128, 64, 32, 10)
    assert color.with_red(1).with_green(2).with_blue(3) == gs.Color(1, 2, 3, 200)
    assert gs.Color(255, 255, 255).contrast_ratio(gs.Color(0, 0, 0)) == pytest.approx(21)
    assert gs.Color(255, 0, 16, 128).to_hex(include_alpha=True) == "#ff001080"
    assert gs.palette_lerp([gs.Color(0, 0, 0), gs.Color(100, 0, 0)], 0.5) == gs.Color(50, 0, 0)


def test_math_data_and_vector_gap_helpers():
    assert gs.sq(3) == 9
    assert gs.fract(1.25) == 0.25
    assert sorted(gs.shuffle([1, 2, 3])) == [1, 2, 3]

    legacy_easy_python_names = {
        "abs_",
        "ceil",
        "floor",
        "sqrt",
        "pow_",
        "round_",
        "exp",
        "log",
        "boolean",
        "byte",
        "char",
        "float_",
        "hex_",
        "int_",
        "str_",
        "unchar",
        "unhex",
        "nf",
        "nfc",
        "nfp",
        "nfs",
        "split_tokens",
        "day",
        "month",
        "year",
        "hour",
        "minute",
        "second",
    }
    assert legacy_easy_python_names.isdisjoint(gs.__all__)
    assert not any(hasattr(gs, name) for name in legacy_easy_python_names)

    vector = gs.Vector(1, 2, 3)
    assert vector[0] == 1
    vector[1] = 4
    assert vector == gs.Vector(1, 4, 3)
    assert vector.set_value("x", 2).get_value("x") == 2
    assert vector.to_string() == "[2, 4, 3]"
    angle = gs.Vector(1, 0).angle_between((0, 1))
    assert math.isclose(angle, math.pi / 2) or math.isclose(angle, 90)
    assert (gs.Vector(5, 5, 5) % 2) == gs.Vector(1, 1, 1)
    assert gs.Vector(1e-13, 2, 0).clamp_to_zero() == gs.Vector(0, 2, 0)
    assert gs.Vector(1, -1, 0).reflect((0, 1, 0)) == gs.Vector(1, 1, 0)
    assert gs.Vector.slerp((1, 0, 0), (0, 1, 0), 0.5).mag() == pytest.approx(1)
    assert gs.Vector.random_2d().mag() == pytest.approx(1)
    assert gs.Vector.random_3d().mag() == pytest.approx(1)


def test_environment_helpers():
    def setup():
        gs.create_canvas(10, 12)
        gs.frame_rate(24)

    def draw():
        assert gs.get_target_frame_rate() == 24
        assert gs.window_width() == 10
        assert gs.window_height() == 12
        assert gs.display_width() >= 10
        assert gs.display_height() >= 12
        assert gs.focused() is True
        gs.cursor()
        gs.no_cursor()

    gs.run(setup=setup, draw=draw, headless=True, max_frames=1)


def test_removed_compatibility_exports_are_absent():
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
    }

    for name in removed_names:
        assert not hasattr(gs, name), name
        assert name not in gs.__all__


def test_accessibility_helpers_store_native_metadata():
    def setup():
        gs.create_canvas(10, 10)
        assert gs.describe("A test canvas") == {
            "label": "canvas",
            "description": "A test canvas",
        }
        assert gs.describe_element("circle", "A small circle") == {
            "label": "circle",
            "description": "A small circle",
        }

    context = gs.run(setup=setup, headless=True, max_frames=0)
    assert context.text_output() == [
        {"label": "canvas", "description": "A test canvas"},
        {"label": "circle", "description": "A small circle"},
    ]
    assert context.grid_output() == context.text_output()
