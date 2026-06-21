"""Data models for the Coin Runner example."""

from __future__ import annotations

from dataclasses import dataclass


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
