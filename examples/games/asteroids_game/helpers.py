"""Input and geometry helpers for the Asteroids example."""

from __future__ import annotations

import math

import gummysnake as gs
from gummysnake.events.input_state import KeyboardEvent

from .constants import CANVAS_HEIGHT, CANVAS_WIDTH


def key_down(value: str) -> bool:
    return gs.key_is_down(ord(value.lower())) or gs.key_is_down(ord(value.upper()))


def key_matches(event: KeyboardEvent, value: str) -> bool:
    return event.matches(value)


def wrap(value: float, maximum: float) -> float:
    return value % maximum


def wrapped_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    dx = min(dx, CANVAS_WIDTH - dx)
    dy = min(dy, CANVAS_HEIGHT - dy)
    return math.hypot(dx, dy)
