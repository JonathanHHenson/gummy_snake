# Backend and Renderer Boundaries

The backend and renderer are intentionally separate because they solve different
problems.

```mermaid
flowchart LR
    Context[SketchContext] --> Backend[CanvasBackend]
    Context --> Renderer[CanvasRenderer]

    Backend --> Runtime[Runtime concerns]
    Renderer --> Drawing[Drawing concerns]

    Runtime --> Windows[window lifecycle]
    Runtime --> Frames[frame scheduling]
    Runtime --> Events[input event polling]
    Runtime --> Shutdown[shutdown]

    Drawing --> Primitives[shapes and paths]
    Drawing --> Assets[images and text]
    Drawing --> Pixels[pixels and export]
    Drawing --> Surface[logical and physical canvas size]
```

## CanvasBackend

`CanvasBackend` is the adapter for runtime concerns. Its public composition root
is `src/gummysnake/backend/canvas.py`; the refactored implementation lives in
focused mixins under `src/gummysnake/backend/_canvas/backend/` for runtime,
events, and frame pacing behavior. It does not decide Gummy Snake API naming
policy and should not contain drawing semantics such as how `rect_mode()`
changes a rectangle.

It is responsible for:

- constructing and owning the `CanvasRenderer`
- checking whether native interactive mode is available
- creating and resizing the canvas through the renderer
- choosing bounded headless execution or interactive execution
- opening native windows when supported
- scheduling frames at the requested frame rate
- polling Rust-originated input events
- normalizing mouse, keyboard, and touch events for `SketchContext`
- stopping and closing renderer resources

Most changes to `CanvasBackend` should be covered by contract tests or focused
unit tests with fake canvas modules/events.

## CanvasRenderer

`CanvasRenderer` is the adapter for drawing concerns. Its public composition root
is `src/gummysnake/backend/canvas_renderer.py`; the refactored implementation
lives in focused mixins under `src/gummysnake/backend/_canvas/renderer/` for
core state/caches, primitives, images, pixels, and text. It should receive
already validated Gummy Snake-level decisions from `SketchContext` and translate
them into Rust canvas calls.

It is responsible for:

- tracking logical canvas dimensions
- tracking physical backing-buffer dimensions
- tracking pixel density
- converting `Color`, style, transform, image, text, and path data into bridge
  payloads
- forwarding primitive drawing to the Rust extension
- reading and updating physical RGBA pixel buffers
- exporting the canvas
- closing runtime canvas resources

Renderer methods should not know about global-mode dispatch, plugin hooks, or
the sketch lifecycle.

## gummysnake.rust.canvas

`gummysnake.rust.canvas` is the Python wrapper around the optional import mechanics and
required runtime capability checks. The PyO3 module is required for current
runtime behavior, but imports can still fail in development environments.

This layer should:

- import `gummysnake.rust._canvas`
- expose a small health-check and capability-check surface
- raise clear Gummy Snake exceptions when the extension is missing
- include rebuild guidance in capability errors

Do not leak raw extension import errors to sketch authors when a package-level
error would explain the problem better.

## Boundary Examples

Use these examples when deciding where code belongs:

| Change | Layer |
| --- | --- |
| Add a new public drawing function | topic module under `src/gummysnake/api/global_mode/`, `src/gummysnake/__init__.py`, `SketchContext` or a `src/gummysnake/_context/` mixin, and maybe `CanvasRenderer`/Rust |
| Change how `rect_mode(CENTER)` computes coordinates | `SketchContext` or geometry helpers |
| Add a new Rust primitive call payload | `src/gummysnake/backend/_canvas/renderer/primitives.py` and `crates/gummy_canvas` |
| Improve missing extension or ABI error text | `gummysnake.rust.canvas` |
| Poll a new native input event | `src/gummysnake/backend/_canvas/backend/events.py` and Rust event support |
| Add a new pixel export format | `src/gummysnake/backend/_canvas/renderer/pixels.py` and `crates/gummy_canvas` |
| Change frame scheduling | `src/gummysnake/backend/_canvas/backend/pacing.py` or `runtime.py` and lifecycle tests |

## Data Flow For A Draw Call

```mermaid
sequenceDiagram
    participant C as SketchContext
    participant S as SketchState
    participant R as CanvasRenderer
    participant X as gummy_canvas

    C->>S: read style, transform, color mode
    C->>C: validate and normalize arguments
    C->>R: draw primitive with normalized payload
    R->>X: call Rust canvas API
    X-->>R: success or renderer error
```

The context owns Gummy Snake behavior. The renderer owns translation. Rust owns actual
rendering.
