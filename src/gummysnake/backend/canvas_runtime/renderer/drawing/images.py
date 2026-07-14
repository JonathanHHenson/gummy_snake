"""Image drawing for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake.assets.image import CanvasImage, Image
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost, MatrixPayload
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


def _same_image_batch_style(
    current: dict[str, object] | None,
    next_style: dict[str, object],
) -> bool:
    if current is None:
        return False
    ignored = {"_style_cache_key", "_style_revision"}
    return all(
        current.get(key) == value for key, value in next_style.items() if key not in ignored
    ) and all(key in next_style or key in ignored for key in current)


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
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        _renderer(self)._flush_model_batch()
        _renderer(self)._flush_text_batch()
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

    def _queue_fast_rust_image(
        self,
        rust_image: object,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: dict[str, object],
        matrix: MatrixPayload,
    ) -> None:
        """Append a stable Rust handle without materializing its RGBA payload in Python."""
        renderer = _renderer(self)
        if renderer._image_batch and not _same_image_batch_style(
            renderer._image_batch.style, style
        ):
            renderer._flush_image_batch()
        if not renderer._image_batch:
            renderer._flush_line_batch_only()
            renderer._flush_primitive_batch_only()
            renderer._flush_model_batch()
            renderer._flush_text_batch()
        renderer._image_batch.append(rust_image, dx, dy, dw, dh, None, matrix)
        renderer._image_batch.style = style

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
        renderer = _renderer(self)
        renderer._require_canvas_method(
            "batch_canvas_images_packed",
            "typed image command recording",
        )
        renderer._flush_line_batch_only()
        renderer._flush_primitive_batch_only()
        renderer._flush_model_batch()
        style_payload = renderer._style_payload(style)
        matrix_payload = renderer._matrix_payload(transform)
        if renderer._image_batch and not _same_image_batch_style(
            renderer._image_batch.style,
            style_payload,
        ):
            renderer._flush_image_batch()
        renderer._image_batch.append(
            rust_image,
            dx,
            dy,
            dw,
            dh,
            source,
            matrix_payload,
        )
        renderer._image_batch.style = style_payload

    def _flush_image_batch(self) -> None:
        renderer = _renderer(self)
        if not renderer._image_batch:
            return
        records, images, style, record_count = renderer._image_batch.drain()
        if style is None or record_count == 0:
            return
        renderer._count("gpu_draws", record_count)
        renderer._count("image_batch_records", record_count)
        renderer._count("image_batch_flushes")
        renderer._max_count("image_batch_max_records", record_count)
        renderer._call(
            "typed batched image drawing",
            renderer._require_canvas_method(
                "batch_canvas_images_packed",
                "typed image command recording",
            ),
            records,
            images,
            style,
        )
