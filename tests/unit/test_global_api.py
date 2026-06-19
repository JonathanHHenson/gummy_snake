import pytest

import p5
from p5.api.current import require_context
from p5.core.vector import Vector
from p5.events.input_state import KeyboardEvent, MouseEvent
from p5.exceptions import ArgumentValidationError

_GLOBAL_CALLBACK_EVENTS = []


def mouse_pressed(event):
    _GLOBAL_CALLBACK_EVENTS.append(("global_mouse_pressed", event.x, event.y))


def test_global_mode_explicit_callbacks():
    frames = []

    def setup():
        p5.create_canvas(16, 12)
        p5.background(0)

    def draw():
        frames.append(p5.frame_count())
        p5.fill(255, 0, 0)
        p5.no_stroke()
        p5.circle(8, 6, 6)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=2)

    assert frames == [0, 1]
    assert context.width == 16
    assert context.height == 12
    assert context.frame_count == 2


def test_global_mode_explicit_event_callbacks():
    events = []

    def setup():
        p5.create_canvas(16, 12)

    def on_key(event):
        events.append(("key_pressed", event.key, event.key_code))

    context = p5.run(
        setup=setup,
        key_pressed=on_key,
        headless=True,
        max_frames=0,
    )

    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))

    assert events == [("key_pressed", "a", 65)]


def test_global_mode_event_callbacks_have_active_context():
    def setup():
        p5.create_canvas(16, 12)

    def on_key(_event):
        p5.no_loop()

    context = p5.run(
        setup=setup,
        key_pressed=on_key,
        headless=True,
        max_frames=0,
    )

    assert context.is_looping() is True

    context.dispatch_keyboard_event(KeyboardEvent(key="p", key_code=80, type="key_pressed"))

    assert context.is_looping() is False


def test_global_mode_module_event_callback_discovery():
    _GLOBAL_CALLBACK_EVENTS.clear()

    def setup():
        p5.create_canvas(16, 12)

    context = p5.run(setup=setup, headless=True, max_frames=0)

    context.dispatch_mouse_event(MouseEvent(x=5, y=7, button="left", type="mouse_pressed"))

    assert _GLOBAL_CALLBACK_EVENTS == [("global_mouse_pressed", 5, 7)]


def test_camel_case_aliases_are_not_exported():
    assert not hasattr(p5, "createCanvas")
    assert not hasattr(p5, "noStroke")
    assert not hasattr(p5, "imageSampling")


def test_image_sampling_api():
    def setup():
        p5.create_canvas(4, 4)
        assert p5.image_sampling() == p5.LINEAR
        p5.no_smooth()
        assert p5.image_sampling() == p5.NEAREST
        p5.smooth()
        assert p5.image_sampling() == p5.LINEAR
        p5.image_sampling(p5.NEAREST)
        assert p5.image_sampling() == p5.NEAREST
        p5.smooth()
        with pytest.raises(ArgumentValidationError):
            p5.image_sampling("bogus")

    p5.run(setup=setup, draw=lambda: None, headless=True, max_frames=0)


def test_global_mode_async_callbacks_are_awaited():
    events = []

    async def setup():
        events.append("setup")
        p5.create_canvas(8, 8)

    async def draw():
        events.append(f"draw:{p5.frame_count()}")
        p5.no_loop()

    async def on_key(event):
        events.append(("key", event.key))

    context = p5.run(setup=setup, draw=draw, key_pressed=on_key, headless=True, max_frames=3)
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
        p5.create_canvas(1, 1)
        loaded = await getattr(p5, loader_name)(tmp_path / path)
        assert loaded == expected

    p5.run(setup=setup, headless=True, max_frames=0)


def test_decorator_sketch_builder_runs_callbacks_and_events():
    app = p5.sketch()
    events = []

    @app.setup
    def configure():
        p5.create_canvas(12, 9)
        events.append(("setup", p5.current.width, p5.current.height))

    @app.draw
    def render():
        events.append(("draw", p5.current.frame_count))
        p5.no_loop()

    @app.mouse_pressed
    def handle_mouse(event):
        events.append(("mouse", event.position.tuple()))

    context = app.run(headless=True, max_frames=3)
    context.dispatch_mouse_event(MouseEvent(x=2, y=3, button="left", type="mouse_pressed"))

    assert events == [("setup", 12, 9), ("draw", 0), ("mouse", (2.0, 3.0, 0.0))]


def test_decorator_event_names_accept_enums_and_strings():
    app = p5.sketch()
    events = []

    @app.setup
    def configure():
        p5.create_canvas(8, 8)

    @app.on(p5.CallbackEventName.KEY_PRESSED)
    def handle_key(event):
        events.append(("key", event.key))

    @app.on(p5.MOUSE_PRESSED)
    def handle_mouse(event):
        events.append(("mouse", event.position.tuple()))

    context = app.run(headless=True, max_frames=0)
    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))
    context.dispatch_mouse_event(MouseEvent(x=2, y=3, button="left", type="mouse_pressed"))

    assert events == [("key", "a"), ("mouse", (2.0, 3.0, 0.0))]


def test_facades_expose_current_input_state():
    seen = []

    def setup():
        p5.create_canvas(10, 10)

    def on_key(_event):
        seen.append(
            (
                p5.current.width,
                p5.mouse.position,
                p5.mouse.moved_x,
                p5.keyboard.key,
                p5.keyboard.code,
                p5.keyboard.is_down("a"),
            )
        )

    context = p5.run(setup=setup, key_pressed=on_key, headless=True, max_frames=0)
    context.dispatch_mouse_event(MouseEvent(x=4, y=5, dx=2, dy=3, type="mouse_moved"))
    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))

    assert seen == [(10, Vector(4, 5), 2, "a", 65, True)]


def test_style_and_transform_context_managers_restore_state():
    seen = []

    def setup():
        p5.create_canvas(10, 10)
        original_fill = require_context().state.style.fill_color
        with p5.style(fill=(255, 0, 0), stroke=None, stroke_weight=5):
            style = require_context().state.style
            seen.append((style.fill_color.to_tuple(), style.stroke_color, style.stroke_weight))
        restored = require_context().state.style
        seen.append((restored.fill_color, restored.stroke_color, restored.stroke_weight))

        original_matrix = require_context().state.transform.matrix
        with p5.transform(translate=Vector(2, 3), scale=2):
            assert require_context().state.transform.matrix != original_matrix
        assert require_context().state.transform.matrix == original_matrix
        assert restored.fill_color == original_fill

    p5.run(setup=setup, headless=True, max_frames=0)

    assert seen[0] == ((255, 0, 0, 255), None, 5)
    assert seen[1][2] == 1


def test_vector_like_drawing_arguments():
    def setup():
        p5.create_canvas(20, 20)

    def draw():
        p5.point(Vector(1, 2))
        p5.line(Vector(0, 0), Vector(4, 4))
        p5.triangle(Vector(0, 0), Vector(4, 0), Vector(2, 3))
        p5.quad(Vector(0, 0), Vector(4, 0), Vector(4, 4), Vector(0, 4))
        p5.no_loop()

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

    assert context.frame_count == 1
