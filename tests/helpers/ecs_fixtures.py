from __future__ import annotations

import inspect
from collections.abc import Iterable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Annotated, cast

import pytest

from gummysnake import Sketch, ecs
from gummysnake.ecs import canvas as ca
from gummysnake.ecs import types as ecs_t
from gummysnake.ecs.physical_payload import BRIDGE_PLAN_VERSION
from gummysnake.ecs.world_facade import EcsWorld
from gummysnake.exceptions import (
    BackendCapabilityError,
    ComponentSchemaError,
    StaleEntityError,
    SystemPlanError,
)
from gummysnake.plugins import Plugin, clear_plugins, install_plugin
from gummysnake.rust import ecs as rust_ecs

HERO = "Hero"
PLATFORM = "Platform"


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    dx: float
    dy: float


@dataclass
class SensorOrigin:
    x: float
    y: float


@dataclass
class Box:
    width: Annotated[int, ecs_t.UInt16]
    height: Annotated[int, ecs_t.UInt16]


@dataclass
class Counter:
    value: int


@dataclass
class Label:
    value: str


@dataclass
class Trail:
    samples: Annotated[list[float], ecs_t.List(ecs_t.Float64)]


@dataclass
class VecPosition:
    xy: Annotated[tuple[float, float], ecs_t.Vec2F32]


@dataclass
class Ping:
    amount: int


__all__ = [
    "Annotated",
    "BackendCapabilityError",
    "BRIDGE_PLAN_VERSION",
    "Box",
    "ComponentSchemaError",
    "Counter",
    "HERO",
    "Iterable",
    "Label",
    "PLATFORM",
    "Ping",
    "Plugin",
    "Position",
    "SensorOrigin",
    "SimpleNamespace",
    "Sketch",
    "StaleEntityError",
    "SystemPlanError",
    "Trail",
    "VecPosition",
    "Velocity",
    "ca",
    "cast",
    "clear_plugins",
    "dataclass",
    "ecs",
    "ecs_t",
    "inspect",
    "install_plugin",
    "pytest",
    "rust_ecs",
    "EcsWorld",
]
