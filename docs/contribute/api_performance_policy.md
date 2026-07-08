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
normalization, `load_pixels()` returning `PixelBuffer`, `pixels()`, and
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

`gs.fast()` and `Sketch.fast()` return a frame-local facade for dense drawing
loops, including batched 2D primitives/images/text and supported 3D camera, light,
transform, material, and model calls. It keeps public Gummy Snake style and
transform state but skips repeated global-mode context lookup and flexible
argument normalization for the hottest drawing calls. Create it inside the scope
whose style/transform state should apply:

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
image, text-measurement, transform, or model calls per frame.

Current optimized hot paths include compact line batches, mixed primitive
batches with per-record style/transform data, transformed sprite/image atlas
batches, batched cached-text atlas fallback for ordered overlays, procedural GPU
instances for supported fill-only primitives, retained replay for static
unchanged command streams, direct Rust shape/clip finalization, and retained GPU
model buffers for supported WEBGL draws. Preserve the public API shape while
keeping these paths visible through renderer diagnostics when changing code from
the renderer performance epics.

## ECS Simulation Hot Paths

Simulation-heavy sketches should prefer `gummysnake.ecs` plans over Python loops
when component data changes every frame. Dataclass components/resources define
Rust storage schemas; decorated `@ecs.system_plan` functions build logical
`ecs.Action` trees; Rust compiles and executes those plans against canonical
component/resource columns. Python should only construct plans, validate schemas,
expose typed views for draw or UDF boundaries, and run explicit `@ecs.system` or
`@ecs.udf` callbacks.

Prefer ECS expressions/actions for hot math:

- use `ecs.set`, `ecs.do_in_order`, `ecs.do_in_parallel`, `ecs.when`,
  `.otherwise()`, `ecs.for_each`, `ecs.exists`, grouped aggregates, events, and
  `ecs.spatial` relations before adding Python iteration;
- use `ecs.spatial.neighbors`, `join`, and `overlaps` with generic algorithms
  such as `HashGrid`, `Quadtree`, `Octree`, or `HilbertCurve` instead of bespoke
  sketch-specific kernels;
- use `iter_component_fields()` for draw-side readback of selected columns, not
  persistent Python mirrors of all component data;
- keep UDFs for side effects, external APIs, or genuinely Python-only operations,
  and count `ecs_udf_calls` when making performance claims;
- treat unsupported non-UDF physical-plan nodes as errors to fix in the ECS DSL or
  Rust executor, not as a reason to add Python fallback execution.

For deterministic performance, `do_in_order()` is serial and observes earlier
writes, while `do_in_parallel()` is for independent snapshot-style action groups.
Strict mode should reject ambiguous duplicate writes; non-strict mode may use
last-write-wins with warnings and diagnostics.

## Pixels And Images

Prefer renderer-native drawing over full-canvas pixel workflows. Use
`load_pixel_bytes()` for readback when a bytes-like RGBA buffer is sufficient.
Use `update_pixels()` with `bytes`, `bytearray`, or `memoryview` for uploads;
these route through the Rust canvas buffer-protocol path without first forcing a
Python `bytes(...)` copy. Re-uploading the exact fresh `load_pixel_bytes()`
payload is a no-op and should be skipped by the runtime. The `PixelBuffer`
returned by `load_pixels()` tracks a dirty byte range, and row-aligned changes
can upload as a Rust region update instead of a full-canvas upload.
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
- `pixel_noop_upload_skip`: skipping an exact fresh pixel-byte re-upload.
- `pixel_region_upload`: sending a dirty `PixelBuffer` region instead of a full canvas.
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
