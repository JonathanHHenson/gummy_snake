"""Top-level builder for Rust ECS physical-plan bridge payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gummysnake.ecs.physical_payload.actions import ActionSerializer
from gummysnake.ecs.physical_payload.expressions import ExpressionSerializer
from gummysnake.ecs.physical_payload.queries import query_payload
from gummysnake.ecs.physical_payload.types import BRIDGE_PLAN_VERSION, BridgePayload, PayloadState

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.systems import BuiltSystem
    from gummysnake.ecs.world import EcsWorld


class PhysicalPayloadBuilder:
    """Build one Rust bridge payload from a validated ECS system plan."""

    def __init__(self, world: EcsWorld, built: BuiltSystem) -> None:
        self.state = PayloadState(world, built)
        self.expressions = ExpressionSerializer(self.state)
        self.actions = ActionSerializer(self.state, self.expressions)

    def build(self) -> BridgePayload:
        """Serialize queries, expressions, actions, and the root action into a payload."""

        root_action = self.actions.serialize_action(self.state.built.plan.action)
        queries = [query_payload(self.state, query) for query in self.state.queries.values()]
        return {
            "version": BRIDGE_PLAN_VERSION,
            "schema_fingerprint": self.state.world._rust.schema_fingerprint(),
            "queries": queries,
            "expressions": self.state.expressions,
            "actions": self.state.actions,
            "root_action": root_action,
            "dynamic": self.state.dynamic,
        }


def build_physical_payload(world: EcsWorld, built: BuiltSystem) -> BridgePayload:
    """Build a Rust bridge payload or raise ``PhysicalPlanUnsupported``."""

    return PhysicalPayloadBuilder(world, built).build()
