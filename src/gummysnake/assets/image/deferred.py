"""Deferred animated-image APIs."""

from __future__ import annotations

from gummysnake.exceptions import UnsupportedFeatureError


class ImageDeferredMixin:
    def blend(self, *_args: object) -> None:
        raise UnsupportedFeatureError(
            "Image.blend() is deferred. Use canvas-level blend(...) for Rust-backed region "
            "blending until image-local blend modes are implemented."
        )

    def delay(self, *_args: object) -> None:
        raise UnsupportedFeatureError(
            "Animated image frame delay controls are deferred because Gummy Snake currently loads "
            "images as single RGBA frames through the Rust canvas runtime."
        )

    def get_current_frame(self) -> int:
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )

    def num_frames(self) -> int:
        return 1

    def play(self) -> None:
        raise UnsupportedFeatureError(
            "Animated image playback is deferred because Gummy Snake currently loads images as "
            "single RGBA frames through the Rust canvas runtime."
        )

    def pause(self) -> None:
        raise UnsupportedFeatureError(
            "Animated image playback is deferred because Gummy Snake currently loads images as "
            "single RGBA frames through the Rust canvas runtime."
        )

    def reset(self) -> None:
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )

    def set_frame(self, frame: int) -> None:
        if int(frame) == 0:
            return None
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )


__all__ = ["ImageDeferredMixin"]
