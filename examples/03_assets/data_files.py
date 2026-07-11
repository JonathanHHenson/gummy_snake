"""JSON, strings, bytes, and writer helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/03_assets/data_files.png")
DATA_DIR = Path("examples/output/03_assets/data")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
LOADED: dict[str, object] = {}
LOADED_BYTES: list[int] = []


@gs.preload
async def preload() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    gs.save_json({"palette": ["navy", "coral", "mint"], "count": 3}, DATA_DIR / "sample.json")
    gs.save_strings(["alpha", "beta", "gamma"], DATA_DIR / "sample.txt")
    gs.save_bytes([2, 3, 5, 8, 13, 21], DATA_DIR / "sample.bin")
    with gs.create_writer(DATA_DIR / "writer.txt") as writer:
        writer.print("created by gs.create_writer")
        writer.print("second line")

    LOADED["json"] = await gs.load_json_async(DATA_DIR / "sample.json")
    LOADED["strings"] = await gs.load_strings_async(DATA_DIR / "sample.txt")
    LOADED_BYTES[:] = await gs.load_bytes_async(DATA_DIR / "sample.bin")
    LOADED["bytes"] = LOADED_BYTES
    LOADED["writer"] = await gs.load_strings_async(DATA_DIR / "writer.txt")


@gs.setup
def setup() -> None:
    gs.create_canvas(620, 340)


@gs.draw
def draw() -> None:
    gs.background(245, 244, 238)
    gs.fill(30, 34, 44)
    gs.text_size(18)
    gs.text("Data helpers", 34, 44)
    gs.text_size(15)
    for i, (name, value) in enumerate(LOADED.items()):
        gs.text(f"{name}: {value}", 34, 92 + i * 48)

    for i, value in enumerate(LOADED_BYTES):
        gs.fill(43, 132, 210)
        gs.rect(360 + i * 34, 256 - int(value) * 7, 22, int(value) * 7)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
