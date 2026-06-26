from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SceneState:
    sprites: list[Any] = field(default_factory=list)
    churn_pixels: bytes = b""
    shots: list[list[float]] = field(default_factory=list)
    asteroids: list[list[float]] = field(default_factory=list)
    stamp: Any = None
    stress_primitive_records: dict[int, list[tuple[Any, ...]]] = field(default_factory=dict)
    stress_sprite_terms: dict[int, list[tuple[Any, ...]]] = field(default_factory=dict)
    stress_sprite_payloads: dict[int, bytes] = field(default_factory=dict)
    stress_overlay_labels: list[tuple[str, int, int]] | None = None
