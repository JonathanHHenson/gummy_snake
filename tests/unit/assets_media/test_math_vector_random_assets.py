import math
import random as py_random
import runpy
from pathlib import Path

import pytest

import gummysnake as gs


def test_math_helpers_and_angle_mode():
    assert gs.map_value(5, 0, 10, 0, 100) == 50
    assert gs.map_value(15, 0, 10, 0, 100, True) == 100
    assert gs.constrain(-1, 0, 10) == 0
    assert gs.norm(5, 0, 10) == 0.5
    assert gs.lerp(10, 20, 0.25) == 12.5
    assert gs.dist(0, 0, 3, 4) == 5
    assert gs.mag(2, 3, 6) == 7

    def setup():
        gs.create_canvas(1, 1)
        gs.angle_mode(gs.DEGREES)

    def draw():
        assert gs.cos(60) == pytest.approx(0.5)
        assert gs.atan2(1, 0) == pytest.approx(90)

    gs.run(setup=setup, draw=draw, headless=True, max_frames=1)


def test_pythonic_math_helpers_and_removed_legacy_easy_names():
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


def test_vector_instance_and_static_helpers():
    vector = gs.create_vector(3, 4)
    assert vector.mag() == 5
    assert vector.copy().normalize().mag() == pytest.approx(1)
    assert vector.copy().limit(2).mag() == pytest.approx(2)
    assert vector.copy().set_heading(0) == gs.Vector(5, 0, 0)
    assert vector.angle_between((0, 4)) == pytest.approx(36.86989764584401)
    assert gs.Vector.angle_between((1, 0), (0, 1)) == pytest.approx(90)
    assert gs.Vector().angle_between((1, 0)) == 0
    vector.set_value("z", 9).set_value(-1, 6)
    assert vector.get_value("z") == 6
    assert vector[-1] == 6
    assert vector.to_string() == "[3, 4, 6]"
    assert str(vector) == "[3, 4, 6]"
    vector = gs.create_vector(3, 4)
    assert vector + gs.Vector(1, 2, 3) == gs.Vector(4, 6, 3)
    assert vector.copy().add((1, 1, 1)) == gs.Vector(4, 5, 1)
    assert gs.Vector.add((1, 2), (3, 4)) == gs.Vector(4, 6, 0)
    assert gs.Vector.dot((1, 2, 3), (4, 5, 6)) == 32
    assert gs.Vector.cross((1, 0, 0), (0, 1, 0)) == gs.Vector(0, 0, 1)
    assert gs.Vector.lerp((0, 0, 0), (10, 20, 30), 0.5) == gs.Vector(5, 10, 15)
    assert abs(gs.Vector(3, 4)) == 5
    assert gs.Vector(3, 4).normalized().tuple() == pytest.approx((0.6, 0.8, 0.0))
    assert gs.Vector(3, 4) @ gs.Vector(2, 0) == 6
    assert round(gs.Vector(1.234, 5.678), 1).tuple() == (1.2, 5.7, 0.0)
    assert (10 - gs.Vector(1, 2, 3)).tuple() == (9.0, 8.0, 7.0)


def test_vector_indexing_and_additional_operations():
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


def test_spline_helpers_draw_and_measure():
    def setup():
        gs.create_canvas(20, 20)
        gs.spline_property("tightness", 0)
        assert gs.spline_point(0, 10, 20, 30, 0) == pytest.approx(10)
        assert gs.spline_point(0, 10, 20, 30, 1) == pytest.approx(20)
        assert gs.spline_tangent(0, 10, 20, 30, 0.5) == pytest.approx(10)
        gs.no_fill()
        gs.stroke(255)
        gs.begin_shape()
        gs.vertex(2, 10)
        gs.spline_vertex(8, 2)
        gs.spline_vertex(14, 10)
        gs.end_shape()

    context = gs.run(setup=setup, headless=True, max_frames=0)
    assert any(value != 0 for value in context.load_pixels())


def test_random_and_noise_are_seedable():
    gs.random_seed(123)
    first = [gs.random(), gs.random(10), gs.random(-1, 1), gs.random(["a", "b", "c"])]
    gs.random_seed(123)
    second = [gs.random(), gs.random(10), gs.random(-1, 1), gs.random(["a", "b", "c"])]
    assert first == second

    gs.noise_seed(42)
    gs.noise_detail(3, 0.4)
    assert 0 <= gs.noise(0.1, 0.2, 0.3) <= 1
    sample = gs.noise(0.5, 0.25)
    gs.noise_seed(42)
    assert gs.noise(0.5, 0.25) == sample


def test_random_seed_controls_all_gummy_snake_random_helpers_without_stdlib_mutation():
    gs.random_seed(321)
    first = (
        gs.random(),
        gs.random_gaussian(),
        gs.shuffle([1, 2, 3, 4]),
        gs.Vector.random_2d().tuple(),
        gs.Vector.random_3d().tuple(),
    )
    gs.random_seed(321)
    second = (
        gs.random(),
        gs.random_gaussian(),
        gs.shuffle([1, 2, 3, 4]),
        gs.Vector.random_2d().tuple(),
        gs.Vector.random_3d().tuple(),
    )
    assert first == second

    py_random.seed(2468)
    expected = [py_random.random() for _ in range(3)]
    py_random.seed(2468)
    gs.random_seed(999)
    gs.random()
    gs.shuffle([1, 2, 3, 4])
    gs.Vector.random_2d()
    assert [py_random.random() for _ in range(3)] == expected


def test_data_helpers_round_trip(tmp_path: Path):
    strings_path = tmp_path / "lines.txt"
    json_path = tmp_path / "data.json"
    bytes_path = tmp_path / "data.bin"
    writer_path = tmp_path / "writer.txt"

    gs.save_strings(["alpha", "beta"], strings_path)
    assert gs.load_strings(strings_path) == ["alpha", "beta"]

    gs.save_json({"answer": 42}, json_path)
    assert gs.load_json(json_path) == {"answer": 42}

    gs.save_bytes([0, 1, 255], bytes_path)
    assert gs.load_bytes(bytes_path) == b"\x00\x01\xff"

    with gs.create_writer(writer_path) as writer:
        writer.write("alpha")
        writer.print(" beta")
    assert writer_path.read_text(encoding="utf-8") == "alpha beta\n"


def test_load_image_resolves_relative_to_calling_script(tmp_path: Path, monkeypatch):
    sketch_dir = tmp_path / "sketch"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)

    asset = gs.create_image(2, 2)
    asset.set(0, 0, gs.Color(255, 0, 0))
    asset_path = assets_dir / "sprite.png"
    asset.save(asset_path)

    script_path = sketch_dir / "main.py"
    script_path.write_text(
        "import gummysnake as gs\n\nIMAGE = gs.load_image('assets/sprite.png')\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    namespace = runpy.run_path(str(script_path))

    loaded = namespace["IMAGE"]
    assert loaded.width == 2
    assert loaded.get(0, 0) == gs.Color(255, 0, 0, 255)


def test_image_manipulation_and_drawing_with_text(tmp_path: Path):
    asset = gs.create_image(4, 4)
    asset.set(0, 0, gs.Color(255, 0, 0))
    assert asset.get(0, 0) == gs.Color(255, 0, 0, 255)
    assert asset[0, 0] == gs.Color(255, 0, 0, 255)
    asset[1, 1] = gs.Color(0, 255, 0)
    assert asset.get(1, 1) == gs.Color(0, 255, 0, 255)
    region = asset.get(0, 0, 2, 2)
    assert isinstance(region, gs.Image)
    assert region.width == 2
    indexed_region = asset[0:2, 0:2]
    assert isinstance(indexed_region, gs.Image)
    assert indexed_region.width == 2
    asset.resize(8, 0)
    assert asset.width == 8
    assert asset.height == 8
    asset.filter(gs.INVERT)

    asset_path = tmp_path / "asset.png"
    asset.save(asset_path)
    loaded = gs.load_image(asset_path)
    assert loaded.width == 8

    def setup():
        gs.create_canvas(32, 32)
        gs.background(255)
        gs.fill(0)
        gs.text_size(12)

    def draw():
        gs.image(loaded, 0, 0, 8, 8)
        gs.text("Hi", 10, 20)
        assert gs.text_width("Hi") > 0
        assert gs.text_ascent() > 0
        assert gs.text_descent() >= 0
        bounds = gs.text_bounds("Hi", 10, 20)
        assert bounds["width"] > 0
        assert gs.font_width("Hi") == pytest.approx(bounds["width"])
        assert gs.font_ascent() == pytest.approx(gs.text_ascent())
        assert gs.font_descent() == pytest.approx(gs.text_descent())
        assert gs.font_bounds("Hi", 10, 20)["height"] == pytest.approx(bounds["height"])
        assert gs.text_direction("rtl") == "rtl"
        assert gs.text_wrap("char") == "char"
        assert gs.text_weight(700) == 700
        assert gs.text_property("direction") == "rtl"
        assert gs.text_properties()["wrap"] == "char"

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    assert len(set(context.load_pixels())) > 1
