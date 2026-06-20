"""Sketch state dataclasses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

from gummysnake import constants as c
from gummysnake.assets.text import DEFAULT_FONT, Font
from gummysnake.core.color import Color
from gummysnake.core.transform import Matrix2D
from gummysnake.events.input_state import InputState


@dataclass(slots=True)
class CanvasState:
    width: int = 100
    height: int = 100
    physical_width: int = 100
    physical_height: int = 100
    pixel_density: float = 1.0
    renderer: c.RendererMode = c.P2D
    created: bool = False


@dataclass(slots=True)
class ColorModeState:
    mode: c.ColorMode = c.RGB
    ranges: tuple[float, float, float, float] = (255.0, 255.0, 255.0, 255.0)


@dataclass(slots=True)
class StyleState:
    fill_color: Color | None = field(default_factory=lambda: Color(255, 255, 255, 255))
    stroke_color: Color | None = field(default_factory=lambda: Color(0, 0, 0, 255))
    stroke_weight: float = 1.0
    stroke_cap: c.StrokeCap = c.ROUND
    stroke_join: c.StrokeJoin = c.MITER
    rect_mode: c.ShapeMode = c.CORNER
    ellipse_mode: c.ShapeMode = c.CENTER
    image_mode: c.ShapeMode = c.CORNER
    image_sampling: c.ImageSampling = c.LINEAR
    blend_mode: c.BlendMode = c.BLEND
    erasing: bool = False
    text_font: Font = field(default_factory=lambda: DEFAULT_FONT)
    text_size: float = 12.0
    text_style: c.TextStyle = c.NORMAL
    text_align_x: c.TextAlign = c.LEFT
    text_align_y: c.TextAlign = c.BASELINE
    text_leading: float = 14.0
    revision: int = 0

    def copy(self) -> StyleState:
        return replace(self)

    def mark_changed(self) -> None:
        self.revision += 1


@dataclass(slots=True)
class TransformState:
    matrix: Matrix2D = field(default_factory=Matrix2D.identity)
    revision: int = 0

    def set_matrix(self, matrix: Matrix2D) -> None:
        self.matrix = matrix
        self.revision += 1


@dataclass(slots=True)
class ShapeState:
    active: bool = False
    vertices: list[tuple[float, float]] = field(default_factory=list)
    kind: c.ShapeKind | None = None


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
