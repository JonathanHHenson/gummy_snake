"""Backend protocols and capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from p5_py.drawing.renderer import Renderer

if TYPE_CHECKING:
    from p5_py.sketch import Sketch


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    interactive: bool = False
    headless: bool = False
    text: bool = False
    images: bool = False
    pixels: bool = True
    paths: bool = True
    transforms: bool = True
    blend_modes: frozenset[str] = field(default_factory=frozenset)
    three_d: bool = False
    shaders: bool = False
    sound: bool = False


class Backend(Protocol):
    name: str
    capabilities: BackendCapabilities
    renderer: Renderer

    def create_canvas(self, width: int, height: int, pixel_density: float = 1.0) -> None: ...

    def resize_canvas(self, width: int, height: int, pixel_density: float = 1.0) -> None: ...

    def run(self, sketch: Sketch, *, max_frames: int | None = None) -> None: ...

    def stop(self) -> None: ...

    def present(self) -> None: ...
