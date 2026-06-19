# Canvas Removal Release Validation

Epics 130-132 completed the migration from the old Pillow/Pyglet split to the
required `p5_canvas` runtime. This document records the final validation areas
for releases that contain the removal.

## Required Runtime

- Canvas is implicit; there is no public backend selector.
- `headless=True` requests bounded/offscreen canvas runtime behavior.
- `headless=False` requests interactive canvas runtime behavior.

## Validation

Run:

```sh
uv run ruff check .
uv run pytest
uv run python examples/basic_shapes.py --headless --frames 1
```

For canvas-specific native validation, run representative examples twice:

- bounded/offscreen: `--headless --frames 1`
- interactive: `--interactive` on a desktop build with native window support

Interactive smoke tests should confirm that windows open, draw, receive input
where the example uses it, resize without corrupting logical coordinates, and
close cleanly.

## Packaging

Pillow and Pyglet are no longer project dependencies. Published wheels must include the Rust canvas extension at `p5.rust._canvas`; pure-Python runtime wheels are invalid because image assets, rendering, text, pixel APIs, export, and presentation are canvas-owned.

Source installs require Rust tooling to build the canvas extension for runtime construction. Missing extension errors must mention the local `uvx maturin develop ... crates/p5_canvas ...` build command.

## Rollback

The removal does not retain a runtime fallback backend. A rollback must restore
the removed backend modules, dependencies, registry entries, and tests together;
selectively re-adding only the registry aliases is not supported.
