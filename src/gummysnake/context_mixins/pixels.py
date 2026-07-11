"""Pixel, canvas export, and compositing methods for SketchContext."""

from __future__ import annotations

from collections.abc import Buffer, Callable, Sequence
from pathlib import Path
from typing import Any, overload

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.context_mixins.pixel_support.compositing import blend as _blend_impl
from gummysnake.context_mixins.pixel_support.compositing import blend_mode as _blend_mode_impl
from gummysnake.context_mixins.pixel_support.compositing import erase as _erase_impl
from gummysnake.context_mixins.pixel_support.compositing import filter_pixels as _filter_pixels_impl
from gummysnake.context_mixins.pixel_support.compositing import no_erase as _no_erase_impl
from gummysnake.context_mixins.pixel_support.exports import save_canvas as _save_canvas_impl
from gummysnake.context_mixins.pixel_support.exports import save_frames as _save_frames_impl
from gummysnake.context_mixins.pixel_support.exports import save_gif as _save_gif_impl
from gummysnake.context_mixins.pixel_support.io import canvas_image as _canvas_image_impl
from gummysnake.context_mixins.pixel_support.io import copy_pixels as _copy_pixels_impl
from gummysnake.context_mixins.pixel_support.io import get_pixel as _get_pixel_impl
from gummysnake.context_mixins.pixel_support.io import load_pixel_bytes as _load_pixel_bytes_impl
from gummysnake.context_mixins.pixel_support.io import load_pixels as _load_pixels_impl
from gummysnake.context_mixins.pixel_support.io import pixel_array as _pixel_array_impl
from gummysnake.context_mixins.pixel_support.io import set_pixel as _set_pixel_impl
from gummysnake.context_mixins.pixel_support.io import (
    update_dirty_pixel_range as _update_dirty_pixel_range_impl,
)
from gummysnake.context_mixins.pixel_support.io import update_pixels as _update_pixels_impl
from gummysnake.core.color import Color
from gummysnake.core.pixels import FrameSaveInfo, PixelBuffer


class PixelContextMixin:
    renderer: Any
    state: Any
    backend: Any
    pixels: Sequence[int] | Buffer
    _last_pixel_bytes: bytes | None

    def _record_performance_diagnostic(self, _name: str) -> None: ...

    def _mark_style_changed(self) -> None: ...

    def load_pixels(self) -> PixelBuffer:
        return _load_pixels_impl(self)

    def load_pixel_bytes(self) -> bytes:
        return _load_pixel_bytes_impl(self)

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        _update_pixels_impl(self, pixels)

    def _update_dirty_pixel_range(
        self,
        pixels: Sequence[int] | Buffer,
        dirty: tuple[int, int],
    ) -> bool:
        return _update_dirty_pixel_range_impl(self, pixels, dirty)

    @overload
    def get(self) -> Image: ...

    @overload
    def get(self, x: int, y: int) -> Color: ...

    @overload
    def get(self, x: int, y: int, w: int, h: int) -> Image: ...

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ) -> Color | Image:
        return _get_pixel_impl(self, x, y, w, h)

    def set(
        self,
        x: int,
        y: int,
        value: Color | tuple[int, int, int] | tuple[int, int, int, int] | Image,
    ) -> None:
        _set_pixel_impl(self, x, y, value)

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
        return _copy_pixels_impl(self, *args)

    def filter(self, mode: c.ImageFilter, value: float | None = None) -> None:
        _filter_pixels_impl(self, mode, value)

    def _canvas_image(self) -> Image:
        return _canvas_image_impl(self)

    def pixel_array(self) -> list[list[tuple[int, int, int, int]]]:
        return _pixel_array_impl(self)

    def save_canvas(
        self,
        path: str | Path,
        *,
        extension: str | None = None,
        overwrite: bool = True,
    ) -> Path:
        return _save_canvas_impl(self, path, extension=extension, overwrite=overwrite)

    def save_frames(
        self,
        path_pattern: str | Path,
        *,
        extension: str = "png",
        count: int = 1,
        duration: float | None = None,
        callback: Callable[[list[FrameSaveInfo]], None] | None = None,
        overwrite: bool = True,
    ) -> list[FrameSaveInfo]:
        return _save_frames_impl(
            self,
            path_pattern,
            extension=extension,
            count=count,
            duration=duration,
            callback=callback,
            overwrite=overwrite,
        )

    def save_gif(
        self,
        path: str | Path,
        *,
        count: int = 1,
        duration: float | None = None,
        overwrite: bool = True,
    ) -> Path:
        return _save_gif_impl(self, path, count=count, duration=duration, overwrite=overwrite)

    def blend_mode(self, mode: c.BlendMode) -> None:
        _blend_mode_impl(self, mode)

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
        _blend_impl(self, *args)

    def erase(self) -> None:
        _erase_impl(self)

    def no_erase(self) -> None:
        _no_erase_impl(self)
