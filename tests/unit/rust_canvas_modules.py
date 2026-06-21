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
    _next_key = 1

    def __init__(self, width: int = 2, height: int = 1, pixels: bytes | None = None) -> None:
        self.width = width
        self.height = height
        self.version = 0
        self.key = FakeRustImage._next_key
        FakeRustImage._next_key += 1
        self._pixels = bytearray(pixels or bytes([255, 0, 0, 255, 0, 0, 255, 255]))

    @staticmethod
    def from_file(path: str) -> FakeRustImage:
        return FakeRustImage()

    @staticmethod
    def from_rgba_bytes(width: int, height: int, pixels: bytes) -> FakeRustImage:
        return FakeRustImage(width, height, pixels)

    def _offset(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("Pixel coordinates are outside the image bounds.")
        return (y * self.width + x) * 4

    def _changed(self) -> None:
        self.version += 1

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        offset = self._offset(x, y)
        return tuple(self._pixels[offset : offset + 4])  # type: ignore[return-value]

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int, a: int) -> None:
        offset = self._offset(x, y)
        self._pixels[offset : offset + 4] = bytes([r, g, b, a])
        self._changed()

    def replace_rgba_bytes(self, pixels: bytes) -> None:
        if len(pixels) != self.width * self.height * 4:
            raise ValueError("RGBA buffer length mismatch")
        self._pixels = bytearray(pixels)
        self._changed()

    def copy(self) -> FakeRustImage:
        return FakeRustImage(self.width, self.height, bytes(self._pixels))

    def crop(self, sx: int, sy: int, sw: int, sh: int) -> FakeRustImage:
        cropped = bytearray(sw * sh * 4)
        for y in range(sh):
            src_y = sy + y
            if not 0 <= src_y < self.height:
                continue
            for x in range(sw):
                src_x = sx + x
                if not 0 <= src_x < self.width:
                    continue
                src = self._offset(src_x, src_y)
                dst = (y * sw + x) * 4
                cropped[dst : dst + 4] = self._pixels[src : src + 4]
        return FakeRustImage(sw, sh, bytes(cropped))

    def resize(self, width: int, height: int) -> None:
        resized = bytearray(width * height * 4)
        for y in range(height):
            sy = min(y * self.height // height, self.height - 1)
            for x in range(width):
                sx = min(x * self.width // width, self.width - 1)
                src = self._offset(sx, sy)
                dst = (y * width + x) * 4
                resized[dst : dst + 4] = self._pixels[src : src + 4]
        self.width = width
        self.height = height
        self._pixels = resized
        self._changed()

    def mask(self, mask: FakeRustImage) -> None:
        for y in range(self.height):
            my = min(y * mask.height // self.height, mask.height - 1)
            for x in range(self.width):
                mx = min(x * mask.width // self.width, mask.width - 1)
                mask_offset = mask._offset(mx, my)
                mask_alpha = (
                    (
                        mask._pixels[mask_offset]
                        + mask._pixels[mask_offset + 1]
                        + mask._pixels[mask_offset + 2]
                    )
                    * mask._pixels[mask_offset + 3]
                    + 382
                ) // 765
                offset = self._offset(x, y) + 3
                self._pixels[offset] = (self._pixels[offset] * mask_alpha + 127) // 255
        self._changed()

    def filter(self, mode: str, value: float | None) -> None:
        if mode == "invert":
            for offset in range(0, len(self._pixels), 4):
                self._pixels[offset] = 255 - self._pixels[offset]
                self._pixels[offset + 1] = 255 - self._pixels[offset + 1]
                self._pixels[offset + 2] = 255 - self._pixels[offset + 2]
        elif mode == "gray":
            for offset in range(0, len(self._pixels), 4):
                gray = round(
                    0.2126 * self._pixels[offset]
                    + 0.7152 * self._pixels[offset + 1]
                    + 0.0722 * self._pixels[offset + 2]
                )
                self._pixels[offset : offset + 3] = bytes([gray, gray, gray])
        self._changed()

    def alpha_composite(self, source: FakeRustImage, dx: int, dy: int) -> None:
        for sy in range(source.height):
            ty = dy + sy
            if not 0 <= ty < self.height:
                continue
            for sx in range(source.width):
                tx = dx + sx
                if not 0 <= tx < self.width:
                    continue
                src = source._pixels[source._offset(sx, sy) : source._offset(sx, sy) + 4]
                dst_offset = self._offset(tx, ty)
                dst = self._pixels[dst_offset : dst_offset + 4]
                alpha = src[3]
                inv = 255 - alpha
                out_alpha = alpha + (dst[3] * inv + 127) // 255
                if out_alpha == 0:
                    self._pixels[dst_offset : dst_offset + 4] = bytes([0, 0, 0, 0])
                else:
                    self._pixels[dst_offset : dst_offset + 4] = bytes(
                        [
                            (src[i] * alpha + dst[i] * dst[3] * inv // 255 + out_alpha // 2)
                            // out_alpha
                            for i in range(3)
                        ]
                        + [out_alpha]
                    )
        self._changed()

    def save(self, path: str) -> None:
        Path(path).write_bytes(b"fake-image")

    def to_rgba_bytes(self) -> bytes:
        return bytes(self._pixels)


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
