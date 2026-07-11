"""Characterize the frame-local fast drawing facade and its retained hot paths."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, cast

import pytest

import gummysnake as gs
from gummysnake import constants as c
from gummysnake._fast_draw import FastDrawScope as CompatibilityFastDrawScope
from gummysnake.fast_draw_runtime.scope import FastDrawScope

_EXPECTED_SLOTS = (
    "_context",
    "_image_matrix",
    "_image_matrix_payload",
    "_image_style_payload",
    "_image_style_revision",
    "_draw_model_fast",
    "_model_batch_cache",
    "_model_batch_signature_cache",
    "_pushed_scope",
    "_transform3d",
    "_transform3d_active",
    "_transform3d_stack",
)
_PUBLIC_METHODS = (
    "point",
    "line",
    "rect",
    "square",
    "ellipse",
    "circle",
    "triangle",
    "image",
    "text",
    "text_width",
    "push",
    "pop",
    "pushed",
    "reset_matrix",
    "translate",
    "scale",
    "apply_matrix_3d",
    "rotate",
    "rotate_x",
    "rotate_y",
    "rotate_z",
    "rotate_quaternion",
    "camera",
    "set_camera",
    "perspective",
    "ortho",
    "frustum",
    "ambient_light",
    "directional_light",
    "point_light",
    "lights",
    "no_lights",
    "ambient_material",
    "specular_material",
    "emissive_material",
    "normal_material",
    "shininess",
    "metalness",
    "plane",
    "box",
    "sphere",
    "ellipsoid",
    "cylinder",
    "cone",
    "torus",
    "model",
)


class _RecorderRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self._model_batch_state = _BatchState()

    def _record(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, args, kwargs))

    def point(self, *args: object) -> None:
        self._record("point", *args)

    def line(self, *args: object) -> None:
        self._record("line", *args)

    def rect(self, *args: object) -> None:
        self._record("rect", *args)

    def ellipse(self, *args: object) -> None:
        self._record("ellipse", *args)

    def triangle(self, *args: object) -> None:
        self._record("triangle", *args)

    def draw_image(self, *args: object, **kwargs: object) -> None:
        self._record("draw_image", *args, **kwargs)

    def text(self, *args: object) -> None:
        self._record("text", *args)

    def text_width(self, value: str, style: object) -> float:
        self._record("text_width", value, style)
        return 37.5


class _BatchState:
    def __init__(self) -> None:
        self.key: object | None = None
        self.records: list[tuple[object, object]] = []

    def has_records(self) -> bool:
        return self.key is not None

    def append(self, key: object, transform: object) -> None:
        self.records.append((key, transform))


class _FastContext:
    width = 320
    height = 240

    def __init__(self) -> None:
        self.renderer = _RecorderRenderer()
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        style = SimpleNamespace(
            rect_mode=c.CORNER,
            ellipse_mode=c.CENTER,
            image_mode=c.CORNER,
            revision=0,
            fill_color=(255, 255, 255, 255),
            stroke_color=None,
        )
        self.state = SimpleNamespace(
            style=style,
            transform=SimpleNamespace(matrix=object()),
        )
        self._camera3d = object()
        self._projection3d = object()
        self._material3d = object()
        self._lights3d: list[object] = []
        self._normal_material3d = False
        self._shader3d = None
        self.fast_model_calls: list[tuple[object, object | None]] = []

    def _angle(self, value: float) -> float:
        return value

    def _draw_image_fast(self, *args: object) -> None:
        self.calls.append(("_draw_image_fast", args, {}))

    def _record_image_diagnostics(self, image: object) -> None:
        self.calls.append(("_record_image_diagnostics", (image,), {}))

    def _draw_model_fast(self, shape: object, *, model_transform: object | None) -> None:
        self.fast_model_calls.append((shape, model_transform))
        self.renderer._model_batch_state.key = object()

    def __getattr__(self, name: str) -> Any:
        def forward(*args: object, **kwargs: object) -> str:
            self.calls.append((name, args, kwargs))
            return name

        return forward


class _OpaqueModel:
    def __iter__(self) -> object:
        raise AssertionError("fast retained model path must not materialize model data")


def _scope() -> tuple[FastDrawScope, _FastContext]:
    context = _FastContext()
    return FastDrawScope(cast(Any, context)), context


def test_fast_draw_scope_public_compatibility_slots_signatures_and_docs() -> None:
    assert gs.FastDrawScope is CompatibilityFastDrawScope is FastDrawScope
    assert FastDrawScope.__slots__ == _EXPECTED_SLOTS
    assert inspect.signature(FastDrawScope) == inspect.signature(CompatibilityFastDrawScope)
    assert tuple(inspect.signature(FastDrawScope.image).parameters) == (
        "self",
        "image",
        "x",
        "y",
        "args",
    )
    assert tuple(inspect.signature(FastDrawScope.rotate).parameters) == (
        "self",
        "angle",
        "x",
        "y",
        "z",
        "axis",
        "quaternion",
    )
    assert inspect.signature(FastDrawScope.cylinder).parameters["bottom_cap"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    scope, _context = _scope()
    assert (scope.width, scope.height) == (320, 240)
    for name in _PUBLIC_METHODS:
        assert inspect.getdoc(getattr(FastDrawScope, name)), (
            f"FastDrawScope.{name} needs a docstring"
        )
    assert inspect.getdoc(FastDrawScope.width.fget)
    assert inspect.getdoc(FastDrawScope.height.fget)


def test_fast_two_d_media_paths_forward_current_style_and_matrix() -> None:
    scope, context = _scope()
    image = cast(Any, object())

    scope.point(1, 2)
    scope.line(1, 2, 3, 4)
    scope.rect(1, 2, 3, 4)
    scope.square(1, 2, 3)
    scope.ellipse(4, 5, 6, 7)
    scope.circle(8, 9, 10)
    scope.triangle(0, 1, 2, 3, 4, 5)
    scope.image(image, 1, 2, 3, 4)
    scope.image(image, 1, 2, 3, 4, 0, 0, 1, 1)
    scope.image(image, 1, 2)
    scope.text("overlay", 5, 6)

    assert scope.text_width("overlay") == 37.5
    assert [name for name, _args, _kwargs in context.renderer.calls] == [
        "point",
        "line",
        "rect",
        "rect",
        "ellipse",
        "ellipse",
        "triangle",
        "draw_image",
        "text",
        "text_width",
    ]
    assert [name for name, _args, _kwargs in context.calls] == [
        "_record_image_diagnostics",
        "_draw_image_fast",
        "_draw_image_fast",
    ]


def test_fast_transform_stack_and_rotation_errors_are_frame_local() -> None:
    scope, _context = _scope()

    scope.translate(10, 20, 30)
    outer_transform = scope._model_transform3d_payload()
    with scope.pushed():
        scope.scale(2)
        scope.rotate_x(0.25)
        scope.rotate_y(0.5)
        scope.rotate_z(0.75)
        scope.rotate_quaternion(1, 0, 0, 0)
        assert scope._model_transform3d_payload() != outer_transform
    assert scope._model_transform3d_payload() == outer_transform

    scope.rotate(0.125, axis=(0, 1, 0))
    scope.rotate(quaternion=(1, 0, 0, 0))
    scope.apply_matrix_3d(tuple(float(index) for index in range(16)))
    assert scope._model_transform3d_payload() is not None
    scope.reset_matrix()
    assert scope._model_transform3d_payload() is None
    with pytest.raises(IndexError):
        scope.pop()
    with pytest.raises(TypeError, match="missing required angle"):
        scope.rotate()
    with pytest.raises(ValueError, match="either angle or quaternion"):
        scope.rotate(1, quaternion=(1, 0, 0, 0))


@pytest.mark.parametrize(
    ("method", "args", "kwargs"),
    (
        ("camera", (1, 2, 3), {}),
        ("set_camera", (object(),), {}),
        ("perspective", (1.0,), {}),
        ("ortho", (-1, 1, -1, 1), {}),
        ("frustum", (-1, 1, -1, 1, 1, 10), {}),
        ("ambient_light", (20,), {}),
        ("directional_light", (255, 0, 0, 1, 0, 0), {}),
        ("point_light", (255, 0, 0, 1, 2, 3), {}),
        ("lights", (), {}),
        ("no_lights", (), {}),
        ("ambient_material", (20,), {}),
        ("specular_material", (20,), {}),
        ("emissive_material", (20,), {}),
        ("normal_material", (), {}),
        ("shininess", (2,), {}),
        ("metalness", (0.5,), {}),
        ("plane", (3, 4), {}),
        ("box", (3, 4, 5), {}),
        ("sphere", (3, 8, 6), {}),
        ("ellipsoid", (3, 4, 5, 8, 6), {}),
        ("cylinder", (3, 4, 8, 2), {"bottom_cap": False, "top_cap": True}),
        ("cone", (3, 4, 8, 2), {"cap": False}),
        ("torus", (3, 1, 8, 6), {}),
    ),
)
def test_fast_three_d_controls_invalidate_batches_and_forward_directly(
    method: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    scope, context = _scope()
    scope._model_batch_cache = ((object(),), object())
    scope._model_batch_signature_cache = (object(), (object(),))

    result = getattr(scope, method)(*args, **kwargs)

    assert context.calls[-1][0] == method
    assert context.calls[-1][2] == kwargs
    if method in {"camera", "set_camera", "perspective", "ortho", "frustum"}:
        assert result == method
    if method not in {"plane", "box", "sphere", "ellipsoid", "cylinder", "cone", "torus"}:
        assert scope._model_batch_cache is None
        assert scope._model_batch_signature_cache is None


def test_fast_model_reuses_retained_batch_without_materializing_model_data() -> None:
    scope, context = _scope()
    shape = cast(Any, _OpaqueModel())

    scope.translate(4, 5, 6)
    scope.model(shape)
    first_transform = context.fast_model_calls[-1][1]
    scope.model(shape)

    assert context.fast_model_calls == [(shape, first_transform)]
    assert len(context.renderer._model_batch_state.records) == 1
    scope.ambient_light(10)
    assert scope._model_batch_cache is None
    scope.model(shape)
    assert len(context.fast_model_calls) == 2


def test_fast_model_preserves_the_legacy_direct_context_forward_when_no_batcher_exists() -> None:
    scope, context = _scope()
    cast(Any, context)._draw_model_fast = None
    scope = FastDrawScope(cast(Any, context))
    shape = cast(Any, _OpaqueModel())

    scope.model(shape)

    assert context.calls[-1] == ("model", (shape,), {})
