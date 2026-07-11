"""Legacy forwarding adapter for the canonical canvas benchmark scenarios.

The adapter exists because prior focused tests import this path and patch its module
state. Scenario implementation remains in :mod:`canvas_backend_perf.scenes`.
"""

from __future__ import annotations

from canvas_backend_perf import scenes as _scenes

gs = _scenes.gs
require_context = _scenes.require_context
sprites = _scenes.sprites
churn_pixels = _scenes.churn_pixels
shots = _scenes.shots
asteroids = _scenes.asteroids
stamp = _scenes.stamp
stress_primitive_records = _scenes.stress_primitive_records
stress_sprite_terms = _scenes.stress_sprite_terms
stress_sprite_payloads = _scenes.stress_sprite_payloads
stress_overlay_labels = _scenes.stress_overlay_labels
_sprite = _scenes._sprite
_reset_asteroids = _scenes._reset_asteroids


def _sync_to_canonical() -> None:
    _scenes.gs = gs
    _scenes.require_context = require_context
    _scenes.sprites = sprites
    _scenes.churn_pixels = churn_pixels
    _scenes.shots = shots
    _scenes.asteroids = asteroids
    _scenes.stamp = stamp
    _scenes.stress_primitive_records = stress_primitive_records
    _scenes.stress_sprite_terms = stress_sprite_terms
    _scenes.stress_sprite_payloads = stress_sprite_payloads
    _scenes.stress_overlay_labels = stress_overlay_labels
    _scenes._sprite = _sprite
    _scenes._reset_asteroids = _reset_asteroids


def _sync_from_canonical() -> None:
    global sprites, churn_pixels, shots, asteroids, stamp
    global \
        stress_primitive_records, \
        stress_sprite_terms, \
        stress_sprite_payloads, \
        stress_overlay_labels
    sprites = _scenes.sprites
    churn_pixels = _scenes.churn_pixels
    shots = _scenes.shots
    asteroids = _scenes.asteroids
    stamp = _scenes.stamp
    stress_primitive_records = _scenes.stress_primitive_records
    stress_sprite_terms = _scenes.stress_sprite_terms
    stress_sprite_payloads = _scenes.stress_sprite_payloads
    stress_overlay_labels = _scenes.stress_overlay_labels


def setup_scene(variant: str) -> None:
    _sync_to_canonical()
    _scenes.setup_scene(variant)
    _sync_from_canonical()


def draw_scene(variant: str) -> None:
    _sync_to_canonical()
    _scenes.draw_scene(variant)
    _sync_from_canonical()
