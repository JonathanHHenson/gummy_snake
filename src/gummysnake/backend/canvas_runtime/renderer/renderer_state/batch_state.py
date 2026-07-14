"""Immutable keys for direct Rust model command recording."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gummysnake.backend.canvas_runtime.renderer.command_ingress import ModelTransformPayload

MatrixPayload = tuple[float, float, float, float, float, float]
ModelBatchSourceSignature = tuple[int, int, int, int, int, int, bool]


@dataclass(frozen=True, slots=True)
class ModelBatchKey:
    """Resolved retained-model state submitted with a packed transform record."""

    model_handle: object
    camera: dict[str, Any]
    projection: dict[str, Any]
    viewport_width: float
    viewport_height: float
    material: dict[str, Any]
    lights: list[dict[str, Any]]
    normal_material: bool
    cull_backfaces: bool
    source_signature: ModelBatchSourceSignature | None = None

    def equivalent_to(self, other: ModelBatchKey) -> bool:
        """Return whether two model command keys resolve to equivalent native state."""

        if (
            self.source_signature is not None
            and other.source_signature is not None
            and self.source_signature == other.source_signature
        ):
            return True
        return (
            self.model_handle is other.model_handle
            and self.camera == other.camera
            and self.projection == other.projection
            and self.viewport_width == other.viewport_width
            and self.viewport_height == other.viewport_height
            and self.material == other.material
            and self.lights == other.lights
            and self.normal_material == other.normal_material
            and self.cull_backfaces == other.cull_backfaces
        )


__all__ = [
    "MatrixPayload",
    "ModelBatchKey",
    "ModelBatchSourceSignature",
    "ModelTransformPayload",
]
