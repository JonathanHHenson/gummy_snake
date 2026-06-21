from __future__ import annotations

from pathlib import Path
from typing import cast

from rust_canvas_modules import FakeCanvasModule, FakeRustImage

from gummysnake import Image
from gummysnake import constants as c
from gummysnake.assets.image import CanvasImage
from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def test_canvas_renderer_pixels_and_save_round_trip(tmp_path: Path) -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(2, 1)

    renderer.background(Color(10, 20, 30, 255))
    assert renderer.load_pixels() == [10, 20, 30, 255, 10, 20, 30, 255]

    renderer.update_pixels([255, 0, 0, 255, 0, 0, 255, 255])
    assert renderer.load_pixels() == [255, 0, 0, 255, 0, 0, 255, 255]
    assert renderer.load_pixel_bytes() == bytes([255, 0, 0, 255, 0, 0, 255, 255])

    output = tmp_path / "canvas.png"
    renderer.save(output)
    assert output.read_bytes() == b"fake-png"


def test_canvas_renderer_bridges_images_and_blend_regions() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    image = Image(2, 1, bytes([255, 0, 0, 255, 255, 0, 0, 255]))
    style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()

    renderer.draw_image(image, 1, 0, 2, 1, style, transform, source=(0, 0, 1, 1))
    renderer.blend_region(image, (0, 0, 1, 1), (0, 1, 1, 1), c.ADD)
    renderer.blend_region(None, (0, 0, 1, 1), (1, 1, 1, 1), c.BLEND)

    canvas = renderer._canvas
    assert canvas is not None
    assert canvas.calls[-3][0] == "draw_canvas_image"
    assert canvas.calls[-3][1] is image.rust_image._rust_image
    assert canvas.calls[-3][-1] == (0, 0, 1, 1)
    assert canvas.calls[-2] == (
        "blend_region",
        image.to_rgba_bytes(),
        2,
        1,
        (0, 0, 1, 1),
        (0, 1, 1, 1),
        c.ADD,
    )
    assert canvas.calls[-1] == (
        "blend_region",
        None,
        None,
        None,
        (0, 0, 1, 1),
        (1, 1, 1, 1),
        c.BLEND,
    )


def test_canvas_renderer_passes_image_tint_in_style_payload() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    image = Image(1, 1, bytes([255, 255, 255, 255]))
    style = StyleState(fill_color=None, stroke_color=None)
    style.image_tint = Color(128, 64, 255, 127)

    renderer.draw_image(image, 0, 0, 1, 1, style, Matrix2D.identity())

    canvas = renderer._canvas
    assert canvas is not None
    call = canvas.calls[-1]
    assert call[0] == "draw_canvas_image"
    assert call[-3]["image_tint"] == (128, 64, 255, 127)


def test_canvas_renderer_bridges_complex_polygon_and_clip_stack() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)
    matrix = Matrix2D.identity()

    renderer.complex_polygon(
        [(0, 0), (7, 0), (7, 7), (0, 7)],
        [[(2, 2), (5, 2), (5, 5), (2, 5)]],
        style,
        matrix,
    )
    renderer.begin_clip([(0, 0), (4, 0), (4, 4)], [], matrix)
    assert renderer.clip_depth() == 1
    renderer.restore_clip_depth(0)

    canvas = renderer._canvas
    assert canvas is not None
    assert [call[0] for call in canvas.calls[-3:]] == [
        "complex_polygon",
        "begin_clip",
        "end_clip",
    ]


def test_canvas_renderer_uses_stable_image_cache_keys_and_versions() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()
    first = Image(1, 1, bytes([255, 0, 0, 255]))
    second = Image(1, 1, bytes([0, 255, 0, 255]))

    renderer.draw_image(first, 0, 0, 1, 1, style, transform)
    renderer.draw_image(second, 1, 0, 1, 1, style, transform)
    first.update_pixels(bytes([0, 0, 255, 255]))
    renderer.draw_image(first, 2, 0, 1, 1, style, transform)

    canvas = renderer._canvas
    assert canvas is not None
    draw_calls = [call for call in canvas.calls if call[0] == "draw_canvas_image"]
    assert draw_calls[0][1] is first.rust_image._rust_image
    assert draw_calls[1][1] is second.rust_image._rust_image
    assert draw_calls[2][1] is first.rust_image._rust_image
    assert first.cache_key != second.cache_key


def test_canvas_renderer_uses_rust_managed_image_after_mutation() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()
    image = Image.from_rust_image(CanvasImage(FakeRustImage()))

    renderer.draw_image(image, 0, 0, 2, 1, style, transform)
    image.set(0, 0, (0, 0, 255, 255))
    renderer.draw_image(image, 0, 1, 2, 1, style, transform)

    canvas = renderer._canvas
    assert canvas is not None
    assert [call[0] for call in canvas.calls][-2:] == ["draw_canvas_image", "draw_canvas_image"]


def test_canvas_renderer_performance_counters_cover_representative_paths() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=Color(0, 0, 0, 255))
    image = Image(1, 1, bytes([255, 0, 0, 255]))
    transform = Matrix2D.identity()

    renderer.background(Color(0, 0, 0, 255))
    renderer.line(0, 0, 3, 1, style, transform)
    renderer.end_frame()
    renderer.draw_image(image, 0, 0, 1, 1, style, transform)
    renderer.draw_image(image, 1, 0, 1, 1, style, transform)
    renderer.text_width("cached", style)
    renderer.text_width("cached", style)
    renderer.load_pixels()
    renderer.update_pixels(bytes([0, 0, 0, 255] * 8))
    renderer.blend_region(None, (0, 0, 1, 1), (1, 0, 1, 1), c.BLEND)

    counters = cast(dict[str, int], renderer.performance_counters())

    assert counters["gpu_draws"] >= 4
    assert counters["image_cache_misses"] == 0
    assert counters["image_cache_hits"] == 0
    assert counters["texture_uploads"] == 0
    assert counters["texture_cache_hits"] == 0
    assert counters["text_cache_misses"] == 1
    assert counters["text_cache_hits"] == 1
    assert counters["text_cache_evictions"] == 0
    assert counters["pixel_readbacks"] >= 1
    assert counters["pixel_uploads"] >= 2
    assert counters["cpu_fallbacks"] >= 1
    assert counters["bridge_calls"] > 0

    renderer.reset_performance_counters()
    reset = renderer.performance_counters()
    assert reset["gpu_draws"] == 0
    assert reset["bridge_calls"] == 0
    assert reset["text_cache_evictions"] == 0
