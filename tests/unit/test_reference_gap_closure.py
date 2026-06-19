from __future__ import annotations

import inspect
import math
import re
import tomllib
from pathlib import Path

import pytest

import p5
from p5 import UnsupportedFeatureError

_ALLOWED_STATUSES = {
    "supported",
    "partial",
    "pythonic_equivalent",
    "deferred",
    "excluded",
    "not_applicable",
}
_SNAKE_CASE_RE = re.compile(r"^[a-z_][a-z0-9_]*$|^[A-Z][A-Za-z0-9_]*$")


def test_reference_compatibility_inventory_tracks_public_exports():
    inventory_path = Path("docs/technical/reference_compatibility_inventory.toml")
    inventory = tomllib.loads(inventory_path.read_text(encoding="utf-8"))

    assert inventory["metadata"]["policy_doc"] == "docs/technical/reference_gap_closure.md"
    for entry in inventory["entry"]:
        assert entry["status"] in _ALLOWED_STATUSES
        assert entry["reference"]
        assert entry["module"]
        assert "notes" in entry
        for public_name in entry["p5_py"]:
            assert hasattr(p5, public_name), public_name
            assert public_name in p5.__all__, public_name


def test_public_function_exports_remain_snake_case_only():
    for name in p5.__all__:
        value = getattr(p5, name)
        if inspect.isfunction(value):
            assert _SNAKE_CASE_RE.fullmatch(name), name
            assert not any(
                char.islower() and next_char.isupper()
                for char, next_char in zip(name, name[1:], strict=False)
            )


def test_color_gap_helpers_and_immutable_mutators():
    color = p5.Color(128, 64, 32, 200)
    assert p5.red(color) == 128
    assert p5.green(color) == 64
    assert p5.blue(color) == 32
    assert p5.alpha(color) == 200
    assert p5.hue(p5.Color(255, 0, 0)) == pytest.approx(0)
    assert p5.saturation(p5.Color(255, 0, 0)) == pytest.approx(100)
    assert p5.brightness(p5.Color(255, 0, 0)) == pytest.approx(100)
    assert p5.lightness(p5.Color(255, 0, 0)) == pytest.approx(50)
    assert color.with_alpha(10) == p5.Color(128, 64, 32, 10)
    assert color.with_red(1).with_green(2).with_blue(3) == p5.Color(1, 2, 3, 200)
    assert p5.Color(255, 255, 255).contrast_ratio(p5.Color(0, 0, 0)) == pytest.approx(21)
    assert p5.Color(255, 0, 16, 128).to_hex(include_alpha=True) == "#ff001080"
    assert p5.palette_lerp([p5.Color(0, 0, 0), p5.Color(100, 0, 0)], 0.5) == p5.Color(50, 0, 0)


def test_math_data_and_vector_gap_helpers():
    assert p5.abs_(-2) == 2
    assert p5.ceil(1.2) == 2
    assert p5.floor(1.8) == 1
    assert p5.sqrt(9) == 3
    assert p5.pow_(2, 3) == 8
    assert p5.round_(1.234, 2) == 1.23
    assert p5.boolean("false") is False
    assert p5.byte(257) == 1
    assert p5.char(65) == "A"
    assert p5.float_("1.5") == 1.5
    assert p5.hex_(15, 2) == "0F"
    assert p5.int_("10") == 10
    assert p5.str_(10) == "10"
    assert p5.unchar("A") == 65
    assert p5.unhex("0F") == 15
    assert p5.nf(7, 3) == "007"
    assert p5.nfc(1234.5, 1) == "1,234.5"
    assert p5.nfp(7, 2) == "+07"
    assert p5.nfs(7, 2) == " 07"
    assert p5.split_tokens("a, b c") == ["a", "b", "c"]
    assert sorted(p5.shuffle([1, 2, 3])) == [1, 2, 3]

    vector = p5.Vector(1, 2, 3)
    assert vector[0] == 1
    vector[1] = 4
    assert vector == p5.Vector(1, 4, 3)
    assert vector.set_value("x", 2).get_value("x") == 2
    assert vector.to_string() == "[2, 4, 3]"
    angle = p5.Vector(1, 0).angle_between((0, 1))
    assert math.isclose(angle, math.pi / 2) or math.isclose(angle, 90)
    assert (p5.Vector(5, 5, 5) % 2) == p5.Vector(1, 1, 1)
    assert p5.Vector(1e-13, 2, 0).clamp_to_zero() == p5.Vector(0, 2, 0)
    assert p5.Vector(1, -1, 0).reflect((0, 1, 0)) == p5.Vector(1, 1, 0)
    assert p5.Vector.slerp((1, 0, 0), (0, 1, 0), 0.5).mag() == pytest.approx(1)
    assert p5.Vector.random_2d().mag() == pytest.approx(1)
    assert p5.Vector.random_3d().mag() == pytest.approx(1)


def test_environment_helpers_and_explicit_browser_sensor_exclusions():
    def setup():
        p5.create_canvas(10, 12)
        p5.frame_rate(24)

    def draw():
        assert p5.get_target_frame_rate() == 24
        assert p5.window_width() == 10
        assert p5.window_height() == 12
        assert p5.display_width() >= 10
        assert p5.display_height() >= 12
        assert p5.focused() is True
        p5.cursor()
        p5.no_cursor()

    p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

    for helper in (p5.get_url, p5.get_url_path, p5.get_url_params, p5.local_storage):
        with pytest.raises(UnsupportedFeatureError):
            helper()

    for helper in (p5.acceleration_x, p5.rotation_z, p5.orientation_y, p5.device_moved):
        with pytest.raises(UnsupportedFeatureError):
            helper()


def test_accessibility_helpers_store_native_metadata():
    def setup():
        p5.create_canvas(10, 10)
        assert p5.describe("A test canvas") == {
            "label": "canvas",
            "description": "A test canvas",
        }
        assert p5.describe_element("circle", "A small circle") == {
            "label": "circle",
            "description": "A small circle",
        }

    context = p5.run(setup=setup, headless=True, max_frames=0)
    assert context.text_output() == [
        {"label": "canvas", "description": "A test canvas"},
        {"label": "circle", "description": "A small circle"},
    ]
    assert context.grid_output() == context.text_output()
