"""Public enum values used by Gummy Snake drawing APIs."""

from __future__ import annotations

from enum import IntEnum, StrEnum


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


class RendererMode(StrEnum):
    """Renderer modes accepted by ``create_canvas()``."""

    P2D = "p2d"
    WEBGL = "webgl"


class BlendMode(StrEnum):
    """Canvas compositing modes."""

    BLEND = "blend"
    ADD = "add"
    DARKEST = "darkest"
    LIGHTEST = "lightest"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    REPLACE = "replace"


class ImageSampling(StrEnum):
    """Image sampling modes."""

    LINEAR = "linear"
    NEAREST = "nearest"


class ImageFilter(StrEnum):
    """Image filter modes."""

    THRESHOLD = "threshold"
    GRAY = "gray"
    INVERT = "invert"
    BLUR = "blur"
    POSTERIZE = "posterize"
    ERODE = "erode"
    DILATE = "dilate"


class MouseButton(StrEnum):
    """Normalized mouse button names."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class KeyCode(IntEnum):
    """Gummy Snake-style public keyboard key code values."""

    BACKSPACE = 8
    TAB = 9
    ENTER = 13
    ESCAPE = 27
    SHIFT = 16
    CONTROL = 17
    ALT = 18
    UP_ARROW = 38
    DOWN_ARROW = 40
    LEFT_ARROW = 37
    RIGHT_ARROW = 39


class TouchEventName(StrEnum):
    """Normalized touch callback/event names."""

    TOUCH_STARTED = "touch_started"
    TOUCH_MOVED = "touch_moved"
    TOUCH_ENDED = "touch_ended"


class CallbackEventName(StrEnum):
    """Normalized sketch callback/event names accepted by ``on()``."""

    MOUSE_MOVED = "mouse_moved"
    MOUSE_DRAGGED = "mouse_dragged"
    MOUSE_PRESSED = "mouse_pressed"
    MOUSE_RELEASED = "mouse_released"
    MOUSE_CLICKED = "mouse_clicked"
    MOUSE_DOUBLE_CLICKED = "mouse_double_clicked"
    MOUSE_WHEEL = "mouse_wheel"
    KEY_PRESSED = "key_pressed"
    KEY_RELEASED = "key_released"
    KEY_TYPED = "key_typed"
    TOUCH_STARTED = "touch_started"
    TOUCH_MOVED = "touch_moved"
    TOUCH_ENDED = "touch_ended"
    TOUCH_CANCELLED = "touch_cancelled"


# Public Gummy Snake-style names are enum members rather than raw constants.
CORNER = ShapeMode.CORNER
CORNERS = ShapeMode.CORNERS
CENTER = ShapeMode.CENTER
RADIUS = ShapeMode.RADIUS

OPEN = ArcMode.OPEN
CLOSE = ArcMode.CLOSE
CHORD = ArcMode.CHORD
PIE = ArcMode.PIE

POINTS = ShapeKind.POINTS
LINES = ShapeKind.LINES
TRIANGLES = ShapeKind.TRIANGLES
TRIANGLE_STRIP = ShapeKind.TRIANGLE_STRIP
TRIANGLE_FAN = ShapeKind.TRIANGLE_FAN
QUADS = ShapeKind.QUADS
QUAD_STRIP = ShapeKind.QUAD_STRIP

RADIANS = AngleMode.RADIANS
DEGREES = AngleMode.DEGREES

RGB = ColorMode.RGB
HSB = ColorMode.HSB
HSL = ColorMode.HSL

ROUND = StrokeCap.ROUND
SQUARE = StrokeCap.SQUARE
PROJECT = StrokeCap.PROJECT
MITER = StrokeJoin.MITER
BEVEL = StrokeJoin.BEVEL

LEFT = TextAlign.LEFT
RIGHT = TextAlign.RIGHT
TOP = TextAlign.TOP
BOTTOM = TextAlign.BOTTOM
BASELINE = TextAlign.BASELINE
NORMAL = TextStyle.NORMAL
ITALIC = TextStyle.ITALIC
BOLD = TextStyle.BOLD
BOLDITALIC = TextStyle.BOLDITALIC

P2D = RendererMode.P2D
WEBGL = RendererMode.WEBGL

BLEND = BlendMode.BLEND
ADD = BlendMode.ADD
DARKEST = BlendMode.DARKEST
LIGHTEST = BlendMode.LIGHTEST
DIFFERENCE = BlendMode.DIFFERENCE
EXCLUSION = BlendMode.EXCLUSION
MULTIPLY = BlendMode.MULTIPLY
SCREEN = BlendMode.SCREEN
REPLACE = BlendMode.REPLACE

LINEAR = ImageSampling.LINEAR
NEAREST = ImageSampling.NEAREST

THRESHOLD = ImageFilter.THRESHOLD
GRAY = ImageFilter.GRAY
INVERT = ImageFilter.INVERT
BLUR = ImageFilter.BLUR
POSTERIZE = ImageFilter.POSTERIZE
ERODE = ImageFilter.ERODE
DILATE = ImageFilter.DILATE

LEFT_BUTTON = MouseButton.LEFT
CENTER_BUTTON = MouseButton.CENTER
RIGHT_BUTTON = MouseButton.RIGHT

BACKSPACE = KeyCode.BACKSPACE
TAB = KeyCode.TAB
ENTER = KeyCode.ENTER
RETURN = KeyCode.ENTER
ESCAPE = KeyCode.ESCAPE
SHIFT = KeyCode.SHIFT
CONTROL = KeyCode.CONTROL
ALT = KeyCode.ALT
OPTION = KeyCode.ALT
UP_ARROW = KeyCode.UP_ARROW
DOWN_ARROW = KeyCode.DOWN_ARROW
LEFT_ARROW = KeyCode.LEFT_ARROW
RIGHT_ARROW = KeyCode.RIGHT_ARROW

TOUCH_STARTED = TouchEventName.TOUCH_STARTED
TOUCH_MOVED = TouchEventName.TOUCH_MOVED
TOUCH_ENDED = TouchEventName.TOUCH_ENDED

MOUSE_MOVED = CallbackEventName.MOUSE_MOVED
MOUSE_DRAGGED = CallbackEventName.MOUSE_DRAGGED
MOUSE_PRESSED = CallbackEventName.MOUSE_PRESSED
MOUSE_RELEASED = CallbackEventName.MOUSE_RELEASED
MOUSE_CLICKED = CallbackEventName.MOUSE_CLICKED
MOUSE_DOUBLE_CLICKED = CallbackEventName.MOUSE_DOUBLE_CLICKED
MOUSE_WHEEL = CallbackEventName.MOUSE_WHEEL
KEY_PRESSED = CallbackEventName.KEY_PRESSED
KEY_RELEASED = CallbackEventName.KEY_RELEASED
KEY_TYPED = CallbackEventName.KEY_TYPED
TOUCH_CANCELLED = CallbackEventName.TOUCH_CANCELLED

__all__ = [
    "ShapeMode",
    "ArcMode",
    "ShapeKind",
    "AngleMode",
    "ColorMode",
    "StrokeCap",
    "StrokeJoin",
    "TextAlign",
    "TextStyle",
    "RendererMode",
    "BlendMode",
    "ImageSampling",
    "ImageFilter",
    "MouseButton",
    "KeyCode",
    "TouchEventName",
    "CallbackEventName",
    "CORNER",
    "CORNERS",
    "CENTER",
    "RADIUS",
    "OPEN",
    "CLOSE",
    "CHORD",
    "PIE",
    "POINTS",
    "LINES",
    "TRIANGLES",
    "TRIANGLE_STRIP",
    "TRIANGLE_FAN",
    "QUADS",
    "QUAD_STRIP",
    "RADIANS",
    "DEGREES",
    "RGB",
    "HSB",
    "HSL",
    "ROUND",
    "SQUARE",
    "PROJECT",
    "MITER",
    "BEVEL",
    "LEFT",
    "RIGHT",
    "TOP",
    "BOTTOM",
    "BASELINE",
    "NORMAL",
    "ITALIC",
    "BOLD",
    "BOLDITALIC",
    "P2D",
    "WEBGL",
    "BLEND",
    "ADD",
    "DARKEST",
    "LIGHTEST",
    "DIFFERENCE",
    "EXCLUSION",
    "MULTIPLY",
    "SCREEN",
    "REPLACE",
    "LINEAR",
    "NEAREST",
    "THRESHOLD",
    "GRAY",
    "INVERT",
    "BLUR",
    "POSTERIZE",
    "ERODE",
    "DILATE",
    "LEFT_BUTTON",
    "CENTER_BUTTON",
    "RIGHT_BUTTON",
    "BACKSPACE",
    "TAB",
    "ENTER",
    "RETURN",
    "ESCAPE",
    "SHIFT",
    "CONTROL",
    "ALT",
    "OPTION",
    "UP_ARROW",
    "DOWN_ARROW",
    "LEFT_ARROW",
    "RIGHT_ARROW",
    "TOUCH_STARTED",
    "TOUCH_MOVED",
    "TOUCH_ENDED",
    "TOUCH_CANCELLED",
    "MOUSE_MOVED",
    "MOUSE_DRAGGED",
    "MOUSE_PRESSED",
    "MOUSE_RELEASED",
    "MOUSE_CLICKED",
    "MOUSE_DOUBLE_CLICKED",
    "MOUSE_WHEEL",
    "KEY_PRESSED",
    "KEY_RELEASED",
    "KEY_TYPED",
]
