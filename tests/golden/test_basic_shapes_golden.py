import hashlib

import p5


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

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)
    return bytes(context.load_pixels())


def test_canvas_basic_shapes_golden_hash():
    digest = hashlib.sha256(_render_reference_pixels()).hexdigest()
    assert digest == "8163600793b1e8e5f317a6c9d9343d5bf8ff73d3d9e30728637b88740b8602c8"
