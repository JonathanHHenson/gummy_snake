from collections.abc import Sequence
from typing import Any

ModelTransformPayload = tuple[float, ...]

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
def parse_obj_model_handle(text: str, source: str, normalize: bool) -> CanvasModel3D: ...
def create_mesh3d_handle(
    vertices: Any,
    face_indices: Any,
    face_offsets: Any,
    normals: Any,
    texcoords: Any,
    material: dict[str, Any] | None = None,
) -> CanvasMesh3D: ...
def create_plane_model_handle(width: float, height: float | None = None) -> CanvasModel3D: ...
def create_box_model_handle(
    width: float, height: float | None = None, depth: float | None = None
) -> CanvasModel3D: ...
def create_sphere_model_handle(
    radius: float, detail_x: int = 24, detail_y: int = 16
) -> CanvasModel3D: ...
def create_ellipsoid_model_handle(
    radius_x: float, radius_y: float, radius_z: float, detail_x: int = 24, detail_y: int = 16
) -> CanvasModel3D: ...
def create_cylinder_model_handle(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    bottom_cap: bool = True,
    top_cap: bool = True,
) -> CanvasModel3D: ...
def create_cone_model_handle(
    radius: float, height: float, detail_x: int = 24, detail_y: int = 1, cap: bool = True
) -> CanvasModel3D: ...
def create_torus_model_handle(
    radius: float, tube_radius: float, detail_x: int = 32, detail_y: int = 16
) -> CanvasModel3D: ...
def project_shade_model_handle(
    model: CanvasModel3D,
    camera: dict[str, Any],
    projection: dict[str, Any],
    viewport_width: float,
    viewport_height: float,
    material: dict[str, Any],
    lights: list[dict[str, Any]],
    normal_material: bool,
    cull_backfaces: bool,
    transform: ModelTransformPayload | None = None,
) -> list[dict[str, Any]]: ...
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

class SketchContextState:
    width: int
    height: int
    physical_width: int
    physical_height: int
    pixel_density: float
    renderer: str
    created: bool
    delta_time: float
    frame_count: int
    target_frame_rate: float
    looping: bool
    redraw_requested: bool
    mouse_x: float
    mouse_y: float
    previous_mouse_x: float
    previous_mouse_y: float
    moved_x: float
    moved_y: float
    mouse_is_pressed: bool
    mouse_inside_window: bool
    mouse_button: str | None
    key: str | None
    key_code: int | None
    code: str | None
    text: str | None
    text_input_active: bool
    key_is_pressed: bool
    touch_supported: bool
    pointer_locked: bool
    pointer_lock_mode: str
    shape_active: bool
    contour_active: bool
    shape_kind: str | None
    def __init__(self) -> None: ...
    def begin_frame_timing(self) -> None: ...
    def increment_frame_count(self) -> None: ...
    def millis(self) -> float: ...
    def sync_canvas(
        self,
        width: int,
        height: int,
        physical_width: int,
        physical_height: int,
        pixel_density: float,
        renderer: str,
        created: bool,
    ) -> None: ...
    def update_mouse(
        self, x: float, y: float, dx: float | None = None, dy: float | None = None
    ) -> None: ...
    def key_is_down(self, key_code: int) -> bool: ...
    def code_is_down(self, code: str) -> bool: ...
    def set_key_down(self, key_code: int, pressed: bool) -> None: ...
    def set_code_down(self, code: str, pressed: bool) -> None: ...
    def update_touches(self, touches: Sequence[Any]) -> None: ...
    def touch_payload(self) -> list[dict[str, Any]]: ...
    def begin_shape_capture(self, kind: str | None = None) -> None: ...
    def reset_shape_capture(self) -> None: ...
    def add_vertex(self, x: float, y: float) -> None: ...
    def extend_vertices(self, vertices: Sequence[tuple[float, float]]) -> None: ...
    def active_vertices(self) -> list[tuple[float, float]]: ...
    def shape_vertices(self) -> list[tuple[float, float]]: ...
    def shape_contours(self) -> list[list[tuple[float, float]]]: ...
    def shape_vertex_count(self) -> int: ...
    def contour_vertex_count(self) -> int: ...
    def begin_contour_capture(self) -> None: ...
    def end_contour_capture(self) -> None: ...
    def reset_contour_capture(self) -> None: ...

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
    @property
    def key(self) -> int: ...
    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int]: ...
    def set_pixel(self, x: int, y: int, r: int, g: int, b: int, a: int) -> None: ...
    def replace_rgba_bytes(self, pixels: bytes) -> None: ...
    def copy(self) -> CanvasImage: ...
    def crop(self, sx: int, sy: int, sw: int, sh: int) -> CanvasImage: ...
    def resize(self, width: int, height: int) -> None: ...
    def mask(self, mask: CanvasImage) -> None: ...
    def filter(self, mode: str, value: float | None = None) -> None: ...
    def alpha_composite(self, source: CanvasImage, dx: int, dy: int) -> None: ...
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

class CanvasMesh3D:
    def vertex_count(self) -> int: ...
    def face_count(self) -> int: ...
    def to_mesh_payload(self) -> dict[str, Any]: ...

class CanvasModel3D:
    def vertex_count(self) -> int: ...
    def face_count(self) -> int: ...
    def to_mesh_handle(self) -> CanvasMesh3D: ...
    def to_mesh_payload(self) -> dict[str, Any]: ...
    def save_obj(self, path: str) -> None: ...
    def save_stl(self, path: str, name: str = "gummy_snake_model") -> None: ...

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
    def resize_canvas(
        self, width: int, height: int, pixel_density: float, renderer: str
    ) -> None: ...
    def dimensions(self) -> tuple[int, int, int, int, float]: ...
    def display_density(self) -> float: ...
    def gpu_available(self) -> bool: ...
    def gpu_status(self) -> str: ...
    def performance_counters(self) -> dict[str, int]: ...
    def reset_performance_counters(self) -> None: ...
    def pump_native_events(self) -> bool: ...
    def request_pointer_lock(self) -> bool: ...
    def exit_pointer_lock(self) -> bool: ...
    def pointer_locked(self) -> bool: ...
    def set_pointer_lock_mode(self, mode: str) -> None: ...
    def pointer_lock_mode(self) -> str: ...
    def start_text_input(self) -> bool: ...
    def stop_text_input(self) -> bool: ...
    def text_input_active(self) -> bool: ...
    def begin_frame(self) -> None: ...
    def end_frame(self) -> None: ...
    def present(self) -> None: ...
    def close(self) -> None: ...
    def background(self, rgba: tuple[int, int, int, int]) -> None: ...
    def clear(self) -> None: ...
    def set_current_style(self, style: dict[str, Any]) -> None: ...
    def current_style(self) -> dict[str, Any]: ...
    def set_current_matrix(
        self, matrix: tuple[float, float, float, float, float, float]
    ) -> None: ...
    def current_matrix(self) -> tuple[float, float, float, float, float, float]: ...
    def push_canvas_state(self) -> None: ...
    def pop_canvas_state(self) -> None: ...
    def translate(self, x: float, y: float) -> None: ...
    def rotate(self, angle: float) -> None: ...
    def scale(self, x: float, y: float | None = None) -> None: ...
    def shear_x(self, angle: float) -> None: ...
    def shear_y(self, angle: float) -> None: ...
    def apply_matrix(self, matrix: tuple[float, float, float, float, float, float]) -> None: ...
    def reset_matrix(self) -> None: ...
    def point(
        self,
        x: float,
        y: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def point_current(self, x: float, y: float) -> None: ...
    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def line_current(self, x1: float, y1: float, x2: float, y2: float) -> None: ...
    def batch_lines(
        self,
        lines: list[tuple[float, float, float, float]],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def batch_lines_current(self, lines: list[tuple[float, float, float, float]]) -> None: ...
    def batch_primitives(
        self,
        records: list[tuple[int, float, float, float, float, float, float]],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def batch_primitives_current(
        self, records: list[tuple[int, float, float, float, float, float, float]]
    ) -> None: ...
    def batch_primitives_mixed(
        self,
        records: list[
            tuple[
                int,
                float,
                float,
                float,
                float,
                float,
                float,
                dict[str, Any],
                tuple[float, float, float, float, float, float],
            ]
        ],
    ) -> None: ...
    def batch_fill_primitives(
        self,
        records: list[tuple[int, float, float, float, float, float, float, int, int, int, int]],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def replay_fill_primitive_batch(self) -> bool: ...
    def polygon(
        self,
        points: list[tuple[float, float]],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
        close: bool = True,
    ) -> None: ...
    def polygon_current(self, points: list[tuple[float, float]], close: bool = True) -> None: ...
    def complex_polygon(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
        close: bool = True,
    ) -> None: ...
    def complex_polygon_current(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        close: bool = True,
    ) -> None: ...
    def begin_clip(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def begin_clip_current(
        self, outer: list[tuple[float, float]], contours: list[list[tuple[float, float]]]
    ) -> None: ...
    def end_clip(self) -> None: ...
    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def rect_current(self, x: float, y: float, width: float, height: float) -> None: ...
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
    def triangle_current(
        self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float
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
    def quad_current(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
    ) -> None: ...
    def shaded_faces(self, faces: list[dict[str, Any]]) -> None: ...
    def draw_model_textured(
        self,
        model: CanvasModel3D,
        image: CanvasImage,
        camera: dict[str, Any],
        projection: dict[str, Any],
        viewport_width: float,
        viewport_height: float,
        material: dict[str, Any],
        lights: list[dict[str, Any]],
        normal_material: bool,
        cull_backfaces: bool,
        transform: ModelTransformPayload | None = None,
    ) -> bool: ...
    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def ellipse_current(self, x: float, y: float, width: float, height: float) -> None: ...
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
    def arc_current(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: str,
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
    def draw_image_current(
        self,
        image_pixels: bytes,
        image_width: int,
        image_height: int,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
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
    def draw_cached_image_current(
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
    def draw_canvas_image_current(
        self,
        image: CanvasImage,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        source: tuple[int, int, int, int] | None = None,
    ) -> None: ...
    def batch_canvas_images(
        self,
        records: list[
            tuple[CanvasImage, float, float, float, float, tuple[int, int, int, int] | None]
        ],
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def batch_canvas_images_transformed(
        self,
        records: list[
            tuple[
                CanvasImage,
                float,
                float,
                float,
                float,
                tuple[int, int, int, int] | None,
                tuple[float, float, float, float, float, float],
            ]
        ],
        style: dict[str, Any],
    ) -> None: ...
    def text(
        self,
        value: str,
        x: float,
        y: float,
        style: dict[str, Any],
        matrix: tuple[float, float, float, float, float, float],
    ) -> None: ...
    def text_current(self, value: str, x: float, y: float) -> None: ...
    def text_width(self, value: str, style: dict[str, Any]) -> float: ...
    def text_width_current(self, value: str) -> float: ...
    def text_ascent(self, style: dict[str, Any]) -> float: ...
    def text_ascent_current(self) -> float: ...
    def text_descent(self, style: dict[str, Any]) -> float: ...
    def text_descent_current(self) -> float: ...
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
    def set_pixel_rgba(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None: ...
    def update_pixel_region(
        self,
        pixels: bytes,
        width: int,
        height: int,
        x: int,
        y: int,
        alpha_composite: bool = True,
    ) -> None: ...
    def adjust_pixel_prefix(
        self, byte_limit: int, stride: int, red_delta: int, green_delta: int
    ) -> None: ...
    def filter_pixels(self, mode: str, value: float | None = None) -> None: ...
    def save(self, path: str) -> None: ...
