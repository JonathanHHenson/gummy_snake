"""Image-based Asteroids demo using Rust-managed canvas image assets.

Run interactively:
    uv run python examples/new_rust_backend/canvas_asteroids_images.py

Run/export a bounded preview:
    uv run python examples/new_rust_backend/canvas_asteroids_images.py --frames 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import p5

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canvas_asteroids import (  # noqa: E402
    ASSET_DIR,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    AsteroidsDemo,
)

DEFAULT_IMAGE_OUTPUT = Path("examples/output/new_rust_backend/canvas_asteroids_images.png")


class ImageAsteroidsDemo(AsteroidsDemo):
    def __init__(
        self,
        *,
        headless: bool | None = None,
        export_canvas: bool = False,
        output: Path = DEFAULT_IMAGE_OUTPUT,
    ) -> None:
        super().__init__(headless=headless, export_canvas=export_canvas, output=output)
        self.use_sprite_assets = True

    def setup(self) -> None:
        p5.create_canvas(CANVAS_WIDTH, CANVAS_HEIGHT, pixel_density=2)
        p5.frame_rate(60)
        p5.image_mode(p5.CENTER)
        self.ship = p5.P5Image.from_file(ASSET_DIR / "playerShip1_blue.png")
        self.laser = p5.P5Image.from_file(ASSET_DIR / "Lasers/laserBlue01.png")
        self.meteor_large = p5.P5Image.from_file(ASSET_DIR / "Meteors/meteorGrey_big1.png")
        self.meteor_medium = p5.P5Image.from_file(ASSET_DIR / "Meteors/meteorGrey_med1.png")
        self.meteor_small = p5.P5Image.from_file(ASSET_DIR / "Meteors/meteorGrey_small1.png")
        self.thrust_flame = p5.P5Image.from_file(ASSET_DIR / "Effects/fire17.png")
        self._reset_game()

    def _draw_hud(self) -> None:
        p5.no_stroke()
        p5.fill(255, 255, 255, 235)
        p5.text_size(16)
        p5.text(f"Score {self.score}", 28, 32)
        p5.text(f"Lives {self.lives}", 28, 56)
        p5.text(f"Wave {self.wave}", 28, 80)
        p5.text("Rotate: A/D or arrows   Thrust: W/up   Fire: space/click", 28, CANVAS_HEIGHT - 40)
        p5.text(f"Last key: {self.last_key!r}", 28, CANVAS_HEIGHT - 18)

        if self.game_over:
            p5.fill(255, 255, 255, 245)
            p5.text_size(34)
            p5.text("GAME OVER", CANVAS_WIDTH / 2 - 96, CANVAS_HEIGHT / 2 - 12)
            p5.text_size(18)
            p5.text("Press R to restart", CANVAS_WIDTH / 2 - 76, CANVAS_HEIGHT / 2 + 22)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--output", type=Path, default=DEFAULT_IMAGE_OUTPUT)
    parser.add_argument("--no-save", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    export_canvas = not args.no_save and args.frames is not None and args.frames > 0
    demo = ImageAsteroidsDemo(
        headless=args.headless,
        export_canvas=export_canvas,
        output=args.output,
    )
    demo.run(max_frames=args.frames)


if __name__ == "__main__":
    main()
