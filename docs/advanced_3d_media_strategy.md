# Advanced 3D, model/shader, and sound/media strategy

Epic 100 covers optional advanced features that should not disrupt the stable 2D-first runtime. This document records the proposed direction, current prototype, and compatibility status for WEBGL-like rendering, model/shader APIs, sound, and native media support.

## Goals

- Keep the public API native Python and backend-agnostic.
- Preserve the current 2D renderer/backends without forcing OpenGL, audio, or capture dependencies on every install.
- Provide clear deferred stubs for p5.js APIs that users may try from WEBGL or media examples.
- Define enough protocol surface to support a future native renderer without committing to a concrete dependency prematurely.

## Non-goals

- No JavaScript, HTML, DOM, browser canvas, or WebGL bindings.
- No browser permission model emulation.
- No immediate full p5.js WEBGL parity.
- No mandatory audio, camera, NumPy, OpenGL, or model-loading dependency in the core package.

## WEBGL-like 3D rendering

### Rendering options evaluated

| Option | Fit | Benefits | Risks |
|---|---|---|---|
| Pyglet OpenGL | Best first native path | Pyglet is already a dependency, owns windows/input, and exposes OpenGL context access | Requires careful split between 2D Pyglet renderer state and 3D pipeline state |
| ModernGL | Strong future option | Pythonic OpenGL abstraction, cleaner shader/buffer APIs than raw OpenGL | New dependency and context integration work with Pyglet |
| PyOpenGL | Possible low-level option | Wide OpenGL coverage | Verbose API, runtime dependency complexity, easier to leak backend details |
| VisPy | Possible research option | Higher-level GPU scene/rendering tools | Larger framework and harder to keep p5-style API/backend boundaries small |
| Panda3D/Ursina | Poor core fit | Full 3D engines | Too heavy and conceptually different from p5-py renderer contracts |
| Software/Pillow 3D | Prototype only | Deterministic and dependency-free | Not suitable for real-time shaded 3D |

### Recommendation

Use the existing Pyglet backend as the first native 3D host, but keep 3D rendering behind a separate optional protocol. The next implementation milestone should be a dedicated renderer, likely named `Pyglet3DRenderer` or an extension of `PygletRenderer`, that owns OpenGL buffers, shader programs, depth testing, camera/projection matrices, and 3D resource lifetimes.

ModernGL can be reconsidered if raw Pyglet/OpenGL code becomes difficult to maintain. It should be introduced only after a small Pyglet-hosted prototype shows that the extra dependency materially simplifies geometry, shader, and texture handling.

### Protocol shape

`src/p5_py/drawing/renderer3d.py` defines backend-agnostic value objects and an optional `Renderer3D` protocol. It includes:

- `Camera3D` and `Projection3D` variants for camera/projection control.
- `Light3D`, `Material3D`, and `Texture3D` for lights, materials, and texture binding.
- `Mesh3D` and `Model3D` for loaded/generated models.
- `Shader3D` and uniform types for Python-native shader loading.
- `Renderer3D` methods for camera, projection, lights, material, texture, shader, model, mesh, and primitive drawing.

The existing 2D `Renderer` protocol remains unchanged. Backends that do not implement `Renderer3D` should keep reporting `BackendCapabilities.three_d=False` and raise clear `UnsupportedFeatureError` or `BackendCapabilityError` paths when a future public 3D API is called.

### Minimal prototype

`src/p5_py/drawing/prototype3d.py` is a dependency-free projection prototype. It renders no pixels, but it validates the hard-to-change semantics first:

- cube mesh generation with indexed faces,
- `Camera3D` eye/target/up handling,
- perspective projection,
- orthographic projection,
- near/far clipping,
- p5-style top-left logical screen coordinates.

Example use:

```python
from p5_py.drawing.prototype3d import cube_model, wireframe_segments
from p5_py.drawing.renderer3d import Camera3D, PerspectiveProjection, Vec3

model = cube_model(100)
camera = Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0))
projection = PerspectiveProjection(fov_y=60, near=1, far=1000)
segments = wireframe_segments(
    model,
    camera,
    projection,
    viewport_width=400,
    viewport_height=300,
)
```

A future renderer can consume the same `Camera3D`, `Projection3D`, `Mesh3D`, and `Model3D` types while replacing the wireframe projection with native GPU rendering.

### Future WEBGL-style public API

The eventual Pythonic public API should prefer snake_case, with p5.js aliases where helpful:

| Pythonic API | p5.js alias | Status |
|---|---|---|
| `create_canvas(width, height, renderer=WEBGL)` | `createCanvas(..., WEBGL)` | Deferred |
| `create_camera()` | `createCamera()` | Deferred stub |
| `camera(...)` | `camera(...)` | Deferred stub |
| `perspective(...)` | `perspective(...)` | Deferred stub |
| `ortho(...)` | `ortho(...)` | Deferred stub |
| `orbit_control()` | `orbitControl()` | Deferred stub |
| `ambient_light(...)` | `ambientLight(...)` | Deferred stub |
| `directional_light(...)` | `directionalLight(...)` | Deferred stub |
| `point_light(...)` | `pointLight(...)` | Deferred stub |
| `normal_material()` | `normalMaterial()` | Deferred stub |
| `ambient_material(...)` | `ambientMaterial(...)` | Deferred stub |
| `specular_material(...)` | `specularMaterial(...)` | Deferred stub |
| `shininess(value)` | `shininess(value)` | Deferred stub |
| `texture(image)` | `texture(image)` | Deferred stub |
| `plane(...)`, `box(...)`, `sphere(...)` | same | Deferred stubs |

## Model loading and shader adaptation

### Model formats

Recommended staged support:

1. **Generated primitives and in-memory `Mesh3D`**. This avoids file-format complexity while camera/projection/rendering semantics stabilize.
2. **Wavefront OBJ** as the first file format. OBJ is text-based, common in p5 examples, and practical to parse with a small Python loader or a lightweight optional loader. It has limited material support, which is acceptable for a first milestone.
3. **glTF 2.0** later for modern models with scene hierarchy, PBR materials, textures, and animation. This should probably use an optional dependency after the renderer has real texture/material support.
4. **STL/PLY** only if there is user demand. They are useful for geometry but do not map as well to p5.js model/shader examples.

No model loader dependency is added in epic 100. When loading is implemented, keep loaders under `src/p5_py/assets/` and return backend-neutral `Model3D` values.

### Proposed model API

```python
shape = load_model("assets/shape.obj", normalize=True)

create_canvas(640, 480, renderer=WEBGL)
model(shape)
```

Pythonic additions may include:

```python
from p5_py.drawing.renderer3d import Mesh3D, Model3D

mesh = Mesh3D(vertices=(...), faces=(...))
model = Model3D(meshes=(mesh,))
```

Compatibility notes:

- Browser URL loading is not supported. Paths should be local filesystem paths or package resources.
- Asynchronous browser preload semantics are not copied. Existing `preload()` remains synchronous Python code.
- OBJ material files should be treated as best-effort until a material/texture pipeline exists.
- glTF animation and skinning are out of scope for the first model milestone.

### Shader API

Shaders should be native OpenGL-style shader programs loaded from local files or source strings. The API should not expose browser `WebGLRenderingContext` objects.

Proposed shape:

```python
shader_program = load_shader("shader.vert", "shader.frag")
shader(shader_program)
shader_program.set_uniform("u_time", millis() / 1000)
reset_shader()
```

Pythonic alternatives can use constructors/value objects:

```python
from p5_py.drawing.renderer3d import Shader3D

shader_program = Shader3D(
    vertex_source=vertex_source,
    fragment_source=fragment_source,
    uniforms={"u_scale": 1.0},
)
```

Uniform values should initially support `bool`, `int`, `float`, `Vec3`, flat numeric tuples, and matrix-like tuple-of-tuples. Texture/sampler uniforms should bind `Texture3D` objects after texture support lands.

Compatibility notes:

- GLSL versions differ between WebGL and desktop OpenGL. p5-py should document the selected GLSL target once a renderer is implemented.
- Browser precision qualifiers, attributes, and built-in uniforms may require adaptation.
- Shader compilation errors should be package-specific and include file paths, line numbers when available, and backend details.
- `load_shader`, `create_shader`, `shader`, and `reset_shader` are currently deferred stubs.

## Sound and media strategy

### API categories

| Category | Examples | Proposed status |
|---|---|---|
| Core p5.js media elements | `create_audio`, `create_video`, `create_capture` | Deferred native APIs, not DOM elements |
| p5.sound-style file playback | `load_sound`, play/pause/stop, volume/rate/pan | Deferred |
| p5.sound-style analysis | amplitude, FFT, waveform | Deferred until playback backend and optional numeric dependency are selected |
| p5.sound-style synthesis | oscillators, envelopes, filters | Deferred and optional |
| Microphone capture | microphone input and amplitude/FFT | Deferred because of OS permissions and device handling |
| Camera capture | webcam frames | Deferred because of OS permissions, device handling, and image/video dependency choices |

The core package should not expose browser media elements. Any future media objects should be Python classes with explicit lifecycle methods and no DOM assumptions.

### Audio libraries evaluated

| Candidate | Playback | Analysis | Capture | Dependency notes |
|---|---|---|---|---|
| `pyglet.media` | Basic playback | Limited | No microphone API | Already in dependencies; useful for a small playback prototype |
| `miniaudio` | Good playback/streaming | Raw sample access possible | Possible depending on API/platform | Extra dependency, but comparatively lightweight |
| `sounddevice` + `soundfile` | Good | Good with NumPy | Good microphone support | Native PortAudio/libsndfile concerns and likely NumPy dependency |
| `pygame.mixer` | Basic playback | Limited | No primary capture path | Larger dependency and less aligned with p5-py renderer architecture |
| `pydub`/FFmpeg | Decoding/transcoding | No real-time analysis alone | No | Requires external FFmpeg for common workflows |
| NumPy/SciPy stack | Analysis foundation | Strong | Not by itself | Large dependency; should remain optional if introduced |

Recommendation:

1. Do not add audio dependencies in epic 100.
2. If basic playback is prioritized, prototype with `pyglet.media` first because it is already installed for the interactive backend.
3. If analysis/capture becomes a product goal, evaluate an optional `sounddevice`/`soundfile`/NumPy stack or `miniaudio` with explicit extras such as `p5-py[sound]`.
4. Keep sound objects backend-neutral so headless tests can use fake clocks/sample buffers without opening audio devices.

### Privacy, platform, and dependency implications

Microphone and camera APIs are not simple compatibility aliases for browser APIs:

- They may trigger macOS, Windows, or Linux permission prompts.
- Device enumeration and default-device behavior vary by platform.
- Headless environments often have no devices and should fail predictably.
- Camera capture likely needs OpenCV, AVFoundation wrappers, GStreamer, or another native media stack.
- Audio capture often needs PortAudio, CoreAudio/WASAPI/ALSA/PulseAudio integration, or a wrapper package.
- Captured audio/video can contain sensitive user data, so future APIs must make device access explicit and document when data leaves memory or is written to disk.

For now, `load_sound`, `create_audio`, `create_video`, and `create_capture` are deferred stubs with clear package-specific errors.

## Compatibility matrix updates

`p5_py.api.compatibility.COMPATIBILITY_MATRIX` now classifies the epic 100 areas as:

- `webgl`: `deferred`
- `webgl_renderer`: `deferred`
- `3d_primitives`: `deferred`
- `camera_projection`: `deferred`
- `lights_materials`: `deferred`
- `textures`: `deferred`
- `models`: `deferred`
- `shaders`: `deferred`
- `sound`: `deferred`
- `sound_playback`: `deferred`
- `sound_analysis`: `deferred`
- `sound_synthesis`: `deferred`
- `media_playback`: `deferred`
- `media_capture`: `deferred`

The deferred stubs live in `src/p5_py/api/compatibility.py` and are exported from `src/p5_py/__init__.py` so users receive immediate, intentional errors instead of missing-attribute failures.

## Next implementation milestones

1. Add a renderer-selection path for `create_canvas(..., renderer=WEBGL)` without changing existing 2D behavior.
2. Build a Pyglet-hosted OpenGL triangle/cube spike using the `Renderer3D` protocol values.
3. Add generated 3D primitives (`plane`, `box`, `sphere`) as mesh builders before file loading.
4. Implement OBJ loading into `Model3D` with deterministic tests.
5. Add shader compilation and uniform tests behind a backend capability gate.
6. Prototype basic sound playback with the existing Pyglet dependency before considering optional sound extras.
