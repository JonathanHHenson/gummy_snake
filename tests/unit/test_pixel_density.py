from pathlib import Path

import pytest

import gummysnake as gs
from gummysnake.exceptions import ArgumentValidationError


def test_global_pixel_density_controls_backing_buffer(tmp_path: Path):
    output = tmp_path / "density.png"

    def setup():
        gs.create_canvas(10, 8, pixel_density=2)
        assert gs.width() == 10
        assert gs.height() == 8
        assert gs.pixel_density() == 2
        assert gs.display_density() == 1

    def draw():
        gs.background(255)
        gs.save_canvas(str(output))

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    assert context.state.canvas.physical_width == 20
    assert context.state.canvas.physical_height == 16
    assert len(context.load_pixels()) == 20 * 16 * 4
    assert output.exists()


def test_pixel_density_api_and_validation():
    def setup():
        gs.create_canvas(10, 10)
        assert gs.pixel_density() == 1
        gs.pixel_density(2)
        assert gs.pixel_density() == 2
        assert gs.display_density() == 1
        with pytest.raises(ArgumentValidationError):
            gs.pixel_density(0)

    gs.run(setup=setup, draw=lambda: None, headless=True, max_frames=0)
