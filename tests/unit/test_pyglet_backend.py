from p5_py.backends.pyglet import PygletBackend


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


class FakePygletModule:
    graphics = FakeGraphics()
    last_window: FakePixelRatioWindow | None = None

    class window:
        @staticmethod
        def Window(width, height, caption, vsync=False):
            FakePygletModule.last_window = FakePixelRatioWindow(vsync=vsync)
            return FakePygletModule.last_window


class FakeFramebufferPygletModule:
    graphics = FakeGraphics()

    class window:
        @staticmethod
        def Window(width, height, caption, vsync=False):
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
