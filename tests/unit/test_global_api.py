import pytest

import p5
from p5.exceptions import ArgumentValidationError


def test_global_mode_explicit_callbacks():
    frames = []

    def setup():
        p5.create_canvas(16, 12)
        p5.background(0)

    def draw():
        frames.append(p5.frame_count())
        p5.fill(255, 0, 0)
        p5.no_stroke()
        p5.circle(8, 6, 6)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=2)

    assert frames == [0, 1]
    assert context.width == 16
    assert context.height == 12
    assert context.frame_count == 2


def test_p5_aliases_delegate_to_pythonic_api():
    def setup():
        p5.createCanvas(10, 10)
        p5.noStroke()
        p5.fill(0, 255, 0)

    def draw():
        p5.rect(1, 1, 8, 8)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()
    assert any(value == 255 for value in pixels)


def test_image_sampling_api_and_aliases():
    def setup():
        p5.createCanvas(4, 4)
        assert p5.image_sampling() == p5.LINEAR
        p5.no_smooth()
        assert p5.image_sampling() == p5.NEAREST
        p5.smooth()
        assert p5.image_sampling() == p5.LINEAR
        p5.imageSampling(p5.NEAREST)
        assert p5.image_sampling() == p5.NEAREST
        p5.smooth()
        with pytest.raises(ArgumentValidationError):
            p5.image_sampling("bogus")

    p5.run(setup=setup, draw=lambda: None, headless=True, max_frames=0)
