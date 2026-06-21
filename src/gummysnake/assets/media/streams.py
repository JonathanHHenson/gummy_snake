"""Backend-neutral video playback and camera capture helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from gummysnake.assets.image import Image
from gummysnake.assets.media.cv2 import (
    capture_is_open as _capture_is_open,
)
from gummysnake.assets.media.cv2 import (
    load_cv2_module as _load_cv2_module,
)
from gummysnake.assets.media.cv2 import (
    release_capture as _release_capture,
)
from gummysnake.assets.media.cv2 import (
    set_capture_dimensions as _set_capture_dimensions,
)
from gummysnake.assets.media.frame import frame_to_image as _frame_to_image
from gummysnake.exceptions import (
    ArgumentValidationError,
    BackendCapabilityError,
    UnsupportedFeatureError,
)

_VIDEO_KINDS = {"video", "camera"}
_AUDIO_KINDS = {"audio", "microphone", "mic"}
_AUDIO_VIDEO_KINDS = {"av", "audio_video", "video+audio", "audio+video"}


class Video:
    """File-backed video stream with explicit frame-reading semantics."""

    def __init__(self, capture: Any, *, path: Path, cv2_module: Any) -> None:
        self._capture = capture
        self._path = path
        self._cv2 = cv2_module
        self._playing = False
        self._loop = False
        self._closed = False
        self._last_frame: Image | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def width(self) -> int:
        return int(self._get_prop("CAP_PROP_FRAME_WIDTH") or 0)

    @property
    def height(self) -> int:
        return int(self._get_prop("CAP_PROP_FRAME_HEIGHT") or 0)

    @property
    def fps(self) -> float | None:
        fps = float(self._get_prop("CAP_PROP_FPS") or 0.0)
        return fps if fps > 0 else None

    @property
    def frame_count(self) -> int | None:
        count = int(self._get_prop("CAP_PROP_FRAME_COUNT") or 0)
        return count if count > 0 else None

    @property
    def duration(self) -> float | None:
        fps = self.fps
        frame_count = self.frame_count
        if fps is None or frame_count is None:
            return None
        return frame_count / fps

    @property
    def is_playing(self) -> bool:
        return self._playing

    def play(self) -> None:
        self._ensure_open()
        self._playing = True

    def pause(self) -> None:
        self._ensure_open()
        self._playing = False

    def stop(self) -> None:
        self._ensure_open()
        self._playing = False
        self.seek(0.0)

    def looping(self, value: bool | None = None) -> bool:
        if value is not None:
            self._loop = bool(value)
        return self._loop

    def seek(self, seconds: float) -> None:
        self._ensure_open()
        if seconds < 0:
            raise ArgumentValidationError("Video.seek() cannot be negative.")
        set_prop = getattr(self._capture, "set", None)
        position_prop = getattr(self._cv2, "CAP_PROP_POS_MSEC", None)
        if not callable(set_prop) or position_prop is None:
            raise BackendCapabilityError("Video seeking is unavailable on this system.")
        set_prop(position_prop, float(seconds) * 1000.0)
        self._last_frame = None

    def current_frame(self) -> Image | None:
        if self._last_frame is None:
            return None
        return self._last_frame.copy()

    def read(self) -> Image | None:
        self._ensure_open()
        if not self._playing and self._last_frame is not None:
            return self._last_frame.copy()
        frame = self._read_next_frame()
        if frame is None:
            return None
        self._last_frame = frame
        return frame.copy()

    def close(self) -> None:
        if self._closed:
            return
        _release_capture(self._capture)
        self._closed = True
        self._playing = False

    def _read_next_frame(self) -> Image | None:
        read = getattr(self._capture, "read", None)
        if not callable(read):
            raise BackendCapabilityError("Video frame reading is unavailable on this system.")
        ok, frame = cast(tuple[bool, Any], read())
        if not ok or frame is None:
            if self._loop:
                self.seek(0.0)
                ok, frame = cast(tuple[bool, Any], read())
            if not ok or frame is None:
                self._playing = False
                return None
        return _frame_to_image(frame)

    def _get_prop(self, name: str) -> float | int | None:
        get_prop = getattr(self._capture, "get", None)
        prop = getattr(self._cv2, name, None)
        if not callable(get_prop) or prop is None:
            return None
        value = get_prop(prop)
        if value is None:
            return None
        if isinstance(value, int | float):
            return value
        return None

    def _ensure_open(self) -> None:
        if self._closed:
            raise BackendCapabilityError("This video has already been closed.")


class Capture:
    """Camera capture stream with explicit lifecycle and frame reads."""

    def __init__(self, capture: Any, *, device: int | str, cv2_module: Any) -> None:
        self._capture = capture
        self._device = device
        self._cv2 = cv2_module
        self._playing = True
        self._closed = False
        self._last_frame: Image | None = None

    @property
    def device(self) -> int | str:
        return self._device

    @property
    def width(self) -> int:
        return int(self._get_prop("CAP_PROP_FRAME_WIDTH") or 0)

    @property
    def height(self) -> int:
        return int(self._get_prop("CAP_PROP_FRAME_HEIGHT") or 0)

    @property
    def is_playing(self) -> bool:
        return self._playing

    def play(self) -> None:
        self._ensure_open()
        self._playing = True

    def pause(self) -> None:
        self._ensure_open()
        self._playing = False

    def current_frame(self) -> Image | None:
        if self._last_frame is None:
            return None
        return self._last_frame.copy()

    def read(self) -> Image | None:
        self._ensure_open()
        if not self._playing and self._last_frame is not None:
            return self._last_frame.copy()
        read = getattr(self._capture, "read", None)
        if not callable(read):
            raise BackendCapabilityError("Camera frame reading is unavailable on this system.")
        ok, frame = cast(tuple[bool, Any], read())
        if not ok or frame is None:
            return None
        image = _frame_to_image(frame)
        self._last_frame = image
        return image.copy()

    def close(self) -> None:
        if self._closed:
            return
        _release_capture(self._capture)
        self._closed = True
        self._playing = False

    def _get_prop(self, name: str) -> float | int | None:
        get_prop = getattr(self._capture, "get", None)
        prop = getattr(self._cv2, name, None)
        if not callable(get_prop) or prop is None:
            return None
        value = get_prop(prop)
        if value is None:
            return None
        if isinstance(value, int | float):
            return value
        return None

    def _ensure_open(self) -> None:
        if self._closed:
            raise BackendCapabilityError("This capture has already been closed.")


def create_video(path: str | Path) -> Video:
    video_path = Path(path).expanduser()
    if not video_path.exists():
        raise ArgumentValidationError(f"Video file does not exist: {video_path!s}.")
    cv2 = _load_cv2_module()
    capture = cv2.VideoCapture(str(video_path))
    if not _capture_is_open(capture):
        _release_capture(capture)
        raise BackendCapabilityError(f"Could not open video file: {video_path!s}.")
    return Video(capture, path=video_path, cv2_module=cv2)


async def create_video_async(path: str | Path) -> Video:
    return create_video(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture:
    normalized_kind = kind.lower()
    if normalized_kind in _AUDIO_KINDS or normalized_kind in _AUDIO_VIDEO_KINDS:
        raise UnsupportedFeatureError(
            "create_capture microphone input is still deferred in Gummy Snake. "
            "The current staged capture API only supports camera/video capture because "
            "microphone access needs separate permission, device, and buffering work."
        )
    if normalized_kind not in _VIDEO_KINDS:
        raise ArgumentValidationError(
            "create_capture() currently supports only kind='video' or kind='camera'."
        )

    cv2 = _load_cv2_module()
    capture = cv2.VideoCapture(device)
    if not _capture_is_open(capture):
        _release_capture(capture)
        raise BackendCapabilityError(
            "Could not open the requested camera device. This can happen in headless "
            "environments, when no camera is available, or when the OS denies access."
        )
    _set_capture_dimensions(capture, cv2, width=width, height=height)
    return Capture(capture, device=device, cv2_module=cv2)


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture:
    return create_capture(kind, device=device, width=width, height=height)


__all__ = [
    "Video",
    "Capture",
    "create_video",
    "create_video_async",
    "create_capture",
    "create_capture_async",
]
