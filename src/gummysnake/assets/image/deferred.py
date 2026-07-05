"""Deferred animated-image APIs."""

from __future__ import annotations

from typing import NoReturn

from gummysnake.exceptions import UnsupportedFeatureError

_SINGLE_FRAME_REASON = (
    "because Gummy Snake currently loads images as single RGBA frames through the Rust "
    "canvas runtime."
)
_FRAME_CONTROLS_DEFERRED = f"Animated image frame controls are deferred {_SINGLE_FRAME_REASON}"
_PLAYBACK_DEFERRED = f"Animated image playback is deferred {_SINGLE_FRAME_REASON}"
_DELAY_DEFERRED = f"Animated image frame delay controls are deferred {_SINGLE_FRAME_REASON}"


def _raise_deferred(message: str) -> NoReturn:
    raise UnsupportedFeatureError(message)


class ImageDeferredMixin:
    """Deferred animated-image API methods kept for compatibility."""

    def blend(self, *_args: object) -> None:
        """Deferred image-local blend operation."""
        _raise_deferred(
            "Image.blend() is deferred. Use canvas-level blend(...) for Rust-backed region "
            "blending until image-local blend modes are implemented."
        )

    def delay(self, *_args: object) -> None:
        """Deferred animated-image frame delay controls."""
        _raise_deferred(_DELAY_DEFERRED)

    def get_current_frame(self) -> int:
        """Deferred animated-image current frame lookup."""
        _raise_deferred(_FRAME_CONTROLS_DEFERRED)

    def num_frames(self) -> int:
        """Return the current single-frame image count."""
        return 1

    def play(self) -> None:
        """Deferred animated-image playback."""
        _raise_deferred(_PLAYBACK_DEFERRED)

    def pause(self) -> None:
        """Deferred animated-image playback pause."""
        _raise_deferred(_PLAYBACK_DEFERRED)

    def reset(self) -> None:
        """Deferred animated-image frame reset."""
        _raise_deferred(_FRAME_CONTROLS_DEFERRED)

    def set_frame(self, frame: int) -> None:
        """Select frame 0 for current single-frame images; other frames are deferred."""
        if int(frame) == 0:
            return None
        _raise_deferred(_FRAME_CONTROLS_DEFERRED)


__all__ = ["ImageDeferredMixin"]
