"""Pixel, canvas export, and compositing methods for SketchContext."""

from __future__ import annotations

from collections.abc import Buffer, Callable, Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake._context.helpers import blend_args, copy_ints, rgba_bytes
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class PixelContextMixin:
    renderer: Any
    state: Any
    backend: Any
    pixels: Sequence[int]
    _last_pixel_bytes: bytes | None

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
        pixels = self.renderer.load_pixel_bytes()
        self._last_pixel_bytes = pixels
        return pixels

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        self._record_performance_diagnostic("pixel_upload")
        if pixels is not None:
            if (
                isinstance(pixels, memoryview)
                and isinstance(pixels.obj, bytes)
                and pixels.obj is getattr(self, "_last_pixel_bytes", None)
            ):
                return
            if isinstance(pixels, bytes) and pixels is getattr(self, "_last_pixel_bytes", None):
                return
            dirty_range = getattr(pixels, "dirty_range", None)
            if callable(dirty_range):
                dirty = dirty_range()
                if (
                    isinstance(dirty, tuple)
                    and len(dirty) == 2
                    and isinstance(dirty[0], int)
                    and isinstance(dirty[1], int)
                    and self._update_dirty_pixel_range(pixels, dirty)
                ):
                    clear_dirty = getattr(pixels, "clear_dirty", None)
                    if callable(clear_dirty):
                        clear_dirty()
                    self.pixels = pixels if isinstance(pixels, Sequence) else bytes(pixels)
                    return
            if isinstance(pixels, Sequence) and not isinstance(
                pixels, bytes | bytearray | memoryview
            ):
                self._record_performance_diagnostic("pixel_list_conversion")
            self.pixels = pixels if isinstance(pixels, Sequence) else bytes(pixels)
        if not self.pixels:
            self.load_pixels()
        self.renderer.update_pixels(self.pixels)

    def _update_dirty_pixel_range(
        self,
        pixels: Sequence[int] | Buffer,
        dirty: tuple[int, int],
    ) -> bool:
        start, end = dirty
        if end <= start:
            return True
        width = self.state.canvas.physical_width
        height = self.state.canvas.physical_height
        total = width * height * 4
        pixel_data = cast(Any, pixels)
        if width <= 0 or len(pixel_data) != total:
            return False
        start_pixel = max(0, start // 4)
        end_pixel = min(width * height, (end + 3) // 4)
        if end_pixel <= start_pixel:
            return True
        start_row, start_col = divmod(start_pixel, width)
        end_row, end_col = divmod(end_pixel - 1, width)
        payload = memoryview(cast(Buffer, pixels))
        if start_row == end_row:
            region_x = start_col
            region_y = start_row
            region_width = end_col - start_col + 1
            byte_start = (start_row * width + start_col) * 4
            byte_end = byte_start + region_width * 4
            region = payload[byte_start:byte_end]
            self.renderer.update_pixel_region(
                region,
                region_width,
                1,
                region_x,
                region_y,
                alpha_composite=False,
            )
            return True
        region_y = start_row
        region_height = end_row - start_row + 1
        byte_start = start_row * width * 4
        byte_end = (end_row + 1) * width * 4
        region = payload[byte_start:byte_end]
        self.renderer.update_pixel_region(
            region,
            width,
            region_height,
            0,
            region_y,
            alpha_composite=False,
        )
        return True

    @overload
    def get(self) -> Image: ...

    @overload
    def get(self, x: int, y: int) -> Color: ...

    @overload
    def get(self, x: int, y: int, w: int, h: int) -> Image: ...

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ) -> Color | Image:
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
        set_pixel_rgba = getattr(self.renderer, "set_pixel_rgba", None)
        if callable(set_pixel_rgba):
            set_pixel_rgba(px, py, (payload[0], payload[1], payload[2], payload[3]))
        else:
            self.renderer.update_pixel_region(
                payload,
                1,
                1,
                px,
                py,
                alpha_composite=False,
            )
        self.pixels = []

    @overload
    def copy(self) -> Image: ...

    @overload
    def copy(self, sx: int, sy: int, sw: int, sh: int, /) -> Image: ...

    @overload
    def copy(
        self, sx: int, sy: int, sw: int, sh: int, dx: int, dy: int, dw: int, dh: int, /
    ) -> None: ...

    @overload
    def copy(
        self,
        image: Image,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        /,
    ) -> None: ...

    def copy(self, *args: Any) -> Image | None:
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

    def save_frames(
        self,
        path_pattern: str | Path,
        *,
        extension: str = "png",
        count: int = 1,
        duration: float | None = None,
        callback: Callable[[list[dict[str, object]]], object] | None = None,
        overwrite: bool = True,
    ) -> list[dict[str, object]]:
        if count <= 0:
            raise ArgumentValidationError("save_frames() count must be positive.")
        suffix = extension if extension.startswith(".") else f".{extension}"
        frame_duration = (
            1.0 / self.state.timing.target_frame_rate
            if duration is None
            else float(duration) / count
        )
        pattern = str(path_pattern)
        results: list[dict[str, object]] = []
        for index in range(count):
            if "{" in pattern:
                output = Path(
                    pattern.format(
                        index=index,
                        frame=index,
                        frame_count=self.state.timing.frame_count,
                    )
                )
            else:
                stem = Path(pattern)
                output = stem.with_name(f"{stem.stem}_{index:04d}{stem.suffix or suffix}")
            if output.suffix == "":
                output = output.with_suffix(suffix)
            saved = self.save_canvas(output, overwrite=overwrite)
            results.append(
                {
                    "path": saved,
                    "frame": index,
                    "frame_count": self.state.timing.frame_count,
                    "duration": frame_duration,
                }
            )
        if callback is not None:
            callback(results)
        return results

    def save_gif(
        self,
        path: str | Path,
        *,
        count: int = 1,
        duration: float | None = None,
        overwrite: bool = True,
    ) -> Path:
        output = Path(path)
        if output.suffix == "":
            output = output.with_suffix(".gif")
        if output.exists() and not overwrite:
            raise ArgumentValidationError(f"Refusing to overwrite existing file: {output!s}.")
        try:
            pil_image = import_module("PIL.Image")
        except ImportError as exc:
            raise BackendCapabilityError(
                "save_gif() requires the optional media/image dependency that provides Pillow. "
                "Install Gummy Snake with the media extra before exporting animated GIFs."
            ) from exc
        if count <= 0:
            raise ArgumentValidationError("save_gif() count must be positive.")
        frame_duration_ms = int(
            round(
                1000.0 / self.state.timing.target_frame_rate
                if duration is None
                else float(duration) * 1000.0 / count
            )
        )
        pixels = self.load_pixel_bytes()
        size = (self.state.canvas.physical_width, self.state.canvas.physical_height)
        frame = cast(Any, pil_image).frombytes("RGBA", size, pixels)
        frames = [frame.copy() for _ in range(count)]
        output.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(
            output,
            save_all=True,
            append_images=frames[1:],
            duration=frame_duration_ms,
            loop=0,
        )
        return output

    def blend_mode(self, mode: c.BlendMode) -> None:
        if mode not in self.backend.capabilities.blend_modes:
            raise ArgumentValidationError(
                f"Unsupported blend mode {mode!r} for backend {self.backend.name!r}."
            )
        self.state.style.blend_mode = mode
        self._mark_style_changed()

    @overload
    def blend(
        self,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None: ...

    @overload
    def blend(
        self,
        image: Image,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None: ...

    def blend(self, *args: Any) -> None:
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
