"""Private helpers for ECS system group scheduling order."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from gummysnake.ecs.runtime_views import _ScheduledSystem, _SystemSetConfig
from gummysnake.exceptions import SystemPlanError

_GROUP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


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
    groups, edges, incoming = _build_group_graph(scheduled_systems, system_groups, group_orders)
    group_order = _topological_group_order(groups, edges, incoming)
    reachability = _group_reachability(groups, edges)
    _validate_system_memberships(scheduled_systems, reachability)
    return _topological_system_order(scheduled_systems, group_order, reachability)


def sorted_system_groups(
    systems: Iterable[_ScheduledSystem],
    system_groups: Mapping[str, _SystemSetConfig],
    group_orders: Sequence[Sequence[str]] = (),
) -> list[str]:
    """Return known groups in topological order and validate dependency conflicts."""

    scheduled_systems = list(systems)
    groups, edges, incoming = _build_group_graph(scheduled_systems, system_groups, group_orders)
    group_order = _topological_group_order(groups, edges, incoming)
    _validate_system_memberships(scheduled_systems, _group_reachability(groups, edges))
    return group_order


def _build_group_graph(
    systems: Sequence[_ScheduledSystem],
    system_groups: Mapping[str, _SystemSetConfig],
    group_orders: Sequence[Sequence[str]],
) -> tuple[dict[str, int], dict[str, set[str]], dict[str, set[str]]]:
    groups: dict[str, int] = {}

    def note_group(name: str) -> str:
        group_name = validate_group_name(name)
        groups.setdefault(group_name, len(groups))
        return group_name

    for group_name in system_groups:
        note_group(group_name)
    for system in systems:
        for group_name in scheduled_system_group_names(system):
            note_group(group_name)

    system_name_to_groups = {
        system.handle.name: scheduled_system_group_names(system) for system in systems
    }
    edges: dict[str, set[str]] = {group_name: set() for group_name in groups}
    incoming: dict[str, set[str]] = {group_name: set() for group_name in groups}

    def add_edge(source: str, target: str) -> None:
        source = note_group(source)
        target = note_group(target)
        edges.setdefault(source, set())
        edges.setdefault(target, set())
        incoming.setdefault(source, set())
        incoming.setdefault(target, set())
        if source == target:
            raise SystemPlanError(f"ECS system group {source!r} cannot depend on itself.")
        edges[source].add(target)
        incoming[target].add(source)

    def resolve_ref(ref: str) -> str:
        name = validate_group_name(str(ref))
        if name in groups:
            return name
        referenced_groups = system_name_to_groups.get(name)
        if referenced_groups is None:
            return note_group(name)
        if len(referenced_groups) != 1:
            raise SystemPlanError(
                f"ECS system {name!r} belongs to multiple groups; order against one "
                "of its group names instead."
            )
        return note_group(referenced_groups[0])

    for system in systems:
        system_groups_for_order = scheduled_system_group_names(system)
        if len(system_groups_for_order) != 1 and (system.before or system.after):
            raise SystemPlanError(
                f"ECS system {system.handle.name!r} cannot combine multiple groups with "
                "system-level before=... or after=.... Order the groups instead."
            )
        group_name = system_groups_for_order[0]
        for before_ref in system.before:
            add_edge(group_name, resolve_ref(before_ref))
        for after_ref in system.after:
            add_edge(resolve_ref(after_ref), group_name)

    for group_name, config in system_groups.items():
        group_name = note_group(group_name)
        for before_ref in config.before:
            add_edge(group_name, resolve_ref(before_ref))
        for after_ref in config.after:
            add_edge(resolve_ref(after_ref), group_name)

    for group_sequence in group_orders:
        normalized = [note_group(validate_group_name(group_name)) for group_name in group_sequence]
        if len(set(normalized)) != len(normalized):
            raise SystemPlanError("gs.order(...) group names must be unique within one order list.")
        for source, target in zip(normalized, normalized[1:], strict=False):
            add_edge(source, target)

    return groups, edges, incoming


def _topological_group_order(
    groups: Mapping[str, int],
    edges: Mapping[str, set[str]],
    incoming: Mapping[str, set[str]],
) -> list[str]:
    incoming_work = {group_name: set(deps) for group_name, deps in incoming.items()}

    def stable_key(group_name: str) -> tuple[int, str]:
        return (groups[group_name], group_name)

    ready = sorted((group for group, deps in incoming_work.items() if not deps), key=stable_key)
    ordered: list[str] = []
    while ready:
        group_name = ready.pop(0)
        ordered.append(group_name)
        for target in sorted(edges.get(group_name, ()), key=stable_key):
            incoming_work[target].remove(group_name)
            if not incoming_work[target]:
                ready.append(target)
                ready.sort(key=stable_key)
    if len(ordered) != len(groups):
        cycle_names = sorted(group for group, deps in incoming_work.items() if deps)
        raise SystemPlanError(
            "ECS system group ordering conflict/cycle detected: " + " -> ".join(cycle_names)
        )
    return ordered


def _group_reachability(
    groups: Mapping[str, int],
    edges: Mapping[str, set[str]],
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
            for target in group_names[index + 1 :]:
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
    system_edges: dict[int, set[int]] = {index: set() for index in range(len(systems))}
    incoming: dict[int, set[int]] = {index: set() for index in range(len(systems))}

    def system_before(left: _ScheduledSystem, right: _ScheduledSystem) -> bool:
        return any(
            right_group in reachability.get(left_group, ())
            for left_group in scheduled_system_group_names(left)
            for right_group in scheduled_system_group_names(right)
        )

    def add_system_edge(source: int, target: int) -> None:
        if source == target:
            raise SystemPlanError(
                f"ECS system {systems[source].handle.name!r} has conflicting group memberships."
            )
        system_edges[source].add(target)
        incoming[target].add(source)

    for left_index, left in enumerate(systems):
        for right_index in range(left_index + 1, len(systems)):
            right = systems[right_index]
            left_before_right = system_before(left, right)
            right_before_left = system_before(right, left)
            if left_before_right and right_before_left:
                raise SystemPlanError(
                    "ECS system group memberships create a scheduling conflict between "
                    f"{left.handle.name!r} and {right.handle.name!r}."
                )
            if left_before_right:
                add_system_edge(left_index, right_index)
            elif right_before_left:
                add_system_edge(right_index, left_index)

    def stable_key(system_index: int) -> tuple[tuple[int, ...], int]:
        group_indices = tuple(
            sorted(
                group_index[group_name]
                for group_name in scheduled_system_group_names(systems[system_index])
            )
        )
        return (group_indices, systems[system_index].handle.id)

    ready = sorted((index for index, deps in incoming.items() if not deps), key=stable_key)
    ordered_indices: list[int] = []
    while ready:
        system_index = ready.pop(0)
        ordered_indices.append(system_index)
        for target in sorted(system_edges.get(system_index, ()), key=stable_key):
            incoming[target].remove(system_index)
            if not incoming[target]:
                ready.append(target)
                ready.sort(key=stable_key)
    if len(ordered_indices) != len(systems):
        cycle_names = sorted(systems[index].handle.name for index, deps in incoming.items() if deps)
        raise SystemPlanError(
            "ECS system group memberships create a scheduling conflict/cycle: "
            + " -> ".join(cycle_names)
        )
    return [systems[index] for index in ordered_indices]


__all__ = [
    "implicit_system_group_name",
    "normalize_group_names",
    "scheduled_system_group_names",
    "sorted_scheduled_systems",
    "sorted_system_groups",
    "validate_group_name",
]
