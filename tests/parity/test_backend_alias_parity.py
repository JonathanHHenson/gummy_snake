import p5_py as p5


def _render_pixels(backend: str) -> list[int]:
    def setup() -> None:
        p5.create_canvas(12, 10)
        p5.no_stroke()

    def draw() -> None:
        p5.background(32)
        p5.fill(255, 200, 0)
        p5.rect(1, 1, 5, 4)
        p5.fill(0, 180, 255)
        p5.circle(8, 6, 3)

    context = p5.run(setup=setup, draw=draw, backend=backend, max_frames=1)
    return context.load_pixels()


def test_headless_and_pillow_backend_aliases_match_pixel_output():
    assert _render_pixels("headless") == _render_pixels("pillow")
