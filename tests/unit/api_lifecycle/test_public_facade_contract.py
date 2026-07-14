"""Characterize public façade parity and package-specific capability errors."""

from __future__ import annotations

import inspect

import pytest

import gummysnake as gs
from gummysnake.backend import create_backend
from gummysnake.context import SketchContext
from gummysnake.exceptions import (
    BackendCapabilityError,
    ContextError,
)
from gummysnake.rust import canvas as canvas_bridge
from gummysnake.rust import ecs as ecs_bridge

_SHARED_SKETCH_CONTEXT_METHODS = (
    "create_canvas",
    "background",
    "fill",
    "no_stroke",
    "rect",
    "circle",
    "line",
    "triangle",
    "text",
    "image",
    "translate",
    "rotate",
    "scale",
    "push",
    "pop",
    "frame_rate",
    "no_loop",
    "redraw",
    "fast",
)
_FAST_DRAW_METHODS = (
    "rect",
    "circle",
    "line",
    "triangle",
    "text",
    "image",
    "translate",
    "rotate",
    "scale",
    "push",
    "pop",
)
_IMAGE_METHODS = (
    "copy",
    "resize",
    "mask",
    "filter",
    "get",
    "set",
    "load_pixels",
    "update_pixels",
    "to_rgba_bytes",
)


def test_sketch_context_and_fast_facades_expose_the_promised_capabilities() -> None:
    for name in _SHARED_SKETCH_CONTEXT_METHODS:
        assert hasattr(gs.Sketch, name), f"Sketch.{name}"
        assert hasattr(SketchContext, name), f"SketchContext.{name}"

    for name in _FAST_DRAW_METHODS:
        assert hasattr(gs.FastDrawScope, name), f"FastDrawScope.{name}"
        assert hasattr(SketchContext, name), f"SketchContext.{name}"

    for name in _IMAGE_METHODS:
        method = getattr(gs.Image, name)
        assert inspect.getdoc(method), f"Image.{name} needs a public docstring"


def _render_global_scene() -> bytes:
    def setup() -> None:
        gs.create_canvas(16, 12)
        gs.background(0)
        gs.no_stroke()
        gs.fill(255, 0, 0)
        with gs.transform(translate=(3, 2)):
            gs.rect(0, 0, 4, 3)
            gs.circle(8, 4, 4)

    return bytes(gs.run(setup=setup, headless=True, max_frames=0).load_pixels())


def _render_object_scene() -> bytes:
    class ObjectSketch(gs.Sketch):
        def setup(self) -> None:
            self.create_canvas(16, 12)
            self.background(0)
            self.no_stroke()
            self.fill(255, 0, 0)
            with self.transform(translate=(3, 2)):
                self.rect(0, 0, 4, 3)
                self.circle(8, 4, 4)

    return bytes(ObjectSketch(headless=True).run(max_frames=0).load_pixels())


def _render_fast_scene() -> bytes:
    def setup() -> None:
        gs.create_canvas(16, 12)
        gs.background(0)
        gs.no_stroke()
        gs.fill(255, 0, 0)
        with gs.transform(translate=(3, 2)):
            draw = gs.fast()
            draw.rect(0, 0, 4, 3)
            draw.circle(8, 4, 4)

    return bytes(gs.run(setup=setup, headless=True, max_frames=0).load_pixels())


def test_global_object_and_fast_facades_render_the_same_scene() -> None:
    global_pixels = _render_global_scene()

    assert _render_object_scene() == global_pixels
    assert _render_fast_scene() == global_pixels


def test_global_mode_requires_an_active_context() -> None:
    with pytest.raises(ContextError, match="requires an active sketch"):
        gs.rect(0, 0, 1, 1)
    with pytest.raises(ContextError, match="requires an active sketch"):
        gs.fast()


def test_missing_canvas_runtime_raises_rebuild_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="requires the Rust canvas runtime"):
        create_backend()


def test_missing_ecs_runtime_raises_rebuild_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ecs_bridge, "_canvas", None)
    monkeypatch.setattr(ecs_bridge, "_ECS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="Rebuild it with"):
        ecs_bridge.require_ecs_runtime()
