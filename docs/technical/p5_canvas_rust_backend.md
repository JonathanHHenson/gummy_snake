# `p5_canvas` Rust backend design

## Summary

`p5_canvas` is a planned Rust-powered GPU rendering and native runtime backend for p5-py. It should eventually replace the current split between:

- `HeadlessBackend` + `PillowRenderer` for deterministic script/export/test rendering.
- `PygletBackend` + `PygletRenderer` / `PygletWebGLRenderer` for interactive windows, scheduling, presentation, and input events.

The Python public API should remain unchanged. Sketches should still call `create_canvas()`, drawing functions, `load_pixels()`, `save_canvas()`, input callbacks, `no_loop()`, `redraw()`, and `run()` through the existing `Sketch` and `SketchContext` layers. The new backend should implement the existing `Backend` and `Renderer` protocols from Python, with rendering, presentation, readback/export surfaces, and native runtime responsibilities delegated to a Rust crate named `p5_canvas`.

This design is intentionally incremental, but the next phase is GPU-first. The current Rust canvas implementation has proved the PyO3 bridge, backend adapter, primitive API surface, and native runtime bridge. Before adding more feature surface such as images, text, pixels, compositing, or export, `p5_canvas` should replace the CPU software RGBA surface with a GPU-backed renderer. Existing Pillow and Pyglet backends should remain available as references and fallbacks until `p5_canvas` reaches feature parity and has broad platform validation.

## Goals

- Create a new Rust crate at `crates/p5_canvas` that exposes a Python extension module through PyO3.
- Provide one backend capable of both interactive and headless operation.
- Render all p5 2D graphics through GPU pipelines, including offscreen/headless surfaces.
- Use CPU work only for command preparation, tessellation, font shaping/rasterization into glyph atlases, image decoding/upload, and pixel readback/export staging.
- Preserve p5-py’s existing backend-agnostic public API and `SketchContext` drawing flow.
- Preserve logical canvas dimensions, physical backing-buffer dimensions, `pixel_density()`, and `display_density()` semantics.
- Preserve top-left p5 coordinate semantics at the Python API boundary.
- Provide normalized mouse, keyboard, and eventually touch input events to the existing Python input state and callbacks.
- Provide deterministic offscreen rendering/export suitable for tests and scripts using GPU textures plus explicit readback staging.
- Support native interactive windows and presentation without routing ordinary frames through Pillow or Pyglet.
- Make the Rust backend package-specific and optional during migration, with clear capability errors when unavailable.

## Non-goals for the first implementation

- No JavaScript, HTML, browser DOM, or browser-only APIs.
- No public API redesign for sketch authors.
- No change to p5.js compatibility exclusions such as `p5.XML`, `p5.Table`, or `p5.TableRow`.
- No immediate removal of Pillow/Pyglet until `p5_canvas` has parity and release confidence.
- No requirement to implement sound in the first backend milestone.
- No requirement to implement full WebGL/shader parity in the first 2D replacement milestone.
- No further expansion of the CPU software renderer beyond maintenance needed to preserve already-completed behavior while the GPU renderer is brought online.

## Current backend API surface

The current backend protocol is defined in `src/p5/backends/base.py`:

```python
class Backend(Protocol):
    name: str
    capabilities: BackendCapabilities
    renderer: Renderer

    def create_canvas(self, width: int, height: int, pixel_density: float | None = None, *, renderer: str = P2D) -> None: ...
    def resize_canvas(self, width: int, height: int, pixel_density: float | None = None, *, renderer: str = P2D) -> None: ...
    def display_density(self) -> float: ...
    def run(self, sketch: Sketch, *, max_frames: int | None = None) -> None: ...
    def stop(self) -> None: ...
    def present(self) -> None: ...
```

The current renderer protocol is defined in `src/p5/drawing/renderer.py` and includes:

- canvas sizing: `width`, `height`, `physical_width`, `physical_height`, `pixel_density`, `resize()`
- frame lifecycle: `begin_frame()`, `end_frame()`
- clear/background: `background()`, `clear()`
- 2D primitives: `point()`, `line()`, `polygon()`, `ellipse()`, `arc()`
- images: `draw_image()` with destination rect and optional source rect
- text: `text()`, `text_width()`, `text_ascent()`, `text_descent()`
- pixels and compositing: `load_pixels()`, `update_pixels()`, `blend_region()`
- export: `save()`

`Sketch._draw_frame()` currently owns lifecycle ordering:

1. timing `begin_frame()`
2. context `begin_frame()`
3. renderer `begin_frame()`
4. Python sketch `draw()` and plugin lifecycle hooks
5. renderer `end_frame()`
6. context `end_frame()`
7. increment `frame_count`

`p5_canvas` should preserve this order. The Rust runtime should schedule frame callbacks, but Python should continue to own sketch lifecycle and plugin dispatch.

## Current backend behavior to preserve

### Headless backend

`HeadlessBackend`:

- advertises `headless=True`
- creates a `PillowRenderer`
- defaults pixel density to `1.0` unless explicitly set
- runs one frame by default when `max_frames` is omitted
- loops up to `max_frames`, calls `sketch._draw_frame()`, then `present()`
- has no window, no input events, and `display_density()` returns `1.0`

### Pyglet backend

`PygletBackend`:

- advertises `interactive=True`
- creates a native window and detects display density
- defaults pixel density to display density when the user does not pass `pixel_density`
- schedules draw frames according to `target_frame_rate`
- calls `sketch._draw_frame()` from the Pyglet clock
- presents renderer output from `on_draw`
- normalizes mouse and keyboard events into `MouseEvent` and `KeyboardEvent`
- flips native bottom-left pointer coordinates into top-left logical p5 coordinates
- scales native pointer coordinates and deltas by `pixel_density`
- stops the sketch and event loop on close

### Pillow renderer

`PillowRenderer` is the deterministic reference for:

- logical-to-physical scaling by `pixel_density`
- RGBA physical pixel buffers
- top-left pixel orientation for `load_pixels()` and `save_canvas()`
- text metrics through the active `StyleState`
- image drawing with source cropping, destination scaling, affine transforms, and sampling modes
- blend modes: `BLEND`, `REPLACE`, `ADD`, `DARKEST`, `LIGHTEST`, `DIFFERENCE`, `EXCLUSION`, `MULTIPLY`, `SCREEN`
- `erase()` semantics that reduce destination alpha

### Pyglet renderer

`PygletRenderer` is the current interactive native path. It accepts logical p5 coordinates and maps them into physical framebuffer coordinates, including the y-axis flip. It uses native Pyglet drawing for common primitives and a Pillow parity surface for pixel/compositing features that need deterministic behavior.

`p5_canvas` should eliminate the Pyglet/Pillow split by making Rust own both the fast native path and deterministic offscreen surface semantics through one GPU renderer.

## Proposed architecture

```text
user sketch
  ↓
p5 public API
  ↓
Sketch / SketchContext
  ↓
Python CanvasBackend + CanvasRenderer adapters
  ↓
PyO3 extension module: p5.rust._canvas
  ↓
Rust crate: crates/p5_canvas
  ↓
window/event loop + render engine + offscreen/export surfaces
```

The Python layer remains thin and type-checker friendly:

```text
src/p5/backends/canvas.py        # Backend implementation and runtime callback bridge
src/p5/backends/canvas_renderer.py # Renderer adapter implementing the Python Renderer protocol
src/p5/rust/canvas.py            # Optional import wrapper and capability checks
crates/p5_canvas/                # Rust extension crate
```

Benchmark coverage for the canvas backend lives under `tests/benchmark/test_canvas_backend_perf.py`.
Run it explicitly with:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
```

Interactive canvas-versus-pyglet benchmarking lives under
`tests/benchmark/test_interactive_backend_perf.py`:

```sh
uv run pytest tests/benchmark/test_interactive_backend_perf.py --run-benchmarks -s
```

The registry should eventually expose:

```python
_BACKENDS = {
    "canvas": "p5.backends.canvas:CanvasBackend",
    "headless": "p5.backends.headless:HeadlessBackend",
    "pillow": "p5.backends.headless:HeadlessBackend",
    "pyglet": "p5.backends.pyglet:PygletBackend",
}
```

After parity, default backend selection can change from `pyglet` to `canvas` when the extension is available and runtime capability checks pass. The existing backends should remain addressable by explicit name during at least one migration window. See `docs/technical/canvas_migration_release.md` for the release checklist, benchmark gates, and rollback plan.

## Rust crate layout

Suggested layout:

```text
crates/p5_canvas/
  Cargo.toml
  src/
    lib.rs              # PyO3 module registration
    canvas.rs           # Canvas state, dimensions, pixel density
    color.rs            # RGBA and color conversion helpers
    error.rs            # Rust error types mapped to Python exceptions
    events.rs           # Native-to-p5 event normalization data
    geometry.rs         # Paths, transforms, tessellation helpers
    gpu.rs              # wgpu device, queue, surfaces, textures, pipelines
    commands.rs         # Frame command recording and batching
    tessellation.rs     # CPU path tessellation feeding GPU vertex/index buffers
    image.rs            # Image decode/upload, texture cache, source rectangles, sampling
    renderer.rs         # Renderer trait and command execution
    runtime.rs          # Interactive/headless run loops
    text.rs             # Font loading, shaping, metrics, GPU glyph atlas
    window.rs           # Native window/display-density integration
```

The renderer stack for the next phase should be `wgpu`-first:

- `winit` owns native windows and input.
- `wgpu` owns device selection, swapchain/surface presentation, offscreen textures, render pipelines, texture uploads, and readback staging buffers.
- `lyon` or an equivalent tessellation layer prepares filled and stroked 2D geometry on the CPU, then all primitive rasterization happens in GPU render passes.
- Headless mode renders into GPU textures without creating a visible window where the platform supports a headless adapter/device.
- Export, `load_pixels()`, and parity tests use explicit GPU-to-CPU readback from top-left-oriented RGBA textures.
- Capability flags and fallback errors must distinguish "extension unavailable", "GPU adapter unavailable", and "feature not yet implemented".

Performance-sensitive implementation constraints:

- Ordinary GPU-backed drawing and presentation must not keep a full CPU RGBA mirror up to date. The CPU parity buffer may become stale after `background()`, `clear()`, primitives, images, text, or blend commands; it should be refreshed only by explicit readback/export paths such as `load_pixels()` and `save_canvas()`.
- Full-canvas CPU writes are acceptable only when the GPU path is unavailable or when an explicit pixel API requires CPU-visible data.
- Interactive surface configuration should prefer low-latency present modes where the platform exposes them (`Immediate`, then `Mailbox`, falling back to `Fifo`) and keep queued frame latency minimal. Avoid adding a second sleep/throttle layer on top of a blocking present path for bounded throughput benchmarks.
- Any future asset, text, pixel, blend, or export feature should include a quick check that the common primitive-heavy benchmarks remain faster than the current Pyglet path.

Candidate Rust dependencies to evaluate in the foundation epic:

- `pyo3` for the Python extension boundary, matching the existing `p5_accel` approach.
- `winit` for cross-platform windows and input events.
- `wgpu` for cross-platform GPU rendering, presentation surfaces, offscreen textures, texture upload, and readback.
- `lyon` for path tessellation.
- `image` for PNG/export/image decoding support where needed.
- `cosmic-text`, `fontdue`, or another Rust text stack for text layout and metrics.

Epics 091-092 now establish the first `wgpu` renderer foundation for offscreen/headless rendering. The Rust canvas can initialize a GPU adapter/device/queue, create offscreen textures, record primitive draw commands, tessellate core 2D primitives on the CPU, rasterize them through GPU render passes, and read pixels back only for explicit compatibility APIs such as `load_pixels()` and `save_canvas()`. The previous CPU software renderer remains only as a fallback when a GPU adapter is unavailable or when a feature has not yet moved to the GPU path.

Epic 093 replaces the interim CPU window presenter with direct `winit` + `wgpu::Surface` presentation. New feature PBIs for images, text, pixels, blend modes, and export should target the GPU renderer directly.

Epic 094 expands the canvas feature surface for assets, pixels, compositing, and export. The current implementation keeps ordinary `BLEND` primitive drawing on the GPU command path and synchronizes the CPU-visible RGBA buffer only when a feature needs destination pixels or explicit output:

- `load_pixels()`, `update_pixels()`, and `save_canvas()` use explicit GPU readback/upload and preserve top-left physical RGBA buffers.
- `draw_image()` bridges p5-py `Image` RGBA data into a Rust-side image cache keyed by image identity/version. Rust owns source-rectangle cropping, affine transforms, destination scaling, clipping, image sampling modes, alpha compositing, erase behavior, and advertised blend modes after the first upload for a given image version.
- `blend_region()` supports canvas and external image sources with HiDPI-aware source/destination rectangles.
- `BLEND`, `REPLACE`, `ADD`, `DARKEST`, `LIGHTEST`, `DIFFERENCE`, `EXCLUSION`, `MULTIPLY`, and `SCREEN` are accepted by the canvas backend. Non-`BLEND` compositing and `erase()` render pending GPU commands, composite against the synchronized RGBA buffer, then upload the result back to the GPU texture.
- Interactive presentation renders or updates the offscreen GPU texture first, then presents that texture to the native window. This keeps primitive, image, text, blend, pixel, and export paths on the same visible frame source.
- `text()`, `text_width()`, `text_ascent()`, and `text_descent()` are exposed through a deterministic Pillow glyph-raster bridge that uploads clipped RGBA text overlays through the canvas image path. The native Rust font loading/shaping/glyph-atlas stack remains the next text milestone.

This preserves the primitive-heavy fast path while making pixel/export and compositing APIs explicit synchronization boundaries. It is not yet a complete replacement for the planned Rust glyph atlas.

## Python API design

### `CanvasBackend`

`CanvasBackend` implements the current `Backend` protocol. It owns a `CanvasRenderer` adapter and a Rust runtime/canvas handle.

Responsibilities:

- create or resize the Rust canvas
- select mode: interactive window or headless/offscreen
- report capabilities
- report display density
- schedule calls into `sketch._draw_frame()`
- dispatch Rust-originated input events into `SketchContext`
- stop the native runtime
- present the current frame when interactive

Not responsible for:

- parsing p5-style drawing arguments
- managing style state
- duplicating p5.js aliases
- changing lifecycle/plugin order
- implementing renderer semantics in Python beyond argument conversion and error mapping

### `CanvasRenderer`

`CanvasRenderer` implements the current `Renderer` protocol and delegates each operation to the Rust canvas handle.

Responsibilities:

- keep `width`, `height`, `physical_width`, `physical_height`, and `pixel_density` mirrored from Rust
- convert `Color`, `StyleState`, `Matrix2D`, and image data into Rust-friendly value objects
- call Rust drawing operations in the same order as existing renderers
- map Rust errors into package-specific Python exceptions such as `ArgumentValidationError` and `BackendCapabilityError`
- keep `load_pixels()` returning a Python `list[int]` for compatibility, while Rust internally uses packed RGBA bytes

The initial bridge can be method-based. If call overhead becomes significant, a later optimization can batch draw commands per frame.

## Rust/Python bridge API

A minimal PyO3 surface could expose an internal class like this:

```python
_canvas.Canvas(
    width: int,
    height: int,
    pixel_density: float,
    mode: Literal["interactive", "headless"],
    renderer: Literal["p2d", "webgl"],
)
```

Suggested methods:

```python
canvas.resize(width, height, pixel_density, renderer)
canvas.dimensions() -> tuple[int, int, int, int, float]
canvas.display_density() -> float

canvas.begin_frame()
canvas.end_frame()
canvas.present()
canvas.close()

canvas.background(rgba)
canvas.clear()
canvas.point(x, y, style, matrix)
canvas.line(x1, y1, x2, y2, style, matrix)
canvas.polygon(points, style, matrix, close=True)
canvas.ellipse(x, y, width, height, style, matrix)
canvas.arc(x, y, width, height, start, stop, mode, style, matrix)
canvas.draw_image(image_bytes_or_handle, image_metadata, dx, dy, dw, dh, style, matrix, source)
canvas.text(value, x, y, style, matrix)
canvas.text_width(value, style) -> float
canvas.text_ascent(style) -> float
canvas.text_descent(style) -> float

canvas.load_pixels() -> bytes
canvas.update_pixels(bytes)
canvas.blend_region(source_image_or_none, source_rect, destination_rect, mode)
canvas.save(path)
```

Runtime/event methods should avoid making Rust call arbitrary Python without explicit GIL handling. A safe first design is for Rust to enqueue normalized events and ask Python to drain them from the backend run loop:

```python
canvas.poll_events() -> list[CanvasEvent]
canvas.run_interactive_frame_loop(frame_callback, event_callback, max_frames)
canvas.run_headless_frames(frame_callback, max_frames)
```

Implementation may choose callback or polling based on event-loop constraints, but Python callback execution must happen with the GIL held and must not violate `Sketch._draw_frame()` ordering.

## Data model across the bridge

### Colors

Use packed RGBA values or `(r, g, b, a)` tuples with `0..255` integer channels. Python `Color` conversion should happen in `CanvasRenderer`.

### Style state

`StyleState` should be flattened into a simple bridge payload. Required fields include:

- fill color or `None`
- stroke color or `None`
- stroke weight
- blend mode
- erasing flag
- image sampling mode
- text font identity/path/name
- text size, leading, align x/y

The Rust side should not import or depend on Python `StyleState` internals.

### Transforms

`Matrix2D` should be passed as six floats `(a, b, c, d, e, f)`. Rust should apply p5 logical transforms first, then map logical coordinates to physical pixels and target coordinate systems internally.

### Images

The current `Image` object stores Pillow image data and a version. The first bridge can upload RGBA bytes and dimensions from Python. Rust should cache native image resources by a Python-provided stable image identity plus version to avoid re-uploading unchanged images.

A later image subsystem can move decoding and storage into Rust, but that should not block renderer replacement.

### Pixels

Public compatibility requires `load_pixels()` to return `list[int]` and `update_pixels()` to accept a sequence of integers with length `physical_width * physical_height * 4`. Rust should store and transfer packed top-left-oriented RGBA bytes. Python can convert `bytes` to `list[int]` at the adapter boundary.

## Rendering semantics

`p5_canvas` should treat Pillow as the reference during parity work.

The target renderer is GPU-backed. Python drawing calls should be converted into Rust-side draw commands, batched for the current frame, and executed by `wgpu` render passes against either a window surface texture or an offscreen texture. The renderer must not read pixels back to the CPU during ordinary drawing or presentation. CPU readback is reserved for explicit APIs such as `load_pixels()`, `save_canvas()`, parity tests, and debugging.

Required 2D semantics:

- logical p5 coordinates with top-left origin
- physical backing size of `round(width * pixel_density)` by `round(height * pixel_density)`
- background fills the entire physical canvas
- clear produces transparent RGBA pixels
- primitives honor fill/stroke/no-fill/no-stroke/stroke weight
- paths and polygons honor transforms and close/open stroke behavior
- ellipses and arcs match current flattened geometry within documented tolerances
- images support destination rectangles, source-rectangle cropping, transforms, sampling, and alpha compositing
- text supports metrics and rendering close enough for existing tests, with documented platform tolerances where font stacks differ
- `load_pixels()` and `save_canvas()` return/export top-left-oriented physical RGBA pixels
- `update_pixels()` uploads exactly one physical RGBA buffer
- `blend_region()` supports source canvas and image sources, crop, destination scaling, and all advertised blend modes
- `erase()` reduces destination alpha like the Pillow reference

## Interactive runtime and input semantics

The interactive mode must preserve the current normalized events:

- mouse moved, dragged, pressed, released, clicked, double-clicked, and wheel
- keyboard pressed, released, and typed
- future touch events, advertised only when implemented

Native pointer coordinates must be converted to logical p5 coordinates:

```text
logical_x = native_physical_x / pixel_density
logical_y = logical_height - native_physical_y / pixel_density
```

Pointer deltas must also be scaled and y-flipped:

```text
logical_dx = native_physical_dx / pixel_density
logical_dy = -native_physical_dy / pixel_density
```

The Rust event layer should normalize platform-specific buttons and key codes into p5-py constants before Python updates `InputState`, or it should pass enough structured information for `CanvasBackend` to do that normalization consistently.

### Epic 093 runtime bridge decision

For the interactive runtime/input milestone, the Python adapter uses a polling bridge rather than letting Rust call arbitrary Python from native callbacks directly:

```python
canvas.native_window_available() -> bool
canvas.open_window() -> None
canvas.should_close() -> bool
canvas.poll_events() -> list[dict[str, object]]
```

`CanvasBackend` owns frame scheduling and calls `sketch._draw_frame()` in the existing lifecycle order. Between scheduled frames it drains `poll_events()` and dispatches normalized `MouseEvent` and `KeyboardEvent` objects into `SketchContext`.

The selected native window/input dependency is `winit`. Interactive presentation now uses `wgpu::Surface` objects owned by the GPU renderer, sharing the same command encoding path as headless/offscreen rendering. The bridge reports `native_window_available() == True` on supported desktop targets and exposes `open_window()`, `should_close()`, `poll_events()`, and `present()` through the PyO3 canvas object so unbounded `backend="canvas"` runs can enter the native interactive loop while bounded runs remain offscreen.

Each native window is bound to a `wgpu::Surface`; surface configuration is recreated on resize/display-density changes and when the surface is lost or outdated. `present()` renders the current command buffer directly into the swapchain texture. Ordinary interactive presentation no longer copies a CPU RGBA surface into the window.

Rust-originated event payloads passed through `poll_events()` should use physical window coordinates by default:

```python
{"type": "mouse_pressed", "x": 20, "y": 10, "button": 1, "modifiers": 0}
{"type": "mouse_dragged", "x": 24, "y": 6, "dx": 4, "dy": -8, "button": "left"}
{"type": "mouse_wheel", "x": 24, "y": 6, "scroll_x": 1, "scroll_y": -2}
{"type": "key_pressed", "key": "a"}
{"type": "key_pressed", "code": "ArrowLeft"}
{"type": "key_typed", "text": "é"}
{"type": "resized", "width": 640, "height": 420, "pixel_density": 2.0}
{"type": "close"}
```

If Rust emits already-logical coordinates, include `"coordinates": "logical"` to skip pixel-density scaling and y-axis flipping in Python.

## Headless runtime semantics

Headless mode should preserve current behavior unless intentionally changed later:

- no window is created
- `display_density()` returns `1.0` unless a platform offscreen display density is intentionally supported and documented
- `create_canvas()` defaults `pixel_density` to `1.0`
- `run(max_frames=None)` draws one frame by default
- `run(max_frames=0)` draws no frames
- export and pixel readback work without an interactive event loop

## Capability flags

Initial `CanvasBackend.capabilities` should be conservative. It should advertise only implemented behavior.

Long-term target:

```python
BackendCapabilities(
    interactive=True,
    headless=True,
    text=True,
    images=True,
    pixels=True,
    pixel_readback=True,
    pixel_update=True,
    canvas_export=True,
    mouse=True,
    keyboard=True,
    touch=False,  # until implemented and tested
    paths=True,
    transforms=True,
    blend_modes=frozenset({BLEND, REPLACE, ADD, DARKEST, LIGHTEST, DIFFERENCE, EXCLUSION, MULTIPLY, SCREEN}),
    three_d=False,  # until WEBGL/3D parity is implemented
    shaders=False,
    sound=False,
)
```

Canvas now accepts `create_canvas(..., renderer=WEBGL)` and shader binding/uniform APIs through the existing software-projected 3D layer, presenting the generated 2D draw commands through the Rust canvas renderer. This makes WEBGL-mode primitives, models, materials, lights, and shader API calls available on `backend="canvas"` while preserving the existing deterministic projection semantics.

This is not yet a Rust-native 3D shader pipeline. A future optimization can move projection, depth, materials, and shader execution fully into Rust/WGPU once the public WEBGL behavior and performance gates are stable.

## Build and packaging strategy

The foundation bridge uses two independent PyO3 crates with explicit maturin commands per module. This keeps the existing `p5_accel` extension stable while allowing `p5_canvas` to grow heavier rendering/runtime dependencies independently.

Current layout:

```text
crates/p5_accel/   -> p5.rust._accelerated
crates/p5_canvas/  -> p5.rust._canvas
```

`pyproject.toml` keeps its single `[tool.maturin]` section pointed at `crates/p5_canvas/Cargo.toml`, so default runtime package builds include `p5.rust._canvas`:

```sh
uvx maturin develop --release
uvx maturin build --release
```

Build the optional acceleration extension explicitly:

```sh
uvx maturin develop --release --manifest-path crates/p5_accel/Cargo.toml --module-name p5.rust._accelerated --python-source src --features extension-module
uvx maturin build --release --manifest-path crates/p5_accel/Cargo.toml --module-name p5.rust._accelerated --python-source src --features extension-module
```

Run Rust crate tests directly with Cargo:

```sh
cargo test --manifest-path crates/p5_canvas/Cargo.toml
```

The Python package remains importable when `_canvas` is unavailable. Selecting backend `canvas` without the extension raises `BackendCapabilityError` with the local maturin build command and fallback backend guidance.

## Testing strategy

Use layered validation:

1. Rust unit tests for geometry, tessellation, GPU command encoding boundaries, blending math helpers, coordinate transforms, event normalization, and pixel-buffer/readback operations.
2. Python unit tests for `CanvasRenderer` argument conversion, error mapping, capability flags, and fallback behavior when `_canvas` is missing.
3. Contract tests shared with the current `Renderer` protocol.
4. Headless GPU parity tests comparing readback from `p5_canvas` GPU textures with `PillowRenderer` for deterministic sketches.
5. Input event tests using synthetic Rust-side events and Python `InputState` assertions.
6. Interactive smoke tests for native windows, `wgpu` surface presentation, frame scheduling, resize, close, and display density.
7. Platform CI coverage where practical for macOS, Linux, and Windows.
8. Performance benchmarks that prove common primitive-heavy sketches render faster than the current Pillow and Pyglet paths without per-draw readback, eager CPU parity-buffer updates, or avoidable present-mode throttling.

For bridge changes, keep running:

```sh
uv run ruff check .
uv run pytest
cargo test --manifest-path crates/p5_canvas/Cargo.toml
```

For rendering changes, also keep running:

```sh
uv run python examples/basic_shapes.py --backend headless --frames 1
```

Once `canvas` exists, add smoke commands such as:

```sh
uv run python examples/basic_shapes.py --backend canvas --frames 1
```

For epic 093 runtime/input bridge changes, run focused synthetic tests:

```sh
uv run pytest tests/unit/test_rust_canvas.py
PYO3_PYTHON=/Users/jhenson/zed_projects/p5_py/.venv/bin/python3 cargo test --manifest-path crates/p5_canvas/Cargo.toml
```

After the `winit`/`wgpu` native layer is enabled and `native_window_available()` returns `True`, manually smoke-test:

```sh
uv run python examples/basic_shapes.py --backend canvas
```

Confirm that a native window opens, frames are presented through the GPU surface, close stops the sketch cleanly, resizing updates `width()`, `height()`, and `display_density()`, mouse move/drag/press/release/click/double-click/wheel callbacks receive logical coordinates, and key press/release/type callbacks update `key`, `key_code`, `key_is_pressed`, and `key_is_down()`.

## Migration plan

1. Add `p5_canvas` as an opt-in backend behind explicit `backend="canvas"`.
2. Keep the completed CPU bridge as an interim scaffold only; do not add more feature surface there unless needed to keep existing tests passing.
3. Add the `wgpu` renderer foundation, command buffering, primitive pipelines, offscreen textures, readback, and interactive surface presentation.
4. Make the GPU renderer pass headless rendering contracts without changing defaults.
5. Add images, text, pixels, compositing, export, and blend modes directly on the GPU renderer.
6. Run examples, benchmarks, and documentation against both old and new backends.
7. Switch the default backend to `canvas` only when the GPU renderer meets parity, performance, packaging, and platform criteria.
8. Keep explicit `headless`, `pillow`, and `pyglet` backends during a deprecation window.
9. Later decide whether to remove, deprecate, or retain Pillow/Pyglet as fallback/reference backends.

## Open questions

- Should the renderer bridge send individual method calls or batched draw commands per frame?
- How much font rendering difference is acceptable compared with Pillow/Pyglet?
- Should image decoding move into Rust immediately, or should the first bridge upload bytes from Python `Image` objects?
- What is the earliest milestone where `canvas` can become the default backend?
- Should WEBGL/3D replacement live in `p5_canvas` from the beginning, or in a later renderer module sharing the same runtime/window layer?
- What minimum GPU adapter/features/limits should be required before `canvas` is considered available?
- How should CI handle machines without reliable GPU access while still validating GPU command encoding and readback behavior?
