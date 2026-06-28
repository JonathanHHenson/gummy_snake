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
        """Draw image.
        
        Args:
            image: The image value. Expected type: `Image | CanvasImage`.
            dx: The dx value. Expected type: `float`.
            dy: The dy value. Expected type: `float`.
            dw: The dw value. Expected type: `float`.
            dh: The dh value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
            source: The source value. Expected type: `tuple[int, int, int, int] | None`. Defaults to
                `None`.
            cache: The cache value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
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
        canvas = renderer._require_canvas()
        batch = getattr(canvas, "batch_canvas_images", None)
        transformed_batch = getattr(canvas, "batch_canvas_images_transformed", None)
        if callable(batch) or callable(transformed_batch):
            renderer._flush_line_batch_only()
            renderer._flush_primitive_batch_only()
            style_payload = renderer._style_payload(style)
            matrix_payload = renderer._matrix_payload(transform)
            if renderer._image_batch and not _same_image_batch_style(
                renderer._image_batch_style,
                style_payload,
            ):
                renderer._flush_image_batch()
            renderer._image_batch.append((rust_image, dx, dy, dw, dh, source, matrix_payload))
            renderer._image_batch_style = style_payload
            renderer._image_batch_matrix = matrix_payload
            return

        renderer._count("gpu_draws")
        current = (
            getattr(canvas, "draw_canvas_image_current", None)
            if renderer._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            renderer._call(
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
        renderer._call(
            "image drawing",
            canvas.draw_canvas_image,
            rust_image,
            dx,
            dy,
            dw,
            dh,
            renderer._style_payload(style),
            renderer._matrix_payload(transform),
            source,
        )

    def _flush_image_batch(self) -> None:
        renderer = _renderer(self)
        if not renderer._image_batch:
            return
        records = renderer._image_batch
        style = renderer._image_batch_style
        renderer._image_batch = []
        renderer._image_batch_style = None
        renderer._image_batch_matrix = None
        if style is None:
            return
        canvas = renderer._require_canvas()
        transformed_batch = getattr(canvas, "batch_canvas_images_transformed", None)
        if callable(transformed_batch):
            renderer._count("gpu_draws", len(records))
            renderer._count("image_batch_records", len(records))
            renderer._count("image_batch_flushes")
            renderer._max_count("image_batch_max_records", len(records))
            renderer._call("transformed batched image drawing", transformed_batch, records, style)
            return
        batch = getattr(canvas, "batch_canvas_images", None)
        if callable(batch):
            grouped: dict[
                MatrixPayload,
                list[tuple[object, float, float, float, float, tuple[int, int, int, int] | None]],
            ] = {}
            for rust_image, dx, dy, dw, dh, source, matrix in records:
                grouped.setdefault(matrix, []).append((rust_image, dx, dy, dw, dh, source))
            for matrix, matrix_records in grouped.items():
                renderer._count("gpu_draws", len(matrix_records))
                renderer._count("image_batch_records", len(matrix_records))
                renderer._count("image_batch_flushes")
                renderer._max_count("image_batch_max_records", len(matrix_records))
                renderer._call("batched image drawing", batch, matrix_records, style, matrix)
            return
        renderer._count("image_batch_fallbacks", len(records))
        for rust_image, dx, dy, dw, dh, source, matrix in records:
            renderer._count("gpu_draws")
            renderer._call(
                "image drawing",
                canvas.draw_canvas_image,
                rust_image,
                dx,
                dy,
                dw,
                dh,
                style,
                matrix,
                source,
            )
