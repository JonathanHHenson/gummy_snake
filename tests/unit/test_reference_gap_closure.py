from __future__ import annotations

import inspect
import math
import re

import pytest

import gummysnake as gs
from gummysnake import UnsupportedFeatureError

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
    assert gs.abs_(-2) == 2
    assert gs.ceil(1.2) == 2
    assert gs.floor(1.8) == 1
    assert gs.sqrt(9) == 3
    assert gs.pow_(2, 3) == 8
    assert gs.round_(1.234, 2) == 1.23
    assert gs.boolean("false") is False
    assert gs.byte(257) == 1
    assert gs.char(65) == "A"
    assert gs.float_("1.5") == 1.5
    assert gs.hex_(15, 2) == "0F"
    assert gs.int_("10") == 10
    assert gs.str_(10) == "10"
    assert gs.unchar("A") == 65
    assert gs.unhex("0F") == 15
    assert gs.nf(7, 3) == "007"
    assert gs.nfc(1234.5, 1) == "1,234.5"
    assert gs.nfp(7, 2) == "+07"
    assert gs.nfs(7, 2) == " 07"
    assert gs.split_tokens("a, b c") == ["a", "b", "c"]
    assert sorted(gs.shuffle([1, 2, 3])) == [1, 2, 3]

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


def test_environment_helpers_and_explicit_browser_sensor_exclusions():
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

    for helper in (gs.get_url, gs.get_url_path, gs.get_url_params, gs.local_storage):
        with pytest.raises(UnsupportedFeatureError):
            helper()

    for helper in (gs.acceleration_x, gs.rotation_z, gs.orientation_y, gs.device_moved):
        with pytest.raises(UnsupportedFeatureError):
            helper()


def test_offscreen_graphics_and_no_canvas_are_explicitly_deferred():
    for helper in (gs.create_graphics, gs.create_framebuffer):
        with pytest.raises(UnsupportedFeatureError, match="offscreen_graphics_framebuffer_design"):
            helper(16, 16)

    with pytest.raises(UnsupportedFeatureError, match="gummy_canvas surface"):
        gs.no_canvas()


def test_advanced_3d_gap_apis_are_explicitly_deferred():
    deferred_helpers = (
        gs.frustum,
        gs.set_camera,
        gs.roll,
        gs.screen_to_world,
        gs.world_to_screen,
        gs.debug_mode,
        gs.no_debug_mode,
        gs.lights,
        gs.no_lights,
        gs.spot_light,
        gs.image_light,
        gs.panorama,
        gs.light_falloff,
        gs.specular_color,
        gs.emissive_material,
        gs.metalness,
        gs.texture_mode,
        gs.texture_wrap,
    )

    for helper in deferred_helpers:
        with pytest.raises(UnsupportedFeatureError, match="advanced WEBGL-style API"):
            helper()


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
