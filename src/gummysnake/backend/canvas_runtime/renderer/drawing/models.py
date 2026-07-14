"""3D model batching helpers for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.command_ingress import pack_model_transform
from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import (
    ModelBatchKey,
    ModelTransformPayload,
)


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class CanvasRendererModelsMixin:
    def _queue_model_batch(self, key: ModelBatchKey, transform: ModelTransformPayload) -> bool:
        """Queue one 3D model transform for a compatible native batch."""
        renderer = _renderer(self)
        renderer._require_canvas_method(
            "_draw_model_shaded_batch_packed",
            "typed batched 3D model drawing",
        )

        packed_transform = pack_model_transform(transform)
        renderer._count("direct_model_draws")
        renderer._count("model_batch_records")
        renderer._count("model_batch_flushes")
        renderer._max_count("model_batch_max_records", 1)
        renderer._call(
            "typed 3D model command recording",
            renderer._require_canvas_method(
                "_draw_model_shaded_batch_packed",
                "typed batched 3D model drawing",
            ),
            key.model_handle,
            key.camera,
            key.projection,
            key.viewport_width,
            key.viewport_height,
            key.material,
            key.lights,
            key.normal_material,
            key.cull_backfaces,
            packed_transform,
        )
        return True

    def _flush_model_batch(self) -> None:
        """Compatibility no-op; model records are submitted directly to Rust."""
        return
