"""Property-style global-mode facades."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.core.vector import Vector, create_vector


class CurrentFacade:
    @property
    def width(self) -> int:
        """Width.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return require_context().width

    @property
    def height(self) -> int:
        """Height.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return require_context().height

    @property
    def frame_count(self) -> int:
        """Frame count.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return require_context().frame_count

    @property
    def delta_time(self) -> float:
        """Delta time.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().delta_time

    @property
    def pixel_density(self) -> float:
        """Pixel density.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().pixel_density()

    @property
    def display_density(self) -> float:
        """Display density.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().display_density()

    @property
    def is_looping(self) -> bool:
        """Is looping.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().is_looping()


class MouseFacade:
    @property
    def x(self) -> float:
        """X.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().mouse_x

    @property
    def y(self) -> float:
        """Y.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().mouse_y

    @property
    def previous_x(self) -> float:
        """Previous x.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().pmouse_x

    @property
    def previous_y(self) -> float:
        """Previous y.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().pmouse_y

    @property
    def moved_x(self) -> float:
        """Moved x.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().moved_x

    @property
    def moved_y(self) -> float:
        """Moved y.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return require_context().moved_y

    @property
    def is_pressed(self) -> bool:
        """Is pressed.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().mouse_is_pressed

    @property
    def is_inside_window(self) -> bool:
        """Is inside window.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().mouse_inside_window

    @property
    def button(self) -> str | None:
        """Button.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return require_context().mouse_button

    @property
    def position(self) -> Vector:
        """Position.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return create_vector(self.x, self.y)

    @property
    def previous_position(self) -> Vector:
        """Previous position.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        return create_vector(self.previous_x, self.previous_y)

    @property
    def wheel(self) -> Vector:
        """Wheel.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vector`.
        """
        context = require_context()
        return create_vector(context._frame_scroll_x, context._frame_scroll_y)

    @property
    def is_pointer_locked(self) -> bool:
        """Is pointer locked.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().state.input.pointer_locked

    @property
    def pointer_lock_mode(self) -> c.PointerLockMode:
        """Pointer lock mode.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `c.PointerLockMode`.
        """
        return require_context().pointer_lock_mode()

    def set_pointer_lock_mode(self, mode: c.PointerLockMode | str) -> c.PointerLockMode:
        """Set pointer lock mode.
        
        Args:
            mode: The mode value. Expected type: `c.PointerLockMode | str`.
        
        Returns:
            The return value. Type: `c.PointerLockMode`.
        """
        return require_context().set_pointer_lock_mode(mode)

    def request_pointer_lock(self) -> bool:
        """Request pointer lock.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().request_pointer_lock()

    def exit_pointer_lock(self) -> bool:
        """Exit pointer lock.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().exit_pointer_lock()


class KeyboardFacade:
    @property
    def key(self) -> str | None:
        """Key.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return require_context().key

    @property
    def code(self) -> int | None:
        """Code.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int | None`.
        """
        return require_context().key_code

    @property
    def physical_code(self) -> str | None:
        """Physical code.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return require_context().code

    @property
    def text(self) -> str | None:
        """Text.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return require_context().typed_text

    @property
    def is_text_input_active(self) -> bool:
        """Is text input active.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().is_text_input_active()

    @property
    def is_pressed(self) -> bool:
        """Is pressed.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().key_is_pressed

    def is_down(self, key_code: int | str) -> bool:
        """Is down.
        
        Args:
            key_code: The key code value. Expected type: `int | str`.
        
        Returns:
            The return value. Type: `bool`.
        """
        if isinstance(key_code, str):
            if len(key_code) != 1:
                raise ValueError("keyboard.is_down() string keys must be one character.")
            context = require_context()
            return context.key_is_down(ord(key_code.lower())) or context.key_is_down(
                ord(key_code.upper())
            )
        return require_context().key_is_down(key_code)

    def start_text_input(self) -> bool:
        """Start text input.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().start_text_input()

    def stop_text_input(self) -> bool:
        """Stop text input.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return require_context().stop_text_input()


current = CurrentFacade()
mouse = MouseFacade()
keyboard = KeyboardFacade()
