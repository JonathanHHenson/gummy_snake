"""Backend-normalized input state."""

from __future__ import annotations

from dataclasses import dataclass, field

from gummysnake import constants as c
from gummysnake.core.vector import Vector
from gummysnake.exceptions import BackendCapabilityError

_SPACE_KEY_NAMES = {"space", "spacebar"}


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
        """Return the position vector for this event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return Vector(self.x, self.y)

    @property
    def delta(self) -> Vector:
        """Return the movement delta for this event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return Vector(self.dx, self.dy)

    @property
    def previous_position(self) -> Vector | None:
        """Return the previous position vector for this event, if available.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector | None`.
        """
        if self.previous_x is None or self.previous_y is None:
            return None
        return Vector(self.previous_x, self.previous_y)

    @property
    def window_position(self) -> Vector | None:
        """Return the window position vector for this event, if available.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector | None`.
        """
        if self.window_x is None or self.window_y is None:
            return None
        return Vector(self.window_x, self.window_y)

    @property
    def scroll(self) -> Vector:
        """Return the scroll delta vector for this event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
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
        """Return whether this keyboard event matches a key or code.
        
        Args:
            value: The value value. Expected type: `str | int`.
        
        Returns:
            The return value. Type: `bool`.
        """
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
        """Return the position vector for this event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return Vector(self.x, self.y)

    @property
    def previous_position(self) -> Vector | None:
        """Return the previous position vector for this event, if available.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector | None`.
        """
        if self.previous_x is None or self.previous_y is None:
            return None
        return Vector(self.previous_x, self.previous_y)

    @property
    def delta(self) -> Vector | None:
        """Return the movement delta for this event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector | None`.
        """
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
        """Return the acceleration vector for this motion event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return Vector(self.acceleration_x, self.acceleration_y, self.acceleration_z)

    @property
    def previous_acceleration(self) -> Vector:
        """Return the previous acceleration vector for this motion event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return Vector(
            self.previous_acceleration_x,
            self.previous_acceleration_y,
            self.previous_acceleration_z,
        )

    @property
    def rotation(self) -> Vector:
        """Return the rotation vector for this motion event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return Vector(self.rotation_x, self.rotation_y, self.rotation_z)

    @property
    def previous_rotation(self) -> Vector:
        """Return the previous rotation vector for this motion event.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return Vector(self.previous_rotation_x, self.previous_rotation_y, self.previous_rotation_z)


@dataclass(slots=True)
class InputState:
    """Public InputState value."""
    mouse_x: float = 0.0
    mouse_y: float = 0.0
    previous_mouse_x: float = 0.0
    previous_mouse_y: float = 0.0
    moved_x: float = 0.0
    moved_y: float = 0.0
    mouse_is_pressed: bool = False
    mouse_inside_window: bool = False
    mouse_button: str | None = None
    key: str | None = None
    key_code: int | None = None
    code: str | None = None
    text: str | None = None
    text_input_active: bool = False
    key_is_pressed: bool = False
    pressed_keys: set[int] = field(default_factory=set)
    pressed_codes: set[str] = field(default_factory=set)
    touches: list[TouchPoint] = field(default_factory=list)
    touch_supported: bool = False
    pointer_locked: bool = False
    pointer_lock_mode: c.PointerLockMode = c.CLAMPED
    acceleration_x: float = 0.0
    acceleration_y: float = 0.0
    acceleration_z: float = 0.0
    previous_acceleration_x: float = 0.0
    previous_acceleration_y: float = 0.0
    previous_acceleration_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    previous_rotation_x: float = 0.0
    previous_rotation_y: float = 0.0
    previous_rotation_z: float = 0.0
    device_orientation: str = "unknown"
    turn_axis: str | None = None
    move_threshold: float = 0.5
    shake_threshold: float = 30.0

    def update_motion(
        self,
        *,
        acceleration_x: float | None = None,
        acceleration_y: float | None = None,
        acceleration_z: float | None = None,
        rotation_x: float | None = None,
        rotation_y: float | None = None,
        rotation_z: float | None = None,
        orientation: str | None = None,
    ) -> MotionEvent:
        """Update motion for this InputState.
        
        Args:
            acceleration_x: The acceleration x value. Expected type: `float | None`. Defaults to
                `None`.
            acceleration_y: The acceleration y value. Expected type: `float | None`. Defaults to
                `None`.
            acceleration_z: The acceleration z value. Expected type: `float | None`. Defaults to
                `None`.
            rotation_x: The rotation x value. Expected type: `float | None`. Defaults to `None`.
            rotation_y: The rotation y value. Expected type: `float | None`. Defaults to `None`.
            rotation_z: The rotation z value. Expected type: `float | None`. Defaults to `None`.
            orientation: The orientation value. Expected type: `str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `MotionEvent`.
        """
        self.previous_acceleration_x = self.acceleration_x
        self.previous_acceleration_y = self.acceleration_y
        self.previous_acceleration_z = self.acceleration_z
        self.previous_rotation_x = self.rotation_x
        self.previous_rotation_y = self.rotation_y
        self.previous_rotation_z = self.rotation_z
        if acceleration_x is not None:
            self.acceleration_x = float(acceleration_x)
        if acceleration_y is not None:
            self.acceleration_y = float(acceleration_y)
        if acceleration_z is not None:
            self.acceleration_z = float(acceleration_z)
        if rotation_x is not None:
            self.rotation_x = float(rotation_x)
        if rotation_y is not None:
            self.rotation_y = float(rotation_y)
        if rotation_z is not None:
            self.rotation_z = float(rotation_z)
        if orientation is not None:
            self.device_orientation = str(orientation)
        deltas = {
            "x": abs(self.rotation_x - self.previous_rotation_x),
            "y": abs(self.rotation_y - self.previous_rotation_y),
            "z": abs(self.rotation_z - self.previous_rotation_z),
        }
        axis, amount = max(deltas.items(), key=lambda item: item[1])
        self.turn_axis = axis if amount >= self.move_threshold else None
        return MotionEvent(
            acceleration_x=self.acceleration_x,
            acceleration_y=self.acceleration_y,
            acceleration_z=self.acceleration_z,
            rotation_x=self.rotation_x,
            rotation_y=self.rotation_y,
            rotation_z=self.rotation_z,
            orientation=self.device_orientation,
            previous_acceleration_x=self.previous_acceleration_x,
            previous_acceleration_y=self.previous_acceleration_y,
            previous_acceleration_z=self.previous_acceleration_z,
            previous_rotation_x=self.previous_rotation_x,
            previous_rotation_y=self.previous_rotation_y,
            previous_rotation_z=self.previous_rotation_z,
            turn_axis=self.turn_axis,
        )

    def update_mouse(
        self, x: float, y: float, *, dx: float | None = None, dy: float | None = None
    ) -> None:
        """Update mouse for this InputState.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            dx: The dx value. Expected type: `float | None`. Defaults to `None`.
            dy: The dy value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self.previous_mouse_x = self.mouse_x
        self.previous_mouse_y = self.mouse_y
        self.mouse_x = x
        self.mouse_y = y
        self.moved_x = self.mouse_x - self.previous_mouse_x if dx is None else dx
        self.moved_y = self.mouse_y - self.previous_mouse_y if dy is None else dy

    def update_touches(self, touches: list[TouchPoint]) -> None:
        """Update touches for this InputState.
        
        Args:
            touches: The touches value. Expected type: `list[TouchPoint]`.
        
        Returns:
            None.
        """
        previous = {touch.id: touch for touch in self.touches}
        updated: list[TouchPoint] = []
        for touch in touches:
            old = previous.get(touch.id)
            updated.append(
                TouchPoint(
                    id=touch.id,
                    x=touch.x,
                    y=touch.y,
                    previous_x=touch.previous_x
                    if touch.previous_x is not None
                    else getattr(old, "x", None),
                    previous_y=touch.previous_y
                    if touch.previous_y is not None
                    else getattr(old, "y", None),
                    pressure=touch.pressure,
                    phase=touch.phase,
                    timestamp=touch.timestamp,
                    device=touch.device,
                )
            )
        self.touches = updated

    def require_touch_supported(self) -> None:
        """Require touch supported for this InputState.
        
        Args:
            None.
        
        Returns:
            None.
        """
        if not self.touch_supported:
            raise BackendCapabilityError(
                "Touch input is not supported by the active backend yet. "
                "The touch API is present so capable future backends can provide "
                f"{c.TOUCH_STARTED}, {c.TOUCH_MOVED}, and {c.TOUCH_ENDED} events."
            )

    def set_key_down(self, key_code: int, pressed: bool) -> None:
        """Set the key down value.
        
        Args:
            key_code: The key code value. Expected type: `int`.
            pressed: The pressed value. Expected type: `bool`.
        
        Returns:
            None.
        """
        if pressed:
            self.pressed_keys.add(key_code)
        else:
            self.pressed_keys.discard(key_code)

    def set_code_down(self, code: str, pressed: bool) -> None:
        """Set the code down value.
        
        Args:
            code: The code value. Expected type: `str`.
            pressed: The pressed value. Expected type: `bool`.
        
        Returns:
            None.
        """
        if pressed:
            self.pressed_codes.add(code)
        else:
            self.pressed_codes.discard(code)

    def key_is_down(self, key_code: int) -> bool:
        """Key is down for this InputState.
        
        Args:
            key_code: The key code value. Expected type: `int`.
        
        Returns:
            The return value. Type: `bool`.
        """
        return key_code in self.pressed_keys

    def code_is_down(self, code: str) -> bool:
        """Code is down for this InputState.
        
        Args:
            code: The code value. Expected type: `str`.
        
        Returns:
            The return value. Type: `bool`.
        """
        return code in self.pressed_codes
