"""Rust physical-plan preparation, execution, reports, and canvas dispatch."""

from gummysnake.ecs.world_runtime.physical_execution.canvas_dispatch import (
    apply_physical_report,
    dispatch_canvas_commands,
    refresh_rust_input_states,
)
from gummysnake.ecs.world_runtime.physical_execution.execution_reports import (
    _direct_canvas_execution_args,
    dispatch_canvas_fill_batches,
    execute_compiled_plan,
    execute_compiled_plans_to_canvas,
    record_physical_report,
    record_spatial_warm_report,
    should_record_spatial_warm_report,
)
from gummysnake.ecs.world_runtime.physical_execution.planning import (
    build_and_compile_payload,
    prepare_scheduled_physical_plan,
    require_plan_built,
    run_physical_system,
    run_physical_systems_batch,
    set_physical_payload,
)

__all__ = [
    "_direct_canvas_execution_args",
    "apply_physical_report",
    "build_and_compile_payload",
    "dispatch_canvas_commands",
    "dispatch_canvas_fill_batches",
    "execute_compiled_plan",
    "execute_compiled_plans_to_canvas",
    "prepare_scheduled_physical_plan",
    "record_physical_report",
    "record_spatial_warm_report",
    "refresh_rust_input_states",
    "require_plan_built",
    "run_physical_system",
    "run_physical_systems_batch",
    "set_physical_payload",
    "should_record_spatial_warm_report",
]
