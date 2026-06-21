"""Rendering helpers for the Asteroids example."""

from __future__ import annotations

import math

import gummysnake as gs

from .constants import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    LASER_SPRITE_HEIGHT,
    LASER_SPRITE_WIDTH,
    SHIP_RADIUS,
    SHIP_SPRITE_HEIGHT,
    SHIP_SPRITE_WIDTH,
)
from .helpers import key_down
from .models import Asteroid, Shot


class AsteroidsRenderingMixin:
    ship: gs.Image | None
    laser: gs.Image | None
    meteor_large: gs.Image | None
    meteor_medium: gs.Image | None
    meteor_small: gs.Image | None
    ship_x: float
    ship_y: float
    ship_angle: float
    shots: list[Shot]
    asteroids: list[Asteroid]
    score: int
    lives: int
    wave: int
    invulnerable: int
    game_over: bool
    last_key: str

    def _draw_space(self) -> None:
        gs.background(8, 13, 32)
        gs.no_stroke()
        for index in range(72):
            x = (index * 97 + gs.frame_count() * (index % 4 + 1)) % CANVAS_WIDTH
            y = (index * 53 + index * index) % CANVAS_HEIGHT
            alpha = 110 + (index % 4) * 35
            gs.fill(190, 220, 255, alpha)
            gs.circle(x, y, 1 + index % 3)

    def _draw_shots(self) -> None:
        if self.laser is None:
            return
        for shot in self.shots:
            with gs.pushed():
                gs.translate(shot.x, shot.y)
                gs.rotate(math.atan2(shot.vy, shot.vx) + math.pi / 2)
                gs.image(self.laser, 0, 0, LASER_SPRITE_WIDTH, LASER_SPRITE_HEIGHT)

    def _draw_asteroids(self) -> None:
        for asteroid in self.asteroids:
            image = self._asteroid_image(asteroid)
            diameter = asteroid.radius * 2
            if image is None:
                gs.fill(95, 100, 115)
                gs.stroke(180, 190, 210)
                gs.circle(asteroid.x, asteroid.y, diameter)
                continue
            with gs.pushed():
                gs.translate(asteroid.x, asteroid.y)
                gs.rotate(asteroid.angle)
                gs.image(image, 0, 0, diameter, diameter)

    def _draw_ship(self) -> None:
        if self.game_over:
            return
        if self.invulnerable > 0 and gs.frame_count() % 12 < 6:
            return

        thrusting = key_down("w") or gs.key_is_down(gs.UP_ARROW)
        if thrusting:
            self._draw_thrust_flame()

        if self.ship is not None:
            with gs.pushed():
                gs.translate(self.ship_x, self.ship_y)
                gs.rotate(self.ship_angle + math.pi / 2)
                gs.image(self.ship, 0, 0, SHIP_SPRITE_WIDTH, SHIP_SPRITE_HEIGHT)
        else:
            self._draw_fallback_ship()

        if self.invulnerable > 0:
            gs.no_fill()
            gs.stroke(78, 205, 255, 150)
            gs.stroke_weight(3)
            gs.circle(self.ship_x, self.ship_y, SHIP_RADIUS * 2.7)

    def _draw_hud(self) -> None:
        gs.no_stroke()
        gs.fill(255, 255, 255, 230)
        gs.text_size(16)
        gs.text(f"Score {self.score}", 28, 32)
        gs.text(f"Lives {self.lives}", 28, 56)
        gs.text(f"Wave {self.wave}", 28, 80)
        gs.text("Rotate: A/D or arrows   Thrust: W/up   Fire: space/click", 28, CANVAS_HEIGHT - 40)
        gs.text(f"Last key: {self.last_key!r}", 28, CANVAS_HEIGHT - 18)

        if self.game_over:
            gs.fill(255, 255, 255, 245)
            gs.text_size(34)
            gs.text("GAME OVER", CANVAS_WIDTH / 2 - 96, CANVAS_HEIGHT / 2 - 12)
            gs.text_size(18)
            gs.text("Press R to restart", CANVAS_WIDTH / 2 - 76, CANVAS_HEIGHT / 2 + 22)

    def _draw_thrust_flame(self) -> None:
        with gs.pushed():
            gs.translate(self.ship_x, self.ship_y)
            gs.rotate(self.ship_angle)
            gs.no_stroke()
            gs.fill(255, 138, 48, 210)
            gs.triangle(-18, 12, -18, -12, -38, 0)
            gs.fill(255, 232, 96, 230)
            gs.triangle(-18, 7, -18, -7, -30, 0)

    def _draw_fallback_ship(self) -> None:
        with gs.pushed():
            gs.translate(self.ship_x, self.ship_y)
            gs.rotate(self.ship_angle)
            gs.stroke(170, 225, 255, 255)
            gs.stroke_weight(3)
            gs.fill(36, 116, 220, 245)
            gs.triangle(32, 0, -24, -23, -13, 0)
            gs.triangle(32, 0, -13, 0, -24, 23)

    def _asteroid_image(self, asteroid: Asteroid) -> gs.Image | None:
        if asteroid.size >= 3:
            return self.meteor_large
        if asteroid.size == 2:
            return self.meteor_medium
        return self.meteor_small
