"""Ordered image-batch helpers for :class:`FastDrawScope`."""

from __future__ import annotations

from typing import Any

from gummysnake.assets.image import CanvasImage, Image


def queue_fast_image(
    scope: Any, image: Image | CanvasImage, dx: float, dy: float, dw: float, dh: float
) -> None:
    """Append a normalized fast-scope image without repeating renderer state work."""
    context = scope._context
    renderer = context.renderer
    queue_image = getattr(renderer, "_queue_fast_rust_image", None)
    if not callable(queue_image):
        renderer.draw_image(
            image,
            dx,
            dy,
            dw,
            dh,
            context.state.style,
            context.state.transform.matrix,
            source=None,
        )
        return
    style = context.state.style
    if scope._image_style_revision != style.revision:
        scope._image_style_revision = style.revision
        scope._image_style_payload = renderer._style_payload(style)
    transform = context.state.transform.matrix
    if scope._image_matrix is not transform:
        scope._image_matrix = transform
        scope._image_matrix_payload = renderer._matrix_payload(transform)
    assert scope._image_style_payload is not None
    assert scope._image_matrix_payload is not None
    rust_image = (
        image._rust_image if isinstance(image, CanvasImage) else image.rust_image._rust_image
    )
    queue_image(
        rust_image,
        dx,
        dy,
        dw,
        dh,
        scope._image_style_payload,
        scope._image_matrix_payload,
    )
