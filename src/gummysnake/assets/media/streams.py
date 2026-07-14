"""Public media streams backed by the canonical Rust media runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

from gummysnake.assets.audio import AudioInput, create_audio_in
from gummysnake.assets.image import Image
from gummysnake.assets.image.canvas import CanvasImage
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError
from gummysnake.rust.canvas import GUMMY_CANVAS_BUILD_COMMAND, require_canvas_runtime

_VIDEO_KINDS = {"video", "camera"}
_AUDIO_KINDS = {"audio", "microphone", "mic"}
_AUDIO_VIDEO_KINDS = {"av", "audio_video", "video+audio", "audio+video"}


class _NativeVideo(Protocol):
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration: float
    is_playing: bool

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def looping(self, value: bool | None = None) -> bool: ...

    def no_loop(self) -> None: ...

    def speed(self, value: float | None = None) -> float: ...

    def time(self) -> float: ...

    def seek(self, seconds: float) -> None: ...

    def read(self) -> Any | None: ...

    def current_frame(self) -> Any | None: ...

    def close(self) -> None: ...

    def diagnostics(self) -> dict[str, object]: ...


class Video:
    """Rust-decoded self-contained video stream with reusable image identity."""

    __slots__ = ("_image", "_native", "_path")

    def __init__(self, native: _NativeVideo, path: Path) -> None:
        self._native = native
        self._path = path
        self._image: Image | None = None

    @property
    def path(self) -> Path:
        """Path to the opened video file."""

        return self._path

    @property
    def width(self) -> int:
        """Decoded video width in pixels."""

        return int(self._native.width)

    @property
    def height(self) -> int:
        """Decoded video height in pixels."""

        return int(self._native.height)

    @property
    def fps(self) -> float:
        """Average decoded frame rate."""

        return float(self._native.fps)

    @property
    def frame_count(self) -> int:
        """Number of decoded frames."""

        return int(self._native.frame_count)

    @property
    def duration(self) -> float:
        """Decoded timeline duration in seconds."""

        return float(self._native.duration)

    @property
    def is_playing(self) -> bool:
        """Return whether explicit reads advance playback."""

        return bool(self._native.is_playing)

    def play(self) -> None:
        """Start or resume frame advancement."""

        self._native.play()

    def pause(self) -> None:
        """Pause frame advancement while preserving the current frame."""

        self._native.pause()

    def stop(self) -> None:
        """Pause and seek to the beginning."""

        self._native.stop()
        self._image = None

    def looping(self, value: bool | None = None) -> bool:
        """Get or set end-of-stream looping."""

        return bool(self._native.looping(value))

    def loop(self) -> None:
        """Enable looping and start playback."""

        cast(Any, self._native).loop()

    def no_loop(self) -> None:
        """Disable end-of-stream looping."""

        self._native.no_loop()

    def speed(self, value: float | None = None) -> float:
        """Get or set the positive playback-speed metadata."""

        if value is not None and (value <= 0 or not float(value) < float("inf")):
            raise ArgumentValidationError("Video.speed() must be positive and finite.")
        return float(self._native.speed(value))

    def time(self) -> float:
        """Return the current decoded timeline position."""

        return float(self._native.time())

    def seek(self, seconds: float) -> None:
        """Seek to a finite position in the decoded timeline."""

        target = float(seconds)
        if target < 0 or target > self.duration or not target < float("inf"):
            raise ArgumentValidationError(
                f"Video.seek() must be between 0 and {self.duration:.6f} seconds."
            )
        self._native.seek(target)
        self._image = None

    def _wrap_image(self, native_image: Any | None) -> Image | None:
        if native_image is None:
            return None
        if self._image is None:
            self._image = Image.from_rust_image(CanvasImage(native_image))
        return self._image

    def read(self) -> Image | None:
        """Read the current/next frame using one stable public image wrapper."""

        return self._wrap_image(self._native.read())

    def current_frame(self) -> Image | None:
        """Return the stable current frame image, if a frame has been read."""

        return self._wrap_image(self._native.current_frame())

    def diagnostics(self) -> dict[str, object]:
        """Return Rust decoder, residency, and image-generation diagnostics."""

        return dict(self._native.diagnostics())

    def close(self) -> None:
        """Release decoded frames and stop playback."""

        self._native.close()
        self._image = None


class Capture:
    """Reserved public camera type for a future Rust-native capture build."""


class AudioVideoCapture:
    """Combined capture type; unavailable until Rust-native camera capture is built."""


def create_video(path: str | Path) -> Video:
    """Open a GIF video through the canonical Rust decoder."""

    video_path = Path(path).expanduser()
    if not video_path.exists():
        raise ArgumentValidationError(f"Video file does not exist: {video_path!s}.")
    runtime = require_canvas_runtime()
    video_type = getattr(runtime, "CanvasVideo", None)
    if not isinstance(video_type, type):
        raise BackendCapabilityError(
            "The installed canvas runtime does not expose CanvasVideo. "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )
    try:
        native = cast(_NativeVideo, cast(Any, video_type).open(str(video_path)))
    except (RuntimeError, ValueError) as exc:
        raise BackendCapabilityError(f"Could not open video file {video_path!s}: {exc}") from exc
    return Video(native, video_path)


async def create_video_async(path: str | Path) -> Video:
    """Open a Rust-owned video from an async lifecycle callback."""

    return create_video(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Create audio input or fail closed for unavailable Rust-native camera capture."""

    del device, width, height
    normalized_kind = kind.lower()
    if normalized_kind in _AUDIO_KINDS:
        audio = create_audio_in()
        audio.start()
        return audio
    if normalized_kind in _VIDEO_KINDS | _AUDIO_VIDEO_KINDS:
        raise BackendCapabilityError(
            "Rust-native camera capture is not available in this gummy_canvas build. "
            "No OpenCV, synthetic camera, or platform decoder fallback is selected."
        )
    raise ArgumentValidationError(
        "create_capture() kind must be 'video'/'camera', 'audio'/'microphone', or 'audio+video'."
    )


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Create a capture object from an async lifecycle callback."""

    return create_capture(kind, device=device, width=width, height=height)


__all__ = [
    "AudioVideoCapture",
    "Capture",
    "Video",
    "create_capture",
    "create_capture_async",
    "create_video",
    "create_video_async",
]
