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
        current = (
            getattr(_renderer(self)._require_canvas(), "draw_canvas_image_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._call(
                "image drawing",
                current,
                rust_image,
                dx,
                dy,
                dw,
                dh,
                source,
            )
            return
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
