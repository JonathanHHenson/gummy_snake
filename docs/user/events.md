# Events and input state

`p5-py` normalizes mouse, keyboard, and touch state through the active `SketchContext`.

## Mouse APIs

Useful mouse state accessors include:

- `mouse_x()` / `mouse_y()`
- `pmouse_x()` / `pmouse_y()`
- `moved_x()` / `moved_y()`
- `mouse_button()`
- `mouse_is_pressed()`

You can also define callbacks such as:

- `mouse_pressed(event)`
- `mouse_released(event)`
- `mouse_moved(event)`
- `mouse_dragged(event)`
- `mouse_wheel(event)`

## Keyboard APIs

Useful keyboard state accessors include:

- `key()`
- `key_code()`
- `key_is_pressed()`
- `key_is_down(code)`

Callbacks include:

- `key_pressed(event)`
- `key_released(event)`
- `key_typed(event)`

## Touch APIs

Touch support is capability-gated. Backends that do not support touch raise a clear package-specific capability error when touch APIs are used.

Normalized touch event names are:

- `touch_started`
- `touch_moved`
- `touch_ended`

## Plugin event hooks

Plugins can observe normalized events before sketch callbacks run:

- `on_mouse_event`
- `on_keyboard_event`
- `on_touch_event`
- `on_event`

See `docs/user/plugins.md`.

## Example

`examples/asteroids.py` demonstrates normalized keyboard and mouse handling with the current runtime.
