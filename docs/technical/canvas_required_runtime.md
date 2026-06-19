# Canvas required runtime

## Decision

p5-py now requires the Rust `p5_canvas` runtime. The public runtime no longer
accepts a backend selector. Sketches run on canvas implicitly and choose
bounded/offscreen versus interactive behavior with `headless=True` or
`headless=False`.

## Rationale

The old migration architecture kept a backend registry so Pillow could provide
deterministic offscreen rendering while Pyglet provided windows, input, and the
native WEBGL follow-on path. That split made public API behavior depend on
backend-specific capability gaps. Canvas now owns rendering, presentation,
readback/export, images, text, input normalization, and bounded offscreen runs,
so preserving the registry and fallback backends adds complexity without a
supported user path.

## Runtime Modes

- Bounded runs: pass `headless=True`, pass `max_frames`, or use an example
  `--headless` / `--frames` argument. Canvas allocates an offscreen surface and
  exits after the requested frames.
- Interactive runs: pass `headless=False`, use an example `--interactive`, or
  omit `max_frames`. Canvas opens a native window when the installed
  `p5.rust._canvas` extension was built with native window support.
- Missing native window support: bounded runs still work; unbounded interactive
  runs raise `BackendCapabilityError` with rebuild guidance.
- Missing canvas extension: package startup raises `BackendCapabilityError`
  with the local `uvx maturin develop ... p5_canvas ...` build command.

## Removed Pieces

- `PygletBackend`, `PygletRenderer`, and `PygletWebGLRenderer`
- `HeadlessBackend`, `PillowRenderer`, and the `pillow` backend alias
- Pyglet and Pillow project dependencies
- Custom backend registration as a supported extension point

## Remaining Extension Points

- p5 plugins may hook lifecycle events and add high-level sketch helpers.
- Public asset, geometry, color, and drawing APIs remain Python APIs over the
  canvas runtime.
- Future native acceleration should extend `p5_canvas` or isolated Rust/Python
  helper modules, not introduce a second public runtime backend.
- Future offscreen graphics and framebuffer APIs must be implemented as
  `p5_canvas` render targets behind Python adapter objects. `create_graphics()`,
  `create_framebuffer()`, and `no_canvas()` currently raise package-specific
  deferred errors; see `docs/technical/offscreen_graphics_framebuffer_design.md`.

## Migration Notes

Sketches that previously selected the Pyglet backend should remove that
argument and use `headless=False` only when they need to force interactive
mode. Workflows that previously selected the old headless or Pillow paths
should use `headless=True` or a finite `max_frames` value.
