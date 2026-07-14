import pytest

import gummysnake as gs
from gummysnake import ArgumentValidationError, UnsupportedFeatureError


def test_image_pixel_helpers_round_trip_and_track_version() -> None:
    image = gs.create_image(2, 1)
    assert image.load_pixels() == [0, 0, 0, 0, 0, 0, 0, 0]
    assert image.pixel_density() == 1.0
    assert isinstance(image.cache_key, int)

    initial_version = image.version
    image.update_pixels(bytes([255, 0, 0, 255, 0, 0, 255, 255]))

    assert image.pixels == [255, 0, 0, 255, 0, 0, 255, 255]
    assert image.get(0, 0) == gs.Color(255, 0, 0, 255)
    assert image.version == initial_version + 1
    assert isinstance(image.rust_image, gs.CanvasImage)


def test_image_cache_keys_are_stable_and_unique() -> None:
    first = gs.create_image(1, 1)
    second = gs.create_image(1, 1)
    key = first.cache_key

    first.update_pixels(memoryview(bytes([1, 2, 3, 4])))

    assert first.cache_key == key
    assert first.cache_key != second.cache_key
    assert first.load_pixels() == [1, 2, 3, 4]


def test_image_update_pixels_validates_buffer_length() -> None:
    image = gs.create_image(2, 1)

    with pytest.raises(ArgumentValidationError, match="must contain 8 bytes"):
        image.update_pixels([1, 2, 3])
    with pytest.raises(ArgumentValidationError, match="between 0 and 255"):
        image.update_pixels([999] * 8)


def test_image_region_copy_validates_empty_regions() -> None:
    image = gs.create_image(2, 2)

    with pytest.raises(ArgumentValidationError, match="region dimensions"):
        image.get(0, 0, 0, 1)


def test_image_local_operations_delegate_to_rust_and_preserve_semantics() -> None:
    image = gs.Image(
        2,
        2,
        bytes(
            [
                10,
                20,
                30,
                255,
                100,
                0,
                0,
                128,
                0,
                90,
                0,
                255,
                0,
                0,
                200,
                64,
            ]
        ),
    )

    cropped = image.get(-1, 0, 2, 2)
    assert isinstance(cropped, gs.Image)
    assert cropped.to_rgba_bytes() == bytes(
        [
            0,
            0,
            0,
            0,
            10,
            20,
            30,
            255,
            0,
            0,
            0,
            0,
            0,
            90,
            0,
            255,
        ]
    )

    resized = image.copy()
    resized.resize(1, 1)
    assert resized.to_rgba_bytes() == bytes([10, 20, 30, 255])

    filtered = image.copy()
    filtered.filter(gs.INVERT)
    assert filtered.to_rgba_bytes()[:8] == bytes([245, 235, 225, 255, 155, 255, 255, 128])

    mask = gs.Image(2, 2, bytes([255, 255, 255, 255, 0, 0, 0, 255] * 2))
    masked = image.copy()
    masked.mask(mask)
    assert masked.to_rgba_bytes()[3::4] == bytes([255, 0, 255, 0])

    target = gs.Image(1, 1, bytes([0, 0, 0, 255]))
    target.set(0, 0, gs.Image(1, 1, bytes([100, 0, 0, 128])))
    assert target.to_rgba_bytes() == bytes([50, 0, 0, 255])


def test_image_local_filters_match_declared_modes_and_preserve_alpha() -> None:
    blur = gs.Image(3, 3, bytes([0, 0, 0, 255] * 9))
    blur.set(1, 1, (255, 90, 0, 255))
    blur.filter(gs.BLUR)
    assert blur.get(1, 1).to_tuple() == (28, 10, 0, 255)

    posterized = gs.Image(1, 1, bytes([128, 64, 1, 37]))
    posterized.filter(gs.POSTERIZE)
    assert posterized.get(0, 0).to_tuple() == (170, 85, 0, 37)

    source = gs.Image(3, 3, bytes([10, 10, 10, 37] * 9))
    source.set(1, 1, (250, 200, 150, 91))
    eroded = source.copy()
    eroded.filter(gs.ERODE)
    dilated = source.copy()
    dilated.filter(gs.DILATE)
    assert eroded.get(1, 1).to_tuple() == (10, 10, 10, 91)
    assert dilated.get(0, 0).to_tuple() == (250, 200, 150, 37)


def test_image_save_uses_png_or_rejects_an_unsupported_suffix(tmp_path) -> None:
    image = gs.create_image(1, 1)

    suffixless_path = tmp_path / "image"
    image.save(suffixless_path)

    output = tmp_path / "image.png"
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ArgumentValidationError, match="only PNG output"):
        image.save(tmp_path / "image.webp")
    with pytest.raises(ArgumentValidationError, match="only PNG output"):
        image.rust_image.save(tmp_path / "image.jpg")


def test_image_pixel_density_setter_is_not_supported() -> None:
    image = gs.create_image(1, 1)

    with pytest.raises(UnsupportedFeatureError, match="pixel_density"):
        image.pixel_density(2)
