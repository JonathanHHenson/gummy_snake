"""Native Pyglet renderer implementation."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from math import atan2, cos, hypot, pi, sin
from pathlib import Path
from typing import Any, cast

from PIL import Image as PILImage

from p5 import constants as c
from p5.assets.image import Image
from p5.backends.pillow import PillowRenderer
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.exceptions import ArgumentValidationError, BackendCapabilityError


def _rgba(color: Color | None) -> tuple[int, int, int, int] | None:
    return None if color is None else color.to_tuple()


_PYGLET_FONT_DPI = 72


class PygletRenderer:
    """Pyglet-native 2D renderer used by the interactive backend.

    The renderer accepts p5-py logical coordinates from ``SketchContext`` and maps them into
    physical framebuffer coordinates. Pyglet uses a bottom-left origin, so the mapping also flips
    the y axis from p5's top-left coordinate system.
    """

    width: int
    height: int
    physical_width: int
    physical_height: int
    pixel_density: float

    def __init__(
        self,
        width: int = 100,
        height: int = 100,
        pixel_density: float = 1.0,
        *,
        pyglet: Any | None = None,
    ) -> None:
        self._pyglet = pyglet
        self._batch: Any | None = None
        self._drawables: list[Any] = []
        self._sprite_pool: list[Any] = []
        self._sprite_pool_index = 0
        self._quad_pool: list[Any] = []
        self._quad_pool_index = 0
        self._image_texture_cache: dict[
            tuple[int, tuple[int, int, int, int] | None], tuple[int, Any]
        ] = {}
        self._surface = PillowRenderer(width, height, pixel_density)
        self._parity_active = False
        self._surface_in_sync = True
        self.resize(width, height, pixel_density)

    def resize(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        if width <= 0 or height <= 0:
            raise ArgumentValidationError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ArgumentValidationError("Pixel density must be positive.")
        self.width = int(width)
        self.height = int(height)
        self.pixel_density = float(pixel_density)
        self.physical_width = max(1, int(round(self.width * self.pixel_density)))
        self.physical_height = max(1, int(round(self.height * self.pixel_density)))
        self._surface.resize(self.width, self.height, self.pixel_density)
        self._parity_active = False
        self._surface_in_sync = True
        self._image_texture_cache.clear()
        self._reset_batch()

    def begin_frame(self) -> None:
        if self._parity_active:
            self._surface.begin_frame()
        self._clear_frame_drawables()

    def end_frame(self) -> None:
        pass

    def background(self, color: Color) -> None:
        self._surface.background(color)
        self._parity_active = False
        self._surface_in_sync = True
        self._clear_frame_drawables()
        self._filled_polygon(
            [
                (0, 0),
                (self.width, 0),
                (self.width, self.height),
                (0, self.height),
            ],
            color.to_tuple(),
            Matrix2D.identity(),
        )

    def clear(self) -> None:
        self._surface.clear()
        self._parity_active = False
        self._surface_in_sync = True
        self._clear_frame_drawables()

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        if self._use_parity_for_style(style):
            self._surface.point(x, y, style, transform)
            return
        self._surface_in_sync = False
        color = _rgba(style.stroke_color or style.fill_color)
        if color is None:
            return
        px, py = self._to_framebuffer(*transform.transform_point(x, y))
        radius = max(0.5, style.stroke_weight * self.pixel_density / 2)
        self._add_shape("Circle", px, py, radius, color=color)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if self._use_parity_for_style(style):
            self._surface.line(x1, y1, x2, y2, style, transform)
            return
        self._surface_in_sync = False
        if style.stroke_color is None:
            return
        p1 = self._to_framebuffer(*transform.transform_point(x1, y1))
        p2 = self._to_framebuffer(*transform.transform_point(x2, y2))
        self._line_between(p1, p2, style)

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        if self._use_parity_for_style(style):
            self._surface.polygon(points, style, transform, close=close)
            return
        self._surface_in_sync = False
        if not points:
            return
        if len(points) == 1:
            self.point(points[0][0], points[0][1], style, transform)
            return
        transformed = [self._to_framebuffer(*transform.transform_point(x, y)) for x, y in points]
        if style.fill_color is not None and close and len(transformed) >= 3:
            self._raw_polygon(transformed, style.fill_color.to_tuple())
        if style.stroke_color is not None:
            self._joined_polyline(transformed, style, closed=close)

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        cx = x + width / 2
        cy = y + height / 2
        rx = width / 2
        ry = height / 2
        points = [(cx + cos(t) * rx, cy + sin(t) * ry) for t in _angle_steps(64)]
        self.polygon(points, style, transform, close=True)

    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: str,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        cx = x + width / 2
        cy = y + height / 2
        rx = width / 2
        ry = height / 2
        while stop < start:
            stop += 2 * pi
        steps = max(8, int(abs(stop - start) / (2 * pi) * 64))
        arc_points = [
            (
                cx + cos(start + (stop - start) * index / steps) * rx,
                cy + sin(start + (stop - start) * index / steps) * ry,
            )
            for index in range(steps + 1)
        ]
        if mode == c.PIE:
            self.polygon([(cx, cy), *arc_points], style, transform, close=True)
        elif mode == c.CHORD:
            self.polygon(arc_points, style, transform, close=True)
        else:
            if style.fill_color is not None and mode != c.OPEN:
                self.polygon(arc_points, style, transform, close=True)
            if style.stroke_color is not None:
                transformed = [
                    self._to_framebuffer(*transform.transform_point(px, py))
                    for px, py in arc_points
                ]
                self._joined_polyline(transformed, style, closed=False)

    def draw_image(
        self,
        image: Image,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: StyleState,
        transform: Matrix2D,
        *,
        source: tuple[int, int, int, int] | None = None,
    ) -> None:
        if self._use_parity_for_image(style, transform):
            self._surface.draw_image(image, dx, dy, dw, dh, style, transform, source=source)
            return
        self._surface_in_sync = False
        if dw <= 0 or dh <= 0:
            return
        texture = self._texture_for_image(image, source)
        self._apply_texture_sampling(texture, style.image_sampling)
        corners = self._transformed_framebuffer_quad(dx, dy, dw, dh, transform)
        if self._can_use_sprite_for_quad(corners):
            x, y, width, height, rotation, reflected = self._sprite_rect_from_quad(corners)
            sprite = self._make_sprite(texture, x=x, y=y)
            sprite.scale_x = width / max(1, texture.width)
            sprite.scale_y = (-height if reflected else height) / max(1, texture.height)
            sprite.rotation = rotation
            return
        self._make_textured_quad(texture, corners)

    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if self._use_parity_for_style(style):
            self._surface.text(value, x, y, style, transform)
            return
        self._surface_in_sync = False
        if style.fill_color is None:
            return
        lines = str(value).splitlines() or [""]
        for line_index, line in enumerate(lines):
            tx, ty = transform.transform_point(x, y + line_index * style.text_leading)
            px, py = self._to_framebuffer(tx, ty)
            label = self._make_label(
                line,
                x=px,
                y=py,
                style=style,
                transform=transform,
            )
            self._drawables.append(label)

    def text_width(self, value: str, style: StyleState) -> float:
        labels = [self._measure_label(line, style) for line in (str(value).splitlines() or [""])]
        return max(
            (float(getattr(label, "content_width", 0.0)) / self.pixel_density for label in labels),
            default=0.0,
        )

    def text_ascent(self, style: StyleState) -> float:
        font = self._load_pyglet_font(style)
        ascent = getattr(font, "ascent", None)
        if ascent is None:
            return style.text_size * 0.8
        return float(ascent) / self.pixel_density

    def text_descent(self, style: StyleState) -> float:
        font = self._load_pyglet_font(style)
        descent = getattr(font, "descent", None)
        if descent is None:
            return style.text_size * 0.2
        return abs(float(descent)) / self.pixel_density

    def load_pixels(self) -> list[int]:
        if self._parity_active:
            return self._surface.load_pixels()
        return list(self._read_framebuffer_rgba())

    def update_pixels(self, pixels: Sequence[int]) -> None:
        self._surface.update_pixels(pixels)
        self._parity_active = True
        self._surface_in_sync = True
        self._reset_batch()

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: str,
    ) -> None:
        self._activate_parity_surface()
        self._surface.blend_region(cast(Any, source_image), source, destination, mode)
        self._reset_batch()

    def save(self, path: str | Path) -> None:
        if self._parity_active:
            self._surface.save(path)
            return
        image = PILImage.frombytes(
            "RGBA",
            (self.physical_width, self.physical_height),
            self._read_framebuffer_rgba(),
        )
        image.save(path)

    def draw(self) -> None:
        if self._batch is not None and not self._parity_active:
            self._batch.draw()
            return
        if self._pyglet is None:
            return
        pyglet = self._load_pyglet()
        batch = pyglet.graphics.Batch()
        texture = self._texture_for_pillow(self._surface.get_image())
        sprite = pyglet.sprite.Sprite(texture, x=0, y=self.physical_height, batch=batch)
        sprite.scale_x = self.physical_width / max(1, texture.width)
        sprite.scale_y = self.physical_height / max(1, texture.height)
        batch.draw()

    def bind_pyglet(self, pyglet: Any) -> None:
        if self._pyglet is pyglet:
            return
        self._pyglet = pyglet
        self._reset_batch()

    def _load_pyglet(self) -> Any:
        if self._pyglet is None:
            import pyglet

            self._pyglet = pyglet
        return self._pyglet

    def _clear_frame_drawables(self) -> None:
        for drawable in self._drawables:
            with suppress(AttributeError):
                drawable.delete()
        self._drawables = []
        for sprite in self._sprite_pool:
            with suppress(AttributeError):
                sprite.visible = False
        self._sprite_pool_index = 0
        self._quad_pool_index = 0
        if self._pyglet is None:
            self._batch = None
            return
        if self._batch is None:
            self._batch = self._load_pyglet().graphics.Batch()

    def _reset_batch(self) -> None:
        for drawable in self._drawables:
            with suppress(AttributeError):
                drawable.delete()
        self._drawables = []
        for sprite in self._sprite_pool:
            with suppress(AttributeError):
                sprite.delete()
        self._sprite_pool = []
        self._sprite_pool_index = 0
        for quad in self._quad_pool:
            with suppress(AttributeError):
                quad.delete()
        self._quad_pool = []
        self._quad_pool_index = 0
        if self._pyglet is None:
            self._batch = None
            return
        self._batch = self._load_pyglet().graphics.Batch()

    def _use_parity_for_style(self, style: StyleState) -> bool:
        if self._parity_active:
            return True
        if style.erasing or style.blend_mode != c.BLEND:
            self._activate_parity_surface()
            return True
        return False

    def _use_parity_for_image(self, style: StyleState, transform: Matrix2D) -> bool:
        if self._parity_active:
            return True
        if style.erasing or style.blend_mode != c.BLEND:
            self._activate_parity_surface()
            return True
        return False

    def _activate_parity_surface(self) -> None:
        if self._parity_active:
            return
        if not self._surface_in_sync:
            with suppress(BackendCapabilityError):
                self._surface.update_pixels(list(self._read_framebuffer_rgba()))
        self._parity_active = True
        self._surface_in_sync = True
        self._reset_batch()

    def _to_framebuffer(self, x: float, y: float) -> tuple[float, float]:
        return x * self.pixel_density, self.physical_height - y * self.pixel_density

    def _line_between(
        self, p1: tuple[float, float], p2: tuple[float, float], style: StyleState
    ) -> None:
        color = _rgba(style.stroke_color)
        if color is None:
            return
        self._add_shape(
            "Line",
            p1[0],
            p1[1],
            p2[0],
            p2[1],
            thickness=max(1, style.stroke_weight * self.pixel_density),
            color=color,
        )

    def _joined_polyline(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        *,
        closed: bool,
    ) -> None:
        color = _rgba(style.stroke_color)
        if len(points) < 2 or color is None:
            return
        self._add_shape(
            "MultiLine",
            *points,
            closed=closed,
            thickness=max(1, style.stroke_weight * self.pixel_density),
            color=color,
        )

    def _filled_polygon(
        self,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        transform: Matrix2D,
    ) -> None:
        transformed = [self._to_framebuffer(*transform.transform_point(x, y)) for x, y in points]
        self._raw_polygon(transformed, color)

    def _raw_polygon(
        self, points: list[tuple[float, float]], color: tuple[int, int, int, int]
    ) -> None:
        if len(points) < 3:
            return
        self._add_shape("Polygon", *points, color=color)

    def _add_shape(self, name: str, *args: Any, **kwargs: Any) -> None:
        pyglet = self._load_pyglet()
        if self._batch is None:
            self._batch = pyglet.graphics.Batch()
        shape_class = getattr(pyglet.shapes, name)
        shape = shape_class(*args, **kwargs, batch=self._batch)
        self._drawables.append(shape)

    def _texture_for_image(
        self, image: Image, source: tuple[int, int, int, int] | None = None
    ) -> Any:
        cache_key = (id(image), source)
        cached = self._image_texture_cache.get(cache_key)
        if cached is not None:
            cached_version, texture = cached
            if cached_version == image.version:
                return texture
        source_image = image.pillow
        if source is not None:
            sx, sy, sw, sh = source
            source_image = source_image.crop((sx, sy, sx + sw, sy + sh))
        texture = self._texture_for_pillow(source_image)
        self._image_texture_cache[cache_key] = (image.version, texture)
        return texture

    def _texture_for_pillow(self, source_image: PILImage.Image) -> Any:
        source_image = source_image.convert("RGBA")
        pyglet = self._load_pyglet()
        image_data = pyglet.image.ImageData(
            source_image.width,
            source_image.height,
            "RGBA",
            source_image.tobytes(),
            pitch=-source_image.width * 4,
        )
        texture_getter = getattr(image_data, "get_texture", None)
        texture = texture_getter() if callable(texture_getter) else image_data
        texture_any: Any = texture
        try:
            texture_any.anchor_x = 0
            texture_any.anchor_y = texture_any.height
        except AttributeError:
            pass
        return texture

    def _apply_texture_sampling(self, texture: Any, sampling: str) -> None:
        pyglet = self._load_pyglet()
        gl = getattr(pyglet, "gl", None)
        if sampling == c.NEAREST:
            filter_value = getattr(gl, "GL_NEAREST", None)
        else:
            filter_value = getattr(gl, "GL_LINEAR", None)
        if filter_value is None:
            return
        with suppress(AttributeError):
            texture.min_filter = filter_value
        with suppress(AttributeError):
            texture.mag_filter = filter_value
        bind_texture = getattr(gl, "glBindTexture", None)
        set_parameter = getattr(gl, "glTexParameteri", None)
        target = getattr(texture, "target", None)
        texture_id = getattr(texture, "id", None)
        min_filter = getattr(gl, "GL_TEXTURE_MIN_FILTER", None)
        mag_filter = getattr(gl, "GL_TEXTURE_MAG_FILTER", None)
        if not (
            callable(bind_texture)
            and callable(set_parameter)
            and target is not None
            and texture_id is not None
            and min_filter is not None
            and mag_filter is not None
        ):
            return
        bind_texture(target, texture_id)
        set_parameter(target, min_filter, filter_value)
        set_parameter(target, mag_filter, filter_value)

    def _make_sprite(self, texture: Any, *, x: float, y: float) -> Any:
        pyglet = self._load_pyglet()
        if self._batch is None:
            self._batch = pyglet.graphics.Batch()
        if self._sprite_pool_index < len(self._sprite_pool):
            sprite = self._sprite_pool[self._sprite_pool_index]
            current_texture = getattr(sprite, "_texture", None)
            if current_texture is None:
                with suppress(AttributeError):
                    sprite.delete()
                sprite = pyglet.sprite.Sprite(texture, x=x, y=y, batch=self._batch)
                self._sprite_pool[self._sprite_pool_index] = sprite
            else:
                image = getattr(sprite, "image", None)
                if image is not texture:
                    sprite.image = texture
                sprite.x = x
                sprite.y = y
                sprite.visible = True
        else:
            sprite = pyglet.sprite.Sprite(texture, x=x, y=y, batch=self._batch)
            self._sprite_pool.append(sprite)
        self._sprite_pool_index += 1
        return sprite

    def _make_textured_quad(
        self,
        texture: Any,
        corners: tuple[
            tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
        ],
    ) -> Any:
        pyglet = self._load_pyglet()
        if self._batch is None:
            self._batch = pyglet.graphics.Batch()
        positions = self._quad_positions(corners)
        tex_coords = self._quad_tex_coords(texture)
        if self._quad_pool_index < len(self._quad_pool):
            quad = self._quad_pool[self._quad_pool_index]
            current_texture = getattr(quad, "texture", None)
            if current_texture is texture:
                quad.position[:] = positions
                quad.tex_coords[:] = tex_coords
            else:
                with suppress(AttributeError):
                    quad.delete()
                quad = self._create_textured_quad(texture, positions, tex_coords)
                self._quad_pool[self._quad_pool_index] = quad
        else:
            quad = self._create_textured_quad(texture, positions, tex_coords)
            self._quad_pool.append(quad)
        self._quad_pool_index += 1
        return quad

    def _create_textured_quad(
        self, texture: Any, positions: tuple[float, ...], tex_coords: tuple[float, ...]
    ) -> Any:
        pyglet = self._load_pyglet()
        shader = pyglet.graphics.get_default_blit_shader()
        sprite_group = getattr(getattr(pyglet, "sprite", None), "SpriteGroup", None)
        if sprite_group is not None:
            group = sprite_group(
                texture,
                pyglet.gl.GL_SRC_ALPHA,
                pyglet.gl.GL_ONE_MINUS_SRC_ALPHA,
                shader,
            )
        else:
            group = pyglet.graphics.TextureGroup(texture)
        quad = shader.vertex_list_indexed(
            4,
            pyglet.gl.GL_TRIANGLES,
            (0, 1, 2, 0, 2, 3),
            batch=self._batch,
            group=group,
            position=("f", positions),
            tex_coords=("f", tex_coords),
        )
        quad.texture = texture
        return quad

    def _quad_positions(
        self,
        corners: tuple[
            tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
        ],
    ) -> tuple[float, ...]:
        top_left, top_right, bottom_right, bottom_left = corners
        ordered = (bottom_left, bottom_right, top_right, top_left)
        return tuple(component for x, y in ordered for component in (x, y, 0.0))

    def _quad_tex_coords(self, texture: Any) -> tuple[float, ...]:
        coords = tuple(
            float(value)
            for value in getattr(texture, "tex_coords", (0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0))
        )
        if len(coords) >= 12:
            return coords[:12]
        return (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0)

    def _transformed_framebuffer_quad(
        self, x: float, y: float, width: float, height: float, transform: Matrix2D
    ) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
        points = (
            transform.transform_point(x, y),
            transform.transform_point(x + width, y),
            transform.transform_point(x + width, y + height),
            transform.transform_point(x, y + height),
        )
        framebuffer = tuple(self._to_framebuffer(*point) for point in points)
        return cast(
            tuple[
                tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
            ],
            framebuffer,
        )

    def _can_use_sprite_for_quad(
        self,
        corners: tuple[
            tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
        ],
    ) -> bool:
        top_left, top_right, bottom_right, bottom_left = corners
        x_axis = (top_right[0] - top_left[0], top_right[1] - top_left[1])
        y_axis = (bottom_left[0] - top_left[0], bottom_left[1] - top_left[1])
        dot = x_axis[0] * y_axis[0] + x_axis[1] * y_axis[1]
        scale = max(1.0, hypot(*x_axis) * hypot(*y_axis))
        return abs(dot) <= scale * 1e-6

    def _sprite_rect_from_quad(
        self,
        corners: tuple[
            tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
        ],
    ) -> tuple[float, float, float, float, float, bool]:
        top_left, top_right, _bottom_right, bottom_left = corners
        left = top_left[0]
        top = top_left[1]
        x_axis = (top_right[0] - left, top_right[1] - top)
        y_axis = (bottom_left[0] - left, bottom_left[1] - top)
        width_px = max(0.0, hypot(*x_axis))
        height_px = max(0.0, hypot(*y_axis))
        rotation = -atan2(x_axis[1], x_axis[0]) * 180 / pi
        reflected = x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0] > 0
        return left, top, width_px, height_px, rotation, reflected

    def _make_label(
        self,
        value: str,
        *,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> Any:
        pyglet = self._load_pyglet()
        if self._batch is None:
            self._batch = pyglet.graphics.Batch()
        label = pyglet.text.Label(
            value,
            font_name=self._pyglet_font_name(style),
            font_size=style.text_size * self.pixel_density,
            dpi=_PYGLET_FONT_DPI,
            x=x,
            y=y,
            anchor_x=self._pyglet_anchor_x(style),
            anchor_y=self._pyglet_anchor_y(style),
            color=style.fill_color.to_tuple() if style.fill_color is not None else (0, 0, 0, 0),
            batch=self._batch,
        )
        rotation = -atan2(transform.b, transform.a) * 180 / pi
        if rotation:
            label.rotation = rotation
        return label

    def _measure_label(self, value: str, style: StyleState) -> Any:
        pyglet = self._load_pyglet()
        return pyglet.text.Label(
            value,
            font_name=self._pyglet_font_name(style),
            font_size=style.text_size * self.pixel_density,
            dpi=_PYGLET_FONT_DPI,
        )

    def _load_pyglet_font(self, style: StyleState) -> Any:
        pyglet = self._load_pyglet()
        font_name = self._pyglet_font_name(style)
        return pyglet.font.load(
            font_name, style.text_size * self.pixel_density, dpi=_PYGLET_FONT_DPI
        )

    def _pyglet_font_name(self, style: StyleState) -> str | None:
        font = style.text_font
        if font.path is not None:
            pyglet = self._load_pyglet()
            add_file = getattr(pyglet.font, "add_file", None)
            if callable(add_file):
                add_file(str(font.path))
            return font.name or font.path.stem
        return None if font.name == "default" else font.name

    def _pyglet_anchor_x(self, style: StyleState) -> str:
        if style.text_align_x == c.CENTER:
            return "center"
        if style.text_align_x == c.RIGHT:
            return "right"
        return "left"

    def _pyglet_anchor_y(self, style: StyleState) -> str:
        if style.text_align_y == c.TOP:
            return "top"
        if style.text_align_y == c.CENTER:
            return "center"
        if style.text_align_y == c.BOTTOM:
            return "bottom"
        return "baseline"

    def _read_framebuffer_rgba(self) -> bytes:
        self.draw()
        pyglet = self._load_pyglet()
        manager = pyglet.image.get_buffer_manager()
        color_buffer = manager.get_color_buffer()
        image_data_getter = getattr(color_buffer, "get_image_data", None)
        image_data = image_data_getter() if callable(image_data_getter) else color_buffer
        width = int(getattr(image_data, "width", self.physical_width))
        height = int(getattr(image_data, "height", self.physical_height))
        get_data = getattr(image_data, "get_data", None)
        if not callable(get_data):
            raise BackendCapabilityError("Pyglet framebuffer readback is unavailable.")
        data: Any = get_data("RGBA", -width * 4)
        if width == self.physical_width and height == self.physical_height:
            return bytes(data)
        image = PILImage.frombytes("RGBA", (width, height), bytes(data))
        return image.resize(
            (self.physical_width, self.physical_height), PILImage.Resampling.NEAREST
        ).tobytes()


def _angle_steps(count: int):
    return (2 * pi * index / count for index in range(count))
