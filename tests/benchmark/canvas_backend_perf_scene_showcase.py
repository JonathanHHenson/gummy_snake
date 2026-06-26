from __future__ import annotations

import math
from typing import Any

from canvas_backend_perf_scene_core import draw_starfield
from canvas_backend_perf_scene_state import SceneState


def draw_asteroids_scene(gs: Any, state: SceneState) -> None:
    gs.image_mode(gs.CENTER)
    gs.background(7, 10, 22)
    draw_starfield(gs, 96)
    for shot in state.shots:
        shot[0] = (shot[0] + shot[2]) % 720
        shot[1] = (shot[1] + shot[3]) % 480
        gs.stroke(120, 220, 255)
        gs.stroke_weight(3)
        gs.line(shot[0], shot[1], shot[0] - shot[2] * 2.2, shot[1] - shot[3] * 2.2)
    for asteroid in state.asteroids:
        asteroid[0] = (asteroid[0] + asteroid[2]) % 720
        asteroid[1] = (asteroid[1] + asteroid[3]) % 480
        asteroid[5] += 0.025
        with gs.pushed():
            gs.translate(asteroid[0], asteroid[1])
            gs.rotate(asteroid[5])
            gs.image(
                state.sprites[int(asteroid[4]) % len(state.sprites)],
                0,
                0,
                asteroid[4] * 2,
                asteroid[4] * 2,
            )
            gs.no_fill()
            gs.stroke(190, 200, 220, 170)
            gs.stroke_weight(2)
            gs.circle(0, 0, asteroid[4] * 2.2)
    with gs.pushed():
        gs.translate(360, 240)
        gs.rotate(-math.pi / 2 + math.sin(gs.frame_count() * 0.04) * 0.7)
        gs.image(state.sprites[0], 0, 0, 88, 64)
        gs.stroke(90, 180, 255)
        gs.line(0, 0, 56, 0)
    gs.fill(245)
    gs.no_stroke()
    gs.text_size(18)
    gs.text(f"wave 4   shots {len(state.shots)}   rocks {len(state.asteroids)}", 24, 34)


def draw_webgl_3d(gs: Any, state: SceneState) -> None:
    gs.background(10, 14, 28)
    gs.ambient_light(45)
    gs.directional_light(255, 244, 230, -0.45, -0.7, -1.0)
    gs.point_light(100, 180, 255, 160, -130, 220)

    with gs.pushed():
        gs.translate(-185, 0)
        gs.rotate(gs.frame_count() * 0.035)
        gs.specular_material(240, 150, 90)
        gs.shininess(18)
        gs.box(120)

    with gs.pushed():
        gs.translate(25, 8)
        gs.normal_material()
        gs.sphere(78, 28, 18)

    with gs.pushed():
        gs.translate(225, 24)
        gs.texture(state.sprites[0])
        gs.rotate(-0.35)
        gs.plane(135, 135)

    with gs.pushed():
        gs.translate(0, 155)
        gs.ambient_material(44, 62, 92)
        gs.plane(650, 160)


def _star(gs: Any, cx: float, cy: float, outer: float, inner: float, points: int) -> None:
    for i in range(points * 2):
        radius = outer if i % 2 == 0 else inner
        angle = -math.pi / 2 + i * math.pi / points
        gs.vertex(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)


def draw_contours_clipping_tint(gs: Any, state: SceneState) -> None:
    gs.background(250, 248, 242)

    gs.no_stroke()
    gs.fill(244, 188, 67)
    gs.circle(150, 180, 82)
    gs.fill(42, 87, 143)
    with gs.shape(gs.CLOSE):
        _star(gs, 150, 180, 112, 54, 7)
        with gs.contour():
            for i in range(28):
                angle = -math.tau * i / 28
                gs.vertex(150 + math.cos(angle) * 38, 180 + math.sin(angle) * 38)

    with gs.clip_path():
        for i in range(36):
            angle = math.tau * i / 36
            wave = 18 * math.sin(angle * 3 + gs.frame_count() * 0.08)
            gs.vertex(
                430 + math.cos(angle) * (142 + wave),
                186 + math.sin(angle) * (96 + wave),
            )
    gs.background(238, 242, 232)
    gs.no_stroke()
    for row in range(8):
        for col in range(11):
            gs.fill(40 + col * 16, 104 + row * 10, 174, 210)
            gs.rect(294 + col * 29, 82 + row * 29, 22, 22)
    gs.end_clip()

    gs.no_fill()
    gs.stroke(32, 45, 63)
    gs.stroke_weight(3)
    with gs.shape(gs.CLOSE):
        for i in range(36):
            angle = math.tau * i / 36
            gs.vertex(430 + math.cos(angle) * 142, 186 + math.sin(angle) * 96)

    assert state.stamp is not None
    gs.image_mode(gs.CENTER)
    for i, color in enumerate([(227, 88, 75, 230), (45, 150, 112, 220), (247, 183, 60, 210)]):
        gs.tint(*color)
        gs.image(state.stamp, 610, 128 + i * 58, 62, 62)
    gs.no_tint()
    gs.image(state.stamp, 690, 186, 72, 72)
    gs.image_mode(gs.CORNER)

    gs.no_stroke()
    gs.fill(30, 34, 44)
    gs.text_size(16)
    gs.text("contour hole", 92, 330)
    gs.text("path clipping", 378, 330)
    gs.text("image tint", 598, 330)
