"""Compatibility imports for renderer batch state.

Implementation lives in :mod:`renderer_state.batch_state`.
"""

from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import (
    LineBatchRecord,
    LineBatchSnapshot,
    LineBatchState,
    MatrixPayload,
    ModelBatchKey,
    ModelBatchSnapshot,
    ModelBatchSourceSignature,
    ModelBatchState,
    ModelTransformPayload,
    PrimitiveBatchMode,
    PrimitiveBatchRecord,
    PrimitiveBatchSnapshot,
    PrimitiveBatchState,
)

__all__ = [
    "LineBatchRecord",
    "LineBatchSnapshot",
    "LineBatchState",
    "MatrixPayload",
    "ModelBatchKey",
    "ModelBatchSnapshot",
    "ModelBatchSourceSignature",
    "ModelBatchState",
    "ModelTransformPayload",
    "PrimitiveBatchMode",
    "PrimitiveBatchRecord",
    "PrimitiveBatchSnapshot",
    "PrimitiveBatchState",
]
