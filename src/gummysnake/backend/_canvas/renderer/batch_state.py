"""Small renderer batch state containers.

The Rust bridge still receives the same tuple payloads; these helpers only keep
Python-side queue bookkeeping cohesive and make flush boundaries explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MatrixPayload = tuple[float, float, float, float, float, float]
LineBatchRecord = tuple[float, float, float, float]
PrimitiveBatchRecord = tuple[object, ...]
PrimitiveBatchMode = Literal["fill", "mixed", "style"]


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
        return bool(self.records)

    def matches_current(self) -> bool:
        return self.current

    def matches_style(self, style: dict[str, object], matrix: MatrixPayload) -> bool:
        return not self.current and self.style is style and self.matrix is matrix

    def append_current(self, record: LineBatchRecord) -> None:
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
        self.records.append(record)
        self.style = style
        self.matrix = matrix
        self.current = False

    def drain(self) -> LineBatchSnapshot:
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
        return bool(self.records)

    def matches_fill(self, matrix: MatrixPayload) -> bool:
        return self.mode == "fill" and self.matrix is matrix

    def matches_mixed(self) -> bool:
        return self.mode == "mixed"

    def matches_current(self) -> bool:
        return self.mode == "style" and self.current

    def matches_styled(self, style: dict[str, object], matrix: MatrixPayload) -> bool:
        return (
            self.mode == "style"
            and not self.current
            and self.style is style
            and self.matrix is matrix
        )

    def append_fill(self, record: PrimitiveBatchRecord, matrix: MatrixPayload) -> None:
        self.records.append(record)
        self.style = None
        self.matrix = matrix
        self.current = False
        self.mode = "fill"

    def append_mixed(self, record: PrimitiveBatchRecord) -> None:
        self.records.append(record)
        self.style = None
        self.matrix = None
        self.current = False
        self.mode = "mixed"

    def append_current(self, record: PrimitiveBatchRecord) -> None:
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
        self.records.append(record)
        self.style = style
        self.matrix = matrix
        self.current = False
        self.mode = "style"

    def drain(self) -> PrimitiveBatchSnapshot:
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
