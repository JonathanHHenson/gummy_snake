"""Deferred animated-image APIs."""

from __future__ import annotations

from gummysnake.exceptions import UnsupportedFeatureError


class ImageDeferredMixin:
    """Public ImageDeferredMixin value for Gummy Snake image features."""
    def blend(self, *_args: object) -> None:
        """Blend for this ImageDeferredMixin.
        
        Args:
            *_args: Additional positional arguments. Expected type: `object`.
        
        Returns:
            None.
        """
        raise UnsupportedFeatureError(
            "Image.blend() is deferred. Use canvas-level blend(...) for Rust-backed region "
            "blending until image-local blend modes are implemented."
        )

    def delay(self, *_args: object) -> None:
        """Delay for this ImageDeferredMixin.
        
        Args:
            *_args: Additional positional arguments. Expected type: `object`.
        
        Returns:
            None.
        """
        raise UnsupportedFeatureError(
            "Animated image frame delay controls are deferred because Gummy Snake currently loads "
            "images as single RGBA frames through the Rust canvas runtime."
        )

    def get_current_frame(self) -> int:
        """Return the current current frame value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )

    def num_frames(self) -> int:
        """Num frames for this ImageDeferredMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return 1

    def play(self) -> None:
        """Start playback for this object.
        
        Args:
            None.
        
        Returns:
            None.
        """
        raise UnsupportedFeatureError(
            "Animated image playback is deferred because Gummy Snake currently loads images as "
            "single RGBA frames through the Rust canvas runtime."
        )

    def pause(self) -> None:
        """Pause playback for this object.
        
        Args:
            None.
        
        Returns:
            None.
        """
        raise UnsupportedFeatureError(
            "Animated image playback is deferred because Gummy Snake currently loads images as "
            "single RGBA frames through the Rust canvas runtime."
        )

    def reset(self) -> None:
        """Reset for this ImageDeferredMixin.
        
        Args:
            None.
        
        Returns:
            None.
        """
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )

    def set_frame(self, frame: int) -> None:
        """Set the frame value.
        
        Args:
            frame: The frame value. Expected type: `int`.
        
        Returns:
            None.
        """
        if int(frame) == 0:
            return None
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )


__all__ = ["ImageDeferredMixin"]
