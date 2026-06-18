from collections.abc import Sequence
from typing import Any

def health_check() -> str: ...
def gpu_available() -> bool: ...

class P5Image:
    @staticmethod
    def from_file(path: str) -> P5Image: ...
    @staticmethod
    def from_rgba_bytes(width: int, height: int, pixels: bytes) -> P5Image: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def version(self) -> int: ...
    def save(self, path: str) -> None: ...
    def to_rgba_bytes(self) -> bytes: ...

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
    def polygon(
        self,
        points: list[tuple[float, float]],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
        close: bool = True,
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
        image: P5Image,
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
    def update_pixels(self, pixels: bytes) -> None: ...
    def save(self, path: str) -> None: ...
