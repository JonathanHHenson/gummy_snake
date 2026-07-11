"""Pixel, image-region, and export forwards for object-mode sketches."""

from __future__ import annotations

from collections.abc import Buffer, Callable, Sequence
from pathlib import Path
from typing import cast, overload

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.core.pixels import FrameSaveInfo, PixelBuffer
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin

type PixelValue = Color | tuple[int, int, int] | tuple[int, int, int, int] | Image
type CopyArg = Image | int


class SketchFacadePixelsMixin(SketchFacadeBaseMixin):
    """Read, update, copy, filter, and export the active object-mode canvas."""

    __facade_doc_topic__ = "Read, modify, copy, filter, or export this sketch's active canvas."

    def load_pixels(self) -> PixelBuffer:
        return self._ctx.load_pixels()

    def load_pixel_bytes(self) -> bytes:
        return self._ctx.load_pixel_bytes()

    def pixels(self) -> Sequence[int]:
        context = self._ctx
        return cast(Sequence[int], context.pixels or context.load_pixels())

    def pixel_array(self) -> list[list[tuple[int, int, int, int]]]:
        return self._ctx.pixel_array()

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        self._ctx.update_pixels(pixels)

    @overload
    def get(self) -> Image: ...

    @overload
    def get(self, x: int, y: int) -> Color: ...

    @overload
    def get(self, x: int, y: int, w: int, h: int) -> Image: ...

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ) -> Color | Image:
        return cast(Color | Image, self._ctx_call("get", x, y, w, h))

    def set(self, x: int, y: int, value: PixelValue) -> None:
        self._ctx.set(x, y, value)

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

    def copy(self, *args: CopyArg) -> Image | None:
        return cast(Image | None, self._ctx_call("copy", *args))

    def filter(self, mode: c.ImageFilter, value: float | None = None) -> None:
        self._ctx.filter(mode, value)

    def save_canvas(
        self, path: str | Path, *, extension: str | None = None, overwrite: bool = True
    ) -> Path:
        return self._ctx.save_canvas(path, extension=extension, overwrite=overwrite)

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
        return self._ctx.save_frames(
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
        return self._ctx.save_gif(path, count=count, duration=duration, overwrite=overwrite)
