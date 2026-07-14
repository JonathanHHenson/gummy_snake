"""Composition facade for frame-local fast drawing capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gummysnake.drawing.software3d.payloads import _IDENTITY4, Matrix4Payload
from gummysnake.fast_draw_runtime.model_batching import FastModelBatchingMixin
from gummysnake.fast_draw_runtime.scope_helpers import _FastPushedScope
from gummysnake.fast_draw_runtime.three_d_controls import FastThreeDControlsMixin
from gummysnake.fast_draw_runtime.transform_state import FastTransformStateMixin
from gummysnake.fast_draw_runtime.two_d_media import FastTwoDMediaMixin

if TYPE_CHECKING:
    from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import (
        ModelBatchKey,
        ModelBatchState,
    )
    from gummysnake.context import SketchContext


class FastDrawScope(
    FastTwoDMediaMixin,
    FastTransformStateMixin,
    FastThreeDControlsMixin,
    FastModelBatchingMixin,
):
    """Frame-local facade for dense 2D, media, and supported 3D drawing loops.

    A scope directly retains its creating :class:`~gummysnake.context.SketchContext` for the
    current frame. Its methods therefore bypass global-mode context lookup and flexible argument
    normalization while still reading the active public style and 2D transform state.
    """

    __slots__ = (
        "_context",
        "_image_matrix",
        "_image_matrix_payload",
        "_image_style_payload",
        "_image_style_revision",
        "_draw_model_fast",
        "_draw_model_instances_fast",
        "_model_batch_cache",
        "_model_batch_signature_cache",
        "_model_batch_state",
        "_pushed_scope",
        "_transform3d",
        "_transform3d_active",
        "_transform3d_compact",
        "_transform3d_stack",
        "_transform3d_tx",
        "_transform3d_ty",
        "_transform3d_tz",
        "_transform3d_qw",
        "_transform3d_qx",
        "_transform3d_qy",
        "_transform3d_qz",
    )

    def __init__(self, context: SketchContext) -> None:
        """Bind a fast scope to ``context`` for the current drawing frame."""
        self._context = context
        self._image_style_revision = -1
        self._image_style_payload: dict[str, object] | None = None
        self._image_matrix: object | None = None
        self._image_matrix_payload: tuple[float, float, float, float, float, float] | None = None
        draw_model_fast = getattr(context, "_draw_model_fast", None)
        self._draw_model_fast = draw_model_fast if callable(draw_model_fast) else None
        draw_model_instances_fast = getattr(context, "_draw_model_instances_fast", None)
        self._draw_model_instances_fast = (
            draw_model_instances_fast if callable(draw_model_instances_fast) else None
        )
        self._model_batch_cache: tuple[tuple[object, ...], ModelBatchKey] | None = None
        self._model_batch_signature_cache: tuple[object, tuple[object, ...]] | None = None
        self._model_batch_state: ModelBatchState | None = getattr(
            context.renderer, "_model_batch_state", None
        )
        self._pushed_scope = _FastPushedScope(self)
        self._transform3d: Matrix4Payload = _IDENTITY4
        self._transform3d_active = False
        self._transform3d_compact = 0
        self._transform3d_stack: list[Matrix4Payload | None] = []
        self._transform3d_tx = 0.0
        self._transform3d_ty = 0.0
        self._transform3d_tz = 0.0
        self._transform3d_qw = 1.0
        self._transform3d_qx = 0.0
        self._transform3d_qy = 0.0
        self._transform3d_qz = 0.0

    @property
    def width(self) -> int:
        """Return the logical width of the bound sketch canvas."""
        return self._context.width

    @property
    def height(self) -> int:
        """Return the logical height of the bound sketch canvas."""
        return self._context.height

    def pushed(self) -> _FastPushedScope:
        """Temporarily push the fast 3D model transform in a ``with`` block."""
        return self._pushed_scope
