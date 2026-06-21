"""Mouse, keyboard, movement deltas, buttons, and touch state access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/05_interaction/input_state.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
POINTER_LOCK_STATUS = "unavailable unless native runtime exposes it"
POINTER_LOCK_MODES = (gs.CLAMPED, gs.UNCLAMPED, gs.FIXED)
TYPED_TEXT = ""


@gs.setup
def setup() -> None:
    gs.create_canvas(620, 360)
    gs.frame_rate(60)


@gs.draw
def draw() -> None:
    gs.background(238, 241, 236)
    position = gs.mouse.position
    x = position.x if gs.mouse.is_inside_window else 310
    y = position.y if gs.mouse.is_inside_window else 180

    gs.no_stroke()
    gs.fill(34, 118, 210, 210 if gs.mouse.is_pressed else 130)
    gs.circle(x, y, 54)
    gs.stroke(32, 36, 44)
    gs.line(gs.mouse.previous_position, position)

    gs.no_stroke()
    gs.fill(30, 34, 44)
    gs.text_size(15)
    rows = [
        f"mouse: ({gs.mouse.x:.1f}, {gs.mouse.y:.1f})",
        f"previous: ({gs.mouse.previous_x:.1f}, {gs.mouse.previous_y:.1f})",
        f"moved: ({gs.mouse.moved_x:.1f}, {gs.mouse.moved_y:.1f})",
        f"wheel: ({gs.mouse.wheel.x:.1f}, {gs.mouse.wheel.y:.1f})",
        f"inside window: {gs.mouse.is_inside_window}",
        f"mouse pressed: {gs.mouse.is_pressed}  button: {gs.mouse.button}",
        f"key pressed: {gs.keyboard.is_pressed}  key: {gs.keyboard.key}  code: {gs.keyboard.code}",
        f"physical key: {gs.keyboard.physical_code}  last typed event: {gs.keyboard.text}",
        f"text input active: {gs.keyboard.is_text_input_active}  press T to toggle",
        f"typed chars: {TYPED_TEXT[-24:]}",
        f"left arrow down: {gs.keyboard.is_down(gs.LEFT_ARROW)}",
        f"pointer lock: {POINTER_LOCK_STATUS}",
        f"lock mode: {gs.mouse.pointer_lock_mode}  press M to cycle",
        f"touch count: {len(gs.touches())}",
    ]
    for i, row in enumerate(rows):
        gs.text(row, 28, 38 + i * 28)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


@gs.on("key_pressed")
def key_pressed(event: gs.KeyboardEvent) -> None:
    global POINTER_LOCK_STATUS
    if event.matches("t"):
        if gs.keyboard.is_text_input_active:
            gs.keyboard.stop_text_input()
        else:
            gs.keyboard.start_text_input()
        return
    if event.matches("m"):
        index = POINTER_LOCK_MODES.index(gs.mouse.pointer_lock_mode)
        mode = POINTER_LOCK_MODES[(index + 1) % len(POINTER_LOCK_MODES)]
        gs.mouse.set_pointer_lock_mode(mode)
        POINTER_LOCK_STATUS = f"mode set to {mode}"
        return
    if not event.matches("l"):
        return
    try:
        if gs.mouse.is_pointer_locked:
            gs.mouse.exit_pointer_lock()
            POINTER_LOCK_STATUS = "pointer lock released"
        else:
            gs.mouse.request_pointer_lock()
            POINTER_LOCK_STATUS = "pointer lock requested"
    except gs.BackendCapabilityError:
        POINTER_LOCK_STATUS = "unavailable in this runtime"


@gs.on("key_typed")
def key_typed(event: gs.KeyboardEvent) -> None:
    global TYPED_TEXT
    if event.text:
        TYPED_TEXT += event.text
    elif event.key and len(event.key) == 1:
        TYPED_TEXT += event.key


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
