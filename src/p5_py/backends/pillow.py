"""Pillow-backed 2D renderer."""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil, cos, floor, pi, sin
from pathlib import Path
from typing import cast

from PIL import Image as PILImage
from PIL import ImageChops, ImageDraw

from p5_py import constants as c
from p5_py.assets.image import Image
from p5_py.core.color import Color
from p5_py.core.state import StyleState
from p5_py.core.transform import Matrix2D
from p5_py.exceptions import ArgumentValidationError

_AFFINE_EPSILON = 1e-12


def _rgba(color: Color | None) -> tuple[int, int, int, int] | None:
    return None if color is None else color.to_tuple()


def _stroke_width(style: StyleState, pixel_density: float) -> int:
    return max(1, int(round(style.stroke_weight * pixel_density)))


class PillowRenderer:
    """Deterministic raster renderer used by headless and Pyglet backends."""

    width: int
    height: int
    physical_width: int
    physical_height: int

    def __init__(self, width: int = 100, height: int = 100, pixel_density: float = 1.0) -> None:
        self.pixel_density = pixel_density
        self._resized_image_cache: dict[tuple[object, ...], PILImage.Image] = {}
        self._text_line_cache: dict[tuple[object, ...], tuple[PILImage.Image, int, int]] = {}
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
        self.image = PILImage.new("RGBA", (self.physical_width, self.physical_height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def begin_frame(self) -> None:
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def end_frame(self) -> None:
        pass

    def background(self, color: Color) -> None:
        self.draw.rectangle(
            (0, 0, self.physical_width, self.physical_height), fill=color.to_tuple()
        )

    def clear(self) -> None:
        self.image = PILImage.new("RGBA", (self.physical_width, self.physical_height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        def draw_point() -> None:
            color = style.stroke_color or style.fill_color
            if color is None:
                return
            tx, ty = self._physical_transform(transform).transform_point(x, y)
            radius = max(0.5, style.stroke_weight * self.pixel_density / 2)
            self.draw.ellipse(
                (tx - radius, ty - radius, tx + radius, ty + radius),
                fill=color.to_tuple(),
            )

        self._draw_with_style(style, draw_point)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        def draw_line() -> None:
            if style.stroke_color is None:
                return
            physical_transform = self._physical_transform(transform)
            p1 = physical_transform.transform_point(x1, y1)
            p2 = physical_transform.transform_point(x2, y2)
            self.draw.line(
                (*p1, *p2),
                fill=style.stroke_color.to_tuple(),
                width=_stroke_width(style, self.pixel_density),
            )

        self._draw_with_style(style, draw_line)

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        def draw_polygon() -> None:
            if not points:
                return
            physical_transform = self._physical_transform(transform)
            transformed = [physical_transform.transform_point(x, y) for x, y in points]
            if len(transformed) == 1:
                tx, ty = transformed[0]
                radius = max(0.5, style.stroke_weight * self.pixel_density / 2)
                color = style.stroke_color or style.fill_color
                if color is not None:
                    self.draw.ellipse(
                        (tx - radius, ty - radius, tx + radius, ty + radius),
                        fill=color.to_tuple(),
                    )
                return
            if style.fill_color is not None and close and len(transformed) >= 3:
                self.draw.polygon(transformed, fill=style.fill_color.to_tuple())
            if style.stroke_color is not None:
                stroke_points = [*transformed, transformed[0]] if close else transformed
                self._draw_joined_polyline(stroke_points, style)

        self._draw_with_style(style, draw_polygon)

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
                physical_transform = self._physical_transform(transform)
                transformed = [physical_transform.transform_point(px, py) for px, py in arc_points]
                self._draw_joined_polyline(transformed, style)

    def _draw_joined_polyline(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
    ) -> None:
        if len(points) < 2 or style.stroke_color is None:
            return
        self.draw.line(
            points,
            fill=style.stroke_color.to_tuple(),
            width=_stroke_width(style, self.pixel_density),
            joint="curve",
        )

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
        if dw <= 0 or dh <= 0:
            return
        source_image = image.pillow
        if source is not None:
            sx, sy, sw, sh = source
            if sw <= 0 or sh <= 0:
                return
            source_image = source_image.crop((sx, sy, sx + sw, sy + sh))
        if source_image.width <= 0 or source_image.height <= 0:
            return
        image_to_canvas = (
            self._physical_transform(transform)
            .multiply(Matrix2D.translation(dx, dy))
            .multiply(
                Matrix2D.scaling(
                    dw / source_image.width,
                    dh / source_image.height,
                )
            )
        )
        if (
            abs(image_to_canvas.a * image_to_canvas.d - image_to_canvas.b * image_to_canvas.c)
            < _AFFINE_EPSILON
        ):
            return
        if abs(image_to_canvas.b) < _AFFINE_EPSILON and abs(image_to_canvas.c) < _AFFINE_EPSILON:
            cache_key = (id(image), image.version, source)
            self._draw_axis_aligned_image(source_image, image_to_canvas, style, cache_key)
            return

        def draw_image_op() -> None:
            canvas_to_image = image_to_canvas.inverse()
            transformed = source_image.transform(
                self.image.size,
                PILImage.Transform.AFFINE,
                (
                    canvas_to_image.a,
                    canvas_to_image.c,
                    canvas_to_image.e,
                    canvas_to_image.b,
                    canvas_to_image.d,
                    canvas_to_image.f,
                ),
                resample=PILImage.Resampling.BICUBIC,
                fillcolor=(0, 0, 0, 0),
            )
            self.image.alpha_composite(transformed)
            self.draw = ImageDraw.Draw(self.image, "RGBA")

        self._draw_with_style(style, draw_image_op)

    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if style.fill_color is None:
            return
        font_size = max(1, int(round(style.text_size * self.pixel_density)))
        font = style.text_font.pillow_font(font_size)
        font_key = (style.text_font.path, style.text_font.name, font_size)
        lines = str(value).splitlines() or [""]
        physical_transform = self._physical_transform(transform)
        for line_index, line in enumerate(lines):
            px, py = physical_transform.transform_point(
                x,
                y + line_index * style.text_leading,
            )
            bbox = self.draw.textbbox((0, 0), line, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            if style.text_align_x == c.CENTER:
                px -= width / 2
            elif style.text_align_x == c.RIGHT:
                px -= width
            if style.text_align_y == c.CENTER:
                py -= height / 2
            elif style.text_align_y == c.BOTTOM:
                py -= height
            elif style.text_align_y == c.BASELINE:
                py -= self.text_ascent(style)
            self._draw_text_line(line, px, py, font, font_key, style)

    def _draw_text_line(
        self,
        line: str,
        x: float,
        y: float,
        font,
        font_key: tuple[object, ...],
        style: StyleState,
    ) -> None:
        fill_color = style.fill_color
        if fill_color is None:
            return
        overlay, offset_x, offset_y = self._cached_text_line(
            line, font, font_key, fill_color.to_tuple()
        )
        self_x = floor(x) + offset_x
        self_y = floor(y) + offset_y
        if style.erasing:
            self._erase_region(overlay, self_x, self_y)
        else:
            self._composite_region(overlay, self_x, self_y, style.blend_mode)

    def _cached_text_line(
        self,
        line: str,
        font,
        font_key: tuple[object, ...],
        fill: tuple[int, int, int, int],
    ) -> tuple[PILImage.Image, int, int]:
        cache_key = (*font_key, line, fill)
        cached = self._text_line_cache.get(cache_key)
        if cached is not None:
            return cached
        bbox = self.draw.textbbox((0, 0), line, font=font)
        left = floor(bbox[0])
        top = floor(bbox[1])
        right = ceil(bbox[2])
        bottom = ceil(bbox[3])
        if right <= left or bottom <= top:
            overlay = PILImage.new("RGBA", (1, 1), (0, 0, 0, 0))
            return overlay, 0, 0
        overlay = PILImage.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        draw.text((-left, -top), line, fill=fill, font=font)
        if len(self._text_line_cache) > 256:
            self._text_line_cache.clear()
        cached = (overlay, left, top)
        self._text_line_cache[cache_key] = cached
        return cached

    def text_width(self, value: str, style: StyleState) -> float:
        font = style.text_font.pillow_font(style.text_size * self.pixel_density)
        lines = str(value).splitlines() or [""]
        return max(
            (self.draw.textlength(line, font=font) / self.pixel_density for line in lines),
            default=0.0,
        )

    def text_ascent(self, style: StyleState) -> float:
        font = style.text_font.pillow_font(style.text_size * self.pixel_density)
        getmetrics = getattr(font, "getmetrics", None)
        if callable(getmetrics):
            ascent, _descent = cast(tuple[int, int], getmetrics())
            return ascent / self.pixel_density
        return style.text_size * 0.8

    def text_descent(self, style: StyleState) -> float:
        font = style.text_font.pillow_font(style.text_size * self.pixel_density)
        getmetrics = getattr(font, "getmetrics", None)
        if callable(getmetrics):
            _ascent, descent = cast(tuple[int, int], getmetrics())
            return descent / self.pixel_density
        return style.text_size * 0.2

    def load_pixels(self) -> list[int]:
        return list(self.image.tobytes())

    def update_pixels(self, pixels: Sequence[int]) -> None:
        expected = self.physical_width * self.physical_height * 4
        if len(pixels) != expected:
            raise ArgumentValidationError(
                f"Pixel buffer length must be {expected}, got {len(pixels)}."
            )
        self.image = PILImage.frombytes(
            "RGBA",
            (self.physical_width, self.physical_height),
            bytes(pixels),
        )
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def save(self, path: str | Path) -> None:
        self.image.save(path)

    def get_image(self) -> PILImage.Image:
        return self.image

    def _draw_axis_aligned_image(
        self,
        source_image: PILImage.Image,
        image_to_canvas: Matrix2D,
        style: StyleState,
        cache_key: tuple[object, ...],
    ) -> None:
        left = image_to_canvas.e
        top = image_to_canvas.f
        right = image_to_canvas.a * source_image.width + image_to_canvas.e
        bottom = image_to_canvas.d * source_image.height + image_to_canvas.f
        dx = int(round(min(left, right)))
        dy = int(round(min(top, bottom)))
        dw = int(round(abs(right - left)))
        dh = int(round(abs(bottom - top)))
        if dw <= 0 or dh <= 0:
            return
        flip_x = right < left
        flip_y = bottom < top
        image = source_image
        if flip_x:
            image = image.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
        if flip_y:
            image = image.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
        resized = self._cached_resized_image(image, (*cache_key, dw, dh, flip_x, flip_y), dw, dh)
        if style.erasing:
            self._erase_region(resized, dx, dy)
        else:
            self._composite_region(resized, dx, dy, style.blend_mode)

    def _cached_resized_image(
        self, image: PILImage.Image, cache_key: tuple[object, ...], width: int, height: int
    ) -> PILImage.Image:
        cached = self._resized_image_cache.get(cache_key)
        if cached is not None:
            return cached
        if len(self._resized_image_cache) > 128:
            self._resized_image_cache.clear()
        resized = image.resize((width, height), PILImage.Resampling.BICUBIC)
        self._resized_image_cache[cache_key] = resized
        return resized

    def blend_region(
        self,
        source_image: PILImage.Image | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: str,
    ) -> None:
        sx, sy, sw, sh = source
        dx, dy, dw, dh = destination
        if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
            return
        if source_image is None:
            sx, sy, sw, sh = self._scale_rect(source)
            image = self.image
        else:
            image = source_image.convert("RGBA")
        dx, dy, dw, dh = self._scale_rect(destination)
        crop = image.crop((sx, sy, sx + sw, sy + sh)).resize((dw, dh), PILImage.Resampling.LANCZOS)
        self._composite_region(crop, dx, dy, mode)

    def _scale_rect(self, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        x, y, width, height = rect
        return (
            int(round(x * self.pixel_density)),
            int(round(y * self.pixel_density)),
            int(round(width * self.pixel_density)),
            int(round(height * self.pixel_density)),
        )

    def _draw_with_style(self, style: StyleState, draw_op) -> None:
        original = self.image
        original_draw = self.draw
        overlay = PILImage.new("RGBA", self.image.size, (0, 0, 0, 0))
        self.image = overlay
        self.draw = ImageDraw.Draw(overlay, "RGBA")
        draw_op()
        self.image = original
        self.draw = original_draw
        if style.erasing:
            self._erase_overlay(overlay)
        else:
            self._composite_overlay(overlay, style.blend_mode)

    def _erase_overlay(self, overlay: PILImage.Image) -> None:
        bbox = overlay.getchannel("A").getbbox()
        if bbox is None:
            return
        self._erase_region(overlay.crop(bbox), bbox[0], bbox[1])

    def _erase_region(self, overlay: PILImage.Image, dx: int, dy: int) -> None:
        clipped = self._clip_region_to_canvas(overlay, dx, dy)
        if clipped is None:
            return
        overlay, dx, dy = clipped
        base_region = self.image.crop((dx, dy, dx + overlay.width, dy + overlay.height))
        base_r, base_g, base_b, base_a = base_region.split()
        overlay_alpha = overlay.getchannel("A")
        new_alpha = ImageChops.subtract(base_a, overlay_alpha)
        erased = PILImage.merge("RGBA", (base_r, base_g, base_b, new_alpha))
        self.image.paste(erased, (dx, dy))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def _composite_overlay(self, overlay: PILImage.Image, mode: str) -> None:
        bbox = overlay.getchannel("A").getbbox()
        if bbox is None:
            return
        self._composite_region(overlay.crop(bbox), bbox[0], bbox[1], mode)

    def _composite_region(self, overlay: PILImage.Image, dx: int, dy: int, mode: str) -> None:
        bbox = overlay.getchannel("A").getbbox()
        if bbox is None:
            return
        if bbox != (0, 0, overlay.width, overlay.height):
            overlay = overlay.crop(bbox)
            dx += bbox[0]
            dy += bbox[1]
        clipped = self._clip_region_to_canvas(overlay, dx, dy)
        if clipped is None:
            return
        overlay, dx, dy = clipped
        if mode == c.BLEND:
            self.image.alpha_composite(overlay, (dx, dy))
        elif mode == c.REPLACE:
            self.image.paste(overlay, (dx, dy), overlay.getchannel("A"))
        else:
            bbox = (dx, dy, dx + overlay.width, dy + overlay.height)
            base_region = self.image.crop(bbox)
            blended = self._blend_images(base_region, overlay, mode)
            composited = PILImage.composite(blended, base_region, overlay.getchannel("A"))
            self.image.paste(composited, (dx, dy))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def _clip_region_to_canvas(
        self, image: PILImage.Image, dx: int, dy: int
    ) -> tuple[PILImage.Image, int, int] | None:
        left = max(0, dx)
        top = max(0, dy)
        right = min(self.physical_width, dx + image.width)
        bottom = min(self.physical_height, dy + image.height)
        if right <= left or bottom <= top:
            return None
        if (left, top, right, bottom) == (dx, dy, dx + image.width, dy + image.height):
            return image, dx, dy
        source_box = (left - dx, top - dy, right - dx, bottom - dy)
        return image.crop(source_box), left, top

    def _blend_images(
        self, base: PILImage.Image, overlay: PILImage.Image, mode: str
    ) -> PILImage.Image:
        base_rgb = base.convert("RGB")
        overlay_rgb = overlay.convert("RGB")
        if mode == c.ADD:
            rgb = ImageChops.add(base_rgb, overlay_rgb)
        elif mode == c.DARKEST:
            rgb = ImageChops.darker(base_rgb, overlay_rgb)
        elif mode == c.LIGHTEST:
            rgb = ImageChops.lighter(base_rgb, overlay_rgb)
        elif mode == c.DIFFERENCE:
            rgb = ImageChops.difference(base_rgb, overlay_rgb)
        elif mode == c.EXCLUSION:
            rgb = _exclusion(base_rgb, overlay_rgb)
        elif mode == c.MULTIPLY:
            rgb = ImageChops.multiply(base_rgb, overlay_rgb)
        elif mode == c.SCREEN:
            rgb = ImageChops.screen(base_rgb, overlay_rgb)
        else:
            raise ArgumentValidationError(f"Unsupported blend mode {mode!r}.")
        result = rgb.convert("RGBA")
        result.putalpha(base.getchannel("A"))
        return result

    def _physical_transform(self, transform: Matrix2D) -> Matrix2D:
        return Matrix2D.scaling(self.pixel_density).multiply(transform)


def _angle_steps(count: int):
    return (2 * pi * index / count for index in range(count))


def _exclusion(base: PILImage.Image, overlay: PILImage.Image) -> PILImage.Image:
    base_bytes = base.tobytes()
    overlay_bytes = overlay.tobytes()
    out = bytes(
        max(0, min(255, b + o - 2 * b * o // 255))
        for b, o in zip(base_bytes, overlay_bytes, strict=True)
    )
    return PILImage.frombytes("RGB", base.size, out)
