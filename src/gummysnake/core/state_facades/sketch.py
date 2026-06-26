"""Sketch runtime state facade."""

from __future__ import annotations

from typing import Any

from gummysnake.core.state_facades.canvas import CanvasState
from gummysnake.core.state_facades.input import InputState
from gummysnake.core.state_facades.shape import ShapeState
from gummysnake.core.state_facades.style import (
    ColorModeState,
    StateStackEntry,
    StyleState,
    TransformState,
)
from gummysnake.core.state_facades.timing import TimingState
from gummysnake.rust.canvas import require_canvas_runtime


class SketchState:
    """Python facade over Rust-owned sketch runtime state."""

    __slots__ = (
        "_rust",
        "canvas",
        "color_mode",
        "style",
        "transform",
        "shape",
        "timing",
        "input",
        "stack",
    )

    def __init__(self) -> None:
        self._rust = require_canvas_runtime().SketchContextState()
        self.canvas = CanvasState(self._rust)
        self.color_mode = ColorModeState()
        self.style = StyleState()
        self.transform = TransformState()
        self.shape = ShapeState(self._rust)
        self.timing = TimingState(self._rust)
        self.input = InputState(self._rust)
        self.stack: list[StateStackEntry] = []

    @property
    def looping(self) -> bool:
        return bool(self._rust.looping)

    @looping.setter
    def looping(self, value: bool) -> None:
        self._rust.looping = bool(value)

    @property
    def redraw_requested(self) -> bool:
        return bool(self._rust.redraw_requested)

    @redraw_requested.setter
    def redraw_requested(self, value: bool) -> None:
        self._rust.redraw_requested = bool(value)

    @property
    def rust(self) -> Any:
        return self._rust
