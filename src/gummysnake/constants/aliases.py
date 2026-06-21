"""Public uppercase aliases for enum-backed constants."""

from __future__ import annotations

from gummysnake.constants.drawing import (
    AngleMode,
    ArcMode,
    ColorMode,
    ShapeKind,
    ShapeMode,
    StrokeCap,
    StrokeJoin,
    TextAlign,
    TextStyle,
)
from gummysnake.constants.input import (
    CallbackEventName,
    KeyCode,
    MouseButton,
    PointerLockMode,
    TouchEventName,
)
from gummysnake.constants.renderer import BlendMode, ImageFilter, ImageSampling, RendererMode

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
UNCLAMPED = PointerLockMode.UNCLAMPED
CLAMPED = PointerLockMode.CLAMPED
FIXED = PointerLockMode.FIXED
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
    "UNCLAMPED",
    "CLAMPED",
    "FIXED",
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
    "TOUCH_CANCELLED",
]
