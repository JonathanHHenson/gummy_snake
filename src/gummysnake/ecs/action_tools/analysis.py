"""Static analysis helpers for ECS action trees."""

from __future__ import annotations

import builtins
from typing import Any

from gummysnake.ecs.actions import (
    Action,
    DefaultAction,
    ExpressionIterableSource,
    ForEachAction,
    WhenAction,
)
from gummysnake.ecs.expressions import QueryProxy, expression_queries


def action_write_targets(action: Action) -> builtins.set[tuple[object, type[Any], str]]:
    targets: builtins.set[tuple[object, type[Any], str]] = builtins.set()
    if isinstance(action, DefaultAction):
        if action.kind == "set" and action.target is not None:
            targets.add(
                (action.target.source, action.target.component_type, action.target.field_name)
            )
        elif (
            action.kind in {"add_component", "remove_component"}
            and action.component_type is not None
        ):
            targets.add((action.entity_query, action.component_type, "*structural*"))
        elif action.kind in {"add_tag", "remove_tag", "despawn"}:
            targets.add((action.entity_query, object, "*structural*"))
        for child in action.children:
            targets.update(action_write_targets(child))
    elif isinstance(action, WhenAction):
        for _, branch in action.branches:
            targets.update(action_write_targets(branch))
        if action.otherwise_action is not None:
            targets.update(action_write_targets(action.otherwise_action))
    elif isinstance(action, ForEachAction):
        targets.update(action_write_targets(action.body))
    return targets


def action_query_refs(action: Action) -> builtins.set[QueryProxy]:
    refs: builtins.set[QueryProxy] = builtins.set()
    if isinstance(action, DefaultAction):
        if action.target is not None and isinstance(action.target.source, QueryProxy):
            refs.add(action.target.source)
        if action.entity_query is not None:
            refs.add(action.entity_query)
        if action.value is not None:
            refs.update(expression_queries(action.value))
        for child in action.children:
            refs.update(action_query_refs(child))
    elif isinstance(action, WhenAction):
        for condition, branch in action.branches:
            refs.update(expression_queries(condition))
            refs.update(action_query_refs(branch))
        if action.otherwise_action is not None:
            refs.update(action_query_refs(action.otherwise_action))
    elif isinstance(action, ForEachAction):
        if isinstance(action.source, ExpressionIterableSource):
            refs.update(expression_queries(action.source.expression))
        refs.update(action_query_refs(action.body))
    return refs


