# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Rendering helpers for the Coin Runner example."""

from __future__ import annotations

import math

import gummysnake as gs

from .constants import CANVAS_HEIGHT, CANVAS_WIDTH, GROUND_TOP, RUNNER_X
from .models import Burst, Gap, Hazard, Pickup, Platform


class CoinRunnerRenderingMixin:
    idle: gs.Image | None
    run_strip: gs.Image | None
    pickup_image: gs.Image | None
    ufo: gs.Image | None
    runner_y: float
    scroll: float
    score: int
    best: int
    coins: int
    combo: int
    lives: int
    shield: int
    invulnerable: int
    game_over: bool
    sound_available: bool
    pickups: list[Pickup]
    hazards: list[Hazard]
    platforms: list[Platform]
    gaps: list[Gap]
    bursts: list[Burst]

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
        image = self.idle if airborne else self.run_strip
        frame_count = 4 if airborne else 6
        frame_w = image.width // frame_count
        frame = (gs.frame_count() // (6 if airborne else 4)) % frame_count
        source_x = frame * frame_w
        gs.image(image, RUNNER_X, self.runner_y, 74, 74, source_x, 0, frame_w, image.height)

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
            gs.text("Press R or click to run again", CANVAS_WIDTH / 2 - 118, CANVAS_HEIGHT / 2 + 34)
