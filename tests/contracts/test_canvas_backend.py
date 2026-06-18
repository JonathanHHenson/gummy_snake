from __future__ import annotations

import pytest

from p5.backends import create_backend, registry
from p5.backends.canvas import CanvasBackend
from p5.exceptions import BackendCapabilityError
from p5.rust import canvas as canvas_bridge
from p5.sketch import Sketch


def test_sketch_defaults_to_canvas_runtime() -> None:
    sketch = Sketch()

    assert sketch.headless is None
    assert isinstance(create_backend(), CanvasBackend)


def test_canvas_runtime_requires_rust_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="requires the Rust canvas extension"):
        create_backend()


def test_canvas_default_eligibility_reports_missing_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    eligible, reason = registry.canvas_default_eligibility()

    assert eligible is False
    assert "unavailable" in reason


def test_canvas_default_eligibility_reports_available_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadyCanvasModule:
        def health_check(self) -> str:
            return "rust-canvas"

        def gpu_available(self) -> bool:
            return True

    monkeypatch.setattr(canvas_bridge, "_canvas", ReadyCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    eligible, reason = registry.canvas_default_eligibility()

    assert eligible is True
    assert "available" in reason
