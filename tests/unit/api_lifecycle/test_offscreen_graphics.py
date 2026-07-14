from __future__ import annotations

import gummysnake as gs
from gummysnake.assets import graphics as graphics_module
from gummysnake.assets.graphics import GraphicsDrawingSurface
from gummysnake.backend.canvas_runtime.host.offscreen import OffscreenCanvasRuntime


def test_graphics_uses_backend_owned_isolated_canvas_and_typed_surface() -> None:
    graphics = gs.create_graphics(6, 4, pixel_density=2)
    try:
        drawing: GraphicsDrawingSurface = graphics.drawing
        drawing.background(0, 0, 255)
        drawing.rect(0, 0, 2, 2)

        snapshot = graphics.snapshot()
        assert graphics.drawing is graphics.drawing
        assert graphics.backend is graphics._offscreen.backend
        assert graphics.pixel_density() == 2.0
        assert snapshot.width == 12
        assert snapshot.height == 8
        assert graphics.cache_key == graphics.snapshot().cache_key
        assert graphics.rust_image is graphics.snapshot().rust_image
        assert len(graphics.to_rgba_bytes()) == 6 * 4 * 4 * 4
    finally:
        graphics.remove()


def test_graphics_remove_closes_its_backend_owned_runtime(monkeypatch) -> None:
    closed: list[OffscreenCanvasRuntime] = []
    original_close = graphics_module.OffscreenCanvasRuntime.close

    def close(runtime: OffscreenCanvasRuntime) -> None:
        closed.append(runtime)
        original_close(runtime)

    monkeypatch.setattr(graphics_module.OffscreenCanvasRuntime, "close", close)
    graphics = gs.create_graphics(2, 2)
    graphics.remove()

    assert closed == [graphics._offscreen]


def test_webgl_framebuffer_preserves_isolated_renderer_and_cleanup() -> None:
    framebuffer = gs.create_framebuffer(5, 3, renderer=gs.WEBGL, depth=False)
    try:
        assert framebuffer.depth is False
        assert framebuffer.context.state.canvas.renderer is gs.WEBGL
        framebuffer.drawing.background(24)
        assert framebuffer.snapshot().width == 5
    finally:
        framebuffer.remove()
