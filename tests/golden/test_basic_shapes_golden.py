import hashlib

import p5_py as p5


def _render_reference_pixels() -> bytes:
    def setup() -> None:
        p5.create_canvas(16, 12)
        p5.no_stroke()

    def draw() -> None:
        p5.background(240)
        p5.fill(255, 0, 0)
        p5.rect(1, 1, 6, 4)
        p5.fill(0, 0, 255)
        p5.circle(11, 7, 4)

    context = p5.run(setup=setup, draw=draw, backend="headless", max_frames=1)
    return bytes(context.load_pixels())


def test_headless_basic_shapes_golden_hash():
    digest = hashlib.sha256(_render_reference_pixels()).hexdigest()
    assert digest == "09d3632ba4e6d4fd8df9a0f7a4f51ef8d09b8fb7414ac8d994b2a66e27c92b23"
