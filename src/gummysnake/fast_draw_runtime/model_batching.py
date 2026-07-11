"""Retained Rust-model batching for :class:`FastDrawScope`."""

# mypy: disable-error-code=misc
# State is stored only in the public facade's frozen slot layout.
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, cast

from gummysnake.drawing.renderer3d import Mesh3D, Model3D
from gummysnake.drawing.software3d.payloads import _IDENTITY4, Matrix4Payload

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class _ModelTransformProvider(Protocol):
    def _model_transform3d_payload(self) -> Matrix4Payload | None: ...


class FastModelBatchingMixin:
    """Reuse compatible renderer model batches without inspecting model geometry."""

    __slots__ = ()

    _context: SketchContext
    _draw_model_fast: Callable[..., object] | None
    _model_batch_cache: tuple[tuple[object, ...], object] | None
    _model_batch_signature_cache: tuple[object, tuple[object, ...]] | None

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
            transform = cast(_ModelTransformProvider, self)._model_transform3d_payload()
            signature = self._model_batch_signature(shape)
            cache = self._model_batch_cache
            if cache is not None and cache[0] == signature:
                key = cache[1]
                batch_state = getattr(self._context.renderer, "_model_batch_state", None)
                if (
                    batch_state is not None
                    and getattr(batch_state, "key", None) is key
                    and batch_state.has_records()
                ):
                    batch_state.append(key, transform or _IDENTITY4)
                    return
            draw_model_fast(shape, model_transform=transform)
            batch_state = getattr(self._context.renderer, "_model_batch_state", None)
            key = None if batch_state is None else getattr(batch_state, "key", None)
            if batch_state is not None and key is not None and batch_state.has_records():
                self._model_batch_cache = (signature, key)
            else:
                self._model_batch_cache = None
            return
        self._context.model(shape)
