from __future__ import annotations

import builtins
from typing import Any

from gummysnake.ecs.action_model.plan_nodes import Action, DefaultAction
from gummysnake.ecs.action_model.udf import (
    RuntimeUdfDefinition,
    UdfCallExpression,
    UdfIterableDefinition,
    udf,
    udf_plan,
    validate_mutation_metadata,
)
from gummysnake.ecs.expressions import EntityExpression, FieldExpression, QueryProxy, ensure_expr
from gummysnake.ecs.expression_tools import ExpressionInput
from gummysnake.ecs.specs import EventWriterProxy
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.exceptions import SystemPlanError


# Re-export core action node types from this compatibility chunk's historical __all__.
from gummysnake.ecs.action_model.plan_nodes import (  # noqa: E402
    EntityIteratorSource,
    EventIterableSource,
    ExpressionIterableSource,
    ForEachAction,
    IterableSource,
    SystemPlan,
    UdfDefinition,
    UdfPlanDefinition,
    WhenAction,
)


def set(target: FieldExpression, value: ExpressionInput) -> DefaultAction:
    """Build an ECS action that assigns a value to a component or resource field.

    Args:
        target: Writable field expression, such as ``query.position.x`` or a resource field.
        value: Python value or ECS expression to store in the target field.

    Returns:
        A complete action node that can be added to a system plan.
    """

    if not isinstance(target, FieldExpression):
        raise SystemPlanError("ecs.set() target must be a component or resource field expression.")
    return DefaultAction("set", target=target, value=ensure_expr(value))


def add_component_action(
    entity: EntityExpression, component: DataclassInstance | type[Any]
) -> DefaultAction:
    """Build an action that adds a component to each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        component: Component type to add, or a component instance whose field values should be used.

    Returns:
        A structural action node for the system plan.
    """

    component_type = component if isinstance(component, type) else type(component)
    return DefaultAction(
        "add_component",
        entity_query=_require_entity_query(entity),
        component_type=component_type,
        component_value=None if isinstance(component, type) else component,
    )


def remove_component_action(entity: EntityExpression, component_type: type[Any]) -> DefaultAction:
    """Build an action that removes a component from each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        component_type: Component class to remove from each matched entity.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction(
        "remove_component",
        entity_query=_require_entity_query(entity),
        component_type=component_type,
    )


def add_tag_action(entity: EntityExpression, tag: EcsTag) -> DefaultAction:
    """Build an action that adds a tag to each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        tag: Tag value to add.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction("add_tag", entity_query=_require_entity_query(entity), tag=tag)


def remove_tag_action(entity: EntityExpression, tag: EcsTag) -> DefaultAction:
    """Build an action that removes a tag from each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        tag: Tag value to remove.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction("remove_tag", entity_query=_require_entity_query(entity), tag=tag)


def despawn_action(entity: EntityExpression) -> DefaultAction:
    """Build an action that despawns each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to despawn.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction("despawn", entity_query=_require_entity_query(entity))


def _require_entity_query(entity: EntityExpression) -> QueryProxy:
    if not isinstance(entity, EntityExpression):
        raise SystemPlanError(
            "ECS structural actions require query.entity from an ecs.Query parameter."
        )
    return entity.query


def emit_event(writer: EventWriterProxy, event: EcsEventValue) -> DefaultAction:
    """Build an action that sends an ECS event.

    Args:
        writer: Event writer proxy received by a system function.
        event: Event dataclass instance to enqueue.

    Returns:
        An event-emission action node for the system plan.
    """

    if not isinstance(writer, EventWriterProxy):
        raise SystemPlanError("ecs.emit_event() expects an ecs.EventWriter[...] parameter.")
    return DefaultAction("emit_event", event_writer=writer, event_value=event)


from gummysnake.ecs.action_tools.building import (  # noqa: E402
    active_build_session,
    append_action,
    build_session,
    conditional,
    do,
    do_in_order,
    do_in_parallel,
    for_each,
    otherwise,
    when,
)


def action_write_targets(action: Action) -> builtins.set[tuple[object, type[Any], str]]:
    """Return field or structural targets written by an action tree.

    Args:
        action: Root action node to inspect.

    Returns:
        A set of ``(source, component_type, field_name)`` tuples used for conflict checks.
    """

    from gummysnake.ecs.action_tools.analysis import action_write_targets as analyze

    return analyze(action)


def action_query_refs(action: Action) -> builtins.set[QueryProxy]:
    """Return query proxies referenced by an action tree.

    Args:
        action: Root action node to inspect.

    Returns:
        Query proxies used by the action or any nested child action.
    """

    from gummysnake.ecs.action_tools.analysis import action_query_refs as analyze

    return analyze(action)


__all__ = [
    "Action",
    "DefaultAction",
    "EntityIteratorSource",
    "EventIterableSource",
    "ExpressionIterableSource",
    "ForEachAction",
    "IterableSource",
    "RuntimeUdfDefinition",
    "SystemPlan",
    "UdfCallExpression",
    "UdfDefinition",
    "UdfIterableDefinition",
    "UdfPlanDefinition",
    "WhenAction",
    "active_build_session",
    "add_component_action",
    "add_tag_action",
    "append_action",
    "build_session",
    "conditional",
    "despawn_action",
    "do",
    "do_in_order",
    "do_in_parallel",
    "emit_event",
    "for_each",
    "otherwise",
    "remove_component_action",
    "remove_tag_action",
    "set",
    "udf",
    "udf_plan",
    "validate_mutation_metadata",
    "when",
]
