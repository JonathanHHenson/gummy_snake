"""Device sensors, motion callbacks, fullscreen/focus, and cursor environment state."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/05_interaction/sensors_environment.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

EVENT_LOG: list[str] = []
LAST_INJECTED_STEP = -1
SENSOR_SAMPLES = (
    {
        "acceleration_x": 2.0,
        "acceleration_y": 0.35,
        "acceleration_z": 0.2,
        "rotation_x": 0.1,
        "rotation_y": 0.25,
        "rotation_z": 1.1,
        "orientation": "landscape",
    },
    {
        "acceleration_x": -1.2,
        "acceleration_y": 1.4,
        "acceleration_z": 0.4,
        "rotation_x": 1.0,
        "rotation_y": 0.35,
        "rotation_z": 0.45,
        "orientation": "portrait",
    },
    {
        "acceleration_x": 0.2,
        "acceleration_y": -1.8,
        "acceleration_z": 0.8,
        "rotation_x": 0.4,
        "rotation_y": 1.2,
        "rotation_z": 0.1,
        "orientation": "landscape",
    },
)


def _remember(message: str) -> None:
    EVENT_LOG.append(message)
    del EVENT_LOG[:-7]


def device_moved(event) -> None:
    delta = event.acceleration - event.previous_acceleration
    _remember(f"{gs.DEVICE_MOVED}: Δaccel=({delta.x:.1f}, {delta.y:.1f}, {delta.z:.1f})")


def device_turned(event) -> None:
    _remember(f"{gs.DEVICE_TURNED}: axis={event.turn_axis} rotation_z={event.rotation_z:.1f}")


def device_shaken(event) -> None:
    magnitude = (event.acceleration_x**2 + event.acceleration_y**2 + event.acceleration_z**2) ** 0.5
    _remember(f"{gs.DEVICE_SHAKEN}: |accel|={magnitude:.1f}")


def setup() -> None:
    gs.create_canvas(720, 430)
    gs.set_move_threshold(0.4)
    gs.set_shake_threshold(1.5)
    gs.fullscreen(False)
    gs.no_cursor()
    gs.cursor("crosshair")


def _inject_current_sample() -> None:
    global LAST_INJECTED_STEP
    step = min(gs.frame_count(), len(SENSOR_SAMPLES) - 1)
    if step != LAST_INJECTED_STEP:
        LAST_INJECTED_STEP = step
        gs.inject_sensor_sample(**SENSOR_SAMPLES[step])


def _draw_acceleration_gauge(x: float, y: float) -> None:
    center_x = x + 110
    center_y = y + 105
    gs.stroke(80, 94, 120)
    gs.no_fill()
    gs.circle(center_x, center_y, 150)
    gs.line(center_x - 85, center_y, center_x + 85, center_y)
    gs.line(center_x, center_y - 85, center_x, center_y + 85)

    end_x = center_x + gs.acceleration_x() * 45
    end_y = center_y - gs.acceleration_y() * 45
    gs.stroke(255, 190, 80)
    gs.line(center_x, center_y, end_x, end_y)
    gs.no_stroke()
    gs.fill(255, 190, 80)
    gs.circle(end_x, end_y, 12)
    gs.fill(220)
    gs.text("acceleration x/y", x + 36, y + 204)


def _draw_rotation_bars(x: float, y: float) -> None:
    values = (
        ("x", gs.rotation_x(), gs.p_rotation_x(), (110, 180, 255)),
        ("y", gs.rotation_y(), gs.p_rotation_y(), (130, 230, 150)),
        ("z", gs.rotation_z(), gs.p_rotation_z(), (255, 120, 150)),
    )
    for index, (axis, value, previous, color) in enumerate(values):
        row_y = y + index * 48
        gs.fill(180)
        gs.text(f"rotation_{axis}: {value:.2f}  previous: {previous:.2f}", x, row_y)
        gs.fill(*color)
        gs.rect(x, row_y + 10, max(4, abs(value) * 110), 16)
        gs.fill(95, 105, 130)
        gs.rect(x, row_y + 29, max(4, abs(previous) * 110), 8)


def draw() -> None:
    _inject_current_sample()

    gs.background(16, 21, 34)
    gs.no_stroke()
    gs.fill(245)
    gs.text_size(22)
    gs.text("Sensors + environment state", 32, 40)
    gs.text_size(14)
    gs.text(
        f"focused={gs.focused()} | fullscreen={gs.fullscreen()} | cursor={gs.cursor()} | "
        f"orientation={gs.device_orientation()} | turn_axis={gs.turn_axis()}",
        32,
        70,
    )
    gs.text(
        "Synthetic sensor samples are injected so this example is deterministic in headless runs.",
        32,
        94,
    )

    _draw_acceleration_gauge(42, 128)
    _draw_rotation_bars(315, 144)

    gs.fill(220)
    gs.text("motion callback log", 315, 310)
    gs.fill(160, 170, 195)
    for index, message in enumerate(EVENT_LOG[-5:]):
        gs.text(message, 315, 334 + index * 18)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(
        setup=setup,
        draw=draw,
        device_moved=device_moved,
        device_turned=device_turned,
        device_shaken=device_shaken,
        headless=ARGS.headless,
        max_frames=ARGS.frames,
    )
