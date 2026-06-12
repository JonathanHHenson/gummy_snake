# Native Pyglet renderer plan

## Current state

The interactive Pyglet backend now uses a native renderer by default:

```text
p5-py public API
  ↓
SketchContext
  ↓
Renderer protocol
  ↓
PygletRenderer
  ↓
Pyglet shape draw commands
  ↓
Pyglet/OpenGL framebuffer
```

The previous bridge backend was useful for the first implementation because it gave p5-py one deterministic renderer for both tests and interactive sketches. The native path removes the per-frame Pillow raster upload from the default interactive backend while preserving the same public p5-py APIs.

Pillow remains the deterministic renderer for the headless backend, golden tests, pixel-buffer workflows, and non-interactive export.

## Architecture

The architecture separates the window/event backend from the renderer:

```text
p5-py public API
  ↓
SketchContext
  ↓
Renderer protocol
  ↓
PygletRenderer
  ↓
Pyglet/OpenGL framebuffer
```

With this split:

- `PygletBackend` owns the window, event loop, input events, resize events, frame scheduling, and shutdown.
- `PygletRenderer` owns native drawing operations.
- `SketchContext` continues to depend only on the renderer/backend protocols.
- The public API remains unchanged.
- Pillow remains the deterministic headless renderer and export/golden-test path.

## Module layout

The first native milestone keeps the backend as a single file and adds a separate renderer module:

```text
src/p5_py/backends/pyglet.py            # window, event loop, input, scheduling
src/p5_py/backends/pyglet_renderer.py   # native drawing through Pyglet shapes
```

The backend can still be split into a package later if Pyglet-specific event, renderer, or capability code grows enough to justify it.

## Responsibilities

### `PygletBackend`

Responsible for:

- creating the native window
- detecting display density / framebuffer size
- running the Pyglet event loop
- scheduling frames
- normalizing mouse and keyboard events
- forwarding resize and close events
- exposing backend capabilities

Not responsible for:

- parsing p5-style arguments
- managing drawing style state
- implementing p5.js aliases
- owning sketch lifecycle semantics
- deciding fill/stroke behavior

### `PygletRenderer`

Responsible for:

- `begin_frame` / `end_frame`
- `background` and `clear`
- points, lines, polygons, rectangles, ellipses, arcs
- fill and stroke rendering
- transform application
- HiDPI coordinate mapping
- capability errors for APIs that are not implemented natively yet
- pixel/export capability handling

## Rendering approach options

### Pyglet shapes

Pros:

- simple first implementation
- clean dependency story
- works with Pyglet's supported public APIs

Cons:

- may not support all stroke joins/caps/fill rules needed for p5 fidelity
- complex paths may require flattening and triangulation

### Batched vertex lists

Pros:

- better performance than recreating shapes every frame
- more control over geometry

Cons:

- more renderer complexity
- requires careful lifecycle and batching design

### Direct OpenGL or ModernGL-style rendering

Pros:

- best long-term performance/control
- natural path toward WEBGL-like features later

Cons:

- larger implementation scope
- shader and context management complexity
- more difficult to keep beginner-friendly and cross-platform

## First native renderer milestone

The first native renderer uses Pyglet shapes plus shared p5-py geometry helpers. This keeps the implementation small and on public Pyglet APIs before introducing lower-level batching or custom OpenGL geometry.

Implemented:

- `background`
- `clear`
- `point`
- `line`
- `polygon`
- `rect`
- `square`
- `ellipse`
- `circle`
- `triangle`
- `quad`
- `arc`

The public `SketchContext` continues to flatten these into renderer polygons or polylines before calling the renderer:

- Bezier curves
- quadratic curves
- custom shapes created by `begin_shape`, `vertex`, `quadratic_vertex`, `bezier_vertex`, and `end_shape`
- arcs where native support is insufficient

## HiDPI behavior

The native renderer preserves the current pixel-density model:

- `width()` and `height()` are logical p5 canvas dimensions.
- `display_density()` reports the native display density when available.
- `pixel_density()` controls the logical-to-physical scale.
- Pyglet native drawing should not double-scale on Retina displays.

`PygletRenderer` receives logical p5 coordinates, applies the active p5-py affine transform, scales by `pixel_density`, and flips the y axis into Pyglet's bottom-left framebuffer coordinate system:

```text
framebuffer_x = logical_x * pixel_density
framebuffer_y = physical_height - logical_y * pixel_density
```

The renderer tracks both logical dimensions and physical framebuffer dimensions so `width()`, `height()`, `pixel_density()`, and `display_density()` remain distinct concepts.

## Pixel and export APIs

The native renderer capability-gates these APIs in the first milestone:

- `image`
- `text`
- `text_width`, `text_ascent`, and `text_descent`
- `load_pixels`
- `update_pixels`
- `save_canvas`

They raise `BackendCapabilityError` with guidance to use the headless backend. Pillow remains the canonical deterministic path for image drawing, text rendering, pixel reads/writes, image export, and golden tests.

Epic `061_native_pyglet_assets_text_export` tracks native support for these remaining renderer-dependent APIs. In particular, `native_save_canvas_pixels.toml` requires `save_canvas` to work in the Pyglet backend by capturing the native framebuffer with correct p5 top-left orientation and physical HiDPI dimensions. The same framebuffer readback path should also be evaluated for `load_pixels`; `update_pixels` may either upload to a native texture/framebuffer path or remain explicitly capability-gated with documentation.

## Migration status

1. `PygletRenderer` exists as a concrete implementation of the `Renderer` protocol.
2. Basic primitive rendering is implemented through Pyglet-native draw commands.
3. Transform, path, and curve support is provided by applying p5-py transform matrices and reusing shared geometry flattening before renderer calls.
4. HiDPI logical and physical dimensions are covered by focused unit tests.
5. Image, text, pixel, and export behavior is explicitly capability-gated for the native renderer until epic `061_native_pyglet_assets_text_export` is implemented.
6. `PygletBackend` uses `PygletRenderer` by default.
7. The bridge-specific Pillow image upload path has been removed from the default Pyglet backend.
8. The headless Pillow backend remains available for deterministic export and tests.
