# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
# -------------------------------------------------------------- diagnostics
def configure(self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None) -> None:
    """Configure duplicate-write handling for this ECS world.

    Args:
        strict: When true, reject ambiguous duplicate writes instead of resolving them.
        warn_on_ambiguity: When true, log warnings for duplicate-write resolution.
    """

    state_runtime.configure(self, strict=strict, warn_on_ambiguity=warn_on_ambiguity)


def diagnostics(self) -> dict[str, Any]:
    """Return ECS counters and diagnostic messages.

    Returns:
        A dictionary of diagnostic names to values.
    """

    return state_runtime.diagnostics(self)


def reset_diagnostics(self) -> None:
    """Reset ECS diagnostic counters and messages."""

    state_runtime.reset_diagnostics(self)


def record_ambiguity(self, message: str) -> None:
    """Record an ambiguity diagnostic message.

    Args:
        message: Human-readable explanation of the ambiguous write or schedule.
    """

    state_runtime.record_ambiguity(self, message)


def _note_field_update(self, entity: Entity, component_type: type[Any]) -> None:
    state_runtime.note_field_update(self, entity, component_type)


def _note_resource_update(self) -> None:
    state_runtime.note_resource_update(self)


def _invalidate_spatial_indexes(self, *, clear_only: bool = False) -> None:
    state_runtime.invalidate_spatial_indexes(self, clear_only=clear_only)


def configure_system_set(
    self,
    name: str,
    *,
    enabled: bool | None = None,
    run_if: Callable[[], bool] | None = None,
) -> None:
    """Deprecated alias for ``group(name, enabled=..., run_if=...)``."""

    self.group(name, enabled=enabled, run_if=run_if)


def group(
    self,
    name: str,
    *,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
    enabled: bool | None = None,
    run_if: Callable[[], bool] | None = None,
) -> None:
    """Create or configure an ECS system group."""

    state_runtime.configure_system_group(
        self,
        name,
        before=tuple(before),
        after=tuple(after),
        enabled=enabled,
        run_if=run_if,
    )


def order(self, groups: Iterable[str]) -> None:
    """Declare a left-to-right ordering for ECS system groups."""

    normalized = tuple(validate_group_name(group_name) for group_name in groups)
    state_runtime.configure_group_order(self, normalized)


def _system_enabled(self, scheduled: _ScheduledSystem) -> bool:
    return state_runtime.system_enabled(self, scheduled)


def _system_run_condition(self, scheduled: _ScheduledSystem) -> bool:
    return state_runtime.system_run_condition(self, scheduled)


def _sorted_systems(self) -> list[_ScheduledSystem]:
    return sorted_scheduled_systems(self._systems, self._system_sets, self._group_orders)


def _begin_change_frame(self) -> None:
    state_runtime.begin_change_frame(self)


def _finalize_change_frame(self) -> None:
    state_runtime.finalize_change_frame(self)


def _mark_component_added(self, entity: Entity, component_type: type[Any]) -> None:
    state_runtime.mark_component_added(self, entity, component_type)


def _mark_component_changed(self, entity: Entity, component_type: type[Any]) -> None:
    state_runtime.mark_component_changed(self, entity, component_type)


def _mark_component_removed(self, entity: Entity, component_type: type[Any]) -> None:
    state_runtime.mark_component_removed(self, entity, component_type)


def _set_system_enabled(self, handle: SystemHandle | str, enabled: bool) -> None:
    state_runtime.set_system_enabled(self, handle, enabled)


EcsWorld.configure = configure
EcsWorld.diagnostics = diagnostics
EcsWorld.reset_diagnostics = reset_diagnostics
EcsWorld.record_ambiguity = record_ambiguity
EcsWorld._note_field_update = _note_field_update
EcsWorld._note_resource_update = _note_resource_update
EcsWorld._invalidate_spatial_indexes = _invalidate_spatial_indexes
EcsWorld.configure_system_set = configure_system_set
EcsWorld.group = group
EcsWorld.order = order
EcsWorld._system_enabled = _system_enabled
EcsWorld._system_run_condition = _system_run_condition
EcsWorld._sorted_systems = _sorted_systems
EcsWorld._begin_change_frame = _begin_change_frame
EcsWorld._finalize_change_frame = _finalize_change_frame
EcsWorld._mark_component_added = _mark_component_added
EcsWorld._mark_component_changed = _mark_component_changed
EcsWorld._mark_component_removed = _mark_component_removed
EcsWorld._set_system_enabled = _set_system_enabled
