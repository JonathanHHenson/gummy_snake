"""Gameplay logic for the Asteroids example."""

from __future__ import annotations

import math

import gummysnake as gs

from .constants import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    INVULNERABLE_FRAMES,
    SHIP_RADIUS,
    SHOT_LIFETIME,
    SHOT_RADIUS,
    SHOT_SPEED,
)
from .helpers import key_down, wrap, wrapped_distance
from .models import Asteroid, Shot


class AsteroidsLogicMixin:
    ship_x: float
    ship_y: float
    ship_vx: float
    ship_vy: float
    ship_angle: float
    shots: list[Shot]
    asteroids: list[Asteroid]
    score: int
    lives: int
    wave: int
    cooldown: int
    invulnerable: int
    game_over: bool

    def _reset_game(self) -> None:
        self.ship_x = CANVAS_WIDTH / 2
        self.ship_y = CANVAS_HEIGHT / 2
        self.ship_vx = 0.0
        self.ship_vy = 0.0
        self.ship_angle = -math.pi / 2
        self.shots.clear()
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.cooldown = 0
        self.invulnerable = INVULNERABLE_FRAMES
        self.game_over = False
        self._spawn_wave()

    def _spawn_wave(self) -> None:
        self.shots.clear()
        count = min(3 + self.wave, 8)
        self.asteroids = []
        for index in range(count):
            side = index % 4
            if side == 0:
                x, y = 40.0, 70.0 + index * 83 % 340
            elif side == 1:
                x, y = CANVAS_WIDTH - 40.0, 90.0 + index * 67 % 300
            elif side == 2:
                x, y = 110.0 + index * 89 % 500, 40.0
            else:
                x, y = 90.0 + index * 71 % 540, CANVAS_HEIGHT - 40.0
            angle = 0.65 + index * 1.73 + self.wave * 0.41
            speed = 1.05 + 0.12 * self.wave + 0.17 * (index % 3)
            self.asteroids.append(
                Asteroid(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    size=3,
                    spin=(-0.025 if index % 2 else 0.025) * (1 + index % 3),
                )
            )

    def _update_ship(self) -> None:
        if self.cooldown > 0:
            self.cooldown -= 1
        if self.invulnerable > 0:
            self.invulnerable -= 1

        if key_down("a") or gs.key_is_down(gs.LEFT_ARROW):
            self.ship_angle -= 0.075
        if key_down("d") or gs.key_is_down(gs.RIGHT_ARROW):
            self.ship_angle += 0.075
        if key_down("w") or gs.key_is_down(gs.UP_ARROW):
            self.ship_vx += math.cos(self.ship_angle) * 0.22
            self.ship_vy += math.sin(self.ship_angle) * 0.22
        if key_down(" "):
            self._fire()

        self.ship_vx *= 0.992
        self.ship_vy *= 0.992
        speed = math.hypot(self.ship_vx, self.ship_vy)
        if speed > 6.0:
            scale = 6.0 / speed
            self.ship_vx *= scale
            self.ship_vy *= scale

        self.ship_x = wrap(self.ship_x + self.ship_vx, CANVAS_WIDTH)
        self.ship_y = wrap(self.ship_y + self.ship_vy, CANVAS_HEIGHT)

    def _update_shots(self) -> None:
        live_shots: list[Shot] = []
        for shot in self.shots:
            shot.x = wrap(shot.x + shot.vx, CANVAS_WIDTH)
            shot.y = wrap(shot.y + shot.vy, CANVAS_HEIGHT)
            shot.age += 1
            if shot.age < SHOT_LIFETIME:
                live_shots.append(shot)
        self.shots = live_shots

    def _update_asteroids(self) -> None:
        for asteroid in self.asteroids:
            asteroid.x = wrap(asteroid.x + asteroid.vx, CANVAS_WIDTH)
            asteroid.y = wrap(asteroid.y + asteroid.vy, CANVAS_HEIGHT)
            asteroid.angle += asteroid.spin

    def _handle_collisions(self) -> None:
        remaining_shots: list[Shot] = []
        hit_asteroids: set[int] = set()
        spawned: list[Asteroid] = []

        for shot in self.shots:
            hit_index = None
            for index, asteroid in enumerate(self.asteroids):
                if index in hit_asteroids:
                    continue
                if (
                    wrapped_distance(shot.x, shot.y, asteroid.x, asteroid.y)
                    <= asteroid.radius + SHOT_RADIUS
                ):
                    hit_index = index
                    break
            if hit_index is None:
                remaining_shots.append(shot)
                continue

            hit_asteroids.add(hit_index)
            asteroid = self.asteroids[hit_index]
            self.score += asteroid.score_value
            spawned.extend(self._split_asteroid(asteroid))

        self.shots = remaining_shots
        self.asteroids = [
            asteroid for index, asteroid in enumerate(self.asteroids) if index not in hit_asteroids
        ] + spawned

        if self.invulnerable > 0:
            return
        for asteroid in self.asteroids:
            if (
                wrapped_distance(self.ship_x, self.ship_y, asteroid.x, asteroid.y)
                <= asteroid.radius + SHIP_RADIUS
            ):
                self._lose_life()
                break

    def _split_asteroid(self, asteroid: Asteroid) -> list[Asteroid]:
        if asteroid.size <= 1:
            return []
        child_size = asteroid.size - 1
        base_angle = math.atan2(asteroid.vy, asteroid.vx)
        child_speed = math.hypot(asteroid.vx, asteroid.vy) + 0.65
        children: list[Asteroid] = []
        for direction in (-1, 1):
            angle = base_angle + direction * 0.82
            children.append(
                Asteroid(
                    x=asteroid.x + math.cos(angle) * 8,
                    y=asteroid.y + math.sin(angle) * 8,
                    vx=math.cos(angle) * child_speed,
                    vy=math.sin(angle) * child_speed,
                    size=child_size,
                    spin=-asteroid.spin * direction * 1.25,
                    angle=asteroid.angle,
                )
            )
        return children

    def _lose_life(self) -> None:
        self.lives -= 1
        if self.lives <= 0:
            self.game_over = True
            return
        self.ship_x = CANVAS_WIDTH / 2
        self.ship_y = CANVAS_HEIGHT / 2
        self.ship_vx = 0.0
        self.ship_vy = 0.0
        self.ship_angle = -math.pi / 2
        self.shots.clear()
        self.invulnerable = INVULNERABLE_FRAMES

    def _fire(self) -> None:
        if self.game_over or self.cooldown > 0:
            return
        nose_x = self.ship_x + math.cos(self.ship_angle) * 34
        nose_y = self.ship_y + math.sin(self.ship_angle) * 34
        self.shots.append(
            Shot(
                x=nose_x,
                y=nose_y,
                vx=self.ship_vx + math.cos(self.ship_angle) * SHOT_SPEED,
                vy=self.ship_vy + math.sin(self.ship_angle) * SHOT_SPEED,
            )
        )
        self.cooldown = 10

    def _aim_toward(self, x: float, y: float) -> None:
        self.ship_angle = math.atan2(y - self.ship_y, x - self.ship_x)
