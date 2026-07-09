# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
"""Backend-normalized input state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from gummysnake import constants as c
from gummysnake.core.vector import Vector
from gummysnake.exceptions import BackendCapabilityError

_SPACE_KEY_NAMES = {"space", "spacebar"}


class _MotionState(Protocol):
    acceleration_x: float
    acceleration_y: float
    acceleration_z: float
    previous_acceleration_x: float
    previous_acceleration_y: float
    previous_acceleration_z: float
    rotation_x: float
    rotation_y: float
    rotation_z: float
    previous_rotation_x: float
    previous_rotation_y: float
    previous_rotation_z: float
    device_orientation: str
    turn_axis: str | None
    move_threshold: float


@dataclass(slots=True)
class MouseEvent:
    """Public MouseEvent value."""

    x: float
    y: float
    button: str | None = None
    dx: float = 0.0
    dy: float = 0.0
    previous_x: float | None = None
    previous_y: float | None = None
    window_x: float | None = None
    window_y: float | None = None
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    click_count: int = 0
    modifiers: int | None = None
    inside_window: bool | None = None
    type: str = "mouse"

    @property
    def position(self) -> Vector:
        return Vector(self.x, self.y)

    @property
    def delta(self) -> Vector:
        return Vector(self.dx, self.dy)

    @property
    def previous_position(self) -> Vector | None:
        if self.previous_x is None or self.previous_y is None:
            return None
        return Vector(self.previous_x, self.previous_y)

    @property
    def window_position(self) -> Vector | None:
        if self.window_x is None or self.window_y is None:
            return None
        return Vector(self.window_x, self.window_y)

    @property
    def scroll(self) -> Vector:
        return Vector(self.scroll_x, self.scroll_y)


@dataclass(slots=True)
class KeyboardEvent:
    """Public KeyboardEvent value."""

    key: str | None = None
    key_code: int | None = None
    code: str | None = None
    text: str | None = None
    repeat: bool = False
    modifiers: int | None = None
    type: str = "keyboard"

    def matches(self, value: str | int) -> bool:
        if isinstance(value, int):
            return self.key_code == value
        if self.key == value:
            return True
        if len(value) == 1 and self.key_code == ord(value):
            return True
        if value == " " and self.key is not None and self.key.lower() in _SPACE_KEY_NAMES:
            return True
        return value.lower() in _SPACE_KEY_NAMES and self.key == " "


@dataclass(slots=True)
class TouchPoint:
    """Public TouchPoint value."""

    id: int
    x: float
    y: float
    previous_x: float | None = None
    previous_y: float | None = None
    pressure: float | None = None
    phase: str | None = None
    timestamp: float | None = None
    device: str | None = None

    @property
    def position(self) -> Vector:
        return Vector(self.x, self.y)

    @property
    def previous_position(self) -> Vector | None:
        if self.previous_x is None or self.previous_y is None:
            return None
        return Vector(self.previous_x, self.previous_y)

    @property
    def delta(self) -> Vector | None:
        previous = self.previous_position
        if previous is None:
            return None
        return self.position - previous


@dataclass(slots=True)
class TouchEvent:
    """Public TouchEvent value."""

    touches: list[TouchPoint] = field(default_factory=list)
    changed_touches: list[TouchPoint] = field(default_factory=list)
    type: str = "touch"


@dataclass(slots=True)
class MotionEvent:
    """Public MotionEvent value."""

    acceleration_x: float = 0.0
    acceleration_y: float = 0.0
    acceleration_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    orientation: str = "unknown"
    previous_acceleration_x: float = 0.0
    previous_acceleration_y: float = 0.0
    previous_acceleration_z: float = 0.0
    previous_rotation_x: float = 0.0
    previous_rotation_y: float = 0.0
    previous_rotation_z: float = 0.0
    turn_axis: str | None = None
    timestamp: float | None = None
    type: str = "motion"

    @property
    def acceleration(self) -> Vector:
        return Vector(self.acceleration_x, self.acceleration_y, self.acceleration_z)

    @property
    def previous_acceleration(self) -> Vector:
        return Vector(
            self.previous_acceleration_x,
            self.previous_acceleration_y,
            self.previous_acceleration_z,
        )

    @property
    def rotation(self) -> Vector:
        return Vector(self.rotation_x, self.rotation_y, self.rotation_z)

    @property
    def previous_rotation(self) -> Vector:
        return Vector(self.previous_rotation_x, self.previous_rotation_y, self.previous_rotation_z)


def _update_motion_state(
    state: _MotionState,
    *,
    acceleration_x: float | None = None,
    acceleration_y: float | None = None,
    acceleration_z: float | None = None,
    rotation_x: float | None = None,
    rotation_y: float | None = None,
    rotation_z: float | None = None,
    orientation: str | None = None,
) -> MotionEvent:
    state.previous_acceleration_x = state.acceleration_x
    state.previous_acceleration_y = state.acceleration_y
    state.previous_acceleration_z = state.acceleration_z
    state.previous_rotation_x = state.rotation_x
    state.previous_rotation_y = state.rotation_y
    state.previous_rotation_z = state.rotation_z
    if acceleration_x is not None:
        state.acceleration_x = float(acceleration_x)
    if acceleration_y is not None:
        state.acceleration_y = float(acceleration_y)
    if acceleration_z is not None:
        state.acceleration_z = float(acceleration_z)
    if rotation_x is not None:
        state.rotation_x = float(rotation_x)
    if rotation_y is not None:
        state.rotation_y = float(rotation_y)
    if rotation_z is not None:
        state.rotation_z = float(rotation_z)
    if orientation is not None:
        state.device_orientation = str(orientation)
    deltas = {
        "x": abs(state.rotation_x - state.previous_rotation_x),
        "y": abs(state.rotation_y - state.previous_rotation_y),
        "z": abs(state.rotation_z - state.previous_rotation_z),
    }
    axis, amount = max(deltas.items(), key=lambda item: item[1])
    state.turn_axis = axis if amount >= state.move_threshold else None
    return MotionEvent(
        acceleration_x=state.acceleration_x,
        acceleration_y=state.acceleration_y,
        acceleration_z=state.acceleration_z,
        rotation_x=state.rotation_x,
        rotation_y=state.rotation_y,
        rotation_z=state.rotation_z,
        orientation=state.device_orientation,
        previous_acceleration_x=state.previous_acceleration_x,
        previous_acceleration_y=state.previous_acceleration_y,
        previous_acceleration_z=state.previous_acceleration_z,
        previous_rotation_x=state.previous_rotation_x,
        previous_rotation_y=state.previous_rotation_y,
        previous_rotation_z=state.previous_rotation_z,
        turn_axis=state.turn_axis,
    )
