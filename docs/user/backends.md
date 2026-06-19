# Runtime modes

The public `p5-py` API is backend-agnostic. Sketch code should call `create_canvas()`, `background()`, `image()`, `load_pixels()`, and other public APIs without depending on renderer internals.

At runtime, drawing, presentation, image asset loading/saving, text, pixel readback/update, and canvas export are owned by the Rust `p5_canvas` extension exposed as `p5.rust._canvas`.

## Modes

### Bounded/headless

Use bounded/headless mode for:

- CI
- unit/integration tests
- PNG export
- reproducible examples

Examples:

```python
p5.run(setup=setup, draw=draw, headless=True, max_frames=1)
```

```sh
uv run python examples/basic_shapes.py --headless --frames 1
```

Bounded/headless mode still uses the canvas runtime; it does not switch to Pillow or another Python image backend.

### Interactive

Use interactive mode for native windows and input:

```python
p5.run(setup=setup, draw=draw, headless=False)
```

Interactive mode requires an installed `p5.rust._canvas` extension with native window support. If native window support is unavailable, bounded/headless runs can still work while unbounded interactive runs raise `BackendCapabilityError` with rebuild guidance.

## Images and assets

`load_image()`, `create_image().save()`, drawing with `image()`, and canvas export are canvas-owned. Published wheels must include `p5.rust._canvas`; otherwise image loading fails with `BackendCapabilityError` because there is no supported Pillow fallback.

## HiDPI

`p5-py` distinguishes logical sketch size from physical backing-buffer size.

- `width()` and `height()` report logical canvas dimensions.
- `pixel_density()` controls backing scale.
- `display_density()` reports native display density when supported.

See `docs/technical/hidpi_rendering.md` for the full model.

## Offscreen graphics

`create_graphics()`, `create_framebuffer()`, and `no_canvas()` are explicit
deferred APIs. They raise `UnsupportedFeatureError` instead of falling back to a
separate Python renderer or exposing canvas internals. Bounded/headless runs
already use an offscreen `p5_canvas` surface for the main sketch; user-created
offscreen render targets still need native ownership, resize, readback, and
cleanup semantics in `p5_canvas`.

See `docs/technical/offscreen_graphics_framebuffer_design.md` for the planned
ownership model.

## Related docs

- `docs/technical/canvas_required_runtime.md`
- `docs/technical/canvas_migration_release.md`
- `docs/technical/offscreen_graphics_framebuffer_design.md`
- `docs/technical/p5_canvas_rust_backend.md`
