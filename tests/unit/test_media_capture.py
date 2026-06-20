from pathlib import Path

import pytest

import gummysnake as gs
from gummysnake import BackendCapabilityError, UnsupportedFeatureError
from gummysnake.assets import media as media_module
from gummysnake.assets.image import create_image


class _FakeVideoCapture:
    def __init__(
        self, source, *, opened: bool = True, frames: list[tuple[bool, object | None]] | None = None
    ):
        self.source = source
        self._opened = opened
        self._frames = list(frames or [])
        self.released = False
        self.set_calls: list[tuple[int, float]] = []
        self.props = {
            1: 320.0,
            2: 240.0,
            3: 10.0,
            4: 25.0,
            5: 0.0,
        }

    def isOpened(self) -> bool:
        return self._opened

    def read(self):
        if self._frames:
            return self._frames.pop(0)
        return False, None

    def release(self) -> None:
        self.released = True

    def get(self, prop: int):
        return self.props.get(prop, 0.0)

    def set(self, prop: int, value: float) -> None:
        self.set_calls.append((prop, value))
        self.props[prop] = value


class _FakeCV2:
    CAP_PROP_FRAME_WIDTH = 1
    CAP_PROP_FRAME_HEIGHT = 2
    CAP_PROP_FPS = 3
    CAP_PROP_FRAME_COUNT = 4
    CAP_PROP_POS_MSEC = 5

    def __init__(self, captures: list[_FakeVideoCapture]) -> None:
        self._captures = captures
        self.calls: list[object] = []

    def VideoCapture(self, source):
        self.calls.append(source)
        return self._captures.pop(0)


class _FakeFrame:
    def __init__(self, shape: tuple[int, ...], payload: bytes) -> None:
        self.shape = shape
        self._payload = payload

    def tobytes(self) -> bytes:
        return self._payload


def test_create_video_wraps_optional_opencv_capture(monkeypatch, tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")

    fake_capture = _FakeVideoCapture(
        str(video_path),
        frames=[(True, object()), (False, None), (True, object())],
    )
    fake_cv2 = _FakeCV2([fake_capture])

    monkeypatch.setattr(media_module, "_load_cv2_module", lambda: fake_cv2)
    monkeypatch.setattr(media_module, "_frame_to_image", lambda _frame: create_image(2, 3))

    clip = gs.create_video(video_path)
    assert clip.width == 320
    assert clip.height == 240
    assert clip.fps == 10.0
    assert clip.frame_count == 25
    assert clip.duration == 2.5

    clip.play()
    frame = clip.read()
    assert frame is not None
    assert frame.width == 2
    assert frame.height == 3

    clip.pause()
    cached = clip.read()
    assert cached is not None
    assert cached.width == 2

    clip.looping(True)
    clip.play()
    looped = clip.read()
    assert looped is not None
    assert fake_capture.set_calls[-1] == (_FakeCV2.CAP_PROP_POS_MSEC, 0.0)

    clip.stop()
    assert fake_capture.set_calls[-1] == (_FakeCV2.CAP_PROP_POS_MSEC, 0.0)

    clip.close()
    assert fake_capture.released is True


def test_create_capture_wraps_camera_with_explicit_lifecycle(monkeypatch):
    fake_capture = _FakeVideoCapture(0, frames=[(True, object())])
    fake_cv2 = _FakeCV2([fake_capture])

    monkeypatch.setattr(media_module, "_load_cv2_module", lambda: fake_cv2)
    monkeypatch.setattr(media_module, "_frame_to_image", lambda _frame: create_image(4, 5))

    camera = gs.create_capture("video", device=2, width=640, height=480)
    frame = camera.read()

    assert frame is not None
    assert frame.width == 4
    assert frame.height == 5
    assert fake_cv2.calls == [2]
    assert (_FakeCV2.CAP_PROP_FRAME_WIDTH, 640) in fake_capture.set_calls
    assert (_FakeCV2.CAP_PROP_FRAME_HEIGHT, 480) in fake_capture.set_calls

    camera.pause()
    cached = camera.read()
    assert cached is not None
    assert cached.width == 4

    camera.close()
    assert fake_capture.released is True


def test_create_capture_audio_input_remains_explicitly_deferred():
    with pytest.raises(UnsupportedFeatureError, match="microphone input is still deferred"):
        gs.create_capture("audio")


def test_media_apis_fail_predictably_without_optional_dependency(monkeypatch, tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")

    def missing_cv2():
        raise BackendCapabilityError("Video playback/capture requires the optional media extra.")

    monkeypatch.setattr(media_module, "_load_cv2_module", missing_cv2)

    with pytest.raises(BackendCapabilityError, match="optional media extra"):
        gs.create_video(video_path)
    with pytest.raises(BackendCapabilityError, match="optional media extra"):
        gs.create_capture("video")


@pytest.mark.parametrize(
    ("shape", "payload", "expected"),
    [
        ((1, 2), bytes([7, 9]), bytes([7, 7, 7, 255, 9, 9, 9, 255])),
        ((1, 1, 3), bytes([1, 2, 3]), bytes([3, 2, 1, 255])),
        ((1, 1, 4), bytes([1, 2, 3, 4]), bytes([3, 2, 1, 4])),
    ],
)
def test_media_frame_conversion_uses_rust_rgba_kernel(
    shape: tuple[int, ...], payload: bytes, expected: bytes
) -> None:
    image = media_module._frame_to_image(_FakeFrame(shape, payload))

    assert image.to_rgba_bytes() == expected
