"""Immutable keys for direct Rust model command recording."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from gummysnake.backend.canvas_runtime.renderer.command_ingress import (
    ModelTransformPayload,
    append_model_transform,
    append_model_translation_quaternion,
)

MatrixPayload = tuple[float, float, float, float, float, float]
ModelBatchSourceSignature = tuple[object, ...]


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


@dataclass(frozen=True, slots=True)
class ModelBatchSnapshot:
    """One drained contiguous retained-model instance run."""

    key: ModelBatchKey | None
    transforms: bytes
    record_count: int
    compact_translation_quaternion: bool


@dataclass(slots=True)
class ModelBatchState:
    """Frame-local packed transforms for one compatible retained-model key."""

    key: ModelBatchKey | None = None
    transforms: bytearray = field(default_factory=bytearray)
    write_size: int = 0
    record_count: int = 0
    compact_translation_quaternion: bool = False

    def has_records(self) -> bool:
        """Return whether this batch contains pending model instances."""
        return self.record_count > 0

    def append(self, key: ModelBatchKey, transform: ModelTransformPayload) -> None:
        """Pack one model transform into the current contiguous instance run."""
        if self.key is None:
            self.key = key
        self.compact_translation_quaternion = False
        self.write_size = append_model_transform(
            self.transforms,
            transform,
            offset=self.write_size,
        )
        self.record_count += 1

    def append_translation_quaternion(
        self,
        key: ModelBatchKey,
        tx: float,
        ty: float,
        tz: float,
        w: float,
        x: float,
        y: float,
        z: float,
    ) -> None:
        """Pack one normalized translation/quaternion transform without a matrix allocation."""
        if self.key is None:
            self.key = key
        self.compact_translation_quaternion = True
        self.write_size = append_model_translation_quaternion(
            self.transforms,
            tx,
            ty,
            tz,
            w,
            x,
            y,
            z,
            offset=self.write_size,
        )
        self.record_count += 1

    def append_many(
        self,
        key: ModelBatchKey,
        transforms: Iterable[ModelTransformPayload],
    ) -> int:
        """Atomically pack an iterable of transforms into the current instance run."""
        try:
            iterator = iter(transforms)
        except TypeError as exc:
            raise ValueError(
                "model_instances() transforms must be an iterable of matrices."
            ) from exc

        original_key = self.key
        original_size = self.write_size
        original_count = self.record_count
        original_compact = self.compact_translation_quaternion
        appended = 0
        try:
            for index, transform in enumerate(iterator):
                try:
                    self.write_size = append_model_transform(
                        self.transforms,
                        transform,
                        offset=self.write_size,
                    )
                except Exception as exc:
                    raise ValueError(
                        f"model_instances() transform at index {index} is invalid: {exc}"
                    ) from exc
                appended += 1
        except BaseException:
            self.write_size = original_size
            self.key = original_key
            self.record_count = original_count
            self.compact_translation_quaternion = original_compact
            raise

        if appended:
            if self.key is None:
                self.key = key
            self.compact_translation_quaternion = False
            self.record_count += appended
        return appended

    def drain(self) -> ModelBatchSnapshot:
        """Return the current packed run and reset the accumulator."""
        snapshot = ModelBatchSnapshot(
            self.key,
            bytes(memoryview(self.transforms)[: self.write_size]),
            self.record_count,
            self.compact_translation_quaternion,
        )
        self.key = None
        self.write_size = 0
        self.record_count = 0
        self.compact_translation_quaternion = False
        return snapshot


__all__ = [
    "MatrixPayload",
    "ModelBatchKey",
    "ModelBatchSnapshot",
    "ModelBatchSourceSignature",
    "ModelBatchState",
    "ModelTransformPayload",
]
