"""Retained Rust-model batching for :class:`FastDrawScope`."""

# mypy: disable-error-code=misc
# State is stored only in the public facade's frozen slot layout.
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING

from gummysnake.drawing.renderer3d import Mesh3D, Model3D
from gummysnake.drawing.software3d.payloads import _IDENTITY4, Matrix4Payload
from gummysnake.exceptions import BackendCapabilityError

ModelInstanceTransform = Sequence[float] | Sequence[Sequence[float]]

if TYPE_CHECKING:
    from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import (
        ModelBatchKey,
        ModelBatchState,
    )
    from gummysnake.context import SketchContext


class FastModelBatchingMixin:
    """Reuse compatible renderer model batches without inspecting model geometry."""

    __slots__ = ()

    _context: SketchContext
    _draw_model_fast: Callable[..., object] | None
    _draw_model_instances_fast: Callable[..., object] | None
    _model_batch_cache: tuple[tuple[object, ...], ModelBatchKey] | None
    _model_batch_signature_cache: tuple[object, tuple[object, ...]] | None
    _model_batch_state: ModelBatchState | None
    _transform3d_active: bool
    _transform3d_compact: int
    _transform3d_tx: float
    _transform3d_ty: float
    _transform3d_tz: float
    _transform3d_qw: float
    _transform3d_qx: float
    _transform3d_qy: float
    _transform3d_qz: float

    if TYPE_CHECKING:

        def _model_transform3d_payload(self) -> Matrix4Payload | None: ...

        def _model_transform3d_batch_payload(
            self,
        ) -> Matrix4Payload | tuple[float, float, float, float, float, float, float] | None: ...

        def _append_model_transform3d(
            self, batch_state: ModelBatchState, key: ModelBatchKey
        ) -> bool: ...

    def _model_batch_signature(self, shape: object) -> tuple[object, ...]:
        cached = self._model_batch_signature_cache
        if cached is not None and cached[0] is shape:
            return cached[1]
        context = self._context
        material = getattr(context, "_material3d", None)
        signature = (
            shape,
            id(getattr(context, "_camera3d", None)),
            id(getattr(context, "_projection3d", None)),
            id(material)
            if material is not None
            else getattr(context.state.style, "fill_color", None),
            id(getattr(context, "_lights3d", None)),
            len(getattr(context, "_lights3d", ())),
            getattr(context, "_normal_material3d", False),
            getattr(context, "_shader3d", None),
            getattr(context.state.style, "stroke_color", None),
        )
        self._model_batch_signature_cache = (shape, signature)
        return signature

    def _invalidate_model_batch_cache(self) -> None:
        self._model_batch_cache = None
        self._model_batch_signature_cache = None

    def model(self, shape: Mesh3D | Model3D) -> None:
        """Draw a model using retained Rust batching without materializing face data."""
        draw_model_fast = self._draw_model_fast
        if draw_model_fast is not None:
            signature_cache = self._model_batch_signature_cache
            if signature_cache is not None and signature_cache[0] is shape:
                signature = signature_cache[1]
            else:
                signature = self._model_batch_signature(shape)
            cache = self._model_batch_cache
            if cache is not None and (cache[0] is signature or cache[0] == signature):
                key = cache[1]
                batch_state = self._model_batch_state
                if batch_state is not None and batch_state.key is key and batch_state.has_records():
                    if self._transform3d_active and self._transform3d_compact:
                        if batch_state.compact_translation_quaternion:
                            batch_state.append_translation_quaternion(
                                key,
                                self._transform3d_tx,
                                self._transform3d_ty,
                                self._transform3d_tz,
                                self._transform3d_qw,
                                self._transform3d_qx,
                                self._transform3d_qy,
                                self._transform3d_qz,
                            )
                            return
                    elif not batch_state.compact_translation_quaternion:
                        batch_state.append(key, self._model_transform3d_payload() or _IDENTITY4)
                        return
            transform = self._model_transform3d_batch_payload()
            draw_model_fast(shape, model_transform=transform)
            batch_state = self._model_batch_state
            current_key = None if batch_state is None else batch_state.key
            if batch_state is not None and current_key is not None and batch_state.has_records():
                self._model_batch_cache = (signature, current_key)
            else:
                self._model_batch_cache = None
            return
        self._context.model(shape)

    def model_instances(
        self,
        shape: Mesh3D | Model3D,
        transforms: Iterable[ModelInstanceTransform],
    ) -> None:
        """Draw bulk retained-model instances from complete per-instance matrices.

        Flat 16-value matrices are column-major. Nested 4x4 row-major matrices and
        existing six-value affine model transforms are also accepted. The supplied
        matrices do not read or mutate this scope's fast transform stack.
        """
        draw_model_instances_fast = self._draw_model_instances_fast
        if draw_model_instances_fast is None:
            raise BackendCapabilityError(
                "model_instances() requires bulk retained-model drawing support from the "
                "active Gummy Snake context."
            )
        draw_model_instances_fast(shape, transforms)
