import math

import gummysnake as gs
from gummysnake.backends.base import BackendCapabilities
from gummysnake.backends.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from gummysnake.sketch import Sketch


class _WebGLSketch(Sketch):
    def __init__(self):
        super().__init__()


def make_context() -> SketchContext:
    sketch = _WebGLSketch()
    backend = CanvasBackend()
    backend.capabilities = BackendCapabilities(three_d=True, shaders=False)
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    context.create_canvas(96, 96, renderer=gs.WEBGL)
    return context

def _camera_radius(context: SketchContext) -> float:
    offset_x = context._camera3d.eye.x - context._camera3d.target.x
    offset_y = context._camera3d.eye.y - context._camera3d.target.y
    offset_z = context._camera3d.eye.z - context._camera3d.target.z
    return math.sqrt(offset_x * offset_x + offset_y * offset_y + offset_z * offset_z)

class Fake3DRenderer:
    three_d = True
    width = 96
    height = 96
    physical_width = 96
    physical_height = 96
    pixel_density = 1.0

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def resize(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        self.width = width
        self.height = height
        self.physical_width = width
        self.physical_height = height
        self.pixel_density = pixel_density

    def begin_frame(self) -> None: ...
    def end_frame(self) -> None: ...
    def background(self, color) -> None: ...
    def clear(self) -> None: ...
    def point(self, x, y, style, transform) -> None: ...
    def line(self, x1, y1, x2, y2, style, transform) -> None: ...
    def polygon(self, points, style, transform, *, close=True) -> None: ...
    def ellipse(self, x, y, width, height, style, transform) -> None: ...
    def arc(self, x, y, width, height, start, stop, mode, style, transform) -> None: ...
    def draw_image(self, image, dx, dy, dw, dh, style, transform, *, source=None) -> None: ...
    def text(self, value, x, y, style, transform) -> None: ...
    def text_width(self, value, style) -> float:
        return 0.0

    def text_ascent(self, style) -> float:
        return 0.0

    def text_descent(self, style) -> float:
        return 0.0

    def load_pixels(self) -> list[int]:
        return [0] * (self.physical_width * self.physical_height * 4)

    def load_pixel_bytes(self) -> bytes:
        return bytes(self.physical_width * self.physical_height * 4)

    def load_pixel_region(self, x, y, width, height) -> bytes:
        return bytes(width * height * 4)

    def update_pixels(self, pixels) -> None: ...
    def update_pixel_region(
        self,
        pixels,
        width,
        height,
        x,
        y,
        *,
        alpha_composite=True,
    ) -> None: ...
    def filter_pixels(self, mode, value=None) -> None: ...
    def blend_region(self, source_image, source, destination, mode) -> None: ...
    def save(self, path) -> None: ...
    def set_camera(self, camera) -> None:
        self.calls.append(("camera", camera))

    def set_projection(self, projection) -> None:
        self.calls.append(("projection", projection))

    def set_lights(self, lights) -> None:
        self.calls.append(("lights", tuple(lights)))

    def set_material(self, material) -> None:
        self.calls.append(("material", material))

    def set_texture(self, texture) -> None:
        self.calls.append(("texture", texture))

    def use_shader(self, shader) -> None:
        self.calls.append(("shader", shader))

    def set_shader_uniform(self, name, value) -> None:
        self.calls.append((f"uniform:{name}", value))

    def draw_model(self, model, transform=None) -> None:
        self.calls.append(("draw_model", model))

    def draw_mesh(self, mesh, transform=None) -> None:
        self.calls.append(("draw_mesh", mesh))

    def plane(self, width, height) -> None: ...
    def box(self, width, height, depth) -> None: ...
    def sphere(self, radius, detail_x=24, detail_y=16) -> None: ...


class FakeCanvas3DBackend:
    name = "canvas"
    capabilities = BackendCapabilities(three_d=True, shaders=True)

    def __init__(self):
        self.renderer = Fake3DRenderer()

    def create_canvas(
        self, width: int, height: int, pixel_density: float | None = None, *, renderer: str = gs.P2D
    ) -> None:
        self.renderer.resize(width, height, 1.0 if pixel_density is None else pixel_density)

    def resize_canvas(
        self, width: int, height: int, pixel_density: float | None = None, *, renderer: str = gs.P2D
    ) -> None:
        self.create_canvas(width, height, pixel_density, renderer=renderer)

    def display_density(self) -> float:
        return 1.0

    def run(self, sketch, *, max_frames: int | None = None) -> None: ...
    def stop(self) -> None: ...
    def present(self) -> None: ...


class FakeUpgradeableCanvasBackend(FakeCanvas3DBackend):
    def __init__(self):
        super().__init__()
        self.capabilities = BackendCapabilities(three_d=True, shaders=False)
        self.enable_calls = 0

    def enable_native_webgl(self) -> bool:
        self.enable_calls += 1
        self.capabilities = BackendCapabilities(three_d=True, shaders=True)
        self.renderer = Fake3DRenderer()
        return True

