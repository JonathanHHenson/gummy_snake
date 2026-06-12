import pytest

from p5_py.backends.pyglet_renderer import PygletRenderer
from p5_py.core.color import Color
from p5_py.core.state import StyleState
from p5_py.core.transform import Matrix2D
from p5_py.exceptions import BackendCapabilityError


class FakeBatch:
    def __init__(self):
        self.drawn = False

    def draw(self):
        self.drawn = True


class FakeGraphics:
    def __init__(self):
        self.batches = []

    def Batch(self):
        batch = FakeBatch()
        self.batches.append(batch)
        return batch


class FakeShape:
    calls = []

    def __init__(self, *args, **kwargs):
        type(self).calls.append((self.__class__.__name__, args, kwargs))


class Polygon(FakeShape):
    calls = []


class Line(FakeShape):
    calls = []


class Circle(FakeShape):
    calls = []


class MultiLine(FakeShape):
    calls = []


class FakeShapes:
    Polygon = Polygon
    Line = Line
    Circle = Circle
    MultiLine = MultiLine


class FakePyglet:
    def __init__(self):
        self.graphics = FakeGraphics()
        self.shapes = FakeShapes()


def reset_shape_calls():
    for shape_class in (Polygon, Line, Circle, MultiLine):
        shape_class.calls.clear()


def test_native_renderer_tracks_logical_and_physical_sizes():
    renderer = PygletRenderer(100, 50, pixel_density=2, pyglet=FakePyglet())

    assert renderer.width == 100
    assert renderer.height == 50
    assert renderer.physical_width == 200
    assert renderer.physical_height == 100


def test_native_renderer_maps_p5_coordinates_to_framebuffer_coordinates():
    reset_shape_calls()
    renderer = PygletRenderer(20, 10, pixel_density=2, pyglet=FakePyglet())
    style = StyleState(stroke_color=Color(0, 0, 0), stroke_weight=2)

    renderer.line(1, 2, 3, 4, style, Matrix2D.translation(5, 0))

    assert Line.calls
    _name, args, kwargs = Line.calls[-1]
    assert args == (12.0, 16.0, 16.0, 12.0)
    assert kwargs["thickness"] == 4
    assert kwargs["color"] == (0, 0, 0, 255)


def test_native_renderer_draws_fill_and_stroke_for_closed_polygons():
    reset_shape_calls()
    renderer = PygletRenderer(20, 20, pyglet=FakePyglet())
    style = StyleState(fill_color=Color(255, 0, 0), stroke_color=Color(0, 0, 255))

    renderer.polygon([(1, 1), (4, 1), (4, 4)], style, Matrix2D.identity())

    assert len(Polygon.calls) == 1
    assert len(Line.calls) == 0
    assert len(MultiLine.calls) == 1
    _name, args, kwargs = MultiLine.calls[-1]
    assert args == ((1.0, 19.0), (4.0, 19.0), (4.0, 16.0))
    assert kwargs["closed"] is True
    assert kwargs["color"] == (0, 0, 255, 255)


def test_native_renderer_gates_pixel_and_export_apis():
    renderer = PygletRenderer(pyglet=FakePyglet())

    with pytest.raises(BackendCapabilityError):
        renderer.load_pixels()
    with pytest.raises(BackendCapabilityError):
        renderer.update_pixels([])
    with pytest.raises(BackendCapabilityError):
        renderer.save("output.png")
