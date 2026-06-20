"""Arcade side-scrolling runner using the hero, shield, UFO, and sound assets.

Run interactively with canvas:
    uv run python examples/games/coin_runner.py --interactive

Run/export a deterministic preview without opening a window:
    uv run python examples/games/coin_runner.py --headless --frames 1

Controls when interactive:
    Hold space, W, up arrow, or mouse for a higher jump.
    R restarts after a crash.
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
from gummysnake.exceptions import BackendCapabilityError

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/games/coin_runner.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

CANVAS_WIDTH = 760
CANVAS_HEIGHT = 420
GROUND_TOP = 340.0
GROUND_Y = GROUND_TOP - 33.0
RUNNER_X = 132.0
RUNNER_WIDTH = 48.0
RUNNER_HEIGHT = 66.0
GRAVITY = 0.68
JUMP_GRAVITY = 1.55
JUMP_SPEED = -15.0
JUMP_BUFFER_FRAMES = 7
GROUNDED_GRACE_FRAMES = 5
MAX_FALL_SPEED = 16.0
START_SAFE_DISTANCE = 1200.0
WORLD_LENGTH = 2800.0


@dataclass
class Pickup:
    x: float
    y: float
    value: int
    bob_phase: float
    kind: str = "coin"
    taken: bool = False

    @property
    def radius(self) -> float:
        return 18.0


@dataclass
class Hazard:
    x: float
    y: float
    width: float
    height: float
    kind: str
    passed: bool = False


@dataclass
class Platform:
    x: float
    y: float
    width: float


@dataclass
class Gap:
    x: float
    width: float


@dataclass
class Burst:
    x: float
    y: float
    age: int = 0


class CoinRunner(gs.Sketch):
    def __init__(self) -> None:
        super().__init__(headless=ARGS.headless)
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
        self.current_gravity = GRAVITY
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
        save_once(ARGS, gs.frame_count(), gs.save_canvas)

    def key_pressed(self, event: KeyboardEvent) -> None:
        key = _key_name(event)
        self.keys.add(key)
        if key in {"space", "up", "w"}:
            self._queue_jump()
        if key == "r" and self.game_over:
            self._reset_game()

    def key_released(self, event: KeyboardEvent) -> None:
        key = _key_name(event)
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

    def _reset_game(self) -> None:
        self.runner_y = GROUND_Y
        self.previous_runner_y = GROUND_Y
        self.runner_vy = 0.0
        self.jump_buffer_frames = 0
        self.grounded_grace_frames = GROUNDED_GRACE_FRAMES
        self.jump_held = False
        self.jump_state = "grounded"
        self.current_gravity = GRAVITY
        self.scroll = 0.0
        self.speed = 4.3
        self.score = 0
        self.coins = 0
        self.combo = 0
        self.lives = 3
        self.shield = 0
        self.invulnerable = 90
        self.game_over = False
        self.platforms = self._build_platforms()
        self.gaps = self._build_gaps()
        self.pickups = self._build_pickups()
        self.hazards = self._build_hazards()
        self.bursts.clear()

    def _queue_jump(self) -> None:
        self.jump_buffer_frames = JUMP_BUFFER_FRAMES
        self.jump_held = True
        self._try_start_jump()

    def _release_jump(self) -> None:
        if self.jump_state == "jumping" and self.runner_vy < 0:
            self.current_gravity = JUMP_GRAVITY

    def _try_start_jump(self) -> bool:
        if self.jump_buffer_frames <= 0:
            return False
        if self._current_floor() is None and self.grounded_grace_frames <= 0:
            return False
        self.runner_vy = JUMP_SPEED
        self.jump_buffer_frames = 0
        self.grounded_grace_frames = 0
        self.jump_held = True
        self.jump_state = "jumping"
        self.current_gravity = GRAVITY
        return True

    def _update(self) -> None:
        self.scroll += self.speed
        self.speed = min(8.4, self.speed + 0.0027)
        self.score += 1
        if self.invulnerable > 0:
            self.invulnerable -= 1

        self._update_runner()
        self._update_pickups()
        self._update_hazards()
        self._update_bursts()
        self._recycle_world()

    def _update_runner(self) -> None:
        self.previous_runner_y = self.runner_y
        if self.jump_buffer_frames > 0:
            self.jump_buffer_frames -= 1
        self._try_start_jump()
        self.jump_held = self.jump_held or any(key in self.keys for key in {"space", "up", "w"})
        if self.jump_state == "jumping" and self.runner_vy >= 0:
            self.jump_state = "falling"
            self.current_gravity = GRAVITY
        self.runner_vy += self.current_gravity
        if self.jump_state == "jumping" and self.runner_vy >= 0:
            self.jump_state = "falling"
            self.current_gravity = GRAVITY
        self.runner_vy = min(MAX_FALL_SPEED, self.runner_vy)

        next_y = self.runner_y + self.runner_vy
        floor = self._landing_floor(next_y)
        if floor is not None:
            self.runner_y = floor
            self.runner_vy = 0.0
            self.grounded_grace_frames = GROUNDED_GRACE_FRAMES
            self.jump_state = "grounded"
            self.current_gravity = GRAVITY
            self._try_start_jump()
        else:
            self.runner_y = next_y
            if self.grounded_grace_frames > 0:
                self.grounded_grace_frames -= 1
            elif self.jump_state == "grounded":
                self.jump_state = "falling"
                self.current_gravity = GRAVITY

        if self.runner_y > CANVAS_HEIGHT + 70:
            self._hit_runner()
            self.runner_y = GROUND_Y - 160
            self.runner_vy = -4.0
            self.grounded_grace_frames = 0
            self.jump_state = "falling"
            self.current_gravity = GRAVITY

    def _update_pickups(self) -> None:
        for pickup in self.pickups:
            while pickup.x - self.scroll < -120:
                pickup.x += WORLD_LENGTH
                pickup.taken = False
                pickup.y = _pickup_height(int(pickup.x // 70))
            if pickup.taken:
                continue
            sx = pickup.x - self.scroll
            sy = pickup.y + math.sin(gs.frame_count() * 0.08 + pickup.bob_phase) * 7.0
            if _circle_rect_collision(sx, sy, pickup.radius, RUNNER_X, self.runner_y, 42, 58):
                pickup.taken = True
                self.combo += 1
                if pickup.kind == "shield":
                    self.shield = min(3, self.shield + 1)
                else:
                    self.coins += 1
                self.score += pickup.value + self.combo * 25
                self.bursts.append(Burst(sx, sy))
                self._play_pickup_sound()

    def _update_hazards(self) -> None:
        for hazard in self.hazards:
            while hazard.x - self.scroll < -160:
                hazard.x += WORLD_LENGTH
                hazard.passed = False
            sx = hazard.x - self.scroll
            if not hazard.passed and sx + hazard.width / 2 < RUNNER_X - RUNNER_WIDTH / 2:
                hazard.passed = True
                self.score += 45
            if self.invulnerable > 0:
                continue
            if _rects_overlap(
                RUNNER_X,
                self.runner_y,
                RUNNER_WIDTH,
                RUNNER_HEIGHT,
                sx,
                hazard.y,
                hazard.width,
                hazard.height,
            ):
                self._hit_runner()
                hazard.passed = True

    def _hit_runner(self) -> None:
        self.combo = 0
        self.invulnerable = 84
        self.bursts.append(Burst(RUNNER_X, self.runner_y - 26))
        if self.shield > 0:
            self.shield -= 1
            self.score = max(0, self.score - 80)
            return
        self.lives -= 1
        self.score = max(0, self.score - 180)
        if self.lives <= 0:
            self.game_over = True
            self.best = max(self.best, self.score)

    def _update_bursts(self) -> None:
        self.bursts = [burst for burst in self.bursts if burst.age < 24]
        for burst in self.bursts:
            burst.age += 1

    def _recycle_world(self) -> None:
        for platform in self.platforms:
            while platform.x + platform.width / 2 - self.scroll < -180:
                platform.x += WORLD_LENGTH
        for gap in self.gaps:
            while gap.x + gap.width / 2 - self.scroll < -180:
                gap.x += WORLD_LENGTH

    def _over_gap(self) -> bool:
        for gap in self.gaps:
            left = gap.x - gap.width / 2 - self.scroll
            right = gap.x + gap.width / 2 - self.scroll
            if left + 18 <= RUNNER_X <= right - 18:
                return True
        return False

    def _current_floor(self) -> float | None:
        for floor in self._candidate_floors():
            if abs(self.runner_y - floor) <= 1.0 and self.runner_vy >= 0:
                return floor
        return None

    def _landing_floor(self, next_y: float) -> float | None:
        previous_bottom = self.previous_runner_y + RUNNER_HEIGHT / 2
        next_bottom = next_y + RUNNER_HEIGHT / 2
        for platform in sorted(self.platforms, key=lambda item: item.y):
            floor = platform.y - RUNNER_HEIGHT / 2
            left = platform.x - platform.width / 2 - self.scroll
            right = platform.x + platform.width / 2 - self.scroll
            if not left <= RUNNER_X <= right:
                continue
            if previous_bottom <= platform.y <= next_bottom:
                return floor
        if not self._over_gap() and previous_bottom <= GROUND_TOP <= next_bottom:
            return GROUND_Y
        return None

    def _candidate_floors(self) -> list[float]:
        floors = [] if self._over_gap() else [GROUND_Y]
        for platform in self.platforms:
            left = platform.x - platform.width / 2 - self.scroll
            right = platform.x + platform.width / 2 - self.scroll
            if left <= RUNNER_X <= right:
                floors.append(platform.y - RUNNER_HEIGHT / 2)
        return floors

    def _build_pickups(self) -> list[Pickup]:
        pickups: list[Pickup] = []
        for index, platform in enumerate(self.platforms):
            if index % 3 == 0:
                pickups.append(
                    Pickup(platform.x, platform.y - 54, 130, index * 0.71, kind="shield")
                )
                continue
            pickups.append(
                Pickup(platform.x - platform.width * 0.26, platform.y - 48, 85, index * 0.71)
            )
            pickups.append(
                Pickup(platform.x + platform.width * 0.12, platform.y - 72, 85, index * 0.91)
            )
        for index in range(12):
            x = 360 + index * 215
            pickups.append(Pickup(float(x), _pickup_height(index), 75, index * 0.53))
        return pickups

    def _build_hazards(self) -> list[Hazard]:
        hazards: list[Hazard] = []
        specs = [
            (START_SAFE_DISTANCE + 80, "barrier"),
            (START_SAFE_DISTANCE + 520, "ufo"),
            (START_SAFE_DISTANCE + 895, "gate"),
            (START_SAFE_DISTANCE + 1200, "ufo"),
            (START_SAFE_DISTANCE + 1435, "barrier"),
            (START_SAFE_DISTANCE + 1670, "gate"),
        ]
        for x, kind in specs:
            if kind == "ufo":
                hazards.append(Hazard(float(x), GROUND_TOP - 128, 66, 46, kind))
            elif kind == "gate":
                hazards.append(Hazard(float(x), GROUND_TOP - 34, 54, 68, kind))
            else:
                hazards.append(Hazard(float(x), GROUND_TOP - 21, 62, 42, kind))
        for platform_index in (3, 5, 6, 8):
            platform = self.platforms[platform_index]
            x_offset = -platform.width * 0.22 if platform_index % 2 else platform.width * 0.22
            hazards.append(
                Hazard(
                    platform.x + x_offset,
                    platform.y - 17,
                    48,
                    34,
                    "barrier",
                )
            )
        return hazards

    def _build_platforms(self) -> list[Platform]:
        specs = [
            (430, 280, 150),
            (695, 236, 170),
            (1010, 292, 145),
            (1260, 250, 180),
            (1575, 205, 150),
            (1840, 278, 190),
            (2140, 230, 165),
            (2450, 286, 180),
            (2685, 246, 145),
        ]
        return [Platform(float(x), float(y), float(width)) for x, y, width in specs]

    def _build_gaps(self) -> list[Gap]:
        specs = [
            (1500, 150),
            (1900, 170),
            (2250, 145),
            (2530, 155),
            (2750, 145),
        ]
        return [Gap(float(x), float(width)) for x, width in specs]

    def _draw_scene(self) -> None:
        self._draw_background()
        self._draw_platforms()
        self._draw_pickups()
        self._draw_hazards()
        self._draw_runner()
        self._draw_bursts()
        self._draw_hud()

    def _draw_background(self) -> None:
        gs.background(104, 185, 218)
        gs.no_stroke()

        gs.fill(255, 245, 174, 210)
        gs.circle(655, 76, 54)
        gs.fill(238, 248, 255, 220)
        for index in range(6):
            x = (index * 190 - self.scroll * 0.18) % (CANVAS_WIDTH + 190) - 90
            y = 74 + (index % 3) * 24
            gs.circle(x, y, 28)
            gs.circle(x + 26, y + 5, 38)
            gs.circle(x + 58, y, 25)

        gs.fill(77, 142, 108)
        for index in range(15):
            x = (index * 74 - self.scroll * 0.45) % (CANVAS_WIDTH + 90) - 45
            height = 44 + (index % 4) * 16
            gs.triangle(x, GROUND_TOP + 8, x + 38, GROUND_TOP - height, x + 76, GROUND_TOP + 8)

        gs.fill(50, 112, 76)
        gs.rect(0, GROUND_TOP, CANVAS_WIDTH, CANVAS_HEIGHT - GROUND_TOP)
        gs.fill(39, 84, 58)
        for index in range(18):
            x = (index * 54 - self.scroll * 0.92) % (CANVAS_WIDTH + 70) - 35
            gs.rect(x, GROUND_TOP + 14 + (index % 2) * 10, 34, 6)
        self._draw_gaps()

    def _draw_gaps(self) -> None:
        for gap in self.gaps:
            x = gap.x - self.scroll
            if not -gap.width < x < CANVAS_WIDTH + gap.width:
                continue
            gs.fill(23, 44, 43)
            gs.rect(x - gap.width / 2, GROUND_TOP - 2, gap.width, CANVAS_HEIGHT - GROUND_TOP + 4)
            gs.fill(16, 29, 35)
            gs.rect(x - gap.width / 2 + 10, GROUND_TOP + 10, gap.width - 20, 54)

    def _draw_platforms(self) -> None:
        for platform in self.platforms:
            x = platform.x - self.scroll
            if not -platform.width < x < CANVAS_WIDTH + platform.width:
                continue
            gs.fill(58, 100, 75)
            gs.rect(x - platform.width / 2, platform.y, platform.width, 16)
            gs.fill(83, 154, 102)
            gs.rect(x - platform.width / 2, platform.y - 7, platform.width, 9)
            gs.fill(35, 74, 52)
            gs.rect(x - platform.width / 2 + 9, platform.y + 16, platform.width - 18, 5)

    def _draw_pickups(self) -> None:
        assert self.pickup_image is not None
        for pickup in self.pickups:
            if pickup.taken:
                continue
            x = pickup.x - self.scroll
            if not -60 < x < CANVAS_WIDTH + 60:
                continue
            y = pickup.y + math.sin(gs.frame_count() * 0.08 + pickup.bob_phase) * 7.0
            pulse = 1.0 + math.sin(gs.frame_count() * 0.14 + pickup.bob_phase) * 0.08
            if pickup.kind == "shield":
                gs.fill(109, 223, 255, 80)
                gs.circle(x, y, 48 * pulse)
                gs.image(self.pickup_image, x, y, 39 * pulse, 39 * pulse)
            else:
                gs.fill(255, 220, 73, 100)
                gs.circle(x, y, 42 * pulse)
                gs.fill(255, 190, 45)
                gs.circle(x, y, 26 * pulse)
                gs.fill(255, 246, 150)
                gs.circle(x - 5, y - 5, 8 * pulse)

    def _draw_hazards(self) -> None:
        for hazard in self.hazards:
            x = hazard.x - self.scroll
            if not -90 < x < CANVAS_WIDTH + 90:
                continue
            if hazard.kind == "ufo":
                self._draw_ufo_hazard(x, hazard)
            elif hazard.kind == "gate":
                self._draw_gate_hazard(x, hazard)
            else:
                self._draw_barrier_hazard(x, hazard)

    def _draw_ufo_hazard(self, x: float, hazard: Hazard) -> None:
        assert self.ufo is not None
        bob = math.sin(gs.frame_count() * 0.09 + hazard.x * 0.03) * 6
        gs.image(self.ufo, x, hazard.y + bob, hazard.width, hazard.height)
        gs.stroke(105, 244, 255, 120)
        gs.stroke_weight(2)
        gs.line(x, hazard.y + bob + 18, x, GROUND_TOP + 3)
        gs.no_stroke()

    def _draw_gate_hazard(self, x: float, hazard: Hazard) -> None:
        gs.fill(44, 48, 74)
        gs.rect(x - hazard.width / 2, hazard.y - hazard.height / 2, hazard.width, hazard.height)
        gs.fill(255, 204, 86)
        gs.rect(x - hazard.width / 2 + 8, hazard.y - hazard.height / 2 + 8, 10, hazard.height - 16)
        gs.rect(x + hazard.width / 2 - 18, hazard.y - hazard.height / 2 + 8, 10, hazard.height - 16)

    def _draw_barrier_hazard(self, x: float, hazard: Hazard) -> None:
        gs.fill(86, 67, 68)
        gs.rect(x - hazard.width / 2, hazard.y - hazard.height / 2, hazard.width, hazard.height)
        gs.fill(255, 212, 94)
        for offset in (-20, 0, 20):
            gs.triangle(
                x + offset - 10,
                hazard.y - 20,
                x + offset,
                hazard.y - 34,
                x + offset + 10,
                hazard.y - 20,
            )

    def _draw_runner(self) -> None:
        assert self.idle is not None
        assert self.run_strip is not None
        if self.invulnerable > 0 and gs.frame_count() % 10 < 4 and self.shield == 0:
            return

        airborne = self._current_floor() is None
        if airborne:
            image = self.idle
            frame_count = 4
        else:
            image = self.run_strip
            frame_count = 6

        frame_w = image.width // frame_count
        frame = (gs.frame_count() // (6 if airborne else 4)) % frame_count
        source_x = frame * frame_w
        gs.image(
            image,
            RUNNER_X,
            self.runner_y,
            74,
            74,
            source_x,
            0,
            frame_w,
            image.height,
        )

        if self.shield > 0:
            gs.no_fill()
            gs.stroke(90, 225, 255, 95 + self.shield * 36)
            gs.stroke_weight(3)
            gs.circle(RUNNER_X, self.runner_y - 5, 78 + self.shield * 5)
            gs.no_stroke()

    def _draw_bursts(self) -> None:
        for burst in self.bursts:
            alpha = max(0, 210 - burst.age * 8)
            radius = 12 + burst.age * 2.4
            gs.no_fill()
            gs.stroke(255, 255, 255, alpha)
            gs.stroke_weight(2)
            gs.circle(burst.x, burst.y, radius)
            gs.no_stroke()

    def _draw_hud(self) -> None:
        gs.no_stroke()
        gs.fill(20, 28, 40, 220)
        gs.rect(18, 18, 340, 74)
        gs.fill(255, 255, 255, 240)
        gs.text_size(17)
        gs.text(f"Score {self.score}", 32, 42)
        gs.text(f"Lives {self.lives}   Coins {self.coins}   Shield {self.shield}", 32, 67)
        if self.combo >= 2:
            gs.fill(255, 238, 138, 245)
            gs.text(f"Combo x{self.combo}", 283, 42)

        gs.fill(20, 28, 40, 190)
        gs.text_size(15)
        gs.text("Hold jump: space/up/click", 24, CANVAS_HEIGHT - 18)

        if not self.sound_available:
            gs.fill(20, 28, 40, 150)
            gs.text("Audio unavailable", CANVAS_WIDTH - 148, CANVAS_HEIGHT - 18)

        if self.game_over:
            gs.fill(10, 14, 22, 185)
            gs.rect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
            gs.fill(255, 255, 255, 245)
            gs.text_size(36)
            gs.text("CRASHED", CANVAS_WIDTH / 2 - 78, CANVAS_HEIGHT / 2 - 32)
            gs.text_size(18)
            gs.text(
                f"Score {self.score}   Best {self.best}",
                CANVAS_WIDTH / 2 - 86,
                CANVAS_HEIGHT / 2 + 2,
            )
            gs.text(
                "Press R or click to run again",
                CANVAS_WIDTH / 2 - 118,
                CANVAS_HEIGHT / 2 + 34,
            )

    def _play_pickup_sound(self) -> None:
        if self.sound is None or not self.sound_available or ARGS.headless:
            return
        try:
            self.sound.play()
        except BackendCapabilityError:
            self.sound_available = False


def _pickup_height(index: int) -> float:
    pattern = (
        GROUND_TOP - 50,
        GROUND_TOP - 92,
        GROUND_TOP - 138,
        GROUND_TOP - 78,
        GROUND_TOP - 118,
    )
    return pattern[index % len(pattern)]


def _rects_overlap(
    ax: float,
    ay: float,
    aw: float,
    ah: float,
    bx: float,
    by: float,
    bw: float,
    bh: float,
) -> bool:
    return abs(ax - bx) * 2 < aw + bw and abs(ay - by) * 2 < ah + bh


def _circle_rect_collision(
    circle_x: float,
    circle_y: float,
    radius: float,
    rect_x: float,
    rect_y: float,
    rect_width: float,
    rect_height: float,
) -> bool:
    half_w = rect_width / 2
    half_h = rect_height / 2
    closest_x = _clamp(circle_x, rect_x - half_w, rect_x + half_w)
    closest_y = _clamp(circle_y, rect_y - half_h, rect_y + half_h)
    return math.hypot(circle_x - closest_x, circle_y - closest_y) <= radius


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _key_name(event: KeyboardEvent) -> str:
    if event.key == " ":
        return "space"
    if event.key:
        return event.key.lower()
    if event.key_code == gs.UP_ARROW:
        return "up"
    return str(event.key_code)


if __name__ == "__main__":
    CoinRunner().run(max_frames=ARGS.frames)
