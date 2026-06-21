from __future__ import annotations

import json
import platform
import sys
import time

from canvas_backend_perf_scenes import draw_scene, setup_scene

import gummysnake as gs
from gummysnake.rust.canvas import is_canvas_runtime_available


def main() -> None:
    variant = sys.argv[1]
    frames = int(sys.argv[2])
    start = 0.0

    def setup() -> None:
        nonlocal start
        setup_scene(variant)
        start = time.perf_counter()

    def draw() -> None:
        draw_scene(variant)

    if not is_canvas_runtime_available():
        print(json.dumps({"skipped": True, "reason": "canvas runtime unavailable"}))
        return
    gs.run(setup=setup, draw=draw, headless=True, max_frames=frames)
    elapsed = time.perf_counter() - start
    print(
        json.dumps(
            {
                "variant": variant,
                "frames": frames,
                "canvas_size": [720, 480],
                "pixel_density": 1.0,
                "backend_mode": "headless",
                "gpu_available": None,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "elapsed": elapsed,
                "fps": frames / max(elapsed, 1e-9),
            }
        )
    )


if __name__ == "__main__":
    main()
