"""Pyglet interactive backend.

The first interactive backend intentionally reuses the Pillow renderer for drawing and presents
that raster surface in a native Pyglet window. This keeps p5-py backend-agnostic while leaving
room for a future custom GPU renderer.
"""

from __future__ import annotations

from typing import Any, cast

from p5_py import constants as c
from p5_py.backends.base import BackendCapabilities
from p5_py.backends.pillow import PillowRenderer
from p5_py.events.input_state import KeyboardEvent, MouseEvent


class PygletBackend:
    name = c.PYGLET
    capabilities = BackendCapabilities(
        interactive=True,
        pixels=True,
        paths=True,
        transforms=True,
        blend_modes=frozenset({c.BLEND, c.REPLACE}),
    )

    def __init__(self) -> None:
        self.renderer = PillowRenderer()
        self._window: Any | None = None
        self._pyglet: Any | None = None
        self._running = False
        self._frames_drawn = 0

    def create_canvas(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        self.renderer.resize(width, height, pixel_density)
        pyglet = self._load_pyglet()
        if self._window is None:
            self._window = pyglet.window.Window(width=width, height=height, caption="p5-py")
        else:
            self._window.set_size(width, height)

    def resize_canvas(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        self.create_canvas(width, height, pixel_density)

    def run(self, sketch, *, max_frames: int | None = None) -> None:
        pyglet = self._load_pyglet()
        if self._window is None:
            self.create_canvas(self.renderer.width, self.renderer.height)
        self._install_handlers(sketch)
        self._running = True
        interval = 1.0 / max(1.0, sketch.context.state.timing.target_frame_rate)

        def tick(_dt: float) -> None:
            if not self._running:
                pyglet.app.exit()
                return
            sketch._draw_frame()
            self._frames_drawn += 1
            if self._window is not None:
                invalidate = getattr(self._window, "invalidate", None)
                if callable(invalidate):
                    invalidate()
            if max_frames is not None and self._frames_drawn >= max_frames:
                self.stop()
                pyglet.app.exit()

        pyglet.clock.schedule_interval(tick, interval)
        pyglet.app.run()
        pyglet.clock.unschedule(tick)

    def stop(self) -> None:
        self._running = False
        if self._pyglet is not None:
            self._pyglet.app.exit()

    def present(self) -> None:
        if self._window is None:
            return
        pyglet = self._load_pyglet()
        image = self.renderer.get_image()
        data = image.tobytes()
        pyglet_image = pyglet.image.ImageData(
            self.renderer.width,
            self.renderer.height,
            "RGBA",
            data,
            pitch=-self.renderer.width * 4,
        )
        presentation_width, presentation_height = self._presentation_size()
        pyglet_image.blit(0, 0, width=presentation_width, height=presentation_height)

    def _presentation_size(self) -> tuple[int, int]:
        if self._window is None:
            return self.renderer.width, self.renderer.height
        framebuffer_size = getattr(self._window, "get_framebuffer_size", None)
        if callable(framebuffer_size):
            width, height = cast(tuple[int | float, int | float], framebuffer_size())
            return int(width), int(height)
        pixel_ratio_getter = getattr(self._window, "get_pixel_ratio", None)
        pixel_ratio = (
            float(cast(int | float, pixel_ratio_getter())) if callable(pixel_ratio_getter) else 1.0
        )
        return (
            int(round(self.renderer.width * pixel_ratio)),
            int(round(self.renderer.height * pixel_ratio)),
        )

    def _load_pyglet(self):
        if self._pyglet is None:
            import pyglet

            self._pyglet = pyglet
        return self._pyglet

    def _install_handlers(self, sketch) -> None:
        window = self._window
        if window is None:
            return

        @window.event
        def on_draw():
            window.clear()
            self.present()

        @window.event
        def on_close():
            sketch.stop()
            self.stop()
            window.close()

        @window.event
        def on_mouse_motion(x, y, dx, dy):
            event = MouseEvent(x=x, y=self.renderer.height - y, dx=dx, dy=-dy, type="mouse_moved")
            sketch.context.update_mouse_event(event)
            sketch._dispatch_callback("mouse_moved", event)

        @window.event
        def on_mouse_drag(x, y, dx, dy, buttons, modifiers):
            event = MouseEvent(
                x=x,
                y=self.renderer.height - y,
                dx=dx,
                dy=-dy,
                button=str(buttons),
                type="mouse_dragged",
            )
            sketch.context.update_mouse_event(event)
            sketch._dispatch_callback("mouse_dragged", event)

        @window.event
        def on_mouse_press(x, y, button, modifiers):
            event = MouseEvent(
                x=x,
                y=self.renderer.height - y,
                button=str(button),
                type="mouse_pressed",
            )
            sketch.context.update_mouse_event(event, pressed=True)
            sketch._dispatch_callback("mouse_pressed", event)

        @window.event
        def on_mouse_release(x, y, button, modifiers):
            event = MouseEvent(
                x=x,
                y=self.renderer.height - y,
                button=str(button),
                type="mouse_released",
            )
            sketch.context.update_mouse_event(event, pressed=False)
            sketch._dispatch_callback("mouse_released", event)

        @window.event
        def on_mouse_scroll(x, y, scroll_x, scroll_y):
            event = MouseEvent(
                x=x,
                y=self.renderer.height - y,
                scroll_x=scroll_x,
                scroll_y=scroll_y,
                type="mouse_wheel",
            )
            sketch.context.update_mouse_event(event)
            sketch._dispatch_callback("mouse_wheel", event)

        @window.event
        def on_key_press(symbol, modifiers):
            event = KeyboardEvent(
                key=chr(symbol) if 0 <= symbol <= 0x10FFFF else None,
                key_code=symbol,
            )
            sketch.context.update_keyboard_event(event, pressed=True)
            sketch._dispatch_callback("key_pressed", event)

        @window.event
        def on_key_release(symbol, modifiers):
            event = KeyboardEvent(
                key=chr(symbol) if 0 <= symbol <= 0x10FFFF else None,
                key_code=symbol,
            )
            sketch.context.update_keyboard_event(event, pressed=False)
            sketch._dispatch_callback("key_released", event)
