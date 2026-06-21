"""Image drawing for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake.assets.image import CanvasImage, Image
from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


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
        _renderer(self)._flush_line_batch()
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
        cached_version = _renderer(self)._image_cache_versions.get(image_key) if cache else None
        image_pixels = None if cached_version == image.version else image.to_rgba_bytes()
        if image_pixels is None:
            _renderer(self)._count("image_cache_hits")
            _renderer(self)._count("texture_cache_hits")
        else:
            _renderer(self)._count("image_cache_misses")
            _renderer(self)._count("texture_uploads")
        callback = getattr(_renderer(self)._require_canvas(), "draw_cached_image", None)
        if cache and callable(callback):
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call(
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
                _renderer(self)._style_payload(style),
                _renderer(self)._matrix_payload(transform),
                source,
            )
            _renderer(self)._remember_image_cache_version(image_key, image.version)
            return
        _renderer(self)._count("cpu_fallbacks")
        _renderer(self)._count("pixel_uploads")
        _renderer(self)._call(
            "image drawing",
            _renderer(self)._require_canvas().draw_image,
            image_pixels if image_pixels is not None else image.to_rgba_bytes(),
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
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
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "image drawing",
            _renderer(self)._require_canvas().draw_canvas_image,
            rust_image,
            dx,
            dy,
            dw,
            dh,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
            source,
        )
