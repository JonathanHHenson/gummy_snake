"""Small renderer batch state containers.

The Rust bridge still receives the same tuple payloads; these helpers only keep
Python-side queue bookkeeping cohesive and make flush boundaries explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MatrixPayload = tuple[float, float, float, float, float, float]
LineBatchRecord = tuple[float, float, float, float]
PrimitiveBatchRecord = tuple[object, ...]
PrimitiveBatchMode = Literal["fill", "mixed", "style"]
ModelTransformPayload = tuple[float, ...]
ModelBatchSourceSignature = tuple[int, int, int, int, int, int, bool]


@dataclass(frozen=True, slots=True)
class LineBatchSnapshot:
    records: list[LineBatchRecord]
    style: dict[str, object] | None
    matrix: MatrixPayload | None
    current: bool


@dataclass(slots=True)
class LineBatchState:
    records: list[LineBatchRecord] = field(default_factory=list)
    style: dict[str, object] | None = None
    matrix: MatrixPayload | None = None
    current: bool = False

    def has_records(self) -> bool:
        """Has records.

        Args:
            None.

        Returns:
            The return value. Type: `bool`.
        """
        return bool(self.records)

    def matches_current(self) -> bool:
        """Matches current.

        Args:
            None.

        Returns:
            The return value. Type: `bool`.
        """
        return self.current

    def matches_style(self, style: dict[str, object], matrix: MatrixPayload) -> bool:
        """Matches style.

        Args:
            style: The style value. Expected type: `dict[str, object]`.
            matrix: The matrix value. Expected type: `MatrixPayload`.

        Returns:
            The return value. Type: `bool`.
        """
        return not self.current and self.style is style and self.matrix is matrix

    def append_current(self, record: LineBatchRecord) -> None:
        """Append current.

        Args:
            record: The record value. Expected type: `LineBatchRecord`.

        Returns:
            None.
        """
        self.records.append(record)
        self.style = None
        self.matrix = None
        self.current = True

    def append_styled(
        self,
        record: LineBatchRecord,
        style: dict[str, object],
        matrix: MatrixPayload,
    ) -> None:
        """Append styled.

        Args:
            record: The record value. Expected type: `LineBatchRecord`.
            style: The style value. Expected type: `dict[str, object]`.
            matrix: The matrix value. Expected type: `MatrixPayload`.

        Returns:
            None.
        """
        self.records.append(record)
        self.style = style
        self.matrix = matrix
        self.current = False

    def drain(self) -> LineBatchSnapshot:
        """Drain.

        Args:
            None.

        Returns:
            The return value. Type: `LineBatchSnapshot`.
        """
        snapshot = LineBatchSnapshot(
            records=self.records,
            style=self.style,
            matrix=self.matrix,
            current=self.current,
        )
        self.records = []
        self.style = None
        self.matrix = None
        self.current = False
        return snapshot


@dataclass(frozen=True, slots=True)
class PrimitiveBatchSnapshot:
    records: list[PrimitiveBatchRecord]
    style: dict[str, object] | None
    matrix: MatrixPayload | None
    current: bool
    mode: PrimitiveBatchMode | None


@dataclass(slots=True)
class PrimitiveBatchState:
    records: list[PrimitiveBatchRecord] = field(default_factory=list)
    style: dict[str, object] | None = None
    matrix: MatrixPayload | None = None
    current: bool = False
    mode: PrimitiveBatchMode | None = None

    def has_records(self) -> bool:
        """Has records.

        Args:
            None.

        Returns:
            The return value. Type: `bool`.
        """
        return bool(self.records)

    def matches_fill(self, matrix: MatrixPayload) -> bool:
        """Matches fill.

        Args:
            matrix: The matrix value. Expected type: `MatrixPayload`.

        Returns:
            The return value. Type: `bool`.
        """
        return self.mode == "fill" and self.matrix is matrix

    def matches_mixed(self) -> bool:
        """Matches mixed.

        Args:
            None.

        Returns:
            The return value. Type: `bool`.
        """
        return self.mode == "mixed"

    def matches_current(self) -> bool:
        """Matches current.

        Args:
            None.

        Returns:
            The return value. Type: `bool`.
        """
        return self.mode == "style" and self.current

    def matches_styled(self, style: dict[str, object], matrix: MatrixPayload) -> bool:
        """Matches styled.

        Args:
            style: The style value. Expected type: `dict[str, object]`.
            matrix: The matrix value. Expected type: `MatrixPayload`.

        Returns:
            The return value. Type: `bool`.
        """
        return (
            self.mode == "style"
            and not self.current
            and self.style is style
            and self.matrix is matrix
        )

    def append_fill(self, record: PrimitiveBatchRecord, matrix: MatrixPayload) -> None:
        """Append fill.

        Args:
            record: The record value. Expected type: `PrimitiveBatchRecord`.
            matrix: The matrix value. Expected type: `MatrixPayload`.

        Returns:
            None.
        """
        self.records.append(record)
        self.style = None
        self.matrix = matrix
        self.current = False
        self.mode = "fill"

    def append_mixed(self, record: PrimitiveBatchRecord) -> None:
        """Append mixed.

        Args:
            record: The record value. Expected type: `PrimitiveBatchRecord`.

        Returns:
            None.
        """
        self.records.append(record)
        self.style = None
        self.matrix = None
        self.current = False
        self.mode = "mixed"

    def append_current(self, record: PrimitiveBatchRecord) -> None:
        """Append current.

        Args:
            record: The record value. Expected type: `PrimitiveBatchRecord`.

        Returns:
            None.
        """
        self.records.append(record)
        self.style = None
        self.matrix = None
        self.current = True
        self.mode = "style"

    def append_styled(
        self,
        record: PrimitiveBatchRecord,
        style: dict[str, object],
        matrix: MatrixPayload,
    ) -> None:
        """Append styled.

        Args:
            record: The record value. Expected type: `PrimitiveBatchRecord`.
            style: The style value. Expected type: `dict[str, object]`.
            matrix: The matrix value. Expected type: `MatrixPayload`.

        Returns:
            None.
        """
        self.records.append(record)
        self.style = style
        self.matrix = matrix
        self.current = False
        self.mode = "style"

    def drain(self) -> PrimitiveBatchSnapshot:
        """Drain.

        Args:
            None.

        Returns:
            The return value. Type: `PrimitiveBatchSnapshot`.
        """
        snapshot = PrimitiveBatchSnapshot(
            records=self.records,
            style=self.style,
            matrix=self.matrix,
            current=self.current,
            mode=self.mode,
        )
        self.records = []
        self.style = None
        self.matrix = None
        self.current = False
        self.mode = None
        return snapshot


@dataclass(frozen=True, slots=True)
class ModelBatchKey:
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
        """Return whether two model runs can be submitted as one native batch."""
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
    key: ModelBatchKey | None
    transforms: list[ModelTransformPayload]


@dataclass(slots=True)
class ModelBatchState:
    key: ModelBatchKey | None = None
    transforms: list[ModelTransformPayload] = field(default_factory=list)

    def has_records(self) -> bool:
        """Return whether the model batch has pending model instances."""
        return bool(self.transforms)

    def append(self, key: ModelBatchKey, transform: ModelTransformPayload) -> None:
        """Append one model transform, starting or extending the current compatible run."""
        self.key = key
        self.transforms.append(transform)

    def drain(self) -> ModelBatchSnapshot:
        """Drain pending model transforms."""
        snapshot = ModelBatchSnapshot(key=self.key, transforms=self.transforms)
        self.key = None
        self.transforms = []
        return snapshot
