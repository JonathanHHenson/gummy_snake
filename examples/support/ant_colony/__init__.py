"""Deterministic, runtime-neutral core for the ant-colony example and benchmark."""

from __future__ import annotations

from .configuration import ANTS_PER_COLONY
from .world import populate_world, update_pheromone_query

__all__ = ["ANTS_PER_COLONY", "populate_world", "update_pheromone_query"]
