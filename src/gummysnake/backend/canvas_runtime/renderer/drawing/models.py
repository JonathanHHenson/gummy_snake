"""3D model batching helpers for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Iterable

from gummysnake.backend.canvas_runtime.renderer._protocols import _renderer
from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import (
    ModelBatchKey,
    ModelTransformPayload,
)


class CanvasRendererModelsMixin:
    def _queue_model_batch(self, key: ModelBatchKey, transform: ModelTransformPayload) -> bool:
        """Queue one 3D model transform for a compatible native batch."""
        renderer = _renderer(self)
        renderer._require_canvas_method(
            "_draw_model_shaded_batch_packed",
            "typed batched 3D model drawing",
        )

        state = renderer._model_batch_state
        if state.has_records() and (
            state.compact_translation_quaternion
            or state.key is None
            or not state.key.equivalent_to(key)
        ):
            renderer._flush_model_batch()
        state.append(key, transform)
        return True

    def _queue_model_batch_translation_quaternion(
        self,
        key: ModelBatchKey,
        tx: float,
        ty: float,
        tz: float,
        w: float,
        x: float,
        y: float,
        z: float,
    ) -> bool:
        """Queue one compact translation/quaternion retained-model transform."""
        renderer = _renderer(self)
        renderer._require_canvas_method(
            "_draw_model_shaded_batch_translation_quaternion_packed",
            "compact batched 3D model drawing",
        )
        state = renderer._model_batch_state
        if state.has_records() and (
            not state.compact_translation_quaternion
            or state.key is None
            or not state.key.equivalent_to(key)
        ):
            renderer._flush_model_batch()
        state.append_translation_quaternion(key, tx, ty, tz, w, x, y, z)
        return True

    def _queue_model_batch_many(
        self,
        key: ModelBatchKey,
        transforms: Iterable[ModelTransformPayload],
    ) -> int:
        """Queue an iterable of transforms under one resolved retained-model key."""
        renderer = _renderer(self)
        renderer._require_canvas_method(
            "_draw_model_shaded_batch_packed",
            "typed batched 3D model drawing",
        )

        state = renderer._model_batch_state
        if state.has_records() and (
            state.compact_translation_quaternion
            or state.key is None
            or not state.key.equivalent_to(key)
        ):
            renderer._flush_model_batch()
        return state.append_many(key, transforms)

    def _flush_model_batch(self) -> None:
        """Submit one contiguous retained-model instance run to Rust."""
        renderer = _renderer(self)
        state = renderer._model_batch_state
        if not state.has_records():
            return
        snapshot = state.drain()
        key = snapshot.key
        if key is None or snapshot.record_count == 0:
            return

        renderer._count("direct_model_draws", snapshot.record_count)
        renderer._count("model_batch_records", snapshot.record_count)
        renderer._count("model_batch_flushes")
        renderer._max_count("model_batch_max_records", snapshot.record_count)
        method_name = (
            "_draw_model_shaded_batch_translation_quaternion_packed"
            if snapshot.compact_translation_quaternion
            else "_draw_model_shaded_batch_packed"
        )
        renderer._call(
            "typed 3D model command recording",
            renderer._require_canvas_method(
                method_name,
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
            snapshot.transforms,
        )
