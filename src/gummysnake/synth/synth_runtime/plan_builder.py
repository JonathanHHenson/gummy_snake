# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
class PlanBuilder:
    """Mutable logical-plan builder used while a track function executes."""

    def __init__(self, *, bpm: float = 60.0, seed: int = 0, repeat_depth: int = 1) -> None:
        if bpm <= 0:
            raise ArgumentValidationError("Track BPM must be positive.")
        self.nodes: list[PlanNode] = []
        self.current_beat = 0.0
        self.bpm = float(bpm)
        self.seed = int(seed)
        self.repeat_depth = int(repeat_depth)
        self.synth_stack: list[SynthSpec] = [SynthSpec("beep", {})]
        self.fx_stack: list[FxHandle] = []

    def child(self, *, repeat_depth: int | None = None) -> PlanBuilder:
        child = PlanBuilder(
            bpm=self.bpm,
            seed=self.seed,
            repeat_depth=self.repeat_depth if repeat_depth is None else repeat_depth,
        )
        child.synth_stack = list(self.synth_stack)
        child.fx_stack = list(self.fx_stack)
        return child

    @property
    def current_synth(self) -> SynthSpec:
        return self.synth_stack[-1]

    def add_event(
        self, kind: Literal["play", "sample"], value: object, opts: dict[str, object]
    ) -> NodeHandle:
        synth_spec = self.current_synth
        if kind == "play":
            synth_definition = _lookup_synth_definition(synth_spec.name)
            if synth_definition is not None:
                merged_opts = {**dict(synth_spec.opts), **dict(opts)}
                if isinstance(synth_definition, CompiledSynthDefinition):
                    return self.add_compiled_synth_definition_event(
                        synth_definition,
                        value,
                        merged_opts,
                    )
                return self.add_synth_definition_event(
                    synth_definition,
                    value,
                    merged_opts,
                )
            if not synth_spec.name.startswith("_"):
                raise ArgumentValidationError(
                    f"No bundled compiled synth asset named {synth_spec.name!r}."
                )
        node = EventNode(
            id=_next_node_id(),
            kind=kind,
            value=value,
            opts=dict(opts),
            beat=self.current_beat,
            synth_name=synth_spec.name,
            synth_opts=dict(synth_spec.opts),
            fx_chain=self.expanded_fx_chain(),
        )
        self.nodes.append(node)
        return NodeHandle(node)

    def add_synth_definition_event(
        self,
        definition: SynthDefinition,
        value: object,
        opts: dict[str, object],
    ) -> NodeHandle:
        stack = _SYNTH_EXPANSION_STACK.get()
        if definition.name in stack:
            raise SynthPlanError(f"Recursive synth definition expansion for {definition.name!r}.")
        child = self.child()
        token_builder = _CURRENT_BUILDER.set(child)
        token_stack = _SYNTH_EXPANSION_STACK.set((*stack, definition.name))
        try:
            result = definition.func(value, **opts)
        finally:
            _SYNTH_EXPANSION_STACK.reset(token_stack)
            _CURRENT_BUILDER.reset(token_builder)
        if result is not None:
            raise SynthPlanError("@sy.synth functions must build actions and return None.")
        node = ThreadNode(
            id=_next_node_id(),
            body=tuple(child.nodes),
            beat=self.current_beat,
            body_beats=child.current_beat,
            name=f"synth:{definition.name}",
        )
        self.nodes.append(node)
        event_paths = _event_node_paths(child.nodes)
        if event_paths:
            first_event, first_path = event_paths[0]
            control_targets = tuple(
                ControlTarget(
                    event_node.id,
                    (node.id, node.name or "thread", *path),
                    event_node.control_note_transpose,
                )
                for event_node, path in event_paths
            )
            return NodeHandle(
                first_event,
                scope_suffix=(node.id, node.name or "thread", *first_path),
                condition_nodes=tuple(event_node for event_node, _path in event_paths),
                control_targets=control_targets,
            )
        placeholder = EventNode(
            id=_next_node_id(),
            kind="play",
            value=None,
            opts={},
            beat=self.current_beat,
            synth_name="_silence",
            synth_opts={},
            fx_chain=(),
        )
        return NodeHandle(placeholder)

    def add_compiled_synth_definition_event(
        self,
        definition: CompiledSynthDefinition,
        value: object,
        opts: dict[str, object],
    ) -> NodeHandle:
        plan = definition.load_plan()
        event_payloads = [_scheduled_event_to_dict(event) for event in plan.events]
        control_payloads = [_scheduled_control_to_dict(control) for control in plan.controls]
        consumed_opts = _apply_template_parameters(
            event_payloads, control_payloads, opts, plan.metadata
        )
        remaining_opts = {key: item for key, item in opts.items() if key not in consumed_opts}
        parent_fx_chain = self.expanded_fx_chain()
        event_id_map: dict[int, int] = {}
        fx_id_map: dict[int, int] = {}
        timeline_items: list[tuple[float, int, PlanNode]] = []

        for event_index, payload in enumerate(event_payloads):
            scheduled_event = _scheduled_event_from_dict(payload)
            event_id = _next_node_id()
            event_id_map[scheduled_event.node_id] = event_id
            event_opts = dict(scheduled_event.opts)
            event_opts.update(remaining_opts)
            fx_chain = (
                *parent_fx_chain,
                *_remap_compiled_fx_chain(scheduled_event.fx_chain, fx_id_map),
            )
            event_node = EventNode(
                id=event_id,
                kind=scheduled_event.kind,
                value=value if scheduled_event.kind == "play" else scheduled_event.value,
                opts=event_opts,
                beat=0.0,
                synth_name=scheduled_event.synth_name,
                synth_opts=dict(scheduled_event.synth_opts),
                fx_chain=fx_chain,
            )
            timeline_items.append((scheduled_event.time_seconds, event_index * 2, event_node))

        for control_index, payload in enumerate(control_payloads):
            scheduled_control = _scheduled_control_from_dict(payload)
            target_id = event_id_map.get(scheduled_control.target_id, scheduled_control.target_id)
            control_node = ControlNode(
                target_id=target_id,
                opts=dict(scheduled_control.opts),
                beat=0.0,
            )
            timeline_items.append(
                (scheduled_control.time_seconds, control_index * 2 + 1, control_node)
            )

        body, body_beats = _compiled_timeline_nodes(timeline_items, self.bpm, plan.duration_seconds)
        thread_node = ThreadNode(
            id=_next_node_id(),
            body=body,
            beat=self.current_beat,
            body_beats=body_beats,
            name=f"synth:{definition.name}",
        )
        self.nodes.append(thread_node)
        event_paths = _event_node_paths(body)
        if event_paths:
            first_event, first_path = event_paths[0]
            control_targets = tuple(
                ControlTarget(
                    event_node.id,
                    (thread_node.id, thread_node.name or "thread", *path),
                    event_node.control_note_transpose,
                )
                for event_node, path in event_paths
            )
            return NodeHandle(
                first_event,
                scope_suffix=(thread_node.id, thread_node.name or "thread", *first_path),
                condition_nodes=tuple(event_node for event_node, _path in event_paths),
                control_targets=control_targets,
            )
        placeholder = EventNode(
            id=_next_node_id(),
            kind="play",
            value=None,
            opts={},
            beat=0.0,
            synth_name="_silence",
            synth_opts={},
            fx_chain=(),
        )
        return NodeHandle(placeholder)

    def add_sleep(self, beats: object) -> None:
        numeric = _literal_float_or_none(beats)
        if numeric is not None and numeric < 0:
            raise ArgumentValidationError("sleep() duration cannot be negative.")
        self.nodes.append(SleepNode(self.current_beat, beats))
        if numeric is not None:
            self.current_beat += numeric
        else:
            # Lazy sleep durations are evaluated later during physical expansion.
            # The builder still needs a beat estimate so following nodes and loop
            # bodies have stable relative positions in the logical plan.
            self.current_beat += _estimated_beats(beats)

    def add_control(
        self, target_id: int, opts: dict[str, object], target_scope_suffix: tuple[object, ...] = ()
    ) -> None:
        self.nodes.append(
            ControlNode(
                target_id=target_id,
                opts=dict(opts),
                beat=self.current_beat,
                target_scope_suffix=target_scope_suffix,
            )
        )

    def add_bind(self, source: Expression) -> SourceBoundExpression:
        bind_id = _next_node_id()
        repeat_depth = _expression_repeat_depth(source, self.repeat_depth)
        self.nodes.append(BindNode(bind_id, source, repeat_depth, self.current_beat))
        return SourceBoundExpression(bind_id, repeat_depth, source)

    def push_synth(self, spec: SynthSpec) -> None:
        self.synth_stack.append(spec)

    def pop_synth(self, spec: SynthSpec) -> None:
        popped = self.synth_stack.pop()
        if popped is not spec:
            raise SynthPlanError("Synth context stack was corrupted.")

    def push_fx(self, handle: FxHandle) -> None:
        self.fx_stack.append(handle)

    def pop_fx(self, handle: FxHandle) -> None:
        popped = self.fx_stack.pop()
        if popped is not handle:
            raise SynthPlanError("FX context stack was corrupted.")

    def expanded_fx_chain(self) -> tuple[FxHandle, ...]:
        expanded: list[FxHandle] = []
        for handle in self.fx_stack:
            expanded.extend(_expand_fx_handle(handle))
        return tuple(expanded)
