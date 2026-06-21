from __future__ import annotations

import pytest
from rust_canvas_modules import (
    FakeCanvasModule,
    FakeCanvasModuleWithBadAbi,
    FakeCanvasModuleWithHealthFailure,
    FakeCanvasModuleWithoutAbi,
    FakeCanvasModuleWithoutGpu,
)

from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust import canvas as canvas_bridge
from gummysnake.rust.canvas import (
    EXPECTED_CANVAS_ABI_VERSION,
    canvas_abi_version,
    canvas_gpu_available,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    canvas_native_window_available,
    is_canvas_runtime_available,
    require_canvas_runtime,
)


def test_canvas_health_check_reports_required_runtime() -> None:
    assert canvas_health_check() == "rust-canvas"
    assert canvas_abi_version() == EXPECTED_CANVAS_ABI_VERSION
    assert canvas_native_window_available() in {True, False}
    assert canvas_gpu_available() in {True, False}
    assert canvas_gpu_status()
    assert is_canvas_runtime_available() is True
    assert canvas_import_error() is None


def test_canvas_wrapper_uses_loaded_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCanvasModule()
    monkeypatch.setattr(canvas_bridge, "_canvas", fake)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    assert is_canvas_runtime_available()
    assert canvas_health_check() == "fake-canvas"
    assert canvas_abi_version() == EXPECTED_CANVAS_ABI_VERSION
    assert canvas_native_window_available() is True
    assert canvas_gpu_available() is True
    assert canvas_gpu_status() == "available"
    assert require_canvas_runtime() is fake


def test_canvas_wrapper_raises_capability_error_when_runtime_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="gummysnake.rust._canvas"):
        require_canvas_runtime()


def test_canvas_wrapper_rejects_runtime_missing_asset_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingAssetClasses(FakeCanvasModule):
        CanvasSound = None

    monkeypatch.setattr(canvas_bridge, "_canvas", MissingAssetClasses())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    with pytest.raises(BackendCapabilityError, match="CanvasSound"):
        require_canvas_runtime()


def test_canvas_wrapper_rejects_runtime_missing_asset_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeCanvasModule()
    monkeypatch.setattr(runtime, "parse_obj_model_handle", None)

    monkeypatch.setattr(canvas_bridge, "_canvas", runtime)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    with pytest.raises(BackendCapabilityError, match="parse_obj_model_handle"):
        require_canvas_runtime()


@pytest.mark.parametrize(
    ("module", "message"),
    [
        (FakeCanvasModuleWithoutAbi(), "expected canvas ABI"),
        (FakeCanvasModuleWithBadAbi(), "expected canvas ABI"),
        (FakeCanvasModuleWithHealthFailure(), "failed its health check"),
    ],
)
def test_canvas_wrapper_rejects_incompatible_or_unhealthy_runtimes(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    message: str,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", module)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    with pytest.raises(BackendCapabilityError, match=message):
        require_canvas_runtime()


def test_canvas_gpu_status_explains_cpu_continuation_when_gpu_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModuleWithoutGpu())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    assert canvas_gpu_available() is False
    assert "headless rendering can continue" in canvas_gpu_status()
