"""Input state forwards for object sketches."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.core.input_events import MotionEvent, TouchPoint
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeInputMixin(SketchFacadeBaseMixin):
    """Object-mode accessors for input state and input controls."""

    @property
    def mouse_x(self) -> float:
        """Mouse x for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.mouse_x

    @property
    def mouse_y(self) -> float:
        """Mouse y for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.mouse_y

    @property
    def pmouse_x(self) -> float:
        """Return the previous pmouse x value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.pmouse_x

    @property
    def pmouse_y(self) -> float:
        """Return the previous pmouse y value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.pmouse_y

    @property
    def moved_x(self) -> float:
        """Moved x for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.moved_x

    @property
    def moved_y(self) -> float:
        """Moved y for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.moved_y

    @property
    def mouse_is_pressed(self) -> bool:
        """Mouse is pressed for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.mouse_is_pressed

    @property
    def mouse_inside_window(self) -> bool:
        """Mouse inside window for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.mouse_inside_window

    @property
    def mouse_button(self) -> str | None:
        """Mouse button for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self._ctx.mouse_button

    @property
    def key(self) -> str | None:
        """Key for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self._ctx.key

    @property
    def key_code(self) -> int | None:
        """Key code for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int | None`.
        """
        return self._ctx.key_code

    @property
    def code(self) -> str | None:
        """Code for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self._ctx.code

    @property
    def typed_text(self) -> str | None:
        """Typed text for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self._ctx.typed_text

    @property
    def key_is_pressed(self) -> bool:
        """Key is pressed for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.key_is_pressed

    @property
    def touches(self) -> list[TouchPoint]:
        """Touches for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `list[TouchPoint]`.
        """
        return self._ctx.touches

    @property
    def acceleration_x(self) -> float:
        """Acceleration x for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.acceleration_x

    @property
    def acceleration_y(self) -> float:
        """Acceleration y for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.acceleration_y

    @property
    def acceleration_z(self) -> float:
        """Acceleration z for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.acceleration_z

    @property
    def p_acceleration_x(self) -> float:
        """Return the previous acceleration x value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.previous_acceleration_x

    @property
    def p_acceleration_y(self) -> float:
        """Return the previous acceleration y value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.previous_acceleration_y

    @property
    def p_acceleration_z(self) -> float:
        """Return the previous acceleration z value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.previous_acceleration_z

    @property
    def rotation_x(self) -> float:
        """Rotation x for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.rotation_x

    @property
    def rotation_y(self) -> float:
        """Rotation y for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.rotation_y

    @property
    def rotation_z(self) -> float:
        """Rotation z for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.rotation_z

    @property
    def p_rotation_x(self) -> float:
        """Return the previous rotation x value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.previous_rotation_x

    @property
    def p_rotation_y(self) -> float:
        """Return the previous rotation y value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.previous_rotation_y

    @property
    def p_rotation_z(self) -> float:
        """Return the previous rotation z value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.state.input.previous_rotation_z

    @property
    def device_orientation(self) -> str:
        """Device orientation for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str`.
        """
        return self._ctx.state.input.device_orientation

    @property
    def turn_axis(self) -> str | None:
        """Turn axis for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self._ctx.state.input.turn_axis

    def key_is_down(self, key_code: int | str) -> bool:
        """Key is down for this SketchFacadeInputMixin.
        
        Args:
            key_code: The key code value. Expected type: `int | str`.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.key_is_down(key_code)

    def start_text_input(self) -> bool:
        """Start text input for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.start_text_input()

    def stop_text_input(self) -> bool:
        """Stop text input for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.stop_text_input()

    def is_text_input_active(self) -> bool:
        """Return whether text input active is active.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.is_text_input_active()

    def set_move_threshold(self, value: float) -> None:
        """Set the move threshold value.
        
        Args:
            value: The value value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.set_move_threshold(value)

    def set_shake_threshold(self, value: float) -> None:
        """Set the shake threshold value.
        
        Args:
            value: The value value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.set_shake_threshold(value)

    def inject_sensor_sample(
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
        """Inject sensor sample for this SketchFacadeInputMixin.
        
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
        return self._ctx.update_sensor_sample(
            acceleration_x=acceleration_x,
            acceleration_y=acceleration_y,
            acceleration_z=acceleration_z,
            rotation_x=rotation_x,
            rotation_y=rotation_y,
            rotation_z=rotation_z,
            orientation=orientation,
        )

    def request_pointer_lock(self) -> bool:
        """Request pointer lock for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.request_pointer_lock()

    def exit_pointer_lock(self) -> bool:
        """Exit pointer lock for this SketchFacadeInputMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.exit_pointer_lock()

    def pointer_lock_mode(self, mode: c.PointerLockMode | str | None = None) -> c.PointerLockMode:
        """Pointer lock mode for this SketchFacadeInputMixin.
        
        Args:
            mode: The mode value. Expected type: `c.PointerLockMode | str | None`. Defaults to
                `None`.
        
        Returns:
            The return value. Type: `c.PointerLockMode`.
        """
        if mode is None:
            return self._ctx.pointer_lock_mode()
        return self._ctx.set_pointer_lock_mode(mode)
