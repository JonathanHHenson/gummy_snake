# Rendering backends

The public `p5-py` API is backend-agnostic.

Your sketch code should call `create_canvas()`, `background()`, `image()`, `load_pixels()`, and other public APIs without depending on backend internals.

## Available backends

### `headless`

Deterministic Pillow-backed rendering intended for:

- CI
- unit/integration tests
- PNG export
- reproducible examples

### `pillow`

Currently an alias of `headless`.

### `pyglet`

Interactive native backend intended for:

- windows and event loops
- normalized keyboard and mouse input
- native presentation
- HiDPI-aware interactive drawing

## Choosing a backend

Use `headless` when you need reproducibility.
Use `pyglet` when you need an actual interactive window.

Examples:

```python
p5.run(setup=setup, draw=draw, backend="headless", max_frames=1)
```

```python
p5.run(setup=setup, draw=draw, backend="pyglet")
```

## HiDPI

`p5-py` distinguishes logical sketch size from physical backing-buffer size.

- `width()` and `height()` report logical canvas dimensions.
- `pixel_density()` controls backing scale.
- `display_density()` reports native display density when supported.

See `docs/technical/hidpi_rendering.md` for the full model.

## Current renderer strategy

The headless path uses Pillow directly.
The current native Pyglet path supports native presentation and a growing native renderer surface while preserving deterministic fallback behavior for parity-sensitive operations.

See `docs/technical/native_pyglet_renderer.md` for current implementation notes.
