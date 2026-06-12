"""Sketch state dataclasses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

from p5_py import constants as c
from p5_py.core.color import Color
from p5_py.core.transform import Matrix2D
from p5_py.events.input_state import InputState


@dataclass(slots=True)
class CanvasState:
    width: int = 100
    height: int = 100
    pixel_density: float = 1.0
    created: bool = False


@dataclass(slots=True)
class ColorModeState:
    mode: str = c.RGB
    ranges: tuple[float, float, float, float] = (255.0, 255.0, 255.0, 255.0)


@dataclass(slots=True)
class StyleState:
    fill_color: Color | None = field(default_factory=lambda: Color(255, 255, 255, 255))
    stroke_color: Color | None = field(default_factory=lambda: Color(0, 0, 0, 255))
    stroke_weight: float = 1.0
    stroke_cap: str = c.ROUND
    stroke_join: str = c.MITER
    rect_mode: str = c.CORNER
    ellipse_mode: str = c.CENTER
    blend_mode: str = c.BLEND

    def copy(self) -> StyleState:
        return replace(self)


@dataclass(slots=True)
class TransformState:
    matrix: Matrix2D = field(default_factory=Matrix2D.identity)


@dataclass(slots=True)
class ShapeState:
    active: bool = False
    vertices: list[tuple[float, float]] = field(default_factory=list)
    kind: str | None = None


@dataclass(slots=True)
class TimingState:
    start_time: float = field(default_factory=time.perf_counter)
    last_frame_time: float = field(default_factory=time.perf_counter)
    delta_time: float = 0.0
    frame_count: int = 0
    target_frame_rate: float = 60.0

    def begin_frame(self) -> None:
        now = time.perf_counter()
        self.delta_time = (now - self.last_frame_time) * 1000.0
        self.last_frame_time = now

    def millis(self) -> float:
        return (time.perf_counter() - self.start_time) * 1000.0


@dataclass(slots=True)
class StateStackEntry:
    style: StyleState
    matrix: Matrix2D


@dataclass(slots=True)
class SketchState:
    canvas: CanvasState = field(default_factory=CanvasState)
    color_mode: ColorModeState = field(default_factory=ColorModeState)
    style: StyleState = field(default_factory=StyleState)
    transform: TransformState = field(default_factory=TransformState)
    shape: ShapeState = field(default_factory=ShapeState)
    timing: TimingState = field(default_factory=TimingState)
    input: InputState = field(default_factory=InputState)
    stack: list[StateStackEntry] = field(default_factory=list)
    looping: bool = True
    redraw_requested: bool = False
