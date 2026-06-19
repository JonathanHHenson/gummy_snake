# Offscreen graphics and framebuffer design

## Status

Offscreen graphics and framebuffer APIs are deferred. The public names
`create_graphics()`, `create_framebuffer()`, `drawing_context()`, and
`no_canvas()` exist only as package-specific stubs that raise
`UnsupportedFeatureError`.

This is intentional. The current runtime requires `p5_canvas` for drawing,
presentation, image loading/saving, text, pixels, export, and native input. A
Python fallback surface would reintroduce backend-dependent rendering behavior
and split HiDPI/readback semantics.

## Public API shape

The planned public surface is Pythonic and renderer-neutral:

- `create_graphics(width, height, renderer=P2D, *, pixel_density=None)` should
  return an offscreen graphics object with p5-style drawing methods.
- `create_framebuffer(width, height, *, pixel_density=None, depth=False, stencil=False)`
  should return a lower-level render target for advanced composition.
- `drawing_context()` remains excluded as a direct context escape hatch; a
  future replacement must be backend-neutral and must not expose Rust or browser
  canvas internals.
- `no_canvas()` remains excluded until it has a concrete canvas-runtime meaning.
  A future implementation would mean no user-presented main surface, not no
  canvas runtime.

Public objects must not expose `p5.rust._canvas` handles, native window objects,
GPU texture IDs, or browser-style drawing contexts.

## Ownership boundaries

`SketchContext` owns sketch lifecycle, current context routing, p5 state stacks,
logical dimensions, pixel-density policy, and plugin hooks. It may hold public
offscreen objects, but it should not allocate render targets directly.

`CanvasBackend` owns runtime mode, scheduling, native presentation, event
dispatch, shutdown, and display density. It may request target creation from
the canvas runtime, but it should not translate drawing commands.

`CanvasRenderer` owns drawing translation and render-target binding. It should
mirror logical dimensions and pixel density for the active target, push/pop
renderer state when drawing into offscreen targets, and prevent state leaks
between the main canvas and offscreen objects.

`p5_canvas` owns native render-target allocation, physical buffer dimensions,
depth/stencil attachments, target switching, readback, resize, cleanup, and
export/compositing primitives. Rust handles should stay private behind Python
adapter classes.

## Required semantics before implementation

- Logical width/height remain p5 units; backing dimensions are
  `logical * pixel_density`.
- `load_pixels()` and framebuffer readback return physical top-left-oriented
  RGBA buffers, matching the main canvas.
- Drawing an offscreen target into the main canvas should use the normal
  `image()` path or a dedicated renderer-neutral composition method.
- Resizing a target reallocates native storage and invalidates stale readback
  buffers.
- `remove()` or context shutdown releases native storage deterministically.
- Normal drawing should not perform CPU readback. Readback happens only when
  requested by pixel/export APIs.
- Headless and interactive modes must share the same API behavior, with
  capability errors only for native features that truly require window/GPU
  support.

## Deferred public behavior

Until the above runtime contract exists, the public stubs fail early:

- `create_graphics(...)` raises `UnsupportedFeatureError` with this design doc.
- `create_framebuffer(...)` raises `UnsupportedFeatureError` with this design
  doc.
- `drawing_context()` raises `UnsupportedFeatureError` with this design doc.
- `no_canvas()` raises `UnsupportedFeatureError` explaining that p5-py still
  requires a `p5_canvas` surface, including bounded/headless runs.

This keeps reference compatibility discoverable without implying that users can
depend on incomplete offscreen rendering behavior.
