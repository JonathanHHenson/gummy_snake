from typing import Any, cast

import pytest

import gummysnake as gs
from gummysnake.api.current import require_context
from gummysnake.core.input_event_model import KeyboardEvent, MouseEvent
from gummysnake.core.vector import Vector


def test_global_mode_async_callbacks_are_awaited():
    events = []

    async def setup():
        events.append("setup")
        gs.create_canvas(8, 8)

    async def draw():
        events.append(f"draw:{gs.frame_count()}")
        gs.no_loop()

    async def on_key(event):
        events.append(("key", event.key))

    context = gs.run(
        setup=setup, draw=draw, key_pressed=cast(Any, on_key), headless=True, max_frames=3
    )
    context.dispatch_keyboard_event(KeyboardEvent(key="x", key_code=88, type="key_pressed"))

    assert events == ["setup", "draw:0", ("key", "x")]


@pytest.mark.parametrize(
    ("loader_name", "path", "expected"),
    [
        ("load_strings_async", "values.txt", ["alpha", "beta"]),
        ("load_bytes_async", "values.txt", b"alpha\nbeta"),
        ("load_json_async", "values.json", {"answer": 42}),
    ],
)
def test_async_data_loaders(tmp_path, loader_name, path, expected):
    text_path = tmp_path / "values.txt"
    text_path.write_text("alpha\nbeta", encoding="utf-8")
    json_path = tmp_path / "values.json"
    json_path.write_text('{"answer": 42}', encoding="utf-8")

    async def setup():
        gs.create_canvas(1, 1)
        loaded = await getattr(gs, loader_name)(tmp_path / path)
        assert loaded == expected

    gs.run(setup=setup, headless=True, max_frames=0)


def test_decorator_sketch_builder_runs_callbacks_and_events():
    app = gs.sketch()
    events = []

    @app.setup
    def configure():
        gs.create_canvas(12, 9)
        events.append(("setup", gs.current.width, gs.current.height))

    @app.draw
    def render():
        events.append(("draw", gs.current.frame_count))
        gs.no_loop()

    @app.mouse_pressed
    def handle_mouse(event):
        events.append(("mouse", event.position.tuple()))

    context = app.run(headless=True, max_frames=3)
    context.dispatch_mouse_event(MouseEvent(x=2, y=3, button="left", type="mouse_pressed"))

    assert events == [("setup", 12, 9), ("draw", 0), ("mouse", (2.0, 3.0, 0.0))]


def test_decorator_event_names_accept_enums_and_strings():
    app = gs.sketch()
    events = []

    @app.setup
    def configure():
        gs.create_canvas(8, 8)

    @app.on(gs.CallbackEventName.KEY_PRESSED)
    def handle_key(event):
        events.append(("key", event.key))

    @app.on(gs.MOUSE_PRESSED)
    def handle_mouse(event):
        events.append(("mouse", event.position.tuple()))

    context = app.run(headless=True, max_frames=0)
    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))
    context.dispatch_mouse_event(MouseEvent(x=2, y=3, button="left", type="mouse_pressed"))

    assert events == [("key", "a"), ("mouse", (2.0, 3.0, 0.0))]


def test_facades_expose_current_input_state():
    seen = []

    def setup():
        gs.create_canvas(10, 10)

    def on_key(_event):
        seen.append(
            (
                gs.current.width,
                gs.mouse.position,
                gs.mouse.moved_x,
                gs.keyboard.key,
                gs.keyboard.code,
                gs.keyboard.is_down("a"),
            )
        )

    context = gs.run(setup=setup, key_pressed=on_key, headless=True, max_frames=0)
    context.dispatch_mouse_event(MouseEvent(x=4, y=5, dx=2, dy=3, type="mouse_moved"))
    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))

    assert seen == [(10, Vector(4, 5), 2, "a", 65, True)]


def test_style_and_transform_context_managers_restore_state():
    seen = []

    def setup():
        gs.create_canvas(10, 10)
        original_fill = require_context().state.style.fill_color
        with gs.style(fill=(255, 0, 0), stroke=None, stroke_weight=5):
            style = require_context().state.style
            assert style.fill_color is not None
            seen.append((style.fill_color.to_tuple(), style.stroke_color, style.stroke_weight))
        restored = require_context().state.style
        seen.append((restored.fill_color, restored.stroke_color, restored.stroke_weight))

        original_matrix = require_context().state.transform.matrix
        with gs.transform(translate=Vector(2, 3), scale=2):
            assert require_context().state.transform.matrix != original_matrix
        assert require_context().state.transform.matrix == original_matrix
        assert restored.fill_color == original_fill

    gs.run(setup=setup, headless=True, max_frames=0)

    assert seen[0] == ((255, 0, 0, 255), None, 5)
    assert seen[1][2] == 1


def test_vector_like_drawing_arguments():
    def setup():
        gs.create_canvas(20, 20)

    def draw():
        gs.point(Vector(1, 2))
        gs.line(Vector(0, 0), Vector(4, 4))
        gs.triangle(Vector(0, 0), Vector(4, 0), Vector(2, 3))
        gs.quad(Vector(0, 0), Vector(4, 0), Vector(4, 4), Vector(0, 4))
        gs.no_loop()

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    assert context.frame_count == 1
