# p5-py examples

These examples are Python-only sketches using the current p5-py MVP API.

Run an interactive sketch with the default Pyglet backend:

```sh
uv run python examples/basic_shapes.py
```

Run an example without opening a window:

```sh
uv run python examples/basic_shapes.py --backend headless --frames 1
```

Export examples save PNG files when run headlessly or when their draw loop reaches the configured frame count.

On Retina/HiDPI displays, the Pyglet backend renders to a higher-resolution backing buffer while keeping p5 coordinates logical. See `docs/hidpi_rendering.md` for details.

## Examples

- `basic_shapes.py` demonstrates canvas creation, colors, fills, strokes, primitives, arcs, and export.
- `bouncing_ball.py` demonstrates animation state, frame drawing, and simple physics.
- `transforms.py` demonstrates `push`, `pop`, `translate`, `rotate`, `scale`, and angle mode.
- `custom_shape.py` demonstrates `begin_shape`, `vertex`, `quadratic_vertex`, `bezier`, and shape export.
- `vector_noise_flow.py` demonstrates `Vector`, `create_vector`, seeded `random`, `noise`, `map_value`, angle mode, and animation.
- `accelerated_noise_pixels.py` demonstrates the optional Rust-backed `noise()` path plus Pillow `EXCLUSION` blend compositing. It defaults to `headless` so the saved PNG is deterministic whether the Rust extension is installed or the Python fallback is active.
- `image_text_data.py` demonstrates `Image`, `create_image`, image pixel edits, image filters, text drawing/metrics, `load_json`, `save_json`, `load_strings`, and `save_strings`. This example defaults to `headless` because image/text drawing is currently implemented by the Pillow renderer.
- `color_style_filters.py` demonstrates RGB/HSB color modes, `lerp_color`, stroke caps/joins, `image_mode`, and image filters. This example defaults to `headless` because image/text drawing is currently implemented by the Pillow renderer.
- `input_spaceship.py` demonstrates normalized mouse and keyboard callbacks, `key_is_down`, mouse movement deltas, and p5-style input state using the Kenney space shooter assets. It defaults to `pyglet` for interactive input and can export a deterministic headless preview.
- `pixels_blend_export.py` demonstrates `load_pixels`, `pixels`, `update_pixels`, `pixel_array`, `blend_mode`, `blend`, `erase`, `no_erase`, and `save_canvas` using the Kenney space shooter assets. This example defaults to `headless` for deterministic Pillow compositing.
- `webgl_wireframe_prototype.py` demonstrates the epic 100 math-only 3D prototype by projecting a cube with `drawing/prototype3d.py` and drawing the resulting wireframe with the existing 2D API. It compares `PerspectiveProjection` and `OrthographicProjection` side by side.
- `webgl_obj_sound.py` demonstrates the first epic 101 software WEBGL-style implementation by loading `examples/assets/teapot.obj`, rendering it with the new 3D public APIs, and optionally playing `examples/assets/coin-drop-4.wav`.
- `webgl_texture_orbit.py` demonstrates procedural texture mapping on generated 3D primitives and pointer-driven `orbit_control()` on the current software WEBGL path.
- `webgl_native_shader.py` demonstrates the native Pyglet WEBGL follow-on path with `create_shader()`, `shader()`, `Shader3D.set_uniform()`, and a depth-tested cube rendered through the new GPU-backed renderer.
- `video_capture.py` demonstrates the staged native camera API with `create_capture()`, `Capture.read()`, and drawing captured frames through the existing `image()` API. It requires the optional `media` extra and may still fail predictably on headless systems or when camera permissions are denied.
