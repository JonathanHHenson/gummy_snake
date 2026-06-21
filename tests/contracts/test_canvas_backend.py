from __future__ import annotations

import pytest

from gummysnake.backend import create_backend, registry
from gummysnake.backend.canvas import CanvasBackend
from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust import canvas as canvas_bridge
from gummysnake.sketch import Sketch


def test_sketch_defaults_to_canvas_runtime() -> None:
    sketch = Sketch()

    assert sketch.headless is None
    assert isinstance(create_backend(), CanvasBackend)


def test_canvas_runtime_requires_rust_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="requires the Rust canvas runtime"):
        create_backend()


def test_canvas_default_eligibility_requires_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="requires the Rust canvas runtime"):
        registry.canvas_default_eligibility()


def test_canvas_default_eligibility_reports_available_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "require_canvas_runtime", lambda: object())
    monkeypatch.setattr(canvas_bridge, "canvas_gpu_available", lambda: True)

    eligible, reason = registry.canvas_default_eligibility()

    assert eligible is True
    assert "available" in reason
