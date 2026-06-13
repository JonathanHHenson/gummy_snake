# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project overview

This repository contains `p5-py`, a Pythonic creative-coding package inspired by p5.js.

The goal is to provide a familiar p5-style sketching model for Python while keeping the implementation idiomatic, maintainable, typed, testable, and backend-agnostic.

The package must remain native Python. Do not add JavaScript or HTML code.

## Package workflow

This project uses `uv`.

Use `uv` for dependency and command execution:

```sh
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format .
uv run python examples/basic_shapes.py --backend headless --frames 1
```

Do not use raw `pip install` or unmanaged virtual environments unless explicitly requested.

The active Python version is defined by `.python-version` and `pyproject.toml`.

## Source layout

Primary package code lives under:

```text
src/p5_py/
```

Important areas:

```text
src/p5_py/api/          global-mode API, p5.js aliases, compatibility stubs
src/p5_py/backends/     backend implementations and backend registry
src/p5_py/core/         color, geometry, state, transforms, math-like core systems
src/p5_py/drawing/      renderer protocol and drawing abstractions
src/p5_py/events/       normalized input/event state
src/p5_py/pixels/       future pixel-buffer functionality
src/p5_py/plugins/      future plugin architecture
src/p5_py/rust/         future Rust acceleration integration
src/p5_py/testing/      future testing helpers
```

Tests live under:

```text
tests/
```

Examples live under:

```text
examples/
```

Docs live under:

```text
docs/
```

Backlog items live under:

```text
backlog/<three_digit_epic_name>/<pbi_name>.toml
```

## Architecture principles

### Keep public API backend-agnostic

The public p5-py API must not directly depend on Pillow, Pyglet, or any future renderer.

The intended layering is:

```text
user sketch
  ↓
p5_py public API
  ↓
Sketch / SketchContext
  ↓
Renderer + Backend protocols
  ↓
Concrete backend / renderer
```

### Separate backend responsibilities from renderer responsibilities

Backends own platform/window/runtime concerns.

Renderers own drawing.

For example:

- `PygletBackend` should own window creation, the event loop, input normalization, frame scheduling, and shutdown.
- A future `PygletRenderer` should own native Pyglet drawing.
- `PillowRenderer` should remain the deterministic headless/export renderer.

Do not push sketch lifecycle, p5.js aliasing, or argument parsing into backend-specific code.

### Preserve custom backend support

Future custom backends should be able to integrate by implementing the backend and renderer protocols and registering themselves through the backend registry.

Avoid hardcoding backend classes outside `p5_py.backends.registry` and backend selection logic.

### Keep p5 compatibility and Pythonic API together

Canonical Python APIs should use `snake_case`, for example:

```python
create_canvas()
frame_rate()
no_loop()
pixel_density()
```

p5.js-style aliases may be provided where useful:

```python
createCanvas()
frameRate()
noLoop()
pixelDensity()
```

Aliases must delegate to the same implementation. Do not duplicate behavior.

### Keep exports type-checker friendly

`src/p5_py/__init__.py` should use explicit imports for public APIs. Avoid dynamic wildcard export machinery that makes Zed/Pyright unable to see package attributes.

## Rendering guidance

### Current rendering state

The current Pyglet backend is a bridge backend:

```text
PillowRenderer renders the frame
PygletBackend presents that image in a native Pyglet window
```

This is intentional for now. See:

```text
docs/technical/native_pyglet_renderer.md
```

The planned next rendering milestone is a native `PygletRenderer`.

### HiDPI and pixel density

p5-py distinguishes logical canvas dimensions from physical backing-buffer dimensions.

- `width()` and `height()` are logical p5 dimensions.
- `pixel_density()` controls physical backing scale.
- `display_density()` reports native display scale when the backend supports it.
- `load_pixels()` and `update_pixels()` currently operate on physical RGBA buffers.

See:

```text
docs/technical/hidpi_rendering.md
```

Do not regress Retina/HiDPI behavior when changing renderers or backends.

## Exclusions

Do not add:

- JavaScript code
- HTML code
- DOM APIs
- browser-only APIs
- `p5.XML`
- `p5.Table`
- `p5.TableRow`

Excluded APIs should raise clear package-specific errors when exposed as compatibility stubs.

## Backlog conventions

Backlog epics use a three-digit prefix to allow insertion between epics, for example:

```text
010_foundation_runtime
020_api_compatibility
030_rendering_2d
031_native_pyglet_renderer
040_color_style_transform
```

Each PBI file must use this TOML layout:

```toml
[my_pbi]
title = "..."
description = '''
As a ...,
I want ...,
So that ...
'''
acceptance_criteria = '''
...
'''
priotity = 'high|medium|low'
status = 'TODO|IN_PROGRESS|DONE'

[my_pbi.task_1]
order = 1
status = 'TODO|IN_PROGRESS|DONE'
description = '''
...
'''
```

Note: the existing schema intentionally uses the misspelled key `priotity`. Preserve it unless the user explicitly requests a schema migration.

When completing work that corresponds to backlog items, update both PBI and task statuses.

Allowed status values are:

```text
TODO
IN_PROGRESS
DONE
```

Validate backlog TOML after edits:

```sh
python - <<'PY'
from pathlib import Path
import tomllib
for path in sorted(Path('backlog').glob('**/*.toml')):
    with path.open('rb') as f:
        tomllib.load(f)
print('Backlog TOML parsed successfully')
PY
```

## Testing and validation

Before finishing code changes, run:

```sh
uv run ruff check .
uv run pytest
```

If formatting changes are needed, run:

```sh
uv run ruff format .
```

Also check Zed diagnostics when practical.

For rendering changes, run at least one headless example smoke test, such as:

```sh
uv run python examples/basic_shapes.py --backend headless --frames 1
```

If examples generate output files, do not accidentally commit generated artifacts unless the user explicitly wants them tracked.

## Test expectations

Add or update tests when changing behavior.

Current useful test areas:

```text
tests/contracts/       backend and renderer contract behavior
tests/integration/     end-to-end sketch rendering behavior
tests/unit/            API, lifecycle, color, transforms, density, backend details
```

Prefer deterministic headless tests for renderer behavior where possible.

For interactive Pyglet behavior, use focused unit tests with fake window/module objects when possible, and document any manual smoke tests.

## Documentation expectations

Update docs when changing architecture, public APIs, rendering behavior, backend behavior, or compatibility status.

Relevant docs include:

```text
docs/technical/project_plan.md
docs/technical/hidpi_rendering.md
docs/technical/native_pyglet_renderer.md
```

## Rust guidance

Rust acceleration is planned but should remain optional and contained.

Future Rust code should live under:

```text
crates/
```

Rust should be used only for pure computational hot paths such as:

- noise generation
- pixel filters
- blend modes
- color conversion
- geometry tessellation
- path flattening

Every Rust-accelerated feature must have a Python fallback unless the user explicitly changes this requirement.

## Dependency guidance

Prefer existing dependencies already in `pyproject.toml`.

Current core dependencies include:

- Pillow
- Pyglet

Current dev dependencies include:

- pytest
- ruff

Add new dependencies only when justified by the task, and use `uv add` or `uv add --dev` so `pyproject.toml` and `uv.lock` stay in sync.

## Safety notes

- Do not modify the sibling `p5.js` repository unless the user explicitly asks.
- Do not commit changes unless the user explicitly asks.
- Do not remove or overwrite generated/user files unless you are sure they are artifacts from your own validation commands.
- Keep changes focused on the requested task.
