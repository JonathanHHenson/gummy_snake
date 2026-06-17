from collections.abc import Sequence
from typing import Any

def health_check() -> str: ...

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
    def load_pixels(self) -> Sequence[int]: ...
    def update_pixels(self, pixels: bytes) -> None: ...
    def save(self, path: str) -> None: ...
