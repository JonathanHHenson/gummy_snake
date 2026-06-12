from p5_py.backends.pyglet import PygletBackend


class FakeFramebufferWindow:
    def get_framebuffer_size(self):
        return 1280, 840


class FakePixelRatioWindow:
    def get_pixel_ratio(self):
        return 2.0


def test_pyglet_presentation_size_uses_framebuffer_size():
    backend = PygletBackend()
    backend.renderer.resize(640, 420)
    backend._window = FakeFramebufferWindow()

    assert backend._presentation_size() == (1280, 840)


def test_pyglet_presentation_size_falls_back_to_pixel_ratio():
    backend = PygletBackend()
    backend.renderer.resize(640, 420)
    backend._window = FakePixelRatioWindow()

    assert backend._presentation_size() == (1280, 840)
