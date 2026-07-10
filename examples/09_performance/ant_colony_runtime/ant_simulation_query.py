from __future__ import annotations

from gummysnake import ecs

from .configuration import (
    ANT_SPEED,
    BLUE_HILL,
    BOUNDARY_STEER,
    CELL_SIZE,
    COLLISION_CORRECTION_MAX,
    FOOD_COLLISION_RADIUS,
    FOOD_COLLISION_RESOLVE,
    FOOD_COLLISION_VELOCITY,
    FOOD_PHEROMONE_STEER,
    FOOD_STEER,
    GRID_HEIGHT,
    GRID_WIDTH,
    HOME_COMPASS_STEER,
    HOME_GRADIENT_STEER,
    HOME_PHEROMONE_STEER,
    HOME_SCAN_RADIUS,
    HOME_SCENT_COMPASS_SUPPRESSION,
    HOME_STEER,
    PHEROMONE_FOLLOW_THRESHOLD,
    PHEROMONE_SENSOR_RADIUS,
    RED_HILL,
    SCENT_WANDER_SUPPRESSION,
    SENSOR_DISTANCE,
    SENSOR_SPACING,
    SENSOR_VECTOR_SCALE,
    STATE_SWITCH_VELOCITY_DAMPING,
    TRAIL_RUNOUT_FRAMES,
    TURN_AROUND_STEER,
    VOXEL_QUADTREE,
    WALL_AVOID_RADIUS,
    WALL_COLLISION_RADIUS,
    WALL_COLLISION_RESOLVE,
    WALL_COLLISION_VELOCITY,
    WALL_STEER,
    WANDER_STEER,
    AntAgent,
    AntDecision,
    GridVoxel,
    PheromoneVoxel,
    _cell_center,
)


def _simulate_ant_query(
    ant: ecs.Query,
    wall: ecs.Query,
    food: ecs.Query,
    hill: ecs.Query,
    trail: ecs.Query,
    *,
    red_colony: bool,
) -> None:
    state = ant[AntAgent]
    decision = ant[AntDecision]
    colony_name = "red" if red_colony else "blue"
    ant_point = ecs.spatial.point2(state.x, state.y)
    wall_point = ecs.spatial.point2(wall[GridVoxel].x, wall[GridVoxel].y)
    food_point = ecs.spatial.point2(food[GridVoxel].x, food[GridVoxel].y)
    hill_point = ecs.spatial.point2(hill[GridVoxel].x, hill[GridVoxel].y)
    center_point = ecs.spatial.point2(state.sensor_center_x, state.sensor_center_y)
    left_point = ecs.spatial.point2(state.sensor_left_x, state.sensor_left_y)
    right_point = ecs.spatial.point2(state.sensor_right_x, state.sensor_right_y)
    trail_point = ecs.spatial.point2(trail[PheromoneVoxel].x, trail[PheromoneVoxel].y)

    walls = ecs.spatial.join(
        ant,
        wall,
        origin_position=ant_point,
        target_position=wall_point,
        radius=WALL_AVOID_RADIUS,
        algorithm=VOXEL_QUADTREE,
        include_self=False,
        allow_fallback=False,
        name="ant_wall_avoidance",
    )
    wall_collisions = ecs.spatial.join(
        ant,
        wall,
        origin_position=ant_point,
        target_position=wall_point,
        radius=WALL_COLLISION_RADIUS,
        algorithm=VOXEL_QUADTREE,
        include_self=False,
        allow_fallback=False,
        name="ant_wall_collision",
    )
    food_contacts = ecs.spatial.join(
        ant,
        food,
        origin_position=ant_point,
        target_position=food_point,
        radius=FOOD_COLLISION_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=FOOD_COLLISION_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_food_collision",
    )
    hills = ecs.spatial.join(
        ant,
        hill,
        origin_position=ant_point,
        target_position=hill_point,
        radius=HOME_SCAN_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=HOME_SCAN_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name=f"{colony_name}_ant_home_scan",
    )
    center_trails = ecs.spatial.join(
        ant,
        trail,
        origin_position=center_point,
        target_position=trail_point,
        radius=PHEROMONE_SENSOR_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PHEROMONE_SENSOR_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_center_pheromone_sensor",
    )
    left_trails = ecs.spatial.join(
        ant,
        trail,
        origin_position=left_point,
        target_position=trail_point,
        radius=PHEROMONE_SENSOR_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PHEROMONE_SENSOR_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_left_pheromone_sensor",
    )
    right_trails = ecs.spatial.join(
        ant,
        trail,
        origin_position=right_point,
        target_position=trail_point,
        radius=PHEROMONE_SENSOR_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PHEROMONE_SENSOR_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_right_pheromone_sensor",
    )

    current_speed = (state.vx * state.vx + state.vy * state.vy).sqrt().clamp_min(1.0e-6)
    forward_x = state.vx / current_speed
    forward_y = state.vy / current_speed
    left_dir_x = (forward_x - forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
    left_dir_y = (forward_y + forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
    right_dir_x = (forward_x + forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
    right_dir_y = (forward_y - forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE

    wall_push_x = walls.sum(-walls.delta.x / walls.distance.clamp_min(1.0))
    wall_push_y = walls.sum(-walls.delta.y / walls.distance.clamp_min(1.0))
    wall_collision_count = wall_collisions.count()
    wall_contact_push_x = wall_collisions.sum(
        -wall_collisions.delta.x / wall_collisions.distance.clamp_min(1.0)
    )
    wall_contact_push_y = wall_collisions.sum(
        -wall_collisions.delta.y / wall_collisions.distance.clamp_min(1.0)
    )
    wall_contact_length_raw = (
        wall_contact_push_x * wall_contact_push_x + wall_contact_push_y * wall_contact_push_y
    ).sqrt()
    wall_contact_length = wall_contact_length_raw.clamp_min(1.0)

    food_contact_count = food_contacts.count()
    food_contact_push_x = food_contacts.sum(
        -food_contacts.delta.x / food_contacts.distance.clamp_min(1.0)
    )
    food_contact_push_y = food_contacts.sum(
        -food_contacts.delta.y / food_contacts.distance.clamp_min(1.0)
    )
    food_contact_length_raw = (
        food_contact_push_x * food_contact_push_x + food_contact_push_y * food_contact_push_y
    ).sqrt()
    food_contact_length = food_contact_length_raw.clamp_min(1.0)

    food_count = food_contact_count
    hill_count = hills.count()
    inv_food = 1.0 / food_count.clamp_min(1.0)
    inv_hill = 1.0 / hill_count.clamp_min(1.0)
    food_x = food_contacts.sum(food_contacts.item[GridVoxel].x) * inv_food
    food_y = food_contacts.sum(food_contacts.item[GridVoxel].y) * inv_food
    home_x = hills.sum(hills.item[GridVoxel].x) * inv_hill
    home_y = hills.sum(hills.item[GridVoxel].y) * inv_hill

    food_dx = food_x - state.x
    food_dy = food_y - state.y
    food_distance = (food_dx * food_dx + food_dy * food_dy).sqrt().clamp_min(1.0)
    home_dx = home_x - state.x
    home_dy = home_y - state.y
    home_distance = (home_dx * home_dx + home_dy * home_dy).sqrt().clamp_min(1.0)
    home_anchor_x, home_anchor_y = _cell_center(RED_HILL if red_colony else BLUE_HILL)
    home_anchor_dx = home_anchor_x - state.x
    home_anchor_dy = home_anchor_y - state.y
    home_anchor_distance = (
        (home_anchor_dx * home_anchor_dx + home_anchor_dy * home_anchor_dy).sqrt().clamp_min(1.0)
    )

    if red_colony:
        center_food_scent = center_trails.sum(center_trails.item[PheromoneVoxel].red_food)
        left_food_scent = left_trails.sum(left_trails.item[PheromoneVoxel].red_food)
        right_food_scent = right_trails.sum(right_trails.item[PheromoneVoxel].red_food)
        center_home_scent = center_trails.sum(center_trails.item[PheromoneVoxel].red_home)
        left_home_scent = left_trails.sum(left_trails.item[PheromoneVoxel].red_home)
        right_home_scent = right_trails.sum(right_trails.item[PheromoneVoxel].red_home)
        center_home_weighted_x = center_trails.sum(center_trails.item[PheromoneVoxel].red_home_x)
        center_home_weighted_y = center_trails.sum(center_trails.item[PheromoneVoxel].red_home_y)
    else:
        center_food_scent = center_trails.sum(center_trails.item[PheromoneVoxel].blue_food)
        left_food_scent = left_trails.sum(left_trails.item[PheromoneVoxel].blue_food)
        right_food_scent = right_trails.sum(right_trails.item[PheromoneVoxel].blue_food)
        center_home_scent = center_trails.sum(center_trails.item[PheromoneVoxel].blue_home)
        left_home_scent = left_trails.sum(left_trails.item[PheromoneVoxel].blue_home)
        right_home_scent = right_trails.sum(right_trails.item[PheromoneVoxel].blue_home)
        center_home_weighted_x = center_trails.sum(center_trails.item[PheromoneVoxel].blue_home_x)
        center_home_weighted_y = center_trails.sum(center_trails.item[PheromoneVoxel].blue_home_y)

    home_vector_length = (
        (
            center_home_weighted_x * center_home_weighted_x
            + center_home_weighted_y * center_home_weighted_y
        )
        .sqrt()
        .clamp_min(1.0e-6)
    )

    margin = CELL_SIZE * 4.0
    max_x = GRID_WIDTH * CELL_SIZE - CELL_SIZE * 0.5
    max_y = GRID_HEIGHT * CELL_SIZE - CELL_SIZE * 0.5

    wander_noise = state.wander_phase.sin() + (state.wander_phase * 1.618).cos() * 0.55
    wander_angle = wander_noise * 1.35
    wander_cos = wander_angle.cos()
    wander_sin = wander_angle.sin()
    wander_dir_x = forward_x * wander_cos - forward_y * wander_sin
    wander_dir_y = forward_y * wander_cos + forward_x * wander_sin
    next_wander_phase = state.wander_phase + state.wander_rate
    food_scent_total = center_food_scent + left_food_scent + right_food_scent
    home_scent_total = center_home_scent + left_home_scent + right_home_scent

    with ecs.do:
        decision.wall_resolve_x.set_to(0.0)
        decision.wall_resolve_y.set_to(0.0)
        decision.food_resolve_x.set_to(0.0)
        decision.food_resolve_y.set_to(0.0)
        decision.steer_x.set_to(0.0)
        decision.steer_y.set_to(0.0)
        decision.returning.set_to(0.0)
        state.trail_age.set_to(state.trail_age + 1.0)

        with ecs.conditional(), ecs.when(wall_collision_count > 0), ecs.conditional():
            with ecs.when(wall_contact_length_raw >= 1.0):
                decision.wall_resolve_x.set_to(wall_contact_push_x / wall_contact_length)
                decision.wall_resolve_y.set_to(wall_contact_push_y / wall_contact_length)
            with ecs.otherwise():
                decision.wall_resolve_x.set_to(-forward_x)
                decision.wall_resolve_y.set_to(-forward_y)

        with ecs.conditional(), ecs.when(food_contact_count > 0), ecs.conditional():
            with ecs.when(food_contact_length_raw >= 1.0):
                decision.food_resolve_x.set_to(food_contact_push_x / food_contact_length)
                decision.food_resolve_y.set_to(food_contact_push_y / food_contact_length)
            with ecs.otherwise():
                decision.food_resolve_x.set_to(-forward_x)
                decision.food_resolve_y.set_to(-forward_y)

        with ecs.conditional():
            with ecs.when(state.carrying >= 0.5):
                decision.returning.set_to(1.0)
                with ecs.conditional(), ecs.when(hill_count > 0):
                    state.carrying.set_to(0.0)
                    decision.steer_x.set_to(
                        decision.steer_x
                        - state.vx * STATE_SWITCH_VELOCITY_DAMPING
                        - forward_x * TURN_AROUND_STEER
                    )
                    decision.steer_y.set_to(
                        decision.steer_y
                        - state.vy * STATE_SWITCH_VELOCITY_DAMPING
                        - forward_y * TURN_AROUND_STEER
                    )
                    state.trail_age.set_to(0.0)
            with ecs.otherwise(), ecs.conditional(), ecs.when(food_contact_count > 0):
                state.carrying.set_to(1.0)
                decision.returning.set_to(1.0)
                decision.steer_x.set_to(
                    decision.steer_x
                    - state.vx * STATE_SWITCH_VELOCITY_DAMPING
                    - forward_x * TURN_AROUND_STEER
                )
                decision.steer_y.set_to(
                    decision.steer_y
                    - state.vy * STATE_SWITCH_VELOCITY_DAMPING
                    - forward_y * TURN_AROUND_STEER
                )
                state.trail_age.set_to(0.0)

        with ecs.conditional(), ecs.when((decision.returning < 0.5) & (food_count > 0)):
            decision.steer_x.set_to(decision.steer_x + food_dx / food_distance * FOOD_STEER)
            decision.steer_y.set_to(decision.steer_y + food_dy / food_distance * FOOD_STEER)

        with ecs.conditional(), ecs.when((decision.returning >= 0.5) & (hill_count > 0)):
            decision.steer_x.set_to(decision.steer_x + home_dx / home_distance * HOME_STEER)
            decision.steer_y.set_to(decision.steer_y + home_dy / home_distance * HOME_STEER)

        with (
            ecs.conditional(),
            ecs.when(
                (decision.returning < 0.5)
                & (food_count <= 0)
                & (food_scent_total > PHEROMONE_FOLLOW_THRESHOLD)
            ),
            ecs.conditional(),
        ):
            with ecs.when(
                (center_food_scent >= left_food_scent) & (center_food_scent >= right_food_scent)
            ):
                decision.steer_x.set_to(decision.steer_x + forward_x * FOOD_PHEROMONE_STEER)
                decision.steer_y.set_to(decision.steer_y + forward_y * FOOD_PHEROMONE_STEER)
            with ecs.when(
                (left_food_scent > center_food_scent) & (left_food_scent >= right_food_scent)
            ):
                decision.steer_x.set_to(decision.steer_x + left_dir_x * FOOD_PHEROMONE_STEER)
                decision.steer_y.set_to(decision.steer_y + left_dir_y * FOOD_PHEROMONE_STEER)
            with ecs.when(
                (right_food_scent > center_food_scent) & (right_food_scent > left_food_scent)
            ):
                decision.steer_x.set_to(decision.steer_x + right_dir_x * FOOD_PHEROMONE_STEER)
                decision.steer_y.set_to(decision.steer_y + right_dir_y * FOOD_PHEROMONE_STEER)

        with (
            ecs.conditional(),
            ecs.when(
                (decision.returning >= 0.5)
                & (hill_count <= 0)
                & (home_scent_total > PHEROMONE_FOLLOW_THRESHOLD)
            ),
        ):
            with ecs.conditional():
                with ecs.when(
                    (center_home_scent >= left_home_scent) & (center_home_scent >= right_home_scent)
                ):
                    decision.steer_x.set_to(decision.steer_x + forward_x * HOME_PHEROMONE_STEER)
                    decision.steer_y.set_to(decision.steer_y + forward_y * HOME_PHEROMONE_STEER)
                with ecs.when(
                    (left_home_scent > center_home_scent) & (left_home_scent >= right_home_scent)
                ):
                    decision.steer_x.set_to(decision.steer_x + left_dir_x * HOME_PHEROMONE_STEER)
                    decision.steer_y.set_to(decision.steer_y + left_dir_y * HOME_PHEROMONE_STEER)
                with ecs.when(
                    (right_home_scent > center_home_scent) & (right_home_scent > left_home_scent)
                ):
                    decision.steer_x.set_to(decision.steer_x + right_dir_x * HOME_PHEROMONE_STEER)
                    decision.steer_y.set_to(decision.steer_y + right_dir_y * HOME_PHEROMONE_STEER)
            decision.steer_x.set_to(
                decision.steer_x + center_home_weighted_x / home_vector_length * HOME_GRADIENT_STEER
            )
            decision.steer_y.set_to(
                decision.steer_y + center_home_weighted_y / home_vector_length * HOME_GRADIENT_STEER
            )

        with ecs.conditional(), ecs.when((decision.returning >= 0.5) & (hill_count <= 0)):
            decision.steer_x.set_to(
                decision.steer_x + home_anchor_dx / home_anchor_distance * HOME_COMPASS_STEER
            )
            decision.steer_y.set_to(
                decision.steer_y + home_anchor_dy / home_anchor_distance * HOME_COMPASS_STEER
            )
            with ecs.conditional(), ecs.when(home_scent_total > PHEROMONE_FOLLOW_THRESHOLD):
                compass_suppression = HOME_COMPASS_STEER * HOME_SCENT_COMPASS_SUPPRESSION
                decision.steer_x.set_to(
                    decision.steer_x - home_anchor_dx / home_anchor_distance * compass_suppression
                )
                decision.steer_y.set_to(
                    decision.steer_y - home_anchor_dy / home_anchor_distance * compass_suppression
                )

        with ecs.conditional():
            with ecs.when(state.x < margin):
                decision.steer_x.set_to(decision.steer_x + BOUNDARY_STEER)
            with ecs.when(state.x > max_x - margin):
                decision.steer_x.set_to(decision.steer_x - BOUNDARY_STEER)

        with ecs.conditional():
            with ecs.when(state.y < margin):
                decision.steer_y.set_to(decision.steer_y + BOUNDARY_STEER)
            with ecs.when(state.y > max_y - margin):
                decision.steer_y.set_to(decision.steer_y - BOUNDARY_STEER)

        with ecs.conditional():
            with ecs.when(
                (decision.returning >= 0.5) & (home_scent_total <= PHEROMONE_FOLLOW_THRESHOLD)
            ):
                decision.steer_x.set_to(decision.steer_x + wander_dir_x * WANDER_STEER * 0.04)
                decision.steer_y.set_to(decision.steer_y + wander_dir_y * WANDER_STEER * 0.04)
            with ecs.when((decision.returning < 0.5) & (food_count > 0)):
                decision.steer_x.set_to(decision.steer_x + wander_dir_x * WANDER_STEER * 0.15)
                decision.steer_y.set_to(decision.steer_y + wander_dir_y * WANDER_STEER * 0.15)
            with ecs.when(
                (decision.returning < 0.5)
                & (food_count <= 0)
                & (food_scent_total > PHEROMONE_FOLLOW_THRESHOLD)
            ):
                decision.steer_x.set_to(
                    decision.steer_x
                    + wander_dir_x * WANDER_STEER * (1.0 - SCENT_WANDER_SUPPRESSION)
                )
                decision.steer_y.set_to(
                    decision.steer_y
                    + wander_dir_y * WANDER_STEER * (1.0 - SCENT_WANDER_SUPPRESSION)
                )
            with ecs.when(
                (decision.returning < 0.5)
                & (food_count <= 0)
                & (food_scent_total <= PHEROMONE_FOLLOW_THRESHOLD)
            ):
                decision.steer_x.set_to(decision.steer_x + wander_dir_x * WANDER_STEER)
                decision.steer_y.set_to(decision.steer_y + wander_dir_y * WANDER_STEER)

        desired_vx = state.vx + decision.steer_x + wall_push_x * WALL_STEER
        desired_vy = state.vy + decision.steer_y + wall_push_y * WALL_STEER
        desired_speed = (desired_vx * desired_vx + desired_vy * desired_vy).sqrt().clamp_min(1.0e-6)
        speed_scale = ANT_SPEED / desired_speed.clamp_min(ANT_SPEED)
        collision_velocity_x = (
            decision.wall_resolve_x * WALL_COLLISION_VELOCITY
            + decision.food_resolve_x * FOOD_COLLISION_VELOCITY
        )
        collision_velocity_y = (
            decision.wall_resolve_y * WALL_COLLISION_VELOCITY
            + decision.food_resolve_y * FOOD_COLLISION_VELOCITY
        )
        resolved_vx = desired_vx * speed_scale + collision_velocity_x
        resolved_vy = desired_vy * speed_scale + collision_velocity_y
        resolved_speed = (
            (resolved_vx * resolved_vx + resolved_vy * resolved_vy).sqrt().clamp_min(1.0e-6)
        )
        resolved_speed_scale = ANT_SPEED / resolved_speed.clamp_min(ANT_SPEED)
        next_vx = resolved_vx * resolved_speed_scale
        next_vy = resolved_vy * resolved_speed_scale
        collision_resolve_x = (
            decision.wall_resolve_x * WALL_COLLISION_RESOLVE
            + decision.food_resolve_x * FOOD_COLLISION_RESOLVE
        ).clamp(-COLLISION_CORRECTION_MAX, COLLISION_CORRECTION_MAX)
        collision_resolve_y = (
            decision.wall_resolve_y * WALL_COLLISION_RESOLVE
            + decision.food_resolve_y * FOOD_COLLISION_RESOLVE
        ).clamp(-COLLISION_CORRECTION_MAX, COLLISION_CORRECTION_MAX)
        next_x = (state.x + next_vx + collision_resolve_x).clamp(CELL_SIZE * 0.5, max_x)
        next_y = (state.y + next_vy + collision_resolve_y).clamp(CELL_SIZE * 0.5, max_y)
        next_speed = (next_vx * next_vx + next_vy * next_vy).sqrt().clamp_min(1.0e-6)
        next_forward_x = next_vx / next_speed
        next_forward_y = next_vy / next_speed
        next_left_x = (next_forward_x - next_forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        next_left_y = (next_forward_y + next_forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        next_right_x = (next_forward_x + next_forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        next_right_y = (next_forward_y - next_forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        trail_raw = (1.0 - state.trail_age / TRAIL_RUNOUT_FRAMES).clamp(0.0, 1.0)
        home_trail_strength = trail_raw * trail_raw
        food_trail_strength = 0.45 + trail_raw * 0.55

        state.x.set_to(next_x)
        state.y.set_to(next_y)
        state.vx.set_to(next_vx)
        state.vy.set_to(next_vy)
        state.wander_phase.set_to(next_wander_phase)
        state.sensor_center_x.set_to(next_x + next_forward_x * SENSOR_DISTANCE)
        state.sensor_center_y.set_to(next_y + next_forward_y * SENSOR_DISTANCE)
        state.sensor_left_x.set_to(next_x + next_left_x * SENSOR_DISTANCE)
        state.sensor_left_y.set_to(next_y + next_left_y * SENSOR_DISTANCE)
        state.sensor_right_x.set_to(next_x + next_right_x * SENSOR_DISTANCE)
        state.sensor_right_y.set_to(next_y + next_right_y * SENSOR_DISTANCE)
        state.home_dir_x.set_to(0.0)
        state.home_dir_y.set_to(0.0)
        state.home_trail.set_to(0.0)
        state.food_trail.set_to(0.0)
        with ecs.conditional():
            with ecs.when(state.carrying < 0.5):
                state.home_dir_x.set_to(-next_forward_x * home_trail_strength)
                state.home_dir_y.set_to(-next_forward_y * home_trail_strength)
                state.home_trail.set_to(home_trail_strength)
            with ecs.otherwise(), ecs.conditional(), ecs.when(trail_raw > 0.0):
                state.food_trail.set_to(food_trail_strength)
