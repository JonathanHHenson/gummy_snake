from pathlib import Path

import pytest

import p5
from p5.exceptions import ArgumentValidationError


def test_global_pixel_density_controls_backing_buffer(tmp_path: Path):
    output = tmp_path / "density.png"

    def setup():
        p5.create_canvas(10, 8, pixel_density=2)
        assert p5.width() == 10
        assert p5.height() == 8
        assert p5.pixel_density() == 2
        assert p5.display_density() == 1

    def draw():
        p5.background(255)
        p5.save_canvas(str(output))

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

    assert context.state.canvas.physical_width == 20
    assert context.state.canvas.physical_height == 16
    assert len(context.load_pixels()) == 20 * 16 * 4
    assert output.exists()


def test_pixel_density_alias_and_validation():
    def setup():
        p5.createCanvas(10, 10)
        assert p5.pixelDensity() == 1
        p5.pixelDensity(2)
        assert p5.pixel_density() == 2
        assert p5.displayDensity() == 1
        with pytest.raises(ArgumentValidationError):
            p5.pixel_density(0)

    p5.run(setup=setup, draw=lambda: None, headless=True, max_frames=0)
