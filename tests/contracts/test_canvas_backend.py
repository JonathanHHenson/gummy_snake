from __future__ import annotations

import pytest

from p5.backends import available_backends, create_backend, get_backend_class, registry
from p5.backends.canvas import CanvasBackend
from p5.exceptions import BackendCapabilityError
from p5.rust import canvas as canvas_bridge
from p5.sketch import Sketch


def test_canvas_backend_is_registered_as_opt_in_backend() -> None:
    assert "canvas" in available_backends()
    assert get_backend_class("canvas") is CanvasBackend


def test_canvas_backend_selection_requires_rust_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="p5.rust._canvas"):
        create_backend("canvas")


def test_default_backend_stays_pyglet_until_canvas_parity_is_marked_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "CANVAS_DEFAULT_PARITY_READY", False)
    monkeypatch.setattr(canvas_bridge, "_canvas", object())

    eligible, reason = registry.canvas_default_eligibility()

    assert eligible is False
    assert "parity criteria" in reason
    assert registry.select_default_backend() == "pyglet"
    assert Sketch().backend_name == "pyglet"


def test_canvas_can_be_selected_as_default_only_after_all_runtime_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadyCanvasModule:
        def health_check(self) -> str:
            return "rust-canvas"

        def native_window_available(self) -> bool:
            return True

        def gpu_available(self) -> bool:
            return True

    monkeypatch.setattr(registry, "CANVAS_DEFAULT_PARITY_READY", True)
    monkeypatch.setattr(canvas_bridge, "_canvas", ReadyCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    eligible, reason = registry.canvas_default_eligibility()

    assert eligible is True
    assert "passed" in reason
    assert registry.select_default_backend() == "canvas"


def test_auto_backend_uses_current_default_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "CANVAS_DEFAULT_PARITY_READY", False)

    backend = create_backend("auto")

    assert backend.__class__.__name__ == "PygletBackend"
