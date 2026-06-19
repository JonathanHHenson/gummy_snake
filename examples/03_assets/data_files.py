"""JSON, strings, bytes, and writer helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/03_assets/data_files.png")
DATA_DIR = Path("examples/output/03_assets/data")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
LOADED: dict[str, object] = {}


def preload() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p5.save_json({"palette": ["navy", "coral", "mint"], "count": 3}, DATA_DIR / "sample.json")
    p5.save_strings(["alpha", "beta", "gamma"], DATA_DIR / "sample.txt")
    p5.save_bytes([2, 3, 5, 8, 13, 21], DATA_DIR / "sample.bin")
    with p5.create_writer(DATA_DIR / "writer.txt") as writer:
        writer.print("created by p5.create_writer")
        writer.print("second line")

    LOADED["json"] = p5.load_json(DATA_DIR / "sample.json")
    LOADED["strings"] = p5.load_strings(DATA_DIR / "sample.txt")
    LOADED["bytes"] = list(p5.load_bytes(DATA_DIR / "sample.bin"))
    LOADED["writer"] = p5.load_strings(DATA_DIR / "writer.txt")


def setup() -> None:
    p5.create_canvas(620, 340)


def draw() -> None:
    p5.background(245, 244, 238)
    p5.fill(30, 34, 44)
    p5.text_size(18)
    p5.text("Data helpers", 34, 44)
    p5.text_size(15)
    for i, (name, value) in enumerate(LOADED.items()):
        p5.text(f"{name}: {value}", 34, 92 + i * 48)

    for i, value in enumerate(LOADED["bytes"]):  # type: ignore[index]
        p5.fill(43, 132, 210)
        p5.rect(360 + i * 34, 256 - int(value) * 7, 22, int(value) * 7)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(preload=preload, setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
