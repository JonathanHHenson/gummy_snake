"""Drawing-related public enum values."""

from __future__ import annotations

from enum import StrEnum


class ShapeMode(StrEnum):
    """Rectangle, ellipse, and image coordinate interpretation modes."""

    CORNER = "corner"
    CORNERS = "corners"
    CENTER = "center"
    RADIUS = "radius"


class ArcMode(StrEnum):
    """Arc and shape closure modes."""

    OPEN = "open"
    CLOSE = "close"
    CHORD = "chord"
    PIE = "pie"


class ShapeKind(StrEnum):
    """Shape primitive kinds accepted by ``begin_shape()``."""

    POINTS = "points"
    LINES = "lines"
    TRIANGLES = "triangles"
    TRIANGLE_STRIP = "triangle_strip"
    TRIANGLE_FAN = "triangle_fan"
    QUADS = "quads"
    QUAD_STRIP = "quad_strip"


class AngleMode(StrEnum):
    """Angle interpretation modes."""

    RADIANS = "radians"
    DEGREES = "degrees"


class ColorMode(StrEnum):
    """Color component interpretation modes."""

    RGB = "rgb"
    HSB = "hsb"
    HSL = "hsl"


class StrokeCap(StrEnum):
    """Line cap styles."""

    ROUND = "round"
    SQUARE = "square"
    PROJECT = "project"


class StrokeJoin(StrEnum):
    """Line join styles."""

    MITER = "miter"
    BEVEL = "bevel"
    ROUND = "round"


class TextAlign(StrEnum):
    """Text alignment values."""

    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"
    TOP = "top"
    BOTTOM = "bottom"
    BASELINE = "baseline"


class TextStyle(StrEnum):
    """Text style values."""

    NORMAL = "normal"
    ITALIC = "italic"
    BOLD = "bold"
    BOLDITALIC = "bolditalic"


__all__ = [
    "AngleMode",
    "ArcMode",
    "ColorMode",
    "ShapeKind",
    "ShapeMode",
    "StrokeCap",
    "StrokeJoin",
    "TextAlign",
    "TextStyle",
]
