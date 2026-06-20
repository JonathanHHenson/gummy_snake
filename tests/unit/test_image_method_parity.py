import pytest

import p5
from p5 import ArgumentValidationError, UnsupportedFeatureError


def test_image_pixel_helpers_round_trip_and_track_version() -> None:
    image = p5.create_image(2, 1)
    assert image.load_pixels() == [0, 0, 0, 0, 0, 0, 0, 0]
    assert image.pixel_density() == 1.0
    assert isinstance(image.cache_key, int)

    initial_version = image.version
    image.update_pixels(bytes([255, 0, 0, 255, 0, 0, 255, 255]))

    assert image.pixels == [255, 0, 0, 255, 0, 0, 255, 255]
    assert image.get(0, 0) == p5.Color(255, 0, 0, 255)
    assert image.version == initial_version + 1
    assert image.rust_image is None


def test_image_cache_keys_are_stable_and_unique() -> None:
    first = p5.create_image(1, 1)
    second = p5.create_image(1, 1)
    key = first.cache_key

    first.update_pixels(memoryview(bytes([1, 2, 3, 4])))

    assert first.cache_key == key
    assert first.cache_key != second.cache_key
    assert first.load_pixels() == [1, 2, 3, 4]


def test_image_update_pixels_validates_buffer_length() -> None:
    image = p5.create_image(2, 1)

    with pytest.raises(ArgumentValidationError, match="must contain 8 bytes"):
        image.update_pixels([1, 2, 3])
    with pytest.raises(ArgumentValidationError, match="between 0 and 255"):
        image.update_pixels([999] * 8)


def test_image_region_copy_validates_empty_regions() -> None:
    image = p5.create_image(2, 2)

    with pytest.raises(ArgumentValidationError, match="region dimensions"):
        image.get(0, 0, 0, 1)


def test_image_deferred_methods_raise_package_specific_errors() -> None:
    image = p5.create_image(1, 1)

    with pytest.raises(UnsupportedFeatureError, match="Image.blend"):
        image.blend(0, 0, 1, 1, 0, 0, 1, 1, p5.BLEND)
    with pytest.raises(UnsupportedFeatureError, match="pixel_density"):
        image.pixel_density(2)
    with pytest.raises(UnsupportedFeatureError, match="Animated image"):
        image.delay(100)
    with pytest.raises(UnsupportedFeatureError, match="Animated image"):
        image.play()
    with pytest.raises(UnsupportedFeatureError, match="Animated image"):
        image.pause()
    with pytest.raises(UnsupportedFeatureError, match="Animated image"):
        image.reset()
    with pytest.raises(UnsupportedFeatureError, match="Animated image"):
        image.get_current_frame()
    with pytest.raises(UnsupportedFeatureError, match="Animated image"):
        image.set_frame(1)

    image.set_frame(0)
    assert image.num_frames() == 1
