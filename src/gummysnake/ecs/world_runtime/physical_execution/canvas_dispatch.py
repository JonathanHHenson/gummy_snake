# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
def dispatch_canvas_commands(world: EcsWorld, report: dict[str, Any]) -> None:
    """Replay canvas draw commands emitted by Rust ECS physical execution."""

    commands = report.get("canvas_commands", ())
    if not commands:
        return
    context = world.context
    if context is None:
        raise SystemExecutionError("ECS canvas draw commands require an active SketchContext.")
    from gummysnake import constants as c
    from gummysnake.drawing.primitive_fast_path import (
        PRIMITIVE_ELLIPSE,
        PRIMITIVE_RECT,
        PRIMITIVE_TRIANGLE,
    )

    fast = context.fast()
    renderer = cast(Any, context.renderer)
    primitive_batch = renderer._primitive_batch_state
    primitive_records = primitive_batch.records
    direct_fill_active = False
    matrix_payload = renderer._matrix_payload(context.state.transform.matrix)
    current_fill = context.state.style.fill_rgba
    direct_fill_allowed = (
        current_fill is not None
        and context.state.style.stroke_rgba is None
        and not context.state.style.erasing
        and context.state.style.blend_mode == c.BLEND
    )

    def refresh_direct_fill_state() -> None:
        nonlocal current_fill, direct_fill_allowed, matrix_payload, primitive_records
        style = context.state.style
        primitive_records = primitive_batch.records
        matrix_payload = renderer._matrix_payload(context.state.transform.matrix)
        current_fill = style.fill_rgba
        direct_fill_allowed = (
            current_fill is not None
            and style.stroke_rgba is None
            and not style.erasing
            and style.blend_mode == c.BLEND
        )

    def append_fill_primitive(kind: int, coords: tuple[float, ...]) -> bool:
        nonlocal direct_fill_active, primitive_records
        if not direct_fill_allowed or current_fill is None:
            return False
        if not direct_fill_active:
            renderer._flush_batches_before_primitive_batch()
            primitive_records = primitive_batch.records
            direct_fill_active = True
        if primitive_batch.has_records() and not primitive_batch.matches_fill(matrix_payload):
            renderer._flush_primitive_batch_only()
            primitive_records = primitive_batch.records
        primitive_records.append((kind, *coords, *current_fill))
        primitive_batch.style = None
        primitive_batch.matrix = matrix_payload
        primitive_batch.current = False
        primitive_batch.mode = "fill"
        return True

    handlers: dict[str, Callable[..., Any]] = {
        "background": context.background,
        "clear": context.clear,
        "fill": context.fill,
        "no_fill": context.no_fill,
        "stroke": context.stroke,
        "no_stroke": context.no_stroke,
        "stroke_weight": context.stroke_weight,
        "rect": fast.rect,
        "circle": fast.circle,
        "ellipse": fast.ellipse,
        "line": fast.line,
        "triangle": fast.triangle,
        "text_size": context.text_size,
        "text": fast.text,
    }
    fallback_handlers: dict[str, Callable[..., Any]] = {}
    for command in commands:
        if isinstance(command, (tuple, list)) and len(command) == 2:
            name = str(command[0])
            args = command[1]
        elif isinstance(command, dict):
            name = str(command.get("command", ""))
            args = command.get("args", ())
        else:
            raise SystemExecutionError("Malformed ECS canvas command report.")
        if not name:
            raise SystemExecutionError("Malformed ECS canvas command without a command name.")
        if name == "rect" and len(args) == 4 and context.state.style.rect_mode == c.CORNER:
            if append_fill_primitive(
                PRIMITIVE_RECT, (args[0], args[1], args[2], args[3], 0.0, 0.0)
            ):
                continue
        elif name == "circle" and len(args) == 3 and context.state.style.ellipse_mode == c.CENTER:
            diameter = args[2]
            if append_fill_primitive(
                PRIMITIVE_ELLIPSE,
                (args[0] - diameter / 2.0, args[1] - diameter / 2.0, diameter, diameter, 0.0, 0.0),
            ):
                continue
        elif (
            name == "ellipse"
            and len(args) in {3, 4}
            and context.state.style.ellipse_mode == c.CENTER
        ):
            width = args[2]
            height = width if len(args) == 3 else args[3]
            if append_fill_primitive(
                PRIMITIVE_ELLIPSE,
                (args[0] - width / 2.0, args[1] - height / 2.0, width, height, 0.0, 0.0),
            ):
                continue
        elif (
            name == "triangle"
            and len(args) == 6
            and append_fill_primitive(
                PRIMITIVE_TRIANGLE,
                (args[0], args[1], args[2], args[3], args[4], args[5]),
            )
        ):
            continue

        draw_api = handlers.get(name)
        if draw_api is None:
            draw_api = fallback_handlers.get(name)
            if draw_api is None:
                candidate = getattr(context, name, None)
                if not callable(candidate):
                    raise SystemExecutionError(f"Unsupported ECS canvas command {name!r}.")
                draw_api = cast(Callable[..., Any], candidate)
                fallback_handlers[name] = draw_api
        draw_api(*args)
        if name in {
            "fill",
            "no_fill",
            "stroke",
            "no_stroke",
            "stroke_weight",
            "erase",
            "no_erase",
            "blend_mode",
        }:
            refresh_direct_fill_state()
        else:
            direct_fill_active = False
            refresh_direct_fill_state()
    world._diagnostics["ecs_canvas_commands"] += len(commands)


def refresh_rust_input_states(world: EcsWorld, payload: dict[str, Any] | None) -> None:
    """Refresh Rust input-state resources required by a compiled physical plan."""
    if payload is None:
        return
    for expr in payload.get("expressions", ()):  # tiny input binding pass; not ECS execution
        if not isinstance(expr, dict) or expr.get("kind") != "input_state":
            continue
        name = str(expr.get("name", ""))
        code = expr.get("code")
        int_code = int(code) if code is not None else None
        if name == "dt":
            world._rust.set_input_state("dt", _current_delta_time(world))
        elif name == "key_down" and int_code is not None:
            world._rust.set_input_state("key_down", _current_key_down(world, int_code), int_code)


def apply_physical_report(world: EcsWorld, report: dict[str, Any]) -> None:
    """Apply component/resource/event mutations reported by Rust physical execution."""
    previous_defer_spatial = world._defer_spatial_invalidation
    previous_spatial_invalidated = world._spatial_invalidated_deferred
    world._defer_spatial_invalidation = True
    world._spatial_invalidated_deferred = False
    try:
        for write in report.get("component_writes", ()):
            component_type = world._component_type_for_schema(str(write["component"]))
            entity = Entity(int(write["index"]), int(write["generation"]), world._world_id)
            world._mark_component_changed(entity, component_type)
        for event in report.get("events", ()):
            event_type = world._component_type_for_schema(str(event["event_type"]))
            payload = _event_payload_from_bridge(event_type, event["payload"])
            world._events.setdefault(event_type, []).append(
                (world._ecs_frame, copy.deepcopy(payload))
            )
        for write in report.get("resource_writes", ()):
            world._component_type_for_schema(str(write["resource"]))
            world._note_resource_update()
    finally:
        invalidated = world._spatial_invalidated_deferred
        world._defer_spatial_invalidation = previous_defer_spatial
        world._spatial_invalidated_deferred = previous_spatial_invalidated or invalidated
        if invalidated and not previous_defer_spatial:
            world._spatial_invalidated_deferred = previous_spatial_invalidated
            world._invalidate_spatial_indexes()
