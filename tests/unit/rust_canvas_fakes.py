from __future__ import annotations

from pathlib import Path
from typing import cast


class FakeCanvas:
    def __init__(
        self,
        width: int,
        height: int,
        pixel_density: float,
        mode: str,
        renderer: str,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ValueError("Pixel density must be positive.")
        self.width = width
        self.height = height
        self.pixel_density = pixel_density
        self.mode = mode
        self.renderer = renderer
        self.physical_width = round(width * pixel_density)
        self.physical_height = round(height * pixel_density)
        self.calls: list[tuple[object, ...]] = []
        self.events: list[dict[str, object]] = []
        self.closed = False
        self.window_open = False
        self.pointer_lock_active = False
        self.pointer_lock_mode_value = "clamped"
        self.text_input_active_value = False
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)
        self.current_style_value: dict[str, object] | None = None
        self.current_matrix_value: tuple[float, float, float, float, float, float] = (
            1.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
        )

    def resize(self, width: int, height: int, pixel_density: float, renderer: str) -> None:
        self._resize_storage(width, height, pixel_density, renderer)
        self.calls.append(("resize", width, height, pixel_density, renderer))

    def resize_canvas(self, width: int, height: int, pixel_density: float, renderer: str) -> None:
        self._resize_storage(width, height, pixel_density, renderer)
        self.calls.append(("resize_canvas", width, height, pixel_density, renderer))

    def _resize_storage(self, width: int, height: int, pixel_density: float, renderer: str) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ValueError("Pixel density must be positive.")
        self.width = width
        self.height = height
        self.pixel_density = pixel_density
        self.renderer = renderer
        self.physical_width = round(width * pixel_density)
        self.physical_height = round(height * pixel_density)
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)

    def dimensions(self) -> tuple[int, int, int, int, float]:
        return (
            self.width,
            self.height,
            self.physical_width,
            self.physical_height,
            self.pixel_density,
        )

    def display_density(self) -> float:
        return 1.0 if not self.window_open else max(1.0, self.pixel_density)

    def gpu_available(self) -> bool:
        return True

    def image_resize_rgba(
        self, width: int, height: int, pixels: bytes, target_width: int, target_height: int
    ) -> bytes:
        return bytes(pixels[:4] * (target_width * target_height))

    def image_crop_rgba(
        self, width: int, height: int, pixels: bytes, sx: int, sy: int, sw: int, sh: int
    ) -> bytes:
        return bytes(sw * sh * 4)

    def image_alpha_composite_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        source_width: int,
        source_height: int,
        source_pixels: bytes,
        dx: int,
        dy: int,
    ) -> bytes:
        return pixels

    def image_mask_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        mask_width: int,
        mask_height: int,
        mask_pixels: bytes,
    ) -> bytes:
        return pixels

    def image_filter_rgba(
        self, width: int, height: int, pixels: bytes, mode: str, value: float | None = None
    ) -> bytes:
        return pixels

    def media_frame_to_rgba(self, width: int, height: int, channels: int, pixels: bytes) -> bytes:
        return bytes(width * height * 4)

    def gpu_status(self) -> str:
        return "available"

    def native_window_available(self) -> bool:
        return True

    def open_window(self) -> None:
        self.mode = "interactive"
        self.window_open = True
        self.closed = False
        self.calls.append(("open_window",))

    def should_close(self) -> bool:
        return self.closed

    def poll_events(self) -> list[dict[str, object]]:
        events = self.events
        self.events = []
        return events

    def pump_native_events(self) -> bool:
        return self.closed

    def request_pointer_lock(self) -> bool:
        if not self.window_open:
            raise ValueError("Native canvas window is not available for pointer lock.")
        self.pointer_lock_active = True
        self.calls.append(("request_pointer_lock",))
        return True

    def exit_pointer_lock(self) -> bool:
        self.pointer_lock_active = False
        self.calls.append(("exit_pointer_lock",))
        return True

    def pointer_locked(self) -> bool:
        return self.pointer_lock_active

    def set_pointer_lock_mode(self, mode: str) -> None:
        if mode not in {"unclamped", "clamped", "fixed"}:
            raise ValueError(
                "Pointer lock mode must be 'unclamped', 'clamped', or 'fixed'."
            )
        self.pointer_lock_mode_value = mode
        self.calls.append(("set_pointer_lock_mode", mode))

    def pointer_lock_mode(self) -> str:
        return self.pointer_lock_mode_value

    def start_text_input(self) -> bool:
        if not self.window_open:
            raise ValueError("Native canvas window is not available for text input.")
        self.text_input_active_value = True
        self.calls.append(("start_text_input",))
        return True

    def stop_text_input(self) -> bool:
        self.text_input_active_value = False
        self.calls.append(("stop_text_input",))
        return True

    def text_input_active(self) -> bool:
        return self.text_input_active_value

    def begin_frame(self) -> None:
        self.calls.append(("begin_frame",))

    def end_frame(self) -> None:
        self.calls.append(("end_frame",))

    def present(self) -> None:
        self.calls.append(("present",))

    def close(self) -> None:
        self.closed = True
        self.pointer_lock_active = False
        self.text_input_active_value = False
        self.calls.append(("close",))

    def background(self, rgba: tuple[int, int, int, int]) -> None:
        self.calls.append(("background", rgba))
        self.pixels = bytes(rgba) * (self.physical_width * self.physical_height)

    def clear(self) -> None:
        self.calls.append(("clear",))
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)

    def set_current_style(self, style: dict[str, object]) -> None:
        self.current_style_value = dict(style)
        self.calls.append(("set_current_style", self.current_style_value))

    def current_style(self) -> dict[str, object]:
        return {} if self.current_style_value is None else dict(self.current_style_value)

    def set_current_matrix(
        self, matrix: tuple[float, float, float, float, float, float]
    ) -> None:
        self.current_matrix_value = matrix
        self.calls.append(("set_current_matrix", matrix))

    def current_matrix(self) -> tuple[float, float, float, float, float, float]:
        return self.current_matrix_value

    def push_canvas_state(self) -> None:
        self.calls.append(("push_canvas_state",))

    def pop_canvas_state(self) -> None:
        self.calls.append(("pop_canvas_state",))

    def point(self, *args: object) -> None:
        self.calls.append(("point", *args))

    def line(self, *args: object) -> None:
        self.calls.append(("line", *args))

    def batch_lines(self, *args: object) -> None:
        self.calls.append(("batch_lines", *args))

    def polygon(self, *args: object) -> None:
        self.calls.append(("polygon", *args))

    def complex_polygon(self, *args: object) -> None:
        self.calls.append(("complex_polygon", *args))

    def begin_clip(self, *args: object) -> None:
        self.calls.append(("begin_clip", *args))

    def end_clip(self) -> None:
        self.calls.append(("end_clip",))

    def rect(self, *args: object) -> None:
        self.calls.append(("rect", *args))

    def triangle(self, *args: object) -> None:
        self.calls.append(("triangle", *args))

    def quad(self, *args: object) -> None:
        self.calls.append(("quad", *args))

    def ellipse(self, *args: object) -> None:
        self.calls.append(("ellipse", *args))

    def arc(self, *args: object) -> None:
        self.calls.append(("arc", *args))

    def draw_image(self, *args: object) -> None:
        self.calls.append(("draw_image", *args))

    def draw_cached_image(self, *args: object) -> None:
        self.calls.append(("draw_cached_image", *args))

    def draw_canvas_image(self, *args: object) -> None:
        self.calls.append(("draw_canvas_image", *args))

    def text(self, *args: object) -> None:
        self.calls.append(("text", *args))

    def text_batch(self, *args: object) -> None:
        self.calls.append(("text_batch", *args))

    def text_batch_current(self, *args: object) -> None:
        self.calls.append(("text_batch_current", *args))

    def text_batch_frame(self, *args: object) -> None:
        self.calls.append(("text_batch_frame", *args))

    def text_batch_frame_current(self, *args: object) -> None:
        self.calls.append(("text_batch_frame_current", *args))

    def text_width(self, value: str, style: dict[str, object]) -> float:
        self.calls.append(("text_width", value, style))
        text_size = cast(float, style["text_size"])
        return len(value) * float(text_size) * 0.5

    def text_ascent(self, style: dict[str, object]) -> float:
        self.calls.append(("text_ascent", style))
        text_size = cast(float, style["text_size"])
        return float(text_size) * 0.8

    def text_descent(self, style: dict[str, object]) -> float:
        self.calls.append(("text_descent", style))
        text_size = cast(float, style["text_size"])
        return float(text_size) * 0.2

    def load_pixels(self) -> bytes:
        return self.pixels

    def load_pixel_bytes(self) -> bytes:
        return self.pixels

    def load_pixel_region(self, x: int, y: int, width: int, height: int) -> bytes:
        self.calls.append(("load_pixel_region", x, y, width, height))
        region = bytearray(width * height * 4)
        for out_y in range(height):
            sy = y + out_y
            if sy < 0 or sy >= self.physical_height:
                continue
            for out_x in range(width):
                sx = x + out_x
                if sx < 0 or sx >= self.physical_width:
                    continue
                src = (sy * self.physical_width + sx) * 4
                dst = (out_y * width + out_x) * 4
                region[dst : dst + 4] = self.pixels[src : src + 4]
        return bytes(region)

    def update_pixels(self, pixels: bytes) -> None:
        expected = self.physical_width * self.physical_height * 4
        if len(pixels) != expected:
            raise ValueError(f"Pixel buffer length must be {expected}, got {len(pixels)}.")
        self.pixels = pixels

    def set_pixel_rgba(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        self.calls.append(("set_pixel_rgba", x, y, rgba))
        if x < 0 or y < 0 or x >= self.physical_width or y >= self.physical_height:
            return
        offset = (y * self.physical_width + x) * 4
        pixel_bytes = bytes(rgba)
        self.pixels = self.pixels[:offset] + pixel_bytes + self.pixels[offset + 4 :]

    def update_pixel_region(
        self,
        pixels: bytes,
        width: int,
        height: int,
        x: int,
        y: int,
        alpha_composite: bool = True,
    ) -> None:
        self.calls.append(("update_pixel_region", pixels, width, height, x, y, alpha_composite))

    def adjust_pixel_prefix(
        self,
        byte_limit: int,
        stride: int,
        red_delta: int,
        green_delta: int,
    ) -> None:
        self.calls.append(("adjust_pixel_prefix", byte_limit, stride, red_delta, green_delta))

    def filter_pixels(self, mode: str, value: float | None = None) -> None:
        self.calls.append(("filter_pixels", mode, value))

    def blend_region(self, *args: object) -> None:
        self.calls.append(("blend_region", *args))

    def save(self, path: str) -> None:
        self.calls.append(("save", path))
        Path(path).write_bytes(b"fake-png")
