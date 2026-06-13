# Epic 101 KT

## What landed

This pass finishes epic 101 as the software WEBGL/media milestone in `p5_py`:

- `create_canvas(..., renderer=WEBGL)` now activates a software-projected 3D path on the current backends.
- Public 3D APIs now work for the implemented slice:
  - `create_camera()` / `camera()`
  - `perspective()` / `ortho()` / `orbit_control()`
  - `ambient_light()` / `directional_light()` / `point_light()`
  - `normal_material()` / `ambient_material()` / `specular_material()` / `shininess()` / `texture()`
  - `plane()` / `box()` / `sphere()`
  - `model()`
- `load_model()` now loads Wavefront OBJ from:
  - local filesystem paths
  - importable package resources via `package=...`
- `load_sound()` now returns a backend-neutral `Sound` object with:
  - `play()` / `pause()` / `stop()`
  - `volume()` / `rate()` / `pan()`
- `create_audio()` is currently staged as the same local-file playback wrapper as `load_sound()`.

## Key implementation choices

### 3D renderer path

This is **not** a native OpenGL renderer yet.

The current WEBGL-like path is implemented in Python with projection/shading helpers in:

- `src/p5_py/drawing/software3d.py`

`SketchContext` projects/shades faces and then draws them through the existing 2D renderer. Flat-shaded faces still lower to renderer polygons, while textured faces are rasterized on a deterministic software path and composited back through the existing image APIs. This keeps the milestone backend-agnostic, deterministic, and headless-testable.

### Lighting behavior

3D lights are treated as **frame-scoped** and are cleared at the start of each draw frame in `SketchContext.begin_frame()`.

Implication for future work:
- examples/tests should set lights inside `draw()` if they depend on them every frame
- camera/material state currently persists, but lights do not

### OBJ limitations

Current OBJ support is intentionally limited:

- geometry only
- optional normals/texcoords when representable by the current `Mesh3D` shape
- `.mtl` / `usemtl` ignored for now; textures are bound explicitly with `texture()` rather than being pulled from OBJ materials
- no glTF / animation / skinning

Normalization currently centers the model and scales the largest span into `[-1, 1]`.

### Sound limitations

Playback currently wraps `pyglet.media` lazily so loading does not require an audio device.

Still deferred:
- FFT / amplitude / waveform analysis
- synthesis
- `create_video()`
- `create_capture()`

## Important files changed

### New modules
- `src/p5_py/api/advanced.py`
- `src/p5_py/assets/model.py`
- `src/p5_py/assets/sound.py`
- `src/p5_py/drawing/software3d.py`
- `src/p5_py/testing/resources/triangle.obj`
- `docs/technical/epic_101_kt.md`

### Core wiring
- `src/p5_py/context.py`
- `src/p5_py/sketch.py`
- `src/p5_py/api/global_mode.py`
- `src/p5_py/api/compatibility.py`
- `src/p5_py/core/state.py`
- `src/p5_py/backends/headless.py`
- `src/p5_py/backends/pyglet.py`
- `src/p5_py/__init__.py`

### Tests/examples/docs/backlog
- `tests/integration/test_webgl_3d.py`
- `tests/unit/test_model_loading.py`
- `tests/unit/test_sound_playback.py`
- `tests/unit/test_compatibility.py`
- `tests/unit/test_webgl_api.py`
- `examples/webgl_obj_sound.py`
- `examples/webgl_texture_orbit.py`
- `examples/README.md`
- `docs/technical/advanced_3d_media_strategy.md`
- `backlog/101_native_3d_media_implementation/*.toml`
- `backlog/102_native_gpu_webgl_follow_on/*.toml`
- `backlog/103_native_media_video_capture/*.toml`

## Backlog status intent

Marked `DONE` in epic 101:
- `model_loading.toml`
- `sound_playback_analysis.toml`
- `webgl_public_api_primitives.toml`
- `webgl_renderer_activation.toml`

Moved into follow-on epics so epic 101 can close honestly around the shipped software milestone:
- `backlog/102_native_gpu_webgl_follow_on/native_pyglet_depth_renderer.toml`
- `backlog/102_native_gpu_webgl_follow_on/shader_pipeline.toml`
- `backlog/103_native_media_video_capture/native_media_capture.toml`

## Validation already run

- `uv run ruff check .`
- `uv run pytest`
- `uv run python examples/webgl_texture_orbit.py --backend headless --frames 1`
- `uv run python examples/webgl_obj_sound.py --backend headless --frames 1`
- backlog TOML parse check via `tomllib`

All passed.

## Good next steps for the next agent

1. Build the native Pyglet/OpenGL depth-tested follow-on renderer behind the same public APIs.
2. Add shader support only after the native renderer direction is chosen.
3. Expand `create_audio()` beyond simple file playback only if there is a concrete media-element API shape to support.
4. Stage `create_video()` / `create_capture()` with explicit permission, lifecycle, and optional-dependency behavior.
