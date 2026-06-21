"""World construction helpers for the Coin Runner example."""

from __future__ import annotations

from .constants import GROUND_TOP, START_SAFE_DISTANCE
from .helpers import pickup_height
from .models import Gap, Hazard, Pickup, Platform


class CoinRunnerWorldMixin:
    platforms: list[Platform]

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
            pickups.append(Pickup(float(x), pickup_height(index), 75, index * 0.53))
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
            hazards.append(Hazard(platform.x + x_offset, platform.y - 17, 48, 34, "barrier"))
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
