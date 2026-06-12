# p5-py Project Plan

## 1. Vision

`p5-py` will be a Pythonic creative coding package inspired by and broadly faithful to p5.js. The goal is to let Python users write sketches with the same approachable mental model as p5.js while using native Python packaging, Python idioms, and native rendering backends.

The project should not be a direct JavaScript port. It should preserve the important p5.js concepts, names, lifecycle, and drawing behavior where practical, but implement them with maintainable Python architecture.

## 2. Scope

### Included

The library should eventually cover the non-browser p5.js feature set:

- Sketch lifecycle: `preload`, `setup`, `draw`, `loop`, `no_loop`, `redraw`, frame timing, cleanup.
- Canvas and renderer management: canvas sizing, resize, pixel density, renderer selection, headless rendering.
- 2D drawing: primitives, paths, curves, shape construction, modes, stroke/fill behavior.
- Color and style: `Color`, RGB/HSB/HSL modes, fill/stroke/background, blend modes, style stack.
- Transforms: matrix stack, translate, rotate, scale, shear, angle modes.
- Math and randomness: p5-compatible helpers where useful, random overloads, gaussian random, Perlin noise.
- Vectors: mutable p5-like vector API plus Python operator support.
- Images and pixels: image loading, drawing, resizing, filters, pixel access, save/export.
- Text and fonts: loading fonts, text drawing, alignment, metrics.
- Input: mouse, keyboard, wheel, event callbacks, lightweight Python event objects.
- Time and date helpers useful for p5 sketch compatibility.
- Optional advanced features: 3D/WebGL-like rendering, shaders, model loading, sound, and touch input.
- Optional Rust acceleration for pure computational hot paths.

### Explicitly excluded

- DOM APIs and browser element helpers.
- HTML and JavaScript source files.
- `p5.XML`.
- `p5.Table` and `p5.TableRow`.
- Browser-specific APIs that have no native Python equivalent.
- Features that are already trivial with Python built-ins may be omitted unless needed for p5 sketch compatibility.

## 3. Guiding principles

### Pythonic but familiar

The public API should make p5.js users feel at home, while still feeling natural to Python users.

Examples:

- Prefer `snake_case` names for canonical Python APIs, such as `create_canvas`, `frame_rate`, and `no_loop`.
- Provide p5.js compatibility aliases where valuable, such as `createCanvas`, `frameRate`, and `noLoop`.
- Support both global sketch mode and object-oriented sketch mode.
- Use Python exceptions with helpful messages rather than silent browser-style behavior.
- Use context managers where they clarify intent, such as `with pushed():`, while still supporting `push()` and `pop()`.

### No browser dependency

The package must be native Python. Rendering, input, media, and packaging should not rely on a browser, JavaScript, or HTML.

### Backend abstraction first

The public API should not know about the rendering backend. Rendering should go through protocols/interfaces so that Pillow/headless, interactive windowed, Skia, OpenGL, or future backends can be swapped without changing sketch code.

### Simple before complete

The project should grow in tiers:

1. A strong 2D-first runtime.
2. Rich 2D fidelity and pixel support.
3. Optional Rust acceleration.
4. Advanced 3D/media support.

### Clear compatibility policy

Every p5.js feature should be classified as one of:

- Supported.
- Pythonic equivalent.
- Partial.
- Deferred.
- Excluded.

Unsupported APIs should fail with clear package-specific errors rather than failing indirectly.

## 4. Proposed package architecture

```text
p5_py/
  __init__.py
  app.py
  sketch.py
  context.py
  constants.py
  exceptions.py

  api/
    __init__.py
    global_mode.py
    aliases.py
    compatibility.py

  core/
    lifecycle.py
    state.py
    settings.py
    color.py
    vector.py
    math.py
    random.py
    noise.py
    transform.py
    geometry.py

  drawing/
    canvas.py
    renderer.py
    primitives.py
    paths.py
    shapes.py
    styles.py
    text.py

  backends/
    __init__.py
    base.py
    headless.py
    pillow.py
    pyglet.py
    opengl.py

  events/
    dispatcher.py
    input_state.py
    mouse.py
    keyboard.py
    touch.py

  assets/
    loaders.py
    image.py
    font.py
    model.py
    sound.py

  pixels/
    buffer.py
    filters.py
    blend.py
    export.py

  plugins/
    base.py
    registry.py
    hooks.py

  rust/
    __init__.py
    _accelerated.pyi

  testing/
    golden.py
    fixtures.py
    headless.py
```

Optional Rust code should live outside the Python source tree but inside the project:

```text
crates/
  p5_accel/
    Cargo.toml
    src/
      lib.rs
      color.rs
      geometry.rs
      noise.rs
      pixels.rs
      vector.rs
```

## 5. Current API coverage

The 040-060 backlog epics are implemented for the deterministic headless/Pillow path:

- Color, style, constants, and transform APIs include RGB/HSB/HSL color modes, style stacks, stroke/fill mutation, affine transforms, angle modes, and p5-style aliases.
- Math, random, noise, and vector APIs include p5-style helpers, seedable random/gaussian values, deterministic Perlin-style noise, and mutable `Vector` objects with Python operators.
- Assets include local image loading, `Image` manipulation (`get`, `set`, `copy`, `resize`, `mask`, and common filters), image drawing with `image_mode`, lightweight text/JSON helpers, font loading, text drawing, alignment, leading, and metrics.

The native Pyglet renderer currently capability-gates image, text, pixel-read/write, and export APIs. Use the headless backend for deterministic image/text/pixel workflows until native support is added. Epic `061_native_pyglet_assets_text_export` tracks the native Pyglet implementation work, including adding `save_canvas` support through framebuffer capture/readback.

## 6. Runtime design

### Sketch modes

`p5-py` should support two styles.

Function-style sketching:

```python
from p5_py import *

def setup():
    create_canvas(600, 400)


def draw():
    background(240)
    circle(mouse_x, mouse_y, 40)

run()
```

Object-oriented sketching:

```python
from p5_py import Sketch

class MySketch(Sketch):
    def setup(self):
        self.create_canvas(600, 400)

    def draw(self):
        self.background(240)
        self.circle(self.mouse_x, self.mouse_y, 40)

MySketch().run()
```

The object-oriented API should be the internal foundation. Global mode should delegate to a current `SketchContext`.

### Lifecycle

The runtime should follow this flow:

1. Create or discover a `Sketch` instance.
2. Create a `SketchContext` with state, renderer, backend, asset registry, input state, and timing.
3. Call `preload()` synchronously before setup.
4. Initialize the backend and canvas.
5. Call `setup()` once.
6. Enter the backend event loop.
7. Each frame, process events, update timing, run draw callbacks if looping, render, and present.
8. On stop, release resources and close windows/files.

### State model

The context should own:

- Canvas dimensions and pixel density.
- Current renderer.
- Fill, stroke, text, and blend style state.
- Transform matrix stack.
- Shape construction state.
- Color mode and angle mode.
- Frame count, delta time, target FPS, and start time.
- Mouse and keyboard state.
- Asset registry.
- Pixel buffer state.

## 6. Rendering strategy

### Initial backend sequence

1. **Headless backend** for tests and deterministic rendering.
2. **Pillow raster backend** for early 2D output, image export, and golden tests.
3. **Interactive Pyglet backend** for native windows, event handling, and interactive presentation.
4. **Native Pyglet renderer** to replace the current Pillow bridge for interactive drawing. See `docs/native_pyglet_renderer.md`.
5. **OpenGL/3D backend** for WebGL-like features if the 2D core is stable.

### Renderer protocol

The renderer interface should include drawing primitives, path drawing, text, images, transform application, pixel operations, clipping, blend modes, and frame presentation. Backends may report capabilities so unsupported features can produce clear errors.

### Fidelity priorities

Early rendering fidelity should prioritize:

- Coordinate behavior.
- Shape modes.
- Fill and stroke order.
- Stroke caps and joins.
- Transform stack behavior.
- Color mode conversion.
- Deterministic image output for tests.

## 7. API coverage roadmap

### Tier 1: 2D sketching core

Deliver a useful package that can run simple sketches:

- Runtime and global API.
- Canvas creation and resizing.
- Basic primitives: point, line, rect, square, ellipse, circle, triangle, quad, arc.
- Background, fill, stroke, no fill/stroke, stroke weight.
- Rect/ellipse modes, angle modes, common constants.
- Push/pop, translate, rotate, scale.
- Mouse and keyboard input.
- Math helpers, random, time helpers.
- Vector class.
- Basic image loading/drawing.
- Basic text drawing.
- Headless and one interactive backend.

### Tier 2: Rich 2D parity

Add expressive p5 features:

- Shape builder: begin/end shape, vertex, contours.
- Curves and Beziers.
- Full RGB/HSB/HSL color modes and interpolation.
- Text metrics and font loading.
- Image manipulation and filters.
- Pixel access with Pythonic NumPy-friendly paths.
- Blend modes, clipping, erase/no erase.
- Save/export APIs.
- Perlin noise fidelity.

### Tier 3: Advanced rendering and media

Implement or clearly defer advanced p5 features:

- WebGL-like renderer.
- 3D primitives, cameras, projections, lighting, materials, textures.
- Model loading.
- Shader API adapted for Python/OpenGL.
- Sound playback, analysis, and synthesis if included.
- Touch input where backend/platform support exists.

## 8. Rust acceleration plan

Rust should be optional, contained, and purely computational. Python fallback implementations must exist for every accelerated feature.

Good candidates:

- Perlin/simplex noise.
- Pixel filters.
- Blend modes.
- Color conversion.
- Geometry tessellation.
- Matrix/vector hot paths.
- Path flattening.

Recommended build pipeline:

- Use `maturin` with `pyo3` when the first Rust extension is introduced.
- Keep Rust module name under `p5_py.rust._accelerated`.
- Expose narrow, typed functions rather than large mutable objects.
- Add parity tests comparing Python and Rust results.
- Keep the package installable in pure Python mode if Rust build tooling is unavailable.

## 9. Testing and quality strategy

### Test layers

- Unit tests for color, vector, math, transforms, state, argument parsing, and events.
- Renderer contract tests that every backend must pass.
- Golden image tests from the deterministic headless backend.
- Compatibility tests for p5-style aliases and overloads.
- Rust/Python parity tests.
- Integration examples that execute without crashing.

### Tooling

Recommended tools:

- `pytest` for testing.
- `ruff` for linting and formatting.
- `mypy` or `pyright` for static typing.
- `pre-commit` for local checks.
- `maturin` for Rust extension builds when needed.
- `uv` or standard `pip` workflows for developer setup.

## 10. Documentation strategy

Documentation should include:

- Getting started guide.
- Sketch lifecycle guide.
- Pythonic API guide.
- p5.js compatibility guide.
- Unsupported and excluded API list.
- Backend selection guide.
- Image and pixel guide.
- HiDPI rendering guide.
- Native Pyglet renderer design guide.
- Rust acceleration guide.
- Contributor architecture guide.
- Examples gallery using Python only.

## 11. Release strategy

### Version 0.1

- Package skeleton.
- Runtime lifecycle.
- Headless/Pillow renderer.
- Basic 2D primitives.
- Color/style basics.
- Math/random/vector basics.
- Initial tests and documentation.

### Version 0.2

- Interactive backend.
- Mouse/keyboard input.
- Text and images.
- More p5 compatibility aliases.
- Golden image tests.

### Version 0.3

- Rich paths and curves.
- Pixel buffer and filters.
- Blend modes.
- Perlin noise.
- Rust acceleration scaffold.

### Version 0.4+

- 3D renderer exploration.
- Sound/media exploration.
- Plugin ecosystem.
- Broader compatibility matrix.

## 12. Major risks

| Risk | Impact | Mitigation |
|---|---:|---|
| Trying to implement all p5.js features at once | High | Deliver in tiers with explicit compatibility statuses. |
| Backend lock-in | High | Define renderer and backend protocols early. |
| WebGL fidelity | High | Treat 3D as a separate advanced milestone. |
| Pixel performance | Medium | Provide NumPy-friendly buffers and Rust acceleration. |
| Font/text differences across platforms | Medium | Use tolerances in tests and document backend differences. |
| Overloaded p5 APIs becoming unmaintainable | Medium | Centralize argument parsing and validation. |
| JavaScript naming conflicting with Python conventions | Medium | Canonical snake_case plus compatibility aliases. |
| Rust complicating installation | Medium | Keep Rust optional with Python fallbacks. |

## 13. Definition of done for planning phase

This planning phase is complete when:

- A detailed project plan exists in `docs/`.
- Backlog epics are organized by major product areas.
- Each backlog item is represented as a TOML PBI under `backlog/<epic_name>/<pbi_name>.toml`.
- Each PBI includes a title, user story, acceptance criteria, priority, and ordered implementation tasks.
- The backlog covers foundation, API compatibility, 2D rendering, state systems, math/vector/noise, assets, input, pixels, Rust acceleration, advanced features, documentation, testing, and release work.
