"""Public constants used by p5-py drawing APIs."""

# Geometry and shape modes
CORNER = "corner"
CORNERS = "corners"
CENTER = "center"
RADIUS = "radius"

OPEN = "open"
CLOSE = "close"
CHORD = "chord"
PIE = "pie"

POINTS = "points"
LINES = "lines"
TRIANGLES = "triangles"
TRIANGLE_STRIP = "triangle_strip"
TRIANGLE_FAN = "triangle_fan"
QUADS = "quads"
QUAD_STRIP = "quad_strip"

# Angles
RADIANS = "radians"
DEGREES = "degrees"

# Color modes
RGB = "rgb"
HSB = "hsb"
HSL = "hsl"

# Stroke caps / joins
ROUND = "round"
SQUARE = "square"
PROJECT = "project"
MITER = "miter"
BEVEL = "bevel"

# Text alignment and style
LEFT = "left"
RIGHT = "right"
TOP = "top"
BOTTOM = "bottom"
BASELINE = "baseline"
NORMAL = "normal"
ITALIC = "italic"
BOLD = "bold"
BOLDITALIC = "bolditalic"

# Renderers
P2D = "p2d"
WEBGL = "webgl"

# Blend modes
BLEND = "blend"
ADD = "add"
DARKEST = "darkest"
LIGHTEST = "lightest"
DIFFERENCE = "difference"
EXCLUSION = "exclusion"
MULTIPLY = "multiply"
SCREEN = "screen"
REPLACE = "replace"

# Image sampling
LINEAR = "linear"
NEAREST = "nearest"

# Image filters
THRESHOLD = "threshold"
GRAY = "gray"
INVERT = "invert"
BLUR = "blur"
POSTERIZE = "posterize"
ERODE = "erode"
DILATE = "dilate"

# Mouse buttons
LEFT_BUTTON = "left"
CENTER_BUTTON = "center"
RIGHT_BUTTON = "right"

# Keyboard keys and codes follow p5.js-style public keyCode values.
# Backends should normalize native key symbols to these constants where needed.
BACKSPACE = 8
TAB = 9
ENTER = 13
RETURN = ENTER
ESCAPE = 27
SHIFT = 16
CONTROL = 17
ALT = 18
OPTION = ALT
UP_ARROW = 38
DOWN_ARROW = 40
LEFT_ARROW = 37
RIGHT_ARROW = 39

# Normalized touch callback/event names
TOUCH_STARTED = "touch_started"
TOUCH_MOVED = "touch_moved"
TOUCH_ENDED = "touch_ended"

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
]
