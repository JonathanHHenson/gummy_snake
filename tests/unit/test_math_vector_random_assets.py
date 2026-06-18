from pathlib import Path

import pytest

import p5


def test_math_helpers_and_angle_mode():
    assert p5.map_value(5, 0, 10, 0, 100) == 50
    assert p5.map_value(15, 0, 10, 0, 100, True) == 100
    assert p5.constrain(-1, 0, 10) == 0
    assert p5.norm(5, 0, 10) == 0.5
    assert p5.lerp(10, 20, 0.25) == 12.5
    assert p5.dist(0, 0, 3, 4) == 5
    assert p5.mag(2, 3, 6) == 7

    def setup():
        p5.create_canvas(1, 1)
        p5.angle_mode(p5.DEGREES)

    def draw():
        assert p5.cos(60) == pytest.approx(0.5)
        assert p5.atan2(1, 0) == pytest.approx(90)

    p5.run(setup=setup, draw=draw, headless=True, max_frames=1)


def test_vector_instance_and_static_helpers():
    vector = p5.create_vector(3, 4)
    assert vector.mag() == 5
    assert vector.copy().normalize().mag() == pytest.approx(1)
    assert vector.copy().limit(2).mag() == pytest.approx(2)
    assert vector + p5.Vector(1, 2, 3) == p5.Vector(4, 6, 3)
    assert vector.copy().add((1, 1, 1)) == p5.Vector(4, 5, 1)
    assert p5.Vector.add((1, 2), (3, 4)) == p5.Vector(4, 6, 0)
    assert p5.Vector.dot((1, 2, 3), (4, 5, 6)) == 32
    assert p5.Vector.cross((1, 0, 0), (0, 1, 0)) == p5.Vector(0, 0, 1)
    assert p5.Vector.lerp((0, 0, 0), (10, 20, 30), 0.5) == p5.Vector(5, 10, 15)


def test_random_and_noise_are_seedable():
    p5.random_seed(123)
    first = [p5.random(), p5.random(10), p5.random(-1, 1), p5.random(["a", "b", "c"])]
    p5.random_seed(123)
    second = [p5.random(), p5.random(10), p5.random(-1, 1), p5.random(["a", "b", "c"])]
    assert first == second

    p5.noise_seed(42)
    p5.noise_detail(3, 0.4)
    assert 0 <= p5.noise(0.1, 0.2, 0.3) <= 1
    sample = p5.noise(0.5, 0.25)
    p5.noise_seed(42)
    assert p5.noise(0.5, 0.25) == sample


def test_data_helpers_round_trip(tmp_path: Path):
    strings_path = tmp_path / "lines.txt"
    json_path = tmp_path / "data.json"

    p5.save_strings(["alpha", "beta"], strings_path)
    assert p5.load_strings(strings_path) == ["alpha", "beta"]

    p5.save_json({"answer": 42}, json_path)
    assert p5.load_json(json_path) == {"answer": 42}


def test_image_manipulation_and_drawing_with_text(tmp_path: Path):
    asset = p5.create_image(4, 4)
    asset.set(0, 0, p5.Color(255, 0, 0))
    assert asset.get(0, 0) == p5.Color(255, 0, 0, 255)
    region = asset.get(0, 0, 2, 2)
    assert isinstance(region, p5.Image)
    assert region.width == 2
    asset.resize(8, 0)
    assert asset.width == 8
    assert asset.height == 8
    asset.filter(p5.INVERT)

    asset_path = tmp_path / "asset.png"
    asset.save(asset_path)
    loaded = p5.load_image(asset_path)
    assert loaded.width == 8

    def setup():
        p5.create_canvas(32, 32)
        p5.background(255)
        p5.fill(0)
        p5.text_size(12)

    def draw():
        p5.image(loaded, 0, 0, 8, 8)
        p5.text("Hi", 10, 20)
        assert p5.text_width("Hi") > 0
        assert p5.text_ascent() > 0
        assert p5.text_descent() >= 0

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)
    assert len(set(context.load_pixels())) > 1
