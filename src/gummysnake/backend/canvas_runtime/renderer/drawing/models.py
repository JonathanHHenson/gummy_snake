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
        canvas = renderer._require_canvas()
        batch = getattr(canvas, "_draw_model_shaded_batch", None)
        if not callable(batch):
            return False

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
        if key is None or not transforms:
            return

        canvas = renderer._require_canvas()
        batch = getattr(canvas, "_draw_model_shaded_batch", None)
        if callable(batch):
            renderer._count("direct_model_draws", len(transforms))
            renderer._count("model_batch_records", len(transforms))
            renderer._count("model_batch_flushes")
            renderer._max_count("model_batch_max_records", len(transforms))
            renderer._call(
                "batched 3D model drawing",
                batch,
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
            return

        draw = getattr(canvas, "draw_model_shaded", None)
        if not callable(draw):
            renderer._count("model_batch_fallbacks", len(transforms))
            return
        renderer._count("model_batch_fallbacks", len(transforms))
        for transform in transforms:
            renderer._count("direct_model_draws")
            renderer._call(
                "3D model drawing",
                draw,
                key.model_handle,
                key.camera,
                key.projection,
                key.viewport_width,
                key.viewport_height,
                key.material,
                key.lights,
                key.normal_material,
                key.cull_backfaces,
                transform,
            )
