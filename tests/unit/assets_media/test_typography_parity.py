import pytest

import gummysnake as gs
from gummysnake import UnsupportedFeatureError


def test_font_outline_helpers_are_explicitly_deferred() -> None:
    font = gs.Font(name="default")

    with pytest.raises(UnsupportedFeatureError, match="text_to_points"):
        font.text_to_points("gs", 0, 0)
    with pytest.raises(UnsupportedFeatureError, match="text_to_paths"):
        font.text_to_paths("gs", 0, 0)
    with pytest.raises(UnsupportedFeatureError, match="text_to_contours"):
        font.text_to_contours("gs", 0, 0)
    with pytest.raises(UnsupportedFeatureError, match="text_to_model"):
        font.text_to_model("gs", 0, 0)
