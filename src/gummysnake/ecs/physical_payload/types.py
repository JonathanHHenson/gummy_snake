"""Shared types and mutable state for ECS physical payload serialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gummysnake.ecs.expressions import QueryProxy
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.systems import BuiltSystem
    from gummysnake.ecs.world import EcsWorld

BRIDGE_PLAN_VERSION = 2

type BridgeNode = dict[str, object]
type BridgePayload = dict[str, object]
type BridgeScalar = bool | int | float | str
type BridgeLiteral = (
    BridgeScalar | list["BridgeLiteral"] | tuple["BridgeLiteral", ...] | dict[str, "BridgeLiteral"]
)


@dataclass(frozen=True)
class PhysicalPlanUnsupported(Exception):
    """Raised internally when a non-UDF node cannot be serialized for Rust execution."""

    reason: str

    def __str__(self) -> str:
        return self.reason


class PayloadState:
    """Mutable payload-building state shared by focused serializers."""

    def __init__(self, world: EcsWorld, built: BuiltSystem) -> None:
        self.world = world
        self.built = built
        self.expressions: list[BridgeNode] = []
        self.actions: list[BridgeNode] = []
        self.expr_indices: dict[int, int] = {}
        self.queries: dict[str, QueryProxy] = {}
        self.loop_item_slots: dict[int, int] = {}
        self.next_loop_item_slot = 0
        self.dynamic = False
        for query in self.built.queries:
            self.register_query(query)

    def register_query(self, query: QueryProxy) -> None:
        """Remember a query referenced by the payload and reject conflicting names."""

        existing = self.queries.get(query.name)
        if existing is not None:
            if existing.spec != query.spec:
                raise SystemPlanError(
                    f"ECS query name {query.name!r} is used for incompatible specifications."
                )
            return
        self.queries[query.name] = query

    def add_expr(self, node: BridgeNode) -> int:
        """Append an expression node and return its numeric payload index."""

        self.expressions.append(node)
        return len(self.expressions) - 1

    def add_action(self, node: BridgeNode) -> int:
        """Append an action node and return its numeric payload index."""

        self.actions.append(node)
        return len(self.actions) - 1

    def mark_dynamic(self) -> None:
        """Record that the payload contains frame-specific evaluated values."""

        self.dynamic = True
