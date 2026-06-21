"""Data models for the Asteroids example."""

from __future__ import annotations

from dataclasses import dataclass


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
