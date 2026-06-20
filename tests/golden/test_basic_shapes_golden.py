import hashlib

import gummysnake as gs


def _render_reference_pixels() -> bytes:
    def setup() -> None:
        gs.create_canvas(16, 12)
        gs.no_stroke()

    def draw() -> None:
        gs.background(240)
        gs.fill(255, 0, 0)
        gs.rect(1, 1, 6, 4)
        gs.fill(0, 0, 255)
        gs.circle(11, 7, 4)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    return bytes(context.load_pixels())


def test_canvas_basic_shapes_golden_hash():
    digest = hashlib.sha256(_render_reference_pixels()).hexdigest()
    assert digest == "8163600793b1e8e5f317a6c9d9343d5bf8ff73d3d9e30728637b88740b8602c8"
