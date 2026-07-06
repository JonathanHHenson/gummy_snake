"""Private helpers for Python-side ECS query materialization."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.actions import Action, action_write_targets
from gummysnake.ecs.expressions import Expression, FieldExpression, QueryProxy, expression_queries
from gummysnake.ecs.runtime_views import EntityView
from gummysnake.ecs.specs import ChangeTerm, QuerySpec, TagTerm, WithoutTerm
from gummysnake.ecs.world_helpers import _component_key
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def match_query(world: EcsWorld, spec: QuerySpec) -> list[EntityView]:
    """Materialize Python entity views for a query specification."""
    components: list[type[Any]] = []
    tags: list[object] = []
    excluded_components: list[type[Any]] = []
    excluded_tags: list[object] = []
    change_terms: list[ChangeTerm] = []
    for term in spec.terms:
        if isinstance(term, TagTerm):
            tags.append(term.value)
        elif isinstance(term, ChangeTerm):
            world.validate_schema(term.component_type)
            change_terms.append(term)
            if term.kind != "removed" and term.component_type not in components:
                components.append(term.component_type)
        elif isinstance(term, WithoutTerm):
            value = term.value
            if isinstance(value, TagTerm):
                excluded_tags.append(value.value)
            elif isinstance(value, type):
                world.validate_schema(value)
                excluded_components.append(value)
            else:
                raise SystemPlanError(f"Unsupported ecs.Without query term {value!r}.")
        elif isinstance(term, type):
            world.validate_schema(term)
            components.append(term)
        else:
            raise SystemPlanError(f"Unsupported ECS query term {term!r}.")
    matches = list(world.iter_entities(*components, tags=tags))
    if excluded_components or excluded_tags:
        matches = [
            entity
            for entity in matches
            if all(
                not world._has_component(entity.entity, component)
                for component in excluded_components
            )
            and all(
                str(tag)
                not in world._rust.entity_tags(entity.entity.index, entity.entity.generation)
                for tag in excluded_tags
            )
        ]
    if change_terms:
        matches = [
            entity for entity in matches if matches_change_terms(world, entity, change_terms)
        ]
        world._diagnostics["ecs_change_filtered_rows"] += len(matches)
    return matches


def iter_join_contexts_for(
    world: EcsWorld,
    base_ctx: dict[object, Any],
    expr: Expression,
    *,
    include_query: QueryProxy | None = None,
) -> Iterator[dict[object, Any]]:
    """Yield context dictionaries for all query combinations needed by an expression."""
    queries = expression_queries(expr)
    if include_query is not None:
        queries.add(include_query)
    yield from iter_join_contexts_for_queries(world, base_ctx, queries)


def iter_join_contexts_for_queries(
    world: EcsWorld, base_ctx: dict[object, Any], queries: Iterable[QueryProxy]
) -> Iterator[dict[object, Any]]:
    """Yield context dictionaries for every combination of currently unbound queries."""
    missing = sorted(
        (query for query in set(queries) if query not in base_ctx), key=lambda q: q.name
    )
    if not missing:
        yield dict(base_ctx)
        return
    matches = [world.match_query(cast(QuerySpec, query.spec)) for query in missing]
    for combo in itertools.product(*matches):
        joined = dict(base_ctx)
        for query, entity in zip(missing, combo, strict=True):
            joined[query] = entity
        yield joined


def write_key(
    target: FieldExpression, ctx: dict[object, Any]
) -> tuple[int, type[Any], str] | tuple[str, type[Any], str]:
    """Return the deterministic write-conflict key for a field mutation target."""
    if isinstance(target.source, QueryProxy):
        entity = ctx[target.source]
        return (entity.entity.index, target.component_type, target.field_name)
    return ("resource", target.component_type, target.field_name)


def check_parallel_children(world: EcsWorld, children: tuple[Action, ...]) -> None:
    """Validate that parallel action children do not write the same target twice."""
    seen: set[tuple[object, type[Any], str]] = set()
    for child in children:
        targets = action_write_targets(child)
        conflict = seen & targets
        if conflict:
            message = (
                "ECS do_in_parallel() children write overlapping targets; "
                "deterministic last-write-wins is used."
            )
            if world.strict:
                raise SystemPlanError(message)
            world.record_ambiguity(message)
            return
        seen.update(targets)


def materialize_udf_arg(world: EcsWorld, arg: object) -> object:
    """Convert a query proxy UDF argument into concrete entity views when needed."""
    if isinstance(arg, QueryProxy):
        return world.match_query(cast(QuerySpec, arg.spec))
    return arg


def matches_change_terms(world: EcsWorld, entity: EntityView, terms: Iterable[ChangeTerm]) -> bool:
    """Return whether an entity satisfies all requested change-detection terms."""
    for term in terms:
        key = _component_key(entity.entity, term.component_type)
        if term.kind == "added" and key not in world._added_components:
            return False
        if term.kind == "changed" and key not in world._changed_components:
            return False
        if term.kind == "removed" and key not in world._removed_components:
            return False
    return True
