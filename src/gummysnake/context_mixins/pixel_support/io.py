"""Pixel readback, upload, and region helpers for SketchContext."""

from __future__ import annotations

from collections.abc import Buffer, Sequence, Sized
from typing import TYPE_CHECKING, cast

from gummysnake.assets.image import Image
from gummysnake.context_mixins.helpers import IntLike, copy_ints, rgba_bytes
from gummysnake.core.color import Color
from gummysnake.core.pixels import PixelBuffer, dirty_pixel_region
from gummysnake.exceptions import ArgumentValidationError

if TYPE_CHECKING:
    from gummysnake.context_mixins.pixels import PixelContextMixin


type CopyArg = Image | IntLike


def copy_pixel_ints(values: tuple[CopyArg, ...]) -> tuple[int, ...]:
    """Validate and coerce copy() coordinate arguments."""
    if any(isinstance(value, Image) for value in values):
        raise ArgumentValidationError("copy() numeric arguments must be integer-compatible values.")
    return copy_ints(cast(tuple[IntLike, ...], values))


def load_pixels(ctx: PixelContextMixin) -> PixelBuffer:
    """Read the full canvas into the context's mutable pixel buffer."""
    ctx._record_performance_diagnostic("pixel_readback")
    ctx._record_performance_diagnostic("pixel_list_conversion")
    pixels = ctx.renderer.load_pixels()
    ctx.pixels = pixels
    return pixels


def load_pixel_bytes(ctx: PixelContextMixin) -> bytes:
    """Read the full canvas as immutable RGBA bytes."""
    ctx._record_performance_diagnostic("pixel_readback")
    pixels = ctx.renderer.load_pixel_bytes()
    ctx._last_pixel_bytes = pixels
    return pixels


def update_pixels(ctx: PixelContextMixin, pixels: Sequence[int] | Buffer | None = None) -> None:
    """Upload the context pixel buffer, using dirty ranges when available."""
    if pixels is not None:
        if (
            isinstance(pixels, memoryview)
            and isinstance(pixels.obj, bytes)
            and pixels.obj is getattr(ctx, "_last_pixel_bytes", None)
        ):
            return
        if isinstance(pixels, bytes) and pixels is getattr(ctx, "_last_pixel_bytes", None):
            return
        dirty_range = getattr(pixels, "dirty_range", None)
        if callable(dirty_range):
            dirty = dirty_range()
            if (
                isinstance(dirty, tuple)
                and len(dirty) == 2
                and isinstance(dirty[0], int)
                and isinstance(dirty[1], int)
                and ctx._update_dirty_pixel_range(pixels, dirty)
            ):
                clear_dirty = getattr(pixels, "clear_dirty", None)
                if callable(clear_dirty):
                    clear_dirty()
                ctx.pixels = pixels
                return
        if isinstance(pixels, Sequence) and not isinstance(pixels, bytes | bytearray | memoryview):
            ctx._record_performance_diagnostic("pixel_list_conversion")
        ctx.pixels = pixels
    if not ctx.pixels:
        ctx.load_pixels()
    ctx._record_performance_diagnostic("pixel_upload")
    ctx.renderer.update_pixels(ctx.pixels)


def update_dirty_pixel_range(
    ctx: PixelContextMixin,
    pixels: Sequence[int] | Buffer,
    dirty: tuple[int, int],
) -> bool:
    """Upload only the dirty byte range from a pixel buffer when it is valid."""
    if not isinstance(pixels, Sized):
        return False
    buffer_length = len(pixels)
    region = dirty_pixel_region(
        buffer_length,
        int(ctx.state.canvas.physical_width),
        int(ctx.state.canvas.physical_height),
        dirty,
    )
    if not region.valid:
        return False
    if region.empty:
        return True
    try:
        payload = memoryview(cast(Buffer, pixels))[region.byte_slice]
    except TypeError:
        return False
    ctx._record_performance_diagnostic("pixel_region_upload")
    ctx.renderer.update_pixel_region(
        payload,
        region.width,
        region.height,
        region.x,
        region.y,
        alpha_composite=False,
    )
    return True


def get_pixel(
    ctx: PixelContextMixin,
    x: int | None = None,
    y: int | None = None,
    w: int | None = None,
    h: int | None = None,
) -> Color | Image:
    """Read a single pixel, image region, or full-canvas image from the canvas."""
    if x is None and y is None:
        return ctx._canvas_image()
    if x is None or y is None:
        raise ArgumentValidationError("get() requires both x and y.")
    density = ctx.state.canvas.pixel_density
    px = int(round(x * density))
    py = int(round(y * density))
    if w is None and h is None:
        ctx._record_performance_diagnostic("pixel_readback")
        pixel = ctx.renderer.load_pixel_region(px, py, 1, 1)
        return Color(*pixel[:4])
    if w is None or h is None:
        raise ArgumentValidationError("get() requires both width and height for regions.")
    pw = int(round(w * density))
    ph = int(round(h * density))
    if pw <= 0 or ph <= 0:
        raise ArgumentValidationError("Image region dimensions must be positive.")
    ctx._record_performance_diagnostic("pixel_readback")
    return Image(pw, ph, ctx.renderer.load_pixel_region(px, py, pw, ph))


def set_pixel(
    ctx: PixelContextMixin,
    x: int,
    y: int,
    value: Color | tuple[int, int, int] | tuple[int, int, int, int] | Image,
) -> None:
    """Write one color or image patch into the canvas pixel buffer."""
    density = ctx.state.canvas.pixel_density
    px = int(round(x * density))
    py = int(round(y * density))
    ctx._record_performance_diagnostic("pixel_upload")
    if isinstance(value, Image):
        ctx.renderer.update_pixel_region(
            value.to_rgba_bytes(),
            value.width,
            value.height,
            px,
            py,
            alpha_composite=True,
        )
        ctx.pixels = []
        return
    payload = rgba_bytes(value)
    set_pixel_rgba = getattr(ctx.renderer, "set_pixel_rgba", None)
    if callable(set_pixel_rgba):
        set_pixel_rgba(px, py, (payload[0], payload[1], payload[2], payload[3]))
    else:
        ctx.renderer.update_pixel_region(
            payload,
            1,
            1,
            px,
            py,
            alpha_composite=False,
        )
    ctx.pixels = []


def copy_pixels(ctx: PixelContextMixin, *args: CopyArg) -> Image | None:
    """Implement the overloaded copy() pixel-region forms."""
    if len(args) == 0:
        return ctx.get()
    if isinstance(args[0], Image):
        if len(args) != 9:
            raise ArgumentValidationError(
                "copy(image, sx, sy, sw, sh, dx, dy, dw, dh) requires nine arguments."
            )
        source = args[0]
        sx, sy, sw, sh, dx, dy, dw, dh = copy_pixel_ints(args[1:])
        patch = source.copy(sx, sy, sw, sh, 0, 0, dw, dh)
        ctx.set(dx, dy, patch)
        return None
    if len(args) == 4:
        sx, sy, sw, sh = copy_pixel_ints(args)
        return ctx.get(sx, sy, sw, sh)
    if len(args) == 8:
        sx, sy, sw, sh, dx, dy, dw, dh = copy_pixel_ints(args)
        patch = ctx.get(sx, sy, sw, sh)
        if not isinstance(patch, Image):
            raise ArgumentValidationError("copy() source region must produce an Image.")
        patch.resize(dw, dh)
        ctx.set(dx, dy, patch)
        return None
    raise ArgumentValidationError("copy() accepts 0, 4, 8, or image plus 8 numeric arguments.")


def canvas_image(ctx: PixelContextMixin) -> Image:
    """Build an Image snapshot from the current physical canvas pixels."""
    ctx._record_performance_diagnostic("cpu_compositing_fallback")
    pixels = ctx.load_pixels()
    return Image(
        ctx.state.canvas.physical_width,
        ctx.state.canvas.physical_height,
        bytes(pixels),
    )


def pixel_array(ctx: PixelContextMixin) -> list[list[tuple[int, int, int, int]]]:
    """Return loaded pixels as rows of RGBA tuples for compatibility helpers."""
    pixels = cast(Sequence[int], ctx.pixels or ctx.load_pixels())
    width = ctx.state.canvas.physical_width
    rows: list[list[tuple[int, int, int, int]]] = []
    for row_start in range(0, len(pixels), width * 4):
        row: list[tuple[int, int, int, int]] = []
        for index in range(row_start, row_start + width * 4, 4):
            row.append((pixels[index], pixels[index + 1], pixels[index + 2], pixels[index + 3]))
        rows.append(row)
    return rows
