# Runtime Model

The runtime is canvas-first and bounded/headless runs still use `p5_canvas`.
There is no supported Pillow or Pyglet fallback.

The runtime starts in Python, creates a Python context, and then uses the Rust
canvas extension for canvas work. Rust can provide native window and input
events, but Python still owns the sketch lifecycle.

```mermaid
sequenceDiagram
    participant S as Sketch.run()
    participant C as SketchContext
    participant B as CanvasBackend
    participant R as CanvasRenderer
    participant X as p5_canvas

    S->>B: create_backend(headless=...)
    S->>C: create context
    S->>S: preload()
    S->>S: setup()
    C->>B: create_canvas()
    B->>R: resize()
    R->>X: allocate canvas
    B->>S: run frames
```

## Startup Sequence

`Sketch.run()` performs these high-level steps:

1. Build a backend with `create_backend(headless=...)`.
2. Create `SketchContext(sketch, backend, plugins=...)`.
3. Bind plugin runtime state.
4. Activate the context so global-mode functions can find it.
5. Dispatch `before_preload` plugin hooks.
6. Run user `preload()`.
7. Dispatch `before_setup` plugin hooks.
8. Run user `setup()`.
9. Ensure a canvas exists, creating the default canvas if needed.
10. Dispatch `after_setup` plugin hooks.
11. Ask the backend to run frames.

The key point is that the backend does not call `setup()` or `draw()` directly.
`Sketch` owns callback order; `CanvasBackend` owns runtime execution.

## Frame Order

```mermaid
flowchart TD
    A[begin timing] --> B[context begin_frame]
    B --> C[renderer begin_frame]
    C --> D[plugin before_draw]
    D --> E[user draw]
    E --> F[plugin after_draw]
    F --> G[renderer end_frame]
    G --> H[context end_frame]
    H --> I[increment frame_count]
    I --> J[present]
```

Keep this ordering intact when changing lifecycle behavior.

## Frame Scheduling

The draw loop checks p5 lifecycle flags before drawing:

- if `state.looping` is true, draw every scheduled frame
- if `state.redraw_requested` is true, draw one frame even when looping is off
- otherwise skip drawing

`no_loop()` sets `state.looping` false. `loop()` sets it true. `redraw()` marks a
single frame as requested. After a frame is drawn, `redraw_requested` is cleared.

Interactive runs schedule frames according to the target frame rate and poll
native events between frames. Headless bounded runs draw a fixed number of frames
as quickly and deterministically as possible.

## Headless vs Interactive

- `headless=True` or `--headless`: bounded offscreen canvas behavior for tests,
  CI, export, and repeatable scripts.
- `headless=False` or `--interactive`: native interactive behavior when the
  installed extension supports it.
- Missing canvas extension or missing native-window support should fail with a
  clear capability error and rebuild guidance.

```mermaid
flowchart TD
    Start[CanvasBackend.run] --> Explicit{interactive requested or inferred?}
    Explicit -->|yes| Native{native window available?}
    Native -->|yes| Interactive[run interactive loop]
    Native -->|no| Error[raise capability error]
    Explicit -->|no| Headless[run bounded headless frames]
```

## Input Dispatch

When native input is available, Rust emits window/input events. `CanvasBackend`
polls those events, normalizes them into Python event dataclasses, updates
`SketchContext.state.input`, and then dispatches optional user callbacks.

```mermaid
sequenceDiagram
    participant X as p5_canvas window
    participant B as CanvasBackend
    participant C as SketchContext
    participant S as Sketch

    X->>B: raw mouse/key/touch event
    B->>C: update input state
    B->>S: dispatch callback name
    S->>S: user callback(event)
```

Input state should always be updated before the user callback runs, so callback
code sees the same values that later p5 input functions return.

## HiDPI

p5py separates logical and physical size:

- `width()` and `height()` return logical dimensions.
- `pixel_density()` controls physical backing scale.
- `load_pixels()` and `update_pixels()` operate on physical top-left RGBA
  buffers.

Do not collapse logical and physical dimensions when touching renderer, export,
pixels, image, or input coordinate code.

## Image And Pixel Ownership

`load_image()` keeps a Rust-managed image asset attached to the public `Image`
object until the user asks for mutable pixel behavior. Drawing that untouched
image should use `Canvas.draw_canvas_image()` so repeated sprite draws can reuse
the Rust texture/cache path without another Python byte upload.

`create_image()` and any mutated `Image` use Python-owned RGBA bytes. Each image
has a stable `cache_key` allocated on the `Image` instance; renderer caches must
use that key rather than `id(image)` so Python object-id reuse cannot draw stale
pixels. Image mutations increment `version`, detach any Rust-managed asset, and
force the next draw to upload the changed pixels under the same stable key.

The Rust canvas image and texture caches are bounded. If cache limits are
changed, keep the lifecycle explicit and preserve tests that draw many transient
images.

`load_pixels()` remains the list-based compatibility API. `load_pixel_bytes()`
is the lower-copy readback path for effects that can work with bytes, and
`update_pixels()` accepts buffer-like inputs such as `bytes`, `bytearray`, and
`memoryview`.

## WEBGL Runtime Status

`create_canvas(..., WEBGL)` currently uses Python software projection and 2D
canvas drawing. It is deterministic and covered by headless tests, but it is not
native accelerated 3D. Backend capabilities therefore distinguish:

- `three_d`: WEBGL mode is accepted.
- `software_three_d`: the Python software 3D path is available.
- `native_three_d`: the native runtime owns 3D geometry and depth rendering.
- `shaders`: shader-style Python API objects are accepted.
- `native_shaders`: user shader programs are handled by the native renderer.

The canvas backend currently reports `three_d=True`, `software_three_d=True`,
`native_three_d=False`, `shaders=True`, and `native_shaders=False`. See
[`native_3d_plan.md`](native_3d_plan.md) before moving 3D drawing into Rust/GPU
code.

## Canvas Creation And Synchronization

Canvas creation is a cross-layer operation:

1. `SketchContext.create_canvas()` validates the renderer kind and backend
   capability.
2. `CanvasBackend.create_canvas()` forwards the requested logical size and pixel
   density to the renderer.
3. `CanvasRenderer.resize()` asks Rust to allocate or resize the canvas.
4. `SketchContext._sync_canvas_state()` copies renderer dimensions back into
   `SketchState.canvas`.

If a change resizes the canvas but does not synchronize `SketchState.canvas`,
`width()`, `height()`, `pixel_density()`, pixels, export, and input coordinates
can disagree.

## Failure Modes To Preserve

- Missing `p5.rust._canvas` should raise a clear backend capability error.
- Requesting interactive mode without native-window support should raise a clear
  capability error.
- Unsupported renderer names should raise `ArgumentValidationError`.
- Requesting `WEBGL` on a backend without 3D support should raise
  `BackendCapabilityError`.
- Native 3D and native shader support should not be implied by software WEBGL
  capability flags.
- Pixel operations should report capability problems explicitly instead of
  failing with unrelated buffer errors.
