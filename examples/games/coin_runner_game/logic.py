"""Gameplay and world logic for the Coin Runner example."""

from __future__ import annotations

import argparse
import math
from typing import TYPE_CHECKING

import gummysnake as gs
from gummysnake.exceptions import BackendCapabilityError

from .constants import (
    CANVAS_HEIGHT,
    GRAVITY,
    GROUND_TOP,
    GROUND_Y,
    GROUNDED_GRACE_FRAMES,
    JUMP_BUFFER_FRAMES,
    JUMP_GRAVITY,
    JUMP_SPEED,
    MAX_FALL_SPEED,
    RUNNER_HEIGHT,
    RUNNER_WIDTH,
    RUNNER_X,
    WORLD_LENGTH,
)
from .helpers import circle_rect_collision, pickup_height, rects_overlap
from .models import Burst, Gap, Hazard, Pickup, Platform


class CoinRunnerLogicMixin:
    keys: set[str]
    runner_y: float
    previous_runner_y: float
    runner_vy: float
    jump_buffer_frames: int
    grounded_grace_frames: int
    jump_held: bool
    jump_state: str
    current_gravity: float
    scroll: float
    speed: float
    score: int
    best: int
    coins: int
    combo: int
    lives: int
    shield: int
    invulnerable: int
    game_over: bool
    pickups: list[Pickup]
    hazards: list[Hazard]
    platforms: list[Platform]
    gaps: list[Gap]
    bursts: list[Burst]
    sound: gs.Sound | None
    sound_available: bool
    args: argparse.Namespace

    if TYPE_CHECKING:

        def _build_platforms(self) -> list[Platform]: ...
        def _build_gaps(self) -> list[Gap]: ...
        def _build_pickups(self) -> list[Pickup]: ...
        def _build_hazards(self) -> list[Hazard]: ...

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
                pickup.y = pickup_height(int(pickup.x // 70))
            if pickup.taken:
                continue
            sx = pickup.x - self.scroll
            sy = pickup.y + math.sin(gs.frame_count() * 0.08 + pickup.bob_phase) * 7.0
            if circle_rect_collision(sx, sy, pickup.radius, RUNNER_X, self.runner_y, 42, 58):
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
            if rects_overlap(
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

    def _play_pickup_sound(self) -> None:
        if self.sound is None or not self.sound_available or getattr(self.args, "headless", False):
            return
        try:
            self.sound.play()
        except BackendCapabilityError:
            self.sound_available = False
