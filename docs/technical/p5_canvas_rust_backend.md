# `p5_canvas` Rust backend design

## Summary

`p5_canvas` is a planned Rust-powered rendering and runtime backend for p5-py. It should eventually replace the current split between:

- `HeadlessBackend` + `PillowRenderer` for deterministic script/export/test rendering.
- `PygletBackend` + `PygletRenderer` / `PygletWebGLRenderer` for interactive windows, scheduling, presentation, and input events.

The Python public API should remain unchanged. Sketches should still call `create_canvas()`, drawing functions, `load_pixels()`, `save_canvas()`, input callbacks, `no_loop()`, `redraw()`, and `run()` through the existing `Sketch` and `SketchContext` layers. The new backend should implement the existing `Backend` and `Renderer` protocols from Python, with the heavy rendering and native runtime responsibilities delegated to a Rust crate named `p5_canvas`.

This design is intentionally incremental. Existing Pillow and Pyglet backends should remain available as references and fallbacks until `p5_canvas` reaches feature parity and has broad platform validation.

## Goals

- Create a new Rust crate at `crates/p5_canvas` that exposes a Python extension module through PyO3.
- Provide one backend capable of both interactive and headless operation.
- Preserve p5-py’s existing backend-agnostic public API and `SketchContext` drawing flow.
- Preserve logical canvas dimensions, physical backing-buffer dimensions, `pixel_density()`, and `display_density()` semantics.
- Preserve top-left p5 coordinate semantics at the Python API boundary.
- Provide normalized mouse, keyboard, and eventually touch input events to the existing Python input state and callbacks.
- Provide deterministic offscreen rendering/export suitable for tests and scripts.
- Support native interactive windows and presentation without routing ordinary frames through Pillow or Pyglet.
- Make the Rust backend package-specific and optional during migration, with clear capability errors when unavailable.

## Non-goals for the first implementation

- No JavaScript, HTML, browser DOM, or browser-only APIs.
- No public API redesign for sketch authors.
- No change to p5.js compatibility exclusions such as `p5.XML`, `p5.Table`, or `p5.TableRow`.
- No immediate removal of Pillow/Pyglet until `p5_canvas` has parity and release confidence.
- No requirement to implement sound in the first backend milestone.
- No requirement to implement full WebGL/shader parity in the first 2D replacement milestone.

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

`p5_canvas` should eliminate the Pyglet/Pillow split by making Rust own both the fast native path and the deterministic offscreen surface semantics.

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

The registry should eventually expose:

```python
_BACKENDS = {
    "canvas": "p5.backends.canvas:CanvasBackend",
    "headless": "p5.backends.headless:HeadlessBackend",
    "pillow": "p5.backends.headless:HeadlessBackend",
    "pyglet": "p5.backends.pyglet:PygletBackend",
}
```

After parity, default backend selection can change from `pyglet` to `canvas` when the extension is available. The existing backends should remain addressable by explicit name during at least one migration window.

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
    image.rs            # Image upload, source rectangles, sampling
    renderer.rs         # Renderer trait and command execution
    runtime.rs          # Interactive/headless run loops
    text.rs             # Font loading, shaping, metrics, glyph cache
    window.rs           # Native window/display-density integration
```

The exact renderer stack should be selected during implementation, but the design should favor:

- a GPU-backed interactive path for windows and presentation
- an offscreen path that can run without a visible window
- deterministic RGBA readback/export semantics
- explicit feature gates for platform-specific functionality

Candidate Rust dependencies to evaluate in the foundation epic:

- `pyo3` for the Python extension boundary, matching the existing `p5_accel` approach.
- `winit` for cross-platform windows and input events.
- `wgpu` for cross-platform GPU rendering and offscreen textures.
- `lyon` for path tessellation.
- `image` for PNG/export/image decoding support where needed.
- `cosmic-text`, `fontdue`, or another Rust text stack for text layout and metrics.

For epic 092, the first implemented 2D stack is a CPU software RGBA surface inside `crates/p5_canvas`, exposed through PyO3 as `p5.rust._canvas.Canvas`.

Tradeoffs:

- It is deterministic and supports headless readback/export without requiring a window, GPU device, or platform-specific render loop.
- It keeps the Python adapter thin: Python converts `Color`, `StyleState`, and `Matrix2D` into simple bridge payloads, while Rust owns canvas sizing, frame lifecycle, pixel buffers, and primitive rasterization.
- It is intentionally not the final interactive renderer. GPU-backed presentation, native window events, image caching, text shaping, blend-mode parity beyond `BLEND`, and future WEBGL/3D remain separate milestones.
- PNG export uses Rust's `image` crate. No new Python runtime dependency is required.

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

WEBGL/3D and shader support should be a separate milestone. The backend should not claim `three_d=True` or `shaders=True` until it can replace the current `PygletWebGLRenderer` behavior.

## Build and packaging strategy

The foundation bridge uses two independent PyO3 crates with explicit maturin commands per module. This keeps the existing `p5_accel` extension stable while allowing `p5_canvas` to grow heavier rendering/runtime dependencies independently.

Current layout:

```text
crates/p5_accel/   -> p5.rust._accelerated
crates/p5_canvas/  -> p5.rust._canvas
```

`pyproject.toml` keeps its single `[tool.maturin]` section pointed at `crates/p5_accel/Cargo.toml`, so existing acceleration commands continue to build `p5.rust._accelerated` by default:

```sh
uvx maturin develop --release
uvx maturin build --release
```

Build the canvas extension explicitly:

```sh
uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml
uvx maturin build --release --manifest-path crates/p5_canvas/Cargo.toml
```

Run Rust crate tests directly with Cargo:

```sh
cargo test --manifest-path crates/p5_canvas/Cargo.toml
```

The Python package remains importable when `_canvas` is unavailable. Selecting backend `canvas` without the extension raises `BackendCapabilityError` with the local maturin build command and fallback backend guidance.

## Testing strategy

Use layered validation:

1. Rust unit tests for geometry, blending, coordinate transforms, event normalization, and pixel-buffer operations.
2. Python unit tests for `CanvasRenderer` argument conversion, error mapping, capability flags, and fallback behavior when `_canvas` is missing.
3. Contract tests shared with the current `Renderer` protocol.
4. Headless parity tests comparing `p5_canvas` output with `PillowRenderer` for deterministic sketches.
5. Input event tests using synthetic Rust-side events and Python `InputState` assertions.
6. Interactive smoke tests for native windows, frame scheduling, resize, close, and display density.
7. Platform CI coverage where practical for macOS, Linux, and Windows.

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

## Migration plan

1. Add `p5_canvas` as an opt-in backend behind explicit `backend="canvas"`.
2. Make it pass headless rendering contracts without changing defaults.
3. Add interactive window/input support and smoke tests.
4. Reach 2D primitives/image/text/pixel/blend/export parity.
5. Run examples and documentation against both old and new backends.
6. Switch the default backend to `canvas` only when the extension is available and platform behavior is stable.
7. Keep explicit `headless`, `pillow`, and `pyglet` backends during a deprecation window.
8. Later decide whether to remove, deprecate, or retain Pillow/Pyglet as fallback/reference backends.

## Open questions

- Which Rust graphics stack best balances deterministic headless rendering with native interactive performance?
- Should the renderer bridge send individual method calls or batched draw commands per frame?
- How much font rendering difference is acceptable compared with Pillow/Pyglet?
- Should image decoding move into Rust immediately, or should the first bridge upload bytes from Python `Image` objects?
- What is the earliest milestone where `canvas` can become the default backend?
- Should WEBGL/3D replacement live in `p5_canvas` from the beginning, or in a later renderer module sharing the same runtime/window layer?
