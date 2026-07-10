"""Private helpers for ECS system group scheduling order."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from gummysnake.ecs.runtime_views import _ScheduledSystem, _SystemSetConfig
from gummysnake.exceptions import SystemPlanError

_GROUP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class _GroupGraph:
    """Insertion-ordered group dependency graph used for one schedule build."""

    groups: dict[str, int] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=dict)
    incoming: dict[str, set[str]] = field(default_factory=dict)

    def note(self, name: str) -> str:
        """Register a validated group and return its normalized name."""
        group_name = validate_group_name(name)
        if group_name not in self.groups:
            self.groups[group_name] = len(self.groups)
            self.edges[group_name] = set()
            self.incoming[group_name] = set()
        return group_name

    def add_edge(self, source: str, target: str) -> None:
        """Record one directed group ordering edge."""
        source_name = self.note(source)
        target_name = self.note(target)
        if source_name == target_name:
            raise SystemPlanError(f"ECS system group {source_name!r} cannot depend on itself.")
        self.edges[source_name].add(target_name)
        self.incoming[target_name].add(source_name)


def validate_group_name(name: str) -> str:
    """Return a valid ECS group name or raise a user-facing scheduling error."""

    normalized = str(name)
    if not _GROUP_NAME_RE.fullmatch(normalized):
        raise SystemPlanError(
            f"ECS system group name {normalized!r} must be snake_case: "
            "lowercase letters, digits, and underscores, starting with a letter."
        )
    return normalized


def implicit_system_group_name(system_name: str) -> str:
    """Return the default group name for a system without an explicit group."""

    snake_name = re.sub(r"[^a-z0-9_]+", "_", system_name.lower()).strip("_")
    if not snake_name:
        snake_name = "unnamed"
    return validate_group_name(f"system_{snake_name}")


def normalize_group_names(group: str | Iterable[Any]) -> tuple[str, ...]:
    """Return validated group memberships from one group name or a sequence."""

    group_names: tuple[str, ...]
    if isinstance(group, str):
        group_names = (validate_group_name(group),)
    else:
        try:
            group_names = tuple(validate_group_name(str(name)) for name in group)
        except TypeError as exc:
            raise SystemPlanError(
                "ECS system group must be a group name or a sequence of group names."
            ) from exc
    if not group_names:
        raise SystemPlanError("ECS system group list cannot be empty.")
    if len(set(group_names)) != len(group_names):
        raise SystemPlanError("ECS system group names must be unique per system.")
    return group_names


def scheduled_system_group_names(system: _ScheduledSystem) -> tuple[str, ...]:
    """Return the group memberships for a scheduled system."""

    return system.group_names or (system.group_name,)


def sorted_scheduled_systems(
    systems: Iterable[_ScheduledSystem],
    system_groups: Mapping[str, _SystemSetConfig],
    group_orders: Sequence[Sequence[str]] = (),
) -> list[_ScheduledSystem]:
    """Return systems in stable group dependency order.

    A system may belong to multiple groups and runs exactly once. The scheduler
    derives system-to-system dependencies from all declared group memberships.
    Intersecting groups are valid when their ordering constraints agree; cycles
    or memberships in mutually ordered groups raise ``SystemPlanError``. Systems
    with equivalent group constraints run in registration order.
    """

    scheduled_systems = list(systems)
    graph = _build_group_graph(scheduled_systems, system_groups, group_orders)
    group_order = _topological_group_order(graph.groups, graph.edges, graph.incoming)
    reachability = _group_reachability(graph.groups, graph.edges)
    _validate_system_memberships(scheduled_systems, reachability)
    return _topological_system_order(scheduled_systems, group_order, reachability)


def sorted_system_groups(
    systems: Iterable[_ScheduledSystem],
    system_groups: Mapping[str, _SystemSetConfig],
    group_orders: Sequence[Sequence[str]] = (),
) -> list[str]:
    """Return known groups in topological order and validate dependency conflicts."""

    scheduled_systems = list(systems)
    graph = _build_group_graph(scheduled_systems, system_groups, group_orders)
    group_order = _topological_group_order(graph.groups, graph.edges, graph.incoming)
    _validate_system_memberships(scheduled_systems, _group_reachability(graph.groups, graph.edges))
    return group_order


def _build_group_graph(
    systems: Sequence[_ScheduledSystem],
    system_groups: Mapping[str, _SystemSetConfig],
    group_orders: Sequence[Sequence[str]],
) -> _GroupGraph:
    graph = _GroupGraph()
    _note_declared_groups(graph, systems, system_groups)
    system_name_to_groups = _system_group_memberships(systems)
    _add_system_order_edges(graph, systems, system_name_to_groups)
    _add_configured_group_edges(graph, system_groups, system_name_to_groups)
    _add_explicit_order_edges(graph, group_orders)
    return graph


def _note_declared_groups(
    graph: _GroupGraph,
    systems: Sequence[_ScheduledSystem],
    system_groups: Mapping[str, _SystemSetConfig],
) -> None:
    for group_name in system_groups:
        graph.note(group_name)
    for system in systems:
        for group_name in scheduled_system_group_names(system):
            graph.note(group_name)


def _system_group_memberships(
    systems: Sequence[_ScheduledSystem],
) -> dict[str, tuple[str, ...]]:
    return {system.handle.name: scheduled_system_group_names(system) for system in systems}


def _resolve_group_reference(
    graph: _GroupGraph, ref: str, system_name_to_groups: Mapping[str, tuple[str, ...]]
) -> str:
    name = validate_group_name(str(ref))
    if name in graph.groups:
        return name
    referenced_groups = system_name_to_groups.get(name)
    if referenced_groups is None:
        return graph.note(name)
    if len(referenced_groups) != 1:
        raise SystemPlanError(
            f"ECS system {name!r} belongs to multiple groups; order against one "
            "of its group names instead."
        )
    return graph.note(referenced_groups[0])


def _add_system_order_edges(
    graph: _GroupGraph,
    systems: Sequence[_ScheduledSystem],
    system_name_to_groups: Mapping[str, tuple[str, ...]],
) -> None:
    for system in systems:
        group_names = scheduled_system_group_names(system)
        _validate_system_level_order(system, group_names)
        group_name = group_names[0]
        _add_before_edges(graph, group_name, system.before, system_name_to_groups)
        _add_after_edges(graph, group_name, system.after, system_name_to_groups)


def _validate_system_level_order(system: _ScheduledSystem, group_names: Sequence[str]) -> None:
    if len(group_names) != 1 and (system.before or system.after):
        raise SystemPlanError(
            f"ECS system {system.handle.name!r} cannot combine multiple groups with "
            "system-level before=... or after=.... Order the groups instead."
        )


def _add_configured_group_edges(
    graph: _GroupGraph,
    system_groups: Mapping[str, _SystemSetConfig],
    system_name_to_groups: Mapping[str, tuple[str, ...]],
) -> None:
    for group_name, config in system_groups.items():
        normalized_group = graph.note(group_name)
        _add_before_edges(graph, normalized_group, config.before, system_name_to_groups)
        _add_after_edges(graph, normalized_group, config.after, system_name_to_groups)


def _add_before_edges(
    graph: _GroupGraph,
    source: str,
    references: Sequence[str],
    system_name_to_groups: Mapping[str, tuple[str, ...]],
) -> None:
    for reference in references:
        graph.add_edge(source, _resolve_group_reference(graph, reference, system_name_to_groups))


def _add_after_edges(
    graph: _GroupGraph,
    target: str,
    references: Sequence[str],
    system_name_to_groups: Mapping[str, tuple[str, ...]],
) -> None:
    for reference in references:
        graph.add_edge(_resolve_group_reference(graph, reference, system_name_to_groups), target)


def _add_explicit_order_edges(graph: _GroupGraph, group_orders: Sequence[Sequence[str]]) -> None:
    for group_sequence in group_orders:
        normalized = _normalize_order_sequence(graph, group_sequence)
        for source, target in zip(normalized, normalized[1:], strict=False):
            graph.add_edge(source, target)


def _normalize_order_sequence(graph: _GroupGraph, group_sequence: Sequence[str]) -> list[str]:
    normalized = [graph.note(validate_group_name(group_name)) for group_name in group_sequence]
    if len(set(normalized)) != len(normalized):
        raise SystemPlanError("gs.order(...) group names must be unique within one order list.")
    return normalized


def _topological_group_order(
    groups: Mapping[str, int],
    edges: Mapping[str, set[str]],
    incoming: Mapping[str, set[str]],
) -> list[str]:
    incoming_work = {group_name: set(deps) for group_name, deps in incoming.items()}
    stable_key = _group_stable_key(groups)
    ready = sorted((group for group, deps in incoming_work.items() if not deps), key=stable_key)
    ordered: list[str] = []
    while ready:
        group_name = ready.pop(0)
        ordered.append(group_name)
        _release_group_dependents(group_name, edges, incoming_work, ready, stable_key)
    if len(ordered) != len(groups):
        _raise_group_cycle(incoming_work)
    return ordered


def _group_stable_key(groups: Mapping[str, int]) -> Callable[[str], tuple[int, str]]:
    return lambda group_name: (groups[group_name], group_name)


def _release_group_dependents(
    group_name: str,
    edges: Mapping[str, set[str]],
    incoming: Mapping[str, set[str]],
    ready: list[str],
    stable_key: Any,
) -> None:
    for target in sorted(edges.get(group_name, ()), key=stable_key):
        incoming[target].remove(group_name)
        if not incoming[target]:
            ready.append(target)
            ready.sort(key=stable_key)


def _raise_group_cycle(incoming: Mapping[str, set[str]]) -> None:
    cycle_names = sorted(group for group, deps in incoming.items() if deps)
    raise SystemPlanError(
        "ECS system group ordering conflict/cycle detected: " + " -> ".join(cycle_names)
    )


def _group_reachability(
    groups: Mapping[str, int], edges: Mapping[str, set[str]]
) -> dict[str, set[str]]:
    reachability: dict[str, set[str]] = {}

    def visit(group_name: str) -> set[str]:
        cached = reachability.get(group_name)
        if cached is not None:
            return cached
        reachable: set[str] = set()
        for target in edges.get(group_name, ()):
            reachable.add(target)
            reachable.update(visit(target))
        reachability[group_name] = reachable
        return reachable

    for group_name in groups:
        visit(group_name)
    return reachability


def _validate_system_memberships(
    systems: Sequence[_ScheduledSystem], reachability: Mapping[str, set[str]]
) -> None:
    for system in systems:
        group_names = scheduled_system_group_names(system)
        for index, source in enumerate(group_names):
            _validate_group_membership_pairs(system, source, group_names[index + 1 :], reachability)


def _validate_group_membership_pairs(
    system: _ScheduledSystem,
    source: str,
    targets: Sequence[str],
    reachability: Mapping[str, set[str]],
) -> None:
    for target in targets:
        if target in reachability.get(source, ()) or source in reachability.get(target, ()):
            raise SystemPlanError(
                f"ECS system {system.handle.name!r} belongs to ordered groups "
                f"{source!r} and {target!r}; split the system or remove one "
                "group membership."
            )


def _topological_system_order(
    systems: Sequence[_ScheduledSystem],
    group_order: Sequence[str],
    reachability: Mapping[str, set[str]],
) -> list[_ScheduledSystem]:
    group_index = {group_name: index for index, group_name in enumerate(group_order)}
    system_edges, incoming = _build_system_dependency_graph(systems, reachability)
    stable_key = _system_stable_key(systems, group_index)
    ordered_indices = _topological_system_indices(systems, system_edges, incoming, stable_key)
    return [systems[index] for index in ordered_indices]


def _build_system_dependency_graph(
    systems: Sequence[_ScheduledSystem], reachability: Mapping[str, set[str]]
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    edges = {index: set() for index in range(len(systems))}
    incoming = {index: set() for index in range(len(systems))}
    for left_index, _left in enumerate(systems):
        for right_index in range(left_index + 1, len(systems)):
            _add_pairwise_system_edge(
                systems, left_index, right_index, edges, incoming, reachability
            )
    return edges, incoming


def _add_pairwise_system_edge(
    systems: Sequence[_ScheduledSystem],
    left_index: int,
    right_index: int,
    edges: Mapping[int, set[int]],
    incoming: Mapping[int, set[int]],
    reachability: Mapping[str, set[str]],
) -> None:
    left_before_right = _system_precedes(systems[left_index], systems[right_index], reachability)
    right_before_left = _system_precedes(systems[right_index], systems[left_index], reachability)
    if left_before_right and right_before_left:
        raise SystemPlanError(
            "ECS system group memberships create a scheduling conflict between "
            f"{systems[left_index].handle.name!r} and {systems[right_index].handle.name!r}."
        )
    if left_before_right:
        _add_system_edge(systems, left_index, right_index, edges, incoming)
    elif right_before_left:
        _add_system_edge(systems, right_index, left_index, edges, incoming)


def _system_precedes(
    left: _ScheduledSystem, right: _ScheduledSystem, reachability: Mapping[str, set[str]]
) -> bool:
    return any(
        right_group in reachability.get(left_group, ())
        for left_group in scheduled_system_group_names(left)
        for right_group in scheduled_system_group_names(right)
    )


def _add_system_edge(
    systems: Sequence[_ScheduledSystem],
    source: int,
    target: int,
    edges: Mapping[int, set[int]],
    incoming: Mapping[int, set[int]],
) -> None:
    if source == target:
        raise SystemPlanError(
            f"ECS system {systems[source].handle.name!r} has conflicting group memberships."
        )
    edges[source].add(target)
    incoming[target].add(source)


def _system_stable_key(
    systems: Sequence[_ScheduledSystem], group_index: Mapping[str, int]
) -> Callable[[int], tuple[tuple[int, ...], int]]:
    def stable_key(system_index: int) -> tuple[tuple[int, ...], int]:
        group_indices = tuple(
            sorted(
                group_index[group_name]
                for group_name in scheduled_system_group_names(systems[system_index])
            )
        )
        return group_indices, systems[system_index].handle.id

    return stable_key


def _topological_system_indices(
    systems: Sequence[_ScheduledSystem],
    edges: Mapping[int, set[int]],
    incoming: Mapping[int, set[int]],
    stable_key: Callable[[int], tuple[tuple[int, ...], int]],
) -> list[int]:
    ready = sorted((index for index, deps in incoming.items() if not deps), key=stable_key)
    ordered: list[int] = []
    while ready:
        system_index = ready.pop(0)
        ordered.append(system_index)
        _release_system_dependents(system_index, edges, incoming, ready, stable_key)
    if len(ordered) != len(systems):
        _raise_system_cycle(systems, incoming)
    return ordered


def _release_system_dependents(
    system_index: int,
    edges: Mapping[int, set[int]],
    incoming: Mapping[int, set[int]],
    ready: list[int],
    stable_key: Callable[[int], tuple[tuple[int, ...], int]],
) -> None:
    for target in sorted(edges.get(system_index, ()), key=stable_key):
        incoming[target].remove(system_index)
        if not incoming[target]:
            ready.append(target)
            ready.sort(key=stable_key)


def _raise_system_cycle(
    systems: Sequence[_ScheduledSystem], incoming: Mapping[int, set[int]]
) -> None:
    cycle_names = sorted(systems[index].handle.name for index, deps in incoming.items() if deps)
    raise SystemPlanError(
        "ECS system group memberships create a scheduling conflict/cycle: "
        + " -> ".join(cycle_names)
    )


__all__ = [
    "implicit_system_group_name",
    "normalize_group_names",
    "scheduled_system_group_names",
    "sorted_scheduled_systems",
    "sorted_system_groups",
    "validate_group_name",
]
