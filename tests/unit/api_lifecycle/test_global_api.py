from typing import Any, cast

import pytest

import gummysnake as gs
from gummysnake.core.input_event_model import KeyboardEvent, MouseEvent
from gummysnake.exceptions import ArgumentValidationError
from gummysnake.rust.canvas import canvas_gpu_available

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
        assert gs.fullscreen() is False
        assert gs.fullscreen(True) is True
        assert gs.fullscreen(False) is False
        assert gs.cursor("crosshair") == "crosshair"
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


def test_accessibility_descriptions_validate_and_replace_duplicate_labels():
    def setup():
        gs.create_canvas(10, 10)
        gs.describe("First", label="status")
        gs.describe("Second", label="status")
        with pytest.raises(ArgumentValidationError, match="description cannot be empty"):
            gs.describe("   ")
        with pytest.raises(ArgumentValidationError, match="label cannot be empty"):
            gs.describe("Valid", label=" ")

    context = gs.run(setup=setup, headless=True, max_frames=0)
    assert context.text_output() == [{"label": "status", "description": "Second"}]


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


def test_offscreen_graphics_framebuffer_and_compute_helpers():
    graphics = gs.create_graphics(4, 4)
    graphics.drawing.background(0, 0, 255)
    assert graphics.width == 4
    assert graphics.height == 4
    assert len(graphics.to_rgba_bytes()) == 4 * 4 * 4

    framebuffer = gs.create_framebuffer(2, 3, depth=True)
    assert framebuffer.depth is True
    assert framebuffer.width == 2
    framebuffer.remove()
    graphics.remove()

    if not canvas_gpu_available():
        pytest.skip("native GPU resource APIs are unavailable")

    buffer = gs.create_storage_buffer([1, 2, 3], dtype="int")
    shader = gs.create_compute_shader(
        source="""
@group(0) @binding(0) var<storage, read_write> values: array<i32>;
@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    values[gid.x] = values[gid.x] + 10;
}
""",
        label="increment",
    )
    gs.dispatch_compute(shader, 3, values=buffer)

    assert gs.read_storage_buffer(buffer) == (11, 12, 13)
    assert gs.webgpu_context()["compute_shaders"] is True
    assert gs.gpu_resource_diagnostics()["compute_dispatches"] >= 1


def test_device_sensor_sample_updates_state_and_dispatches_callbacks():
    events = []

    def setup():
        gs.create_canvas(4, 4)
        gs.set_move_threshold(0.1)
        gs.set_shake_threshold(1.0)

    def on_moved(event):
        events.append((event.type, event.acceleration_x))

    def on_turned(event):
        events.append((event.type, event.turn_axis))

    def on_shaken(event):
        events.append((event.type, event.acceleration_x))

    context = gs.run(
        setup=setup,
        device_moved=on_moved,
        device_turned=on_turned,
        device_shaken=on_shaken,
        headless=True,
        max_frames=0,
    )

    event = context.update_sensor_sample(
        acceleration_x=2.0, rotation_z=1.0, orientation="landscape"
    )

    assert event.acceleration_x == 2.0
    assert context.state.input.device_orientation == "landscape"
    assert context.state.input.turn_axis == "z"
    assert events == [("device_moved", 2.0), ("device_turned", "z"), ("device_shaken", 2.0)]


def test_object_mode_facade_exposes_advanced_epic_helpers():
    if not canvas_gpu_available():
        pytest.skip("native GPU resource APIs are unavailable")

    class AdvancedSketch(gs.Sketch):
        def setup(self):
            self.create_canvas(8, 8, renderer=gs.WEBGPU)
            buffer = self.create_storage_buffer([1, 2], dtype="int")
            shader = self.create_compute_shader(
                source="""
@group(0) @binding(0) var<storage, read_write> values: array<i32>;
@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    values[gid.x] = values[gid.x] * 2;
}
"""
            )
            self.dispatch_compute(shader, 2, values=buffer)
            assert self.read_storage_buffer(buffer) == (2, 4)
            assert self.webgpu_context()["storage_buffers"] is True

            graphics = self.create_graphics(2, 2)
            graphics.drawing.background(255)
            assert graphics.width == 2
            graphics.remove()

            audio = self.create_audio_in()
            audio.push_samples([0.5])
            assert self.create_amplitude(audio.read()).analyze() == pytest.approx(0.5)
            assert self.get_audio_context()["analysis"] is True

            self.set_move_threshold(0.1)
            self.inject_sensor_sample(rotation_x=0.2, orientation="portrait")
            assert self.turn_axis == "x"
            assert self.device_orientation == "portrait"

            self.lights()
            model = self.build_geometry(lambda: self.box(2))
            assert model.meshes
            self.free_geometry(model)

    AdvancedSketch(headless=True).run(max_frames=0)


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
