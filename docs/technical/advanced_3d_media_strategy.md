# Advanced 3D, model/shader, and sound/media strategy

Epic 100 established the protocol and math-only projection prototype for optional advanced features without disrupting the stable 2D-first runtime. Epic 101 now adds a first complete software milestone: a software-projected WEBGL-style path with orbit controls and texture mapping, backend-neutral OBJ loading, and basic sound playback while native GPU rendering, shaders, video, and capture remain follow-on work. This document records the current implementation status, limitations, and follow-on direction.

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

Use a software-projected WEBGL-style path as the first stable cross-backend milestone. The current implementation projects and shades 3D faces in Python, then draws the result through the existing 2D renderers so headless and Pyglet sketches can share deterministic semantics.

A true native Pyglet/OpenGL renderer is still a planned follow-on milestone. ModernGL can be reconsidered later if raw Pyglet/OpenGL code becomes difficult to maintain or the software path becomes a performance bottleneck.

### Protocol shape

`src/p5/drawing/renderer3d.py` defines backend-agnostic value objects and an optional `Renderer3D` protocol. It includes:

- `Camera3D` and `Projection3D` variants for camera/projection control.
- `Light3D`, `Material3D`, and `Texture3D` for lights, materials, and texture binding.
- `Mesh3D` and `Model3D` for loaded/generated models.
- `Shader3D` and uniform types for Python-native shader loading.
- `Renderer3D` methods for camera, projection, lights, material, texture, shader, model, mesh, and primitive drawing.

The existing 2D `Renderer` protocol remains unchanged. The current milestone keeps 3D projection logic in `SketchContext` plus `src/p5/drawing/software3d.py`, which means existing headless and Pyglet backends can report `three_d=True` without introducing a dedicated GPU renderer yet. The `Renderer3D` protocol remains the target contract for a later native backend.

### Minimal prototype

`src/p5/drawing/prototype3d.py` remains the dependency-free math prototype that validated the hard-to-change semantics first. The public WEBGL-style APIs now build on that work through `src/p5/drawing/software3d.py`, which adds generated primitives, face projection, simple lighting/material shading, and `model()` drawing on the existing renderers.

- cube mesh generation with indexed faces,
- `Camera3D` eye/target/up handling,
- perspective projection,
- orthographic projection,
- near/far clipping,
- p5-style top-left logical screen coordinates.

Example use:

```python
from p5.drawing.prototype3d import cube_model, wireframe_segments
from p5.drawing.renderer3d import Camera3D, PerspectiveProjection, Vec3

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

A future renderer can consume the same `Camera3D`, `Projection3D`, `Mesh3D`, and `Model3D` types while replacing the software projection/shading path with native GPU rendering.

### Future WEBGL-style public API

The public API is intentionally Pythonic and exports snake_case names only:

| Pythonic API | Status |
|---|---|
| `create_canvas(width, height, renderer=WEBGL)` | Implemented on the software 3D path |
| `create_camera()` | Implemented |
| `camera(...)` | Implemented |
| `perspective(...)` | Implemented |
| `ortho(...)` | Implemented |
| `orbit_control()` | Implemented on interactive backends with mouse drag + wheel input |
| `frustum(...)`, `set_camera(...)`, `roll(...)` | Deferred stubs |
| `screen_to_world(...)`, `world_to_screen(...)` | Deferred stubs |
| `debug_mode(...)`, `no_debug_mode()` | Deferred stubs |
| `ambient_light(...)` | Implemented |
| `directional_light(...)` | Implemented |
| `point_light(...)` | Implemented |
| `lights()`, `no_lights()`, `spot_light(...)` | Deferred stubs |
| `image_light(...)`, `panorama(...)` | Deferred stubs |
| `light_falloff(...)`, `specular_color(...)` | Deferred stubs |
| `normal_material()` | Implemented |
| `ambient_material(...)` | Implemented |
| `specular_material(...)` | Implemented |
| `shininess(value)` | Implemented |
| `emissive_material(...)`, `metalness(...)` | Deferred stubs |
| `texture(image)` | Implemented as a software-mapped texture path for UV-capable meshes/primitives |
| `texture_mode(...)`, `texture_wrap(...)` | Deferred stubs |
| `plane(...)`, `box(...)`, `sphere(...)` | Implemented |

## Model loading and shader adaptation

### Model formats

Recommended staged support:

1. **Generated primitives and in-memory `Mesh3D`**. This avoids file-format complexity while camera/projection/rendering semantics stabilize.
2. **Wavefront OBJ** as the first file format. OBJ is text-based, common in p5 examples, and practical to parse with a small Python loader or a lightweight optional loader. It has limited material support, which is acceptable for a first milestone.
3. **glTF 2.0** later for modern models with scene hierarchy, PBR materials, textures, and animation. This should probably use an optional dependency after the renderer has real texture/material support.
4. **STL/PLY** only if there is user demand. They are useful for geometry but do not map as well to p5.js model/shader examples.

No model loader dependency is added in epic 100. When loading is implemented, keep loaders under `src/p5/assets/` and return backend-neutral `Model3D` values.

### Proposed model API

```python
shape = load_model("assets/shape.obj", normalize=True)

create_canvas(640, 480, renderer=WEBGL)
model(shape)
```

Pythonic additions may include:

```python
from p5.drawing.renderer3d import Mesh3D, Model3D

mesh = Mesh3D(vertices=(...), faces=(...))
model = Model3D(meshes=(mesh,))
```

Compatibility notes:

- Browser URL loading is not supported. Paths should be local filesystem paths or package resources.
- Asynchronous browser preload semantics are not copied. Existing `preload()` remains synchronous Python code.
- OBJ material files are currently ignored. `texture()` currently works with explicit p5-py `Image` values and UV-capable meshes/primitives, but it does not yet load `.mtl` textures automatically.
- The current software texture path uses per-triangle affine interpolation. It is deterministic and cross-backend, but it is not a native GPU texture pipeline and does not yet provide perspective-correct sampling, mipmaps, or wrap/filter controls.
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
from p5.drawing.renderer3d import Shader3D

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
- `load_shader`, `create_shader`, `shader`, and `reset_shader` now work on the native Pyglet WEBGL renderer.
- Shader variant helpers such as `create_filter_shader`, `filter_shader`, `create_image_shader`, `create_stroke_shader`, `create_color_shader`, `create_material_shader`, and `normal_shader` are exported as deferred stubs until a native shader variant design exists.
- The current shader target is a desktop OpenGL compatibility profile, so user shaders should prefer compatibility built-ins such as `gl_Vertex`, `gl_ModelViewProjectionMatrix`, and `gl_FragColor` or the auto-populated `u_projection`, `u_view`, `u_model`, and `u_model_view_projection` uniforms.
- Headless/software WEBGL keeps its deterministic fallback path but still reports shader binding as unsupported because there is no native GPU shader backend there.
- WebGPU/storage-buffer/compute names such as `webgpu_context`, `create_storage_buffer`, `update_storage_buffer`, `read_storage_buffer`, `create_compute_shader`, `dispatch_compute`, and `strands` are explicit deferred/excluded stubs. They should not be implemented until the Rust canvas runtime exposes a safe native GPU abstraction with clear synchronization, resource-limit, and packaging semantics.

## Sound and media strategy

### API categories

| Category | Examples | Proposed status |
|---|---|---|
| File-backed audio elements | `create_audio`, local-file playback lifecycle | Partial via the same backend-neutral object as `load_sound` |
| p5.sound-style file playback | `load_sound`, play/pause/stop, volume/rate/pan | Partial using `pyglet.media` |
| p5.sound-style analysis | amplitude, FFT, waveform | Deferred until playback backend and optional numeric dependency are selected |
| p5.sound-style synthesis | oscillators, envelopes, filters | Deferred and optional |
| File-backed video playback | `create_video`, explicit `play()` / `pause()` / `read()` lifecycle | Partial using optional `opencv-python-headless` |
| Camera capture | `create_capture("video")`, explicit `read()` / `close()` lifecycle | Partial using optional `opencv-python-headless` |
| Microphone capture | microphone input and amplitude/FFT | Deferred because of OS permissions and device handling |

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

1. Do not add additional audio dependencies for the first playback milestone.
2. Basic playback now uses `pyglet.media` because it is already installed and can be wrapped behind a backend-neutral `Sound` object.
3. Video playback and camera capture now use an optional `media` extra backed by `opencv-python-headless`. This keeps native media decoding/device access out of the core install while still providing a practical first Python-native API.
4. If microphone analysis/capture becomes a product goal, evaluate an optional `sounddevice`/`soundfile`/NumPy stack or `miniaudio` with explicit extras such as `p5-py[sound]`.
5. Keep sound and media objects backend-neutral so headless tests can use fake players/capture objects without opening real devices.

### Privacy, platform, and dependency implications

Microphone and camera APIs are not simple native equivalents of browser APIs:

- They may trigger macOS, Windows, or Linux permission prompts.
- Device enumeration and default-device behavior vary by platform.
- Headless environments often have no devices and should fail predictably.
- Camera capture likely needs OpenCV, AVFoundation wrappers, GStreamer, or another native media stack.
- Audio capture often needs PortAudio, CoreAudio/WASAPI/ALSA/PulseAudio integration, or a wrapper package.
- Captured audio/video can contain sensitive user data, so future APIs must make device access explicit and document when data leaves memory or is written to disk.

`load_sound` and `create_audio` now load local files into a backend-neutral `Sound` object with `play`, `pause`, `stop`, `volume`, `rate`, and `pan` controls.

`create_video(path)` now stages file-backed video playback through a backend-neutral `Video` object with explicit lifecycle semantics:

- `play()` marks the stream as advancing.
- `pause()` freezes advancement while preserving the last decoded frame.
- `stop()` pauses and seeks back to the beginning.
- `read()` returns the current/next frame as a p5-py `Image`, which can be drawn through the existing `image()` API.
- `looping(True)` restarts at the beginning when the stream reaches the end.
- audio tracks are intentionally ignored in this first milestone.

`create_capture("video", ...)` now stages camera capture through a backend-neutral `Capture` object with explicit lifecycle semantics:

- `read()` returns the latest decoded camera frame as a p5-py `Image`.
- `pause()` / `play()` stop or resume frame acquisition.
- `close()` releases the device explicitly.
- optional `width=` / `height=` requests are forwarded as best-effort capture hints.

Predictable failure behavior is intentional:

- If the optional dependency is missing, both APIs raise `BackendCapabilityError` with install guidance for `p5-py[media]`.
- If a file cannot be opened, `create_video()` raises `ArgumentValidationError`.
- If a camera cannot be opened, `create_capture()` raises `BackendCapabilityError` explaining that headless environments, missing devices, or denied OS permissions are common causes.
- `create_capture("audio")` and other microphone-oriented modes remain deferred with a package-specific `UnsupportedFeatureError`.
- Sound analysis, synthesis, audio input, and audio-context escape hatches remain deferred with package-specific stubs: `create_amplitude`, `create_fft`, `create_audio_in`, `create_audio_input`, `create_oscillator`, `create_envelope`, `create_sound_filter`, and `get_audio_context`.

## Compatibility matrix updates

`p5.api.compatibility.COMPATIBILITY_MATRIX` now classifies the epic 100 areas as:

- `webgl`: `partial`
- `webgl_renderer`: `partial`
- `3d_primitives`: `partial`
- `camera_projection`: `partial`
- `lights_materials`: `partial`
- `textures`: `partial`
- `models`: `partial`
- `shaders`: `partial`
- `sound`: `partial`
- `sound_playback`: `partial`
- `sound_analysis`: `deferred`
- `sound_synthesis`: `deferred`
- `media_playback`: `partial`
- `media_capture`: `partial`
- `webgpu`: `deferred`
- `strands_compute`: `excluded`

Implemented wrappers live in `src/p5/api/advanced.py` and are re-exported through `src/p5/api/compatibility.py` and `src/p5/__init__.py`. Remaining deferred APIs still raise immediate, intentional package-specific errors instead of failing with missing attributes.

## Next implementation milestones

1. Build a true Pyglet-hosted OpenGL renderer behind the existing 3D value objects and capability gates.
2. Add shader compilation, binding, and uniform support.
3. Extend model loading beyond OBJ when there is demand, likely starting with optional glTF support.
4. Add amplitude/FFT analysis and optional synthesis on top of the current sound object design.
5. Extend the staged `create_video` / `create_capture` APIs with tighter sketch-loop integration, optional audio-track support, and broader device/media format coverage once there is product demand.
