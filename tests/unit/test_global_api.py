import pytest

import p5
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
