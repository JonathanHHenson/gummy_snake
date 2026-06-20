from gummysnake.backends import create_backend
from gummysnake.backends.canvas import CanvasBackend


def test_canvas_runtime_is_constructed_without_backend_name():
    assert isinstance(create_backend(), CanvasBackend)


def test_headless_false_requests_interactive_canvas_runtime():
    backend = create_backend(headless=False)

    assert isinstance(backend, CanvasBackend)
    assert backend._headless is False
    assert backend._interactive is True


def test_headless_true_requests_offscreen_canvas_runtime():
    backend = create_backend(headless=True)

    assert isinstance(backend, CanvasBackend)
    assert backend._headless is True
    assert backend._interactive is False
