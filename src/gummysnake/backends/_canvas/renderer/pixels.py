# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Pixel and export operations for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.exceptions import ArgumentValidationError


class CanvasRendererPixelsMixin:
    def load_pixels(self) -> list[int]:
        self._flush_line_batch()
        self._count("pixel_readbacks")
        pixels = self._call("pixel readback", self._require_canvas().load_pixels)
        return list(pixels)

    def load_pixel_bytes(self) -> bytes:
        self._flush_line_batch()
        self._count("pixel_readbacks")
        callback = getattr(self._require_canvas(), "load_pixel_bytes", None)
        if callable(callback):
            return bytes(self._call("pixel byte readback", callback))
        return bytes(self._call("pixel readback", self._require_canvas().load_pixels))

    def load_pixel_region(self, x: int, y: int, width: int, height: int) -> bytes:
        self._flush_line_batch()
        self._count("pixel_readbacks")
        return bytes(
            self._call(
                "pixel region readback",
                self._require_canvas().load_pixel_region,
                int(x),
                int(y),
                int(width),
                int(height),
            )
        )

    def update_pixels(self, pixels: Sequence[int] | Buffer) -> None:
        self._flush_line_batch()
        payload = self._pixel_payload(pixels)
        self._count("pixel_uploads")
        self._call("pixel upload", self._require_canvas().update_pixels, payload)

    def update_pixel_region(
        self,
        pixels: Sequence[int] | Buffer,
        width: int,
        height: int,
        x: int,
        y: int,
        *,
        alpha_composite: bool = True,
    ) -> None:
        self._flush_line_batch()
        payload = self._pixel_payload(pixels)
        self._count("pixel_uploads")
        self._call(
            "pixel region upload",
            self._require_canvas().update_pixel_region,
            payload,
            int(width),
            int(height),
            int(x),
            int(y),
            alpha_composite,
        )

    def filter_pixels(self, mode: c.ImageFilter, value: float | None = None) -> None:
        self._flush_line_batch()
        self._count("cpu_fallbacks")
        self._count("pixel_uploads")
        self._call("pixel filter", self._require_canvas().filter_pixels, mode.value, value)

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None:
        self._flush_line_batch()
        self._count("cpu_fallbacks")
        self._count("pixel_uploads")
        if isinstance(source_image, Image):
            self._blend_image(
                source_image.to_rgba_bytes(),
                source_image.width,
                source_image.height,
                source,
                destination,
                mode,
            )
            return
        if source_image is None:
            self._blend_image(None, None, None, source, destination, mode)
            return
        convert = getattr(source_image, "convert", None)
        if callable(convert):
            source_image = convert("RGBA")
        width = getattr(source_image, "width", None)
        height = getattr(source_image, "height", None)
        tobytes = getattr(source_image, "tobytes", None)
        if not isinstance(width, int) or not isinstance(height, int) or not callable(tobytes):
            raise ArgumentValidationError("blend_region() source image must expose RGBA pixels.")
        self._blend_image(tobytes(), width, height, source, destination, mode)

    def save(self, path: str | Path) -> None:
        self._flush_line_batch()
        self._call("canvas export", self._require_canvas().save, str(path))

    @staticmethod
    def _pixel_payload(pixels: Sequence[int] | Buffer) -> bytes:
        try:
            return bytes(pixels)
        except ValueError as exc:
            raise ArgumentValidationError(
                "Pixel values must be integers between 0 and 255."
            ) from exc

    def _blend_image(
        self,
        pixels: bytes | None,
        width: int | None,
        height: int | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None:
        self._call(
            "region blending",
            self._require_canvas().blend_region,
            pixels,
            width,
            height,
            source,
            destination,
            mode,
        )
