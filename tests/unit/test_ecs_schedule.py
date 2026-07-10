from __future__ import annotations

from tests.helpers.ecs_fixtures import (
    EcsWorld,
    Plugin,
    Position,
    Sketch,
    SystemPlanError,
    ca,
    clear_plugins,
    ecs,
    install_plugin,
    pytest,
)


def test_system_dependency_cycles_error() -> None:
    world = EcsWorld()

    @ecs.system_plan
    def one() -> None:
        pass

    @ecs.system_plan
    def two() -> None:
        pass

    world.add_system(one, name="one")
    world.add_system(two, name="two", after=["one"])
    with pytest.raises(SystemPlanError, match="cycle"):
        world.add_system(one, name="one-again", after=["two"], before=["one"])


def test_system_group_order_and_validation() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))

    @ecs.system_plan
    def input_system(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(1)

    @ecs.system_plan
    def simulation_system(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(entity[Position].x * 10)

    @ecs.system_plan
    def draw_system(entity: ecs.Query[Position]) -> None:
        entity[Position].y.set_to(entity[Position].x + 5)

    world.order(["input", "simulation", "draw"])
    world.add_system(draw_system, group="draw")
    world.add_system(simulation_system, group="simulation")
    world.add_system(input_system, group="input")
    world.run_pre_draw_systems()

    entity = world.get_entity(Position)
    assert entity[Position].x == 10
    assert entity[Position].y == 15

    with pytest.raises(SystemPlanError, match="snake_case"):
        world.group("not-snake")
    with pytest.raises(SystemPlanError, match="unique"):
        world.order(["input", "input"])
    with pytest.raises(SystemPlanError, match="conflict|cycle"):
        world.group("input", after=["draw"])


def test_systems_can_belong_to_intersecting_ordered_groups() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))

    @ecs.system_plan
    def simulation(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(1)

    @ecs.system_plan
    def background(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(entity[Position].x * 10 + 2)

    @ecs.system_plan
    def actors(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(entity[Position].x * 10 + 3)

    @ecs.system_plan
    def export(entity: ecs.Query[Position]) -> None:
        entity[Position].y.set_to(entity[Position].x)

    world.order(["simulation", "draw", "export"])
    world.order(["draw_background", "draw_actors"])
    world.add_system(export, group="export")
    world.add_system(actors, group=("draw", "draw_actors"))
    world.add_system(background, group=("draw", "draw_background"))
    world.add_system(simulation, group="simulation")
    world.run_pre_draw_systems()

    entity = world.get_entity(Position)
    assert entity[Position].x == 123
    assert entity[Position].y == 123


def test_same_group_systems_run_in_registration_order() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))

    @ecs.system_plan
    def first(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(entity[Position].x * 10 + 1)

    @ecs.system_plan
    def second(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(entity[Position].x * 10 + 2)

    world.add_system(first, group="draw")
    world.add_system(second, group="draw")
    world.run_pre_draw_systems()

    assert world.get_entity(Position)[Position].x == 12


def test_multi_group_memberships_reject_order_conflicts() -> None:
    world = EcsWorld()

    @ecs.system_plan
    def invalid() -> None:
        pass

    world.order(["early", "late"])
    with pytest.raises(SystemPlanError, match="ordered groups"):
        world.add_system(invalid, group=("early", "late"))


def test_system_group_kwarg_rejects_system_before_after() -> None:
    with pytest.raises(SystemPlanError, match="cannot also declare before"):

        @ecs.system_plan(group="simulation", before=["draw"])
        def invalid_group_order() -> None:
            pass


def test_ecs_canvas_rejects_runtime_drawing_alias_use() -> None:
    with pytest.raises(SystemPlanError, match="logical plan"):
        ca.background(0)


def test_ecs_canvas_alias_and_rust_system_draw_commands() -> None:
    import gummysnake.ecs.canvas as canonical_canvas

    assert ca is canonical_canvas

    @ecs.system_plan(group="draw")
    def draw_position(entity: ecs.Query[Position]) -> None:
        ca.no_stroke()
        ca.fill(255, 210, 80)
        ca.circle(entity[Position].x, entity[Position].y, 4)

    class EcsCanvasSketch(Sketch):
        def setup(self) -> None:
            self.create_canvas(8, 8)
            self.add_entity(Position(4, 4))
            self.add_system(draw_position)

    context = EcsCanvasSketch().run(max_frames=1)

    diagnostics = context.ecs_diagnostics()
    assert diagnostics["ecs_physical_system_runs"] >= 1
    assert diagnostics["ecs_canvas_commands"] == 2
    assert diagnostics["ecs_canvas_direct_fill_primitives"] == 0
    assert diagnostics["ecs_canvas_fill_batch_primitives"] == 1


def test_ecs_group_hooks_surround_system_and_draw_groups() -> None:
    events: list[str] = []

    class Recorder(Plugin):
        name = "ecs-recorder"

        def before_simulation(self, context) -> None:
            del context
            events.append("before_simulation")

        def after_simulation(self, context) -> None:
            del context
            events.append("after_simulation")

        def before_draw(self, context) -> None:
            del context
            events.append("before_draw")

        def after_draw(self, context) -> None:
            del context
            events.append("after_draw")

    @ecs.udf
    def mark_system_run() -> None:
        events.append("system")

    @ecs.system_plan(group="simulation")
    def marker_system() -> None:
        mark_system_run()

    class EcsLifecycleSketch(Sketch):
        def setup(self) -> None:
            self.create_canvas(8, 8)
            self.order(["simulation", "draw"])
            self.add_system(marker_system)

        def draw(self) -> None:
            events.append("draw")
            self.no_loop()

    clear_plugins()
    try:
        install_plugin(Recorder())
        EcsLifecycleSketch().run(max_frames=1)
    finally:
        clear_plugins()

    assert events == [
        "before_simulation",
        "system",
        "after_simulation",
        "before_draw",
        "draw",
        "after_draw",
    ]
