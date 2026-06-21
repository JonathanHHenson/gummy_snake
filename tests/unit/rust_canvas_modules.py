from __future__ import annotations

from pathlib import Path

from rust_canvas_fakes import FakeCanvas

from gummysnake.rust.canvas import EXPECTED_CANVAS_ABI_VERSION


class FakeRustMatrix2D:
    def __init__(
        self,
        a: float = 1.0,
        b: float = 0.0,
        c: float = 0.0,
        d: float = 1.0,
        e: float = 0.0,
        f: float = 0.0,
    ) -> None:
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    def multiply(self, other: FakeRustMatrix2D) -> FakeRustMatrix2D:
        return FakeRustMatrix2D(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    @staticmethod
    def translation(x: float, y: float) -> FakeRustMatrix2D:
        return FakeRustMatrix2D(1.0, 0.0, 0.0, 1.0, x, y)


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
    Matrix2D = FakeRustMatrix2D
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
