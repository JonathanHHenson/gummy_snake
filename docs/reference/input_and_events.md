# Input and Events

Interactive input is available when the installed canvas runtime supports a
native window.

## State Functions

- `mouse_x()`
- `mouse_y()`
- `pmouse_x()`
- `pmouse_y()`
- `moved_x()`
- `moved_y()`
- `mouse_is_pressed()`
- `mouse_is_inside_window()`
- `mouse_button()`
- `key()`
- `key_code()`
- `key_is_pressed()`
- `key_is_down(code)`
- `start_text_input()`
- `stop_text_input()`
- `is_text_input_active()`
- `touches()`
- `pointer_lock_mode(mode=None)`
- `request_pointer_lock()`
- `exit_pointer_lock()`
- `focused()`

## Property Facades

The `gs.mouse` and `gs.keyboard` facades provide property-style access while a
sketch callback is active:

- `gs.mouse.x`
- `gs.mouse.y`
- `gs.mouse.position`
- `gs.mouse.previous_position`
- `gs.mouse.moved_x`
- `gs.mouse.moved_y`
- `gs.mouse.wheel`
- `gs.mouse.is_pressed`
- `gs.mouse.is_inside_window`
- `gs.mouse.button`
- `gs.mouse.is_pointer_locked`
- `gs.mouse.pointer_lock_mode`
- `gs.mouse.set_pointer_lock_mode(mode)`
- `gs.keyboard.key`
- `gs.keyboard.code`
- `gs.keyboard.physical_code`
- `gs.keyboard.text`
- `gs.keyboard.is_pressed`
- `gs.keyboard.is_down(code_or_character)`
- `gs.keyboard.is_text_input_active`
- `gs.keyboard.start_text_input()`
- `gs.keyboard.stop_text_input()`

Mouse coordinates are logical canvas coordinates. Native runtimes may also
provide event window coordinates on `MouseEvent.window_position`. Wheel deltas
are accumulated for the current frame on `gs.mouse.wheel`.
`gs.mouse.is_inside_window` reports whether the native runtime currently sees
the mouse inside the window; it updates from SDL enter/leave events and remains
true while pointer lock is active.

Keyboard state tracks the display key, numeric key code, physical code string,
typed text, repeat flag, and simultaneous pressed keys. `key_is_down()` accepts
numeric key codes and string identifiers.

`key_typed` callbacks are driven by native text input, not raw key-down events.
Call `start_text_input()` or `gs.keyboard.start_text_input()` when a sketch is
ready to collect text, and call `stop_text_input()` when text entry should end.
Regular `key_pressed` and `key_released` callbacks continue to run regardless of
text input state.

Pointer lock is available only when the native canvas backend reports support.
Unsupported runtimes raise `BackendCapabilityError` with runtime/rebuild
guidance.

Pointer-lock coordinate handling is controlled by `pointer_lock_mode(mode)` or
`gs.mouse.set_pointer_lock_mode(mode)`. Modes are:

- `gs.CLAMPED` / `"clamped"`: locked coordinates are clamped to the canvas bounds.
- `gs.UNCLAMPED` / `"unclamped"`: locked coordinates accumulate relative deltas without bounds.
- `gs.FIXED` / `"fixed"`: locked coordinates stay at the canvas center while deltas still report movement.

## Callback Names

Define callbacks on a function-mode sketch module or on a `Sketch` subclass:

- `mouse_moved(event)`
- `mouse_dragged(event)`
- `mouse_pressed(event)`
- `mouse_released(event)`
- `mouse_clicked(event)`
- `mouse_double_clicked(event)`
- `mouse_wheel(event)`
- `key_pressed(event)`
- `key_released(event)`
- `key_typed(event)`
- `touch_started(event)`
- `touch_moved(event)`
- `touch_ended(event)`
- `touch_cancelled(event)`

Callbacks may also be declared without an event parameter.

Event objects expose Python-friendly helpers:

- `MouseEvent.position`
- `MouseEvent.previous_position`
- `MouseEvent.window_position`
- `MouseEvent.delta`
- `MouseEvent.scroll`
- `MouseEvent.click_count`
- `KeyboardEvent.code`
- `KeyboardEvent.text`
- `KeyboardEvent.repeat`
- `KeyboardEvent.matches(value)`
- `TouchPoint.position`
- `TouchPoint.previous_position`
- `TouchPoint.delta`
