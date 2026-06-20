"""Playable Asteroids-style demo using Kenney space shooter assets.

Run interactively with canvas:
    uv run python examples/games/asteroids.py --interactive

Run/export a deterministic preview without opening a window:
    uv run python examples/games/asteroids.py --headless --frames 1

Controls when interactive:
    A/D or left/right arrows rotate the ship.
    W or up arrow thrusts forward.
    Space or click fires a laser.
    R restarts after game over.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake.events.input_state import KeyboardEvent, MouseEvent

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/games/asteroids.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 480
SHIP_RADIUS = 28.0
SHIP_SPRITE_WIDTH = 86
SHIP_SPRITE_HEIGHT = 64
LASER_SPRITE_WIDTH = 12
LASER_SPRITE_HEIGHT = 36
SHOT_RADIUS = 5.0
SHOT_SPEED = 9.0
SHOT_LIFETIME = 54
INVULNERABLE_FRAMES = 120


@dataclass
class Shot:
    x: float
    y: float
    vx: float
    vy: float
    age: int = 0


@dataclass
class Asteroid:
    x: float
    y: float
    vx: float
    vy: float
    size: int
    spin: float
    angle: float = 0.0

    @property
    def radius(self) -> float:
        return 18.0 + self.size * 16.0

    @property
    def score_value(self) -> int:
        return 50 * (4 - self.size)


class AsteroidsGame(gs.Sketch):
    def __init__(self) -> None:
        super().__init__(headless=ARGS.headless)
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
        save_once(ARGS, gs.frame_count(), gs.save_canvas)

    def mouse_pressed(self, event: MouseEvent) -> None:
        self._aim_toward(event.x, event.y)
        self._fire()

    def mouse_dragged(self, event: MouseEvent) -> None:
        self._aim_toward(event.x, event.y)

    def mouse_moved(self, event: MouseEvent) -> None:
        self._aim_toward(event.x, event.y)

    def key_pressed(self, event: KeyboardEvent) -> None:
        self.last_key = event.key or str(event.key_code)
        if _key_matches(event, "r") and self.game_over:
            self._reset_game()
        if _key_matches(event, " "):
            self._fire()

    def key_typed(self, event: KeyboardEvent) -> None:
        self.last_key = event.key or "typed"

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

        if _key_down("a") or gs.key_is_down(gs.LEFT_ARROW):
            self.ship_angle -= 0.075
        if _key_down("d") or gs.key_is_down(gs.RIGHT_ARROW):
            self.ship_angle += 0.075
        if _key_down("w") or gs.key_is_down(gs.UP_ARROW):
            self.ship_vx += math.cos(self.ship_angle) * 0.22
            self.ship_vy += math.sin(self.ship_angle) * 0.22
        if _key_down(" "):
            self._fire()

        self.ship_vx *= 0.992
        self.ship_vy *= 0.992
        speed = math.hypot(self.ship_vx, self.ship_vy)
        if speed > 6.0:
            scale = 6.0 / speed
            self.ship_vx *= scale
            self.ship_vy *= scale

        self.ship_x = _wrap(self.ship_x + self.ship_vx, CANVAS_WIDTH)
        self.ship_y = _wrap(self.ship_y + self.ship_vy, CANVAS_HEIGHT)

    def _update_shots(self) -> None:
        live_shots: list[Shot] = []
        for shot in self.shots:
            shot.x = _wrap(shot.x + shot.vx, CANVAS_WIDTH)
            shot.y = _wrap(shot.y + shot.vy, CANVAS_HEIGHT)
            shot.age += 1
            if shot.age < SHOT_LIFETIME:
                live_shots.append(shot)
        self.shots = live_shots

    def _update_asteroids(self) -> None:
        for asteroid in self.asteroids:
            asteroid.x = _wrap(asteroid.x + asteroid.vx, CANVAS_WIDTH)
            asteroid.y = _wrap(asteroid.y + asteroid.vy, CANVAS_HEIGHT)
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
                    _wrapped_distance(shot.x, shot.y, asteroid.x, asteroid.y)
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
                _wrapped_distance(self.ship_x, self.ship_y, asteroid.x, asteroid.y)
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

        thrusting = _key_down("w") or gs.key_is_down(gs.UP_ARROW)
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


def _key_down(value: str) -> bool:
    return gs.key_is_down(ord(value.lower())) or gs.key_is_down(ord(value.upper()))


def _key_matches(event: KeyboardEvent, value: str) -> bool:
    return event.key == value or event.key_code in {ord(value.lower()), ord(value.upper())}


def _wrap(value: float, maximum: float) -> float:
    return value % maximum


def _wrapped_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    dx = min(dx, CANVAS_WIDTH - dx)
    dy = min(dy, CANVAS_HEIGHT - dy)
    return math.hypot(dx, dy)


if __name__ == "__main__":
    AsteroidsGame().run(max_frames=ARGS.frames)
