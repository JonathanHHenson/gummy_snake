from collections.abc import Sequence
from typing import Any

def health_check() -> str: ...
def canvas_abi_version() -> int: ...
def gpu_available() -> bool: ...
def native_window_available() -> bool: ...
def image_resize_rgba(
    width: int, height: int, pixels: bytes, target_width: int, target_height: int
) -> bytes: ...
def image_crop_rgba(
    width: int, height: int, pixels: bytes, sx: int, sy: int, sw: int, sh: int
) -> bytes: ...
def image_alpha_composite_rgba(
    width: int,
    height: int,
    pixels: bytes,
    source_width: int,
    source_height: int,
    source_pixels: bytes,
    dx: int,
    dy: int,
) -> bytes: ...
def image_mask_rgba(
    width: int,
    height: int,
    pixels: bytes,
    mask_width: int,
    mask_height: int,
    mask_pixels: bytes,
) -> bytes: ...
def image_filter_rgba(
    width: int, height: int, pixels: bytes, mode: str, value: float | None = None
) -> bytes: ...
def media_frame_to_rgba(width: int, height: int, channels: int, pixels: bytes) -> bytes: ...
def parse_obj_model(text: str, source: str, normalize: bool) -> dict[str, Any]: ...
def project_shade_faces(
    meshes: list[dict[str, Any]],
    camera: dict[str, Any],
    projection: dict[str, Any],
    viewport_width: float,
    viewport_height: float,
    material: dict[str, Any],
    lights: list[dict[str, Any]],
    normal_material: bool,
    cull_backfaces: bool,
) -> list[dict[str, Any]]: ...
def rasterize_faces_rgba(width: int, height: int, faces: list[dict[str, Any]]) -> bytes: ...

CANVAS_ABI_VERSION: int

class CanvasImage:
    @staticmethod
    def from_file(path: str) -> CanvasImage: ...
    @staticmethod
    def from_rgba_bytes(width: int, height: int, pixels: bytes) -> CanvasImage: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def version(self) -> int: ...
    def save(self, path: str) -> None: ...
    def to_rgba_bytes(self) -> bytes: ...

class CanvasSound:
    @staticmethod
    def from_file(path: str) -> CanvasSound: ...
    @property
    def path(self) -> str: ...
    @property
    def duration(self) -> float | None: ...
    @property
    def byte_len(self) -> int: ...
    def to_bytes(self) -> bytes: ...

class Canvas:
    def __init__(
        self,
        width: int,
        height: int,
        pixel_density: float = 1.0,
        mode: str = "headless",
        renderer: str = "p2d",
    ) -> None: ...
    def resize(self, width: int, height: int, pixel_density: float, renderer: str) -> None: ...
    def dimensions(self) -> tuple[int, int, int, int, float]: ...
    def display_density(self) -> float: ...
    def gpu_available(self) -> bool: ...
    def gpu_status(self) -> str: ...
    def performance_counters(self) -> dict[str, int]: ...
    def reset_performance_counters(self) -> None: ...
    def begin_frame(self) -> None: ...
    def end_frame(self) -> None: ...
    def present(self) -> None: ...
    def close(self) -> None: ...
    def background(self, rgba: tuple[int, int, int, int]) -> None: ...
    def clear(self) -> None: ...
    def point(
        self,
        x: float,
        y: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def batch_lines(
        self,
        lines: list[tuple[float, float, float, float]],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def polygon(
        self,
        points: list[tuple[float, float]],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
        close: bool = True,
    ) -> None: ...
    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def triangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def quad(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: str,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def draw_image(
        self,
        image_pixels: bytes,
        image_width: int,
        image_height: int,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
        source: tuple[int, int, int, int] | None = None,
    ) -> None: ...
    def draw_cached_image(
        self,
        image_key: int,
        image_version: int,
        image_pixels: bytes | None,
        image_width: int,
        image_height: int,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
        source: tuple[int, int, int, int] | None = None,
    ) -> None: ...
    def draw_canvas_image(
        self,
        image: CanvasImage,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
        source: tuple[int, int, int, int] | None = None,
    ) -> None: ...
    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def text_width(self, value: str, style: dict[str, Any]) -> float: ...
    def text_ascent(self, style: dict[str, Any]) -> float: ...
    def text_descent(self, style: dict[str, Any]) -> float: ...
    def blend_region(
        self,
        source_pixels: bytes | None,
        source_width: int | None,
        source_height: int | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: str,
    ) -> None: ...
    def load_pixels(self) -> Sequence[int]: ...
    def load_pixel_bytes(self) -> bytes: ...
    def load_pixel_region(self, x: int, y: int, width: int, height: int) -> bytes: ...
    def update_pixels(self, pixels: bytes) -> None: ...
    def update_pixel_region(
        self,
        pixels: bytes,
        width: int,
        height: int,
        x: int,
        y: int,
        alpha_composite: bool = True,
    ) -> None: ...
    def filter_pixels(self, mode: str, value: float | None = None) -> None: ...
    def save(self, path: str) -> None: ...
