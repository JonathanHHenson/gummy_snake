from pathlib import Path

import pytest
from PIL import Image as PILImage

from p5.assets.image import Image
from p5.backends.pyglet import PygletBackend
from p5.backends.pyglet_renderer import PygletRenderer
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D


class FakeBatch:
    def __init__(self):
        self.drawn = False

    def draw(self):
        self.drawn = True


class FakeVertexList:
    calls = []
    deleted = []

    def __init__(self, count, mode, indices, batch=None, group=None, **data):
        self.count = count
        self.mode = mode
        self.indices = list(indices)
        self.batch = batch
        self.group = group
        self.position = list(data.get("position", (None, ()))[1])
        self.tex_coords = list(data.get("tex_coords", (None, ()))[1])
        self.texture = getattr(group, "texture", None)
        type(self).calls.append(self)

    def delete(self):
        type(self).deleted.append(self)


class FakeBlitShader:
    def vertex_list_indexed(self, count, mode, indices, batch=None, group=None, **data):
        return FakeVertexList(count, mode, indices, batch=batch, group=group, **data)


class FakeTextureGroup:
    def __init__(self, texture, order=0, parent=None):
        self.texture = texture
        self.order = order
        self.parent = parent


class FakeSpriteGroup:
    def __init__(self, texture, blend_src, blend_dest, program, parent=None):
        self.texture = texture
        self.blend_src = blend_src
        self.blend_dest = blend_dest
        self.program = program
        self.parent = parent


class FakeGraphics:
    def __init__(self):
        self.batches = []
        self.blit_shader = FakeBlitShader()

    def Batch(self):
        batch = FakeBatch()
        self.batches.append(batch)
        return batch

    def get_default_blit_shader(self):
        return self.blit_shader

    TextureGroup = FakeTextureGroup


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
        self.target = 3553
        self.id = 1
        self.min_filter = 9729
        self.mag_filter = 9729
        self.tex_coords = (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0)


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
    deleted = []

    def __init__(self, texture, x, y, batch):
        self.texture = texture
        self._image = texture
        self._texture = texture
        self.x = x
        self.y = y
        self.batch = batch
        self.scale_x = 1
        self.scale_y = 1
        self.rotation = 0
        self.visible = True
        type(self).calls.append(self)

    @property
    def image(self):
        return self._image

    @image.setter
    def image(self, texture):
        self._image = texture
        self._texture = texture
        self.texture = texture

    def delete(self):
        type(self).deleted.append(self)


class FakeSpriteModule:
    Sprite = FakeSprite
    SpriteGroup = FakeSpriteGroup


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

    def load(self, name, size, dpi=None):
        self.loaded.append((name, size, dpi))
        return FakeLoadedFont()


class FakeGL:
    GL_TEXTURE_MIN_FILTER = 10241
    GL_TEXTURE_MAG_FILTER = 10240
    GL_NEAREST = 9728
    GL_LINEAR = 9729
    GL_TRIANGLES = 4
    GL_SRC_ALPHA = 770
    GL_ONE_MINUS_SRC_ALPHA = 771

    def __init__(self):
        self.calls = []

    def glBindTexture(self, target, texture_id):
        self.calls.append(("bind", target, texture_id))

    def glTexParameteri(self, target, parameter, value):
        self.calls.append(("param", target, parameter, value))


class FakePyglet:
    def __init__(self):
        self.graphics = FakeGraphics()
        self.shapes = FakeShapes()
        self.image = FakeImageModule()
        self.sprite = FakeSpriteModule()
        self.text = FakeTextModule()
        self.font = FakeFontModule()
        self.gl = FakeGL()


def reset_shape_calls():
    for shape_class in (Polygon, Line, Circle, MultiLine):
        shape_class.calls.clear()
    FakeImageData.calls.clear()
    FakeSprite.calls.clear()
    FakeSprite.deleted.clear()
    FakeVertexList.calls.clear()
    FakeVertexList.deleted.clear()
    FakeLabel.calls.clear()


def test_native_backend_reports_implemented_capabilities():
    capabilities = PygletBackend.capabilities

    assert capabilities.images is True
    assert capabilities.text is True
    assert capabilities.pixel_readback is True
    assert capabilities.canvas_export is True
    assert capabilities.pixels is True
    assert capabilities.pixel_update is True
    assert {
        "blend",
        "replace",
        "add",
        "darkest",
        "lightest",
        "difference",
        "exclusion",
        "multiply",
        "screen",
    }.issubset(capabilities.blend_modes)


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


def test_native_renderer_default_draw_path_does_not_upload_full_canvas_texture():
    reset_shape_calls()
    pyglet = FakePyglet()
    renderer = PygletRenderer(20, 10, pixel_density=2, pyglet=pyglet)
    style = StyleState(stroke_color=Color(0, 0, 0), stroke_weight=2)

    renderer.line(1, 2, 3, 4, style, Matrix2D.identity())
    renderer.draw()

    assert pyglet.graphics.batches[-1].drawn is True
    assert FakeImageData.calls == []


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
    assert (sprite.x, sprite.y) == (2.0, 16.0)
    assert sprite.scale_x == 3.0
    assert sprite.scale_y == 4.0


def test_native_renderer_uses_native_path_for_reflected_image_transforms():
    reset_shape_calls()
    renderer = PygletRenderer(10, 10, pyglet=FakePyglet())
    image = Image(PILImage.new("RGBA", (2, 3), (0, 0, 0, 0)))

    transform = Matrix2D.translation(5, 5).multiply(Matrix2D.scaling(-1, 1))
    renderer.draw_image(image, -1, -1.5, 2, 3, StyleState(image_mode="corner"), transform)

    assert renderer._parity_active is False
    assert len(FakeSprite.calls) == 1
    sprite = FakeSprite.calls[-1]
    assert sprite.x == pytest.approx(6.0)
    assert sprite.y == pytest.approx(6.5)
    assert sprite.scale_x == pytest.approx(1.0)
    assert sprite.scale_y == pytest.approx(-1.0)
    assert sprite.rotation == pytest.approx(-180.0)


def test_native_renderer_resets_sprite_rotation_when_reused_after_reflection():
    reset_shape_calls()
    renderer = PygletRenderer(10, 10, pyglet=FakePyglet())
    image = Image(PILImage.new("RGBA", (2, 3), (0, 0, 0, 0)))

    left_transform = Matrix2D.translation(5, 5).multiply(Matrix2D.scaling(-1, 1))
    renderer.begin_frame()
    renderer.draw_image(image, -1, -1.5, 2, 3, StyleState(image_mode="corner"), left_transform)
    renderer.begin_frame()
    renderer.draw_image(image, 4, 3.5, 2, 3, StyleState(image_mode="corner"), Matrix2D.identity())

    assert len(FakeSprite.calls) == 1
    sprite = FakeSprite.calls[-1]
    assert sprite.x == pytest.approx(4.0)
    assert sprite.y == pytest.approx(6.5)
    assert sprite.scale_x == pytest.approx(1.0)
    assert sprite.scale_y == pytest.approx(1.0)
    assert sprite.rotation == pytest.approx(0.0)


def test_native_renderer_uses_native_quad_path_for_sheared_image_transforms():
    reset_shape_calls()
    pyglet = FakePyglet()
    renderer = PygletRenderer(10, 10, pyglet=pyglet)
    image = Image(PILImage.new("RGBA", (2, 2), (255, 0, 0, 255)))

    transform = Matrix2D.translation(2, 3).multiply(Matrix2D(1, 0.25, 0.5, 1, 0, 0))
    renderer.draw_image(image, 1, 2, 3, 4, StyleState(), transform)

    assert renderer._parity_active is False
    assert len(FakeSprite.calls) == 0
    assert len(FakeVertexList.calls) == 1
    quad = FakeVertexList.calls[-1]
    assert quad.mode == pyglet.gl.GL_TRIANGLES
    assert quad.indices == [0, 1, 2, 0, 2, 3]
    assert quad.position == pytest.approx(
        [
            6.0,
            0.75,
            0.0,
            9.0,
            0.0,
            0.0,
            7.0,
            4.0,
            0.0,
            4.0,
            4.75,
            0.0,
        ]
    )


def test_native_renderer_reuses_native_quad_for_unchanged_sheared_images():
    reset_shape_calls()
    renderer = PygletRenderer(10, 10, pyglet=FakePyglet())
    image = Image(PILImage.new("RGBA", (2, 2), (255, 0, 0, 255)))
    transform = Matrix2D(1, 0.25, 0.5, 1, 0, 0)

    renderer.begin_frame()
    renderer.draw_image(image, 1, 2, 3, 4, StyleState(), transform)
    renderer.begin_frame()
    renderer.draw_image(image, 2, 3, 3, 4, StyleState(), transform)

    assert len(FakeVertexList.calls) == 1
    assert FakeVertexList.calls[0].position == pytest.approx(
        [
            5.5,
            2.5,
            0.0,
            8.5,
            1.75,
            0.0,
            6.5,
            5.75,
            0.0,
            3.5,
            6.5,
            0.0,
        ]
    )


def test_native_renderer_uses_native_path_for_nearest_image_sampling():
    reset_shape_calls()
    pyglet = FakePyglet()
    renderer = PygletRenderer(10, 10, pyglet=pyglet)
    image = Image(PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)))

    style = StyleState()
    style.image_sampling = "nearest"

    renderer.draw_image(image, 1, 2, 3, 4, style, Matrix2D.identity())

    assert renderer._parity_active is False
    assert len(FakeSprite.calls) == 1
    texture = FakeSprite.calls[-1].texture
    assert texture.min_filter == pyglet.gl.GL_NEAREST
    assert texture.mag_filter == pyglet.gl.GL_NEAREST
    assert pyglet.gl.calls == [
        ("bind", texture.target, texture.id),
        ("param", texture.target, pyglet.gl.GL_TEXTURE_MIN_FILTER, pyglet.gl.GL_NEAREST),
        ("param", texture.target, pyglet.gl.GL_TEXTURE_MAG_FILTER, pyglet.gl.GL_NEAREST),
    ]


def test_native_renderer_keeps_nearest_images_native_after_polygon_draws():
    reset_shape_calls()
    pyglet = FakePyglet()
    renderer = PygletRenderer(10, 10, pyglet=pyglet)
    image = Image(PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)))
    style = StyleState(image_sampling="nearest")

    renderer.background(Color(0, 0, 0, 255))
    renderer.polygon(
        [(1, 1), (5, 1), (5, 5), (1, 5)],
        StyleState(fill_color=Color(80, 80, 80, 255), stroke_color=None),
        Matrix2D.identity(),
    )
    renderer.draw_image(image, 1, 2, 3, 4, style, Matrix2D.identity())

    assert renderer._parity_active is False
    assert pyglet.image.framebuffer.calls == []
    assert len(FakeSprite.calls) == 1


def test_native_renderer_reuses_cached_image_texture_for_unchanged_images():
    reset_shape_calls()
    renderer = PygletRenderer(10, 10, pyglet=FakePyglet())
    image = Image(PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)))

    renderer.begin_frame()
    renderer.draw_image(image, 0, 0, 1, 1, StyleState(), Matrix2D.identity())
    renderer.begin_frame()
    renderer.draw_image(image, 2, 0, 1, 1, StyleState(), Matrix2D.identity())

    assert len(FakeImageData.calls) == 1
    assert FakeImageData.calls[0][3] == bytes((255, 0, 0, 255))
    assert len(FakeSprite.calls) == 1
    assert FakeSprite.calls[0].texture is FakeSprite.calls[0].image
    assert FakeSprite.calls[0].visible is True


def test_native_renderer_reuploads_image_texture_when_source_image_changes():
    reset_shape_calls()
    renderer = PygletRenderer(10, 10, pyglet=FakePyglet())
    image = Image(PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)))

    renderer.begin_frame()
    renderer.draw_image(image, 0, 0, 1, 1, StyleState(), Matrix2D.identity())
    image.set(0, 0, Color(0, 255, 0, 255))
    renderer.begin_frame()
    renderer.draw_image(image, 2, 0, 1, 1, StyleState(), Matrix2D.identity())

    assert len(FakeImageData.calls) == 2
    assert FakeImageData.calls[0][3] == bytes((255, 0, 0, 255))
    assert FakeImageData.calls[1][3] == bytes((0, 255, 0, 255))
    assert len(FakeSprite.calls) == 1
    assert FakeSprite.calls[0].image.data == bytes((0, 255, 0, 255))


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
    assert first.kwargs["font_size"] == 24
    assert first.kwargs["dpi"] == 72
    assert renderer.text_width("Hi", style) == pytest.approx(12.0)
    assert renderer.text_ascent(style) == pytest.approx(8.0)
    assert renderer.text_descent(style) == pytest.approx(2.0)


def test_native_renderer_load_pixels_update_pixels_and_save_use_top_left_rgba(tmp_path: Path):
    renderer = PygletRenderer(2, 2, pyglet=FakePyglet())
    pixels = [
        255,
        0,
        0,
        255,
        0,
        255,
        0,
        255,
        0,
        0,
        255,
        255,
        255,
        255,
        255,
        255,
    ]

    renderer.update_pixels(pixels)

    assert renderer.load_pixels() == pixels
    output = tmp_path / "capture.png"
    renderer.save(output)
    with PILImage.open(output) as saved:
        assert saved.mode == "RGBA"
        assert saved.size == (2, 2)
        assert list(saved.tobytes()) == pixels


def test_native_renderer_blend_and_erase_match_pillow_surface():
    renderer = PygletRenderer(4, 1, pyglet=FakePyglet())
    renderer.background(Color(100, 100, 100, 255))
    renderer.polygon(
        [(0, 0), (1, 0), (1, 1), (0, 1)],
        StyleState(fill_color=Color(128, 255, 255, 255), stroke_color=None, blend_mode="multiply"),
        Matrix2D.identity(),
    )
    renderer.polygon(
        [(3, 0), (4, 0), (4, 1), (3, 1)],
        StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None, erasing=True),
        Matrix2D.identity(),
    )

    pixels = renderer.load_pixels()

    assert pixels[0:4] == [50, 100, 100, 255]
    assert pixels[12:16] == [100, 100, 100, 0]
