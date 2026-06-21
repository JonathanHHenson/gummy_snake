# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Image drawing for the Rust canvas renderer."""

from __future__ import annotations

from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


class CanvasRendererImagesMixin:
    def draw_image(
        self,
        image: Image | CanvasImage,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: StyleState,
        transform: Matrix2D,
        *,
        source: tuple[int, int, int, int] | None = None,
        cache: bool = True,
    ) -> None:
        self._flush_line_batch()
        if isinstance(image, CanvasImage):
            self._draw_rust_image(image._rust_image, dx, dy, dw, dh, style, transform, source)
            return
        if image.rust_image is not None:
            self._draw_rust_image(
                image.rust_image._rust_image,
                dx,
                dy,
                dw,
                dh,
                style,
                transform,
                source,
            )
            return
        image_key = image.cache_key
        cached_version = self._image_cache_versions.get(image_key) if cache else None
        image_pixels = None if cached_version == image.version else image.to_rgba_bytes()
        if image_pixels is None:
            self._count("image_cache_hits")
            self._count("texture_cache_hits")
        else:
            self._count("image_cache_misses")
            self._count("texture_uploads")
        callback = getattr(self._require_canvas(), "draw_cached_image", None)
        if cache and callable(callback):
            self._count("gpu_draws")
            self._call(
                "image drawing",
                callback,
                image_key,
                image.version,
                image_pixels,
                image.width,
                image.height,
                dx,
                dy,
                dw,
                dh,
                self._style_payload(style),
                self._matrix_payload(transform),
                source,
            )
            self._remember_image_cache_version(image_key, image.version)
            return
        self._count("cpu_fallbacks")
        self._count("pixel_uploads")
        self._call(
            "image drawing",
            self._require_canvas().draw_image,
            image_pixels if image_pixels is not None else image.to_rgba_bytes(),
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            self._style_payload(style),
            self._matrix_payload(transform),
            source,
        )

    def _draw_rust_image(
        self,
        rust_image: object,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: StyleState,
        transform: Matrix2D,
        source: tuple[int, int, int, int] | None,
    ) -> None:
        self._count("gpu_draws")
        self._call(
            "image drawing",
            self._require_canvas().draw_canvas_image,
            rust_image,
            dx,
            dy,
            dw,
            dh,
            self._style_payload(style),
            self._matrix_payload(transform),
            source,
        )
