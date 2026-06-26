"""Runnable Coin Runner example app."""

from __future__ import annotations

import argparse

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake.core.input_events import KeyboardEvent, MouseEvent

from .constants import ASSETS, CANVAS_HEIGHT, CANVAS_WIDTH, GROUND_Y, GROUNDED_GRACE_FRAMES, OUTPUT
from .helpers import key_name
from .logic import CoinRunnerLogicMixin
from .models import Burst, Gap, Hazard, Pickup, Platform
from .rendering import CoinRunnerRenderingMixin
from .world import CoinRunnerWorldMixin


class CoinRunner(CoinRunnerLogicMixin, CoinRunnerWorldMixin, CoinRunnerRenderingMixin, gs.Sketch):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__(headless=args.headless)
        self.args = args
        self.keys: set[str] = set()
        self.idle: gs.Image | None = None
        self.run_strip: gs.Image | None = None
        self.pickup_image: gs.Image | None = None
        self.ufo: gs.Image | None = None
        self.sound: gs.Sound | None = None
        self.sound_available = True
        self.runner_y = GROUND_Y
        self.previous_runner_y = GROUND_Y
        self.runner_vy = 0.0
        self.jump_buffer_frames = 0
        self.grounded_grace_frames = GROUNDED_GRACE_FRAMES
        self.jump_held = False
        self.jump_state = "grounded"
        self.current_gravity = 0.68
        self.scroll = 0.0
        self.speed = 4.3
        self.score = 0
        self.best = 0
        self.coins = 0
        self.combo = 0
        self.lives = 3
        self.shield = 0
        self.invulnerable = 0
        self.game_over = False
        self.pickups: list[Pickup] = []
        self.hazards: list[Hazard] = []
        self.platforms: list[Platform] = []
        self.gaps: list[Gap] = []
        self.bursts: list[Burst] = []

    def preload(self) -> None:
        self.idle = gs.load_image(ASSETS / "herochar/herochar_idle_anim_strip_4.png")
        self.run_strip = gs.load_image(ASSETS / "herochar/herochar_run_anim_strip_6.png")
        self.pickup_image = gs.load_image(ASSETS / "Power-ups/powerupBlue_shield.png")
        self.ufo = gs.load_image(ASSETS / "ufoBlue.png")
        self.sound = gs.load_sound(ASSETS / "coin-drop-4.wav")
        self.sound.volume(0.35)

    def setup(self) -> None:
        gs.create_canvas(CANVAS_WIDTH, CANVAS_HEIGHT)
        gs.frame_rate(60)
        gs.image_mode(gs.CENTER)
        gs.no_smooth()
        self._reset_game()

    def draw(self) -> None:
        if not self.game_over:
            self._update()

        self._draw_scene()
        save_once(self.args, gs.frame_count(), gs.save_canvas)

    def key_pressed(self, event: KeyboardEvent) -> None:
        key = key_name(event)
        self.keys.add(key)
        if key in {"space", "up", "w"}:
            self._queue_jump()
        if key == "r" and self.game_over:
            self._reset_game()

    def key_released(self, event: KeyboardEvent) -> None:
        key = key_name(event)
        self.keys.discard(key)
        if key in {"space", "up", "w"}:
            self.jump_held = False
            self._release_jump()

    def mouse_pressed(self, _event: MouseEvent) -> None:
        if self.game_over:
            self._reset_game()
            return
        self._queue_jump()

    def mouse_released(self, _event: MouseEvent) -> None:
        self.jump_held = False
        self._release_jump()


def run(doc: str | None = None) -> None:
    args = example_parser(doc or "", OUTPUT).parse_args()
    CoinRunner(args).run(max_frames=args.frames)
