from __future__ import annotations

from gummysnake.core.color import Color
from gummysnake.core.state import StyleState


def test_style_state_exposes_lazy_packed_rgba_fields() -> None:
    style = StyleState(fill_color=Color(1, 2, 3, 4), stroke_color=Color(5, 6, 7, 8))

    assert style.fill_rgba == (1, 2, 3, 4)
    assert style.stroke_rgba == (5, 6, 7, 8)
    assert style.image_tint_rgba is None

    style.fill_color = Color(9, 10, 11, 12)
    style.stroke_color = None
    style.image_tint = Color(13, 14, 15, 16)

    assert style.fill_rgba == (9, 10, 11, 12)
    assert style.stroke_rgba is None
    assert style.image_tint_rgba == (13, 14, 15, 16)


def test_style_state_mark_changed_refreshes_packed_rgba_fields() -> None:
    style = StyleState()
    style.fill_color = Color(20, 21, 22, 23)
    style.stroke_color = None
    style.image_tint = Color(24, 25, 26, 27)

    style.mark_changed()

    assert style.revision == 1
    assert style.fill_rgba == (20, 21, 22, 23)
    assert style.stroke_rgba is None
    assert style.image_tint_rgba == (24, 25, 26, 27)


def test_style_state_copy_preserves_public_color_and_packed_rgba() -> None:
    style = StyleState(
        fill_color=Color(31, 32, 33, 34),
        stroke_color=None,
        image_tint=Color(35, 36, 37, 38),
    )

    copied = style.copy()

    assert copied.fill_color == Color(31, 32, 33, 34)
    assert copied.stroke_color is None
    assert copied.image_tint == Color(35, 36, 37, 38)
    assert copied.fill_rgba == (31, 32, 33, 34)
    assert copied.stroke_rgba is None
    assert copied.image_tint_rgba == (35, 36, 37, 38)
