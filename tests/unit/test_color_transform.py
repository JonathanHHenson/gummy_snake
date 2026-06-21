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
    assert gs.palette_lerp([gs.Color(0, 0, 0), gs.Color(100, 0, 0)], 0.5) == gs.Color(50, 0, 0)


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


def test_matrix_numpy_ndarray_round_trip():
    np = pytest.importorskip("numpy")
    matrix = Matrix2D(1, 2, 3, 4, 5, 6)

    array = matrix.to_ndarray()

    assert isinstance(array, np.ndarray)
    assert array.tolist() == [[1, 3, 5], [2, 4, 6], [0, 0, 1]]
    assert Matrix2D.from_ndarray(array) == matrix
    assert Matrix2D.from_ndarray(matrix.to_ndarray(shape=(2, 3))) == matrix


def test_matrix_uses_rust_runtime_when_available(monkeypatch):
    class RustMatrix:
        def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
            self.a = a
            self.b = b
            self.c = c
            self.d = d
            self.e = e
            self.f = f

        @staticmethod
        def translation(x, y):
            return RustMatrix(1, 0, 0, 1, x, y)

        def multiply(self, other):
            return RustMatrix(self.a, self.b, self.c, self.d, self.e + other.e, self.f + other.f)

        def transform_point(self, x, y):
            return (self.a * x + self.e, self.d * y + self.f)

        def as_tuple(self):
            return (self.a, self.b, self.c, self.d, self.e, self.f)

    class Runtime:
        Matrix2D = RustMatrix

    monkeypatch.setattr("gummysnake.rust.canvas.is_canvas_runtime_available", lambda: True)
    monkeypatch.setattr("gummysnake.rust.canvas.require_canvas_runtime", lambda: Runtime())

    matrix = Matrix2D.identity().multiply(Matrix2D.translation(10, 5))

    assert matrix.as_tuple() == (1.0, 0.0, 0.0, 1.0, 10.0, 5.0)
    assert matrix.transform_point(1, 2) == (11.0, 7.0)
