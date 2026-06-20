# Input and Events

Interactive input is available when the installed canvas extension supports a
native window.

## State Functions

- `mouse_x()`
- `mouse_y()`
- `pmouse_x()`
- `pmouse_y()`
- `moved_x()`
- `moved_y()`
- `mouse_is_pressed()`
- `mouse_button()`
- `key()`
- `key_code()`
- `key_is_pressed()`
- `key_is_down(code)`
- `touches()`
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
- `gs.mouse.is_pressed`
- `gs.mouse.button`
- `gs.keyboard.key`
- `gs.keyboard.code`
- `gs.keyboard.is_pressed`
- `gs.keyboard.is_down(code_or_character)`

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
- `MouseEvent.delta`
- `MouseEvent.scroll`
- `KeyboardEvent.matches(value)`
- `TouchPoint.position`
- `TouchPoint.previous_position`
- `TouchPoint.delta`
