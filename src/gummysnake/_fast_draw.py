"""Frame-local fast drawing facade."""

from __future__ import annotations

import math
from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol, overload

from gummysnake import constants as c
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.geometry import resolve_ellipse, resolve_rect
from gummysnake.drawing.renderer3d import Mesh3D, Model3D
from gummysnake.drawing.software3d.payloads import (
    _IDENTITY4,
    Matrix4Payload,
    _coerce_matrix4_payload,
)

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class SupportsText(Protocol):
    def __str__(self) -> str: ...


_PRIMITIVE_RECT = 1
_PRIMITIVE_TRIANGLE = 2
_PRIMITIVE_ELLIPSE = 3


def _queue_fill_primitive(context: SketchContext, kind: int, coords: tuple[float, ...]) -> bool:
    queue = getattr(context.renderer, "queue_fill_primitive_fast_path", None)
    if not callable(queue):
        return False
    return bool(queue(kind, coords, context.state.style, context.state.transform.matrix))


def _mat4_multiply(left: Matrix4Payload, right: Matrix4Payload) -> Matrix4Payload:
    values = [0.0] * 16
    for column in range(4):
        for row in range(4):
            values[column * 4 + row] = sum(
                left[k * 4 + row] * right[column * 4 + k] for k in range(4)
            )
    return tuple(values)


def _mat4_is_translation(matrix: Matrix4Payload) -> bool:
    return (
        matrix[:12] == (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        and matrix[15] == 1.0
    )


def _mat4_translation_then_rotation(
    translation: Matrix4Payload, rotation: Matrix4Payload
) -> Matrix4Payload:
    return (
        rotation[0],
        rotation[1],
        rotation[2],
        0.0,
        rotation[4],
        rotation[5],
        rotation[6],
        0.0,
        rotation[8],
        rotation[9],
        rotation[10],
        0.0,
        translation[12],
        translation[13],
        translation[14],
        1.0,
    )


def _mat4_translation(x: float, y: float, z: float) -> Matrix4Payload:
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        float(x),
        float(y),
        float(z),
        1.0,
    )


def _mat4_scale(x: float, y: float, z: float) -> Matrix4Payload:
    return (
        float(x),
        0.0,
        0.0,
        0.0,
        0.0,
        float(y),
        0.0,
        0.0,
        0.0,
        0.0,
        float(z),
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _mat4_axis_angle(angle: float, x: float, y: float, z: float) -> Matrix4Payload:
    axis_length = math.sqrt(x * x + y * y + z * z)
    if axis_length <= 1.0e-12:
        raise ValueError("rotate() axis must be non-zero.")
    x /= axis_length
    y /= axis_length
    z /= axis_length
    cosine = math.cos(angle)
    sine = math.sin(angle)
    one_minus_cosine = 1.0 - cosine
    return (
        cosine + x * x * one_minus_cosine,
        y * x * one_minus_cosine + z * sine,
        z * x * one_minus_cosine - y * sine,
        0.0,
        x * y * one_minus_cosine - z * sine,
        cosine + y * y * one_minus_cosine,
        z * y * one_minus_cosine + x * sine,
        0.0,
        x * z * one_minus_cosine + y * sine,
        y * z * one_minus_cosine - x * sine,
        cosine + z * z * one_minus_cosine,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _mat4_quaternion(w: float, x: float, y: float, z: float) -> Matrix4Payload:
    length = math.sqrt(w * w + x * x + y * y + z * z)
    if length <= 1.0e-12:
        raise ValueError("rotate_quaternion() requires a non-zero quaternion.")
    w /= length
    x /= length
    y /= length
    z /= length
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return (
        1.0 - 2.0 * (yy + zz),
        2.0 * (xy + wz),
        2.0 * (xz - wy),
        0.0,
        2.0 * (xy - wz),
        1.0 - 2.0 * (xx + zz),
        2.0 * (yz + wx),
        0.0,
        2.0 * (xz + wy),
        2.0 * (yz - wx),
        1.0 - 2.0 * (xx + yy),
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _sequence3(value: Sequence[float], *, name: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{name} must contain exactly three values.")
    return (float(value[0]), float(value[1]), float(value[2]))


def _sequence4(value: Sequence[float], *, name: str) -> tuple[float, float, float, float]:
    if len(value) != 4:
        raise ValueError(f"{name} must contain exactly four values.")
    return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))


class _FastPushedScope:
    __slots__ = ("_scope",)

    def __init__(self, scope: FastDrawScope) -> None:
        self._scope = scope

    def __enter__(self) -> None:
        self._scope.push()
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._scope.pop()
        return None


class FastDrawScope:
    """Frame-local facade for dense drawing loops."""

    __slots__ = (
        "_context",
        "_draw_model_fast",
        "_model_batch_cache",
        "_model_batch_signature_cache",
        "_pushed_scope",
        "_transform3d",
        "_transform3d_active",
        "_transform3d_stack",
    )

    def __init__(self, context: SketchContext) -> None:
        self._context = context
        draw_model_fast = getattr(context, "_draw_model_fast", None)
        self._draw_model_fast = draw_model_fast if callable(draw_model_fast) else None
        self._model_batch_cache: tuple[tuple[object, ...], object] | None = None
        self._model_batch_signature_cache: tuple[object, tuple[object, ...]] | None = None
        self._pushed_scope = _FastPushedScope(self)
        self._transform3d: Matrix4Payload = _IDENTITY4
        self._transform3d_active = False
        self._transform3d_stack: list[tuple[Matrix4Payload, bool]] = []

    @property
    def width(self) -> int:
        return self._context.width

    @property
    def height(self) -> int:
        return self._context.height

    def _compose_transform3d(self, transform: Matrix4Payload) -> None:
        self._transform3d = (
            _mat4_multiply(self._transform3d, transform) if self._transform3d_active else transform
        )
        self._transform3d_active = True

    def _model_transform3d_payload(self) -> Matrix4Payload | None:
        return self._transform3d if self._transform3d_active else None

    def _model_batch_signature(self, shape: object) -> tuple[object, ...]:
        cached = self._model_batch_signature_cache
        if cached is not None and cached[0] is shape:
            return cached[1]
        context = self._context
        material = getattr(context, "_material3d", None)
        signature = (
            shape,
            id(getattr(context, "_camera3d", None)),
            id(getattr(context, "_projection3d", None)),
            id(material)
            if material is not None
            else getattr(context.state.style, "fill_color", None),
            id(getattr(context, "_lights3d", None)),
            len(getattr(context, "_lights3d", ())),
            getattr(context, "_normal_material3d", False),
            getattr(context, "_shader3d", None),
            getattr(context.state.style, "stroke_color", None),
        )
        self._model_batch_signature_cache = (shape, signature)
        return signature

    def push(self) -> None:
        """Push the fast 3D model transform stack."""
        self._transform3d_stack.append((self._transform3d, self._transform3d_active))

    def pop(self) -> None:
        """Pop a transform frame pushed by ``fast().push()``."""
        self._transform3d, self._transform3d_active = self._transform3d_stack.pop()

    def pushed(self) -> _FastPushedScope:
        """Temporarily push style and fast transforms inside a ``with`` block."""
        return self._pushed_scope

    def reset_matrix(self) -> None:
        """Reset the active fast 3D model transform."""
        self._transform3d = _IDENTITY4
        self._transform3d_active = False

    def translate(self, x: float, y: float, z: float = 0.0) -> None:
        """Translate subsequent fast 3D model draws."""
        fx = float(x)
        fy = float(y)
        fz = float(z)
        self._compose_transform3d(_mat4_translation(fx, fy, fz))

    def scale(self, x: float, y: float | None = None, z: float | None = None) -> None:
        """Scale subsequent fast 3D model draws."""
        fx = float(x)
        if y is None and z is None:
            fy = fz = fx
        else:
            fy = fx if y is None else float(y)
            fz = 1.0 if z is None else float(z)
        self._compose_transform3d(_mat4_scale(fx, fy, fz))

    def apply_matrix_3d(self, matrix: Sequence[float] | Sequence[Sequence[float]]) -> None:
        """Compose a 4x4 model matrix for subsequent fast 3D model draws.

        A flat 16-value sequence is interpreted as column-major. A nested 4x4 sequence is
        interpreted as conventional row-major rows and converted internally.
        """
        self._compose_transform3d(_coerce_matrix4_payload(matrix))

    def rotate(
        self,
        angle: float | None = None,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 1.0,
        *,
        axis: Sequence[float] | None = None,
        quaternion: Sequence[float] | None = None,
    ) -> None:
        """Rotate drawing state using z-rotation, axis-angle, or a quaternion.

        ``quaternion`` uses ``(w, x, y, z)`` order. Without an axis/quaternion this behaves
        like the regular 2D ``rotate()`` while also updating the fast 3D model transform.
        """
        if quaternion is not None:
            if angle is not None:
                raise ValueError("rotate() accepts either angle or quaternion, not both.")
            self.rotate_quaternion(*_sequence4(quaternion, name="quaternion"))
            return
        if angle is None:
            raise TypeError("rotate() missing required angle or quaternion.")
        if axis is not None:
            x, y, z = _sequence3(axis, name="axis")
        radians = self._context._angle(float(angle))
        self._compose_transform3d(_mat4_axis_angle(radians, float(x), float(y), float(z)))

    def rotate_x(self, angle: float) -> None:
        """Rotate subsequent fast 3D model draws around the x axis."""
        self._compose_transform3d(
            _mat4_axis_angle(self._context._angle(float(angle)), 1.0, 0.0, 0.0)
        )

    def rotate_y(self, angle: float) -> None:
        """Rotate subsequent fast 3D model draws around the y axis."""
        self._compose_transform3d(
            _mat4_axis_angle(self._context._angle(float(angle)), 0.0, 1.0, 0.0)
        )

    def rotate_z(self, angle: float) -> None:
        """Rotate subsequent fast 3D model draws around the z axis."""
        self.rotate(angle)

    def rotate_quaternion(self, w: float, x: float, y: float, z: float) -> None:
        """Rotate subsequent fast 3D model draws by a ``(w, x, y, z)`` quaternion."""
        rotation = _mat4_quaternion(float(w), float(x), float(y), float(z))
        if self._transform3d_active and _mat4_is_translation(self._transform3d):
            self._transform3d = _mat4_translation_then_rotation(self._transform3d, rotation)
            return
        self._compose_transform3d(rotation)

    def point(self, x: float, y: float) -> None:
        context = self._context
        context.renderer.point(
            float(x),
            float(y),
            context.state.style,
            context.state.transform.matrix,
        )

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        context = self._context
        context.renderer.line(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            context.state.style,
            context.state.transform.matrix,
        )

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        context = self._context
        fx = float(x)
        fy = float(y)
        fw = float(width)
        if height is not None and context.state.style.rect_mode == c.CORNER:
            fh = float(height)
            if _queue_fill_primitive(context, _PRIMITIVE_RECT, (fx, fy, fw, fh, 0.0, 0.0)):
                return
            context.renderer.rect(
                fx,
                fy,
                fw,
                fh,
                context.state.style,
                context.state.transform.matrix,
            )
            return
        h = width if height is None else height
        rx, ry, rw, rh = resolve_rect(
            context.state.style.rect_mode,
            fx,
            fy,
            fw,
            float(h),
        )
        context.renderer.rect(
            rx,
            ry,
            rw,
            rh,
            context.state.style,
            context.state.transform.matrix,
        )

    def square(self, x: float, y: float, size: float) -> None:
        self.rect(x, y, size, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        context = self._context
        h = width if height is None else height
        ex, ey, ew, eh = resolve_ellipse(
            context.state.style.ellipse_mode,
            float(x),
            float(y),
            float(width),
            float(h),
        )
        context.renderer.ellipse(
            ex,
            ey,
            ew,
            eh,
            context.state.style,
            context.state.transform.matrix,
        )

    def circle(self, x: float, y: float, diameter: float) -> None:
        context = self._context
        if context.state.style.ellipse_mode == c.CENTER:
            fx = float(x)
            fy = float(y)
            d = float(diameter)
            left = fx - d / 2.0
            top = fy - d / 2.0
            if _queue_fill_primitive(context, _PRIMITIVE_ELLIPSE, (left, top, d, d, 0.0, 0.0)):
                return
            context.renderer.ellipse(
                left,
                top,
                d,
                d,
                context.state.style,
                context.state.transform.matrix,
            )
            return
        self.ellipse(x, y, diameter, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        context = self._context
        values = (float(x1), float(y1), float(x2), float(y2), float(x3), float(y3))
        if _queue_fill_primitive(context, _PRIMITIVE_TRIANGLE, values):
            return
        context.renderer.triangle(
            values[0],
            values[1],
            values[2],
            values[3],
            values[4],
            values[5],
            context.state.style,
            context.state.transform.matrix,
        )

    @overload
    def image(self, image: Image | CanvasImage, x: float, y: float, /) -> None: ...

    @overload
    def image(
        self, image: Image | CanvasImage, x: float, y: float, width: float, height: float, /
    ) -> None: ...

    @overload
    def image(
        self,
        image: Image | CanvasImage,
        x: float,
        y: float,
        width: float,
        height: float,
        sx: float,
        sy: float,
        sw: float,
        sh: float,
        /,
    ) -> None: ...

    def image(self, image: Image | CanvasImage, x: float, y: float, *args: float) -> None:
        context = self._context
        if len(args) == 2:
            dx = float(x)
            dy = float(y)
            dw = float(args[0])
            dh = float(args[1])
            if context.state.style.image_mode == c.CENTER:
                dx -= dw / 2.0
                dy -= dh / 2.0
            elif context.state.style.image_mode != c.CORNER:
                context._draw_image_fast(image, x, y, *args)
                return
            context._record_image_diagnostics(image)
            context.renderer.draw_image(
                image,
                dx,
                dy,
                dw,
                dh,
                context.state.style,
                context.state.transform.matrix,
                source=None,
            )
            return
        context._draw_image_fast(image, x, y, *args)

    def text(self, value: SupportsText, x: float, y: float) -> None:
        context = self._context
        context.renderer.text(
            str(value), float(x), float(y), context.state.style, context.state.transform.matrix
        )

    def text_width(self, value: SupportsText) -> float:
        context = self._context
        return context.renderer.text_width(str(value), context.state.style)

    def _invalidate_model_batch_cache(self) -> None:
        self._model_batch_cache = None
        self._model_batch_signature_cache = None

    def camera(self, *args: Any) -> Any:
        """Set or return the active 3D camera without global-mode lookup."""
        self._invalidate_model_batch_cache()
        return self._context.camera(*args)

    def set_camera(self, camera: Any) -> Any:
        """Set the active 3D camera without global-mode lookup."""
        self._invalidate_model_batch_cache()
        return self._context.set_camera(camera)

    def perspective(self, *args: Any) -> Any:
        """Set or return the active 3D perspective projection."""
        self._invalidate_model_batch_cache()
        return self._context.perspective(*args)

    def ortho(self, *args: Any) -> Any:
        """Set or return the active 3D orthographic projection."""
        self._invalidate_model_batch_cache()
        return self._context.ortho(*args)

    def frustum(self, *args: Any) -> Any:
        """Set the active 3D frustum projection."""
        self._invalidate_model_batch_cache()
        return self._context.frustum(*args)

    def ambient_light(self, *args: Any) -> None:
        """Add an ambient 3D light without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.ambient_light(*args)

    def directional_light(self, *args: Any) -> None:
        """Add a directional 3D light without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.directional_light(*args)

    def point_light(self, *args: Any) -> None:
        """Add a point 3D light without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.point_light(*args)

    def lights(self) -> None:
        """Enable default 3D lights without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.lights()

    def no_lights(self) -> None:
        """Disable 3D lights without global-mode lookup."""
        self._invalidate_model_batch_cache()
        self._context.no_lights()

    def ambient_material(self, *args: Any) -> None:
        """Set the active ambient 3D material."""
        self._invalidate_model_batch_cache()
        self._context.ambient_material(*args)

    def specular_material(self, *args: Any) -> None:
        """Set the active specular 3D material."""
        self._invalidate_model_batch_cache()
        self._context.specular_material(*args)

    def emissive_material(self, *args: Any) -> None:
        """Set the active emissive 3D material."""
        self._invalidate_model_batch_cache()
        self._context.emissive_material(*args)

    def normal_material(self) -> None:
        """Use normal-based 3D material coloring."""
        self._invalidate_model_batch_cache()
        self._context.normal_material()

    def shininess(self, value: float) -> None:
        """Set active 3D material shininess."""
        self._invalidate_model_batch_cache()
        self._context.shininess(float(value))

    def metalness(self, value: float) -> None:
        """Set active 3D material metalness."""
        self._invalidate_model_batch_cache()
        self._context.metalness(float(value))

    def plane(self, width: float, height: float | None = None) -> None:
        """Draw a 3D plane without global-mode lookup."""
        self._context.plane(float(width), None if height is None else float(height))

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        """Draw a 3D box without global-mode lookup."""
        self._context.box(
            float(width),
            None if height is None else float(height),
            None if depth is None else float(depth),
        )

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        """Draw a 3D sphere without global-mode lookup."""
        self._context.sphere(float(radius), int(detail_x), int(detail_y))

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        """Draw a 3D ellipsoid without global-mode lookup."""
        self._context.ellipsoid(
            float(radius_x),
            None if radius_y is None else float(radius_y),
            None if radius_z is None else float(radius_z),
            int(detail_x),
            int(detail_y),
        )

    def cylinder(
        self,
        radius: float,
        height: float,
        detail_x: int = 24,
        detail_y: int = 1,
        *,
        bottom_cap: bool = True,
        top_cap: bool = True,
    ) -> None:
        """Draw a 3D cylinder without global-mode lookup."""
        self._context.cylinder(
            float(radius),
            float(height),
            int(detail_x),
            int(detail_y),
            bottom_cap=bottom_cap,
            top_cap=top_cap,
        )

    def cone(
        self,
        radius: float,
        height: float,
        detail_x: int = 24,
        detail_y: int = 1,
        *,
        cap: bool = True,
    ) -> None:
        """Draw a 3D cone without global-mode lookup."""
        self._context.cone(float(radius), float(height), int(detail_x), int(detail_y), cap=cap)

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        """Draw a 3D torus without global-mode lookup."""
        self._context.torus(
            float(radius),
            None if tube_radius is None else float(tube_radius),
            int(detail_x),
            int(detail_y),
        )

    def model(self, shape: Mesh3D | Model3D) -> None:
        """Draw a 3D model, preferring the Rust-native model path for Rust-backed meshes."""
        draw_model_fast = self._draw_model_fast
        if draw_model_fast is not None:
            transform = self._model_transform3d_payload()
            signature = self._model_batch_signature(shape)
            cache = self._model_batch_cache
            if cache is not None and cache[0] == signature:
                key = cache[1]
                batch_state = getattr(self._context.renderer, "_model_batch_state", None)
                if (
                    batch_state is not None
                    and getattr(batch_state, "key", None) is key
                    and batch_state.has_records()
                ):
                    batch_state.append(key, transform or _IDENTITY4)
                    return
            draw_model_fast(shape, model_transform=transform)
            batch_state = getattr(self._context.renderer, "_model_batch_state", None)
            key = None if batch_state is None else getattr(batch_state, "key", None)
            if batch_state is not None and key is not None and batch_state.has_records():
                self._model_batch_cache = (signature, key)
            else:
                self._model_batch_cache = None
            return
        self._context.model(shape)
