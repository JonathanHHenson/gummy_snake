from __future__ import annotations

from gummysnake.rust.canvas import EXPECTED_CANVAS_ABI_VERSION
from tests.helpers.canvas_runtime.assets import (
    FakeRustImage,
    FakeRustMatrix2D,
    FakeRustMesh3D,
    FakeRustModel3D,
    FakeRustSound,
)
from tests.helpers.canvas_runtime.fakes import FakeCanvas
from tests.helpers.canvas_runtime.state import FakeSketchContextState


class FakeCanvasModule:
    CANVAS_ABI_VERSION = EXPECTED_CANVAS_ABI_VERSION
    Matrix2D = FakeRustMatrix2D
    Canvas = FakeCanvas
    CanvasImage = FakeRustImage
    CanvasModel3D = FakeRustModel3D
    CanvasMesh3D = FakeRustMesh3D
    CanvasSound = FakeRustSound
    SketchContextState = FakeSketchContextState

    def canvas_abi_version(self) -> int:
        return EXPECTED_CANVAS_ABI_VERSION

    def health_check(self) -> str:
        return "fake-canvas"

    def native_window_available(self) -> bool:
        return True

    def gpu_available(self) -> bool:
        return True

    def parse_obj_model_handle(self, text: str, source: str, normalize: bool) -> FakeRustModel3D:
        return FakeRustModel3D()


class FakeCanvasModuleWithoutNativeWindow(FakeCanvasModule):
    class Canvas(FakeCanvas):
        def native_window_available(self) -> bool:
            return False

    def native_window_available(self) -> bool:
        return False


class FakeCanvasModuleWithoutGpu(FakeCanvasModule):
    def gpu_available(self) -> bool:
        return False


class FakeCanvasModuleWithHealthFailure(FakeCanvasModule):
    def health_check(self) -> str:
        raise RuntimeError("boom")


class FakeCanvasModuleWithoutAbi:
    CANVAS_ABI_VERSION = None
    Canvas = FakeCanvas

    def canvas_abi_version(self) -> None:
        return None


class FakeCanvasModuleWithBadAbi(FakeCanvasModule):
    CANVAS_ABI_VERSION = EXPECTED_CANVAS_ABI_VERSION + 1

    def canvas_abi_version(self) -> int:
        return EXPECTED_CANVAS_ABI_VERSION + 1
