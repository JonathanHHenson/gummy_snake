"""Runnable Asteroids example app."""

from __future__ import annotations

import argparse
import math

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake.core.input_event_model import KeyboardEvent, MouseEvent

from .constants import ASSETS, CANVAS_HEIGHT, CANVAS_WIDTH, INVULNERABLE_FRAMES, OUTPUT
from .helpers import key_matches
from .logic import AsteroidsLogicMixin
from .models import Asteroid, Shot
from .rendering import AsteroidsRenderingMixin


class AsteroidsGame(AsteroidsLogicMixin, AsteroidsRenderingMixin, gs.Sketch):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__(headless=args.headless)
        self.args = args
        self.ship: gs.Image | None = None
        self.laser: gs.Image | None = None
        self.meteor_large: gs.Image | None = None
        self.meteor_medium: gs.Image | None = None
        self.meteor_small: gs.Image | None = None
        self.thrust_flame: gs.Image | None = None
        self.ship_x = CANVAS_WIDTH / 2
        self.ship_y = CANVAS_HEIGHT / 2
        self.ship_vx = 0.0
        self.ship_vy = 0.0
        self.ship_angle = -math.pi / 2
        self.shots: list[Shot] = []
        self.asteroids: list[Asteroid] = []
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.cooldown = 0
        self.invulnerable = INVULNERABLE_FRAMES
        self.game_over = False
        self.last_key = "none"

    def preload(self) -> None:
        self.ship = gs.load_image(ASSETS / "playerShip1_blue.png")
        self.laser = gs.load_image(ASSETS / "Lasers/laserBlue01.png")
        self.meteor_large = gs.load_image(ASSETS / "Meteors/meteorGrey_big1.png")
        self.meteor_medium = gs.load_image(ASSETS / "Meteors/meteorGrey_med1.png")
        self.meteor_small = gs.load_image(ASSETS / "Meteors/meteorGrey_small1.png")
        self.thrust_flame = gs.load_image(ASSETS / "Effects/fire17.png")

    def setup(self) -> None:
        gs.create_canvas(CANVAS_WIDTH, CANVAS_HEIGHT)
        gs.frame_rate(60)
        gs.image_mode(gs.CENTER)
        self._reset_game()

    def draw(self) -> None:
        if not self.game_over:
            self._update_ship()
            self._update_shots()
            self._update_asteroids()
            self._handle_collisions()
            if not self.asteroids:
                self.wave += 1
                self._spawn_wave()

        self._draw_space()
        self._draw_shots()
        self._draw_asteroids()
        self._draw_ship()
        self._draw_hud()
        save_once(self.args, gs.frame_count(), gs.save_canvas)

    def mouse_pressed(self, event: MouseEvent) -> None:
        self._aim_toward(event.x, event.y)
        self._fire()

    def mouse_dragged(self, event: MouseEvent) -> None:
        self._aim_toward(event.x, event.y)

    def mouse_moved(self, event: MouseEvent) -> None:
        self._aim_toward(event.x, event.y)

    def key_pressed(self, event: KeyboardEvent) -> None:
        self.last_key = event.key or str(event.key_code)
        if key_matches(event, "r") and self.game_over:
            self._reset_game()
        if key_matches(event, " "):
            self._fire()

    def key_typed(self, event: KeyboardEvent) -> None:
        self.last_key = event.key or "typed"


def run(doc: str | None = None) -> None:
    args = example_parser(doc or "", OUTPUT).parse_args()
    AsteroidsGame(args).run(max_frames=args.frames)
