from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest

import gummysnake as gs
from gummysnake import BackendCapabilityError
from gummysnake.assets.media import frame as media_frame_module
from gummysnake.assets.media import streams as media_streams_module

_ONE_PIXEL_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def test_create_video_uses_rust_gif_lifecycle_and_stable_image_identity(tmp_path: Path) -> None:
    video_path = tmp_path / "clip.gif"
    video_path.write_bytes(_ONE_PIXEL_GIF)

    clip = gs.create_video(video_path)
    assert clip.path == video_path
    assert clip.width == 1
    assert clip.height == 1
    assert clip.frame_count == 1
    assert clip.duration > 0
    assert clip.fps > 0
    assert clip.speed() == 1.0
    assert clip.speed(1.25) == 1.25

    first = clip.read()
    assert first is not None
    first_key = first.cache_key
    first_version = first.version
    assert clip.current_frame() is first
    assert clip.read() is first

    clip.play()
    assert clip.read() is None
    clip.loop()
    looped = clip.read()
    assert looped is first
    assert looped.cache_key == first_key
    assert looped.version > first_version
    assert clip.diagnostics()["decoder"] == "rust-image-gif"

    clip.stop()
    assert clip.time() == 0.0
    clip.close()
    with pytest.raises(RuntimeError, match="closed"):
        clip.read()


def test_non_gif_video_fails_without_decoder_fallback(tmp_path: Path) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"not a video")

    with pytest.raises(BackendCapabilityError, match="GIF video files only"):
        gs.create_video(video_path)


def test_assets_package_exports_async_media_helpers() -> None:
    import gummysnake.assets as assets

    assert assets.create_video_async is media_streams_module.create_video_async
    assert assets.create_capture_async is media_streams_module.create_capture_async
    assert assets.MediaFrameSink is media_frame_module.MediaFrameSink


def test_video_capture_fails_closed_without_rust_camera_capability() -> None:
    with pytest.raises(BackendCapabilityError, match="Rust-native camera capture"):
        gs.create_capture("video", device=2, width=640, height=480)
    with pytest.raises(BackendCapabilityError, match="No OpenCV"):
        gs.create_capture("audio+video")


def test_create_capture_audio_input_starts_headless_safe_stream() -> None:
    audio = gs.create_capture("audio")

    assert isinstance(audio, gs.AudioInput)
    assert audio.is_started is True
    audio.push_samples([0.25, -0.25])
    assert audio.read().samples == (0.25, -0.25)


@pytest.mark.parametrize(
    ("array", "expected"),
    [
        (np.array([[7, 9]], dtype=np.uint8), bytes([7, 7, 7, 255, 9, 9, 9, 255])),
        (np.array([[[1, 2, 3]]], dtype=np.uint8), bytes([3, 2, 1, 255])),
        (np.array([[[1, 2, 3, 4]]], dtype=np.uint8), bytes([3, 2, 1, 4])),
    ],
)
def test_media_frame_sink_borrows_contiguous_buffers_and_reuses_image(
    array: np.ndarray, expected: bytes
) -> None:
    sink = gs.MediaFrameSink(int(array.shape[1]), int(array.shape[0]))

    image = sink.update(array)
    key = image.cache_key
    version = image.version
    same_image = sink.update(array)

    assert image.to_rgba_bytes() == expected
    assert same_image is image
    assert same_image.cache_key == key
    assert same_image.version == version + 1
    assert sink.diagnostics()["frames_written"] == 2


def test_media_frame_sink_rejects_non_contiguous_source() -> None:
    source = np.zeros((2, 4, 3), dtype=np.uint8)[:, ::2, :]
    sink = gs.MediaFrameSink(2, 2)

    with pytest.raises(BackendCapabilityError, match="C-contiguous"):
        sink.update(source)
