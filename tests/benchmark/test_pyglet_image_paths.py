from __future__ import annotations

import json
import statistics
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

FRAMES = 180
REPEATS = 2
ASSET = Path("examples/assets/herochar/herochar_idle_anim_strip_4.png")
VARIANTS = (
    "image_nosmooth",
    "image_left_nosmooth",
    "image_shear_nosmooth",
    "rect_image_nosmooth",
)
CHILD_CODE = textwrap.dedent(
    """
    from __future__ import annotations

    import json
    import sys
    import time
    from pathlib import Path

    import p5

    variant = sys.argv[1]
    frames = int(sys.argv[2])
    asset = Path(sys.argv[3])
    sprite = None
    start = 0.0


    def cut_strip(image: p5.Image, num_sprites: int) -> list[p5.Image]:
        sprite_width = image.width // num_sprites
        return [
            image.get(i * sprite_width, 0, sprite_width, image.height) for i in range(num_sprites)
        ]


    def setup() -> None:
        nonlocal_vars = globals()
        p5.create_canvas(1200, 800)
        p5.frame_rate(10_000)
        nonlocal_vars["sprite"] = cut_strip(p5.load_image(asset), 4)[0]
        nonlocal_vars["start"] = time.perf_counter()


    def draw() -> None:
        p5.background(0)

        if variant == "rect_image_nosmooth":
            with p5.pushed():
                p5.fill(90, 90, 90)
                p5.no_stroke()
                p5.rect(250, 650, 700, 40)

        with p5.pushed():
            p5.no_smooth()
            p5.image_mode(p5.CENTER)
            if variant == "image_left_nosmooth":
                p5.translate(600, 400)
                p5.scale(-1, 1)
                p5.image(sprite, 0, 0, 50, 50)
            elif variant == "image_shear_nosmooth":
                p5.translate(600, 400)
                p5.apply_matrix(1, 0.25, 0.5, 1, 0, 0)
                p5.image(sprite, 0, 0, 50, 50)
            else:
                p5.image(sprite, 600, 400, 50, 50)


    def main() -> None:
        p5.run(setup=setup, draw=draw, backend=p5.PYGLET, max_frames=frames)
        elapsed = time.perf_counter() - start
        fps = frames / max(elapsed, 1e-9)
        print(json.dumps({"variant": variant, "frames": frames, "elapsed": elapsed, "fps": fps}))


    if __name__ == "__main__":
        main()
    """
)


@dataclass(frozen=True)
class BenchmarkSummary:
    variant: str
    samples: tuple[float, ...]

    @property
    def mean_fps(self) -> float:
        return statistics.mean(self.samples)

    @property
    def min_fps(self) -> float:
        return min(self.samples)

    @property
    def max_fps(self) -> float:
        return max(self.samples)


def _run_variant(variant: str, *, frames: int = FRAMES, repeats: int = REPEATS) -> BenchmarkSummary:
    samples: list[float] = []
    for _ in range(repeats):
        result = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, variant, str(frames), str(ASSET)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise AssertionError(f"benchmark variant {variant!r} failed\n{detail}")
        payload = json.loads(result.stdout.strip())
        samples.append(float(payload["fps"]))
    return BenchmarkSummary(variant=variant, samples=tuple(samples))


@pytest.mark.benchmark
@pytest.mark.parametrize("variant", VARIANTS)
def test_pyglet_image_benchmark_variants_execute(variant: str) -> None:
    summary = _run_variant(variant)
    print(
        f"benchmark {summary.variant}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f}"
    )
    assert summary.mean_fps > 0


@pytest.mark.benchmark
def test_pyglet_image_benchmark_regressions() -> None:
    baseline = _run_variant("image_nosmooth")
    left = _run_variant("image_left_nosmooth")
    shear = _run_variant("image_shear_nosmooth")
    rect = _run_variant("rect_image_nosmooth")

    print(
        "benchmark ratios: "
        f"left/baseline={left.mean_fps / baseline.mean_fps:.3f} "
        f"shear/baseline={shear.mean_fps / baseline.mean_fps:.3f} "
        f"rect/baseline={rect.mean_fps / baseline.mean_fps:.3f}"
    )

    assert left.mean_fps >= baseline.mean_fps * 0.70
    assert shear.mean_fps >= baseline.mean_fps * 0.70
    assert rect.mean_fps >= baseline.mean_fps * 0.70
