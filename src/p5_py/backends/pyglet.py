"""Pyglet interactive backend."""

from __future__ import annotations

import time
from typing import Any, cast

from p5_py import constants as c
from p5_py.backends.base import BackendCapabilities
from p5_py.backends.pyglet_renderer import PygletRenderer
from p5_py.events.input_state import KeyboardEvent, MouseEvent


class PygletBackend:
    name = c.PYGLET
    capabilities = BackendCapabilities(
        interactive=True,
        pixels=False,
        paths=True,
        transforms=True,
        blend_modes=frozenset({c.BLEND, c.REPLACE}),
    )

    def __init__(self) -> None:
        self.renderer = PygletRenderer()
        self._window: Any | None = None
        self._pyglet: Any | None = None
        self._running = False
        self._frames_drawn = 0
        self._next_frame_time = 0.0

    def create_canvas(self, width: int, height: int, pixel_density: float | None = None) -> None:
        pyglet = self._load_pyglet()
        self.renderer.bind_pyglet(pyglet)
        if self._window is None:
            self._window = pyglet.window.Window(
                width=width, height=height, caption="p5-py", vsync=True
            )
        else:
            self._window.set_vsync(True)
            self._window.set_size(width, height)
        density = self._display_density_for_width(width) if pixel_density is None else pixel_density
        self.renderer.resize(width, height, density)

    def resize_canvas(self, width: int, height: int, pixel_density: float | None = None) -> None:
        self.create_canvas(width, height, pixel_density)

    def run(self, sketch, *, max_frames: int | None = None) -> None:
        pyglet = self._load_pyglet()
        if self._window is None:
            self.create_canvas(self.renderer.width, self.renderer.height)
        self._install_handlers(sketch)
        self._running = True
        self._frames_drawn = 0
        if max_frames == 0:
            return
        interval = 1.0 / max(1.0, sketch.context.state.timing.target_frame_rate)
        self._next_frame_time = time.perf_counter()

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
                return
            delay = self._next_frame_delay(time.perf_counter(), interval)
            pyglet.clock.schedule_once(tick, delay)

        pyglet.clock.schedule_once(tick, 0.0)
        pyglet.app.run()

    def stop(self) -> None:
        self._running = False
        if self._pyglet is not None:
            self._pyglet.app.exit()

    def display_density(self) -> float:
        return self._display_density_for_width(self.renderer.width)

    def _display_density_for_width(self, logical_width: int) -> float:
        if self._window is None:
            return 1.0
        pixel_ratio_getter = getattr(self._window, "get_pixel_ratio", None)
        if callable(pixel_ratio_getter):
            return max(1.0, float(cast(int | float, pixel_ratio_getter())))
        framebuffer_size = getattr(self._window, "get_framebuffer_size", None)
        if callable(framebuffer_size):
            width, _height = cast(tuple[int | float, int | float], framebuffer_size())
            return max(1.0, float(width) / max(1, logical_width))
        return 1.0

    def present(self) -> None:
        if self._window is None:
            return
        self.renderer.draw()

    def _framebuffer_size(self) -> tuple[int, int]:
        if self._window is None:
            return self.renderer.physical_width, self.renderer.physical_height
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

    def _next_frame_delay(self, now: float, interval: float) -> float:
        self._next_frame_time += interval
        while self._next_frame_time <= now:
            self._next_frame_time += interval
        return max(0.0, self._next_frame_time - now)

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
