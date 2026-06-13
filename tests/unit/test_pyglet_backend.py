from p5_py.backends.pyglet import PygletBackend
from p5_py.backends.pyglet_webgl_renderer import PygletWebGLRenderer


class FakeBatch:
    def draw(self):
        pass


class FakeGraphics:
    @staticmethod
    def Batch():
        return FakeBatch()


class FakeFramebufferWindow:
    def get_framebuffer_size(self):
        return 1280, 840


class FakePixelRatioWindow:
    def __init__(self, *, vsync=False):
        self.vsync = vsync

    def get_pixel_ratio(self):
        return 2.0


class FakeConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeGL:
    Config = FakeConfig


class FakePygletModule:
    graphics = FakeGraphics()
    gl = FakeGL()
    last_window: FakePixelRatioWindow | None = None
    last_window_kwargs: dict | None = None

    class window:
        @staticmethod
        def Window(width, height, caption, vsync=False, **kwargs):
            FakePygletModule.last_window = FakePixelRatioWindow(vsync=vsync)
            FakePygletModule.last_window_kwargs = kwargs
            return FakePygletModule.last_window


class FakeFramebufferPygletModule:
    graphics = FakeGraphics()
    gl = FakeGL()

    class window:
        @staticmethod
        def Window(width, height, caption, vsync=False, **kwargs):
            return FakeFramebufferWindow()


def test_pyglet_framebuffer_size_uses_framebuffer_size():
    backend = PygletBackend()
    backend.renderer.resize(640, 420)
    backend._window = FakeFramebufferWindow()

    assert backend._framebuffer_size() == (1280, 840)


def test_pyglet_framebuffer_size_falls_back_to_pixel_ratio():
    backend = PygletBackend()
    backend.renderer.resize(640, 420)
    backend._window = FakePixelRatioWindow()

    assert backend._framebuffer_size() == (1280, 840)


def test_pyglet_create_canvas_defaults_to_display_density():
    backend = PygletBackend()
    backend._pyglet = FakePygletModule()

    backend.create_canvas(640, 420)

    assert backend.renderer.width == 640
    assert backend.renderer.height == 420
    assert backend.renderer.pixel_density == 2
    assert backend.renderer.physical_width == 1280
    assert backend.renderer.physical_height == 840
    assert FakePygletModule.last_window is not None
    assert FakePygletModule.last_window.vsync is False


def test_pyglet_create_canvas_uses_framebuffer_density_fallback():
    backend = PygletBackend()
    backend._pyglet = FakeFramebufferPygletModule()

    backend.create_canvas(640, 420)

    assert backend.renderer.pixel_density == 2
    assert backend.renderer.physical_width == 1280
    assert backend.renderer.physical_height == 840


def test_pyglet_create_canvas_uses_native_webgl_renderer_and_depth_config():
    backend = PygletBackend()
    backend._pyglet = FakePygletModule()

    backend.create_canvas(320, 240, renderer="webgl")

    assert isinstance(backend.renderer, PygletWebGLRenderer)
    assert FakePygletModule.last_window_kwargs is not None
    config = FakePygletModule.last_window_kwargs["config"]
    assert isinstance(config, FakeConfig)
    assert config.kwargs == {"double_buffer": True, "depth_size": 24}


def test_pyglet_pointer_coordinates_are_scaled_to_logical_canvas_space():
    backend = PygletBackend()
    backend.renderer.resize(640, 420, pixel_density=2)

    assert backend._logical_pointer_position(320, 200) == (160, 320)
    assert backend._logical_pointer_delta(12, -8) == (6, 4)


def test_next_frame_delay_compensates_for_late_callback():
    backend = PygletBackend()
    interval = 1.0 / 60.0
    backend._next_frame_time = 0.0

    first_delay = backend._next_frame_delay(0.002, interval)
    second_delay = backend._next_frame_delay(0.0197, interval)

    assert first_delay == interval - 0.002
    assert second_delay == 2 * interval - 0.0197
    assert second_delay < interval


def test_next_frame_delay_skips_missed_frames_after_large_delay():
    backend = PygletBackend()
    interval = 1.0 / 60.0
    backend._next_frame_time = 0.0

    delay = backend._next_frame_delay(0.250, interval)

    assert 0.0 < delay <= interval
    assert backend._next_frame_time > 0.250
