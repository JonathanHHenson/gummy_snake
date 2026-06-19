import pytest

import p5
from p5 import UnsupportedFeatureError


def test_font_outline_helpers_are_explicitly_deferred() -> None:
    font = p5.Font(name="default")

    with pytest.raises(UnsupportedFeatureError, match="text_to_points"):
        font.text_to_points("p5", 0, 0)
    with pytest.raises(UnsupportedFeatureError, match="text_to_paths"):
        font.text_to_paths("p5", 0, 0)
    with pytest.raises(UnsupportedFeatureError, match="text_to_contours"):
        font.text_to_contours("p5", 0, 0)
    with pytest.raises(UnsupportedFeatureError, match="text_to_model"):
        font.text_to_model("p5", 0, 0)
