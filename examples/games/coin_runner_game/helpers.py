"""Geometry and input helpers for the Coin Runner example."""

from __future__ import annotations

import math

import gummysnake as gs
from gummysnake.events.input_state import KeyboardEvent

from .constants import GROUND_TOP


def pickup_height(index: int) -> float:
    pattern = (
        GROUND_TOP - 50,
        GROUND_TOP - 92,
        GROUND_TOP - 138,
        GROUND_TOP - 78,
        GROUND_TOP - 118,
    )
    return pattern[index % len(pattern)]


def rects_overlap(
    ax: float,
    ay: float,
    aw: float,
    ah: float,
    bx: float,
    by: float,
    bw: float,
    bh: float,
) -> bool:
    return abs(ax - bx) * 2 < aw + bw and abs(ay - by) * 2 < ah + bh


def circle_rect_collision(
    circle_x: float,
    circle_y: float,
    radius: float,
    rect_x: float,
    rect_y: float,
    rect_width: float,
    rect_height: float,
) -> bool:
    half_w = rect_width / 2
    half_h = rect_height / 2
    closest_x = clamp(circle_x, rect_x - half_w, rect_x + half_w)
    closest_y = clamp(circle_y, rect_y - half_h, rect_y + half_h)
    return math.hypot(circle_x - closest_x, circle_y - closest_y) <= radius


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def key_name(event: KeyboardEvent) -> str:
    if event.key == " ":
        return "space"
    if event.key:
        return event.key.lower()
    if event.key_code == gs.UP_ARROW:
        return "up"
    return str(event.key_code)
