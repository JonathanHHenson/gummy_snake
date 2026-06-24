# Images, Pixels, and Assets

## Images

- `load_image(path)`
- `load_image_async(path)`
- `create_image(width, height)`
- `image(img, x, y, width=None, height=None, ...)`
- `image_mode(mode)`
- `image_sampling(mode)`
- `smooth()`
- `no_smooth()`
- `tint(*color)`
- `no_tint()`

Images are loaded by the Rust canvas runtime. There is no Pillow fallback.
Async loader variants are awaitable and useful from `async def preload()` or
`async def setup()` callbacks.

`load_image()` and `create_image()` return the normal Python `Image` type, but
RGBA storage is backed by a Rust-managed `CanvasImage` handle. Drawing images
uses the renderer's canvas-owned sprite path, and mutations such as `set()`,
`update_pixels()`, `resize()`, `mask()`, or `filter()` update the Rust image
handle instead of switching to Python-owned pixel storage. Bulk image-local work
such as resize, mask, filter, crop/copy, and alpha compositing is handled by the
Rust canvas runtime so the public Python API does not run nested per-pixel loops
for normal image sizes.

`smooth()` and `image_sampling(LINEAR)` request linear sampling.
`no_smooth()` and `image_sampling(NEAREST)` request nearest-neighbor sampling.
The renderer may choose the fastest supported path for the current sampling
mode, transform, blend mode, and backend capabilities.
Dense sprite loops are internally batched where ordering permits. Alternating
draws from a small set of images can use a runtime-managed atlas path while
preserving public `image()` semantics, tint, source rectangles, and sampling
mode.

`tint()` multiplies image RGB and alpha during drawing without changing the
source image. `no_tint()` restores untinted drawing, and `push()`/`pop()` preserve
the tint state like other style settings.

Image objects also support Python indexing:

```python
color = img[x, y]
img[x, y] = gs.Color(255, 0, 0)
tile = img[x0:x1, y0:y1]
```

## Pixels

- `load_pixels()`
- `load_pixel_bytes()`
- `update_pixels()`
- `pixels()`
- `pixel_array()`
- `get(...)`
- `set(...)`

Pixel buffers are physical RGBA buffers. When `pixel_density()` is greater than
`1`, the physical pixel size is larger than the logical canvas size.

`load_pixels()` returns a `list[int]`. Use `load_pixel_bytes()`
for performance-sensitive readback when a bytes-like RGBA buffer is enough.
`update_pixels()` accepts the list returned by `load_pixels()` and efficient
buffer-like inputs such as `bytes`, `bytearray`, and `memoryview`.

Performance diagnostics can be enabled when investigating slow pixel or image
paths:

```python
gs.enable_performance_diagnostics()
pixels = gs.load_pixels()
report = gs.performance_diagnostics()
```

The report contains counters and short public-language messages for readback,
pixel list conversion, pixel upload, texture upload/cache hits, and CPU
compositing fallback helpers such as canvas `get()`, `set()`, and `filter()`.
Small canvas `get(x, y)`, `get(x, y, w, h)`, and `set(...)` operations route
through Rust region APIs and avoid reconstructing a full Python `Image` for
region work. Full-canvas `load_pixels()` remains a full physical-buffer readback.

Renderer/runtime counters are available separately:

```python
gs.reset_renderer_performance_counters()
# draw representative frames
report = gs.renderer_performance_counters()
```

Text-heavy sketches can inspect `text_cache_hits`, `text_cache_misses`,
`text_cache_evictions`, and `text_measurements` in that report to spot dynamic
text churn. Dense label overlays should prefer `text_batch()` and `text_widths()`
so repeated labels can stay on the Rust-owned text path with fewer Python bridge
calls. The renderer may use direct GPU glyph-atlas text or cached line textures
internally depending on ordering, style, transform, and font requirements.

For native interactive timing, enable frame pacing diagnostics and inspect
`frame_pacing_diagnostics()` for draw, present, frame-interval, and input-poll
timings.

## Export

- `save_canvas(path=None)`
- `save_frames(path_pattern, count=1, duration=None, callback=None)`
- `save_gif(path, count=1, duration=None)`
- `save_bytes(data, path)`
- `save_json(data, path)`
- `save_strings(lines, path)`
- `create_writer(path)`

`save_frames()` writes a deterministic numbered sequence from the current canvas
state. Patterns may use `{index}`, `{frame}`, or `{frame_count}` placeholders;
without placeholders, files are named with a zero-padded suffix. `save_gif()`
encodes captured frames as an animated GIF when the optional Pillow-backed media
dependency is installed, otherwise it raises `BackendCapabilityError`.

## Data and Text Assets

- `load_json(path)`
- `load_json_async(path)`
- `load_strings(path)`
- `load_strings_async(path)`
- `load_bytes(path)`
- `load_bytes_async(path)`
- `load_font(path)`
- `load_font_async(path)`

## Sound and Media

- `load_sound(path)`
- `load_sound_async(path)`
- `create_audio(...)`
- `create_capture(...)`
- `create_capture_async(...)`
- `create_video(...)`
- `create_video_async(...)`

`load_sound()` returns the public `Sound` wrapper with a Rust-managed
`CanvasSound` handle attached. Sound bytes and duration metadata stay in the
canvas runtime until code asks for Python bytes with `sound.to_bytes()`, while
Python keeps the current friendly `play()`, `pause()`, `stop()`, `volume()`,
`rate()`, and `pan()` controls.

Audio analysis, synthesis, Web Audio contexts, oscillator/envelope/filter APIs,
and microphone/audio capture are not public APIs yet. They remain deferred until
native backends, deterministic DSP tests, and capability reporting are in place.

Some media helpers require installing the `media` extra.
Decoded grayscale, BGR, and BGRA frames are converted to Gummy Snake RGBA image buffers
by the Rust canvas runtime once the optional media dependency supplies a
contiguous frame buffer.

`create_capture()` currently covers native video/camera capture through the
optional media backend. Browser permission APIs and DOM media elements are not
exposed.

3D asset helpers also include awaitable variants:

- `load_model_async(path, normalize=False, package=None)`
- `load_shader_async(vertex_path, fragment_path)`

Wavefront OBJ parsing, normalization, primitive model generation, GPU-ready
triangle packing, and OBJ/STL export are handled by the Rust canvas runtime.
`Model3D` and `Mesh3D` keep Rust-managed handles as canonical storage and expose
immutable Python tuple buffers plus optional lazy NumPy views for inspection and
interchange. Built-in WEBGL drawing reuses retained GPU vertex/index buffers
when GPU acceleration is available, with transform/projection, depth testing,
texture sampling, and material lighting handled by GPU pipelines.
