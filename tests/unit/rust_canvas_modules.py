from __future__ import annotations

from pathlib import Path

from rust_canvas_fakes import FakeCanvas

from gummysnake.rust.canvas import EXPECTED_CANVAS_ABI_VERSION


class FakeRustImage:
    width = 2
    height = 1
    version = 0

    def save(self, path: str) -> None:
        Path(path).write_bytes(b"fake-image")

    def to_rgba_bytes(self) -> bytes:
        return bytes([255, 0, 0, 255, 0, 0, 255, 255])


class FakeRustModel3D:
    pass


class FakeRustMesh3D:
    pass


class FakeRustSound:
    path = "fake.wav"
    duration = 1.0
    byte_len = 4

    def to_bytes(self) -> bytes:
        return b"fake"


class FakeCanvasModule:
    CANVAS_ABI_VERSION = EXPECTED_CANVAS_ABI_VERSION
    Canvas = FakeCanvas
    CanvasImage = FakeRustImage
    CanvasModel3D = FakeRustModel3D
    CanvasMesh3D = FakeRustMesh3D
    CanvasSound = FakeRustSound

    def canvas_abi_version(self) -> int:
        return EXPECTED_CANVAS_ABI_VERSION

    def health_check(self) -> str:
        return "fake-canvas"

    def native_window_available(self) -> bool:
        return True

    def gpu_available(self) -> bool:
        return True


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
