"""3D model batching helpers for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
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

        state = renderer._model_batch_state
        if not state.has_records():
            renderer._flush_line_batch_only()
            renderer._flush_primitive_batch_only()
            renderer._flush_image_batch()
            renderer._flush_text_batch()
            state.append(key, transform)
            return True

        if state.key is not None and state.key.equivalent_to(key):
            state.append(key, transform)
            return True

        renderer._flush_model_batch()
        state.append(key, transform)
        return True

    def _flush_model_batch(self) -> None:
        """Flush queued 3D model transforms as one native model batch."""
        renderer = _renderer(self)
        if not renderer._model_batch_state.has_records():
            return
        snapshot = renderer._model_batch_state.drain()
        key = snapshot.key
        transforms = snapshot.transforms
        record_count = snapshot.record_count
        if key is None or not transforms or record_count == 0:
            return

        renderer._count("direct_model_draws", record_count)
        renderer._count("model_batch_records", record_count)
        renderer._count("model_batch_flushes")
        renderer._max_count("model_batch_max_records", record_count)
        renderer._call(
            "typed batched 3D model drawing",
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
            transforms,
        )
