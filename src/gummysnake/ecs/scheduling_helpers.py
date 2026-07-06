"""Private helpers for ECS system scheduling order."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from gummysnake.ecs.runtime_views import SystemHandle, _ScheduledSystem, _SystemSetConfig
from gummysnake.exceptions import SystemPlanError


def sorted_scheduled_systems(
    systems: Iterable[_ScheduledSystem],
    system_sets: Mapping[str, _SystemSetConfig],
) -> list[_ScheduledSystem]:
    """Return systems in stable dependency order."""

    scheduled_systems = list(systems)
    by_name = {system.handle.name: system for system in scheduled_systems}
    by_id = {system.handle.id: system for system in scheduled_systems}
    edges: dict[int, set[int]] = {system.handle.id: set() for system in scheduled_systems}
    incoming: dict[int, set[int]] = {system.handle.id: set() for system in scheduled_systems}

    def resolve(ref: SystemHandle | str) -> _ScheduledSystem:
        if isinstance(ref, SystemHandle):
            try:
                return by_id[ref.id]
            except KeyError as exc:
                raise SystemPlanError(f"Unknown ECS system dependency {ref!r}.") from exc
        try:
            return by_name[ref]
        except KeyError as exc:
            raise SystemPlanError(f"Unknown ECS system dependency {ref!r}.") from exc

    for system in scheduled_systems:
        for before_ref in system.before:
            target = resolve(before_ref)
            edges[system.handle.id].add(target.handle.id)
            incoming[target.handle.id].add(system.handle.id)
        for after_ref in system.after:
            source = resolve(after_ref)
            edges[source.handle.id].add(system.handle.id)
            incoming[system.handle.id].add(source.handle.id)

    stable = {
        system.handle.id: (_effective_order(system, system_sets), system.handle.id)
        for system in scheduled_systems
    }

    def stable_key(system_id: int) -> tuple[int, int]:
        return stable[system_id]

    ready = sorted(
        (system_id for system_id, deps in incoming.items() if not deps),
        key=stable_key,
    )
    ordered_ids: list[int] = []
    while ready:
        system_id = ready.pop(0)
        ordered_ids.append(system_id)
        for target_id in sorted(edges[system_id], key=stable_key):
            incoming[target_id].remove(system_id)
            if not incoming[target_id]:
                ready.append(target_id)
                ready.sort(key=stable_key)
    if len(ordered_ids) != len(scheduled_systems):
        cycle_ids = [system_id for system_id, deps in incoming.items() if deps]
        cycle_names = [by_id[system_id].handle.name for system_id in cycle_ids]
        raise SystemPlanError(
            "ECS system dependency cycle detected: " + " -> ".join(sorted(cycle_names))
        )
    return [by_id[system_id] for system_id in ordered_ids]


def _effective_order(
    scheduled: _ScheduledSystem,
    system_sets: Mapping[str, _SystemSetConfig],
) -> int:
    config = system_sets.get(scheduled.set_name or "")
    return scheduled.order if config is None or config.order is None else config.order
