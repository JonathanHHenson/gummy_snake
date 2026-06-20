import pytest

import gummysnake as gs
from gummysnake.core.transform import Matrix2D


def test_color_helpers_and_immutable_mutators():
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
    assert gs.palette_lerp([gs.Color(0, 0, 0), gs.Color(100, 0, 0)], 0.5) == gs.Color(
        50, 0, 0
    )


def test_color_modes_hsb():
    def setup():
        gs.create_canvas(5, 5)
        gs.color_mode(gs.HSB)

    def draw():
        color = gs.color(120, 100, 100, 1)
        assert color.to_tuple() == (0, 255, 0, 255)

    gs.run(setup=setup, draw=draw, headless=True, max_frames=1)


def test_matrix_translation_and_rotation():
    matrix = Matrix2D.identity().multiply(Matrix2D.translation(10, 5))
    assert matrix.transform_point(1, 2) == (11, 7)
