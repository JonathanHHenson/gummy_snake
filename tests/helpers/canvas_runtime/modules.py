from __future__ import annotations

from gummysnake.backend.canvas_runtime.renderer.command_ingress import FRAME_COMMAND_ABI_VERSION
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


class FakeCanvasSynthProgram:
    pass


class FakeGpuStorageBuffer:
    pass


class FakeGpuComputeShader:
    pass


class FakeCanvasMediaFrameSink:
    pass


class FakeCanvasVideo:
    pass


class FakeCanvasModule:
    CANVAS_ABI_VERSION = EXPECTED_CANVAS_ABI_VERSION
    FRAME_COMMAND_ABI_VERSION = FRAME_COMMAND_ABI_VERSION
    Matrix2D = FakeRustMatrix2D
    Canvas = FakeCanvas
    CanvasImage = FakeRustImage
    CanvasMediaFrameSink = FakeCanvasMediaFrameSink
    CanvasVideo = FakeCanvasVideo
    GpuStorageBuffer = FakeGpuStorageBuffer
    GpuComputeShader = FakeGpuComputeShader
    CanvasModel3D = FakeRustModel3D
    CanvasMesh3D = FakeRustMesh3D
    CanvasSound = FakeRustSound
    CanvasSynthProgram = FakeCanvasSynthProgram
    SketchContextState = FakeSketchContextState

    def canvas_abi_version(self) -> int:
        return EXPECTED_CANVAS_ABI_VERSION

    def frame_command_abi_version(self) -> int:
        return FRAME_COMMAND_ABI_VERSION

    def health_check(self) -> str:
        return "fake-canvas"

    def native_window_available(self) -> bool:
        return True

    def gpu_available(self) -> bool:
        return True

    def webgpu_context_info(self) -> dict[str, object]:
        return {"native_gpu": True}

    def gpu_resource_diagnostics(self) -> dict[str, int]:
        return {}

    def reset_gpu_resource_diagnostics(self) -> None:
        return None

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
