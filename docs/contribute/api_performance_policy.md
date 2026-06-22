# API Performance Policy

Public APIs should be easy to start with and predictable under load. When those
goals conflict, keep the default path clear and provide an explicit fast path
instead of exposing renderer or Rust internals.

## API Classes

Fast-default APIs are expected to be suitable inside `draw()` and moderate
loops without extra ceremony. This includes primitive drawing, style changes,
transforms, cached image drawing, text measurement with stable style, vector
math, random/noise helpers, and context managers such as `style()`,
`transform()`, and `pushed()`.

Convenience APIs preserve familiar Gummy Snake behavior even when they allocate or
convert data. This includes global-mode dispatch, vector-like argument
normalization, `load_pixels()` returning `list[int]`, `pixels()`, and
`pixel_array()`. Document a faster Pythonic alternative when one exists.

Advanced APIs are supported but may have backend-dependent costs. This includes
blend modes, text shaping/metrics, image sampling modes, software 3D,
shader objects, and model/image asset loading. Keep capability errors explicit
and avoid promising native acceleration unless the backend reports it.
When an advanced path is hot, prefer moving bulk work into `gummy_canvas` or an
existing Rust/GPU path over materializing Python lists, pixel buffers, vertices,
or per-face objects in every frame.

Intentionally slow or diagnostic APIs should be opt-in or visibly named for
inspection. This includes performance diagnostics, full-canvas readback,
canvas-to-image helpers such as `get()`, CPU image filters applied to the
canvas, and benchmark-only utilities.

## Hot-Loop Guidance

`gs.fast()` and `Sketch.fast()` return a frame-local facade for dense 2D loops.
It keeps public Gummy Snake style and transform state but skips repeated global-mode
context lookup and flexible argument normalization for the hottest drawing
calls. Create it inside the scope whose style/transform state should apply:

```python
def draw():
    gs.background(245)
    draw_fast = gs.fast()
    with gs.style(stroke=(20, 80, 160, 180)):
        for x, y, dx, dy in vectors:
            draw_fast.line(x, y, x + dx, y + dy)
```

Use normal global-mode calls in simple sketches and setup code. Use local
bindings or `gs.fast()` in loops that issue hundreds or thousands of primitive,
image, or text-measurement calls per frame.

## Pixels And Images

Prefer renderer-native drawing over full-canvas pixel workflows. Use
`load_pixel_bytes()` for readback when a bytes-like RGBA buffer is sufficient.
Use `update_pixels()` with `bytes`, `bytearray`, or `memoryview` for uploads;
these route through the Rust canvas buffer-protocol path without first forcing a
Python `bytes(...)` copy. The `PixelBuffer` returned by `load_pixels()` tracks a
dirty byte range, and row-aligned changes can upload as a Rust region update
instead of a full-canvas upload.
Images are backed by Rust-managed `CanvasImage` handles. Mutating image pixels
is supported and keeps storage in Rust, but repeated per-frame mutations should
still be treated as texture-update work.

WEBGL model and mesh data are also Rust-managed. Export and built-in model
drawing should use Rust handles rather than Python geometry loops in `draw()`.
When GPU drawing is available, retained model buffers and GPU
transform/projection/depth/material pipelines are the preferred path. Fallback
software projection should remain Rust-owned and keep logical-to-physical
scaling in the canvas runtime.

Captured `begin_shape()` buffers live in Rust. Normal `end_shape()` and
`clip()` calls finalize those buffers directly into Rust canvas draw/clip
operations; Python vertex-list extraction is a compatibility fallback and should
show up in renderer diagnostics if it returns to a hot path.

## Diagnostics

Performance diagnostics are opt-in:

```python
gs.enable_performance_diagnostics()
# draw or inspect
report = gs.performance_diagnostics()
```

Counters use public terms:

- `pixel_readback`: reading canvas pixels back to Python.
- `pixel_list_conversion`: materializing or consuming Python pixel lists.
- `pixel_upload`: sending a full pixel buffer to the canvas.
- `texture_upload`: drawing a new or changed Python `Image`.
- `texture_cache_hit`: drawing an unchanged Python `Image` already seen.
- `cpu_compositing_fallback`: using a canvas helper that copies pixels through
  Python image operations.

Diagnostics must not print by default or mention private Rust implementation
details in user-facing messages.

## Adding Public APIs

When adding an API, classify it in this document's terms before documenting it.
If the API is likely to be used in `draw()`, include an allocation and dispatch
budget in tests or benchmarks. If it is convenience-oriented or diagnostic,
make the cost explicit in reference docs and provide the fast-default route.
