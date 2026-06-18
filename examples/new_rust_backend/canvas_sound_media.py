"""Backend-neutral sound and media lifecycle demo for canvas migration work."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import ClassVar

import p5
from p5.assets.sound import Sound
from p5.exceptions import BackendCapabilityError

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
SOUND_PATH = ASSET_DIR / "coin-drop-4.wav"
OUTPUT = Path("examples/output/new_rust_backend/canvas_sound_media.png")


class CanvasSoundMediaDemo(p5.Sketch):
    sound: ClassVar[Sound | None] = None

    def __init__(self, *, backend: str = "canvas", play: bool = False, export_canvas: bool = False):
        super().__init__(backend=backend)
        self.play_on_start = play
        self.export_canvas = export_canvas
        self.status = "sound ready"

    def setup(self) -> None:
        p5.create_canvas(640, 360)
        p5.frame_rate(60)
        if CanvasSoundMediaDemo.sound is None:
            CanvasSoundMediaDemo.sound = p5.create_audio(SOUND_PATH)
        CanvasSoundMediaDemo.sound.volume(0.35)
        CanvasSoundMediaDemo.sound.rate(1.0)
        CanvasSoundMediaDemo.sound.pan(0.0)
        if self.play_on_start:
            self._play_sound()

    def draw(self) -> None:
        p5.background(31, 35, 42)
        p5.no_stroke()
        p5.fill(58, 190, 160)
        progress = (p5.frame_count() % 120) / 120
        p5.rect(60, 150, 520 * progress, 24)
        p5.fill(240)
        p5.text_size(24)
        p5.text("backend-neutral sound", 60, 90)
        p5.text_size(16)
        p5.text(self.status, 60, 124)
        if self.export_canvas and p5.frame_count() == 0:
            p5.save_canvas(str(OUTPUT), overwrite=True)

    def mouse_pressed(self, event: object = None) -> None:
        self._play_sound()

    def key_typed(self, event: object = None) -> None:
        self._play_sound()

    def _play_sound(self) -> None:
        sound = CanvasSoundMediaDemo.sound
        if sound is None:
            return
        try:
            sound.play()
            self.status = f"playing {sound.path.name}, duration {sound.duration or 0:.2f}s"
        except BackendCapabilityError as exc:
            self.status = str(exc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="canvas", choices=p5.available_backends())
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    demo = CanvasSoundMediaDemo(
        backend=args.backend,
        play=args.play,
        export_canvas=not args.no_save and args.frames is not None and args.frames > 0,
    )
    demo.run(max_frames=args.frames)


if __name__ == "__main__":
    main()
