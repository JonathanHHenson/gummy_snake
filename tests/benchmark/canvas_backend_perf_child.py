from __future__ import annotations

import json
import platform
import sys
import time

from canvas_backend_perf_scenes import draw_scene, setup_scene

import gummysnake as gs
from gummysnake.rust.canvas import require_canvas_runtime


def main() -> None:
    variant = sys.argv[1]
    frames = int(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "interactive"
    if mode not in {"interactive", "headless"}:
        raise ValueError("benchmark mode must be 'interactive' or 'headless'")
    start = 0.0
    canvas_size = [0, 0]

    def setup() -> None:
        nonlocal start, canvas_size
        setup_scene(variant)
        canvas_size = [gs.current.width, gs.current.height]
        start = time.perf_counter()

    def draw() -> None:
        draw_scene(variant)

    require_canvas_runtime()
    gs.run(setup=setup, draw=draw, headless=(mode == "headless"), max_frames=frames)
    elapsed = time.perf_counter() - start
    print(
        json.dumps(
            {
                "variant": variant,
                "frames": frames,
                "canvas_size": canvas_size,
                "pixel_density": 1.0,
                "backend_mode": mode,
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
