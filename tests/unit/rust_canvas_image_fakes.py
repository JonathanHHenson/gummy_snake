from __future__ import annotations


class FakeCanvasImageKernelsMixin:
    def image_resize_rgba(
        self, width: int, height: int, pixels: bytes, target_width: int, target_height: int
    ) -> bytes:
        return bytes(pixels[:4] * (target_width * target_height))

    def image_crop_rgba(
        self, width: int, height: int, pixels: bytes, sx: int, sy: int, sw: int, sh: int
    ) -> bytes:
        return bytes(sw * sh * 4)

    def image_alpha_composite_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        source_width: int,
        source_height: int,
        source_pixels: bytes,
        dx: int,
        dy: int,
    ) -> bytes:
        return pixels

    def image_mask_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        mask_width: int,
        mask_height: int,
        mask_pixels: bytes,
    ) -> bytes:
        return pixels

    def image_filter_rgba(
        self, width: int, height: int, pixels: bytes, mode: str, value: float | None = None
    ) -> bytes:
        return pixels

    def media_frame_to_rgba(self, width: int, height: int, channels: int, pixels: bytes) -> bytes:
        return bytes(width * height * 4)
