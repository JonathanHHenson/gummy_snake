from __future__ import annotations

from typing import Protocol


class TouchLike(Protocol):
    id: int
    x: float
    y: float
    previous_x: float | None
    previous_y: float | None
    pressure: float | None
    phase: str | None
    timestamp: float | None
    device: str | None


class FakeSketchContextState:
    def __init__(self) -> None:
        self.width = 100
        self.height = 100
        self.physical_width = 100
        self.physical_height = 100
        self.pixel_density = 1.0
        self.renderer = "p2d"
        self.created = False
        self.delta_time = 0.0
        self.frame_count = 0
        self.target_frame_rate = 60.0
        self.looping = True
        self.redraw_requested = False
        self.mouse_x = 0.0
        self.mouse_y = 0.0
        self.previous_mouse_x = 0.0
        self.previous_mouse_y = 0.0
        self.moved_x = 0.0
        self.moved_y = 0.0
        self.mouse_is_pressed = False
        self.mouse_inside_window = False
        self.mouse_button: str | None = None
        self.key: str | None = None
        self.key_code: int | None = None
        self.code: str | None = None
        self.text: str | None = None
        self.text_input_active = False
        self.key_is_pressed = False
        self.touch_supported = False
        self.pointer_locked = False
        self.pointer_lock_mode = "clamped"
        self._pressed_keys: set[int] = set()
        self._pressed_codes: set[str] = set()
        self._touches: list[dict[str, object]] = []
        self.shape_active = False
        self.contour_active = False
        self.shape_kind: str | None = None
        self._shape_vertices: list[tuple[float, float]] = []
        self._shape_contours: list[list[tuple[float, float]]] = []
        self._contour_vertices: list[tuple[float, float]] = []

    def begin_frame_timing(self) -> None:
        self.delta_time = 16.0

    def increment_frame_count(self) -> None:
        self.frame_count += 1

    def millis(self) -> float:
        return self.frame_count * 16.0

    def sync_canvas(
        self,
        width: int,
        height: int,
        physical_width: int,
        physical_height: int,
        pixel_density: float,
        renderer: str,
        created: bool,
    ) -> None:
        self.width = width
        self.height = height
        self.physical_width = physical_width
        self.physical_height = physical_height
        self.pixel_density = pixel_density
        self.renderer = renderer
        self.created = created

    def update_mouse(
        self, x: float, y: float, dx: float | None = None, dy: float | None = None
    ) -> None:
        self.previous_mouse_x = self.mouse_x
        self.previous_mouse_y = self.mouse_y
        self.mouse_x = x
        self.mouse_y = y
        self.moved_x = self.mouse_x - self.previous_mouse_x if dx is None else dx
        self.moved_y = self.mouse_y - self.previous_mouse_y if dy is None else dy

    def key_is_down(self, key_code: int) -> bool:
        return key_code in self._pressed_keys

    def code_is_down(self, code: str) -> bool:
        return code in self._pressed_codes

    def set_key_down(self, key_code: int, pressed: bool) -> None:
        if pressed:
            self._pressed_keys.add(key_code)
        else:
            self._pressed_keys.discard(key_code)

    def set_code_down(self, code: str, pressed: bool) -> None:
        if pressed:
            self._pressed_codes.add(code)
        else:
            self._pressed_codes.discard(code)

    def update_touches(self, touches: list[TouchLike]) -> None:
        previous = {touch["id"]: touch for touch in self._touches}
        self._touches = []
        for touch in touches:
            old = previous.get(touch.id)
            self._touches.append(
                {
                    "id": touch.id,
                    "x": touch.x,
                    "y": touch.y,
                    "previous_x": touch.previous_x
                    if touch.previous_x is not None
                    else (None if old is None else old["x"]),
                    "previous_y": touch.previous_y
                    if touch.previous_y is not None
                    else (None if old is None else old["y"]),
                    "pressure": touch.pressure,
                    "phase": touch.phase,
                    "timestamp": touch.timestamp,
                    "device": touch.device,
                }
            )

    def touch_payload(self) -> list[dict[str, object]]:
        return [dict(touch) for touch in self._touches]

    def begin_shape_capture(self, kind: str | None = None) -> None:
        if self.shape_active:
            raise RuntimeError("begin_shape() cannot be nested.")
        self.shape_active = True
        self.contour_active = False
        self.shape_kind = kind
        self._shape_vertices.clear()
        self._shape_contours.clear()
        self._contour_vertices.clear()

    def reset_shape_capture(self) -> None:
        self.shape_active = False
        self.contour_active = False
        self.shape_kind = None
        self._shape_vertices.clear()
        self._shape_contours.clear()
        self._contour_vertices.clear()

    def add_vertex(self, x: float, y: float) -> None:
        if self.contour_active:
            self._contour_vertices.append((x, y))
        else:
            self._shape_vertices.append((x, y))

    def add_quadratic_vertex(self, _cx: float, _cy: float, x: float, y: float) -> None:
        self._shape_vertices.append((x, y))

    def add_cubic_vertex(
        self,
        _x2: float,
        _y2: float,
        _x3: float,
        _y3: float,
        x4: float,
        y4: float,
    ) -> None:
        self._shape_vertices.append((x4, y4))

    def extend_vertices(self, vertices: list[tuple[float, float]]) -> None:
        if self.contour_active:
            self._contour_vertices.extend(vertices)
        else:
            self._shape_vertices.extend(vertices)

    def active_vertices(self) -> list[tuple[float, float]]:
        return list(self._contour_vertices if self.contour_active else self._shape_vertices)

    def shape_vertices(self) -> list[tuple[float, float]]:
        return list(self._shape_vertices)

    def shape_contours(self) -> list[list[tuple[float, float]]]:
        return [list(contour) for contour in self._shape_contours]

    def shape_vertex_count(self) -> int:
        return len(self._shape_vertices)

    def contour_vertex_count(self) -> int:
        return len(self._contour_vertices)

    def begin_contour_capture(self) -> None:
        self.contour_active = True
        self._contour_vertices.clear()

    def end_contour_capture(self) -> None:
        self._shape_contours.append(list(self._contour_vertices))
        self._contour_vertices.clear()
        self.contour_active = False

    def reset_contour_capture(self) -> None:
        self._contour_vertices.clear()
        self.contour_active = False
