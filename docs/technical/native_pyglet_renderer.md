# Native Pyglet renderer plan

## Current state

The interactive Pyglet backend uses `PygletRenderer` by default. The renderer uses native Pyglet draw objects for normal frames. A deterministic Pillow parity surface is kept for p5-fidelity features that require pixel-exact compositing, and it is activated lazily only when a sketch uses pixel upload, `blend`, `erase`, or non-default blend modes:

```text
p5-py public API
  ↓
SketchContext
  ↓
Renderer protocol
  ↓
PygletRenderer
  ↓
Pillow parity surface for exact 2D semantics
  ↓
Pyglet texture presentation
  ↓
Pyglet/OpenGL framebuffer
```

Normal primitive, image, and text frames present the native Pyglet batch directly. When a parity-only feature is used, the renderer switches to presenting the parity surface so `update_pixels`, `blend`, `erase`, and related readback/export behavior match the headless/Pillow behavior without imposing a full-canvas texture upload on every ordinary frame.

Pillow remains the deterministic renderer for the headless backend, golden tests, and non-interactive export.

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
Pillow parity surface + Pyglet texture presentation
  ↓
Pyglet/OpenGL framebuffer
```

With this split:

- `PygletBackend` owns the window, event loop, input events, resize events, frame scheduling, and shutdown.
- `PygletRenderer` owns Pyglet presentation and switches to a deterministic parity surface only for pixel/compositing features that need it.
- `SketchContext` continues to depend only on the renderer/backend protocols.
- The public API remains unchanged.
- Pillow remains the deterministic headless renderer and export/golden-test path.

## Module layout

The first native milestone keeps the backend as a single file and adds a separate renderer module:

```text
src/p5_py/backends/pyglet.py                 # window, event loop, input, scheduling
src/p5_py/backends/pyglet_renderer.py        # Pyglet presentation plus parity rendering
src/p5_py/backends/pyglet_webgl_renderer.py  # native depth-tested WEBGL renderer + shader path
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
- image drawing from p5-py `Image` objects, including transformed/cropped destination rectangles
- text drawing and text metrics
- `load_pixels`, `update_pixels`, `blend`, `erase`, and `save_canvas` parity through the renderer surface
- capability flags that advertise only implemented behavior

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

The first native renderer uses Pyglet draw objects for the common path and a deterministic parity surface as a targeted fallback for pixel/compositing semantics. This keeps ordinary interactive drawing fast while preserving correctness before introducing lower-level batching, shader compositing, or custom OpenGL geometry.

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
- `image` and `image_mode`, including affine transforms, center/corner/corners modes, destination scaling, and source-rectangle cropping
- `text`, `text_width`, `text_ascent`, and `text_descent`
- `load_pixels` and `update_pixels`
- `blend_mode`, `blend`, `erase`, and `no_erase`
- `save_canvas`

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
- Pyglet presentation should not double-scale on Retina displays.

`PygletRenderer` receives logical p5 coordinates. Native helper objects map them into Pyglet's bottom-left framebuffer coordinate system, while the parity surface scales the same logical coordinates by `pixel_density` before rasterizing:

```text
framebuffer_x = logical_x * pixel_density
framebuffer_y = physical_height - logical_y * pixel_density
```

The renderer tracks both logical dimensions and physical framebuffer dimensions so `width()`, `height()`, `pixel_density()`, and `display_density()` remain distinct concepts.

## Assets, text, pixel, and export APIs

The native renderer now supports common image and text workflows:

- `image` honors `image_mode(CORNER)`, `image_mode(CENTER)`, and `image_mode(CORNERS)`, plus active affine transforms, destination scaling, and source-rectangle cropping. `translate(x, y); rotate(a); image(sprite, 0, 0, w, h)` rotates around the expected local origin when the image mode places that origin at the intended pivot.
- `image(img, x, y, w, h, sx, sy, sw, sh)` crops the source rectangle before transforming the full destination rectangle.
- `text` uses Pyglet labels for normal rendering and mirrors into the parity surface only after that path has been activated.
- `save_canvas`, `load_pixels`, and `update_pixels` operate on a top-left-oriented physical RGBA buffer.
- `blend_mode`, `blend`, `erase`, and `no_erase` follow the same deterministic compositing rules as the headless backend for primitives, images, and text.

Captures use physical HiDPI dimensions, not logical `width()`/`height()`. Normal `save_canvas`/`load_pixels` read from the native framebuffer; once parity mode is active, they use the parity surface. A later renderer milestone can replace the parity surface with shader/framebuffer passes while keeping these semantics.

## Migration status

1. `PygletRenderer` exists as a concrete implementation of the `Renderer` protocol.
2. Basic primitive rendering constructs and presents Pyglet draw commands on the normal fast path.
3. Transform, path, and curve support is provided by applying p5-py transform matrices and reusing shared geometry flattening before renderer calls.
4. HiDPI logical and physical dimensions are covered by focused unit tests.
5. Image drawing, transformed image pivots, text rendering/metrics, pixel readback/update, compositing, and canvas export are implemented for Pyglet-backed sketches.
6. `PygletBackend` advertises pixel update and all implemented blend constants.
7. `PygletBackend` uses `PygletRenderer` by default and switches to `PygletWebGLRenderer` for `create_canvas(..., renderer=WEBGL)`.
8. The native WEBGL renderer requests a depth-capable context and exposes package-level `load_shader`, `create_shader`, `shader`, and `reset_shader` APIs on that path.
9. The headless Pillow backend remains available for deterministic export and tests.
