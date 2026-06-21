"""Structural protocols for composed SketchContext mixins."""

from __future__ import annotations

from typing import Any, Protocol


class SketchContextHost(Protocol):
    backend: Any
    renderer: Any
    state: Any

    def _angle(self, value: float) -> float: ...
    def _mark_style_changed(self) -> None: ...
    def _record_performance_diagnostic(self, name: str) -> None: ...
    def _reset_3d_state(self) -> None: ...
