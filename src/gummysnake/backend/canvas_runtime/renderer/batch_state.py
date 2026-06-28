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
