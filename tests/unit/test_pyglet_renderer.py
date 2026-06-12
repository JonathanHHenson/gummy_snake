from pathlib import Path

import pytest
from PIL import Image as PILImage

from p5_py.assets.image import Image
from p5_py.backends.pyglet import PygletBackend
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


class FakeTexture:
    def __init__(self, width, height, data, pitch):
        self.width = width
        self.height = height
        self.data = data
        self.pitch = pitch


class FakeImageData:
    calls = []

    def __init__(self, width, height, fmt, data, pitch=None):
        self.width = width
        self.height = height
        self.fmt = fmt
        self.data = data
        self.pitch = pitch
        type(self).calls.append((width, height, fmt, data, pitch))

    def get_texture(self):
        return FakeTexture(self.width, self.height, self.data, self.pitch)


class FakeFramebufferImage:
    def __init__(self, width, height, data):
        self.width = width
        self.height = height
        self.data = data
        self.calls = []

    def get_data(self, fmt, pitch):
        self.calls.append((fmt, pitch))
        return self.data


class FakeColorBuffer:
    def __init__(self, image_data):
        self.image_data = image_data

    def get_image_data(self):
        return self.image_data


class FakeBufferManager:
    def __init__(self, image_data):
        self.image_data = image_data

    def get_color_buffer(self):
        return FakeColorBuffer(self.image_data)


class FakeImageModule:
    ImageData = FakeImageData

    def __init__(self):
        self.framebuffer = FakeFramebufferImage(2, 2, bytes(range(16)))

    def get_buffer_manager(self):
        return FakeBufferManager(self.framebuffer)


class FakeSprite:
    calls = []

    def __init__(self, texture, x, y, batch):
        self.texture = texture
        self.x = x
        self.y = y
        self.batch = batch
        self.scale_x = 1
        self.scale_y = 1
        self.rotation = 0
        type(self).calls.append(self)


class FakeSpriteModule:
    Sprite = FakeSprite


class FakeLabel:
    calls = []

    def __init__(self, text, **kwargs):
        self.text = text
        self.kwargs = kwargs
        self.content_width = len(text) * float(kwargs.get("font_size", 12)) * 0.5
        self.content_height = float(kwargs.get("font_size", 12))
        self.rotation = 0
        type(self).calls.append(self)


class FakeTextModule:
    Label = FakeLabel


class FakeLoadedFont:
    ascent = 16
    descent = -4


class FakeFontModule:
    def __init__(self):
        self.loaded = []
        self.files = []

    def add_file(self, path):
        self.files.append(path)

    def load(self, name, size):
        self.loaded.append((name, size))
        return FakeLoadedFont()


class FakePyglet:
    def __init__(self):
        self.graphics = FakeGraphics()
        self.shapes = FakeShapes()
        self.image = FakeImageModule()
        self.sprite = FakeSpriteModule()
        self.text = FakeTextModule()
        self.font = FakeFontModule()


def reset_shape_calls():
    for shape_class in (Polygon, Line, Circle, MultiLine):
        shape_class.calls.clear()
    FakeImageData.calls.clear()
    FakeSprite.calls.clear()
    FakeLabel.calls.clear()


def test_native_backend_reports_implemented_capabilities():
    capabilities = PygletBackend.capabilities

    assert capabilities.images is True
    assert capabilities.text is True
    assert capabilities.pixel_readback is True
    assert capabilities.canvas_export is True
    assert capabilities.pixel_update is False


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


def test_native_renderer_draws_images_with_texture_upload_and_source_crop():
    reset_shape_calls()
    renderer = PygletRenderer(20, 10, pixel_density=2, pyglet=FakePyglet())
    image = Image(PILImage.new("RGBA", (4, 4), (255, 0, 0, 255)))

    renderer.draw_image(
        image,
        1,
        2,
        3,
        4,
        StyleState(),
        Matrix2D.identity(),
        source=(1, 1, 2, 2),
    )

    assert FakeImageData.calls
    width, height, fmt, _data, pitch = FakeImageData.calls[-1]
    assert (width, height, fmt, pitch) == (2, 2, "RGBA", -8)
    assert FakeSprite.calls
    sprite = FakeSprite.calls[-1]
    assert (sprite.x, sprite.y) == (2.0, 8.0)
    assert sprite.scale_x == 3.0
    assert sprite.scale_y == 4.0


def test_native_renderer_reuploads_current_image_data_each_draw():
    reset_shape_calls()
    renderer = PygletRenderer(10, 10, pyglet=FakePyglet())
    image = Image(PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)))

    renderer.draw_image(image, 0, 0, 1, 1, StyleState(), Matrix2D.identity())
    image.set(0, 0, Color(0, 255, 0, 255))
    renderer.draw_image(image, 2, 0, 1, 1, StyleState(), Matrix2D.identity())

    assert len(FakeImageData.calls) == 2
    assert FakeImageData.calls[0][3] == bytes((255, 0, 0, 255))
    assert FakeImageData.calls[1][3] == bytes((0, 255, 0, 255))


def test_native_renderer_draws_and_measures_text():
    reset_shape_calls()
    renderer = PygletRenderer(100, 50, pixel_density=2, pyglet=FakePyglet())
    style = StyleState(
        fill_color=Color(10, 20, 30),
        text_size=12,
        text_align_x="center",
        text_align_y="top",
    )

    renderer.text("Hi\nPy", 10, 5, style, Matrix2D.translation(1, 2))

    assert len(FakeLabel.calls) == 2
    first = FakeLabel.calls[0]
    assert first.text == "Hi"
    assert first.kwargs["x"] == 22.0
    assert first.kwargs["y"] == 86.0
    assert first.kwargs["anchor_x"] == "center"
    assert first.kwargs["anchor_y"] == "top"
    assert first.kwargs["color"] == (10, 20, 30, 255)
    assert renderer.text_width("Hi", style) == pytest.approx(12.0)
    assert renderer.text_ascent(style) == pytest.approx(8.0)
    assert renderer.text_descent(style) == pytest.approx(2.0)


def test_native_renderer_load_pixels_and_save_read_framebuffer_top_left(tmp_path: Path):
    pyglet = FakePyglet()
    renderer = PygletRenderer(2, 2, pyglet=pyglet)

    assert renderer.load_pixels() == list(range(16))
    assert pyglet.image.framebuffer.calls[-1] == ("RGBA", -8)

    output = tmp_path / "capture.png"
    renderer.save(output)

    with PILImage.open(output) as saved:
        assert saved.mode == "RGBA"
        assert saved.size == (2, 2)
        assert saved.tobytes() == bytes(range(16))


def test_native_renderer_still_gates_update_pixels():
    renderer = PygletRenderer(pyglet=FakePyglet())

    with pytest.raises(BackendCapabilityError):
        renderer.update_pixels([])
