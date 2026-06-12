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

# Text alignment
LEFT = "left"
RIGHT = "right"
TOP = "top"
BOTTOM = "bottom"
BASELINE = "baseline"

# Renderers / backends
P2D = "p2d"
WEBGL = "webgl"
HEADLESS = "headless"
PYGLET = "pyglet"
PILLOW = "pillow"

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

# Mouse buttons
LEFT_BUTTON = "left"
CENTER_BUTTON = "center"
RIGHT_BUTTON = "right"

__all__ = [name for name in globals() if name.isupper()]
