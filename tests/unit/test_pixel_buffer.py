from __future__ import annotations

from gummysnake.pixels import PixelBuffer
from gummysnake.pixels._buffer import dirty_pixel_region


def test_pixel_buffer_preserves_list_like_slice_and_equality() -> None:
    pixels = PixelBuffer([1, 2, 3, 4, 5, 6])

    assert pixels == [1, 2, 3, 4, 5, 6]
    assert pixels[1:4] == [2, 3, 4]
    assert isinstance(pixels[1:4], list)
    assert pixels != [1, 2, 3]


def test_pixel_buffer_tracks_item_and_slice_dirty_range() -> None:
    pixels = PixelBuffer(bytes(16))

    assert pixels.dirty_range() is None

    pixels[5] = 10
    assert pixels.dirty_range() == (5, 6)

    pixels[8:12] = bytes([1, 2, 3, 4])
    assert pixels.dirty_range() == (5, 12)

    pixels.clear_dirty()
    assert pixels.dirty_range() is None


def test_pixel_buffer_tracks_negative_step_slice_dirty_range() -> None:
    pixels = PixelBuffer(bytes(10))

    pixels[8:2:-2] = bytes([1, 2, 3])

    assert pixels.dirty_range() == (4, 9)


def test_dirty_pixel_region_single_row() -> None:
    region = dirty_pixel_region(4 * 3 * 2, 3, 2, (4, 12))

    assert region.valid
    assert not region.empty
    assert region.byte_slice == slice(4, 12)
    assert (region.x, region.y, region.width, region.height) == (1, 0, 2, 1)


def test_dirty_pixel_region_unaligned_byte_expands_to_full_pixel() -> None:
    region = dirty_pixel_region(4 * 3 * 2, 3, 2, (5, 6))

    assert region.valid
    assert not region.empty
    assert region.byte_slice == slice(4, 8)
    assert (region.x, region.y, region.width, region.height) == (1, 0, 1, 1)


def test_dirty_pixel_region_full_rows_for_multi_row_range() -> None:
    region = dirty_pixel_region(4 * 3 * 3, 3, 3, (12, 36))

    assert region.valid
    assert not region.empty
    assert region.byte_slice == slice(12, 36)
    assert (region.x, region.y, region.width, region.height) == (0, 1, 3, 2)


def test_dirty_pixel_region_partial_multi_row_expands_to_full_rows() -> None:
    region = dirty_pixel_region(4 * 3 * 3, 3, 3, (8, 20))

    assert region.valid
    assert not region.empty
    assert region.byte_slice == slice(0, 24)
    assert (region.x, region.y, region.width, region.height) == (0, 0, 3, 2)


def test_dirty_pixel_region_empty_and_invalid_states() -> None:
    empty = dirty_pixel_region(4 * 3 * 2, 3, 2, (8, 8))
    assert empty.valid
    assert empty.empty

    invalid_length = dirty_pixel_region(4 * 3 * 2 - 1, 3, 2, (0, 4))
    assert not invalid_length.valid
    assert not invalid_length.empty

    invalid_size = dirty_pixel_region(0, 0, 2, (0, 4))
    assert not invalid_size.valid
    assert not invalid_size.empty
