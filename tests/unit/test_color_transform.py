import gummysnake as gs
from gummysnake.core.transform import Matrix2D


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
