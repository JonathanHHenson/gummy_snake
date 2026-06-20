from typing import Any, cast

import pytest

import gummysnake as gs
from gummysnake.api.current import require_context
from gummysnake.core.vector import Vector
from gummysnake.events.input_state import KeyboardEvent, MouseEvent
from gummysnake.exceptions import ArgumentValidationError

_GLOBAL_CALLBACK_EVENTS = []


def mouse_pressed(event):
    _GLOBAL_CALLBACK_EVENTS.append(("global_mouse_pressed", event.x, event.y))


def test_global_mode_explicit_callbacks():
    frames = []

    def setup():
        gs.create_canvas(16, 12)
        gs.background(0)

    def draw():
        frames.append(gs.frame_count())
        gs.fill(255, 0, 0)
        gs.no_stroke()
        gs.circle(8, 6, 6)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=2)

    assert frames == [0, 1]
    assert context.width == 16
    assert context.height == 12
    assert context.frame_count == 2


def test_global_mode_explicit_event_callbacks():
    events = []

    def setup():
        gs.create_canvas(16, 12)

    def on_key(event):
        events.append(("key_pressed", event.key, event.key_code))

    context = gs.run(
        setup=setup,
        key_pressed=on_key,
        headless=True,
        max_frames=0,
    )

    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))

    assert events == [("key_pressed", "a", 65)]


def test_global_mode_event_callbacks_have_active_context():
    def setup():
        gs.create_canvas(16, 12)

    def on_key(_event):
        gs.no_loop()

    context = gs.run(
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
        gs.create_canvas(16, 12)

    context = gs.run(setup=setup, headless=True, max_frames=0)

    context.dispatch_mouse_event(MouseEvent(x=5, y=7, button="left", type="mouse_pressed"))

    assert _GLOBAL_CALLBACK_EVENTS == [("global_mouse_pressed", 5, 7)]


def test_camel_case_aliases_are_not_exported():
    assert not hasattr(gs, "createCanvas")
    assert not hasattr(gs, "noStroke")
    assert not hasattr(gs, "imageSampling")


def test_environment_helpers():
    def setup():
        gs.create_canvas(10, 12)
        gs.frame_rate(24)

    def draw():
        assert gs.get_target_frame_rate() == 24
        assert gs.window_width() == 10
        assert gs.window_height() == 12
        assert gs.display_width() >= 10
        assert gs.display_height() >= 12
        assert gs.focused() is True
        gs.cursor()
        gs.no_cursor()

    gs.run(setup=setup, draw=draw, headless=True, max_frames=1)


def test_accessibility_helpers_store_native_metadata():
    def setup():
        gs.create_canvas(10, 10)
        assert gs.describe("A test canvas") == {
            "label": "canvas",
            "description": "A test canvas",
        }
        assert gs.describe_element("circle", "A small circle") == {
            "label": "circle",
            "description": "A small circle",
        }

    context = gs.run(setup=setup, headless=True, max_frames=0)
    assert context.text_output() == [
        {"label": "canvas", "description": "A test canvas"},
        {"label": "circle", "description": "A small circle"},
    ]
    assert context.grid_output() == context.text_output()


def test_image_sampling_api():
    def setup():
        gs.create_canvas(4, 4)
        assert gs.image_sampling() == gs.LINEAR
        gs.no_smooth()
        assert gs.image_sampling() == gs.NEAREST
        gs.smooth()
        assert gs.image_sampling() == gs.LINEAR
        gs.image_sampling(gs.NEAREST)
        assert gs.image_sampling() == gs.NEAREST
        gs.smooth()
        with pytest.raises(ArgumentValidationError):
            gs.image_sampling(cast(Any, "bogus"))

    gs.run(setup=setup, draw=lambda: None, headless=True, max_frames=0)


def test_fast_draw_scope_composes_with_style_and_transform_contexts():
    def setup():
        gs.create_canvas(16, 16)
        gs.background(0, 0, 0, 255)
        gs.no_stroke()
        with gs.style(fill=(255, 0, 0, 255)), gs.transform(translate=(4, 0)):
            draw = gs.fast()
            draw.rect(0, 0, 4, 4)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    pixels = context.load_pixels()

    def pixel_at(x: int, y: int) -> list[int]:
        offset = (y * context.state.canvas.physical_width + x) * 4
        return pixels[offset : offset + 4]

    assert pixel_at(0, 0) == [0, 0, 0, 255]
    assert pixel_at(4, 0) == [255, 0, 0, 255]


def test_fast_draw_scope_is_available_on_object_oriented_sketches():
    class FastSketch(gs.Sketch):
        def setup(self):
            self.create_canvas(8, 8)

        def draw(self):
            self.background(0)
            self.no_stroke()
            self.fill(255)
            self.fast().circle(4, 4, 4)

    context = FastSketch(headless=True).run(max_frames=1)

    assert context.load_pixels()[0:4] == [0, 0, 0, 255]
    assert any(value == 255 for value in context.load_pixels())


def test_performance_diagnostics_are_opt_in_and_use_public_terms():
    image = gs.create_image(1, 1)
    image.update_pixels(bytes([255, 0, 0, 255]))

    def setup():
        gs.create_canvas(2, 1)
        gs.image(image, 0, 0)
        assert gs.performance_diagnostics()["counters"] == {}
        gs.enable_performance_diagnostics()
        gs.image(image, 0, 0)
        gs.image(image, 1, 0)
        gs.load_pixels()
        gs.update_pixels(bytes([0, 0, 0, 255, 255, 0, 0, 255]))

    context = gs.run(setup=setup, headless=True, max_frames=0)
    diagnostics = context.performance_diagnostics()
    counters = cast(dict[str, int], diagnostics["counters"])
    messages = "\n".join(cast(list[str], diagnostics["messages"]))

    assert diagnostics["enabled"] is True
    assert counters["texture_upload"] == 1
    assert counters["texture_cache_hit"] == 1
    assert counters["pixel_readback"] >= 1
    assert counters["pixel_upload"] == 1
    assert "Pixel readback" in messages
    assert "Rust" not in messages


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
