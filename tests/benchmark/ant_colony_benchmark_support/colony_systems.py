# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false


@ecs.system_plan(group="simulation_ants")
def simulate_red_ants(
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[RED_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=True)


@ecs.system_plan(group="simulation_ants")
def simulate_blue_ants(
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[BLUE_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=False)
