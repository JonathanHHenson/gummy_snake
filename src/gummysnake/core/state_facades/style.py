"""Style, color, transform, and stack state containers."""

from __future__ import annotations

from dataclasses import dataclass, field

from gummysnake import constants as c
from gummysnake.assets.text import DEFAULT_FONT, Font
from gummysnake.core.color import Color
from gummysnake.core.transform import Matrix2D


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
    image_tint: Color | None = None
    blend_mode: c.BlendMode = c.BLEND
    erasing: bool = False
    text_font: Font = field(default_factory=lambda: DEFAULT_FONT)
    text_size: float = 12.0
    text_style: c.TextStyle = c.NORMAL
    text_align_x: c.TextAlign = c.LEFT
    text_align_y: c.TextAlign = c.BASELINE
    text_leading: float = 14.0
    revision: int = 0
    _fill_rgba_source: Color | None = field(init=False, default=None, repr=False)
    _fill_rgba: tuple[int, int, int, int] | None = field(init=False, default=None, repr=False)
    _stroke_rgba_source: Color | None = field(init=False, default=None, repr=False)
    _stroke_rgba: tuple[int, int, int, int] | None = field(init=False, default=None, repr=False)
    _image_tint_rgba_source: Color | None = field(init=False, default=None, repr=False)
    _image_tint_rgba: tuple[int, int, int, int] | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._refresh_packed_rgba()

    @staticmethod
    def _color_rgba(color: Color | None) -> tuple[int, int, int, int] | None:
        return None if color is None else (color.r, color.g, color.b, color.a)

    def _refresh_packed_rgba(self) -> None:
        self._fill_rgba_source = self.fill_color
        self._fill_rgba = self._color_rgba(self.fill_color)
        self._stroke_rgba_source = self.stroke_color
        self._stroke_rgba = self._color_rgba(self.stroke_color)
        self._image_tint_rgba_source = self.image_tint
        self._image_tint_rgba = self._color_rgba(self.image_tint)

    @property
    def fill_rgba(self) -> tuple[int, int, int, int] | None:
        if self._fill_rgba_source is not self.fill_color:
            self._fill_rgba_source = self.fill_color
            self._fill_rgba = self._color_rgba(self.fill_color)
        return self._fill_rgba

    @property
    def stroke_rgba(self) -> tuple[int, int, int, int] | None:
        if self._stroke_rgba_source is not self.stroke_color:
            self._stroke_rgba_source = self.stroke_color
            self._stroke_rgba = self._color_rgba(self.stroke_color)
        return self._stroke_rgba

    @property
    def image_tint_rgba(self) -> tuple[int, int, int, int] | None:
        if self._image_tint_rgba_source is not self.image_tint:
            self._image_tint_rgba_source = self.image_tint
            self._image_tint_rgba = self._color_rgba(self.image_tint)
        return self._image_tint_rgba

    def copy(self) -> StyleState:
        return StyleState(
            fill_color=self.fill_color,
            stroke_color=self.stroke_color,
            stroke_weight=self.stroke_weight,
            stroke_cap=self.stroke_cap,
            stroke_join=self.stroke_join,
            rect_mode=self.rect_mode,
            ellipse_mode=self.ellipse_mode,
            image_mode=self.image_mode,
            image_sampling=self.image_sampling,
            image_tint=self.image_tint,
            blend_mode=self.blend_mode,
            erasing=self.erasing,
            text_font=self.text_font,
            text_size=self.text_size,
            text_style=self.text_style,
            text_align_x=self.text_align_x,
            text_align_y=self.text_align_y,
            text_leading=self.text_leading,
            revision=self.revision,
        )

    def mark_changed(self) -> None:
        self._refresh_packed_rgba()
        self.revision += 1


@dataclass(slots=True)
class TransformState:
    matrix: Matrix2D = field(default_factory=Matrix2D.identity)
    revision: int = 0

    def set_matrix(self, matrix: Matrix2D) -> None:
        self.matrix = matrix
        self.revision += 1


@dataclass(slots=True)
class StateStackEntry:
    style: StyleState
    matrix: Matrix2D
    clip_depth: int
