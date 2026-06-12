import p5_py as p5
from p5_py.core.transform import Matrix2D


def test_color_modes_hsb():
    def setup():
        p5.create_canvas(5, 5)
        p5.color_mode(p5.HSB)

    def draw():
        color = p5.color(120, 100, 100, 1)
        assert color.to_tuple() == (0, 255, 0, 255)

    p5.run(setup=setup, draw=draw, backend="headless", max_frames=1)


def test_matrix_translation_and_rotation():
    matrix = Matrix2D.identity().multiply(Matrix2D.translation(10, 5))
    assert matrix.transform_point(1, 2) == (11, 7)
