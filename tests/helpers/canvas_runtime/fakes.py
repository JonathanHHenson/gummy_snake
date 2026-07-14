from __future__ import annotations

from collections.abc import Buffer
from pathlib import Path
from struct import Struct
from typing import cast

from tests.helpers.canvas_runtime.image_kernels import FakeCanvasImageKernelsMixin


class FakeCanvas(FakeCanvasImageKernelsMixin):
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

    def frame_command_diagnostics(self) -> dict[str, int]:
        return {
            "abi_version": 1,
            "generation": 1,
            "storage_bytes": 0,
            "storage_capacity_bytes": 0,
            "segments": 0,
            "records": 0,
            "segment_bytes": 0,
        }

    def gpu_available(self) -> bool:
        return True

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
            raise ValueError("Pointer lock mode must be 'unclamped', 'clamped', or 'fixed'.")
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

    def set_current_matrix(self, matrix: tuple[float, float, float, float, float, float]) -> None:
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

    def batch_lines_packed(
        self,
        payload: bytes,
        style: dict[str, object],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None:
        record_format = Struct("<4d")
        records = [
            record_format.unpack_from(payload, offset) for offset in range(0, len(payload), 32)
        ]
        self.calls.append(("batch_lines", records, style, matrix))

    def batch_lines_current_packed(self, payload: bytes) -> None:
        record_format = Struct("<4d")
        records = [
            record_format.unpack_from(payload, offset) for offset in range(0, len(payload), 32)
        ]
        self.calls.append(("batch_lines_current", records))

    def batch_primitives(self, *args: object) -> None:
        self.calls.append(("batch_primitives", *args))

    def batch_primitives_packed(
        self,
        payload: bytes,
        style: dict[str, object],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None:
        record_format = Struct("<B7x6d")
        records = [
            record_format.unpack_from(payload, offset) for offset in range(0, len(payload), 56)
        ]
        self.calls.append(("batch_primitives", records, style, matrix))

    def batch_primitives_current_packed(self, payload: bytes) -> None:
        record_format = Struct("<B7x6d")
        records = [
            record_format.unpack_from(payload, offset) for offset in range(0, len(payload), 56)
        ]
        self.calls.append(("batch_primitives_current", records))

    def batch_primitives_mixed_packed(
        self,
        payload: bytes,
        styles: bytes,
        matrices: bytes,
    ) -> None:
        record_format = Struct("<B7x6dII")
        style_format = Struct("<BB6x4B4Bd")
        matrix_format = Struct("<6d")
        records = [
            record_format.unpack_from(payload, offset)
            for offset in range(0, len(payload), record_format.size)
        ]
        decoded_styles = [
            style_format.unpack_from(styles, offset)
            for offset in range(0, len(styles), style_format.size)
        ]
        decoded_matrices = [
            matrix_format.unpack_from(matrices, offset)
            for offset in range(0, len(matrices), matrix_format.size)
        ]
        self.calls.append(("batch_primitives_mixed", records, decoded_styles, decoded_matrices))

    def batch_fill_primitives(self, *args: object) -> None:
        self.calls.append(("batch_fill_primitives", *args))

    def batch_fill_primitives_packed(
        self,
        payload: bytes,
        matrix: tuple[float, float, float, float, float, float],
    ) -> None:
        record_format = Struct("<B7x6d4B")
        records = [
            record_format.unpack_from(payload, offset)
            for offset in range(0, len(payload), record_format.size)
        ]
        self.calls.append(("batch_fill_primitives", records, matrix))

    def replay_fill_primitive_batch(self) -> bool:
        self.calls.append(("replay_fill_primitive_batch",))
        return True

    def polygon_packed(
        self,
        points: bytes,
        contour_ends: bytes,
        style: dict[str, object],
        matrix: tuple[float, float, float, float, float, float],
        close: bool,
    ) -> None:
        groups = self._decode_path(points, contour_ends)
        name = "polygon" if len(groups) == 1 else "complex_polygon"
        args: tuple[object, ...] = (groups[0],) if len(groups) == 1 else (groups[0], groups[1:])
        self.calls.append((name, *args, style, matrix, close))

    def polygon_current_packed(self, points: bytes, contour_ends: bytes, close: bool) -> None:
        groups = self._decode_path(points, contour_ends)
        name = "polygon_current" if len(groups) == 1 else "complex_polygon_current"
        args: tuple[object, ...] = (groups[0],) if len(groups) == 1 else (groups[0], groups[1:])
        self.calls.append((name, *args, close))

    @staticmethod
    def _decode_path(points: bytes, contour_ends: bytes) -> list[list[tuple[float, float]]]:
        point_format = Struct("<2d")
        all_points = [
            point_format.unpack_from(points, offset)
            for offset in range(0, len(points), point_format.size)
        ]
        end_format = Struct("<I")
        groups: list[list[tuple[float, float]]] = []
        start = 0
        for offset in range(0, len(contour_ends), end_format.size):
            (end,) = end_format.unpack_from(contour_ends, offset)
            groups.append(all_points[start:end])
            start = end
        return groups

    def polygon(self, *args: object) -> None:
        self.calls.append(("polygon", *args))

    def complex_polygon(self, *args: object) -> None:
        self.calls.append(("complex_polygon", *args))

    def begin_clip_packed(
        self,
        points: bytes,
        contour_ends: bytes,
        matrix: tuple[float, float, float, float, float, float],
    ) -> None:
        groups = self._decode_path(points, contour_ends)
        self.calls.append(("begin_clip", groups[0], groups[1:], matrix))

    def begin_clip_current_packed(self, points: bytes, contour_ends: bytes) -> None:
        groups = self._decode_path(points, contour_ends)
        self.calls.append(("begin_clip_current", groups[0], groups[1:]))

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

    def batch_canvas_images_packed(
        self,
        payload: bytes,
        images: list[object],
        style: dict[str, object],
    ) -> None:
        record_format = Struct("<IB3x4d4i6d")
        records = []
        for offset in range(0, len(payload), record_format.size):
            record = record_format.unpack_from(payload, offset)
            image_index, flags, dx, dy, dw, dh, sx, sy, sw, sh, *matrix = record
            source = (sx, sy, sw, sh) if flags & 1 else None
            records.append((images[image_index], dx, dy, dw, dh, source, tuple(matrix)))
        self.calls.append(("batch_canvas_images", records, style))

    def batch_canvas_images(self, *args: object) -> None:
        self.calls.append(("batch_canvas_images", *args))

    def _draw_model_shaded_batch_packed(self, *args: object) -> None:
        transforms = cast(bytes, args[-1])
        record_format = Struct("<16d")
        decoded = [
            record_format.unpack_from(transforms, offset)
            for offset in range(0, len(transforms), record_format.size)
        ]
        self.calls.append(("draw_model_shaded_batch", *args[:-1], decoded))

    def text(self, *args: object) -> None:
        self.calls.append(("text", *args))

    @staticmethod
    def _decode_text_batch(records: bytes, utf8: bytes) -> list[tuple[str, float, float]]:
        record_format = Struct("<II2d")
        items = []
        for offset in range(0, len(records), record_format.size):
            text_offset, length, x, y = record_format.unpack_from(records, offset)
            items.append((utf8[text_offset : text_offset + length].decode(), x, y))
        return items

    def text_batch_packed(self, records: bytes, utf8: bytes, *args: object) -> bool:
        self.calls.append(("text_batch", self._decode_text_batch(records, utf8), *args))
        return False

    def text_batch_frame_packed(self, records: bytes, utf8: bytes, *args: object) -> bool:
        self.calls.append(("text_batch_frame", self._decode_text_batch(records, utf8), *args))
        return False

    def text_batch(self, *args: object) -> None:
        self.calls.append(("text_batch", *args))

    def text_batch_frame(self, *args: object) -> None:
        self.calls.append(("text_batch_frame", *args))

    def text_width(self, value: str, style: dict[str, object]) -> float:
        self.calls.append(("text_width", value, style))
        text_size = cast(float, style["text_size"])
        return len(value) * float(text_size) * 0.5

    def text_width_current(self, value: str) -> float:
        self.calls.append(("text_width_current", value))
        return len(value) * 6.0

    def text_ascent(self, style: dict[str, object]) -> float:
        self.calls.append(("text_ascent", style))
        text_size = cast(float, style["text_size"])
        return float(text_size) * 0.8

    def text_ascent_current(self) -> float:
        self.calls.append(("text_ascent_current",))
        return 9.6

    def text_descent(self, style: dict[str, object]) -> float:
        self.calls.append(("text_descent", style))
        text_size = cast(float, style["text_size"])
        return float(text_size) * 0.2

    def text_descent_current(self) -> float:
        self.calls.append(("text_descent_current",))
        return 2.4

    def apply_effects_packed(self, payload: bytes) -> None:
        record_format = Struct("<BB6xQQiid")
        for offset in range(0, len(payload), record_format.size):
            kind, mode, first, second, third, fourth, value = record_format.unpack_from(
                payload, offset
            )
            if kind == 1:
                self.calls.append(("adjust_pixel_prefix", first, second, third, fourth))
            elif kind == 2:
                names = {
                    1: "gray",
                    2: "invert",
                    3: "threshold",
                    4: "blur",
                    5: "posterize",
                    6: "erode",
                    7: "dilate",
                }
                self.calls.append(
                    ("filter_pixels", names[mode & 0x7F], value if mode & 0x80 else None)
                )

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

    def update_pixel_buffer(self, pixels: Buffer) -> None:
        self.update_pixels(bytes(pixels))

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

    def update_pixel_region_buffer(
        self,
        pixels: Buffer,
        width: int,
        height: int,
        x: int,
        y: int,
        alpha_composite: bool = True,
    ) -> None:
        self.update_pixel_region(bytes(pixels), width, height, x, y, alpha_composite)

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

    def save_gif(self, path: str, count: int, frame_duration_ms: int) -> None:
        self.calls.append(("save_gif", path, count, frame_duration_ms))
        Path(path).write_bytes(b"GIF89a")
