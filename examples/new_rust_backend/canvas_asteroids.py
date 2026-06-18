"""Asteroids-style demo for the experimental Rust canvas backend.

This example replaces all image loading with drawn primitives since the
Rust canvas does not yet support ``p5.image()``.

Run interactively with the Rust canvas backend (requires native runtime):
    uv run python examples/new_rust_backend/canvas_asteroids.py

Run a bounded offscreen/export pass:
    uv run python examples/new_rust_backend/canvas_asteroids.py --frames 1
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from pathlib import Path

import p5

DEFAULT_OUTPUT = Path("examples/output/new_rust_backend/canvas_asteroids.png")
EXPORT_CANVAS = True
OUTPUT = DEFAULT_OUTPUT

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 480
SHIP_RADIUS = 28.0
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


class AsteroidsDemo:
    def __init__(self, *, export_canvas: bool) -> None:
        self.export_canvas = export_canvas
        self.ship_x = CANVAS_WIDTH / 2.0
        self.ship_y = CANVAS_HEIGHT / 2.0
        self.ship_vx = 0.0
        self.ship_vy = 0.0
        self.ship_angle: float = -math.pi / 2.0
        self.shots: list[Shot] = []
        self.asteroids: list[Asteroid] = []
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.cooldown = 0
        self.invulnerable: int = INVULNERABLE_FRAMES
        self.game_over = False
        self.last_key = "none"

        # FPS logging state
        self._fps_frames: int = 0
        self._fps_last_print: float = time.monotonic()

    def setup(self) -> None:
        p5.create_canvas(CANVAS_WIDTH, CANVAS_HEIGHT)
        p5.frame_rate(60)
        self._reset_game()

    def draw(self) -> None:
        self._update_fps()

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

        if EXPORT_CANVAS and p5.frame_count() == 0:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            p5.save_canvas(str(OUTPUT), overwrite=True)

    def key_pressed(self, event: object = None) -> None:  # noqa: ARG002
        if _key_matches("r") and self.game_over:
            self._reset_game()

    def key_typed(self, event: object = None) -> None:  # noqa: ARG002
        self.last_key = "typed"

    def mouse_pressed(self, event: object = None) -> None:  # noqa: ARG002
        self._fire()

    def _reset_game(self) -> None:
        self.ship_x = CANVAS_WIDTH / 2.0
        self.ship_y = CANVAS_HEIGHT / 2.0
        self.ship_vx = 0.0
        self.ship_vy = 0.0
        self.ship_angle = -math.pi / 2.0
        self.shots.clear()
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.cooldown = 0
        self.invulnerable = INVULNERABLE_FRAMES
        self.game_over = False
        self._spawn_wave()

    def _update_fps(self) -> None:
        self._fps_frames += 1
        now = time.monotonic()
        elapsed = now - self._fps_last_print
        if elapsed >= 1.0:
            fps = self._fps_frames / elapsed
            print(f"[FPS] {int(fps)} ({self._fps_frames} frames in {elapsed:.3f}s)")
            self._fps_frames = 0
            self._fps_last_print = now

    def _spawn_wave(self) -> None:
        self.shots.clear()
        count = min(3 + self.wave, 8)
        self.asteroids.clear()
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

        if p5.key_is_down(ord("a")) or p5.key_is_down(p5.LEFT_ARROW):
            self.ship_angle -= 0.075
        if p5.key_is_down(ord("d")) or p5.key_is_down(p5.RIGHT_ARROW):
            self.ship_angle += 0.075
        if p5.key_is_down(ord("w")) or p5.key_is_down(p5.UP_ARROW):
            self.ship_vx += math.cos(self.ship_angle) * 0.22
            self.ship_vy += math.sin(self.ship_angle) * 0.22
        if p5.key_is_down(ord(" ")) or p5.mouse_button == 1:
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
                if _wrapped_distance(shot.x, shot.y, asteroid.x, asteroid.y) <= (
                    asteroid.radius + SHOT_RADIUS
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
            if _wrapped_distance(self.ship_x, self.ship_y, asteroid.x, asteroid.y) <= (
                asteroid.radius + SHIP_RADIUS
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
        self.ship_x = CANVAS_WIDTH / 2.0
        self.ship_y = CANVAS_HEIGHT / 2.0
        self.ship_vx = 0.0
        self.ship_vy = 0.0
        self.ship_angle = -math.pi / 2.0
        self.shots.clear()
        self.invulnerable = INVULNERABLE_FRAMES

    def _fire(self) -> None:
        if self.game_over or self.cooldown > 0:
            return
        nose_x = self.ship_x + math.cos(self.ship_angle) * 34.0
        nose_y = self.ship_y + math.sin(self.ship_angle) * 34.0
        self.shots.append(
            Shot(
                x=nose_x,
                y=nose_y,
                vx=self.ship_vx + math.cos(self.ship_angle) * SHOT_SPEED,
                vy=self.ship_vy + math.sin(self.ship_angle) * SHOT_SPEED,
            )
        )
        self.cooldown = 10

    def _draw_space(self) -> None:
        p5.background(8, 13, 32)
        p5.no_stroke()
        for index in range(72):
            x = (index * 97 + p5.frame_count() * (index % 4 + 1)) % CANVAS_WIDTH
            y = (index * 53 + index * index) % CANVAS_HEIGHT
            alpha = 110 + (index % 4) * 35
            p5.fill(190, 220, 255, alpha)
            p5.circle(x, y, 1 + index % 3)

    def _draw_shots(self) -> None:
        for shot in self.shots:
            with p5.pushed():
                p5.translate(shot.x, shot.y)
                angle = math.atan2(shot.vy, shot.vx) + math.pi / 2.0
                p5.rotate(angle)
                # Draw laser as a small rectangle (scaled down from sprite dims)
                p5.stroke(100, 200, 255, 240)
                p5.stroke_weight(3)
                p5.no_fill()
                p5.line(0, -LASER_SPRITE_HEIGHT / 2.0, 0, LASER_SPRITE_HEIGHT / 2.0)

    def _draw_asteroids(self) -> None:
        for asteroid in self.asteroids:
            diameter = asteroid.radius * 2.0
            p5.no_fill()
            p5.stroke(180, 190, 210)
            # Draw asteroid as an ellipse with spin (closest to polygon available)
            aspect = 0.7 + asteroid.size * 0.1
            with p5.pushed():
                p5.translate(asteroid.x, asteroid.y)
                p5.rotate(asteroid.angle)
                p5.ellipse(0, 0, diameter * aspect, diameter)

    def _draw_ship(self) -> None:
        if self.game_over:
            return

        # Blink when invulnerable
        if self.invulnerable > 0 and p5.frame_count() % 12 < 6:
            return

        thrusting = _key_down("w") or p5.key_is_down(p5.UP_ARROW)
        if thrusting:
            self._draw_thrust_flame()

        # Draw ship body as a filled triangle pointing upward (rotated)
        with p5.pushed():
            p5.translate(self.ship_x, self.ship_y)
            angle = self.ship_angle + math.pi / 2.0
            p5.rotate(angle)

            # Draw ship body as two triangles (bow pointing UP in local space)
            half_width = SHIP_RADIUS * 0.85
            wing_slot_y = SHIP_RADIUS * 0.18

            p5.stroke(170, 225, 255, 255)
            p5.stroke_weight(3)
            p5.fill(36, 116, 220, 245)
            # Simplified: two triangles forming a pointed bow shape
            p5.triangle(0, -SHIP_RADIUS, -half_width, SHIP_RADIUS * 0.72, 0, wing_slot_y)
            p5.triangle(0, -SHIP_RADIUS, 0, wing_slot_y, half_width, SHIP_RADIUS * 0.72)

        # Draw invulnerability ring
        if self.invulnerable > 0:
            p5.no_fill()
            p5.stroke(78, 205, 255, 150)
            p5.stroke_weight(3)
            p5.circle(self.ship_x, self.ship_y, SHIP_RADIUS * 2.7)

    def _draw_hud(self) -> None:
        # Draw HUD using rectangles and lines (no text support yet)
        # Score bar: filled rectangle at top-left with score as bar height indicator
        p5.no_stroke()

        # Top line (score) - simple text-like indicator using a thick rectangle
        p5.stroke(255, 255, 255)
        p5.stroke_weight(1)

        # Draw score as a series of filled rects (score / 50 = kills, each block)
        score_kills = self.score // 50
        p5.no_stroke()
        for i in range(score_kills):
            x = 28 + i * (LASER_SPRITE_WIDTH - 4)
            p5.fill(255, 196, 61)
            if x < CANVAS_WIDTH - 20:
                p5.rect(x, 16, LASER_SPRITE_WIDTH - 4, 8)

        # Lives as small circles in bottom area
        for i in range(self.lives):
            lx = 28 + i * 24
            ly = CANVAS_HEIGHT - 60
            p5.fill(78, 205, 255)
            p5.stroke(255, 255, 255)
            p5.stroke_weight(1.5)
            p5.circle(lx, ly, 16)

        # Wave as a filled rectangle bar
        wave_x = 28.0
        wave_width = min(self.wave * 40, CANVAS_WIDTH - 120)
        p5.no_stroke()
        p5.fill(90, 190, 255)
        p5.rect(wave_x, CANVAS_HEIGHT - 36, wave_width, 12)

        # Instructions as a series of colored bars (top right)
        self._draw_instructions_bar()

        # Game over screen as filled rectangles
        if self.game_over:
            p5.fill(8, 13, 32, 160)
            p5.rect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)

            # "GAME OVER" represented as horizontal line + info
            center_x = CANVAS_WIDTH / 2.0
            p5.no_stroke()
            p5.fill(255, 80, 80)

            # Draw a simple cross/collision symbol
            p5.stroke(255, 80, 80)
            p5.stroke_weight(4)
            p5.line(
                center_x - 36, CANVAS_HEIGHT / 2.0 - 18, center_x + 36, CANVAS_HEIGHT / 2.0 + 18
            )
            p5.line(
                center_x - 36, CANVAS_HEIGHT / 2.0 + 18, center_x + 36, CANVAS_HEIGHT / 2.0 - 18
            )

            p5.stroke(255, 232, 96)
            p5.no_fill()

    def _draw_instructions_bar(self) -> None:
        bar_x = CANVAS_WIDTH - 180.0
        bar_y = 20.0

        # Draw control info as colored rectangles stacked (no text yet)
        p5.no_stroke()

        # Rotate bar (A/D keys indicator)
        p5.fill(20, 145, 110)
        for i in range(8):
            p5.rect(bar_x, bar_y + i * 6, 60, 4)

        # Thrust bar (W key indicator)
        p5.fill(244, 91, 105)
        for i in range(6):
            p5.rect(bar_x, bar_y + 52 + i * 6, 40, 4)

        # Fire bar (space/click indicator)
        p5.fill(106, 76, 147)
        for i in range(5):
            p5.rect(bar_x, bar_y + 88 + i * 6, 72, 4)

    def _draw_thrust_flame(self) -> None:
        with p5.pushed():
            p5.translate(self.ship_x, self.ship_y)
            angle = self.ship_angle + math.pi / 2.0
            p5.rotate(angle)

            # Flame extends from wing bottom (back of ship, +Y) outward away from bow (-Y)
            half_width = SHIP_RADIUS * 0.85
            wing_y = SHIP_RADIUS * 0.72  # base at ship's tail
            outer_tip_y = SHIP_RADIUS * 1.36  # further from bow (more +Y)
            inner_tip_y = SHIP_RADIUS * 1.02  # further from bow (more +Y)

            # Outer flame: wide triangle from wing bottom corners, pointing away from bow
            p5.no_stroke()
            p5.fill(255, 138, 48, 210)
            p5.triangle(-half_width, wing_y, half_width, wing_y, 0, outer_tip_y)

            # Inner flame (yellow): narrower triangle from inner notch, pointing away from bow
            p5.fill(255, 232, 96, 230)
            notch_y = SHIP_RADIUS * 0.18
            p5.triangle(-notch_y, wing_y, notch_y, wing_y, 0, inner_tip_y)


def _key_down(value: str) -> bool:
    return p5.key_is_down(ord(value.lower())) or p5.key_is_down(ord(value.upper()))


def _key_matches(value: str) -> bool:
    # Simplified match for Rust canvas (no KeyboardEvent passed in headless)
    return p5.key_is_down(ord(value.lower())) or p5.key_is_down(ord(value.upper()))


def _wrap(value: float, maximum: float) -> float:
    return value % maximum


def _wrapped_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    dx = min(dx, CANVAS_WIDTH - dx)
    dy = min(dy, CANVAS_HEIGHT - dy)
    return math.hypot(dx, dy)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=p5.CANVAS, choices=p5.available_backends())
    parser.add_argument("--frames", type=int)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-save", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global EXPORT_CANVAS, OUTPUT
    OUTPUT = args.output
    EXPORT_CANVAS = not args.no_save and args.frames is not None and args.frames > 0
    demo = AsteroidsDemo(export_canvas=EXPORT_CANVAS)
    p5.run(setup=demo.setup, draw=demo.draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
