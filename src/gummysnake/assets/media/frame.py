"""Rust-owned reusable decoded-media frame sinks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, cast

from gummysnake.assets.image import Image
from gummysnake.assets.image.canvas import CanvasImage
from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust.canvas import GUMMY_CANVAS_BUILD_COMMAND, require_canvas_runtime


class DecodedFrame(Protocol):
    """Contiguous unsigned-byte decoded frame accepted by :class:`MediaFrameSink`."""

    @property
    def shape(self) -> Sequence[int]: ...

    def __buffer__(self, flags: int, /) -> memoryview: ...

    def __release_buffer__(self, buffer: memoryview, /) -> None: ...


class _NativeMediaFrameSink(Protocol):
    image: Any

    def update(
        self,
        pixels: object,
        width: int,
        height: int,
        format: str = "rgba",
        stride: int | None = None,
    ) -> None: ...

    def diagnostics(self) -> dict[str, int]: ...


class MediaFrameSink:
    """Reusable Rust image identity for contiguous decoded frame buffers."""

    __slots__ = ("_image", "_native")

    def __init__(self, width: int, height: int) -> None:
        runtime = require_canvas_runtime()
        sink_type = getattr(runtime, "CanvasMediaFrameSink", None)
        if not isinstance(sink_type, type):
            raise BackendCapabilityError(
                "The installed canvas runtime does not expose CanvasMediaFrameSink. "
                f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        try:
            self._native = cast(_NativeMediaFrameSink, sink_type(int(width), int(height)))
        except ValueError as exc:
            raise BackendCapabilityError(
                f"Could not create a native media frame sink: {exc}"
            ) from exc
        self._image = Image.from_rust_image(CanvasImage(self._native.image))

    @property
    def image(self) -> Image:
        """Return the stable public image wrapper updated by this sink."""

        return self._image

    def update(
        self,
        frame: DecodedFrame,
        *,
        format: str | None = None,
        stride: int | None = None,
    ) -> Image:
        """Borrow a contiguous frame buffer and update the stable Rust image."""

        shape = getattr(frame, "shape", None)
        if shape is None or len(shape) not in {2, 3}:
            raise BackendCapabilityError(
                "Decoded media frames must expose a 2D grayscale or 3D byte-buffer shape."
            )
        height = int(shape[0])
        width = int(shape[1])
        channels = 1 if len(shape) == 2 else int(shape[2])
        inferred = {1: "gray", 3: "bgr", 4: "bgra"}.get(channels)
        pixel_format = format or inferred
        if pixel_format is None:
            raise BackendCapabilityError(
                "Decoded media frames must use gray, BGR, BGRA, or explicit RGBA format."
            )
        try:
            view = memoryview(cast(Any, frame))
        except TypeError as exc:
            raise BackendCapabilityError(
                "Decoded media frames must expose a C-contiguous unsigned-byte buffer; "
                "frame.tobytes() copying is not used."
            ) from exc
        if not view.c_contiguous or view.itemsize != 1:
            raise BackendCapabilityError(
                "Decoded media frames must be C-contiguous unsigned-byte buffers."
            )
        row_stride = stride
        if row_stride is None and view.ndim >= 2 and view.strides:
            row_stride = int(view.strides[0])
        try:
            self._native.update(view, width, height, pixel_format, row_stride)
        except ValueError as exc:
            raise BackendCapabilityError(f"Native media frame conversion failed: {exc}") from exc
        return self._image

    def diagnostics(self) -> dict[str, int]:
        """Return copy, allocation, image-key, and generation diagnostics."""

        return {
            str(key): int(value)
            for key, value in dict(self._native.diagnostics()).items()
            if isinstance(value, int) and not isinstance(value, bool)
        }


def frame_to_image(frame: DecodedFrame) -> Image:
    """Convert one contiguous decoded frame through a Rust-owned frame sink."""

    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) not in {2, 3}:
        raise BackendCapabilityError(
            "Decoded media frames must expose grayscale, BGR, BGRA, or RGBA dimensions."
        )
    sink = MediaFrameSink(int(shape[1]), int(shape[0]))
    return sink.update(frame)


def convert_frame_bytes(frame: DecodedFrame, width: int, height: int, channels: int) -> bytes:
    """Compatibility helper returning RGBA bytes after native sink conversion."""

    shape = getattr(frame, "shape", None)
    if shape is None or int(shape[0]) != height or int(shape[1]) != width:
        raise BackendCapabilityError("Decoded media frame dimensions do not match the request.")
    expected_channels = 1 if len(shape) == 2 else int(shape[2])
    if expected_channels != channels:
        raise BackendCapabilityError(
            "Decoded media frame channel count does not match the request."
        )
    return MediaFrameSink(width, height).update(frame).to_rgba_bytes()


__all__ = ["DecodedFrame", "MediaFrameSink", "convert_frame_bytes", "frame_to_image"]
