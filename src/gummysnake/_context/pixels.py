"""Pixel, canvas export, and compositing methods for SketchContext."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import Any

from gummysnake import constants as c
from gummysnake._context.helpers import blend_args, copy_ints, rgba_bytes
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.exceptions import ArgumentValidationError


class PixelContextMixin:
    renderer: Any
    state: Any
    backend: Any
    pixels: Sequence[int]

    def _record_performance_diagnostic(self, _name: str) -> None: ...

    def _mark_style_changed(self) -> None: ...

    def load_pixels(self) -> list[int]:
        self._record_performance_diagnostic("pixel_readback")
        self._record_performance_diagnostic("pixel_list_conversion")
        pixels = self.renderer.load_pixels()
        self.pixels = pixels
        return pixels

    def load_pixel_bytes(self) -> bytes:
        self._record_performance_diagnostic("pixel_readback")
        return self.renderer.load_pixel_bytes()

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        self._record_performance_diagnostic("pixel_upload")
        if pixels is not None:
            if isinstance(pixels, Sequence) and not isinstance(
                pixels, bytes | bytearray | memoryview
            ):
                self._record_performance_diagnostic("pixel_list_conversion")
            self.pixels = pixels if isinstance(pixels, Sequence) else bytes(pixels)
        if not self.pixels:
            self.load_pixels()
        self.renderer.update_pixels(self.pixels)

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ):
        if x is None and y is None:
            return self._canvas_image()
        if x is None or y is None:
            raise ArgumentValidationError("get() requires both x and y.")
        density = self.state.canvas.pixel_density
        px = int(round(x * density))
        py = int(round(y * density))
        if w is None and h is None:
            self._record_performance_diagnostic("pixel_readback")
            pixel = self.renderer.load_pixel_region(px, py, 1, 1)
            return Color(*pixel[:4])
        if w is None or h is None:
            raise ArgumentValidationError("get() requires both width and height for regions.")
        pw = int(round(w * density))
        ph = int(round(h * density))
        if pw <= 0 or ph <= 0:
            raise ArgumentValidationError("Image region dimensions must be positive.")
        self._record_performance_diagnostic("pixel_readback")
        return Image(pw, ph, self.renderer.load_pixel_region(px, py, pw, ph))

    def set(
        self,
        x: int,
        y: int,
        value: Color | tuple[int, int, int] | tuple[int, int, int, int] | Image,
    ) -> None:
        density = self.state.canvas.pixel_density
        px = int(round(x * density))
        py = int(round(y * density))
        self._record_performance_diagnostic("pixel_upload")
        if isinstance(value, Image):
            self.renderer.update_pixel_region(
                value.to_rgba_bytes(),
                value.width,
                value.height,
                px,
                py,
                alpha_composite=True,
            )
            self.pixels = []
            return
        payload = rgba_bytes(value)
        self.renderer.update_pixel_region(
            payload,
            1,
            1,
            px,
            py,
            alpha_composite=False,
        )
        self.pixels = []

    def copy(self, *args: object):
        if len(args) == 0:
            return self.get()
        if isinstance(args[0], Image):
            if len(args) != 9:
                raise ArgumentValidationError(
                    "copy(image, sx, sy, sw, sh, dx, dy, dw, dh) requires nine arguments."
                )
            source = args[0]
            sx, sy, sw, sh, dx, dy, dw, dh = copy_ints(args[1:])
            patch = source.copy(sx, sy, sw, sh, 0, 0, dw, dh)
            self.set(dx, dy, patch)
            return None
        if len(args) == 4:
            sx, sy, sw, sh = copy_ints(args)
            return self.get(sx, sy, sw, sh)
        if len(args) == 8:
            sx, sy, sw, sh, dx, dy, dw, dh = copy_ints(args)
            patch = self.get(sx, sy, sw, sh)
            if not isinstance(patch, Image):
                raise ArgumentValidationError("copy() source region must produce an Image.")
            patch.resize(dw, dh)
            self.set(dx, dy, patch)
            return None
        raise ArgumentValidationError("copy() accepts 0, 4, 8, or image plus 8 numeric arguments.")

    def filter(self, mode: c.ImageFilter, value: float | None = None) -> None:
        self._record_performance_diagnostic("cpu_compositing_fallback")
        self._record_performance_diagnostic("pixel_upload")
        self.renderer.filter_pixels(mode, value)
        self.pixels = []

    def _canvas_image(self) -> Image:
        self._record_performance_diagnostic("cpu_compositing_fallback")
        pixels = self.load_pixels()
        return Image(
            self.state.canvas.physical_width,
            self.state.canvas.physical_height,
            bytes(pixels),
        )

    def pixel_array(self) -> list[list[tuple[int, int, int, int]]]:
        pixels = self.pixels or self.load_pixels()
        width = self.state.canvas.physical_width
        rows: list[list[tuple[int, int, int, int]]] = []
        for row_start in range(0, len(pixels), width * 4):
            row: list[tuple[int, int, int, int]] = []
            for index in range(row_start, row_start + width * 4, 4):
                row.append((pixels[index], pixels[index + 1], pixels[index + 2], pixels[index + 3]))
            rows.append(row)
        return rows

    def save_canvas(
        self,
        path: str | Path,
        *,
        extension: str | None = None,
        overwrite: bool = True,
    ) -> Path:
        output = Path(path)
        if output.name in {"", "."}:
            raise ArgumentValidationError("save_canvas() requires a file path, not a directory.")
        if extension is not None:
            suffix = extension if extension.startswith(".") else f".{extension}"
            output = output.with_suffix(suffix.lower())
        elif output.suffix == "":
            output = output.with_suffix(".png")
        if output.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
            raise ArgumentValidationError(f"Unsupported canvas export format {output.suffix!r}.")
        if output.exists() and not overwrite:
            raise ArgumentValidationError(f"Refusing to overwrite existing file: {output!s}.")
        output.parent.mkdir(parents=True, exist_ok=True)
        self.renderer.save(output)
        return output

    def blend_mode(self, mode: c.BlendMode) -> None:
        if mode not in self.backend.capabilities.blend_modes:
            raise ArgumentValidationError(
                f"Unsupported blend mode {mode!r} for backend {self.backend.name!r}."
            )
        self.state.style.blend_mode = mode
        self._mark_style_changed()

    def blend(self, *args: object) -> None:
        parsed = blend_args(
            args,
            self.backend.capabilities.blend_modes,
            backend_name=self.backend.name,
        )
        self.renderer.blend_region(
            parsed.source_image,
            parsed.source_rect,
            parsed.dest_rect,
            parsed.mode,
        )

    def erase(self) -> None:
        self.state.style.erasing = True
        self._mark_style_changed()

    def no_erase(self) -> None:
        self.state.style.erasing = False
        self._mark_style_changed()
