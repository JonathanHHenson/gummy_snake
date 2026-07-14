"""Image drawing for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake.assets.image import CanvasImage, Image
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost, MatrixPayload
from gummysnake.backend.canvas_runtime.renderer.command_ingress import pack_image_commands
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
        if renderer._model_batch_state.record_count:
            renderer._flush_model_batch()
        records, images = pack_image_commands([(rust_image, dx, dy, dw, dh, None, matrix)])
        renderer._count("gpu_draws")
        renderer._count("image_batch_records")
        renderer._count("image_batch_flushes")
        renderer._max_count("image_batch_max_records", 1)
        renderer._call(
            "typed image command recording",
            renderer._require_canvas_method(
                "batch_canvas_images_packed",
                "typed image command recording",
            ),
            records,
            images,
            style,
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
        if renderer._model_batch_state.record_count:
            renderer._flush_model_batch()
        renderer._require_canvas_method(
            "batch_canvas_images_packed",
            "typed image command recording",
        )
        style_payload = renderer._style_payload(style)
        matrix_payload = renderer._matrix_payload(transform)
        records, images = pack_image_commands(
            [(rust_image, dx, dy, dw, dh, source, matrix_payload)]
        )
        renderer._count("gpu_draws")
        renderer._count("image_batch_records")
        renderer._count("image_batch_flushes")
        renderer._max_count("image_batch_max_records", 1)
        renderer._call(
            "typed image command recording",
            renderer._require_canvas_method(
                "batch_canvas_images_packed",
                "typed image command recording",
            ),
            records,
            images,
            style_payload,
        )

    def _flush_image_batch(self) -> None:
        return
